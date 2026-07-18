#!/usr/bin/env python3
"""Lossless OpenCode prompt transport contract for v157 worker.

The v157 worker must deliver the full multiline prompt to the OpenCode CLI
without passing it through cmd.exe, so that the model receives every byte of
the prompt including the sentinel and the editing instructions.
"""
from __future__ import annotations

import hashlib
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
spec = importlib.util.spec_from_file_location("agent_worker_v157_transport", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake", encoding="utf-8")
    return str(path)


def _make_workspace(tmp: Path, *, node_dir: Path | None = None, shim_dir: Path | None = None) -> dict:
    bin_dir = tmp / "Safe Bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    cmd_dir = tmp / "System32"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    node = (node_dir or bin_dir) / "node.exe"
    _touch(node)
    shim_path = (shim_dir or bin_dir) / "opencode.CMD"
    shim_path.parent.mkdir(parents=True, exist_ok=True)
    print_argv = tmp / "print_argv.py"
    print_argv.write_text(
        "import sys, json, hashlib\n"
        "args = sys.argv[1:]\n"
        "print('argv_capture=' + json.dumps({"
        "  'argv': args,"
        "  'hashes': [hashlib.sha256(a.encode('utf-8')).hexdigest() for a in args],"
        "  'lengths': [len(a) for a in args]"
        "}, ensure_ascii=False))\n",
        encoding="utf-8",
    )
    shim_path.write_text(
        f'@echo off\n"{sys.executable}" "{print_argv}" %*\n',
        encoding="utf-8",
    )
    entrypoint = bin_dir / "opencode"
    entrypoint.write_text(
        '#!/usr/bin/env node\n'
        "const crypto = require('crypto');\n"
        "function sha256(t) { return crypto.createHash('sha256').update(t, 'utf8').digest('hex'); }\n"
        "const argv = process.argv.slice(2).map((a, i) => ({ index: i, length: a.length, sha256: sha256(a), escaped_repr: JSON.stringify(a) }));\n"
        "console.log('argv_capture=' + JSON.stringify({ argv_count: argv.length, args: argv }, null, 2));\n",
        encoding="utf-8",
    )
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
        "runtime_min_versions": {"opencode": "1.2.27", "git": "2.0", "gh": "2.0", "python": "3.11", "node": "18.0"},
    }
    return cfg


def _run_node_command(cmd: list[str]) -> subprocess.CompletedProcess:
    real_node = shutil.which("node.exe") or shutil.which("node") or "node"
    real_cmd = [real_node, *cmd[1:]]
    return subprocess.run(real_cmd, capture_output=True, text=False, shell=False)


def _parse_capture(stdout: bytes) -> dict:
    text = stdout.decode("utf-8", "ignore")
    # The fake entrypoint prints "argv_capture=" followed by JSON on one or more lines.
    prefix = "argv_capture="
    idx = text.find(prefix)
    if idx == -1:
        return {}
    return json.loads(text[idx + len(prefix):])


