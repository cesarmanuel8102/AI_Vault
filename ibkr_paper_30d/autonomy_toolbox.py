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

import json
import shutil
import subprocess
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from .autonomous_research import (
    AutonomousOpenOrderAction,
    AutonomousPositionAction,
    AutonomousTradeProposal,
    ProposalValidation,
    ResearchRequest,
    ResearchResult,
    ResearchTool,
)
from .autonomy_workspace import AutonomyWorkspace
from .source_provenance import tolerant_sha256
from .redaction import redact_text
from .trader_invocation import TraderDecision, TraderInputBundle

QUANTCONNECT_TIMEOUT_SECONDS = 120.0
MAX_OUTPUT = 32 * 1024
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_AUTO_EXECUTABLE = object()
_SAFE_INPUT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
RESEARCH_INPUT_DIRECTORY = "datasets/research_inputs"
SANDBOX_WORKSPACE_ROOT = "/workspace"
NON_RETRYABLE_REPEAT_WINDOW_SECONDS = 6 * 60 * 60

WORKSPACE_OPERATIONS = ("list", "read", "write", "delete", "write_from_research_result")
_WORKSPACE_OPERATION_ALIASES = {
    "create": "write",
    "update": "write",
    "put": "write",
    "get": "read",
    "inspect": "list",
    "ls": "list",
    "remove": "delete",
    "create_from_research_result": "write_from_research_result",
}
_WORKSPACE_FIELDS = {
    "list": {"path"},
    "read": {"path", "artifact_id"},
    "write": {"path", "content", "cycle_id"},
    "delete": {"path", "artifact_id", "cycle_id"},
    "write_from_research_result": {"path", "source_request_id", "json_pointer", "cycle_id"},
}
# Descriptive hints the model sends; they never change host behaviour.
_WORKSPACE_IGNORED_FIELDS = {"include_content", "overwrite", "artifact_type", "description"}
RUN_SCRIPT_ARGUMENTS = ("path", "arguments", "timeout_seconds", "cycle_id", "input_request_ids")
_RUN_SCRIPT_ALIASES = {
    "script_path": "path",
    "script": "path",
    "args": "arguments",
    "argv": "arguments",
    "input_request_id": "input_request_ids",
    "input_result_request_id": "input_request_ids",
    "input_source_request_id": "input_request_ids",
}
QUANTCONNECT_OPERATIONS = ("STATUS", "LIST_LOCAL_PROJECTS", "RUN_LOCAL_BACKTEST")


def tool_error(
    tool: ResearchTool,
    operation: str,
    error_type: str,
    *,
    retryable: bool,
    corrective_hint: str,
    **extra: Any,
) -> dict[str, Any]:
    """Structured, model-actionable failure description."""

    return {
        "tool": tool.value,
        "operation": str(operation)[:80],
        "error_type": error_type,
        "retryable": retryable,
        "corrective_hint": corrective_hint,
        "error": error_type,
        **extra,
    }


