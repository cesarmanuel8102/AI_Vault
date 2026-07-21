#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker154", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
BASE = "baab482a829a233cdffc25e558ff22eb6d335e69"
HEAD = "686533399b9789fdd5737a3c69ab1a6c6469a4bd"
BRANCH = "agent/pilot-20260716-091529"

assert worker.WORKER_VERSION == "1.5.7"
assert worker.pilot_marker_text(FRONT) == """# Agent Loop Pilot
WORKER_VERSION=1.5.7
FRONT_ID=PILOT-KIMI-CODEX-20260716-091529
STATUS=PASS
EXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR
SUPERVISOR=CODEX_GITHUB_ACTION
"""

def sh(args, cwd):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def init_repo(root: Path):
    repo = root / "repo"; repo.mkdir(parents=True)
    sh(["git", "init"], repo)
    sh(["git", "config", "user.name", "test"], repo)
    sh(["git", "config", "user.email", "test@example.invalid"], repo)
    pv = repo / "scripts/agent_loop/pilot_verify.py"; pv.parent.mkdir(parents=True)
    pv.write_text((ROOT / "scripts/agent_loop/pilot_verify.py").read_text(encoding="utf-8"), encoding="utf-8")
    pilot = repo / "docs/agent_loop/pilot"; pilot.mkdir(parents=True)
    (pilot / "PILOT_MARKER.md").write_text(f"# Agent Loop Pilot\nWORKER_VERSION=1.5.2\nFRONT_ID={FRONT}\nSTATUS=PASS\nEXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR\nSUPERVISOR=CODEX_GITHUB_ACTION\n", encoding="utf-8")
    (pilot / "EXECUTOR_REPORT.json").write_text(json.dumps({
        "schema_version": 1, "front_id": FRONT, "issue_number": 5, "cycle": 2,
        "base_sha": "4722de72388c9d4d1bd2659dfc8cbfe214c1772e",
        "changed_files": ["docs/agent_loop/pilot/PILOT_MARKER.md"],
        "local_test_passed": True, "merge_performed": False, "canonical_local_sync": False,
    }, indent=2), encoding="utf-8")
    sh(["git", "add", "."], repo); sh(["git", "commit", "-m", "current bad pr6 fixture"], repo)
    return repo

