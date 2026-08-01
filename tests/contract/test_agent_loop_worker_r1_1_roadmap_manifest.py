#!/usr/bin/env python3
from __future__ import annotations

import copy
import base64
import hashlib
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER_PATH = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
VERIFY_PATH = ROOT / "scripts/agent_loop/pilot_verify.py"
MANIFEST_PATH = ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json"
ROADMAP_PATH = ROOT / "docs/roadmap/BRAIN_101_ROADMAP.md"

module_spec = importlib.util.spec_from_file_location("agent_worker_r1_1", WORKER_PATH)
assert module_spec and module_spec.loader
worker = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(worker)
verify_spec = importlib.util.spec_from_file_location("pilot_verify_r1_1", VERIFY_PATH)
assert verify_spec and verify_spec.loader
pilot_verify = importlib.util.module_from_spec(verify_spec)
verify_spec.loader.exec_module(pilot_verify)

def git_blob(path):
    relative = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


manifest_bytes = git_blob(MANIFEST_PATH)
roadmap_bytes = git_blob(ROADMAP_PATH)
manifest = json.loads(manifest_bytes.decode("utf-8"))
roadmap_hash = hashlib.sha256(roadmap_bytes).hexdigest()
active_items = [item_id for item_id, item in manifest["roadmap_items"].items() if item.get("status") == "AUTHORIZED_ACTIVE"]
assert len(active_items) == 1, active_items
ACTIVE_ITEM_ID = active_items[0]
ACTIVE_DEPENDENCIES = manifest["roadmap_items"][ACTIVE_ITEM_ID]["dependencies"]
CLOSED_ITEM_ID = "R1.1"


def source(current_manifest=None, current_roadmap=None):
    def load(_spec):
        selected_manifest = copy.deepcopy(current_manifest or manifest)
        selected_manifest_bytes = json.dumps(selected_manifest, indent=2, ensure_ascii=False).encode("utf-8")
        return selected_manifest, selected_manifest_bytes, current_roadmap or roadmap_bytes
    return load


def cfg(loader=None, install_root="X"):
    return {
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "install_root": install_root,
        "max_kimi_cycles_default": 3,
        "test_profiles": {"pilot": []},
        "_roadmap_manifest_loader": loader or source(),
    }


def valid_spec():
    return {
        "schema_version": 1,
        "front_id": f"BRAIN-101-{ACTIVE_ITEM_ID}-TEST",
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "expected_base_sha": "a" * 40,
        "work_branch": "agent/pilot-r1-1-test",
        "objective": "Validate the canonical roadmap binding.",
        "test_profile": "pilot",
        "max_kimi_cycles": 1,
        "allowed_paths": sorted(worker.PROFILE_ALLOWED_PATHS["pilot"]),
        "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS),
        "roadmap_id": manifest["roadmap_id"],
        "roadmap_version": manifest["roadmap_version"],
        "roadmap_sha256": roadmap_hash,
        "roadmap_item_id": ACTIVE_ITEM_ID,
        "dependencies": ACTIVE_DEPENDENCIES,
        "human_final_authority": True,
    }


def expect_error(spec, contains, current_cfg=None):
    try:
        worker.validate_roadmap_contract(current_cfg or cfg(), spec)
    except Exception as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"expected error containing {contains!r}")


def expect_persisted_error(state, contains):
    try:
        worker.validate_persisted_roadmap_binding(state)
    except Exception as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"expected persisted error containing {contains!r}")


binding = worker.validate_roadmap_contract(cfg(), valid_spec())
assert binding["roadmap_id"] == "BRAIN-101"
assert binding["roadmap_item_id"] == ACTIVE_ITEM_ID
assert binding["roadmap_sha256"] == roadmap_hash
assert binding["base_sha"] == "a" * 40

for field in ("roadmap_id", "roadmap_version", "roadmap_sha256", "roadmap_item_id", "dependencies", "human_final_authority"):
    bad = valid_spec()
    del bad[field]
    expect_error(bad, "missing fields")

