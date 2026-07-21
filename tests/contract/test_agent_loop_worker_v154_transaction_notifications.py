#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker154_tx", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
BASE = "baab482a829a233cdffc25e558ff22eb6d335e69"
HEAD = "686533399b9789fdd5737a3c69ab1a6c6469a4bd"
BRANCH = "agent/pilot-20260716-091529"
REPO = "cesarmanuel8102/AI_Vault"
OWNER = "cesarmanuel8102"

SPEC = {
    "schema_version": 1,
    "front_id": FRONT,
    "repo": REPO,
    "owner": OWNER,
    "base_branch": "codex/own-capital-sustainable-return",
    "expected_base_sha": BASE,
    "work_branch": BRANCH,
    "objective": "pilot",
    "test_profile": "pilot",
    "max_kimi_cycles": 3,
    "allowed_paths": sorted(worker.PROFILE_ALLOWED_PATHS["pilot"]),
    "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS),
}


def install_fake(monkey, fail_at=None, issue_state="OPEN", pr_state="OPEN", pr_draft=True, issue_phase="loop:repairing", pr_phase="loop:repairing", diff=None, comments=None):
    store = {
        "issue_body": "<!-- AGENT_LOOP_SPEC " + json.dumps(SPEC, separators=(",", ":")) + " AGENT_LOOP_SPEC -->",
        "pr_body": "EXPECTED_BASE_SHA: 4722de72388c9d4d1bd2659dfc8cbfe214c1772e",
        "issue_labels": {issue_phase},
        "pr_labels": {pr_phase},
        "comments": list(comments or []),
        "events": [],
        "comment_posts": [],
        "phase_calls": [],
        "mutated": False,
    }
    original = {
        "gh_json": worker.gh_json,
        "update_issue_body": worker.update_issue_body,
        "update_pr_body": worker.update_pr_body,
        "edit_labels": worker.edit_labels,
        "pr_changed_files": worker.pr_changed_files,
        "scheduled_task_disabled": worker.scheduled_task_disabled,
        "event": worker.event,
        "comment": worker.comment,
        "issue_comments": worker.issue_comments,
        "save_json": worker.save_json,
    }
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            if fail_at == "convergence_readback" and store["mutated"]:
                return {"number": 5, "state": issue_state, "author": {"login": OWNER}, "body": store["issue_body"], "labels": [{"name": "loop:blocked"}], "url": "https://github.com/x/issues/5"}
            return {"number": 5, "state": issue_state, "author": {"login": OWNER}, "body": store["issue_body"], "labels": [{"name": x} for x in sorted(store["issue_labels"])], "url": "https://github.com/x/issues/5"}
        if args[:2] == ["pr", "view"]:
            if fail_at == "convergence_readback" and store["mutated"]:
                return {"number": 6, "url": "https://github.com/x/pull/6", "state": pr_state, "isDraft": pr_draft, "headRefName": BRANCH, "headRefOid": HEAD, "baseRefName": "codex/own-capital-sustainable-return", "body": store["pr_body"], "labels": [{"name": "loop:blocked"}]}
            return {"number": 6, "url": "https://github.com/x/pull/6", "state": pr_state, "isDraft": pr_draft, "headRefName": BRANCH, "headRefOid": HEAD, "baseRefName": "codex/own-capital-sustainable-return", "body": store["pr_body"], "labels": [{"name": x} for x in sorted(store["pr_labels"])]}
        if args[:1] == ["api"]:
            return {"object": {"sha": BASE}}
        raise AssertionError(args)
    def fake_update_issue(repo, number, body):
        if fail_at == "issue_body": raise RuntimeError("issue body fail")
        store["mutated"] = True
        store["issue_body"] = body
    def fake_update_pr(repo, number, body):
        if fail_at == "pr_body": raise RuntimeError("pr body fail")
        store["mutated"] = True
        store["pr_body"] = body
    def fake_edit(repo, number, add=(), remove=()):
        target = "issue_labels" if int(number) == 5 else "pr_labels"
        store["phase_calls"].append((int(number), tuple(add), tuple(remove)))
        if fail_at == "issue_label" and int(number) == 5: raise RuntimeError("issue label fail")
        if fail_at == "pr_label" and int(number) == 6: raise RuntimeError("pr label fail")
        store["mutated"] = True
        store[target] = (store[target] - set(remove)) | set(add)
    worker.gh_json = fake_gh
    worker.update_issue_body = fake_update_issue
    worker.update_pr_body = fake_update_pr
    worker.edit_labels = fake_edit
    worker.pr_changed_files = lambda repo, number: sorted(diff if diff is not None else worker.PROFILE_ALLOWED_PATHS["pilot"])
    worker.scheduled_task_disabled = lambda: True
    worker.event = lambda cfg, kind, **fields: store["events"].append((kind, fields))
    worker.comment = lambda repo, number, body: (store["comment_posts"].append((int(number), body)), store["comments"].append({"body": body}))
    worker.issue_comments = lambda repo, number: list(store["comments"])
    def fake_save_json(path, data):
        if fail_at == "state_save": raise RuntimeError("state save fail")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    worker.save_json = fake_save_json
    return store, original


