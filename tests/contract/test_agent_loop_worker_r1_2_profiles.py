#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER_PATH = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
module_spec = importlib.util.spec_from_file_location("agent_worker_r1_2", WORKER_PATH)
assert module_spec and module_spec.loader
worker = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(worker)


def config(profile: str, command: list[str] | None = None) -> dict:
    default_command = ["git", "diff", "--check"] if profile == "roadmap-doc" else [sys.executable, "-m", "py_compile"]
    return {
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "max_kimi_cycles_default": 3,
        "test_profiles": {profile: command or default_command},
    }


def issue(profile: str, allowed: list[str], branch: str | None = None) -> dict:
    spec = {
        "schema_version": 1,
        "front_id": f"BRAIN-101-R1.2-{profile.upper()}",
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "expected_base_sha": "a" * 40,
        "work_branch": branch or f"agent/{profile}-r1-2",
        "objective": "Make the exact governed profile change.",
        "test_profile": profile,
        "max_kimi_cycles": 1,
        "allowed_paths": allowed,
        "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS),
    }
    return {
        "number": 56,
        "author": {"login": "cesarmanuel8102"},
        "body": f"<!-- AGENT_LOOP_SPEC {json.dumps(spec, separators=(',', ':'))} AGENT_LOOP_SPEC -->",
    }


def expect_parse_error(candidate: dict, cfg: dict, contains: str) -> None:
    try:
        worker.parse_spec(candidate, cfg)
    except Exception as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"expected parse failure containing {contains!r}")


roadmap_paths = ["ROADMAP_STATUS.json", "docs/roadmap/evidence/R1_2.md"]
test_paths = ["tests/contract/test_r1_2_example.py"]
parsed_roadmap = worker.parse_spec(issue("roadmap-doc", roadmap_paths), config("roadmap-doc"))
parsed_test = worker.parse_spec(issue("test-only", test_paths), config("test-only"))
assert parsed_roadmap["allowed_paths"] == sorted(roadmap_paths)
assert parsed_test["allowed_paths"] == test_paths

expect_parse_error(issue("roadmap-doc", roadmap_paths, "agent/test-only-wrong"), config("roadmap-doc"), "work branch")
expect_parse_error(issue("test-only", ["scripts/unsafe.py"]), config("test-only"), "trusted profile")
expect_parse_error(issue("roadmap-doc", ["docs/roadmap/../unsafe.md"]), config("roadmap-doc"), "traversal")
expect_parse_error(issue("test-only", test_paths), config("test-only", ["cmd.exe", "/c", "echo bad"]), "unsafe")
expect_parse_error(issue("roadmap-doc", []), config("roadmap-doc"), "trusted profile")
expect_parse_error(issue("test-only", [test_paths[0], test_paths[0]]), config("test-only"), "duplicates")

assert worker.profile_paths_are_trusted("roadmap-doc", set(roadmap_paths))
assert worker.profile_paths_are_trusted("test-only", set(test_paths))
assert not worker.profile_paths_are_trusted("test-only", {"tests/ok.py", "docs/not-ok.md"})
assert worker.profile_command_is_trusted("roadmap-doc", ["git", "diff", "--check"])
assert worker.profile_command_is_trusted("test-only", [sys.executable, "-m", "py_compile"])
assert not worker.profile_command_is_trusted("test-only", [sys.executable])
assert not worker.profile_command_is_trusted("test-only", [sys.executable, "-m", "pytest", "-q"])
assert not worker.profile_command_is_trusted("test-only", [sys.executable, "-c", "print('bad')"])
assert not worker.profile_command_is_trusted("test-only", ["powershell.exe", "-Command", "Write-Host bad"])

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    repo = root / "repo"
    repo.mkdir()
    existing = repo / "docs/roadmap/evidence/R1_2.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("before\n", encoding="utf-8")
    spec = copy.deepcopy(parsed_roadmap)
    model, seeds = worker.prepare_model_workspace(repo, spec, 1)
    assert set(seeds) == {"docs/roadmap/evidence/R1_2.md"}
    (model / "docs/roadmap/evidence/R1_2.md").write_text("after\n", encoding="utf-8")
    (model / "ROADMAP_STATUS.json").write_text("{}\n", encoding="utf-8")
    changed = worker.audit_and_sync_model_workspace(model, repo, seeds, spec)
    assert changed == sorted(roadmap_paths)
    assert existing.read_text(encoding="utf-8") == "after\n"
    assert (repo / "ROADMAP_STATUS.json").read_text(encoding="utf-8") == "{}\n"

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    repo = root / "repo"
    repo.mkdir()
    spec = copy.deepcopy(parsed_test)
    model, seeds = worker.prepare_model_workspace(repo, spec, 1)
    target = model / test_paths[0]
    target.parent.mkdir(parents=True)
    target.write_text("print('ok')\n", encoding="utf-8")
    (model / "unexpected.txt").write_text("bad\n", encoding="utf-8")
    try:
        worker.audit_and_sync_model_workspace(model, repo, seeds, spec)
    except worker.ModelWorkspaceScopeViolation as exc:
        assert exc.reason_code == "MODEL_WORKSPACE_EXTRA_PATHS"
    else:
        raise AssertionError("unexpected path must fail closed")

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    model = root / "model"
    model.mkdir()
    for rel in roadmap_paths:
        path = model / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("changed\n", encoding="utf-8")
    sentinel = worker.prompt_task_sentinel(parsed_roadmap["front_id"], 1)
    events = [
        {"type": "tool_use", "part": {"type": "tool", "tool": "write", "state": {"status": "completed", "input": {"filePath": rel}}}}
        for rel in roadmap_paths
    ]
    events.append({"type": "text", "part": {"type": "text", "text": sentinel}})
    log = root / "executor.jsonl"
    log.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
    original_event = worker.event
    worker.event = lambda *_a, **_k: None
    try:
        worker.validate_executor_delivery({"install_root": str(root)}, parsed_roadmap, model, log, 1, issue_no=56)
        bad_events = events[:-2] + [events[-1]]
        log.write_text("\n".join(json.dumps(item) for item in bad_events) + "\n", encoding="utf-8")
        try:
            worker.validate_executor_delivery({"install_root": str(root)}, parsed_roadmap, model, log, 1, issue_no=56)
        except worker.ExecutorAttemptConsumed as exc:
            assert exc.failure_class == "PROFILE_WRITE_CONTRACT_FAILED"
        else:
            raise AssertionError("missing exact write target must fail closed")
    finally:
        worker.event = original_event

