from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1"


@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
def test_multi_universe_service_script_parses(shell: str) -> None:
    executable = shutil.which(shell)
    if executable is None:
        pytest.skip(f"{shell} unavailable")
    command = (
        f"$e=$null;$t=$null;[Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{exit 1}}"
    )
    completed = subprocess.run([executable, "-NoProfile", "-Command", command])
    assert completed.returncode == 0


def test_multi_universe_launcher_is_direct_and_fail_closed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    lowered = source.lower()

    assert "RUN_IBKR_MARKET_DATA_GATE.ps1" not in source
    assert "--multi-universe-authority-path" in source
    assert "$TransitionAuthorityPath" in source
    assert "$ValidateOnly" in source
    assert "4001" not in source
    assert "reqGlobalCancel" not in source
    assert "Remove-Item" not in source
    assert "Start-Process" not in source
    assert "--target-successor-epoch-id" in source
    assert "--target-successor-definition-sha256" in source
    assert "validated_only" in lowered