def restore(original):
    for name, value in original.items():
        setattr(worker, name, value)


def make_install(tmp: Path):
    (tmp / "state").mkdir(parents=True)
    (tmp / "worker").mkdir(parents=True)
    (tmp / "worker/agent_worker.py").write_text("old worker", encoding="utf-8")
    state = {
        "issue_number": 5,
        "front": FRONT,
        "spec": dict(SPEC),
        "repo_dir": str(tmp / "repo"),
        "pr_number": 6,
        "pr_url": "https://github.com/x/pull/6",
        "cycles": 3,
        "last_head_sha": HEAD,
        "status": "loop:token-exhausted",
        "terminal_notified": False,
    }
    path = tmp / "state/issue-5.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {"install_root": str(tmp), "repo": REPO, "owner": OWNER, "base_branch": "codex/own-capital-sustainable-return", "max_kimi_cycles_default": 3, "test_profiles": {"pilot": []}}, path


def run_resume_case(fail_at=None, **kwargs):
    with tempfile.TemporaryDirectory() as td:
        cfg, state_path = make_install(Path(td))
        original_state = state_path.read_bytes()
        store, original = install_fake(worker, fail_at=fail_at, **kwargs)
        try:
            try:
                worker.trusted_resume_issue5_pr6_v154(cfg, 5, FRONT, BASE, 6, BRANCH, HEAD)
                outcome = "PASS"
            except Exception as exc:
                outcome = str(exc)
            state_bytes = state_path.read_bytes()
            worker_text = (Path(td) / "worker/agent_worker.py").read_text(encoding="utf-8")
            return outcome, store, original_state, state_bytes, worker_text
        finally:
            restore(original)

# 1 and 20: successful resume sets local WAITING_GITHUB and second resume rejected.
with tempfile.TemporaryDirectory() as td:
    cfg, state_path = make_install(Path(td))
    store, original = install_fake(worker)
    try:
        worker.trusted_resume_issue5_pr6_v154(cfg, 5, FRONT, BASE, 6, BRANCH, HEAD)
        st = json.loads(state_path.read_text(encoding="utf-8"))
        assert st["status"] == "WAITING_GITHUB" and st["cycles"] == 2
        assert store["issue_labels"] == {"loop:repairing"} and store["pr_labels"] == {"loop:repairing"}
        try:
            worker.trusted_resume_issue5_pr6_v154(cfg, 5, FRONT, BASE, 6, BRANCH, HEAD)
            raise AssertionError("second resume should fail")
        except Exception as exc:
            assert "already completed" in str(exc)
    finally:
        restore(original)

# 2-6: rollback restores state/body/labels/worker after failures following mutation.
for failure in ("state_save", "issue_label", "pr_label", "convergence_readback"):
    outcome, store, before, after, worker_text = run_resume_case(fail_at=failure)
    assert failure.replace("_", " ").split()[0] in outcome or "fail" in outcome or "phase mismatch" in outcome, (failure, outcome)
    assert before == after, failure
    assert store["issue_labels"] == {"loop:repairing"}, failure
    assert store["pr_labels"] == {"loop:repairing"}, failure
    assert "4722de72388c9d4d1bd2659dfc8cbfe214c1772e" in store["pr_body"], failure
    assert worker_text == "old worker", failure
    assert any(kind == "trusted_v154_resume_rollback" for kind, _ in store["events"]), failure

