#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker153_base", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
OLD_BASE = "0" * 40
CONTROL = "1" * 40
BRANCH = "agent/pilot-20260716-091529"

def sh(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def make_spec(old_base):
    return {
        "schema_version": 1,
        "front_id": FRONT,
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "expected_base_sha": old_base,
        "work_branch": BRANCH,
        "objective": "pilot",
        "test_profile": "pilot",
        "max_kimi_cycles": 3,
        "allowed_paths": [
            "docs/agent_loop/pilot/PILOT_MARKER.md",
            "docs/agent_loop/pilot/EXECUTOR_REPORT.json",
        ],
        "forbidden_paths": [
            "memory/semantic/",
            "memory/rollback",
            "tmp_agent/state/",
            "tmp_agent/brain_v9/trading/",
            "financial_autonomy/",
            "tmp_agent/brain_v9/core/session.py",
        ],
    }

def issue_body(specd):
    return "<!-- AGENT_LOOP_SPEC " + json.dumps(specd, separators=(",", ":")) + " AGENT_LOOP_SPEC -->"

def setup_repo(td):
    root = Path(td)
    src = root / "src"; bare = root / "remote.git"; work = root / "work"
    src.mkdir()
    sh(["git", "init"], src)
    sh(["git", "config", "user.name", "test"], src)
    sh(["git", "config", "user.email", "test@example.invalid"], src)
    pilot = src / "docs/agent_loop/pilot"; pilot.mkdir(parents=True)
    (pilot / "PILOT_MARKER.md").write_text("old marker\n", encoding="utf-8")
    (pilot / "EXECUTOR_REPORT.json").write_text('{"old":true}\n', encoding="utf-8")
    sh(["git", "add", "."], src); sh(["git", "commit", "-m", "old base"], src)
    old_base = sh(["git", "rev-parse", "HEAD"], src)
    sh(["git", "checkout", "-b", BRANCH], src)
    (pilot / "PILOT_MARKER.md").write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
    (pilot / "EXECUTOR_REPORT.json").write_text('{"schema_version":1,"worker_version":"1.5.3","status":"PASS"}\n', encoding="utf-8")
    sh(["git", "add", "."], src); sh(["git", "commit", "-m", "pilot"], src)
    old_pr_head = sh(["git", "rev-parse", "HEAD"], src)
    sh(["git", "checkout", "-b", "codex/own-capital-sustainable-return", old_base], src)
    (src / "scripts/agent_loop/local_worker").mkdir(parents=True)
    (src / "scripts/agent_loop/local_worker/agent_worker.py").write_text("# v153\n", encoding="utf-8")
    sh(["git", "add", "."], src); sh(["git", "commit", "-m", "control plane v153"], src)
    new_base = sh(["git", "rev-parse", "HEAD"], src)
    sh(["git", "init", "--bare", str(bare)], root)
    sh(["git", "remote", "add", "origin", str(bare)], src)
    sh(["git", "push", "origin", "codex/own-capital-sustainable-return", BRANCH], src)
    sh(["git", "clone", str(bare), str(work)], root)
    sh(["git", "checkout", BRANCH], work)
    return root, work, old_base, old_pr_head, new_base

def install_state(td, work, old_base, old_pr_head):
    state_dir = Path(td) / "install/state"; state_dir.mkdir(parents=True)
    specd = make_spec(old_base)
    state = {
        "issue_number": 5,
        "front": FRONT,
        "spec": specd,
        "repo_dir": str(work),
        "pr_number": 6,
        "pr_url": "https://github.com/cesarmanuel8102/AI_Vault/pull/6",
        "last_head_sha": old_pr_head,
        "cycles": 3,
        "status": "loop:blocked",
        "terminal_notified": True,
    }
    path = state_dir / "issue-5.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path, specd

def fake_gh_factory(specd, old_base, old_pr_head, new_base, compare_status="ahead", pr_head=None, issue_update=None):
    def fake_gh(args):
        if args[:1] == ["api"] and "/compare/" in args[1]:
            return {"status": compare_status}
        if args[:1] == ["api"] and args[1].endswith("/git/ref/heads/codex/own-capital-sustainable-return"):
            return {"object": {"sha": new_base}}
        if args[:2] == ["issue", "view"]:
            return {"number": 5, "state": "OPEN", "author": {"login": "cesarmanuel8102"},
                    "body": issue_body(specd), "labels": [{"name": "loop:blocked"}],
                    "url": "https://github.com/cesarmanuel8102/AI_Vault/issues/5"}
        if args[:2] == ["pr", "view"]:
            return {"number": 6, "url": "https://github.com/cesarmanuel8102/AI_Vault/pull/6",
                    "state": "OPEN", "isDraft": True, "headRefName": BRANCH,
                    "headRefOid": pr_head or old_pr_head,
                    "baseRefName": "codex/own-capital-sustainable-return",
                    "labels": [{"name": "loop:blocked"}]}
        raise AssertionError(args)
    return fake_gh

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    calls = []
    old_gh, old_update, old_phase, old_event = worker.gh_json, worker.update_issue_body, worker.set_phase, worker.event
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, new_base)
    worker.update_issue_body = lambda repo, num, body: calls.append(("body", body))
    worker.set_phase = lambda *a, **k: calls.append(("phase", a))
    worker.event = lambda *a, **k: None
    try:
        worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
    finally:
        worker.gh_json, worker.update_issue_body, worker.set_phase, worker.event = old_gh, old_update, old_phase, old_event
    ns = json.loads(state_path.read_text(encoding="utf-8"))
    assert ns["spec"]["expected_base_sha"] == new_base
    assert ns["pr_number"] == 6 and ns["pr_url"].endswith("/6")
    assert ns["cycles"] == 2 and ns["status"] == "WAITING_GITHUB"
    new_head = sh(["git", "rev-parse", f"origin/{BRANCH}"], work)
    diff = sh(["git", "diff", "--name-only", new_base, new_head], work).splitlines()
    assert sorted(diff) == sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])
    assert any(c[0] == "body" and new_base in c[1] for c in calls)
    assert [c for c in calls if c[0] == "phase"][-2][1][2] == "loop:repairing"

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    old_gh = worker.gh_json
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, new_base, compare_status="diverged")
    try:
        try:
            worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
            raise AssertionError("expected compare failure")
        except Exception as exc:
            assert "does not contain" in str(exc)
    finally:
        worker.gh_json = old_gh

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    old_gh = worker.gh_json
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, "bad-new-base")
    try:
        try:
            worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
            raise AssertionError("expected new base mismatch")
        except Exception as exc:
            assert "new base mismatch" in str(exc)
    finally:
        worker.gh_json = old_gh

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    old_gh = worker.gh_json
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, new_base, pr_head="bad")
    try:
        try:
            worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
            raise AssertionError("expected head mismatch")
        except Exception as exc:
            assert "old PR HEAD mismatch" in str(exc)
    finally:
        worker.gh_json = old_gh

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    old_gh, old_update, old_phase, old_event = worker.gh_json, worker.update_issue_body, worker.set_phase, worker.event
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, new_base)
    worker.update_issue_body = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("issue update failed"))
    worker.set_phase = lambda *a, **k: None
    worker.event = lambda *a, **k: None
    try:
        try:
            worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
            raise AssertionError("expected issue update failure")
        except Exception as exc:
            assert "issue update failed" in str(exc)
    finally:
        worker.gh_json, worker.update_issue_body, worker.set_phase, worker.event = old_gh, old_update, old_phase, old_event
    assert json.loads(state_path.read_text(encoding="utf-8"))["spec"]["expected_base_sha"] == old_base
    assert sh(["git", "rev-parse", f"origin/{BRANCH}"], work) == old_pr_head

