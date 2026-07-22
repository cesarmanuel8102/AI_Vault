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
MANIFEST_PATH = ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json"
ROADMAP_PATH = ROOT / "docs/roadmap/BRAIN_101_ROADMAP.md"

module_spec = importlib.util.spec_from_file_location("agent_worker_r1_1", WORKER_PATH)
assert module_spec and module_spec.loader
worker = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(worker)

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
        "front_id": "BRAIN-101-R1.1-TEST",
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
        "roadmap_item_id": "R1.1",
        "dependencies": ["R0"],
        "human_final_authority": True,
    }


def expect_error(spec, contains, current_cfg=None):
    try:
        worker.validate_roadmap_contract(current_cfg or cfg(), spec)
    except Exception as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"expected error containing {contains!r}")


binding = worker.validate_roadmap_contract(cfg(), valid_spec())
assert binding["roadmap_id"] == "BRAIN-101"
assert binding["roadmap_item_id"] == "R1.1"
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
bad = valid_spec(); bad["roadmap_item_id"] = "R1.2"; bad["dependencies"] = ["R1.1"]; expect_error(bad, "not authorized active")
bad = valid_spec(); bad["dependencies"] = []; expect_error(bad, "dependency declaration mismatch")
bad = valid_spec(); bad["human_final_authority"] = False; expect_error(bad, "must be true")

bad_manifest = copy.deepcopy(manifest)
bad_manifest["roadmap_sha256"] = "0" * 64
expect_error(valid_spec(), "manifest hash", cfg(source(bad_manifest)))
bad_manifest = copy.deepcopy(manifest)
bad_manifest["roadmap_items"]["R1.1"]["dependencies"] = ["R9.9"]
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

state = {"spec": valid_spec(), "roadmap_binding": binding}
worker.validate_persisted_roadmap_binding(state)
state["spec"]["roadmap_item_id"] = "R1.2"
try:
    worker.validate_persisted_roadmap_binding(state)
except ValueError as exc:
    assert "binding mismatch" in str(exc)
else:
    raise AssertionError("persisted binding mutation was accepted")

with tempfile.TemporaryDirectory() as td:
    runtime_cfg = cfg(install_root=td)
    issue = {
        "number": 101,
        "title": "R1.1",
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
        assert saved["roadmap_binding"]["roadmap_item_id"] == "R1.1"
        assert calls[0][0] == "roadmap_manifest_validated"
        assert calls[1] == "execute"
    finally:
        for name, value in originals.items():
            setattr(worker, name, value)

print("PASS: Agent Loop R1.1 roadmap manifest validation")