# 7-11: strict preconditions.
for kwargs, expected in [
    ({"issue_phase": "loop:repairing", "pr_phase": "loop:ci"}, "phase mismatch"),
    ({"issue_state": "CLOSED"}, "issue is not open"),
    ({"pr_state": "CLOSED"}, "PR is not open"),
    ({"pr_draft": False}, "PR is not draft"),
    ({"diff": ["docs/agent_loop/pilot/PILOT_MARKER.md", "bad.txt"]}, "unexpected PR diff"),
]:
    outcome, *_ = run_resume_case(**kwargs)
    assert expected in outcome, (kwargs, outcome)

# 12-13: stable terminal notification dedupe by key.
with tempfile.TemporaryDirectory() as td:
    cfg, state_path = make_install(Path(td))
    st = json.loads(state_path.read_text(encoding="utf-8"))
    st["status"] = "loop:token-exhausted"
    key = worker.notification_key(st["front"], st["pr_number"], st["last_head_sha"], "loop:token-exhausted")
    marker = worker.notification_marker(key)
    store, original = install_fake(worker, comments=[{"body": marker + "\nlegacy duplicate body"}])
    try:
        worker.publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum Kimi cycles reached")
        assert store["comment_posts"] == []
        st = json.loads(state_path.read_text(encoding="utf-8"))
        assert key in st["notification_keys"] and st["terminal_notified"] is True
        st["last_head_sha"] = "f" * 40
        st["terminal_notified"] = False
        worker.publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum Kimi cycles reached")
        assert len(store["comment_posts"]) == 1
    finally:
        restore(original)

# Legacy TOKEN_EXHAUSTED comment without marker must seed the stable key and publish zero comments.
with tempfile.TemporaryDirectory() as td:
    cfg, state_path = make_install(Path(td))
    st = json.loads(state_path.read_text(encoding="utf-8"))
    legacy_body = "[AGENT-LOOP][TOKEN_EXHAUSTED]\n\n@cesarmanuel8102 Maximum Kimi cycles reached. Human audit required."
    key = worker.notification_key(st["front"], st["pr_number"], st["last_head_sha"], "loop:token-exhausted")
    store, original = install_fake(worker, comments=[{"body": legacy_body}])
    try:
        worker.publish_terminal_notification(cfg, state_path, st, "loop:token-exhausted", "Maximum Kimi cycles reached. Human audit required.")
        assert store["comment_posts"] == []
        ns = json.loads(state_path.read_text(encoding="utf-8"))
        assert key in ns["notification_keys"] and ns["terminal_notified"] is True
    finally:
        restore(original)

# 14-17: cycle accounting and loop:ci convergence primitives.
with tempfile.TemporaryDirectory() as td:
    cfg, state_path = make_install(Path(td))
    store, original = install_fake(worker)
    try:
        st = json.loads(state_path.read_text(encoding="utf-8"))
        st["cycles"] = 2
        worker.set_converged_phase(cfg, state_path, st, "loop:ci", pr_number=6)
        ns = json.loads(state_path.read_text(encoding="utf-8"))
        assert ns["status"] == "WAITING_GITHUB"
        assert store["issue_labels"] == {"loop:ci"} and store["pr_labels"] == {"loop:ci"}
        st["cycles"] = 2
        state_path.write_text(json.dumps(st), encoding="utf-8")
        before_cycles = json.loads(state_path.read_text(encoding="utf-8"))["cycles"]
        # Network/local retry terminalizer does not consume Kimi cycles.
        worker.terminalize_state_error(cfg, state_path, RuntimeError("temporary TLS timeout"))
        after_cycles = json.loads(state_path.read_text(encoding="utf-8"))["cycles"]
        assert before_cycles == after_cycles
    finally:
        restore(original)

