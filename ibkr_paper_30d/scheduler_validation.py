"""Read-only scheduler and startup validation for the PAPER service."""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import ntpath
import socket
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kernel_manifest import verify_kernel_manifest
from .runtime_provenance import (
    build_approved_runtime_material,
    verify_runtime_provenance,
)

SCHEMA = "SCHEDULER_STARTUP_VALIDATION_V1"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


@dataclass(frozen=True)
class SchedulerExpectation:
    task_name: str
    repo_root: str
    approved_head: str
    owner_user: str
    require_frozen: bool


@dataclass(frozen=True)
class SchedulerTaskSnapshot:
    task_name: str
    exists: bool
    enabled: bool
    execute: str
    arguments: tuple[str, ...]
    user_id: str
    logon_type: str
    run_level: str
    multiple_instances: str
    working_directory: str
    restart_count: int
    restart_interval_minutes: int
    weekly_days: tuple[str, ...]
    weekly_start: str
    logon_users: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SchedulerTaskSnapshot":
        raw_arguments = payload.get("arguments", ())
        if isinstance(raw_arguments, str):
            arguments = tuple(_split_windows_command_line(raw_arguments))
        else:
            arguments = tuple(str(item) for item in raw_arguments)
        return cls(
            task_name=str(payload.get("task_name", "")),
            exists=bool(payload.get("exists", False)),
            enabled=bool(payload.get("enabled", False)),
            execute=str(payload.get("execute", "")),
            arguments=arguments,
            user_id=str(payload.get("user_id", "")),
            logon_type=str(payload.get("logon_type", "")),
            run_level=str(payload.get("run_level", "")),
            multiple_instances=str(payload.get("multiple_instances", "")),
            working_directory=str(payload.get("working_directory", "")),
            restart_count=int(payload.get("restart_count", 0) or 0),
            restart_interval_minutes=int(
                payload.get("restart_interval_minutes", 0) or 0
            ),
            weekly_days=tuple(str(item) for item in payload.get("weekly_days", ())),
            weekly_start=str(payload.get("weekly_start", "")),
            logon_users=tuple(str(item) for item in payload.get("logon_users", ())),
        )


@dataclass(frozen=True)
class RuntimeGateSnapshot:
    repo_root: str
    current_head: str
    gateway_available: bool
    kernel_verified: bool
    provenance_gate: str
    lock_diagnostic: str


def _normalized_path(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(value.strip().strip('"')))


def _same_path(left: str, right: str) -> bool:
    return bool(left and right) and _normalized_path(left) == _normalized_path(right)


def _argument_value(arguments: Sequence[str], name: str) -> str | None:
    lowered = [item.casefold() for item in arguments]
    try:
        index = lowered.index(name.casefold())
    except ValueError:
        return None
    if index + 1 >= len(arguments):
        return None
    return arguments[index + 1]


def _has_flag(arguments: Sequence[str], name: str) -> bool:
    return name.casefold() in {item.casefold() for item in arguments}


def validate_scheduler_startup(
    task: SchedulerTaskSnapshot,
    runtime: RuntimeGateSnapshot,
    expected: SchedulerExpectation,
) -> dict[str, object]:
    reasons: list[str] = []
    if task.task_name.casefold() != expected.task_name.casefold():
        reasons.append("SCHEDULER_TASK_NAME_MISMATCH")
    if not task.exists:
        reasons.append("SCHEDULER_TASK_MISSING")
    if expected.require_frozen and task.enabled:
        reasons.append("SCHEDULER_TASK_NOT_FROZEN")
    if not expected.require_frozen and not task.enabled:
        reasons.append("SCHEDULER_TASK_NOT_ENABLED")

    if ntpath.basename(task.execute).casefold() != "powershell.exe":
        reasons.append("ACTION_EXECUTABLE_MISMATCH")
    expected_script = ntpath.join(expected.repo_root, "RUN_IBKR_MARKET_DATA_GATE.ps1")
    if not _same_path(_argument_value(task.arguments, "-File") or "", expected_script):
        reasons.append("ACTION_SCRIPT_MISMATCH")
    if not _same_path(
        _argument_value(task.arguments, "-RepoRoot") or "", expected.repo_root
    ):
        reasons.append("ACTION_REPO_ROOT_MISMATCH")
    if _argument_value(task.arguments, "-ApprovedHead") != expected.approved_head:
        reasons.append("ACTION_APPROVED_HEAD_MISMATCH")
    if _argument_value(task.arguments, "-PythonExe") is None:
        reasons.append("ACTION_PYTHON_EXE_MISSING")
    if not _has_flag(task.arguments, "-Scheduled"):
        reasons.append("ACTION_SCHEDULED_FLAG_MISSING")
    if _has_flag(task.arguments, "-InspectStatus"):
        reasons.append("ACTION_INSPECTION_MODE_FORBIDDEN")

    if task.user_id.casefold() != expected.owner_user.casefold():
        reasons.append("PRINCIPAL_USER_MISMATCH")
    if task.logon_type.casefold() != "interactive":
        reasons.append("INTERACTIVE_TOKEN_REQUIRED")
    if task.run_level.casefold() != "highest":
        reasons.append("HIGHEST_RUNLEVEL_REQUIRED")
    if task.multiple_instances.casefold() != "ignorenew":
        reasons.append("MULTIPLE_INSTANCES_NOT_IGNORE_NEW")
    if not _same_path(task.working_directory, expected.repo_root):
        reasons.append("WORKING_DIRECTORY_MISMATCH")
    if task.restart_count < 3 or task.restart_interval_minutes < 5:
        reasons.append("RETRY_POLICY_INSUFFICIENT")
    if {item.casefold() for item in task.weekly_days} != {
        item.casefold() for item in WEEKDAYS
    } or task.weekly_start != "09:35":
        reasons.append("WEEKLY_TRIGGER_INVALID")
    if expected.owner_user.casefold() not in {
        item.casefold() for item in task.logon_users
    }:
        reasons.append("LOGON_TRIGGER_MISSING")

    if not _same_path(runtime.repo_root, expected.repo_root):
        reasons.append("REPOSITORY_ROOT_MISMATCH")
    if runtime.current_head != expected.approved_head:
        reasons.append("APPROVED_HEAD_MISMATCH")
    if not runtime.gateway_available:
        reasons.append("GATEWAY_UNAVAILABLE")
    if not runtime.kernel_verified:
        reasons.append("KERNEL_VERIFICATION_FAILED")
    if runtime.provenance_gate != "PASS":
        reasons.append("RUNTIME_PROVENANCE_FAILED")
    if runtime.lock_diagnostic != "PASS":
        reasons.append("LOCK_DIAGNOSTIC_FAILED")

    return {
        "schema": SCHEMA,
        "status": "PASS" if not reasons else "BLOCK",
        "reason_codes": list(dict.fromkeys(reasons)),
        "approved_head": expected.approved_head,
        "observed_head": runtime.current_head,
        "scheduler_frozen": not task.enabled,
        "gateway_available": runtime.gateway_available,
        "kernel_verified": runtime.kernel_verified,
        "runtime_provenance_gate": runtime.provenance_gate,
        "lock_diagnostic": runtime.lock_diagnostic,
        "mutations_performed": 0,
        "broker_write_calls": 0,
    }


