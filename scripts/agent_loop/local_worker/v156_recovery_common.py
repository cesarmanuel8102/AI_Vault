#!/usr/bin/env python3
"""Shared authorization and rollback primitives for v1.5.6 recovery."""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
WORKER_SOURCE = ROOT / "scripts" / "agent_loop" / "local_worker" / "agent_worker.py"
_spec = importlib.util.spec_from_file_location("agent_worker_v156_runtime", WORKER_SOURCE)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load worker module: {WORKER_SOURCE}")
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)

REPO = "cesarmanuel8102/AI_Vault"
BASE_BRANCH = "codex/own-capital-sustainable-return"
ISSUE = 5
PR = 6
FRONT = "PILOT-KIMI-CODEX-20260716-091529"
WORK_BRANCH = "agent/pilot-20260716-091529"
HISTORICAL_BASE = "220fa3b043d2cae8f8b084c0617027d754963335"
PRE_PR10_BASE = "a6bbcc528cddab29677ef7125948cec92d772ef1"
OLD_PR_HEAD = "c94fa5c995684a8db2ecbec09ceef1cfb30c55c5"
PILOT_FILES = sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class OwnerActionRequired(RuntimeError):
    """Rollback could not safely restore a remotely moved branch."""

    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        super().__init__(json.dumps({"status": "OWNER_ACTION_REQUIRED", **evidence}, sort_keys=True))


class Authorization:
    def __init__(
        self,
        historical_base: str,
        pre_pr10_base: str,
        approved_feature_head: str,
        approved_merged_base: str,
        approved_control_plane_commit: str,
        expected_old_pr_head: str,
        expected_front: str,
        expected_pr_number: int,
        expected_work_branch: str,
        approved_worker_sha256: str,
    ) -> None:
        self.historical_base = historical_base
        self.pre_pr10_base = pre_pr10_base
        self.approved_feature_head = approved_feature_head
        self.approved_merged_base = approved_merged_base
        self.approved_control_plane_commit = approved_control_plane_commit
        self.expected_old_pr_head = expected_old_pr_head
        self.expected_front = expected_front
        self.expected_pr_number = expected_pr_number
        self.expected_work_branch = expected_work_branch
        self.approved_worker_sha256 = approved_worker_sha256


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_sha(name: str, value: str) -> str:
    normalized = str(value or "").lower()
    if not SHA_RE.fullmatch(normalized):
        raise ValueError(f"{name} must be a full lowercase 40-character SHA")
    return normalized


def bounded(value: Any, limit: int = 1500) -> str:
    return str(value or "")[-limit:]


def fire(hooks: dict[str, Callable[..., None]] | None, name: str, **context: Any) -> None:
    callback = (hooks or {}).get(name)
    if callback is not None:
        callback(**context)


def git(args: list[str], cwd: Path, *, check: bool = True) -> str:
    return worker.run(["git", *args], cwd=cwd, check=check).strip()


def remote_branch_sha(repo_dir: Path, branch: str) -> str:
    output = git(["ls-remote", "--heads", "origin", f"refs/heads/{branch}"], repo_dir)
    rows = [line.split() for line in output.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) < 2:
        raise ValueError(f"Unable to resolve exact remote branch {branch}")
    return require_sha(f"remote branch {branch}", rows[0][0])


def live_base_sha(cfg: dict[str, Any]) -> str:
    ref = worker.gh_json(["api", f"repos/{cfg['repo']}/git/ref/heads/{BASE_BRANCH}"])
    return require_sha("live base", ((ref.get("object") or {}).get("sha") or ""))


def require_contains(cfg: dict[str, Any], ancestor: str, descendant: str, label: str, *, strictly_ahead: bool = False) -> None:
    result = worker.gh_json(["api", f"repos/{cfg['repo']}/compare/{ancestor}...{descendant}"])
    status = str(result.get("status") or "")
    allowed = {"ahead"} if strictly_ahead else {"ahead", "identical"}
    if status not in allowed:
        raise ValueError(f"{label}: compare status {status!r}")


def issue_spec(body: str) -> dict[str, Any]:
    match = worker.SPEC_RE.search(body or "")
    if not match:
        raise ValueError("Issue body missing AGENT_LOOP_SPEC")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise ValueError("AGENT_LOOP_SPEC must be an object")
    return value


def replace_issue_base(body: str, new_base: str) -> str:
    match = worker.SPEC_RE.search(body or "")
    if not match:
        raise ValueError("Issue body missing AGENT_LOOP_SPEC")
    spec = json.loads(match.group(1))
    spec["expected_base_sha"] = new_base
    block = "<!-- AGENT_LOOP_SPEC " + json.dumps(spec, separators=(",", ":"), ensure_ascii=False) + " AGENT_LOOP_SPEC -->"
    return body[: match.start()] + block + body[match.end() :]