def run_phase_convergence_failure(fail_at: str):
    with tempfile.TemporaryDirectory() as td:
        cfg, state_path = make_install(Path(td))
        original_state = state_path.read_bytes()
        store, original = install_fake(worker)
        original.update({
            "read_issue_labels": worker.read_issue_labels,
            "read_pr_labels": worker.read_pr_labels,
            "save_json": worker.save_json,
        })
        read_counts = {"issue": 0, "pr": 0}
        def fake_save_json(path, data):
            if fail_at == "state_save":
                raise RuntimeError("state save fail")
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        def fake_read_issue(repo_name, num):
            read_counts["issue"] += 1
            if fail_at == "issue_readback" and read_counts["issue"] > 1:
                return {"labels": [{"name": "loop:blocked"}]}
            return {"labels": [{"name": x} for x in sorted(store["issue_labels"])]}
        def fake_read_pr(repo_name, num):
            read_counts["pr"] += 1
            if fail_at == "pr_readback" and read_counts["pr"] > 1:
                return {"labels": [{"name": "loop:blocked"}]}
            return {"labels": [{"name": x} for x in sorted(store["pr_labels"])]}
        def fake_edit(repo_name, number, add=(), remove=()):
            target = "issue_labels" if int(number) == 5 else "pr_labels"
            if fail_at == "issue_label" and int(number) == 5:
                raise RuntimeError("issue label fail")
            if fail_at == "pr_label" and int(number) == 6:
                raise RuntimeError("pr label fail")
            store[target] = (store[target] - set(remove)) | set(add)
        worker.save_json = fake_save_json
        worker.read_issue_labels = fake_read_issue
        worker.read_pr_labels = fake_read_pr
        worker.edit_labels = fake_edit
        try:
            try:
                st = json.loads(state_path.read_text(encoding="utf-8"))
                worker.set_converged_phase(cfg, state_path, st, "loop:ci", pr_number=6)
                raise AssertionError("phase convergence should fail")
            except Exception as exc:
                assert "fail" in str(exc) or "phase mismatch" in str(exc), str(exc)
            assert state_path.read_bytes() == original_state
            assert store["issue_labels"] == {"loop:repairing"}, (fail_at, store["issue_labels"])
            assert store["pr_labels"] == {"loop:repairing"}, (fail_at, store["pr_labels"])
            assert any(kind == "phase_convergence_rollback" for kind, _ in store["events"])
        finally:
            restore(original)

for failure in ("issue_label", "pr_label", "issue_readback", "pr_readback"):
    run_phase_convergence_failure(failure)

def run_process_state_case(mode: str):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        repo = root / "repo"; repo.mkdir()
        (repo / "docs/agent_loop/pilot").mkdir(parents=True)
        (repo / "docs/agent_loop/pilot/PILOT_MARKER.md").write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
        (root / "opencode.jsonl").write_text("{}\n", encoding="utf-8")
        cfg = {"install_root": str(root), "repo": REPO, "owner": OWNER, "base_branch": "codex/own-capital-sustainable-return", "max_local_retries": 1, "max_kimi_cycles_default": 3, "test_profiles": {"pilot": []}, "opencode_model": "fake"}
        state_path = root / "state/issue-5.json"; state_path.parent.mkdir()
        state_path.write_text(json.dumps({"issue_number": 5, "front": FRONT, "spec": dict(SPEC), "repo_dir": str(repo), "pr_number": 6, "pr_url": "https://github.com/x/pull/6", "cycles": 2, "last_head_sha": HEAD, "status": "WAITING_GITHUB", "terminal_notified": False}), encoding="utf-8")
        calls = {"push": 0, "kimi": 0, "rollback": 0, "events": [], "phase": []}
        originals = {name: getattr(worker, name) for name in ("gh_json", "latest_feedback", "prepare_model_workspace", "run_kimi", "audit_and_sync_model_workspace", "run_marker_content_check", "run_final_verifier", "run", "set_phase", "read_issue_labels", "read_pr_labels", "event", "write_final_local_report", "publish_terminal_notification")}
        def fake_gh(args):
            if args[:2] == ["pr", "view"]:
                return {"number": 6, "url": "https://github.com/x/pull/6", "headRefOid": HEAD, "labels": [{"name": "loop:repairing"}], "state": "OPEN"}
            raise AssertionError(args)
        def fake_run(args, cwd=None, **kwargs):
            if args[:2] == ["git", "diff"]:
                return "docs/agent_loop/pilot/PILOT_MARKER.md\n" if "--cached" not in args else "docs/agent_loop/pilot/PILOT_MARKER.md\ndocs/agent_loop/pilot/EXECUTOR_REPORT.json\n"
            if args[:2] == ["git", "ls-files"]: return ""
            if args[:2] == ["git", "rev-parse"]: return HEAD
            if args[:2] == ["git", "push"]:
                calls["push"] += 1
                return ""
            if args[:3] == ["git", "reset", "--hard"] and "HEAD~1" in args:
                calls["rollback"] += 1
                return ""
            if args[0] == "git": return ""
            return ""
        def fake_prepare(repo_dir, spec, cycle):
            model = root / f"model-{cycle}"
            (model / "docs/agent_loop/pilot").mkdir(parents=True)
            (model / "docs/agent_loop/pilot/PILOT_MARKER.md").write_text("stale marker\n", encoding="utf-8")
            return model, {}
        def fake_run_kimi(*args, **kwargs):
            calls["kimi"] += 1
            spec = args[1]
            model_dir = args[2]
            cycle = args[4]
            marker = model_dir / "docs/agent_loop/pilot/PILOT_MARKER.md"
            marker.write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
            log = root / "opencode.jsonl"
            log.write_text(json.dumps({"text": worker.prompt_task_sentinel(spec["front_id"], cycle)}) + "\n", encoding="utf-8")
            return log, None
        def fake_audit(*args, **kwargs):
            if mode == "model_content_failure":
                raise RuntimeError("PILOT_MARKER_CONTENT_MISMATCH")
            return ["docs/agent_loop/pilot/PILOT_MARKER.md"]
        worker.gh_json = fake_gh
        worker.latest_feedback = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("temporary TLS timeout")) if mode == "network_transient" else "feedback"
        worker.prepare_model_workspace = fake_prepare
        worker.run_kimi = fake_run_kimi
        worker.audit_and_sync_model_workspace = fake_audit
        def fake_marker_content_check(repo_dir, expected_front_id):
            assert expected_front_id == FRONT
            return True, "content ok"
        def fake_final_verifier(repo_dir, base, head, expected_front_id):
            assert expected_front_id == FRONT
            return (False, "final verifier failed") if mode == "trusted_verifier_failure" else (True, "final ok")
        worker.run_marker_content_check = fake_marker_content_check
        worker.run_final_verifier = fake_final_verifier
        worker.run = fake_run
        worker.set_phase = lambda repo_name, number, phase: calls["phase"].append((int(number), phase))
        read_counts = {"issue": 0, "pr": 0}
        def process_issue_labels(repo_name, number):
            read_counts["issue"] += 1
            if mode == "success_convergence_failure" and read_counts["issue"] > 1:
                return {"labels": [{"name": "loop:blocked"}]}
            return {"labels": [{"name": "loop:ci"}]}
        def process_pr_labels(repo_name, number):
            read_counts["pr"] += 1
            return {"labels": [{"name": "loop:ci"}]}
        worker.read_issue_labels = process_issue_labels
        worker.read_pr_labels = process_pr_labels
        worker.event = lambda cfg, kind, **fields: calls["events"].append((kind, fields))
        worker.write_final_local_report = lambda *a, **k: root / "final_report.json"
        worker.publish_terminal_notification = lambda cfg, state_path, st, phase, message: (_ for _ in ()).throw(AssertionError("terminal notification should not publish"))
        try:
            if mode == "network_transient":
                worker.process_once(cfg)
            else:
                worker.process_state(cfg, state_path)
            st = json.loads(state_path.read_text(encoding="utf-8"))
            return st, calls
        finally:
            for name, value in originals.items():
                setattr(worker, name, value)