with tempfile.TemporaryDirectory() as td:
    target = Path(td) / test_paths[0]
    target.parent.mkdir(parents=True)
    target.write_text("print('PASS')\n", encoding="utf-8")
    ok, output = worker.run_profile(config("test-only"), parsed_test, Path(td))
    assert ok and output == "TEST_ONLY_AST_VALIDATED:1"
    target.write_text("raise SystemExit(7)\n", encoding="utf-8")
    ok, output = worker.run_profile(config("test-only"), parsed_test, Path(td))
    assert ok and output == "TEST_ONLY_AST_VALIDATED:1", "valid model-authored code must not execute"
    target.write_text("def broken(:\n", encoding="utf-8")
    ok, output = worker.run_profile(config("test-only"), parsed_test, Path(td))
    assert not ok and output.startswith("TEST_ONLY_SYNTAX_INVALID:")

with tempfile.TemporaryDirectory() as td:
    multi_paths = ["tests/contract/one.py", "tests/contract/two.py"]
    multi_spec = worker.parse_spec(issue("test-only", multi_paths), config("test-only"))
    for rel in multi_paths:
        target = Path(td) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("print('PASS')\n", encoding="utf-8")
    ok, output = worker.run_profile(config("test-only"), multi_spec, Path(td))
    assert ok and output == "TEST_ONLY_AST_VALIDATED:2"

with tempfile.TemporaryDirectory() as td:
    target = Path(td) / test_paths[0]
    target.parent.mkdir(parents=True)
    target.write_text("print('PASS')\n", encoding="utf-8")
    calls: list[object] = []
    original_subprocess_run = worker.subprocess.run
    worker.subprocess.run = lambda *_a, **_k: calls.append((_a, _k)) or (_ for _ in ()).throw(AssertionError("must not execute"))
    try:
        ok, output = worker.run_profile(config("test-only"), parsed_test, Path(td))
        assert ok and output == "TEST_ONLY_AST_VALIDATED:1"
        assert calls == []
    finally:
        worker.subprocess.run = original_subprocess_run

captured: list[list[str]] = []
original_run, original_gh_json = worker.run, worker.gh_json
worker.run = lambda args, **_kwargs: captured.append(list(args)) or ("https://github.com/cesarmanuel8102/AI_Vault/pull/999" if args[:2] == ["gh", "pr"] else "")
worker.gh_json = lambda *_a, **_k: {"number": 999, "url": "https://github.com/cesarmanuel8102/AI_Vault/pull/999", "headRefOid": "b" * 40}
try:
    worker.create_pr({"repo": "cesarmanuel8102/AI_Vault", "opencode_model": "model"}, parsed_test, 56, ROOT)
finally:
    worker.run, worker.gh_json = original_run, original_gh_json
pr_create = next(args for args in captured if args[:3] == ["gh", "pr", "create"])
body = pr_create[pr_create.index("--body") + 1]
assert "AGENT_LOOP_PROFILE: test-only" in body
assert "--draft" in pr_create

pilot = copy.deepcopy(worker.PROFILE_ALLOWED_PATHS["pilot"])
assert worker.profile_paths_are_trusted("pilot", pilot)
assert not worker.profile_paths_are_trusted("pilot", {"docs/agent_loop/pilot/PILOT_MARKER.md"})

print("PASS: Agent Loop R1.2 roadmap-doc and test-only profiles")
