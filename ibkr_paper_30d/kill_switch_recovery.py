from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import psutil

from .canonical import canonical_bytes, sha256_json
from .experiment_control import (
    ExperimentClockStore,
    ExperimentControlError,
    KillSwitchStore,
)
from .ibkr_readonly import expected_identity_hash
from .ibkr_readonly_session import IBKRReadOnlySessionCollector, ReadOnlyMessageGuard
from .persistence import Database
from .successor_epoch import current_epoch_authority_bindings


class KillSwitchRecoveryError(RuntimeError):
    pass


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_expected_account_hash(path: Path) -> str:
    try:
        payload = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_IDENTITY_INVALID") from exc
    value = payload.get("account_sha256") if isinstance(payload, dict) else None
    if not isinstance(value, str) or len(value) != 64:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_IDENTITY_INVALID")
    return value


def _redact_accounts(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _redact_accounts(item)
            for key, item in value.items()
            if str(key).lower() not in {"account", "accountid", "account_id", "acctnumber"}
        }
    if isinstance(value, (list, tuple)):
        return [_redact_accounts(item) for item in value]
    return value


def _assert_no_active_execution_authority(
    db: Database, *, pid_alive: Callable[[int], bool]
) -> None:
    row = db.execute(
        "SELECT payload_json FROM experiment_state WHERE experiment_id=?",
        ("ibkr-paper-30d",),
    ).fetchone()
    if row is None:
        return
    try:
        payload = json.loads(str(row[0]))
    except json.JSONDecodeError as exc:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_LOCK_AMBIGUOUS") from exc
    if not isinstance(payload, dict):
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_LOCK_AMBIGUOUS")
    if payload.get("order_authority") is not False:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_ORDER_AUTHORITY_NOT_CLEAR")
    if payload.get("state") == "ACTIVE":
        pid = payload.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int):
            raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_LOCK_AMBIGUOUS")
        if pid_alive(pid):
            raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_PROCESS_STILL_ACTIVE")


