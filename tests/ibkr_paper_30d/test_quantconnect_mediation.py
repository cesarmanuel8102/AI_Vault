from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from ibkr_paper_30d.autonomous_research import ResearchRequest, ResearchTool
from ibkr_paper_30d.autonomy_toolbox import (
    AutonomyToolbox,
    QuantConnectMediator,
    run_quantconnect_command,
)
from ibkr_paper_30d.autonomy_workspace import AutonomyWorkspace


class BaseToolbox:
    def manifest(self):
        return []

    def execute(self, request, bundle):
        raise AssertionError("base toolbox should not receive QuantConnect requests")


class Runner:
    def __init__(self, *, stdout: str = "lean 1.2.3", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any):
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, self.returncode, stdout=self.stdout, stderr=""
        )


class Backend:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result or {"returncode": 0, "stdout": "backtest complete", "stderr": ""}
        self.calls: list[dict[str, Any]] = []

    def execute(self, *, operation: str, project_path: Path, timeout_seconds: float):
        self.calls.append(
            {
                "operation": operation,
                "project_path": project_path,
                "timeout_seconds": timeout_seconds,
            }
        )
        return dict(self.result)


def _request(arguments: dict[str, Any]) -> ResearchRequest:
    return ResearchRequest(
        request_id="qc-1",
        tool=ResearchTool.QUANTCONNECT,
        arguments=arguments,
        purpose="optional research",
    )


def test_status_invokes_only_version_with_a_clean_environment_and_redacts_output(tmp_path: Path) -> None:
    runner = Runner(stdout="lean 1.2.3 TOKEN=supersecret DU1234567")
    mediator = QuantConnectMediator(
        workspace_root=tmp_path,
        executable="C:/Python/Scripts/lean.exe",
        runner=runner,
    )

    result = mediator.execute({"operation": "STATUS"})

    assert result["status"] == "RUNTIME_AVAILABLE"
    assert "supersecret" not in str(result)
    assert "DU1234567" not in str(result)
    command, kwargs = runner.calls[0]
    assert command == ["C:/Python/Scripts/lean.exe", "--version"]
    assert kwargs["shell"] is False
    assert set(kwargs["env"]) == {"SystemRoot"}


def test_missing_cli_is_optional_unavailable_and_not_an_error(tmp_path: Path) -> None:
    result = QuantConnectMediator(
        workspace_root=tmp_path,
        executable=None,
    ).execute({"operation": "STATUS"})

    assert result == {
        "status": "OPTIONAL_UNAVAILABLE",
        "operation": "STATUS",
        "required": False,
        "reason": "LEAN_CLI_UNAVAILABLE",
    }


@pytest.mark.parametrize(
    "arguments",
    (
        {"operation": "RAW_COMMAND", "arguments": ["live", "--brokerage", "ib"]},
        {"operation": "LIVE"},
        {"operation": "RUN_LOCAL_BACKTEST", "project": "../../Secrets"},
        {"operation": "RUN_LOCAL_BACKTEST", "project": "C:/repo/project"},
        {"operation": "RUN_LOCAL_BACKTEST", "project": "project; whoami"},
        {"operation": "RUN_LOCAL_BACKTEST", "project": "project", "brokerage": "ibkr"},
    ),
)
def test_unauthorized_operations_paths_and_fields_are_rejected(
    tmp_path: Path, arguments: dict[str, Any]
) -> None:
    mediator = QuantConnectMediator(
        workspace_root=tmp_path,
        executable="lean.exe",
        runner=Runner(),
        backend=Backend(),
    )

    result = mediator.execute(arguments)

    assert result["status"] == "UNAUTHORIZED_OPERATION"
    assert "credential" not in str(result).lower()


def test_backtest_requires_an_explicit_secure_backend(tmp_path: Path) -> None:
    project = tmp_path / "experiments" / "quantconnect" / "alpha"
    project.mkdir(parents=True)
    mediator = QuantConnectMediator(
        workspace_root=tmp_path,
        executable="lean.exe",
        runner=Runner(),
    )

    result = mediator.execute(
        {"operation": "RUN_LOCAL_BACKTEST", "project": "alpha", "timeout_seconds": 30}
    )

    assert result["status"] == "OPTIONAL_UNAVAILABLE"
    assert result["reason"] == "SECURE_BACKTEST_BACKEND_UNAVAILABLE"


def test_backtest_backend_receives_only_a_canonical_workspace_project(tmp_path: Path) -> None:
    project = tmp_path / "experiments" / "quantconnect" / "alpha"
    project.mkdir(parents=True)
    backend = Backend()
    mediator = QuantConnectMediator(
        workspace_root=tmp_path,
        executable="lean.exe",
        runner=Runner(),
        backend=backend,
    )

    result = mediator.execute(
        {"operation": "RUN_LOCAL_BACKTEST", "project": "alpha", "timeout_seconds": 30}
    )

    assert result["status"] == "RUNTIME_AVAILABLE"
    assert result["operation"] == "RUN_LOCAL_BACKTEST"
    assert backend.calls == [
        {
            "operation": "RUN_LOCAL_BACKTEST",
            "project_path": project.resolve(),
            "timeout_seconds": 30.0,
        }
    ]


def test_toolbox_returns_optional_unavailable_without_blocking_core_research(tmp_path: Path) -> None:
    workspace = AutonomyWorkspace(tmp_path / "workspace")
    mediator = QuantConnectMediator(workspace_root=workspace.paths.root, executable=None)
    toolbox = AutonomyToolbox(BaseToolbox(), workspace, quantconnect=mediator)

    result = toolbox.execute(_request({"operation": "STATUS"}), None)

    assert result.success is True
    assert result.data["status"] == "OPTIONAL_UNAVAILABLE"
    assert result.error is None


def test_legacy_raw_command_entrypoint_never_executes_lean(tmp_path: Path) -> None:
    result = run_quantconnect_command(["backtest", "project"])

    assert result["status"] == "UNAUTHORIZED_OPERATION"
    assert result["success"] is False
