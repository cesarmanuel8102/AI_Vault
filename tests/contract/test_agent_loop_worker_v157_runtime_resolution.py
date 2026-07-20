#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("agent_worker_v157_runtime", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

IS_WINDOWS = os.name == "nt"


class Completed:
    def __init__(self, stdout: bytes = b"", returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake\n", encoding="utf-8")
    return str(path)


def cfg_for(root: Path) -> dict:
    bin_dir = root / "Safe Bin"
    cmd_dir = root / "System32"
    return {
        "install_root": str(root / "install"),
        "opencode_model": "ollama-cloud/kimi-k2.7-code",
        "opencode_output_token_max": 4096,
        "runtime_executables": {
            "git_exe": touch(bin_dir / "git.exe"),
            "gh_exe": touch(bin_dir / "gh.exe"),
            "python_exe": touch(bin_dir / "python.exe"),
            "opencode_cmd": touch(bin_dir / "opencode.CMD"),
            "node_exe": touch(bin_dir / "node.exe"),
            "opencode_entrypoint": touch(bin_dir / "opencode"),
            "cmd_exe": touch(cmd_dir / "cmd.exe"),
        },
        "executable_allowlist_dirs": [str(bin_dir), str(cmd_dir)],
        "runtime_min_versions": {
            "git": "2.0",
            "gh": "2.0",
            "python": "3.11",
            "opencode": "0.0",
        },
    }


def expect_error(fn, text: str) -> None:
    try:
        fn()
    except Exception as exc:
        assert text.lower() in str(exc).lower(), (text, str(exc))
    else:
        raise AssertionError(f"expected {text}")


def main() -> int:
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cfg = cfg_for(root)
        old_path = os.environ.get("PATH")
        try:
            os.environ["PATH"] = ""
            resolved = worker.configure_runtime_resolution(cfg, require_config=True)
            assert resolved["gh"].endswith("gh.exe")
            assert resolved["opencode"].endswith("opencode.CMD")
            cmd = worker.command_for_subprocess(["opencode", "run", "arg with spaces"])
            assert isinstance(cmd, list), cmd
            if IS_WINDOWS:
                assert cmd[0].endswith("node.exe")
                assert cmd[1].endswith("opencode")
            else:
                assert cmd[0].endswith("opencode.CMD"), cmd
            assert "arg with spaces" in cmd[-1]
            checks["path_empty_absolute_config_passes"] = True
            checks["lossless_node_entrypoint_used"] = True
            worker._RUNTIME_EXECUTABLES.pop("node", None)
            worker._RUNTIME_EXECUTABLES.pop("opencode_entrypoint", None)
            cmd = worker.command_for_subprocess(["opencode", "run", "arg with spaces"])
            if IS_WINDOWS:
                assert isinstance(cmd, str), cmd
                assert cmd.endswith("cmd.exe") or "cmd.exe" in cmd
                assert "/d /s /c" in cmd
            else:
                assert isinstance(cmd, list), cmd
                assert cmd[0].endswith("opencode.CMD"), cmd
                assert "cmd.exe" not in " ".join(cmd).lower()
            assert "arg with spaces" in cmd
            checks["cmd_fallback_uses_configured_cmd"] = True
        finally:
            worker._RUNTIME_EXECUTABLES = {}
            if old_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = old_path

        bad = cfg_for(root / "bad-relative")
        bad["runtime_executables"]["gh_exe"] = "gh.exe"
        expect_error(lambda: worker.configure_runtime_resolution(bad, require_config=True), "not_absolute")
        checks["relative_path_fails"] = True

        bad = cfg_for(root / "bad-missing")
        bad["runtime_executables"]["gh_exe"] = str(root / "missing" / "gh.exe")
        expect_error(lambda: worker.configure_runtime_resolution(bad, require_config=True), "not_file")
        checks["missing_file_fails"] = True

        bad = cfg_for(root / "bad-extension")
        bad_file = root / "bad-extension" / "Safe Bin" / "gh.txt"
        bad["runtime_executables"]["gh_exe"] = touch(bad_file)
        expect_error(lambda: worker.configure_runtime_resolution(bad, require_config=True), "extension_denied")
        checks["extension_fails"] = True

        bad = cfg_for(root / "bad-outside")
        outside = root / "outside" / "gh.exe"
        bad["runtime_executables"]["gh_exe"] = touch(outside)
        expect_error(lambda: worker.configure_runtime_resolution(bad, require_config=True), "outside_allowlist")
        checks["outside_allowlist_fails"] = True

        old_run = worker.subprocess.run
        try:
            calls = []

            def fake_run(args, **kwargs):
                calls.append(list(args))
                text = " ".join(str(x) for x in args)
                if "gh.exe" in text and "auth" in text:
                    return Completed(b"github.com\nToken: gho_************************************\n")
                if "opencode" in text and "models" in text:
                    return Completed(b"ollama-cloud/kimi-k2.7-code\n")
                if "--version" in text and "python.exe" in text:
                    return Completed(b"Python 3.11.9\n")
                if "--version" in text and "gh.exe" in text:
                    return Completed(b"gh version 2.60.0\n")
                if "--version" in text and "opencode" in text:
                    return Completed(b"opencode 0.1.0\n")
                if "--version" in text:
                    return Completed(b"git version 2.50.0\n")
                return Completed(b"ok\n")

            worker.subprocess.run = fake_run
            preflight_cfg = cfg_for(root / "preflight")
            result = worker.run_preflight(preflight_cfg)
            assert result["status"] == "PASS"
            assert all(item["ok"] for item in result["checks"].values())
            assert calls, "preflight did not execute checks"
            checks["preflight_uses_config_without_path"] = True
        finally:
            worker.subprocess.run = old_run
            worker._RUNTIME_EXECUTABLES = {}

        bad = cfg_for(root / "bad-preflight")
        bad["runtime_executables"]["gh_exe"] = str(root / "bad-preflight" / "missing" / "gh.exe")
        expect_error(lambda: worker.run_preflight(bad), "not_file")
        checks["preflight_fails_before_mutation"] = True

    failed = [name for name, ok in checks.items() if not ok]
    print({"status": "PASS" if not failed else "FAIL", "checks": checks, "failed": failed})
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