def _latest_authority(db: Database) -> tuple[str, str]:
    successor = current_epoch_authority_bindings(db)
    if successor is not None:
        return (
            successor["authorization_event_id"],
            successor["clock_event_sha256"],
        )
    authorization = db.execute(
        "SELECT event_id FROM experiment_authorization_events "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    clock = ExperimentClockStore(db).load()
    if authorization is None or clock is None:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_AUTHORITY_MISSING")
    return str(authorization[0]), clock.event_sha256


def recover_kill_switch(
    *,
    repo_root: Path,
    approved_head: str,
    recovery_reason_code: str,
    evidence_collector: Callable[..., Any],
    head_reader: Callable[[Path], str],
    current_sid: Callable[[], str],
    token_elevated: Callable[[], bool],
    now_utc: Callable[[], datetime],
    pid_alive: Callable[[int], bool] = psutil.pid_exists,
) -> dict[str, object]:
    root = repo_root.resolve()
    if head_reader(root).strip().lower() != approved_head.lower():
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_HEAD_MISMATCH")
    if not token_elevated():
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_REQUIRES_ELEVATION")
    owner_sid = current_sid()
    if not owner_sid:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_OWNER_INVALID")
    expected_account_hash = _read_expected_account_hash(
        root / "Secrets" / "expected_paper_account_identity_v1.json"
    )

    evidence = evidence_collector(
        host="127.0.0.1",
        port=4002,
        client_id=19739,
        symbols=(),
    )
    if not evidence.connected or not evidence.authenticated or not evidence.heartbeat_ok:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_BROKER_NOT_READY")
    if len(evidence.managed_accounts) != 1:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_ACCOUNT_MISMATCH")
    account = str(evidence.managed_accounts[0]).strip().upper()
    if not account.startswith("DU") or expected_identity_hash(account) != expected_account_hash:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_ACCOUNT_MISMATCH")
    required_queries = {
        "managed_accounts",
        "positions",
        "open_orders",
        "executions",
        "current_time",
    }
    if any(evidence.query_completeness.get(name) is not True for name in required_queries):
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_RECONCILIATION_INCOMPLETE")
    if evidence.open_orders:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_OPEN_ORDERS_PRESENT")
    if any(
        message_id not in ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS
        for message_id in evidence.outbound_message_ids
    ):
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_BROKER_WRITE_DETECTED")
    if not evidence.server_timestamp_utc:
        raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_BROKER_TIME_INVALID")

    collected_at = now_utc().astimezone(timezone.utc)
    broker_evidence = {
        "schema": "KILL_SWITCH_RECOVERY_BROKER_EVIDENCE_V1",
        "environment": "PAPER",
        "host": "127.0.0.1",
        "port": 4002,
        "account_identity_sha256": expected_account_hash,
        "server_timestamp_utc": evidence.server_timestamp_utc,
        "collected_at_utc": _utc(collected_at),
        "query_completeness": {
            name: bool(evidence.query_completeness.get(name))
            for name in sorted(required_queries)
        },
        "positions_sha256": sha256_json(_redact_accounts(evidence.positions)),
        "open_orders_sha256": sha256_json(_redact_accounts(evidence.open_orders)),
        "executions_sha256": sha256_json(_redact_accounts(evidence.executions)),
        "positions_count": len(evidence.positions),
        "open_orders_count": len(evidence.open_orders),
        "executions_count": len(evidence.executions),
        "outbound_message_ids": list(evidence.outbound_message_ids),
        "broker_write_count": 0,
    }

    db_path = root / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    report_path = (
        root
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "kill_switch_recovery_v1.json"
    )
    with Database.open(db_path) as db:
        _assert_no_active_execution_authority(db, pid_alive=pid_alive)
        authorization_event_id, clock_event_sha256 = _latest_authority(db)
        trigger = db.execute(
            "SELECT event_id,payload_sha256,state FROM kill_switch_events "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if trigger is None or str(trigger[2]) != "KILL_SWITCH_TRIGGERED":
            raise KillSwitchRecoveryError("KILL_SWITCH_RECOVERY_TRIGGER_REQUIRED")
        receipt = {
            "schema": "KILL_SWITCH_RECOVERY_RECEIPT_V1",
            "trigger_event_id": str(trigger[0]),
            "trigger_payload_sha256": str(trigger[1]),
            "approved_head": approved_head.lower(),
            "owner_sid": owner_sid,
            "account_identity_sha256": expected_account_hash,
            "authorization_event_id": authorization_event_id,
            "clock_event_sha256": clock_event_sha256,
            "broker_evidence_sha256": sha256_json(broker_evidence),
            "broker_server_time_utc": evidence.server_timestamp_utc,
            "collected_at_utc": _utc(collected_at),
            "expires_at_utc": _utc(collected_at + timedelta(seconds=30)),
            "positions_count": len(evidence.positions),
            "open_orders_count": len(evidence.open_orders),
            "executions_count": len(evidence.executions),
            "broker_write_count": 0,
            "query_completeness": broker_evidence["query_completeness"],
            "recovery_reason_code": recovery_reason_code,
        }
        event_id = KillSwitchStore(db).recover(
            receipt,
            now_utc=collected_at,
            expected_owner_sid=owner_sid,
            expected_account_identity_sha256=expected_account_hash,
            expected_approved_head=approved_head.lower(),
            expected_authorization_event_id=authorization_event_id,
            expected_clock_event_sha256=clock_event_sha256,
            precommit_verifier=lambda current_db: _assert_no_active_execution_authority(
                current_db, pid_alive=pid_alive
            ),
        )
    report = {
        "schema": "KILL_SWITCH_RECOVERY_REPORT_V1",
        "status": "PASS",
        "recovery_event_id": event_id,
        "receipt": receipt,
        "broker_evidence": broker_evidence,
    }
    _atomic_json(report_path, report)
    return report


def _git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def _is_elevated() -> bool:
    return os.name != "nt" or bool(ctypes.windll.shell32.IsUserAnAdmin())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.kill_switch_recovery")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--approved-head", required=True)
    parser.add_argument("--reason-code", required=True)
    args = parser.parse_args(argv)
    try:
        from .day1_launch import current_process_sid

        result = recover_kill_switch(
            repo_root=args.repo_root,
            approved_head=args.approved_head,
            recovery_reason_code=args.reason_code,
            evidence_collector=IBKRReadOnlySessionCollector().collect,
            head_reader=_git_head,
            current_sid=current_process_sid,
            token_elevated=_is_elevated,
            now_utc=lambda: datetime.now(timezone.utc),
        )
    except (ExperimentControlError, KillSwitchRecoveryError) as exc:
        print(canonical_bytes({"status": "BLOCK", "reason_codes": [str(exc)]}).decode())
        return 2
    print(canonical_bytes(result).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