bad = valid_spec(); bad["roadmap_id"] = "OTHER"; expect_error(bad, "roadmap id mismatch")
bad = valid_spec(); bad["roadmap_version"] = "0"; expect_error(bad, "roadmap version mismatch")
bad = valid_spec(); bad["roadmap_sha256"] = "0" * 64; expect_error(bad, "roadmap hash mismatch")
bad = valid_spec(); bad["roadmap_sha256"] = "A" * 64; expect_error(bad, "lowercase 64-character")
bad = valid_spec(); bad["roadmap_item_id"] = "R9.9"; expect_error(bad, "not registered")
bad = valid_spec(); bad["roadmap_item_id"] = CLOSED_ITEM_ID; bad["dependencies"] = ["R0"]; expect_error(bad, "not authorized active")
bad = valid_spec(); bad["dependencies"] = []; expect_error(bad, "dependency declaration mismatch")
bad = valid_spec(); bad["human_final_authority"] = False; expect_error(bad, "must be true")

bad_manifest = copy.deepcopy(manifest)
bad_manifest["roadmap_sha256"] = "0" * 64
expect_error(valid_spec(), "manifest hash", cfg(source(bad_manifest)))
bad_manifest = copy.deepcopy(manifest)
bad_manifest["roadmap_items"][ACTIVE_ITEM_ID]["dependencies"] = ["R9.9"]
bad = valid_spec(); bad["dependencies"] = ["R9.9"]
expect_error(bad, "dependency open", cfg(source(bad_manifest)))
expect_error(valid_spec(), "manifest hash", cfg(source(current_roadmap=roadmap_bytes + b"\nchanged")))

original_gh_json = worker.gh_json
remote_calls = []
try:
    def fake_gh_json(args):
        remote_calls.append(args)
        endpoint = args[1]
        payload = manifest_bytes if worker.ROADMAP_MANIFEST_PATH in endpoint else roadmap_bytes
        return {"type": "file", "content": base64.b64encode(payload).decode("ascii")}

    worker.gh_json = fake_gh_json
    production_cfg = cfg()
    production_cfg.pop("_roadmap_manifest_loader")
    remote_binding = worker.validate_roadmap_contract(production_cfg, valid_spec())
    assert remote_binding["roadmap_sha256"] == roadmap_hash
    assert len(remote_calls) == 2
    assert all(call[0] == "api" and ("?ref=" + "a" * 40) in call[1] for call in remote_calls)
    worker.gh_json = lambda _args: {"type": "file"}
    expect_error(valid_spec(), "source unavailable", production_cfg)
finally:
    worker.gh_json = original_gh_json

worker.validate_persisted_roadmap_binding({"spec": {"front_id": "PRE-R1"}})
expect_persisted_error({"spec": valid_spec()}, "persisted roadmap binding missing")

state = {"spec": valid_spec(), "roadmap_binding": copy.deepcopy(binding)}
worker.validate_persisted_roadmap_binding(state)
mutated = copy.deepcopy(state)
mutated["spec"]["roadmap_item_id"] = CLOSED_ITEM_ID
expect_persisted_error(mutated, "binding mismatch")
mutated = copy.deepcopy(state)
mutated["spec"]["dependencies"] = ["R9.9"]
expect_persisted_error(mutated, "binding mismatch")
mutated = copy.deepcopy(state)
del mutated["roadmap_binding"]["manifest_sha256"]
expect_persisted_error(mutated, "manifest hash invalid")
for invalid_hash in ("A" * 64, "not-a-sha"):
    mutated = copy.deepcopy(state)
    mutated["roadmap_binding"]["manifest_sha256"] = invalid_hash
    expect_persisted_error(mutated, "manifest hash invalid")
