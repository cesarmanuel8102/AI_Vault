from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from ibkr_paper_30d.autonomy_workspace import AutonomyWorkspace, WorkspaceViolation


class RecordingSandbox:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run(
        self,
        *,
        workspace_root: Path,
        script_relative: str,
        arguments: tuple[str, ...],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "workspace_root": workspace_root,
                "script_relative": script_relative,
                "arguments": arguments,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "schema": "RESEARCH_SANDBOX_RUN_V1",
            "status": "COMPLETED",
            "returncode": 0,
            "elapsed_ms": 1,
            "stdout": "sandboxed\n",
            "stderr": "",
            "resource_usage": {},
            "generated_artifacts": [],
            "failure_reason": None,
        }


def test_workspace_delegates_script_execution_to_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = RecordingSandbox()
    workspace = AutonomyWorkspace(tmp_path / "workspace", sandbox=sandbox)
    workspace.write_artifact("tools/probe.py", "print('sandboxed')\n")

    def owner_context_execution_forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("Owner-context subprocess execution is forbidden")

    monkeypatch.setattr(subprocess, "run", owner_context_execution_forbidden)
    result = workspace.run_script(
        "tools/probe.py",
        arguments=["alpha", "beta"],
        timeout_seconds=12,
    )

    assert result["status"] == "COMPLETED"
    assert result["stdout"] == "sandboxed\n"
    assert sandbox.calls == [
        {
            "workspace_root": (tmp_path / "workspace").resolve(),
            "script_relative": "tools/probe.py",
            "arguments": ("alpha", "beta"),
            "timeout_seconds": 12.0,
        }
    ]


def test_workspace_has_no_owner_context_execution_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = AutonomyWorkspace(tmp_path / "workspace")
    workspace.write_artifact("tools/probe.py", "print('unsafe')\n")

    def owner_context_execution_forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("Owner-context subprocess execution attempted")

    monkeypatch.setattr(subprocess, "run", owner_context_execution_forbidden)

    with pytest.raises(WorkspaceViolation, match="secure research sandbox unavailable"):
        workspace.run_script("tools/probe.py")


def test_sandbox_receipt_never_carries_broker_write_authority(tmp_path: Path) -> None:
    sandbox = RecordingSandbox()
    workspace = AutonomyWorkspace(tmp_path / "workspace", sandbox=sandbox)
    workspace.write_artifact("tools/probe.py", "print('ok')\n")

    result = workspace.run_script("tools/probe.py")

    serialized = str(result).lower()
    for forbidden in (
        "placeorder",
        "cancelorder",
        "reqglobalcancel",
        "order_authority",
        "authorize",
    ):
        assert forbidden not in serialized
