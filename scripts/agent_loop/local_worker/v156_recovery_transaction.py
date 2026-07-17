#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from v156_recovery_common import *


def execute_recovery(
    cfg: dict[str, Any],
    auth: Authorization,
    *,
    source_worker: Path,
    control_plane_root: Path = ROOT,
    hooks: dict[str, Callable[..., None]] | None = None,
) -> dict[str, Any]:
    auth = validate_authorization(auth)
    if cfg.get("repo") != REPO or cfg.get("base_branch", BASE_BRANCH) != BASE_BRANCH:
        raise ValueError("repository or base branch mismatch")
    worker.require_scheduled_task_disabled_for_trusted(cfg, "trusted v1.5.6 dynamic post-merge recovery")

    control_plane_root = control_plane_root.resolve()
    source_worker = source_worker.resolve()
    expected_source = (control_plane_root / "scripts" / "agent_loop" / "local_worker" / "agent_worker.py").resolve()
    if source_worker != expected_source or not source_worker.is_file():
        raise ValueError("source worker must come from the exact approved control-plane checkout")
    checkout_head = require_sha("local control-plane HEAD", git(["rev-parse", "HEAD"], control_plane_root))
    if checkout_head != auth.approved_control_plane_commit:
        raise ValueError("local control-plane checkout HEAD mismatch")
    if auth.approved_control_plane_commit != auth.approved_merged_base:
        raise ValueError("control-plane checkout is not the approved merged base")
    source_sha = worker.sha256_file(source_worker).upper()
    if source_sha != auth.approved_worker_sha256:
        raise ValueError("approved worker SHA mismatch")

    if live_base_sha(cfg) != auth.approved_merged_base:
        raise ValueError("live base differs from approved merged base")
    require_contains(cfg, auth.approved_feature_head, auth.approved_merged_base, "merged base does not contain feature HEAD", strictly_ahead=True)
    require_contains(cfg, auth.pre_pr10_base, auth.approved_feature_head, "feature HEAD is not descended from pre-PR10 base")
    require_contains(cfg, auth.historical_base, auth.pre_pr10_base, "pre-PR10 base is not descended from historical base")
    require_contains(cfg, auth.pre_pr10_base, auth.approved_merged_base, "merged base is not descended from pre-PR10 base")

    state_path = Path(cfg["install_root"]) / "state" / "issue-5.json"
    original_state = state_path.read_bytes()
    state = json.loads(original_state.decode("utf-8-sig"))
    spec = state.get("spec") or {}
    if state.get("front") != FRONT or int(state.get("issue_number") or 0) != ISSUE or int(state.get("pr_number") or 0) != PR:
        raise ValueError("local state identity mismatch")
    if int(state.get("cycles") or -1) != 3 or state.get("status") != "WAITING_GITHUB":
        raise ValueError("local state is not the preserved failed cycle")
    if state.get("trusted_v154_resume_done") is not True or state.get("trusted_v155_recovery_done") or state.get("trusted_v156_post_merge_recovery_done"):
        raise ValueError("local recovery flags mismatch")
    if state.get("last_head_sha") != auth.expected_old_pr_head or spec.get("expected_base_sha") != auth.historical_base:
        raise ValueError("local state SHA mismatch")
    worker.validate_v155_recovery_event_chronology(cfg, auth.historical_base, auth.expected_old_pr_head, state.get("repo_dir"))
    repo_dir = Path(str(state.get("repo_dir") or ""))
    validate_local_pilot_repo(repo_dir, auth.expected_old_pr_head)

    issue = worker.gh_json(["issue", "view", str(ISSUE), "--repo", REPO, "--json", "number,state,body,author,labels,url"])
    pr = worker.gh_json(["pr", "view", str(PR), "--repo", REPO, "--json", "number,url,state,isDraft,headRefName,headRefOid,baseRefName,body,labels"])
    if str(issue.get("state") or "").upper() != "OPEN" or str(pr.get("state") or "").upper() != "OPEN" or pr.get("isDraft") is not True:
        raise ValueError("Issue #5 or PR #6 is not open/Draft")
    if exact_phase(issue) != {"loop:repairing"} or exact_phase(pr) != {"loop:token-exhausted"}:
        raise ValueError("Issue/PR phase mismatch")
    if pr.get("headRefName") != WORK_BRANCH or pr.get("headRefOid") != auth.expected_old_pr_head or pr.get("baseRefName") != BASE_BRANCH:
        raise ValueError("PR #6 branch, HEAD or base mismatch")
    remote_issue_spec = issue_spec(issue.get("body") or "")
    if remote_issue_spec.get("expected_base_sha") != auth.historical_base:
        raise ValueError("Issue #5 expected base moved")
    if pr_expected_base(pr.get("body") or "") != auth.historical_base:
        raise ValueError("PR #6 expected base moved")
    if worker.pr_changed_files(REPO, PR) != PILOT_FILES:
        raise ValueError("PR #6 diff is not exactly the two pilot files")
    if len(legacy_token_comments(cfg)) != 3:
        raise ValueError("expected exactly three legacy TOKEN_EXHAUSTED comments")

    install_root = Path(cfg["install_root"])
    installed_worker = install_root / "worker" / "agent_worker.py"
    if not installed_worker.is_file():
        raise FileNotFoundError(str(installed_worker))
    event_path = install_root / "reports" / "worker-events.jsonl"
    original_event = event_path.read_bytes() if event_path.exists() else None
    original_worker = installed_worker.read_bytes()
    original_issue_body = issue.get("body") or ""
    original_pr_body = pr.get("body") or ""
    original_issue_labels = worker.labels(issue)
    original_pr_labels = worker.labels(pr)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reports = install_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    state_backup = state_path.with_suffix(state_path.suffix + f".bak-v156-dynamic-{stamp}")
    worker_backup = reports / f"agent_worker.py.bak-v156-dynamic-{stamp}"
    issue_backup = reports / f"issue-5-body.bak-v156-dynamic-{stamp}.md"
    pr_backup = reports / f"pr-6-body.bak-v156-dynamic-{stamp}.md"
    event_backup = reports / f"worker-events.jsonl.bak-v156-dynamic-{stamp}"
    state_backup.write_bytes(original_state)
    worker_backup.write_bytes(original_worker)
    issue_backup.write_text(original_issue_body, encoding="utf-8")
    pr_backup.write_text(original_pr_body, encoding="utf-8")
    if original_event is not None:
        event_backup.write_bytes(original_event)

    pushed = False
    issue_body_may_have_changed = False
    pr_body_may_have_changed = False
    issue_labels_may_have_changed = False
    pr_labels_may_have_changed = False
    new_head: str | None = None
    primary: Exception | None = None
    try:
        shutil.copy2(source_worker, installed_worker)
        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:
            raise ValueError("installed worker SHA mismatch")
        fire(hooks, "after_worker_install", installed=installed_worker)

        if live_base_sha(cfg) != auth.approved_merged_base:
            raise ValueError("live base moved during transaction")
        if remote_branch_sha(repo_dir, WORK_BRANCH) != auth.expected_old_pr_head:
            raise ValueError("remote pilot branch moved during transaction")
        git(["fetch", "origin", BASE_BRANCH, WORK_BRANCH], repo_dir)
        if git(["rev-parse", f"origin/{BASE_BRANCH}"], repo_dir) != auth.approved_merged_base:
            raise ValueError("fetched base does not equal approved merged base")
        if git(["rev-parse", f"origin/{WORK_BRANCH}"], repo_dir) != auth.expected_old_pr_head:
            raise ValueError("fetched pilot branch moved")

        old_blobs = {path: git(["rev-parse", f"{auth.expected_old_pr_head}:{path}"], repo_dir) for path in PILOT_FILES}
        git(["checkout", "-B", WORK_BRANCH, auth.expected_old_pr_head], repo_dir)
        git(["config", "user.name", "AI Vault Kimi Worker"], repo_dir)
        git(["config", "user.email", "ai-vault-worker@users.noreply.github.com"], repo_dir)
        git(["merge", "--no-ff", "--no-edit", auth.approved_merged_base], repo_dir)
        new_head = require_sha("new pilot HEAD", git(["rev-parse", "HEAD"], repo_dir))
        for path, old_blob in old_blobs.items():
            if git(["rev-parse", f"{new_head}:{path}"], repo_dir) != old_blob:
                raise ValueError(f"base merge modified pilot artifact: {path}")
        changed = sorted(line for line in git(["diff", "--name-only", auth.approved_merged_base, new_head], repo_dir).splitlines() if line)
        if changed != PILOT_FILES:
            raise ValueError(f"advanced pilot diff is not exact: {changed}")
        fire(hooks, "after_local_merge", repo_dir=repo_dir, new_head=new_head)

        git(["push", "origin", f"HEAD:refs/heads/{WORK_BRANCH}"], repo_dir)
        pushed = True
        fire(hooks, "after_push", repo_dir=repo_dir, new_head=new_head)

        issue_body_may_have_changed = True
        worker.update_issue_body(REPO, ISSUE, replace_issue_base(original_issue_body, auth.approved_merged_base))
        fire(hooks, "after_issue_body")
        pr_body_may_have_changed = True
        worker.update_pr_body(REPO, PR, replace_pr_base(original_pr_body, auth.approved_merged_base))
        fire(hooks, "after_pr_body")

        state = worker.seed_terminal_notification_keys_from_comments(cfg, state, "loop:token-exhausted", "Maximum Kimi cycles reached. Human audit required.")
        next_spec = dict(state.get("spec") or {})
        next_spec["expected_base_sha"] = auth.approved_merged_base
        state.update(cycles=2, status="WAITING_GITHUB", last_head_sha=new_head, spec=next_spec, local_retry_count=0, terminal_notified=False, trusted_v156_post_merge_recovery_done=True, worker_version="1.5.6", updated_utc=utc())
        fire(hooks, "before_state_write", state_path=state_path, state=state)
        worker.save_json(state_path, state)
        fire(hooks, "after_state_write")
        issue_labels_may_have_changed = True
        worker.set_phase(REPO, ISSUE, "loop:repairing")
        fire(hooks, "after_issue_label")
        pr_labels_may_have_changed = True
        worker.set_phase(REPO, PR, "loop:repairing")
        fire(hooks, "after_pr_label")

        reloaded = worker.load_json(state_path)
        issue_after = worker.gh_json(["issue", "view", str(ISSUE), "--repo", REPO, "--json", "number,state,body,labels"])
        pr_after = worker.gh_json(["pr", "view", str(PR), "--repo", REPO, "--json", "number,state,isDraft,headRefName,headRefOid,baseRefName,body,labels"])
        fire(hooks, "before_postcondition_readback")
        if int(reloaded.get("cycles") or -1) != 2 or reloaded.get("status") != "WAITING_GITHUB" or reloaded.get("last_head_sha") != new_head:
            raise ValueError("state postcondition failed")
        if (reloaded.get("spec") or {}).get("expected_base_sha") != auth.approved_merged_base or reloaded.get("trusted_v156_post_merge_recovery_done") is not True:
            raise ValueError("state base/recovery postcondition failed")
        if exact_phase(issue_after) != {"loop:repairing"} or issue_spec(issue_after.get("body") or "").get("expected_base_sha") != auth.approved_merged_base:
            raise ValueError("Issue #5 postcondition failed")
        if exact_phase(pr_after) != {"loop:repairing"} or pr_after.get("headRefOid") != new_head or pr_expected_base(pr_after.get("body") or "") != auth.approved_merged_base:
            raise ValueError("PR #6 postcondition failed")
        if remote_branch_sha(repo_dir, WORK_BRANCH) != new_head:
            raise ValueError("remote pilot HEAD postcondition failed")
        if worker.sha256_file(installed_worker).upper() != auth.approved_worker_sha256:
            raise ValueError("installed worker postcondition failed")

        success_fields = {
            "historical_base": auth.historical_base,
            "pre_pr10_base": auth.pre_pr10_base,
            "approved_feature_head": auth.approved_feature_head,
            "approved_merged_base": auth.approved_merged_base,
            "approved_control_plane_commit": auth.approved_control_plane_commit,
            "old_pr_head": auth.expected_old_pr_head,
            "new_pr_head": new_head,
            "installed_worker_sha": auth.approved_worker_sha256,
            "state_backup": str(state_backup),
            "worker_backup": str(worker_backup),
            "issue_body_backup": str(issue_backup),
            "pr_body_backup": str(pr_backup),
            "event_backup": str(event_backup) if original_event is not None else None,
            "task_disabled": worker.scheduled_task_disabled(),
            "canonical_touched": False,
            "kimi_executed": False,
            "once_executed": False,
        }
        fire(hooks, "before_success_event", fields=success_fields)
        append_event_transactional(cfg, "trusted_v156_dynamic_post_merge_recovery", success_fields, hooks)
        return {"status": "POST_MERGE_RECOVERED_EXISTING_PR_V156", **success_fields}
    except Exception as exc:
        primary = exc
        rollback: dict[str, Any] = {"worker": False, "state": False, "local_branch": False, "remote_branch": False, "issue_body": False, "pr_body": False, "issue_labels": False, "pr_labels": False, "event_log": False, "task_disabled": worker.scheduled_task_disabled(), "owner_action_required": False}
        try:
            installed_worker.write_bytes(original_worker)
            rollback["worker"] = True
        except Exception as rb_exc:
            rollback["worker_error"] = bounded(rb_exc)
        try:
            state_path.write_bytes(original_state)
            rollback["state"] = True
        except Exception as rb_exc:
            rollback["state_error"] = bounded(rb_exc)
        try:
            git(["reset", "--hard", auth.expected_old_pr_head], repo_dir)
            rollback["local_branch"] = True
        except Exception as rb_exc:
            rollback["local_error"] = bounded(rb_exc)
        if pushed and new_head:
            try:
                git(["push", f"--force-with-lease=refs/heads/{WORK_BRANCH}:{new_head}", "origin", f"{auth.expected_old_pr_head}:refs/heads/{WORK_BRANCH}"], repo_dir)
                rollback["remote_branch"] = True
            except Exception as rb_exc:
                actual_remote = "unknown"
                try:
                    actual_remote = remote_branch_sha(repo_dir, WORK_BRANCH)
                except Exception:
                    pass
                rollback.update(owner_action_required=True, remote_error=bounded(rb_exc), expected_lease_sha=new_head, actual_remote_sha=actual_remote, attempted_rollback_target=auth.expected_old_pr_head)
        if issue_body_may_have_changed:
            try:
                worker.update_issue_body(REPO, ISSUE, original_issue_body)
                rollback["issue_body"] = True
            except Exception as rb_exc:
                rollback["issue_body_error"] = bounded(rb_exc)
        if pr_body_may_have_changed:
            try:
                worker.update_pr_body(REPO, PR, original_pr_body)
                rollback["pr_body"] = True
            except Exception as rb_exc:
                rollback["pr_body_error"] = bounded(rb_exc)
        if issue_labels_may_have_changed:
            try:
                worker.restore_label_set(REPO, ISSUE, original_issue_labels)
                rollback["issue_labels"] = True
            except Exception as rb_exc:
                rollback["issue_labels_error"] = bounded(rb_exc)
        if pr_labels_may_have_changed:
            try:
                worker.restore_label_set(REPO, PR, original_pr_labels)
                rollback["pr_labels"] = True
            except Exception as rb_exc:
                rollback["pr_labels_error"] = bounded(rb_exc)
        rollback["event_log"] = restore_event_log(event_path, original_event)
        payload = {"primary_error": bounded(primary), "rollback": rollback, "historical_base": auth.historical_base, "pre_pr10_base": auth.pre_pr10_base, "approved_feature_head": auth.approved_feature_head, "approved_merged_base": auth.approved_merged_base, "old_pr_head": auth.expected_old_pr_head, "attempted_new_pr_head": new_head}
        best_effort_rollback_event(cfg, payload)
        if rollback["owner_action_required"]:
            raise OwnerActionRequired(payload) from primary
        raise


def run_locked(cfg: dict[str, Any], auth: Authorization, *, source_worker: Path, control_plane_root: Path = ROOT, hooks: dict[str, Callable[..., None]] | None = None) -> dict[str, Any]:
    lock = Path(cfg["install_root"]) / "state" / "worker.lock"
    with worker.SingleInstanceLock(lock):
        return execute_recovery(cfg, auth, source_worker=source_worker, control_plane_root=control_plane_root, hooks=hooks)
