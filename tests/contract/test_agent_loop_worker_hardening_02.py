#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
CONTRACT_PATH = ROOT / "scripts/agent_loop/local_worker/worker_contract.json"

spec = importlib.util.spec_from_file_location("agent_worker_hardening_02", MODULE_PATH)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
checks: dict[str, bool] = {}

def expect_error(fn, contains: str) -> None:
    try:
        fn()
    except Exception as exc:
        assert contains.lower() in str(exc).lower(), (contains, str(exc))
    else:
        raise AssertionError(f"expected error containing {contains!r}")

def valid_spec() -> dict:
    return {
        "schema_version": 1,
        "front_id": "PILOT-KIMI-CODEX-TEST01",
        "repo": "cesarmanuel8102/AI_Vault",
        "owner": "cesarmanuel8102",
        "base_branch": "codex/own-capital-sustainable-return",
        "expected_base_sha": "a" * 40,
        "work_branch": "agent/pilot-test01",
        "objective": "Create the exact harmless pilot marker.",
        "test_profile": "pilot",
        "max_kimi_cycles": 3,
        "allowed_paths": [
            "docs/agent_loop/pilot/PILOT_MARKER.md",
            "docs/agent_loop/pilot/EXECUTOR_REPORT.json",
        ],
        "forbidden_paths": sorted(worker.REQUIRED_FORBIDDEN_PATHS | {"C:/AI_VAULT_CANONICAL"}),
    }

def issue_from(payload: dict, author: str = "cesarmanuel8102") -> dict:
    return {
        "author": {"login": author},
        "body": "<!-- AGENT_LOOP_SPEC\n" + json.dumps(payload) + "\nAGENT_LOOP_SPEC -->",
    }

cfg = {
    "repo": "cesarmanuel8102/AI_Vault",
    "owner": "cesarmanuel8102",
    "base_branch": "codex/own-capital-sustainable-return",
    "max_kimi_cycles_default": 6,
    "test_profiles": {"pilot": ["python", "scripts/agent_loop/pilot_verify.py", "--local"]},
    "opencode_model": "ollama-cloud/kimi-k2.7-code",
    "opencode_output_token_max": 4096,
}

parsed = worker.parse_spec(issue_from(valid_spec()), cfg)
assert set(parsed["allowed_paths"]) == worker.PROFILE_ALLOWED_PATHS["pilot"]
expect_error(lambda: worker.parse_spec(issue_from(valid_spec(), "attacker"), cfg), "untrusted")
bad = valid_spec(); bad["work_branch"] = "agent/real-16c"
expect_error(lambda: worker.parse_spec(issue_from(bad), cfg), "pilot worker")
bad = valid_spec(); bad["allowed_paths"].append("tmp_agent/brain_v9/main.py")
expect_error(lambda: worker.parse_spec(issue_from(bad), cfg), "trusted profile")
bad = valid_spec(); bad["expected_base_sha"] = "short"
expect_error(lambda: worker.parse_spec(issue_from(bad), cfg), "40-character")
checks["trusted_spec_profile"] = True

assert worker.path_allowed("docs/agent_loop/pilot/PILOT_MARKER.md", parsed["allowed_paths"], parsed["forbidden_paths"])
assert not worker.path_allowed("tmp_agent/brain_v9/main.py", parsed["allowed_paths"], parsed["forbidden_paths"])
checks["path_boundary"] = True

