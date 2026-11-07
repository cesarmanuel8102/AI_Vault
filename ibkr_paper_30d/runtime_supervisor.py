"""Reason-scoped runtime recovery, runtime supervision and auditor-receipt renewal.

These are availability controls for the PAPER runtime. They never place, modify
or cancel orders, never change sleeves, ledgers or the clock, and never relax
PAPER identity, reconciliation, lock or receipt predicates:

* ``automatic_kill_switch_recovery`` clears a kill switch only when it was set by
  the continuity runtime for a transient watchdog reason, never for an Owner
  kill, and only with a flat, fully reconciled PAPER account, a dead and stale
  writer, the approved HEAD and a passing auditor receipt.
* ``supervise_runtime`` restarts a dead runtime exclusively through the existing
  launcher task (single instance, lock-protected), leaves slow processes alone,
  and opens a circuit breaker after repeated restarts.
* ``renew_auditor_receipt_if_due`` refreshes the auditor receipt before it
  expires by running the unchanged independent Receipts stage.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import EventRepository, utc_now
from .types import new_uuid7

RUNTIME_ACTOR = "CONTINUITY_V3_RUNTIME"
RECOVERABLE_RUNTIME_REASONS = frozenset(
    {"CONTINUITY_WATCHDOG_FAILED", "CONTINUITY_WATCHDOG_SHUTDOWN_TIMEOUT"}
)
UNCERTAIN_STATE_ALERTS = frozenset(
    {"BROKER_STATE_UNCERTAIN", "MODEL_EXECUTION_RESULT_UNCERTAIN", "CANARY_STATE_UNCERTAIN"}
)
RECOVERY_COOLDOWN = timedelta(minutes=5)
LOCK_STALE_AFTER = timedelta(minutes=2)
HEARTBEAT_HEALTHY_WITHIN = timedelta(minutes=3)
MAX_AUTOMATIC_RECOVERIES_PER_DAY = 3
MAX_SUPERVISOR_RESTARTS_PER_HOUR = 3
RECEIPT_RENEW_AFTER = timedelta(hours=20)
LAUNCHER_TASK_NAME = "CodexIBKRMultiUniversePilot"
RUNTIME_PROCESS_MARKER = "ibkr_paper_30d.day1_launch"
_TRIGGER_REASON = re.compile(r"^critical runtime event (continuity-v3-[0-9a-f]{32})$")
_RUNTIME_REASON = re.compile(r"runtime_reason_code=([A-Z][A-Z0-9_]+)")

AlertSink = Callable[[str, dict[str, Any]], None]


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _db_path(repo_root: Path) -> Path:
    return Path(repo_root) / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"


def _append_state_event(
    db: Database, event_type: str, payload: Mapping[str, Any], *, now: datetime
) -> None:
    EventRepository(db).append(
        event_type,
        {
            "schema": "RUNTIME_SUPERVISION_EVENT_V1",
            "event_type": event_type,
            "observed_at_utc": _iso(now),
            **payload,
        },
    )


def database_alert_sink(db_path: Path) -> AlertSink:
    """Durable alert rows plus a best-effort Windows Event Log entry for the Owner."""

    def sink(event_type: str, payload: dict[str, Any]) -> None:
        body = {
            "schema": "RUNTIME_SUPERVISION_ALERT_V1",
            "event_type": event_type,
            "owner_action_required": event_type != "AUTOMATIC_RUNTIME_RECOVERY_PERFORMED",
            "created_at_utc": utc_now(),
            **payload,
        }
        with Database.open(db_path) as db:
            db.execute(
                "INSERT INTO alerts(alert_id,event_type,payload_json,payload_sha256,created_at_utc) "
                "VALUES(?,?,?,?,?)",
                (str(new_uuid7()), event_type, canonical_bytes(body).decode("utf-8"),
                 sha256_json(body), utc_now()),
            )
        try:
            import win32evtlog
            import win32evtlogutil

            win32evtlogutil.ReportEvent(
                "CodexIBKRPaper30D",
                int(sha256_json(body)[:7], 16),
                eventType=win32evtlog.EVENTLOG_WARNING_TYPE,
                strings=[event_type, json.dumps(payload, sort_keys=True, default=str)[:2000]],
            )
        except Exception:
            pass

    return sink


# --- state readers -----------------------------------------------------------------------


def classify_kill_switch(db: Database) -> dict[str, Any]:
    row = db.execute(
        "SELECT event_id,state,payload_json FROM kill_switch_events ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {"state": "KILL_SWITCH_TRIGGERED", "recoverable": False,
                "reason_codes": ["KILL_SWITCH_HISTORY_MISSING"]}
    state = str(row[1])
    if state != "KILL_SWITCH_TRIGGERED":
        return {"state": state, "recoverable": False, "reason_codes": []}
    payload = json.loads(str(row[2]))
    created = db.execute(
        "SELECT created_at_utc FROM kill_switch_events WHERE event_id=?", (str(row[0]),)
    ).fetchone()
    result: dict[str, Any] = {
        "state": state,
        "trigger_event_id": str(row[0]),
        "actor": str(payload.get("actor") or ""),
        "triggered_at_utc": str(created[0]) if created else None,
        "recoverable": False,
        "runtime_reason_codes": [],
        "reason_codes": [],
    }
    match = _TRIGGER_REASON.fullmatch(str(payload.get("reason") or ""))
    if result["actor"] != RUNTIME_ACTOR or match is None:
        result["reason_codes"] = ["KILL_SWITCH_NOT_RUNTIME_SCOPED"]
        return result
    correlation = match.group(1)
    alert = db.execute(
        "SELECT event_type,payload_json FROM alerts WHERE alert_id=?", (f"alert-{correlation}",)
    ).fetchone()
    codes: set[str] = set()
    if alert is not None:
        found = _RUNTIME_REASON.search(str(alert[1]))
        codes.add(found.group(1) if found else str(alert[0]))
    result["correlation_id"] = correlation
    result["runtime_reason_codes"] = sorted(codes)
    if not codes:
        result["reason_codes"] = ["RUNTIME_REASON_UNKNOWN"]
    elif not codes <= RECOVERABLE_RUNTIME_REASONS:
        result["reason_codes"] = ["RUNTIME_REASON_NOT_RECOVERABLE"]
    else:
        result["recoverable"] = True
    return result


def read_execution_lock(db: Database) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT payload_json FROM experiment_state WHERE experiment_id='EXECUTION_LOCK_V1'"
    ).fetchone()
    return None if row is None else json.loads(str(row[0]))


def approved_runtime_head(db: Database) -> str | None:
    row = db.execute(
        "SELECT payload_json FROM successor_transition_events "
        "WHERE event_type='RUNTIME_RELEASE_AUTHORIZED' ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    head = json.loads(str(row[0])).get("approved_git_head")
    return str(head).lower() if head else None


def _recorded_flat(db: Database) -> bool | None:
    """Latest broker reconciliation per sleeve: True if flat, None if unknown."""

    flat = True
    for sleeve in ("REGULAR_SLEEVE", "CONTINUOUS_SLEEVE"):
        row = db.execute(
            "SELECT payload_json FROM sleeve_ledger_events WHERE sleeve=? "
            "AND event_type='BROKER_STATE_RECONCILED' ORDER BY sequence DESC LIMIT 1",
            (sleeve,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row[0]))
        if payload.get("positions") or int(payload.get("open_order_count") or 0):
            flat = False
    return flat


def _events_since(db: Database, event_type: str, since: datetime, *, action: str | None = None) -> int:
    count = 0
    for (raw,) in db.execute(
        "SELECT payload_json FROM state_events WHERE event_type=?", (event_type,)
    ).fetchall():
        payload = json.loads(str(raw))
        observed = _parse(payload.get("observed_at_utc"))
        if observed is None or observed < since:
            continue
        if action is not None and payload.get("action") not in (
            {action} if isinstance(action, str) else set(action)
        ):
            continue
        count += 1
    return count


def _uncertain_since(db: Database, since: str | None) -> bool:
    if since is None:
        return True
    marks = ",".join("?" for _ in UNCERTAIN_STATE_ALERTS)
    row = db.execute(
        f"SELECT 1 FROM alerts WHERE event_type IN ({marks}) AND created_at_utc>=? LIMIT 1",
        (*sorted(UNCERTAIN_STATE_ALERTS), since),
    ).fetchone()
    return row is not None


def _lock_reasons(lock: Mapping[str, Any] | None, now: datetime, pid_alive: Callable[[int], bool]) -> list[str]:
    if lock is None:
        return []
    reasons: list[str] = []
    pid = lock.get("pid")
    if lock.get("state") == "ACTIVE" and isinstance(pid, int) and not isinstance(pid, bool) and pid_alive(pid):
        reasons.append("WRITER_STILL_ACTIVE")
    heartbeat = _parse(lock.get("heartbeat_at_utc"))
    if heartbeat is not None and now - heartbeat < LOCK_STALE_AFTER:
        reasons.append("EXECUTION_LOCK_NOT_STALE")
    return reasons


# --- reason-scoped kill switch recovery ---------------------------------------------------


def automatic_kill_switch_recovery(
    *,
    repo_root: Path,
    now_utc: Callable[[], datetime],
    pid_alive: Callable[[int], bool],
    auditor_gate: Callable[[], Mapping[str, Any]],
    head_reader: Callable[[Path], str],
    evidence_collector: Callable[..., Any],
    current_sid: Callable[[], str],
    token_elevated: Callable[[], bool],
    alert_sink: AlertSink,
) -> dict[str, Any]:
    from .experiment_control import ExperimentControlError
    from .kill_switch_recovery import KillSwitchRecoveryError, recover_kill_switch

    root = Path(repo_root)
    now = now_utc().astimezone(timezone.utc)
    with Database.open(_db_path(root)) as db:
        classification = classify_kill_switch(db)
        if classification["state"] != "KILL_SWITCH_TRIGGERED":
            return {"status": "NOT_REQUIRED", "classification": classification}
        reasons = list(classification["reason_codes"])
        triggered = _parse(classification.get("triggered_at_utc"))
        if triggered is None or now - triggered < RECOVERY_COOLDOWN:
            reasons.append("RECOVERY_COOLDOWN_ACTIVE")
        if _events_since(db, "AUTOMATIC_KILL_SWITCH_RECOVERY", now - timedelta(days=1)) >= MAX_AUTOMATIC_RECOVERIES_PER_DAY:
            reasons.append("AUTOMATIC_RECOVERY_BUDGET_EXHAUSTED")
        if _uncertain_since(db, classification.get("triggered_at_utc")):
            reasons.append("UNCERTAIN_STATE_PRESENT")
        reasons.extend(_lock_reasons(read_execution_lock(db), now, pid_alive))
        approved = approved_runtime_head(db)
    current = head_reader(root).strip().lower()
    if approved is None or current != approved:
        reasons.append("APPROVED_HEAD_MISMATCH")
    if auditor_gate().get("gate_status") != "PASS":
        reasons.append("AUDITOR_RECEIPT_NOT_PASS")
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        _blocked(root, classification, reasons, now, alert_sink)
        return {"status": "BLOCKED", "reason_codes": reasons, "classification": classification}
    runtime_reason = classification["runtime_reason_codes"][0]
    try:
        report = recover_kill_switch(
            repo_root=root,
            approved_head=approved,
            recovery_reason_code=f"AUTOMATIC_{runtime_reason}",
            evidence_collector=evidence_collector,
            head_reader=head_reader,
            current_sid=current_sid,
            token_elevated=token_elevated,
            now_utc=lambda: now,
            pid_alive=pid_alive,
            require_flat=True,
        )
    except (ExperimentControlError, KillSwitchRecoveryError) as exc:
        reasons = [str(exc)]
        _blocked(root, classification, reasons, now, alert_sink)
        return {"status": "BLOCKED", "reason_codes": reasons, "classification": classification}
    receipt_sha256 = sha256_json(report["receipt"])
    with Database.open(_db_path(root)) as db:
        _append_state_event(
            db,
            "AUTOMATIC_KILL_SWITCH_RECOVERY",
            {
                "trigger_event_id": classification["trigger_event_id"],
                "runtime_reason_codes": classification["runtime_reason_codes"],
                "recovery_event_id": report["recovery_event_id"],
                "recovery_receipt_sha256": receipt_sha256,
                "approved_head": approved,
            },
            now=now,
        )
    alert_sink(
        "AUTOMATIC_RUNTIME_RECOVERY_PERFORMED",
        {"trigger_event_id": classification["trigger_event_id"],
         "runtime_reason_codes": classification["runtime_reason_codes"],
         "recovery_receipt_sha256": receipt_sha256},
    )
    return {"status": "RECOVERED", "recovery_receipt_sha256": receipt_sha256,
            "classification": classification}


def _blocked(root: Path, classification: Mapping[str, Any], reasons: list[str], now: datetime,
             alert_sink: AlertSink) -> None:
    with Database.open(_db_path(root)) as db:
        already = _events_since(db, "AUTOMATIC_KILL_SWITCH_RECOVERY_BLOCKED", now - timedelta(hours=1))
        _append_state_event(
            db, "AUTOMATIC_KILL_SWITCH_RECOVERY_BLOCKED",
            {"trigger_event_id": classification.get("trigger_event_id"), "reason_codes": reasons},
            now=now,
        )
    transient = set(reasons) <= {"RECOVERY_COOLDOWN_ACTIVE", "EXECUTION_LOCK_NOT_STALE"}
    if not already and not transient:
        alert_sink("OWNER_ACTION_REQUIRED",
                   {"trigger_event_id": classification.get("trigger_event_id"), "reason_codes": reasons})


# --- supervisor ---------------------------------------------------------------------------


def supervise_runtime(
    *,
    repo_root: Path,
    now_utc: Callable[[], datetime],
    pid_alive: Callable[[int], bool],
    process_cmdline: Callable[[int], str],
    task_state: Callable[[], str],
    start_task: Callable[[], None],
    terminate_process: Callable[[int], None],
    alert_sink: AlertSink,
) -> dict[str, Any]:
    now = now_utc().astimezone(timezone.utc)
    root = Path(repo_root)
    with Database.open(_db_path(root)) as db:
        lock = read_execution_lock(db) or {}
        classification = classify_kill_switch(db)
        recorded_flat = _recorded_flat(db)
        restarts = _events_since(
            db, "RUNTIME_SUPERVISOR_ACTION", now - timedelta(hours=1),
            action=("RELAUNCH_REQUESTED", "STOP_IDLE_RUNTIME_REQUESTED"),
        )
        breaker_alerted = _events_since(
            db, "RUNTIME_SUPERVISOR_ACTION", now - timedelta(hours=1), action="CIRCUIT_BREAKER_OPEN"
        )
        stale_alerted = _events_since(
            db, "RUNTIME_SUPERVISOR_ACTION", now - timedelta(hours=1), action="SLOW_OR_HUNG_ALERTED"
        )
        owner_alerted = _events_since(
            db, "RUNTIME_SUPERVISOR_ACTION", now - timedelta(hours=1), action="OWNER_ACTION_REQUIRED"
        )
        clock_row = db.execute(
            "SELECT payload_json FROM state_events WHERE event_type='EXPERIMENT_MEASUREMENT_CLOCK_STARTED' "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
    clock_end = None if clock_row is None else _parse(json.loads(str(clock_row[0])).get("end_utc"))
    pid = lock.get("pid")
    valid_pid = isinstance(pid, int) and not isinstance(pid, bool)
    alive = bool(lock.get("state") == "ACTIVE" and valid_pid and pid_alive(pid))
    heartbeat = _parse(lock.get("heartbeat_at_utc"))
    heartbeat_age = None if heartbeat is None else (now - heartbeat).total_seconds()
    killed = classification["state"] == "KILL_SWITCH_TRIGGERED"
    detail: dict[str, Any] = {"pid": pid if valid_pid else None, "heartbeat_age_seconds": heartbeat_age,
                              "kill_switch": classification["state"]}

    def record(action: str, *, alert: str | None = None, **extra: Any) -> dict[str, Any]:
        payload = {"action": action, **detail, **extra}
        if action != "HEALTHY":
            with Database.open(_db_path(root)) as db:
                _append_state_event(db, "RUNTIME_SUPERVISOR_ACTION", payload, now=now)
        if alert is not None:
            alert_sink(alert, payload)
        return payload

    if alive:
        if heartbeat_age is not None and heartbeat_age <= HEARTBEAT_HEALTHY_WITHIN.total_seconds():
            if not killed:
                return record("HEALTHY")
            if not classification["recoverable"]:
                return record("OWNER_ACTION_REQUIRED",
                              alert=None if owner_alerted else "OWNER_ACTION_REQUIRED",
                              reason_codes=classification["reason_codes"])
            triggered = _parse(classification.get("triggered_at_utc"))
            if triggered is None or now - triggered < RECOVERY_COOLDOWN:
                return record("KILL_SWITCH_COOLDOWN")
            if recorded_flat is not True:
                return record("KILL_SWITCH_EXPOSURE_PRESENT",
                              alert=None if owner_alerted else "OWNER_ACTION_REQUIRED")
            if restarts >= MAX_SUPERVISOR_RESTARTS_PER_HOUR:
                return record("CIRCUIT_BREAKER_OPEN",
                              alert=None if breaker_alerted else "RUNTIME_SUPERVISOR_CIRCUIT_BREAKER")
            if RUNTIME_PROCESS_MARKER not in (process_cmdline(pid) or ""):
                return record("PROCESS_IDENTITY_UNVERIFIED", alert="OWNER_ACTION_REQUIRED")
            terminate_process(pid)
            return record("STOP_IDLE_RUNTIME_REQUESTED")
        return record("SLOW_OR_HUNG_ALERTED",
                      alert=None if stale_alerted else "RUNTIME_HEARTBEAT_STALE")
    if killed and not classification["recoverable"]:
        return record("OWNER_ACTION_REQUIRED",
                      alert=None if owner_alerted else "OWNER_ACTION_REQUIRED",
                      reason_codes=classification["reason_codes"])
    if clock_end is not None and now >= clock_end:
        return record("EXPERIMENT_CLOCK_ENDED")
    if str(task_state()).lower() == "running":
        return record("LAUNCHER_ALREADY_RUNNING")
    if restarts >= MAX_SUPERVISOR_RESTARTS_PER_HOUR:
        return record("CIRCUIT_BREAKER_OPEN",
                      alert=None if breaker_alerted else "RUNTIME_SUPERVISOR_CIRCUIT_BREAKER")
    start_task()
    return record("RELAUNCH_REQUESTED")


# --- auditor receipt renewal --------------------------------------------------------------


def renew_auditor_receipt_if_due(
    *,
    repo_root: Path,
    now_utc: Callable[[], datetime],
    runtime_alive: Callable[[], bool],
    head_reader: Callable[[Path], str],
    run_receipts_stage: Callable[[str], int],
    auditor_gate: Callable[[], Mapping[str, Any]],
    alert_sink: AlertSink,
    launch_attempt_id_reader: Callable[[], str | None],
) -> dict[str, Any]:
    root = Path(repo_root)
    now = now_utc().astimezone(timezone.utc)
    receipt_path = root / "state" / "ibkr_paper_30d" / "reports" / "auditor_gate_v2_receipt.json"
    try:
        completed = _parse(json.loads(receipt_path.read_text(encoding="utf-8")).get("completed_at_utc"))
    except (OSError, json.JSONDecodeError):
        completed = None
    age = None if completed is None else now - completed
    if age is not None and age < RECEIPT_RENEW_AFTER:
        return {"status": "NOT_DUE", "receipt_age_hours": round(age.total_seconds() / 3600, 2)}
    if not runtime_alive():
        return {"status": "LAUNCHER_RENEWS"}
    with Database.open(_db_path(root)) as db:
        approved = approved_runtime_head(db)

    def outcome(status: str, **extra: Any) -> dict[str, Any]:
        payload = {"status": status, "approved_head": approved, **extra}
        with Database.open(_db_path(root)) as db:
            _append_state_event(db, "AUDITOR_RECEIPT_RENEWAL", payload, now=now)
        if status != "RENEWED":
            alert_sink("AUDITOR_RECEIPT_RENEWAL_FAILED", payload)
        return payload

    if approved is None or head_reader(root).strip().lower() != approved:
        return outcome("BLOCKED", reason_codes=["APPROVED_HEAD_MISMATCH"])
    attempt = launch_attempt_id_reader()
    if not attempt:
        return outcome("BLOCKED", reason_codes=["LAUNCH_ATTEMPT_ID_UNAVAILABLE"])
    code = run_receipts_stage(attempt)
    try:
        refreshed = _parse(json.loads(receipt_path.read_text(encoding="utf-8")).get("completed_at_utc"))
    except (OSError, json.JSONDecodeError):
        refreshed = None
    gate = dict(auditor_gate())
    if code != 0 or refreshed is None or (completed is not None and refreshed <= completed) or gate.get("gate_status") != "PASS":
        return outcome("FAILED", exit_code=code, gate=gate)
    return outcome("RENEWED", completed_at_utc=_iso(refreshed))


# --- host adapters and CLI ----------------------------------------------------------------


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _task_state(name: str) -> str:
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"(Get-ScheduledTask -TaskName '{name}').State"],
        capture_output=True, text=True, timeout=60, check=False,
    )
    return completed.stdout.strip() or "Unknown"


def _start_task(name: str) -> None:
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"Start-ScheduledTask -TaskName '{name}'"],
        capture_output=True, text=True, timeout=60, check=True,
    )


def _process_cmdline(pid: int) -> str:
    import psutil

    try:
        return " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return ""


def _terminate(pid: int) -> None:
    import psutil

    process = psutil.Process(pid)
    if RUNTIME_PROCESS_MARKER not in " ".join(process.cmdline()):
        raise RuntimeError("PROCESS_IDENTITY_UNVERIFIED")
    for child in process.children(recursive=True):
        child.terminate()
    process.terminate()
    process.wait(timeout=60)


def _auditor_gate(root: Path) -> Callable[[], Mapping[str, Any]]:
    from .runtime_integrity import (
        DEFAULT_AUDITOR_RECEIPT,
        DEFAULT_READONLY_RECEIPT,
        RuntimeAuditorGate,
    )

    gate = RuntimeAuditorGate(
        readonly_receipt_path=root / DEFAULT_READONLY_RECEIPT,
        auditor_receipt_path=root / DEFAULT_AUDITOR_RECEIPT,
    )
    return gate.evaluate


def _latest_launch_attempt(root: Path) -> str | None:
    with Database.open(_db_path(root)) as db:
        row = db.execute(
            "SELECT payload_json FROM state_events WHERE event_type='AUTONOMOUS_SERVICE_STARTED' "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
    return None if row is None else json.loads(str(row[0])).get("launch_attempt_id") or None


def main(argv: Sequence[str] | None = None) -> int:
    import psutil

    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.runtime_supervisor")
    parser.add_argument("command", choices=("recover-kill-switch", "supervise", "renew-auditor-receipt"))
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--task-name", default=LAUNCHER_TASK_NAME)
    parser.add_argument("--authority-path", type=Path, help="multi-universe launch authority JSON")
    parser.add_argument("--python-exe", default="python")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    sink = database_alert_sink(_db_path(root))
    now = lambda: datetime.now(timezone.utc)  # noqa: E731
    if args.command == "recover-kill-switch":
        from .day1_launch import current_process_sid
        from .ibkr_readonly_session import IBKRReadOnlySessionCollector
        from .kill_switch_recovery import _is_elevated

        result = automatic_kill_switch_recovery(
            repo_root=root, now_utc=now, pid_alive=psutil.pid_exists,
            auditor_gate=_auditor_gate(root), head_reader=_git_head,
            evidence_collector=IBKRReadOnlySessionCollector().collect,
            current_sid=current_process_sid, token_elevated=_is_elevated, alert_sink=sink,
        )
        code = 0 if result["status"] in {"NOT_REQUIRED", "RECOVERED"} else 2
    elif args.command == "supervise":
        result = supervise_runtime(
            repo_root=root, now_utc=now, pid_alive=psutil.pid_exists,
            process_cmdline=_process_cmdline, task_state=lambda: _task_state(args.task_name),
            start_task=lambda: _start_task(args.task_name), terminate_process=_terminate,
            alert_sink=sink,
        )
        code = 0
    else:
        if args.authority_path is None:
            parser.error("--authority-path is required for renew-auditor-receipt")
        authority = json.loads(args.authority_path.read_text(encoding="utf-8"))

        def runtime_alive() -> bool:
            with Database.open(_db_path(root)) as db:
                lock = read_execution_lock(db) or {}
            pid = lock.get("pid")
            return bool(lock.get("state") == "ACTIVE" and isinstance(pid, int) and psutil.pid_exists(pid))

        def run_stage(attempt: str) -> int:
            return subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(root / "FINALIZE_IBKR_PREREQUISITES.ps1"),
                    "-RepoRoot", str(root), "-PythonExe", args.python_exe,
                    "-Stage", "Receipts", "-ConfirmStage", "-SkipTaskRegistration",
                    "-LaunchAttemptId", attempt,
                    "-TargetSuccessorEpochId", str(authority["successor_epoch_id"]),
                    "-TargetSuccessorDefinitionSha256", str(authority["successor_definition_sha256"]).lower(),
                ],
                cwd=str(root), timeout=900, check=False,
            ).returncode

        result = renew_auditor_receipt_if_due(
            repo_root=root, now_utc=now, runtime_alive=runtime_alive, head_reader=_git_head,
            run_receipts_stage=run_stage, auditor_gate=_auditor_gate(root), alert_sink=sink,
            launch_attempt_id_reader=lambda: _latest_launch_attempt(root),
        )
        code = 0 if result["status"] in {"NOT_DUE", "LAUNCHER_RENEWS", "RENEWED"} else 2
    print(json.dumps(result, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