def _canonical_arguments(
    arguments: dict[str, Any], aliases: dict[str, str], tool: ResearchTool, operation: str
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fold documented aliases into canonical names; conflicting values fail."""

    canonical: dict[str, Any] = {}
    for key, value in arguments.items():
        name = aliases.get(key, key)
        if name in canonical and canonical[name] != value:
            return {}, tool_error(
                tool, operation, "CONFLICTING_ARGUMENTS", retryable=False,
                corrective_hint=f"Provide '{name}' only once (aliases: "
                + ", ".join(sorted(k for k, v in aliases.items() if v == name)) + ").",
            )
        canonical[name] = value
    return canonical, None


def _research_result_data(history: list[dict[str, Any]] | None, request_id: str) -> Any:
    for event in reversed(history or ()):
        if event.get("type") != "research_result":
            continue
        payload = event.get("payload") or {}
        if isinstance(payload.get("result"), dict):
            payload = payload["result"]
        if str(payload.get("request_id") or "") == request_id and payload.get("success"):
            return payload.get("data")
    raise LookupError(request_id)


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    current = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(token)]
        else:
            current = current[token]
    return current


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
        payload, conflict = _canonical_arguments(
            dict(arguments or {}), {"action": "operation", "op": "operation"},
            ResearchTool.QUANTCONNECT, "STATUS",
        )
        if conflict is not None:
            return {**conflict, "status": "UNAUTHORIZED_OPERATION", "required": False}
        operation = str(payload.get("operation") or "STATUS").upper()
        payload["operation"] = operation
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
                sorted(
                    item.name
                    for item in root.iterdir()
                    if item.is_dir() and not item.is_symlink()
                )
                if root.is_dir()
                else []
            )
            return {
                "status": (
                    "RUNTIME_AVAILABLE" if self.executable else "OPTIONAL_UNAVAILABLE"
                ),
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
        environment = (
            {"SystemRoot": os.environ["SystemRoot"]}
            if "SystemRoot" in os.environ
            else {}
        )
        # The Lean CLI needs a home directory; give it an empty, dedicated one
        # outside the model workspace instead of the Owner profile.
        isolated_home = self.workspace_root.parent / "research_lean_home"
        isolated_home.mkdir(parents=True, exist_ok=True)
        environment["HOME"] = str(isolated_home)
        environment["USERPROFILE"] = str(isolated_home)
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
        if not isinstance(project_name, str) or not _PROJECT_NAME.fullmatch(
            project_name
        ):
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        project_root = (self.workspace_root / "experiments" / "quantconnect").resolve()
        project = (project_root / project_name).resolve()
        if (
            project_root not in project.parents
            or not project.is_dir()
            or project.is_symlink()
        ):
            return self._unauthorized("RUN_LOCAL_BACKTEST")
        try:
            timeout = float(
                payload.get("timeout_seconds", QUANTCONNECT_TIMEOUT_SECONDS)
            )
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
            "status": (
                "RUNTIME_AVAILABLE" if completed.get("returncode") == 0 else "FAILED"
            ),
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
            "tool": ResearchTool.QUANTCONNECT.value,
            "error_type": "OPERATION_OR_ARGUMENTS_NOT_ALLOWED",
            "retryable": False,
            "valid_operations": list(QUANTCONNECT_OPERATIONS),
            "corrective_hint": (
                "Use {'operation': 'STATUS'} or {'operation': 'LIST_LOCAL_PROJECTS'}, or "
                "{'operation': 'RUN_LOCAL_BACKTEST', 'project': <name under "
                "experiments/quantconnect>, 'timeout_seconds': 1-600}."
            ),
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
        self._non_retryable_failures: dict[str, float] = {}

    def workspace_summary(self) -> dict[str, Any] | None:
        """Persistent-workspace context for the prompt (capability, not duty)."""

        if self.workspace is None:
            return None
        return self.workspace.summary()

    def broker_server_time_utc(self) -> str:
        """Return only the broker clock required by host-side safety checks."""

        clock_reader = getattr(self.base, "broker_server_time_utc", None)
        server_time_utc = (
            clock_reader() if callable(clock_reader)
            else self.base._account_state({}).get("server_time_utc")
        )
        if not isinstance(server_time_utc, str) or not server_time_utc:
            raise RuntimeError("BROKER_SERVER_TIME_UNAVAILABLE")
        return server_time_utc

    def account_reconciliation_snapshot(
        self,
        *,
        observed_at_utc: str | None = None,
    ) -> dict[str, Any]:
        """Delegate the host-only account cash observation to the IBKR adapter."""

        return self.base.account_reconciliation_snapshot(
            observed_at_utc=observed_at_utc
        )

    def validate_proposal(
        self,
        proposal: AutonomousTradeProposal,
        bundle: TraderInputBundle,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        if ib is None:
            return self.base.validate_proposal(proposal, bundle)
        return self.base.validate_proposal(proposal, bundle, ib=ib)

    def validate_position_action(
        self,
        action: AutonomousPositionAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        if ib is None:
            return self.base.validate_position_action(action, bundle, decision)
        return self.base.validate_position_action(action, bundle, decision, ib=ib)

    def validate_open_order_action(
        self,
        action: AutonomousOpenOrderAction,
        bundle: TraderInputBundle,
        decision: TraderDecision,
        *,
        ib: Any | None = None,
    ) -> ProposalValidation:
        if ib is None:
            return self.base.validate_open_order_action(action, bundle, decision)
        return self.base.validate_open_order_action(action, bundle, decision, ib=ib)

    def _connect(self, *, client_id: int | None = None) -> Any:
        return self.base._connect(client_id=client_id)

    def _proposal_contract(
        self, ib: Any, proposal: AutonomousTradeProposal
    ) -> Any:
        return self.base._proposal_contract(ib, proposal)

    def _resolve_open_position(
        self, ib: Any, action: AutonomousPositionAction
    ) -> Any:
        return self.base._resolve_open_position(ib, action)

    def live_contract_quote_evidence(
        self,
        ib: Any,
        contract: Any,
        *,
        wait_seconds: float = 2.0,
        max_age_seconds: float = 15.0,
    ) -> dict[str, Any]:
        return self.base.live_contract_quote_evidence(
            ib,
            contract,
            wait_seconds=wait_seconds,
            max_age_seconds=max_age_seconds,
        )

    def live_contract_session_evidence(
        self,
        ib: Any,
        contract: Any,
    ) -> dict[str, Any]:
        return self.base.live_contract_session_evidence(ib, contract)

    def manifest(self) -> list[dict[str, Any]]:
        manifest = list(self.base.manifest())
        manifest.extend(
            [
                {
                    "tool": ResearchTool.WORKSPACE.value,
                    "purpose": (
                        "Persistent research workspace you control. Artifacts persist across "
                        "cycles. Pass the operation as 'operation' (alias 'action'). "
                        "write_from_research_result stores the data of an earlier successful "
                        "research request of this cycle (source_request_id, optional RFC 6901 "
                        "json_pointer relative to that result's data, e.g. '/bars') as JSON."
                    ),
                    "valid_operations": list(WORKSPACE_OPERATIONS),
                    "arguments": {
                        operation: sorted(fields)
                        for operation, fields in _WORKSPACE_FIELDS.items()
                    },
                },
                {
                    "tool": ResearchTool.RUN_RESEARCH_SCRIPT.value,
                    "purpose": (
                        "Run a python research script you created in tools/ inside an isolated "
                        "sandbox without broker access, credentials or network. The working "
                        "directory is /workspace/experiments. input_request_ids lists earlier "
                        "successful research requests of this cycle; the host stores each "
                        "result's data as /workspace/datasets/research_inputs/<request_id>.json "
                        "and appends those absolute paths after 'arguments'."
                    ),
                    "arguments": list(RUN_SCRIPT_ARGUMENTS),
                    "argument_aliases": dict(_RUN_SCRIPT_ALIASES),
                },
                {
                    "tool": ResearchTool.QUANTCONNECT.value,
                    "purpose": (
                        "Typed access to the optional QuantConnect research laboratory through "
                        "an approved secure backend. Raw commands and LIVE are unavailable."
                    ),
                    "valid_operations": list(QUANTCONNECT_OPERATIONS),
                },
            ]
        )
        return manifest

    def execute(self, request: ResearchRequest, bundle: Any) -> ResearchResult:
        return self.execute_with_history(request, bundle, None)

    def execute_with_history(
        self,
        request: ResearchRequest,
        bundle: Any,
        history: list[dict[str, Any]] | None,
    ) -> ResearchResult:
        capability = request.tool in {
            ResearchTool.WORKSPACE,
            ResearchTool.RUN_RESEARCH_SCRIPT,
            ResearchTool.QUANTCONNECT,
        }
        if not capability:
            return self.base.execute(request, bundle)
        fingerprint = tolerant_sha256(
            {"tool": request.tool.value, "arguments": dict(request.arguments or {})}
        )
        failed_at = self._non_retryable_failures.get(fingerprint)
        if failed_at is not None and time.monotonic() - failed_at < NON_RETRYABLE_REPEAT_WINDOW_SECONDS:
            return self._result(
                request,
                tool_error(
                    request.tool,
                    str((request.arguments or {}).get("operation") or ""),
                    "IDENTICAL_NON_RETRYABLE_REQUEST_REPEATED",
                    retryable=False,
                    corrective_hint=(
                        "This exact request already failed with a non-retryable error; "
                        "change the arguments according to the earlier corrective_hint."
                    ),
                ),
                success=False,
            )
        if request.tool == ResearchTool.WORKSPACE:
            result = self._workspace(request, history)
        elif request.tool == ResearchTool.RUN_RESEARCH_SCRIPT:
            result = self._run_script(request, history)
        else:
            data = self.quantconnect.execute(dict(request.arguments or {}))
            data.setdefault("available", data.get("status") == "RUNTIME_AVAILABLE")
            success = data.get("status") in {"RUNTIME_AVAILABLE", "OPTIONAL_UNAVAILABLE"}
            if not success:
                data.setdefault("retryable", False)
            result = ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=success,
                data=data,
                error=None if success else str(data.get("reason") or "quantconnect_failed"),
            )
        if not result.success and result.data.get("retryable") is False:
            self._non_retryable_failures[fingerprint] = time.monotonic()
        return result

    # ------------------------------------------------------------------

    @staticmethod
    def _result(request: ResearchRequest, data: dict[str, Any], *, success: bool) -> ResearchResult:
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=success,
            data=data,
            error=None if success else str(data.get("error") or "operation_failed"),
        )

    def _workspace(
        self, request: ResearchRequest, history: list[dict[str, Any]] | None
    ) -> ResearchResult:
        tool = ResearchTool.WORKSPACE
        arguments, conflict = _canonical_arguments(
            dict(request.arguments or {}), {"action": "operation", "op": "operation"}, tool, ""
        )
        if conflict is not None:
            return self._result(request, conflict, success=False)
        raw_operation = str(arguments.pop("operation", "list") or "list").lower()
        operation = _WORKSPACE_OPERATION_ALIASES.get(raw_operation, raw_operation)
        if operation not in _WORKSPACE_FIELDS:
            return self._result(
                request,
                tool_error(
                    tool, raw_operation, "UNSUPPORTED_OPERATION", retryable=False,
                    corrective_hint="Use one of the valid_operations in the 'operation' field.",
                    valid_operations=list(WORKSPACE_OPERATIONS),
                ),
                success=False,
            )
        if operation == "list" and arguments.get("path") not in (None, ""):
            path = str(arguments["path"])
            if any(item["path"] == path for item in self.workspace.list_artifacts()):
                operation = "read"
        unsupported = sorted(
            set(arguments) - _WORKSPACE_FIELDS[operation] - _WORKSPACE_IGNORED_FIELDS
        )
        if unsupported:
            return self._result(
                request,
                tool_error(
                    tool, operation, "UNSUPPORTED_ARGUMENTS", retryable=False,
                    corrective_hint=(
                        f"'{operation}' accepts {sorted(_WORKSPACE_FIELDS[operation])}."
                    ),
                    unsupported_arguments=unsupported,
                ),
                success=False,
            )
        cycle_id = str(arguments.get("cycle_id", ""))
        try:
            if operation in {"read", "delete"} and not arguments.get("path"):
                artifact_id = str(arguments.get("artifact_id") or "")
                match = next(
                    (
                        item["path"]
                        for item in self.workspace.list_artifacts()
                        if item.get("artifact_id") == artifact_id
                    ),
                    None,
                )
                if match is None:
                    return self._result(
                        request,
                        tool_error(
                            tool, operation, "ARTIFACT_NOT_FOUND", retryable=False,
                            corrective_hint="Use WORKSPACE list to find an existing path or artifact_id.",
                        ),
                        success=False,
                    )
                arguments["path"] = match
            if operation == "list":
                data = {
                    "artifacts": self.workspace.list_artifacts(),
                    "summary": self.workspace.summary(),
                }
            elif operation == "read":
                data = dict(self.workspace.read_artifact(str(arguments["path"])))
            elif operation == "write":
                if "content" not in arguments or not arguments.get("path"):
                    return self._result(
                        request,
                        tool_error(
                            tool, operation, "MISSING_ARGUMENT", retryable=False,
                            corrective_hint="'write' requires 'path' and 'content'.",
                        ),
                        success=False,
                    )
                data = {
                    "artifact": self.workspace.write_artifact(
                        str(arguments["path"]), str(arguments["content"]), cycle_id=cycle_id
                    )
                }
            elif operation == "delete":
                data = dict(
                    self.workspace.delete_artifact(str(arguments["path"]), cycle_id=cycle_id)
                )
            else:
                source = str(arguments.get("source_request_id") or "")
                if not source or not arguments.get("path"):
                    return self._result(
                        request,
                        tool_error(
                            tool, operation, "MISSING_ARGUMENT", retryable=False,
                            corrective_hint="Provide 'path' and 'source_request_id'.",
                        ),
                        success=False,
                    )
                try:
                    document = _research_result_data(history, source)
                except LookupError:
                    return self._result(request, self._input_not_found(tool, operation, [source]), success=False)
                try:
                    pointer = str(arguments.get("json_pointer") or "")
                    if pointer == "/data" or pointer.startswith("/data/"):
                        document = {"data": document}
                    document = _json_pointer(document, pointer)
                except (KeyError, IndexError, ValueError, TypeError):
                    return self._result(
                        request,
                        tool_error(
                            tool, operation, "JSON_POINTER_NOT_FOUND", retryable=False,
                            corrective_hint="json_pointer is relative to the result data, e.g. '/bars'.",
                        ),
                        success=False,
                    )
                data = {
                    "artifact": self.workspace.write_artifact(
                        str(arguments["path"]),
                        json.dumps(document, sort_keys=True, default=str),
                        cycle_id=cycle_id,
                    )
                }
        except Exception as exc:
            return self._result(
                request,
                tool_error(
                    tool, operation, type(exc).__name__, retryable=False,
                    corrective_hint=str(exc)[:300],
                ),
                success=False,
            )
        return self._result(request, data, success=True)

    @staticmethod
    def _input_not_found(tool: ResearchTool, operation: str, missing: list[str]) -> dict[str, Any]:
        return tool_error(
            tool, operation, "INPUT_RESULT_NOT_FOUND", retryable=False,
            corrective_hint=(
                "Inputs must be request_ids of successful research requests made earlier "
                "in this same cycle; fetch the data first, then reference its request_id."
            ),
            missing_request_ids=missing,
        )

    def _run_script(
        self, request: ResearchRequest, history: list[dict[str, Any]] | None
    ) -> ResearchResult:
        tool = ResearchTool.RUN_RESEARCH_SCRIPT
        arguments, conflict = _canonical_arguments(
            dict(request.arguments or {}), _RUN_SCRIPT_ALIASES, tool, "RUN"
        )
        if conflict is not None:
            return self._result(request, conflict, success=False)
        unsupported = sorted(set(arguments) - set(RUN_SCRIPT_ARGUMENTS))
        if unsupported:
            return self._result(
                request,
                tool_error(
                    tool, "RUN", "UNSUPPORTED_ARGUMENTS", retryable=False,
                    corrective_hint=(
                        f"Supported fields: {list(RUN_SCRIPT_ARGUMENTS)}. Pass data with "
                        "input_request_ids (results of this cycle become JSON files appended "
                        "to the script arguments) or write it with WORKSPACE first; stdin and "
                        "inline payloads are not delivered to scripts."
                    ),
                    unsupported_arguments=unsupported,
                ),
                success=False,
            )
        if not arguments.get("path"):
            return self._result(
                request,
                tool_error(
                    tool, "RUN", "MISSING_ARGUMENT", retryable=False,
                    corrective_hint="Provide 'path' (alias 'script_path') of a script under tools/.",
                ),
                success=False,
            )
        raw_arguments = arguments.get("arguments") or []
        if isinstance(raw_arguments, str):
            raw_arguments = [raw_arguments]
        script_arguments = [str(item) for item in raw_arguments]
        raw_inputs = arguments.get("input_request_ids") or []
        if isinstance(raw_inputs, str):
            raw_inputs = [raw_inputs]
        cycle_id = str(arguments.get("cycle_id", ""))
        missing = []
        documents = []
        for request_id in (str(item) for item in raw_inputs):
            if not _SAFE_INPUT_ID.fullmatch(request_id):
                missing.append(request_id)
                continue
            try:
                documents.append((request_id, _research_result_data(history, request_id)))
            except LookupError:
                missing.append(request_id)
        if missing:
            return self._result(request, self._input_not_found(tool, "RUN", missing), success=False)
        try:
            for request_id, document in documents:
                relative = f"{RESEARCH_INPUT_DIRECTORY}/{request_id}.json"
                self.workspace.write_artifact(
                    relative, json.dumps(document, sort_keys=True, default=str), cycle_id=cycle_id
                )
                script_arguments.append(f"{SANDBOX_WORKSPACE_ROOT}/{relative}")
            run = self.workspace.run_script(
                str(arguments["path"]),
                cycle_id=cycle_id,
                timeout_seconds=float(arguments.get("timeout_seconds", 60)),
                arguments=script_arguments,
            )
        except Exception as exc:
            return self._result(
                request,
                tool_error(
                    tool, "RUN", type(exc).__name__, retryable=False,
                    corrective_hint=str(exc)[:300],
                ),
                success=False,
            )
        data = dict(run)
        success = run.get("status") == "COMPLETED"
        if not success:
            data.update(
                {
                    "tool": tool.value,
                    "operation": "RUN",
                    "error_type": str(run.get("failure_reason") or run.get("status") or "SCRIPT_FAILED"),
                    "retryable": True,
                    "corrective_hint": (
                        "Inspect stderr/returncode; scripts run with cwd /workspace/experiments "
                        "and receive input files as absolute /workspace/... paths."
                    ),
                    "error": "run_failed",
                }
            )
        return self._result(request, data, success=success)


def run_quantconnect_command(
    arguments: list[str], *, timeout_seconds: float = QUANTCONNECT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Compatibility tombstone for the removed raw-command boundary."""

    return {
        "success": False,
        "status": "UNAUTHORIZED_OPERATION",
        "error": "raw QuantConnect commands are not allowed; use typed operations",
    }