def pr_expected_base(body: str) -> str:
    matches = re.findall(r"EXPECTED_BASE_SHA:\s*([0-9a-fA-F]{40})", body or "")
    if len(matches) != 1:
        raise ValueError(f"PR body must contain exactly one EXPECTED_BASE_SHA; found {len(matches)}")
    return matches[0].lower()


def replace_pr_base(body: str, new_base: str) -> str:
    if pr_expected_base(body) == new_base:
        return body
    return re.sub(r"EXPECTED_BASE_SHA:\s*[0-9a-fA-F]{40}", f"EXPECTED_BASE_SHA: {new_base}", body, count=1)


def exact_phase(obj: dict[str, Any]) -> set[str]:
    return worker.labels(obj) & worker.PHASE_LABELS


def legacy_token_comments(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    expected = "maximum kimi cycles reached. human audit required."
    matches: list[dict[str, Any]] = []
    for comment in worker.issue_comments(cfg["repo"], PR):
        text = re.sub(r"\s+", " ", str(comment.get("body") or "").strip()).lower()
        if "[agent-loop][token_exhausted]" in text and expected in text:
            matches.append(comment)
    return matches


def validate_local_pilot_repo(repo_dir: Path, expected_head: str) -> None:
    if not repo_dir.exists() or not repo_dir.is_dir():
        raise ValueError("state.repo_dir missing or not a directory")
    if git(["rev-parse", "--is-inside-work-tree"], repo_dir).lower() != "true":
        raise ValueError("state.repo_dir is not a Git worktree")
    if git(["rev-parse", "HEAD"], repo_dir) != expected_head:
        raise ValueError("local pilot HEAD mismatch")
    if git(["status", "--porcelain"], repo_dir):
        raise ValueError("local pilot worktree is dirty")
    if git(["rev-list", f"{expected_head}..HEAD"], repo_dir):
        raise ValueError("local pilot contains a commit above expected HEAD")
    tracking = git(["rev-parse", f"origin/{WORK_BRANCH}"], repo_dir)
    if tracking != expected_head:
        raise ValueError("local origin tracking ref mismatch")
    if remote_branch_sha(repo_dir, WORK_BRANCH) != expected_head:
        raise ValueError("remote pilot branch mismatch")


def validate_authorization(auth: Authorization) -> Authorization:
    values = {
        "historical_base": require_sha("historical_base", auth.historical_base),
        "pre_pr10_base": require_sha("pre_pr10_base", auth.pre_pr10_base),
        "approved_feature_head": require_sha("approved_feature_head", auth.approved_feature_head),
        "approved_merged_base": require_sha("approved_merged_base", auth.approved_merged_base),
        "approved_control_plane_commit": require_sha("approved_control_plane_commit", auth.approved_control_plane_commit),
        "expected_old_pr_head": require_sha("expected_old_pr_head", auth.expected_old_pr_head),
    }
    if values["historical_base"] != HISTORICAL_BASE:
        raise ValueError("historical base is not the approved preserved-pilot base")
    if values["pre_pr10_base"] != PRE_PR10_BASE:
        raise ValueError("pre-PR10 base mismatch")
    if values["expected_old_pr_head"] != OLD_PR_HEAD:
        raise ValueError("old pilot HEAD mismatch")
    if auth.expected_front != FRONT or auth.expected_work_branch != WORK_BRANCH or int(auth.expected_pr_number) != PR:
        raise ValueError("front, PR or work-branch mismatch")
    if values["approved_control_plane_commit"] != values["approved_merged_base"]:
        raise ValueError("approved control-plane commit must equal approved merged base")
    return Authorization(**values, expected_front=auth.expected_front, expected_pr_number=int(auth.expected_pr_number), expected_work_branch=auth.expected_work_branch, approved_worker_sha256=str(auth.approved_worker_sha256).upper())


def append_event_transactional(cfg: dict[str, Any], kind: str, fields: dict[str, Any], hooks: dict[str, Callable[..., None]] | None) -> None:
    path = Path(cfg["install_root"]) / "reports" / "worker-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = json.dumps({"timestamp_utc": utc(), "kind": kind, **fields}, ensure_ascii=False) + "\n"
    callback = (hooks or {}).get("partial_event_append")
    if callback is not None:
        callback(path=path, record=record)
        return
    with path.open("a", encoding="utf-8") as stream:
        stream.write(record)


def restore_event_log(path: Path, original: bytes | None) -> bool:
    try:
        if original is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
        return True
    except Exception:
        return False


def best_effort_rollback_event(cfg: dict[str, Any], payload: dict[str, Any]) -> None:
    try:
        path = Path(cfg["install_root"]) / "reports" / "worker-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"timestamp_utc": utc(), "kind": "trusted_v156_dynamic_post_merge_rollback", **payload}, ensure_ascii=False) + "\n")
    except Exception:
        pass
