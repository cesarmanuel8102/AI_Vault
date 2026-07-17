#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, os, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker155", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"
BASE = "220fa3b043d2cae8f8b084c0617027d754963335"
HEAD = "c94fa5c995684a8db2ecbec09ceef1cfb30c55c5"
BRANCH = "agent/pilot-20260716-091529"
REPO = "cesarmanuel8102/AI_Vault"
OWNER = "cesarmanuel8102"
assert worker.WORKER_VERSION == "1.5.5"

def git(args, cwd: Path) -> str:
    cp = subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert cp.returncode == 0, cp.stdout
    return cp.stdout.strip()

def create_real_repo(root: Path, dirty=False, ahead=False, non_git=False):
    repo = root / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    if non_git:
        return repo, HEAD
    git(["init"], repo)
    git(["config", "user.name", "test"], repo)
    git(["config", "user.email", "test@example.invalid"], repo)
    (repo / "pilot.txt").write_text("pilot\n", encoding="utf-8")
    git(["add", "pilot.txt"], repo)
    git(["commit", "-m", "pilot"], repo)
    expected = git(["rev-parse", "HEAD"], repo)
    git(["update-ref", "refs/remotes/origin/agent/pilot-20260716-091529", expected], repo)
    if ahead:
        (repo / "ahead.txt").write_text("ahead\n", encoding="utf-8")
        git(["add", "ahead.txt"], repo)
        git(["commit", "-m", "ahead"], repo)
    if dirty:
        (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    return repo, expected

SPEC = {
    "schema_version": 1, "front_id": FRONT, "repo": REPO, "owner": OWNER,
    "base_branch": "codex/own-capital-sustainable-return", "expected_base_sha": BASE,
    "work_branch": BRANCH, "objective": "pilot", "test_profile": "pilot", "max_kimi_cycles": 3,
    "allowed_paths": sorted(worker.PROFILE_ALLOWED_PATHS["pilot"]),
    "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS),
}

def issue_body(specd=SPEC):
    return "<!-- AGENT_LOOP_SPEC " + json.dumps(specd, separators=(",", ":")) + " AGENT_LOOP_SPEC -->"

def write_events(root: Path, head=HEAD, malformed=False, out_of_order=False, later_success=False):
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    rows = [
        {"event":"trusted_v154_resume_existing_pr","issue":5,"pr":6,"base":BASE,"head":head},
        {"event":"repair_local_gate_failed","issue":5,"pr":6,"cycle":3,"cycle_before":2,"cycle_after":3,"failure_class":"MODEL_CONTENT_FAILURE","current_head":head,"expected_base":BASE},
    ]
    if out_of_order:
        rows = list(reversed(rows))
    if later_success:
        rows.append({"event":"set_phase","issue":5,"phase":"loop:ci"})
    if malformed:
        (reports / "worker-events.jsonl").write_text("not-json\n", encoding="utf-8")
    else:
        (reports / "worker-events.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")

def make_install(tmp: Path, events=True, repo_case="valid", head_override=None):
    (tmp / "state").mkdir(parents=True)
    (tmp / "worker").mkdir(parents=True)
    (tmp / "worker/agent_worker.py").write_text("old worker", encoding="utf-8")
    if repo_case == "missing":
        repo_dir, head = None, head_override or HEAD
    elif repo_case == "empty":
        repo_dir, head = "", head_override or HEAD
    elif repo_case == "nonexistent":
        repo_dir, head = str(tmp / "does-not-exist"), head_override or HEAD
    elif repo_case == "nongit":
        repo, head = create_real_repo(tmp, non_git=True); repo_dir = str(repo)
    elif repo_case == "dirty":
        repo, head = create_real_repo(tmp, dirty=True); repo_dir = str(repo)
    elif repo_case == "ahead":
        repo, head = create_real_repo(tmp, ahead=True); repo_dir = str(repo)
    elif repo_case == "wrong_head":
        repo, good = create_real_repo(tmp); repo_dir = str(repo); head = "0" * 40
    else:
        repo, head = create_real_repo(tmp); repo_dir = str(repo)
    state = {
        "issue_number": 5, "front": FRONT, "spec": dict(SPEC), "repo_dir": repo_dir,
        "pr_number": 6, "pr_url": "https://github.com/x/pull/6", "cycles": 3,
        "last_head_sha": head, "status": "WAITING_GITHUB", "local_retry_count": 1,
        "terminal_notified": True, "trusted_v154_resume_done": True,
    }
    path = tmp / "state/issue-5.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    if events:
        write_events(tmp, head=head)
    return {"install_root": str(tmp), "repo": REPO, "owner": OWNER, "base_branch": SPEC["base_branch"], "max_kimi_cycles_default": 3, "test_profiles": {"pilot": []}}, path, head

def install_fake(fail_at=None, comments=None, head=HEAD):
    store = {
        "issue_body": issue_body(), "pr_body": f"EXPECTED_BASE_SHA: {BASE}",
        "issue_labels": {"loop:repairing"}, "pr_labels": {"loop:repairing"},
        "comments": list(comments or []), "events": [], "comment_posts": [], "copy_calls": [], "run_calls": [], "mutated": False,
    }
    original = {name: getattr(worker, name) for name in (
        "gh_json", "update_issue_body", "update_pr_body", "edit_labels", "read_issue_labels", "read_pr_labels",
        "restore_label_set", "pr_changed_files", "scheduled_task_disabled", "event", "comment", "issue_comments", "save_json", "run_kimi", "run")}
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            labs = {"loop:blocked"} if fail_at == "issue_readback" and store["mutated"] else store["issue_labels"]
            return {"number": 5, "state": "OPEN", "author": {"login": OWNER}, "body": store["issue_body"], "labels": [{"name": x} for x in sorted(labs)], "url": "https://github.com/x/issues/5"}
        if args[:2] == ["pr", "view"]:
            labs = {"loop:blocked"} if fail_at == "pr_readback" and store["mutated"] else store["pr_labels"]
            return {"number": 6, "url": "https://github.com/x/pull/6", "state": "OPEN", "isDraft": True, "headRefName": BRANCH, "headRefOid": head, "baseRefName": SPEC["base_branch"], "body": store["pr_body"], "labels": [{"name": x} for x in sorted(labs)]}
        if args[:1] == ["api"]:
            return {"object": {"sha": BASE}}
        raise AssertionError(args)
    def fake_edit(repo, number, add=(), remove=()):
        if fail_at == "issue_label" and int(number) == 5: raise RuntimeError("issue label fail")
        if fail_at == "pr_label" and int(number) == 6: raise RuntimeError("pr label fail")
        key = "issue_labels" if int(number) == 5 else "pr_labels"
        store["mutated"] = True
        store[key] = (store[key] - set(remove)) | set(add)
    def fake_save(path, data):
        if fail_at == "state_partial":
            path.write_bytes(b'{"truncated":')
            raise RuntimeError("partial state write fail")
        if fail_at == "state_save": raise RuntimeError("state save fail")
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    worker.gh_json = fake_gh
    worker.update_issue_body = lambda repo, num, body: store.update(mutated=True, issue_body=body)
    worker.update_pr_body = lambda repo, num, body: store.update(mutated=True, pr_body=body)
    worker.edit_labels = fake_edit
    worker.read_issue_labels = lambda repo, num: fake_gh(["issue", "view"])
    worker.read_pr_labels = lambda repo, num: fake_gh(["pr", "view"])
    worker.restore_label_set = lambda repo, num, labs: store.update(**({"issue_labels": set(labs)} if int(num)==5 else {"pr_labels": set(labs)}))
    worker.pr_changed_files = lambda repo, num: sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])
    worker.scheduled_task_disabled = lambda: True
    def fake_event(cfg, kind, **fields):
        store["events"].append((kind, fields))
        if fail_at == "event_append" and kind == "trusted_v155_recovery_existing_pr":
            raise RuntimeError("partial event append failure")
    worker.event = fake_event
    worker.comment = lambda repo, number, body: store["comment_posts"].append((number, body))
    worker.issue_comments = lambda repo, number: list(store["comments"])
    worker.save_json = fake_save
    worker.run_kimi = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Kimi must not run during recovery"))
    def fake_run(args, cwd=None, env=None, check=True, timeout=None):
        store["run_calls"].append(args)
        if args and args[0] == "git" and cwd is not None:
            cp = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            if check and cp.returncode != 0:
                raise RuntimeError(cp.stdout)
            return cp.stdout
        raise AssertionError("unexpected run during recovery: " + repr(args))
    worker.run = fake_run
    return store, original