mutated = copy.deepcopy(state)
mutated["roadmap_binding"]["dependencies"] = ["R0", "R0"]
expect_persisted_error(mutated, "dependencies invalid")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    remote = root / "remote.git"
    repo = root / "repo"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    for args in (["config", "user.name", "test"], ["config", "user.email", "test@example.invalid"], ["config", "core.autocrlf", "false"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    marker = repo / "docs" / "agent_loop" / "pilot" / "PILOT_MARKER.md"
    report = repo / "docs" / "agent_loop" / "pilot" / "EXECUTOR_REPORT.json"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"base\n")
    report.write_bytes(b"{}\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "base"], check=True, capture_output=True)
    old_base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    old_spec = valid_spec()
    old_spec["expected_base_sha"] = old_base
    subprocess.run(["git", "-C", str(repo), "branch", "-M", old_spec["work_branch"]], check=True)
    marker.write_bytes(b"candidate\n")
    subprocess.run(["git", "-C", str(repo), "add", marker.relative_to(repo).as_posix()], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", f"test(agent-loop): complete {old_spec['front_id']}"], check=True, capture_output=True)
    old_head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "push", "origin", f"HEAD:refs/heads/{old_spec['work_branch']}"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-b", "base-next", old_base], check=True, capture_output=True)
    (repo / "BASE_NEXT.md").write_bytes(b"next\n")
    subprocess.run(["git", "-C", str(repo), "add", "BASE_NEXT.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "next base"], check=True, capture_output=True)
    new_base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "push", "origin", f"HEAD:refs/heads/codex/own-capital-sustainable-return"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "checkout", old_spec["work_branch"]], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "-m", f"chore(control-plane): synchronize {old_spec['front_id']} base", new_base], check=True, capture_output=True)
    first_sync = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-b", "base-latest", new_base], check=True, capture_output=True)
    (repo / "BASE_LATEST.md").write_bytes(b"latest\n")
    subprocess.run(["git", "-C", str(repo), "add", "BASE_LATEST.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "latest base"], check=True, capture_output=True)
    new_base = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "push", "origin", f"HEAD:refs/heads/codex/own-capital-sustainable-return"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "checkout", old_spec["work_branch"]], check=True, capture_output=True)
    assert subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() == first_sync
    subprocess.run(["git", "-C", str(repo), "merge", "--no-ff", "-m", f"chore(control-plane): synchronize {old_spec['front_id']} base", new_base], check=True, capture_output=True)
    sync_head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "push", "origin", f"HEAD:refs/heads/{old_spec['work_branch']}"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "reset", "--hard", old_head], check=True, capture_output=True)

    next_spec = copy.deepcopy(old_spec)
    next_spec["expected_base_sha"] = new_base
    issue_body = f"<!-- AGENT_LOOP_SPEC\n{json.dumps(next_spec, indent=2)}\nAGENT_LOOP_SPEC -->"
    issue_obj = {"number": 112, "body": issue_body, "author": {"login": "cesarmanuel8102"}, "labels": [{"name": "loop:repairing"}], "state": "OPEN"}
    pr_obj = {"number": 113, "headRefOid": sync_head, "labels": [{"name": "loop:repairing"}], "state": "OPEN"}
    state_path = root / "issue-112.json"
    state = {"issue_number": 112, "pr_number": 113, "front": old_spec["front_id"], "status": "WAITING_GITHUB", "cycles": 1,
             "last_head_sha": old_head, "repo_dir": str(repo), "spec": old_spec,
             "roadmap_binding": worker.validate_roadmap_contract(cfg(), old_spec), "updated_utc": "2026-01-01T00:00:00Z"}
    worker.save_json(state_path, state)
    original_gh_json, original_event = worker.gh_json, worker.event
    events = []
    try:
        def repair_gh_json(args):
            endpoint = args[1] if args and args[0] == "api" else ""
            if endpoint.endswith("/pulls/113"):
                return {"state": "open", "draft": True, "user": {"login": "cesarmanuel8102"},
                        "head": {"sha": sync_head, "ref": old_spec["work_branch"], "repo": {"full_name": "cesarmanuel8102/AI_Vault"}},
                        "base": {"sha": old_base, "ref": "codex/own-capital-sustainable-return"}}
            if "/git/ref/heads/" in endpoint:
                return {"object": {"sha": new_base}}
            if "/compare/" in endpoint:
                return {"status": "ahead"}
            raise AssertionError(args)

        worker.gh_json = repair_gh_json
        worker.event = lambda _cfg, kind, **fields: events.append((kind, fields))
        before_state = state_path.read_bytes()
        denied_issue = copy.deepcopy(issue_obj); denied_issue["labels"] = [{"name": "loop:ci"}]
        try:
            worker.rebind_roadmap_repair_base(cfg(), state_path, state, denied_issue, pr_obj)
        except Exception as exc:
            assert "phase mismatch" in str(exc)
        else:
            raise AssertionError("wrong Issue phase must fail closed")
        assert state_path.read_bytes() == before_state
        assert subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() == old_head

        updated = worker.rebind_roadmap_repair_base(cfg(), state_path, state, issue_obj, pr_obj)
        assert updated["spec"]["expected_base_sha"] == new_base
        assert updated["roadmap_binding"]["base_sha"] == new_base
        merged_head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        parents = subprocess.run(["git", "-C", str(repo), "rev-list", "--parents", "-n", "1", merged_head], check=True, capture_output=True, text=True).stdout.split()
        assert merged_head == sync_head
        assert parents == [sync_head, first_sync, new_base]
        assert updated["last_head_sha"] == sync_head
        assert events and events[-1][0] == "roadmap_repair_base_rebound"
    finally:
        worker.gh_json, worker.event = original_gh_json, original_event

