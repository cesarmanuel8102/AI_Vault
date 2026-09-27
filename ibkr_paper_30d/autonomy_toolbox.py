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
from typing import Any

from .autonomous_research import ResearchRequest, ResearchResult, ResearchTool
from .autonomy_workspace import AutonomyWorkspace


QUANTCONNECT_TIMEOUT_SECONDS = 120.0


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


class AutonomyToolbox:
    """Capability extension over the IBKR research toolbox."""

    def __init__(self, base_toolbox: Any, workspace: AutonomyWorkspace | None) -> None:
        self.base = base_toolbox
        self.workspace = workspace

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
                        "Status of the optional QuantConnect research laboratory. "
                        "Optional: you decide whether a research question warrants it."
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
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=True,
                data=_quantconnect_status(),
                error=None,
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
    """Execute a read-only QuantConnect CLI command.

    Whitelisted subcommands only: the lean CLI must never be able to
    touch IBKR state, and live-trading subcommands are excluded.
    """

    allowed_first = {"config", "list", "report", "data", "backtest", "research", "object-store", "logs", "cloud"}
    if not arguments:
        return {"success": False, "error": "no command provided"}
    head = str(arguments[0]).lower()
    if head not in allowed_first:
        return {
            "success": False,
            "error": f"quantconnect command not allowed: {head}",
        }
    lean = shutil.which("lean")
    if lean is None:
        return {"success": False, "error": "lean CLI not available"}
    try:
        completed = subprocess.run(
            [lean, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "quantconnect command timed out"}
    return {
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[: MAX_OUTPUT],
        "stderr": (completed.stderr or "")[: MAX_OUTPUT],
    }


MAX_OUTPUT = 32 * 1024