with tempfile.TemporaryDirectory() as td:
    root = Path(td); repo = init_repo(root)
    p = subprocess.run([sys.executable, "scripts/agent_loop/pilot_verify.py", "--local", "--expected-front-id", FRONT], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert p.returncode != 0 and "marker worker version too old" in p.stdout
    model = root / "model" / "docs/agent_loop/pilot"; model.mkdir(parents=True)
    (model / "PILOT_MARKER.md").write_text(worker.pilot_marker_text(FRONT), encoding="utf-8")
    changed = worker.audit_and_sync_model_workspace(root / "model", repo, {}, {"front_id": FRONT})
    assert changed == ["docs/agent_loop/pilot/PILOT_MARKER.md"]
    ok, out = worker.run_marker_content_check(repo, FRONT)
    assert ok, out
    changes = worker.changed_files(repo, sh(["git", "rev-parse", "HEAD"], repo))
    worker.write_executor_report({"opencode_model":"ollama-cloud/kimi-k2.7-code"}, {"front_id":FRONT,"expected_base_sha":BASE,"test_profile":"pilot"}, repo, 5, 3, changes, True, out, root / "opencode.jsonl")
    report = json.loads((repo / "docs/agent_loop/pilot/EXECUTOR_REPORT.json").read_text(encoding="utf-8"))
    assert report["worker_version"] == worker.WORKER_VERSION
    assert report["executor"] == "OpenCode/Ollama tool executor"
    assert report["agent"] == "brain-opencode-executor"
    assert report["model"] == "ollama-cloud/kimi-k2.7-code"
    assert report["front_id"] == FRONT
    assert report["base_sha"] == BASE
    assert report["issue_number"] == 5 and report["cycle"] == 3
    assert report["changed_files"] == sorted(["docs/agent_loop/pilot/PILOT_MARKER.md", "docs/agent_loop/pilot/EXECUTOR_REPORT.json"])
    sh(["git", "add", "docs/agent_loop/pilot/PILOT_MARKER.md", "docs/agent_loop/pilot/EXECUTOR_REPORT.json"], repo)
    sh(["git", "commit", "-m", "repair fixture"], repo)
    head = sh(["git", "rev-parse", "HEAD"], repo)
    ok, final = worker.run_final_verifier(repo, "HEAD~1", head, FRONT)
    assert ok, final

with tempfile.TemporaryDirectory() as td:
    root = Path(td); repo = init_repo(root)
    bad = root / "bad" / "docs/agent_loop/pilot"; bad.mkdir(parents=True)
    (bad / "PILOT_MARKER.md").write_text("bad marker\n", encoding="utf-8")
    try:
        worker.audit_and_sync_model_workspace(root / "bad", repo, {}, {"front_id": FRONT})
        raise AssertionError("malformed marker should fail")
    except Exception as exc:
        assert "PILOT_MARKER_CONTENT_MISMATCH" in str(exc)

with tempfile.TemporaryDirectory() as td:
    root = Path(td); repo = init_repo(root)
    deepseek_front = "PILOT-V157-DEEPSEEK-ACTIVATION-20260720-192619"
    model = root / "model" / "docs/agent_loop/pilot"; model.mkdir(parents=True)
    expected = worker.pilot_marker_text(deepseek_front)
    (model / "PILOT_MARKER.md").write_bytes(expected.removesuffix("\n").encode("utf-8"))
    changed = worker.audit_and_sync_model_workspace(
        root / "model", repo, {}, {"front_id": deepseek_front}
    )
    assert changed == ["docs/agent_loop/pilot/PILOT_MARKER.md"]
    assert (repo / "docs/agent_loop/pilot/PILOT_MARKER.md").read_bytes() == expected.encode("utf-8")

with tempfile.TemporaryDirectory() as td:
    root = Path(td); repo = init_repo(root)
    model = root / "model" / "docs/agent_loop/pilot"; model.mkdir(parents=True)
    (model / "PILOT_MARKER.md").write_text(worker.pilot_marker_text(FRONT) + "\n", encoding="utf-8")
    try:
        worker.audit_and_sync_model_workspace(root / "model", repo, {}, {"front_id": FRONT})
        raise AssertionError("an extra terminal blank line must fail")
    except Exception as exc:
        assert "PILOT_MARKER_CONTENT_MISMATCH" in str(exc)

with tempfile.TemporaryDirectory() as td:
    cfg = {"install_root": td, "repo": "cesarmanuel8102/AI_Vault", "owner":"cesarmanuel8102", "base_branch":"codex/own-capital-sustainable-return", "max_kimi_cycles_default": 3, "test_profiles":{"pilot":[]}}
    state_dir = Path(td) / "state"; state_dir.mkdir(parents=True)
    state = state_dir / "issue-5.json"
    specd = {"schema_version":1,"front_id":FRONT,"repo":"cesarmanuel8102/AI_Vault","owner":"cesarmanuel8102","base_branch":"codex/own-capital-sustainable-return","expected_base_sha":BASE,"work_branch":BRANCH,"objective":"pilot","test_profile":"pilot","max_kimi_cycles":3,"allowed_paths":["docs/agent_loop/pilot/PILOT_MARKER.md","docs/agent_loop/pilot/EXECUTOR_REPORT.json"],"forbidden_paths":["memory/semantic/","memory/rollback","tmp_agent/state/","tmp_agent/brain_v9/trading/","financial_autonomy/","tmp_agent/brain_v9/core/session.py"]}
    repo = init_repo(Path(td) / "work")
    state.write_text(json.dumps({"issue_number":5,"front":FRONT,"spec":specd,"repo_dir":str(repo),"pr_number":6,"pr_url":"https://github.com/cesarmanuel8102/AI_Vault/pull/6","cycles":3,"last_head_sha":HEAD,"status":"loop:token-exhausted","terminal_notified":False}), encoding="utf-8")
    calls=[]
    old_gh, old_phase, old_update, old_sched, old_event, old_diff = worker.gh_json, worker.set_phase, worker.update_pr_body, worker.scheduled_task_disabled, worker.event, worker.pr_changed_files
    worker.scheduled_task_disabled = lambda: True
    worker.set_phase = lambda *a, **k: calls.append(("phase", a))
    worker.update_pr_body = lambda repo_name, num, body: calls.append(("pr_body", body))
    worker.event = lambda *a, **k: calls.append(("event", a, k))
    worker.pr_changed_files = lambda repo_name, num: sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return {"number":5,"state":"OPEN","author":{"login":"cesarmanuel8102"},"body":"<!-- AGENT_LOOP_SPEC "+json.dumps(specd,separators=(",",":"))+" AGENT_LOOP_SPEC -->","labels":[{"name":"loop:repairing"}],"url":"https://github.com/cesarmanuel8102/AI_Vault/issues/5"}
        if args[:2] == ["pr", "view"]:
            data={"number":6,"url":"https://github.com/cesarmanuel8102/AI_Vault/pull/6","state":"OPEN","isDraft":True,"headRefName":BRANCH,"headRefOid":HEAD,"baseRefName":"codex/own-capital-sustainable-return","body":"EXPECTED_BASE_SHA: 4722de72388c9d4d1bd2659dfc8cbfe214c1772e","labels":[{"name":"loop:repairing"}]}
            if "labels" in args[-1] and args[-1] == "labels": return {"labels":[{"name":"loop:repairing"}]}
            return data
        if args[:1] == ["api"]: return {"object":{"sha":BASE}}
        raise AssertionError(args)
    worker.gh_json = fake_gh
    try:
        backup = worker.trusted_resume_issue5_pr6_v154(cfg, 5, FRONT, BASE, 6, BRANCH, HEAD)
        ns = json.loads(state.read_text(encoding="utf-8"))
        assert backup.exists() and ns["cycles"] == 2 and ns["status"] == "WAITING_GITHUB"
        assert ns["trusted_v154_resume_done"] is True and ns["terminal_notified"] is False
        assert any(c[0] == "pr_body" and BASE in c[1] for c in calls)
        try:
            worker.trusted_resume_issue5_pr6_v154(cfg, 5, FRONT, BASE, 6, BRANCH, HEAD)
            raise AssertionError("second resume must fail")
        except Exception as exc:
            assert "already completed" in str(exc)
    finally:
        worker.gh_json, worker.set_phase, worker.update_pr_body, worker.scheduled_task_disabled, worker.event, worker.pr_changed_files = old_gh, old_phase, old_update, old_sched, old_event, old_diff

print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION}, indent=2))
