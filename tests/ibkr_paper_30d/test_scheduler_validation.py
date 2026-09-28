from __future__ import annotations

from dataclasses import replace

import pytest

from ibkr_paper_30d.scheduler_validation import (
    RuntimeGateSnapshot,
    SchedulerExpectation,
    SchedulerTaskSnapshot,
    validate_scheduler_startup,
)

HEAD = "a" * 40
ROOT = r"C:\AI_VAULT_IBKR"
USER = r"CXASUS_TUF_F16\cesar"


def expectation(**updates) -> SchedulerExpectation:
    subject = SchedulerExpectation(
        task_name="CodexIBKRMarketDataGate",
        repo_root=ROOT,
        approved_head=HEAD,
        owner_user=USER,
        require_frozen=True,
    )
    return replace(subject, **updates)


def task(**updates) -> SchedulerTaskSnapshot:
    subject = SchedulerTaskSnapshot(
        task_name="CodexIBKRMarketDataGate",
        exists=True,
        enabled=False,
        execute="PowerShell.exe",
        arguments=(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            rf"{ROOT}\RUN_IBKR_MARKET_DATA_GATE.ps1",
            "-RepoRoot",
            ROOT,
            "-PythonExe",
            r"C:\Python311\python.exe",
            "-ApprovedHead",
            HEAD,
            "-Scheduled",
        ),
        user_id=USER,
        logon_type="Interactive",
        run_level="Highest",
        multiple_instances="IgnoreNew",
        working_directory=ROOT,
        restart_count=3,
        restart_interval_minutes=5,
        weekly_days=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
        weekly_start="09:35",
        logon_users=(USER,),
    )
    return replace(subject, **updates)


def runtime(**updates) -> RuntimeGateSnapshot:
    subject = RuntimeGateSnapshot(
        repo_root=ROOT,
        current_head=HEAD,
        gateway_available=True,
        kernel_verified=True,
        provenance_gate="PASS",
        lock_diagnostic="PASS",
    )
    return replace(subject, **updates)


def test_complete_frozen_scheduler_and_runtime_validation_passes():
    report = validate_scheduler_startup(task(), runtime(), expectation())

    assert report["status"] == "PASS"
    assert report["reason_codes"] == []
    assert report["scheduler_frozen"] is True
    assert report["mutations_performed"] == 0
    assert report["broker_write_calls"] == 0


@pytest.mark.parametrize(
    ("task_updates", "reason"),
    [
        ({"exists": False}, "SCHEDULER_TASK_MISSING"),
        ({"task_name": "OtherTask"}, "SCHEDULER_TASK_NAME_MISMATCH"),
        ({"enabled": True}, "SCHEDULER_TASK_NOT_FROZEN"),
        ({"execute": "cmd.exe"}, "ACTION_EXECUTABLE_MISMATCH"),
        ({"arguments": ("-Scheduled",)}, "ACTION_SCRIPT_MISMATCH"),
        ({"user_id": r"OTHER\owner"}, "PRINCIPAL_USER_MISMATCH"),
        ({"logon_type": "ServiceAccount"}, "INTERACTIVE_TOKEN_REQUIRED"),
        ({"run_level": "Limited"}, "HIGHEST_RUNLEVEL_REQUIRED"),
        ({"multiple_instances": "Parallel"}, "MULTIPLE_INSTANCES_NOT_IGNORE_NEW"),
        ({"working_directory": r"C:\Windows"}, "WORKING_DIRECTORY_MISMATCH"),
        ({"restart_count": 0}, "RETRY_POLICY_INSUFFICIENT"),
        ({"weekly_days": ("Friday",)}, "WEEKLY_TRIGGER_INVALID"),
        ({"logon_users": ()}, "LOGON_TRIGGER_MISSING"),
    ],
)
def test_scheduler_configuration_defects_fail_closed(task_updates, reason):
    report = validate_scheduler_startup(task(**task_updates), runtime(), expectation())
    assert report["status"] == "BLOCK"
    assert reason in report["reason_codes"]


@pytest.mark.parametrize(
    ("runtime_updates", "reason"),
    [
        ({"repo_root": r"C:\alternate"}, "REPOSITORY_ROOT_MISMATCH"),
        ({"current_head": "b" * 40}, "APPROVED_HEAD_MISMATCH"),
        ({"gateway_available": False}, "GATEWAY_UNAVAILABLE"),
        ({"kernel_verified": False}, "KERNEL_VERIFICATION_FAILED"),
        ({"provenance_gate": "BLOCK"}, "RUNTIME_PROVENANCE_FAILED"),
        ({"lock_diagnostic": "BLOCK"}, "LOCK_DIAGNOSTIC_FAILED"),
    ],
)
def test_runtime_defects_fail_closed(runtime_updates, reason):
    report = validate_scheduler_startup(
        task(), runtime(**runtime_updates), expectation()
    )
    assert report["status"] == "BLOCK"
    assert reason in report["reason_codes"]


def test_activation_validation_requires_enabled_task_instead_of_frozen_task():
    report = validate_scheduler_startup(
        task(enabled=True),
        runtime(),
        expectation(require_frozen=False),
    )
    assert report["status"] == "PASS"
    assert report["scheduler_frozen"] is False


def test_approved_head_and_repo_arguments_are_exact_not_prefix_matches():
    altered = list(task().arguments)
    altered[altered.index(HEAD)] = HEAD + "0"
    altered[altered.index(ROOT)] = ROOT + "_OTHER"

    report = validate_scheduler_startup(
        task(arguments=tuple(altered)), runtime(), expectation()
    )

    assert "ACTION_APPROVED_HEAD_MISMATCH" in report["reason_codes"]
    assert "ACTION_REPO_ROOT_MISMATCH" in report["reason_codes"]


def test_windows_scheduled_action_command_line_is_parsed_without_truncation():
    raw = (
        "-NoProfile -ExecutionPolicy Bypass -File "
        f'"{ROOT}\\RUN_IBKR_MARKET_DATA_GATE.ps1" '
        f'-RepoRoot "{ROOT}" -PythonExe "C:\\Program Files\\Python\\python.exe" '
        f"-ApprovedHead {HEAD} -Scheduled"
    )
    payload = {**task().__dict__, "arguments": raw}

    parsed = SchedulerTaskSnapshot.from_mapping(payload)
    report = validate_scheduler_startup(parsed, runtime(), expectation())

    assert report["status"] == "PASS"
