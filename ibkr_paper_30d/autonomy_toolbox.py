"""AUTONOMY_EPOCH_1 research toolbox extension.

Wraps the existing IBKR research toolbox with three capability tools:

* WORKSPACE — inspect/create/manage the persistent model workspace.
* RUN_RESEARCH_SCRIPT — execute model-created python research scripts
  in an isolated subprocess (no broker authority, no credentials, no
  kernel imports reachable through the host process).
* QUANTCONNECT — optional research lab access through the locally
  configured `lean` CLI. Availability is reported honestly; the tool
  never blocks trading and never mutates IBKR state.

These are capabilities, not prescriptions: the model decides whether to
use them. None of them carries broker-write authority of any kind.
"""

from __future__ import annotations

import shutil
import subprocess
import os
import re
from pathlib import Path
from typing import Any, Callable, Protocol

from .autonomous_research import ResearchRequest, ResearchResult, ResearchTool
from .autonomy_workspace import AutonomyWorkspace
from .redaction import redact_text


QUANTCONNECT_TIMEOUT_SECONDS = 120.0
MAX_OUTPUT = 32 * 1024
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_AUTO_EXECUTABLE = object()


def quantconnect_available() -> bool:
    """Report whether the optional QuantConnect lab is configured.

    Availability only. This must never gate trading decisions.
    """

    lean = shutil.which("lean")
    if lean is None:
        return False
    return True


def _quantconnect_status() -> dict[str, Any]:
    lean = shutil.which("lean")
    return {
        "available": lean is not None,
        "cli": lean or "",
        "capability": "optional research laboratory (backtests, historical research, simulations)",
        "required": False,
        "notes": (
            "Use when you judge a backtest or simulation has positive "
            "expected value. This capability cannot mutate IBKR execution "
            "state. No credentials are exposed to you."
        ),
    }


