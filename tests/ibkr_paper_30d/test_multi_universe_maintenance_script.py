from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1"


def test_script_defaults_to_validate_only_and_forbids_dangerous_surfaces():
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "validateonly" in lowered
    assert "if ($apply)" in lowered
    assert "4001" not in source
    assert "globalcancel" not in lowered
    assert "reqglobalcancel" not in lowered
    assert "unregister-scheduledtask" not in lowered
    assert "remove-item" not in lowered
    assert "$apply = $true" not in lowered


@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh"])
def test_script_parses_in_both_powershell_engines(shell):
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} unavailable")
    command = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',"
        "[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_default_invocation_is_report_only(tmp_path):
    executable = shutil.which("pwsh") or shutil.which("powershell.exe")
    if executable is None:
        pytest.skip("PowerShell unavailable")
    before = tuple(tmp_path.iterdir())
    result = subprocess.run(
        [
            executable,
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    after = tuple(tmp_path.iterdir())
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"mode":"VALIDATE_ONLY"' in result.stdout.replace(" ", "")
    assert before == after