old_env = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY")}
try:
    os.environ["GH_TOKEN"] = "secret"
    os.environ["GITHUB_TOKEN"] = "secret"
    os.environ["OPENAI_API_KEY"] = "secret"
    env = worker.opencode_env(cfg, ROOT)
    assert all(k not in env for k in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY"))
    permission = json.loads(env["OPENCODE_CONFIG_CONTENT"])["permission"]
    assert permission["bash"] == "deny"
    assert permission["external_directory"] == "deny"
finally:
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
checks["credential_and_shell_boundary"] = True

original_name = worker.os.name
original_which = worker.shutil.which
original_comspec = os.environ.get("COMSPEC")
try:
    worker.os.name = "nt"
    worker.shutil.which = lambda name: {
        "opencode": r"C:\\Tools\\opencode.cmd",
        "cmd.exe": r"C:\\Windows\\System32\\cmd.exe",
    }.get(name)
    os.environ["COMSPEC"] = r"C:\\Windows\\System32\\cmd.exe"
    command = worker.command_for_subprocess(["opencode", "run", "hello world"])
    assert command[:4] == [r"C:\\Windows\\System32\\cmd.exe", "/d", "/s", "/c"]
    assert "opencode.cmd" in command[4]
finally:
    worker.os.name = original_name
    worker.shutil.which = original_which
    if original_comspec is None:
        os.environ.pop("COMSPEC", None)
    else:
        os.environ["COMSPEC"] = original_comspec
checks["windows_cmd_resolution"] = True

original_run = worker.run
try:
    worker._OPENCODE_RUN_HELP = None
    worker.run = lambda *args, **kwargs: "Options:\n  --model\n  --auto\n"
    assert worker.opencode_run_supports("--auto") is True
    worker._OPENCODE_RUN_HELP = None
    worker.run = lambda *args, **kwargs: "Options:\n  --model\n"
    assert worker.opencode_run_supports("--auto") is False
finally:
    worker.run = original_run
    worker._OPENCODE_RUN_HELP = None
checks["dynamic_cli_flags"] = True

with tempfile.TemporaryDirectory() as td:
    lock = Path(td) / "worker.lock"
    with worker.SingleInstanceLock(lock):
        expect_error(lambda: worker.SingleInstanceLock(lock).__enter__(), "another worker")
checks["single_instance_lock"] = True

captured = {}
original_edit = worker.edit_labels
try:
    worker.edit_labels = lambda repo, number, add=(), remove=(): captured.update(repo=repo, number=number, add=set(add), remove=set(remove))
    worker.set_phase("o/r", 7, "loop:ci")
    assert captured["add"] == {"loop:ci"}
    assert "loop:blocked" in captured["remove"] and "agent:queued" in captured["remove"]
finally:
    worker.edit_labels = original_edit
checks["exclusive_labels"] = True

assert worker.classify_error(RuntimeError("unknown option --auto")) == "loop:blocked"
assert worker.classify_error(RuntimeError("rate limit")) == "loop:token-exhausted"
assert worker.classify_error(RuntimeError("temporary TLS timeout")) == "RETRY"
checks["bounded_error_classification"] = True

with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "repo"; repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    marker = repo / "docs/agent_loop/pilot/PILOT_MARKER.md"
    marker.parent.mkdir(parents=True)
    marker.write_text("# Agent Loop Pilot\n", encoding="utf-8")
    log = Path(td) / "opencode.jsonl"; log.write_text("{}\n", encoding="utf-8")
    cfg2 = dict(cfg, install_root=str(Path(td) / "install"))
    payload = valid_spec(); payload["expected_base_sha"] = base
    worker.write_executor_report(cfg2, payload, repo, 2, 1, ["docs/agent_loop/pilot/PILOT_MARKER.md"], True, "PASS", log)
    report = json.loads((repo / "docs/agent_loop/pilot/EXECUTOR_REPORT.json").read_text(encoding="utf-8"))
    assert set(report["changed_files"]) == worker.PROFILE_ALLOWED_PATHS["pilot"]
checks["executor_report_consistency"] = True

assert contract["worker_version"] == worker.WORKER_VERSION == "1.5.1"
assert contract["pilot_only"] is True and contract["general_fronts_supported"] is False
assert contract["hardening"]["agent_shell_denied"] is True
checks["contract_truthfulness"] = True

failed = [name for name, ok in checks.items() if not ok]
print(json.dumps({"status": "PASS" if not failed else "FAIL", "checks": checks, "failed": failed}, indent=2))
raise SystemExit(0 if not failed else 1)