st, calls = run_process_state_case("model_content_failure")
assert st["cycles"] == 3 and calls["push"] == 0 and not [x for x in calls["phase"] if x[1] == "loop:ci"]
assert any(fields.get("failure_class") == "MODEL_CONTENT_FAILURE" and fields.get("cycle_before") == 2 and fields.get("cycle_after") == 3 for _, fields in calls["events"])

st, calls = run_process_state_case("trusted_verifier_failure")
assert st["cycles"] == 2 and calls["push"] == 0 and calls["rollback"] == 1 and not calls["phase"]
assert any(fields.get("failure_class") == "TRUSTED_VERIFIER_OR_WORKER_INTERNAL_FAILURE" and fields.get("cycle_before") == 2 and fields.get("cycle_after") == 2 for _, fields in calls["events"])

st, calls = run_process_state_case("network_transient")
assert st["cycles"] == 2 and st["status"] == "LOCAL_RETRY" and calls["kimi"] == 0 and calls["push"] == 0
assert any(kind == "state_retry_scheduled" for kind, _ in calls["events"])

st, calls = run_process_state_case("success")
assert st["cycles"] == 3 and st["status"] == "WAITING_GITHUB" and calls["push"] == 1
assert (5, "loop:ci") in calls["phase"] and (6, "loop:ci") in calls["phase"]

try:
    run_process_state_case("success_convergence_failure")
    raise AssertionError("post-push convergence failure should be explicit")
except Exception as exc:
    assert "phase mismatch" in str(exc), str(exc)

print(json.dumps({"status": "PASS", "worker_version": worker.WORKER_VERSION, "checks": 20}, indent=2))
