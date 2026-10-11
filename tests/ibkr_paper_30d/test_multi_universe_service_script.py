from pathlib import Path
import json
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
    assert "--transition-phase" not in lowered
    assert "--entry-authority-mode" not in lowered
    assert "--new-regular-entries-allowed" not in lowered
    assert "--new-continuous-entries-allowed" not in lowered


def test_validate_only_binds_receipt_finalizer_and_runtime_to_same_attempt(
    tmp_path: Path,
) -> None:
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if shell is None:
        pytest.skip("PowerShell unavailable")
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                "schema": "MULTI_UNIVERSE_LAUNCH_AUTHORITY_V1",
                "successor_epoch_id": "AUTONOMY_EPOCH_2",
                "successor_definition_sha256": "1" * 64,
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RepoRoot",
            str(ROOT),
            "-ApprovedHead",
            head,
            "-TransitionAuthorityPath",
            str(authority),
            "-ValidateOnly",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])

    assert payload["receipt_finalizer_required"] is True
    assert payload["launch_attempt_id"] in payload["receipt_finalizer_arguments"]
    assert payload["launch_attempt_id"] in payload["python_arguments"]