with tempfile.TemporaryDirectory() as td:
    runtime_cfg = cfg(install_root=td)
    issue = {
        "number": 101,
        "title": "R1.2",
        "body": "",
        "author": {"login": "cesarmanuel8102"},
        "labels": [{"name": "agent:queued"}],
        "url": "https://example.invalid/101",
    }
    calls = []
    originals = {name: getattr(worker, name) for name in ("gh_json", "parse_spec", "execute_initial", "event")}
    try:
        worker.gh_json = lambda args: [issue] if args[:2] == ["issue", "list"] else (_ for _ in ()).throw(AssertionError(args))
        worker.parse_spec = lambda *_args: valid_spec()
        worker.execute_initial = lambda *_args: calls.append("execute")
        worker.event = lambda _cfg, kind, **fields: calls.append((kind, fields))
        worker.process_once(runtime_cfg)
        state_path = Path(td) / "state" / "issue-101.json"
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["roadmap_binding"]["roadmap_item_id"] == ACTIVE_ITEM_ID
        assert calls[0][0] == "roadmap_manifest_validated"
        assert calls[1] == "execute"
    finally:
        for name, value in originals.items():
            setattr(worker, name, value)

with tempfile.TemporaryDirectory() as td:
    runtime_cfg = cfg(install_root=td)
    issue = {
        "number": 104,
        "title": "R1.2 failure preservation",
        "body": "",
        "author": {"login": "cesarmanuel8102"},
        "labels": [{"name": "agent:queued"}],
        "url": "https://example.invalid/104",
    }
    originals = {
        name: getattr(worker, name)
        for name in ("gh_json", "parse_spec", "execute_initial", "event", "set_converged_phase", "publish_terminal_notification")
    }
    try:
        worker.gh_json = lambda args: [issue] if args[:2] == ["issue", "list"] else (_ for _ in ()).throw(AssertionError(args))
        worker.parse_spec = lambda *_args: valid_spec()
        worker.execute_initial = lambda *_args: (_ for _ in ()).throw(RuntimeError("post-admission failure"))
        worker.event = lambda *_args, **_kwargs: None

        def preserve_phase(_cfg, path, current, phase, **_kwargs):
            current = copy.deepcopy(current)
            current["status"] = phase
            worker.save_json(path, current)
            return current

        worker.set_converged_phase = preserve_phase
        worker.publish_terminal_notification = lambda _cfg, _path, current, _phase, _message: current
        worker.process_once(runtime_cfg)
        saved = json.loads((Path(td) / "state" / "issue-104.json").read_text(encoding="utf-8"))
        assert saved["status"] == "loop:blocked"
        assert saved["roadmap_binding"] == binding
        assert saved["state_schema_version"] == worker.STATE_SCHEMA_VERSION
    finally:
        for name, value in originals.items():
            setattr(worker, name, value)

