#!/usr/bin/env python3
"""Real Windows cmd.exe quoting contract for v157 worker.

This test creates a real .CMD shim on disk and invokes it through the
worker, verifying that arguments containing spaces, shell metacharacters,
and backslashes arrive exactly once in the shim's argv.

No mocks are used for the cmd.exe transport layer.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("agent_worker_v157_cmd", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake", encoding="utf-8")
    return str(path)


def _make_workspace(tmp: Path, shim_dir: Path | None = None) -> tuple[Path, Path, dict]:
    bin_dir = tmp / "Safe Bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cmd_dir = tmp / "System32"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    shim_path = (shim_dir or bin_dir) / "opencode.CMD"
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    print_argv = tmp / "print_argv.py"
    print_argv.write_text(
        "import sys, json\nprint('argv_capture=' + json.dumps(sys.argv[1:], ensure_ascii=False))\n",
        encoding="utf-8",
    )
    shim_path.write_text(
        f'@echo off\n"{sys.executable}" "{print_argv}" %*\n',
        encoding="utf-8",
    )
    # Create a minimal fake JS entrypoint so the lossless path can be resolved.
    entrypoint = bin_dir / "opencode"
    entrypoint.write_text(
        "#!/usr/bin/env node\n"
        "const crypto = require('crypto');\n"
        "function sha256(t) { return crypto.createHash('sha256').update(t, 'utf8').digest('hex'); }\n"
        "const argv = process.argv.slice(2).map((a, i) => ({ index: i, length: a.length, sha256: sha256(a), escaped_repr: JSON.stringify(a) }));\n"
        "console.log('argv_capture=' + JSON.stringify({ argv_count: argv.length, args: argv }, null, 2));\n",
        encoding="utf-8",
    )
    node = bin_dir / "node.exe"
    _touch(node)
    cfg = {
        "install_root": str(tmp / "install"),
        "opencode_model": "ollama-cloud/kimi-k2.7-code",
        "opencode_output_token_max": 4096,
        "runtime_executables": {
            "cmd_exe": _touch(cmd_dir / "cmd.exe"),
            "opencode_cmd": str(shim_path),
            "node_exe": str(node),
            "opencode_entrypoint": str(entrypoint),
            "git_exe": _touch(bin_dir / "git.exe"),
            "gh_exe": _touch(bin_dir / "gh.exe"),
            "python_exe": _touch(bin_dir / "python.exe"),
        },
        "executable_allowlist_dirs": [str(bin_dir), str(cmd_dir)] + ([str(shim_dir)] if shim_dir else []),
        "runtime_min_versions": {"opencode": "0.0", "git": "2.0", "gh": "2.0", "python": "3.11"},
    }
    return bin_dir, cmd_dir, cfg


def _run_worker_command(cmd: str | list[str]) -> subprocess.CompletedProcess:
    """Run the command returned by the worker.

    For .CMD shims the worker returns a single command-line string and we run
    it through the real cmd.exe. For the lossless Node path it returns a list.
    """
    if isinstance(cmd, list):
        real_node = shutil.which("node.exe") or shutil.which("node") or "node"
        return subprocess.run([real_node, *cmd[1:]], capture_output=True, text=False, shell=False)
    real_cmd = shutil.which("cmd.exe") or "cmd.exe"
    first_space = cmd.find(" ")
    if first_space != -1:
        cmd = str(real_cmd) + cmd[first_space:]
    return subprocess.run(cmd, capture_output=True, text=False, shell=False)


def _parse_capture(stdout: bytes) -> list[str]:
    text = stdout.decode("utf-8", "ignore")
    prefix = "argv_capture="
    idx = text.find(prefix)
    if idx == -1:
        return []
    payload = json.loads(text[idx + len(prefix):])
    if isinstance(payload, list):
        return payload
    def _json_unescape(s: str) -> str:
        if len(s) >= 2 and s[0] == s[-1] == '"':
            s = s[1:-1]
        return s.replace(chr(92)+chr(92), chr(92))
    return [_json_unescape(a["escaped_repr"]) for a in payload.get("args", [])]


def test_workspace_without_spaces() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_workspace(tmp)
        worker.configure_runtime_resolution(_make_workspace(tmp)[2], require_config=True)
        try:
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\workspace", "--model", "m", "simple prompt"]
            )
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv == ["run", "--dir", r"C:\workspace", "--model", "m", "simple prompt"], argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_workspace_with_spaces() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_workspace(tmp)
        worker.configure_runtime_resolution(_make_workspace(tmp)[2], require_config=True)
        try:
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\AI Vault With Spaces", "--model", "m", "prompt with spaces"]
            )
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv == ["run", "--dir", r"C:\AI Vault With Spaces", "--model", "m", "prompt with spaces"], argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_cmd_shim_path_with_spaces() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        shim_dir = tmp / "Shim Dir"
        _make_workspace(tmp, shim_dir=shim_dir)
        worker.configure_runtime_resolution(_make_workspace(tmp, shim_dir=shim_dir)[2], require_config=True)
        try:
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\AI Vault", "prompt"]
            )
            # The worker should resolve the spaced .CMD path to a short 8.3 path.
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv == ["run", "--dir", r"C:\AI Vault", "prompt"], argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_prompt_with_metacharacters() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_workspace(tmp)
        worker.configure_runtime_resolution(_make_workspace(tmp)[2], require_config=True)
        try:
            prompt = "task A & B (C) ^ D | E <F> G!H%I"
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\dir", "--model", "m", prompt]
            )
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv[-1] == prompt, argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_backslash_path() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_workspace(tmp)
        worker.configure_runtime_resolution(_make_workspace(tmp)[2], require_config=True)
        try:
            path = r"C:\Users\cesar\AI Vault\repo"
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", path, "prompt"]
            )
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv == ["run", "--dir", path, "prompt"], argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_no_command_injection() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _make_workspace(tmp)
        worker.configure_runtime_resolution(_make_workspace(tmp)[2], require_config=True)
        try:
            command = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\dir", "hello && calc.exe"]
            )
            p = _run_worker_command(command)
            assert p.returncode == 0, p.stderr.decode("cp1252", "ignore")
            argv = _parse_capture(p.stdout)
            assert argv[-1] == "hello && calc.exe", argv
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_sanitize_command_for_log_does_not_leak_prompt() -> None:
    long_prompt = "x" * 300
    safe = worker.sanitize_command_for_log(["opencode", "run", "--dir", r"C:\secret", "--model", "m", long_prompt])
    assert any("truncated" in str(x) for x in safe), safe
    assert len(str(safe[-1])) <= 160, safe


def test_command_log_redacts_sensitive_words() -> None:
    safe = worker.sanitize_command_for_log(["gh", "auth", "login", "--token", "secret123"])
    assert any(str(x) == "<redacted>" for x in safe), safe


def main() -> int:
    tests = [
        test_workspace_without_spaces,
        test_workspace_with_spaces,
        test_cmd_shim_path_with_spaces,
        test_prompt_with_metacharacters,
        test_backslash_path,
        test_no_command_injection,
        test_sanitize_command_for_log_does_not_leak_prompt,
        test_command_log_redacts_sensitive_words,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL: {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())