class QuantConnectBackend(Protocol):
    def execute(
        self,
        *,
        operation: str,
        project_path: Path,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


def _bounded_redacted(value: Any) -> str:
    return redact_text(str(value or ""))[:MAX_OUTPUT]


class QuantConnectMediator:
    """Typed, optional QuantConnect research boundary.

    The default mediator can inspect runtime availability. Model-authored
    projects execute only when a separately reviewed secure backend is
    injected; the Owner-context Lean CLI is never used as that backend.
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        executable: str | None | object = _AUTO_EXECUTABLE,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        backend: QuantConnectBackend | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.executable = (
            shutil.which("lean") if executable is _AUTO_EXECUTABLE else executable
        )
        self.runner = runner
        self.backend = backend

    def execute(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(arguments or {})
        operation = str(payload.get("operation") or "STATUS").upper()
        allowed_fields = {
            "STATUS": {"operation"},
            "LIST_LOCAL_PROJECTS": {"operation"},
            "RUN_LOCAL_BACKTEST": {"operation", "project", "timeout_seconds"},
        }
        if operation not in allowed_fields or set(payload) - allowed_fields[operation]:
            return self._unauthorized(operation)
        if operation == "STATUS":
            return self._status()
        if operation == "LIST_LOCAL_PROJECTS":
            root = self.workspace_root / "experiments" / "quantconnect"
            projects = (
                sorted(item.name for item in root.iterdir() if item.is_dir() and not item.is_symlink())
                if root.is_dir()
                else []
            )
            return {
                "status": "RUNTIME_AVAILABLE" if self.executable else "OPTIONAL_UNAVAILABLE",
                "operation": operation,
                "required": False,
                "projects": projects[:100],
            }
        return self._run_local_backtest(payload)

    def _status(self) -> dict[str, Any]:
        if not self.executable:
            return {
                "status": "OPTIONAL_UNAVAILABLE",
                "operation": "STATUS",
                "required": False,
                "reason": "LEAN_CLI_UNAVAILABLE",
            }
        environment = {"SystemRoot": os.environ["SystemRoot"]} if "SystemRoot" in os.environ else {}
        try:
            completed = self.runner(
                [self.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
                shell=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "status": "FAILED",
                "operation": "STATUS",
                "required": False,
                "reason": type(exc).__name__,
            }
        if completed.returncode != 0:
            return {
                "status": "OPTIONAL_UNAVAILABLE",
                "operation": "STATUS",
                "required": False,
                "reason": "LEAN_CLEAN_ENVIRONMENT_PROBE_FAILED",
                "stderr": _bounded_redacted(completed.stderr),
            }
        return {
            "status": "RUNTIME_AVAILABLE",
            "operation": "STATUS",
            "required": False,
            "version": _bounded_redacted(completed.stdout),
            "secure_backtest_backend": self.backend is not None,
        }

    def _run_local_backtest(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_name = payload.get("project")
        if not isinstance(project_name, str) or not _PROJECT_NAME.fullmatch(project_name):
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        project_root = (self.workspace_root / "experiments" / "quantconnect").resolve()
        project = (project_root / project_name).resolve()
        if project_root not in project.parents or not project.is_dir() or project.is_symlink():
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        try:
            timeout = float(payload.get("timeout_seconds", QUANTCONNECT_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        if not 1.0 <= timeout <= 600.0:
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        if self.backend is None:
            return {
                "status": "OPTIONAL_UNAVAILABLE",
                "operation": "RUN_LOCAL_BACKTEST",
                "required": False,
                "reason": "SECURE_BACKTEST_BACKEND_UNAVAILABLE",
            }
        try:
            completed = self.backend.execute(
                operation="RUN_LOCAL_BACKTEST",
                project_path=project,
                timeout_seconds=timeout,
            )
        except Exception as exc:
            return {
                "status": "FAILED",
                "operation": "RUN_LOCAL_BACKTEST",
                "required": False,
                "reason": _bounded_redacted(type(exc).__name__),
            }
        return {
            "status": "RUNTIME_AVAILABLE" if completed.get("returncode") == 0 else "FAILED",
            "operation": "RUN_LOCAL_BACKTEST",
            "required": False,
            "returncode": int(completed.get("returncode", 1)),
            "stdout": _bounded_redacted(completed.get("stdout")),
            "stderr": _bounded_redacted(completed.get("stderr")),
        }

    @staticmethod
    def _unauthorized(operation: str) -> dict[str, Any]:
        return {
            "status": "UNAUTHORIZED_OPERATION",
            "operation": operation[:80],
            "required": False,
            "reason": "OPERATION_OR_ARGUMENTS_NOT_ALLOWED",
        }


class AutonomyToolbox:
    """Capability extension over the IBKR research toolbox."""

    def __init__(
        self,
        base_toolbox: Any,
        workspace: AutonomyWorkspace | None,
        *,
        quantconnect: QuantConnectMediator | None = None,
    ) -> None:
        self.base = base_toolbox
        self.workspace = workspace
        self.quantconnect = quantconnect or QuantConnectMediator(
            workspace_root=workspace.paths.root if workspace is not None else Path.cwd()
        )

    def workspace_summary(self) -> dict[str, Any] | None:
        """Persistent-workspace context for the prompt (capability, not duty)."""

        if self.workspace is None:
            return None
        return self.workspace.summary()

    def manifest(self) -> list[dict[str, Any]]:
        manifest = list(self.base.manifest())
        manifest.extend(
            [
                {
                    "tool": ResearchTool.WORKSPACE.value,
                    "purpose": (
                        "Persistent research workspace you control. Inspect, create, "
                        "read, delete and list your own research artifacts (notes, "
                        "datasets, experiments, tools). Artifacts persist across cycles."
                    ),
                },
                {
                    "tool": ResearchTool.RUN_RESEARCH_SCRIPT.value,
                    "purpose": (
                        "Run a python research script you created in tools/. The script "
                        "executes in an isolated subprocess without broker access. "
                        "Use WORKSPACE first to create the script."
                    ),
                },
                {
                    "tool": ResearchTool.QUANTCONNECT.value,
                    "purpose": (
                        "Typed access to the optional QuantConnect research laboratory: "
                        "STATUS, LIST_LOCAL_PROJECTS, or RUN_LOCAL_BACKTEST through an "
                        "approved secure backend. Raw commands and LIVE are unavailable."
                    ),
                },
            ]
        )
        return manifest

    def execute(self, request: ResearchRequest, bundle: Any) -> ResearchResult:
        if request.tool == ResearchTool.WORKSPACE:
            return self._workspace(request)
        if request.tool == ResearchTool.RUN_RESEARCH_SCRIPT:
            return self._run_script(request)
        if request.tool == ResearchTool.QUANTCONNECT:
            data = self.quantconnect.execute(dict(request.arguments or {}))
            data.setdefault("available", data.get("status") == "RUNTIME_AVAILABLE")
            success = data.get("status") in {"RUNTIME_AVAILABLE", "OPTIONAL_UNAVAILABLE"}
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=success,
                data=data,
                error=None if success else str(data.get("reason") or "quantconnect_failed"),
            )
        return self.base.execute(request, bundle)

    # ------------------------------------------------------------------

    def _workspace(self, request: ResearchRequest) -> ResearchResult:
        arguments = dict(request.arguments or {})
        operation = str(arguments.get("operation", "list")).lower()
        try:
            if operation == "list":
                data = {
                    "success": True,
                    "artifacts": self.workspace.list_artifacts(),
                    "summary": self.workspace.summary(),
                }
            elif operation == "read":
                data = {**self.workspace.read_artifact(str(arguments["path"]))}
                data["success"] = True
            elif operation == "write":
                artifact = self.workspace.write_artifact(
                    str(arguments["path"]),
                    str(arguments["content"]),
                    cycle_id=str(arguments.get("cycle_id", "")),
                )
                data = {"success": True, "artifact": artifact}
            elif operation == "delete":
                data = {
                    "success": True,
                    **self.workspace.delete_artifact(
                        str(arguments["path"]),
                        cycle_id=str(arguments.get("cycle_id", "")),
                    ),
                }
            else:
                data = {
                    "success": False,
                    "error": f"unknown workspace operation: {operation}",
                }
        except Exception as exc:
            data = {
                "success": False,
                "error": f"{type(exc).__name__}:{exc}"[:400],
            }
        success = bool(data.pop("success", False))
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=success,
            data=data,
            error=None if success else str(data.get("error") or "operation_failed"),
        )

    def _run_script(self, request: ResearchRequest) -> ResearchResult:
        arguments = dict(request.arguments or {})
        try:
            run = self.workspace.run_script(
                str(arguments["path"]),
                cycle_id=str(arguments.get("cycle_id", "")),
                timeout_seconds=float(arguments.get("timeout_seconds", 60)),
                arguments=[str(item) for item in (arguments.get("arguments") or [])],
            )
            data = dict(run)
            success = run.get("status") == "COMPLETED"
        except Exception as exc:
            data = {"error": f"{type(exc).__name__}:{exc}"[:400]}
            success = False
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=success,
            data=data,
            error=None if success else str(data.get("error") or "run_failed"),
        )


def run_quantconnect_command(
    arguments: list[str], *, timeout_seconds: float = QUANTCONNECT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Compatibility tombstone for the removed raw-command boundary."""

    return {
        "success": False,
        "status": "UNAUTHORIZED_OPERATION",
        "error": "raw QuantConnect commands are not allowed; use typed operations",
    }