with tempfile.TemporaryDirectory() as td:
    _, work, old_base, old_pr_head, new_base = setup_repo(td)
    state_path, specd = install_state(td, work, old_base, old_pr_head)
    cfg = {"repo": "cesarmanuel8102/AI_Vault", "owner": "cesarmanuel8102",
           "base_branch": "codex/own-capital-sustainable-return", "install_root": str(Path(td) / "install"),
           "max_kimi_cycles_default": 3, "test_profiles": {"pilot": {}}}
    old_gh, old_run = worker.gh_json, worker.run
    worker.gh_json = fake_gh_factory(specd, old_base, old_pr_head, new_base)
    def failing_push(args, *a, **k):
        if args[:3] == ["git", "push", "origin"]:
            raise RuntimeError("branch update failed")
        return old_run(args, *a, **k)
    worker.run = failing_push
    try:
        try:
            worker.trusted_base_advance_existing_pr(cfg, 5, FRONT, old_base, new_base, CONTROL, 6, BRANCH, old_pr_head)
            raise AssertionError("expected branch update failure")
        except Exception as exc:
            assert "branch update failed" in str(exc)
    finally:
        worker.gh_json, worker.run = old_gh, old_run
    assert json.loads(state_path.read_text(encoding="utf-8"))["spec"]["expected_base_sha"] == old_base
    assert sh(["git", "rev-parse", f"origin/{BRANCH}"], work) == old_pr_head

script = (ROOT / "scripts/agent_loop/Repair-AgentLoop-v1.5.3.ps1").read_text(encoding="utf-8")
assert "Disable-ScheduledTask" in script and "Scheduled task is not disabled; refusing install" in script
assert "--trusted-base-advance-existing-pr" in script
assert "Enable-ScheduledTask" in script and script.index("--trusted-base-advance-existing-pr") < script.index("Enable-ScheduledTask")

print(json.dumps({"status": "PASS", "worker_version": worker.WORKER_VERSION}, indent=2))