with tempfile.TemporaryDirectory() as td:
    runtime_cfg = cfg(install_root=td)
    issue = {
        "number": 102,
        "title": "Invalid R1.2",
        "body": "",
        "author": {"login": "cesarmanuel8102"},
        "labels": [{"name": "agent:queued"}],
        "url": "https://example.invalid/102",
    }
    invalid_spec = valid_spec()
    invalid_spec["roadmap_sha256"] = "0" * 64
    calls = []
    saved_statuses = []
    originals = {
        name: getattr(worker, name)
        for name in ("gh_json", "parse_spec", "execute_initial", "event", "save_json", "set_converged_phase", "publish_terminal_notification")
    }
    try:
        worker.gh_json = lambda args: [issue] if args[:2] == ["issue", "list"] else (_ for _ in ()).throw(AssertionError(args))
        worker.parse_spec = lambda *_args: invalid_spec
        worker.execute_initial = lambda *_args: calls.append("execute")
        worker.event = lambda _cfg, kind, **fields: calls.append((kind, fields))

        def save_state(path, current):
            saved_statuses.append(current.get("status"))
            originals["save_json"](path, current)

        worker.save_json = save_state

        def set_phase(_cfg, state_path, current, phase, **_kwargs):
            current = dict(current)
            current["status"] = phase
            worker.save_json(state_path, current)
            return current

        worker.set_converged_phase = set_phase
        worker.publish_terminal_notification = lambda _cfg, _state_path, current, _phase, _message: current
        worker.process_once(runtime_cfg)
        state_path = Path(td) / "state" / "issue-102.json"
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved["status"] == "loop:blocked"
        assert "LOCAL_EXECUTION" not in saved_statuses
        assert "execute" not in calls
        assert not any(isinstance(call, tuple) and call[0] == "roadmap_manifest_validated" for call in calls)
    finally:
        for name, value in originals.items():
            setattr(worker, name, value)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    repo = root / "repo"
    repo.mkdir()
    model = root / "model"
    (model / "docs/agent_loop/pilot").mkdir(parents=True)
    (model / "docs/agent_loop/pilot/PILOT_MARKER.md").write_text(
        worker.pilot_marker_text(valid_spec()["front_id"]), encoding="utf-8"
    )
    log = root / "opencode.jsonl"
    log.write_text("\n".join(json.dumps(item) for item in [
        {"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {
            "status": "completed", "input": {"filePath": "docs/agent_loop/pilot/PILOT_MARKER.md"}}}},
        {"type": "text", "part": {"type": "text", "text": worker.prompt_task_sentinel(valid_spec()["front_id"], 1)}},
    ]) + "\n", encoding="utf-8")
    state_path = root / "state" / "issue-103.json"
    initial_state = {
        "issue_number": 103,
        "front": valid_spec()["front_id"],
        "spec": valid_spec(),
        "roadmap_binding": copy.deepcopy(binding),
        "cycles": 0,
        "status": "LOCAL_EXECUTION",
        "local_retry_count": 17,
        "state_schema_version": worker.STATE_SCHEMA_VERSION,
        "worker_version": worker.WORKER_VERSION,
        "updated_utc": worker.utc(),
    }
    worker.save_json(state_path, initial_state)
    runtime_cfg = cfg(install_root=td)
    runtime_cfg["opencode_model"] = "ollama-cloud/deepseek-v4-pro"
    issue = {"number": 103}
    originals = {
        name: getattr(worker, name)
        for name in (
            "set_phase", "prepare_repo", "event", "prepare_model_workspace", "run_kimi",
            "validate_executor_delivery", "audit_and_sync_model_workspace", "changed_files",
            "path_allowed", "run_profile", "run", "create_pr", "write_final_local_report",
            "set_converged_phase",
        )
    }
    try:
        worker.set_phase = lambda *_a, **_k: None
        worker.prepare_repo = lambda *_a, **_k: repo
        worker.event = lambda *_a, **_k: None
        worker.prepare_model_workspace = lambda *_a, **_k: (model, {})
        worker.run_kimi = lambda *_a, **_k: (log, "session-r1")
        worker.validate_executor_delivery = lambda *_a, **_k: None
        worker.audit_and_sync_model_workspace = lambda *_a, **_k: None
        worker.changed_files = lambda *_a, **_k: (
            sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])
            if (repo / "docs/agent_loop/pilot/EXECUTOR_REPORT.json").exists()
            else ["docs/agent_loop/pilot/PILOT_MARKER.md"]
        )
        worker.path_allowed = lambda path, *_a, **_k: path in worker.PROFILE_ALLOWED_PATHS["pilot"]
        worker.run_profile = lambda *_a, **_k: (True, "PASS")
        worker.run = lambda *_a, **_k: ""
        worker.create_pr = lambda *_a, **_k: {
            "number": 39, "url": "https://example.invalid/pr/39", "headRefOid": "b" * 40,
        }
        worker.write_final_local_report = lambda *_a, **_k: root / "final.json"

        def converge(_cfg, path, current, phase, *, pr_number=None):
            assert phase == "loop:ci" and pr_number == 39
            current = copy.deepcopy(current)
            current["status"] = phase
            worker.save_json(path, current)
            return current

        worker.set_converged_phase = converge
        worker.execute_initial(runtime_cfg, issue, valid_spec(), state_path)
    finally:
        for name, value in originals.items():
            setattr(worker, name, value)

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["status"] == "loop:ci"
    assert saved["cycles"] == 1 and saved["pr_number"] == 39
    assert saved["state_schema_version"] == worker.STATE_SCHEMA_VERSION
    assert saved["roadmap_binding"] == binding
    assert saved["local_retry_count"] == 17
    report = json.loads((repo / "docs/agent_loop/pilot/EXECUTOR_REPORT.json").read_text(encoding="utf-8"))
    assert report["roadmap_binding"] == {
        key: binding[key]
        for key in (
            "repository", "integration_branch", "approval_status", "r0_status",
            "roadmap_id", "roadmap_version", "roadmap_item_id", "roadmap_sha256",
            "roadmap_item_status", "manifest_sha256", "base_sha", "dependencies",
        )
    }
    assert report["human_final_authority"] is True
    assert report["live_trading_enabled"] is False
    assert report["merge_performed"] is False
    assert report["canonical_local_sync"] is False

    canonical_base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    canonical_report = copy.deepcopy(report)
    canonical_report["base_sha"] = canonical_base
    canonical_report["roadmap_binding"].update({
        "base_sha": canonical_base,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "roadmap_sha256": hashlib.sha256(roadmap_bytes).hexdigest(),
    })

    def errors(candidate, manifest_override=None, roadmap_override=None):
        if manifest_override is None and roadmap_override is None:
            return pilot_verify.validate_roadmap_governance(candidate, canonical_base, ROOT)

        def loader(_sha, path):
            return (manifest_override if manifest_override is not None else manifest_bytes) \
                if path.endswith("MANIFEST.json") else (roadmap_override if roadmap_override is not None else roadmap_bytes)
        return pilot_verify.validate_roadmap_governance(candidate, canonical_base, ROOT, loader)

    def mismatch(field, value, expected_error):
        candidate = copy.deepcopy(canonical_report)
        candidate["roadmap_binding"][field] = value
        assert expected_error in errors(candidate), (field, errors(candidate))

    assert errors(canonical_report) == []
    missing = copy.deepcopy(canonical_report); del missing["roadmap_binding"]
    assert "roadmap binding missing" in errors(missing)
    unsafe = copy.deepcopy(canonical_report); unsafe["live_trading_enabled"] = True
    assert "live_trading_enabled must be false" in errors(unsafe)
    mismatch("roadmap_id", "OTHER", "roadmap binding roadmap_id mismatch")
    mismatch("roadmap_version", "0", "roadmap binding roadmap_version mismatch")
    mismatch("roadmap_item_id", "R9.9", "roadmap binding item not registered")
    mismatch("roadmap_sha256", "0" * 64, "roadmap binding roadmap_sha256 mismatch")
    mismatch("manifest_sha256", "0" * 64, "roadmap binding manifest_sha256 mismatch")
    mismatch("dependencies", [], "roadmap binding dependencies mismatch")
    mismatch("dependencies", ["R0", "R0"], "roadmap binding dependencies invalid")
    mismatch("repository", "other/repo", "roadmap binding repository mismatch")
    mismatch("integration_branch", "other", "roadmap binding integration_branch mismatch")
    mismatch("approval_status", "PENDING", "roadmap binding approval_status mismatch")
    mismatch("r0_status", "OPEN", "roadmap binding r0_status mismatch")
    mismatch("roadmap_item_status", "BLOCKED", "roadmap binding item status mismatch")

    for field in ("repository", "integration_branch", "approval_status", "r0_status", "roadmap_item_status"):
        candidate = copy.deepcopy(canonical_report)
        del candidate["roadmap_binding"][field]
        assert field in " ".join(errors(candidate)), (field, errors(candidate))

    modified_manifest = copy.deepcopy(manifest)
    modified_manifest["roadmap_items"][ACTIVE_ITEM_ID]["status"] = "BLOCKED_PENDING_R1_1"
    modified_manifest_bytes = json.dumps(modified_manifest, indent=2).encode("utf-8")
    assert "roadmap binding item not authorized active" in errors(canonical_report, manifest_override=modified_manifest_bytes)
    modified_manifest = copy.deepcopy(manifest); modified_manifest["approval_status"] = "PENDING"
    modified_manifest_bytes = json.dumps(modified_manifest, indent=2).encode("utf-8")
    assert "canonical manifest approval status mismatch" in errors(canonical_report, manifest_override=modified_manifest_bytes)
    modified_manifest = copy.deepcopy(manifest); modified_manifest["repository"] = "other/repo"
    assert "canonical manifest repository mismatch" in errors(
        canonical_report, manifest_override=json.dumps(modified_manifest).encode("utf-8"))
    modified_manifest = copy.deepcopy(manifest); modified_manifest["integration_branch"] = "other"
    assert "canonical manifest integration branch mismatch" in errors(
        canonical_report, manifest_override=json.dumps(modified_manifest).encode("utf-8"))
    modified_manifest = copy.deepcopy(manifest); modified_manifest["r0_status"] = "OPEN"
    assert "canonical manifest r0 status mismatch" in errors(
        canonical_report, manifest_override=json.dumps(modified_manifest).encode("utf-8"))
    assert "canonical roadmap bytes hash mismatch" in errors(canonical_report, roadmap_override=roadmap_bytes + b"\nchanged")
    assert "roadmap binding manifest_sha256 mismatch" in errors(canonical_report, manifest_override=manifest_bytes + b" ")

print("PASS: Agent Loop R1.1 roadmap manifest validation")