def _split_windows_command_line(command: str) -> list[str]:
    if not command.strip():
        return []
    if hasattr(ctypes, "windll"):
        argc = ctypes.c_int()
        parser = ctypes.windll.shell32.CommandLineToArgvW
        parser.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        parser.restype = ctypes.POINTER(ctypes.c_wchar_p)
        pointer = parser(command, ctypes.byref(argc))
        if not pointer:
            raise ValueError("scheduled action arguments are not parseable")
        try:
            return [pointer[index] for index in range(argc.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
    import shlex

    return [item.strip('"') for item in shlex.split(command, posix=False)]


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def _gateway_available() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 4002), timeout=0.75):
            return True
    except OSError:
        return False


def _lock_storage_diagnostic(root: Path) -> str:
    database = root / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    if not database.exists():
        return "PASS"
    try:
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check != ("ok",):
                return "BLOCK"
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='execution_lock_projection'"
            ).fetchone()
    except (OSError, sqlite3.Error, ValueError):
        return "BLOCK"
    return "PASS"


def collect_runtime_snapshot(root: Path, approved_head: str) -> RuntimeGateSnapshot:
    current_head = _git_head(root)
    try:
        manifest = json.loads(
            (root / "IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json").read_text(
                encoding="utf-8"
            )
        )
        kernel_verified = bool(verify_kernel_manifest(root, manifest)["verified"])
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ):
        kernel_verified = False
    try:
        material = build_approved_runtime_material(root, approved_head)
        provenance = verify_runtime_provenance(root, material)["gate_status"]
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        provenance = "BLOCK"
    return RuntimeGateSnapshot(
        repo_root=str(root.resolve()),
        current_head=current_head,
        gateway_available=_gateway_available(),
        kernel_verified=kernel_verified,
        provenance_gate=str(provenance),
        lock_diagnostic=_lock_storage_diagnostic(root),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--approved-head", required=True)
    parser.add_argument("--expected-repo-root", required=True)
    parser.add_argument("--expected-owner", required=True)
    parser.add_argument("--task-name", default="CodexIBKRMarketDataGate")
    parser.add_argument("--task-snapshot-base64", required=True)
    parser.add_argument("--require-frozen", action="store_true")
    args = parser.parse_args(argv)

    try:
        decoded = base64.b64decode(args.task_snapshot_base64, validate=True)
        payload = json.loads(decoded.decode("utf-8"))
        task = SchedulerTaskSnapshot.from_mapping(payload)
        runtime = collect_runtime_snapshot(args.repo_root, args.approved_head)
        report = validate_scheduler_startup(
            task,
            runtime,
            SchedulerExpectation(
                task_name=args.task_name,
                repo_root=args.expected_repo_root,
                approved_head=args.approved_head,
                owner_user=args.expected_owner,
                require_frozen=args.require_frozen,
            ),
        )
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        report = {
            "schema": SCHEMA,
            "status": "BLOCK",
            "reason_codes": ["SCHEDULER_SNAPSHOT_INVALID"],
            "error_type": type(exc).__name__,
            "approved_head": args.approved_head,
            "mutations_performed": 0,
            "broker_write_calls": 0,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