def restore(original):
    for name, value in original.items(): setattr(worker, name, value)

def test_cli_lock_contention_aborts_before_mutation():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg, state_path, head = make_install(root)
        cfg_path = root / "config.json"; cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        source = root / "source_worker.py"; source.write_bytes(MODULE.read_bytes())
        before_state = state_path.read_bytes(); before_worker = (root / "worker/agent_worker.py").read_bytes()
        holder = root / "hold_lock.py"
        holder.write_text(f"""
import importlib.util, time, pathlib
spec=importlib.util.spec_from_file_location('w', r'{MODULE}')
w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)
with w.SingleInstanceLock(pathlib.Path(r'{root / 'state/worker.lock'}')):
    print('LOCK_HELD', flush=True)
    time.sleep(5)
""", encoding="utf-8")
        p = subprocess.Popen([sys.executable, str(holder)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert "LOCK_HELD" in p.stdout.readline()
            cmd = [sys.executable, str(MODULE), "--config", str(cfg_path), "--trusted-v155-deploy-recover-existing-pr", "5", "--expected-base-sha", BASE, "--expected-pr-head", head, "--source-worker", str(source), "--approved-worker-sha256", worker.sha256_file(source)]
            cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            assert cp.returncode != 0
            assert "worker.lock busy" in cp.stdout or "another worker instance" in cp.stdout
            assert "process_evidence" in cp.stdout
            assert before_state == state_path.read_bytes()
            assert before_worker == (root / "worker/agent_worker.py").read_bytes()
            assert not list((root / "reports").glob("*.bak-v155-deploy-*"))
        finally:
            p.terminate(); p.wait(timeout=10)

def run_recovery(fail_at=None, malformed_events=False, out_of_order=False, later_success=False, deploy=False, repo_case="valid", fail_after_success_event=False):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg, state_path, head = make_install(root, events=False, repo_case=repo_case)
        write_events(root, head=head, malformed=malformed_events, out_of_order=out_of_order, later_success=later_success)
        before = state_path.read_bytes(); before_worker = (root / "worker/agent_worker.py").read_bytes()
        comments = [{"body": "[AGENT-LOOP][TOKEN_EXHAUSTED]\n\n@cesarmanuel8102 Maximum Kimi cycles reached. Human audit required."} for _ in range(3)]
        store, original = install_fake(fail_at=fail_at, comments=comments, head=head)
        try:
            try:
                if deploy:
                    source = root / "source_worker.py"; source.write_bytes(MODULE.read_bytes())
                    backup = worker.trusted_v155_deploy_recover_existing_pr(cfg, 5, str(source), worker.sha256_file(source), BASE, head)
                else:
                    backup = worker.trusted_v155_recover_existing_pr(cfg, 5, BASE, head)
                outcome = "PASS"
            except Exception as exc:
                backup = None; outcome = str(exc)
            after = state_path.read_bytes()
            return outcome, backup, before, after, before_worker, (root / "worker/agent_worker.py").read_bytes(), json.loads(after.decode("utf-8")) if after.startswith(b'{') else {}, store
        finally:
            restore(original)

def test_event_chronology_fail_closed():
    for kwargs in ({"malformed_events": True}, {"out_of_order": True}, {"later_success": True}):
        outcome, *_ = run_recovery(**kwargs)
        assert outcome != "PASS", kwargs

def test_authoritative_repo_dir_fail_closed_before_mutation():
    for repo_case in ("missing", "empty", "nonexistent", "nongit", "wrong_head", "dirty", "ahead"):
        outcome, backup, before, after, before_worker, after_worker, st, store = run_recovery(repo_case=repo_case)
        assert outcome != "PASS", repo_case
        assert before == after, repo_case
        assert before_worker == after_worker, repo_case
        assert store["issue_labels"] == {"loop:repairing"}, repo_case
        assert store["pr_labels"] == {"loop:repairing"}, repo_case
        assert not store["comment_posts"], repo_case

def test_recovery_success_and_legacy_dedupe():
    outcome, backup, before, after, before_worker, after_worker, st, store = run_recovery()
    assert outcome == "PASS" and backup, outcome
    assert st["cycles"] == 2 and st["status"] == "WAITING_GITHUB"
    assert st["trusted_v155_recovery_done"] is True
    assert st["terminal_notified"] is False and st["local_retry_count"] == 0
    assert st["notification_keys"], "legacy TOKEN_EXHAUSTED comments should seed ledger"
    assert store["comment_posts"] == []
    assert not any(kind for kind, _ in store["events"] if "kimi" in kind.lower())

def test_partial_and_ambiguous_failures_restore_state_labels_worker():
    for fail_at in ("state_partial", "state_save", "issue_label", "pr_label", "issue_readback", "pr_readback", "event_append"):
        outcome, backup, before, after, before_worker, after_worker, st, store = run_recovery(fail_at=fail_at)
        assert outcome != "PASS", fail_at
        assert before == after, fail_at
        assert before_worker == after_worker, fail_at
        assert store["issue_labels"] == {"loop:repairing"}, fail_at
        assert store["pr_labels"] == {"loop:repairing"}, fail_at
        assert any(kind == "trusted_v155_recovery_rollback" for kind, _ in store["events"]), fail_at

def test_atomic_deploy_recovery_success():
    outcome, backup, before, after, before_worker, after_worker, st, store = run_recovery(deploy=True)
    assert outcome == "PASS", outcome
    assert before_worker != after_worker
    assert st["cycles"] == 2 and st["status"] == "WAITING_GITHUB"
    assert any(kind == "trusted_v155_deploy_recovery_existing_pr" for kind, _ in store["events"])

def test_atomic_deploy_failure_restores_worker_and_state():
    outcome, backup, before, after, before_worker, after_worker, st, store = run_recovery(fail_at="state_partial", deploy=True)
    assert outcome != "PASS"
    assert before == after
    assert before_worker == after_worker
    assert any(kind == "trusted_v155_deploy_recovery_rollback" for kind, _ in store["events"])

def test_main_trusted_commands_are_lock_guarded():
    src = MODULE.read_text(encoding="utf-8")
    assert "--trusted-v155-deploy-recover-existing-pr" in src
    assert "trusted_v155_deploy_recover_existing_pr" in src
    assert "with SingleInstanceLock(lock_path)" in src

if __name__ == "__main__":
    test_cli_lock_contention_aborts_before_mutation()
    test_event_chronology_fail_closed()
    test_authoritative_repo_dir_fail_closed_before_mutation()
    test_recovery_success_and_legacy_dedupe()
    test_partial_and_ambiguous_failures_restore_state_labels_worker()
    test_atomic_deploy_recovery_success()
    test_atomic_deploy_failure_restores_worker_and_state()
    test_main_trusted_commands_are_lock_guarded()
    print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION,"checks":8,"authoritative_repo_dir":"PASS","event_chronology":"PASS","partial_write_rollback":"PASS","cli_lock_contention":"PASS","atomic_deploy_recovery":"PASS"}, indent=2))