def test_lossless_multiline_lf() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = "line1\nline2\nline3\nsentinel=ACK|pipe"
            cmd = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\workspace", "--model", "m", "--agent", "a", "--format", "json", "--title", "t", prompt]
            )
            assert isinstance(cmd, list), cmd
            p = _run_node_command(cmd)
            assert p.returncode == 0, p.stderr.decode("utf-8", "ignore")
            capture = _parse_capture(p.stdout)
            assert [a["escaped_repr"] for a in capture.get("args", [])] == [json.dumps(x) for x in ["run", "--dir", r"C:\workspace", "--model", "m", "--agent", "a", "--format", "json", "--title", "t", prompt]], capture
            assert capture['args'][-1]['sha256'] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_multiline_crlf() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = "line1\r\nline2\r\nline3"
            cmd = worker.command_for_subprocess(["opencode", "run", "--dir", r"C:\workspace", prompt])
            assert isinstance(cmd, list)
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][-1]['escaped_repr'] == json.dumps(prompt)
            assert capture['args'][-1]['sha256'] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_full_prompt_sentinel() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = worker.make_prompt({"front_id": "FASEB-V157-PROBE", "objective": "write marker and return sentinel"}, 1)
            assert "ACK_TASK_ID=FASEB-V157-PROBE|cycle=1" in prompt
            cmd = worker.command_for_subprocess(["opencode", "run", "--dir", r"C:\workspace", "--model", "m", prompt])
            assert isinstance(cmd, list)
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][-1]['escaped_repr'] == json.dumps(prompt)
            assert capture['args'][-1]['sha256'] == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            assert capture['args'][-1]['length'] == len(prompt)
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_workspace_with_spaces() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = "edit\nnow"
            cmd = worker.command_for_subprocess(
                ["opencode", "run", "--dir", r"C:\AI Vault With Spaces", "--model", "m", prompt]
            )
            assert isinstance(cmd, list)
            assert r"C:\AI Vault With Spaces" in cmd
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][2]['escaped_repr'] == json.dumps(r"C:\AI Vault With Spaces")
            assert capture['args'][-1]['escaped_repr'] == json.dumps(prompt)
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_metacharacters() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = 'task A & B (C) ^ D | E <F> G!H%I "quoted"'
            cmd = worker.command_for_subprocess(["opencode", "run", "--dir", r"C:\dir", "--model", "m", prompt])
            assert isinstance(cmd, list)
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][-1]['escaped_repr'] == json.dumps(prompt)
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_empty_prompt() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            cmd = worker.command_for_subprocess(["opencode", "run", "--dir", r"C:\dir", ""])
            assert isinstance(cmd, list)
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][-1]['escaped_repr'] == json.dumps("")
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_no_shell_injection() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = "hello && calc.exe || whoami"
            cmd = worker.command_for_subprocess(["opencode", "run", "--dir", r"C:\dir", "--model", "m", prompt])
            assert isinstance(cmd, list)
            p = _run_node_command(cmd)
            assert p.returncode == 0
            capture = _parse_capture(p.stdout)
            assert capture['args'][-1]['escaped_repr'] == json.dumps(prompt)
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_lossless_entrypoint_resolution() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            prompt = "x"
            cmd = worker.command_for_subprocess(["opencode", "run", prompt])
            assert isinstance(cmd, list)
            assert cmd[0].endswith("node.exe")
            assert cmd[1].endswith("opencode")
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_missing_node_falls_back_to_cmd_shim() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        cfg["runtime_executables"].pop("node_exe")
        original_path = os.environ.get("PATH", "")
        # Restrict PATH so shutil.which cannot discover a real node.exe.
        os.environ["PATH"] = str(Path(cfg["runtime_executables"]["cmd_exe"]).parent)
        try:
            worker.configure_runtime_resolution(cfg, require_config=False)
            cmd = worker.command_for_subprocess(["opencode", "run", "prompt"])
            assert isinstance(cmd, str)
            assert "cmd.exe" in cmd.lower()
        finally:
            os.environ["PATH"] = original_path
            worker._RUNTIME_EXECUTABLES = {}


def test_missing_entrypoint_falls_back_to_cmd_shim() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        cfg["runtime_executables"].pop("opencode_entrypoint")
        worker.configure_runtime_resolution(cfg, require_config=False)
        try:
            cmd = worker.command_for_subprocess(["opencode", "run", "prompt"])
            assert isinstance(cmd, str)
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def test_runtime_version_min_check() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cfg = _make_workspace(tmp)
        # Use real opencode and node so we can run --version through the lossless path.
        cfg["runtime_executables"]["opencode_cmd"] = "C:/Users/cesar/AppData/Roaming/npm/opencode.CMD"
        cfg["runtime_executables"]["node_exe"] = "C:/Program Files/nodejs/node.exe"
        cfg["runtime_executables"]["opencode_entrypoint"] = "C:/Users/cesar/AppData/Roaming/npm/node_modules/opencode-ai/bin/opencode"
        cfg["executable_allowlist_dirs"].extend(["C:/Program Files/nodejs", "C:/Users/cesar/AppData/Roaming/npm"])
        worker.configure_runtime_resolution(cfg, require_config=True)
        try:
            version_cmd = worker.command_for_subprocess(["opencode", "--version"])
            import subprocess
            out, _ = worker.decode_process_output(
                subprocess.run(version_cmd, capture_output=True, text=False, timeout=30, shell=False).stdout
            )
            assert out.strip() == "1.2.27"
            assert not worker._safe_version_at_least(out, "99.99.99")
            assert worker._safe_version_at_least(out, "1.2.27")
        finally:
            worker._RUNTIME_EXECUTABLES = {}


def main() -> int:
    tests = [
        test_lossless_multiline_lf,
        test_lossless_multiline_crlf,
        test_lossless_full_prompt_sentinel,
        test_lossless_workspace_with_spaces,
        test_lossless_metacharacters,
        test_lossless_empty_prompt,
        test_lossless_no_shell_injection,
        test_lossless_entrypoint_resolution,
        test_missing_node_falls_back_to_cmd_shim,
        test_missing_entrypoint_falls_back_to_cmd_shim,
        test_runtime_version_min_check,
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
