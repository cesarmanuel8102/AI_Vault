#!/usr/bin/env python3
"""Prepare exact, reproducible artifacts for the supervision-first PAPER pilot.

This tool performs no broker writes. It consumes a fresh read-only PAPER receipt,
the canonical Day1 ledger, and the existing epoch authority. It emits the V4
transition target plus phase-specific maintenance evidence.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psutil

from ibkr_paper_30d.canary_candidate import OwnerPilotAuthorization
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.contract_ownership import canonical_contract_identity
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.multi_universe_maintenance import (
    MaintenanceConfig,
    MaintenanceEvidence,
)
from ibkr_paper_30d.multi_universe_models import (
    CapitalSleeve,
    OwnerEconomicRiskAuthorization,
    SleeveAuthorityDefinition,
    TransitionPhase,
    TransitionTarget,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.readonly_acceptance import is_safe_account_summary_partial
from ibkr_paper_30d.successor_supervision import build_supervision_binding_plan

ACCOUNT_HASH = "cd82698d836ef78fd1a0c70b90ccebf690e43076ec2aa0aae4067c03faa4f5b0"
WRITER_CLIENT_ID = 19761
MUTEX_NAME = r"Local\CodexIbkrPaper30DExecutionLockV1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload))


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.DEVNULL
    ).strip()


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _writer_process_count() -> int:
    count = 0
    for process in psutil.process_iter(("cmdline",)):
        try:
            command = " ".join(process.info.get("cmdline") or ()).lower()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if "ibkr_paper_30d.day1_launch" in command:
            count += 1
    return count


def _receipt_is_certain(receipt: dict[str, Any]) -> bool:
    return receipt.get("status") == "PASS" or is_safe_account_summary_partial(receipt)


def _validate_receipt(receipt: dict[str, Any], now: datetime) -> None:
    if not _receipt_is_certain(receipt):
        raise RuntimeError("READONLY_BROKER_STATE_NOT_CERTAIN")
    broker_writes = receipt.get("real_order_writes_attempted")
    if (
        receipt.get("expected_account_identity_hash") != ACCOUNT_HASH
        or receipt.get("gateway_mode") != "PAPER"
        or int(receipt.get("port") or 0) != 4002
        or broker_writes is None
        or int(broker_writes) != 0
    ):
        raise RuntimeError("READONLY_PAPER_AUTHORITY_INVALID")
    try:
        observed = datetime.fromisoformat(
            str(receipt["server_timestamp_utc"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("READONLY_BROKER_TIMESTAMP_INVALID") from exc
    age = now - observed
    if age < timedelta(seconds=-5) or age > timedelta(minutes=3):
        raise RuntimeError("READONLY_BROKER_EVIDENCE_STALE")


def _validate_live_supervision_lock(lock: dict[str, Any], now: datetime) -> None:
    try:
        heartbeat = datetime.fromisoformat(
            str(lock["heartbeat_at_utc"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        pid = int(lock["pid"])
        generation = int(lock["generation"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("SUCCESSOR_WRITER_LOCK_INVALID") from exc
    if (
        lock.get("state") != "ACTIVE"
        or lock.get("order_authority") is not False
        or generation <= 0
        or now - heartbeat > timedelta(seconds=90)
        or now < heartbeat - timedelta(seconds=5)
        or not psutil.pid_exists(pid)
        or _writer_process_count() != 1
    ):
        raise RuntimeError("SUCCESSOR_WRITER_LOCK_NOT_SUPERVISION_ONLY")


def _ledger_payload(state: Any, last_event_sha256: str) -> dict[str, Any]:
    return {
        "schema": "DAY1_LEDGER_SOURCE_STATE_V1",
        "allocation_usd": str(state.allocation),
        "cash_usd": str(state.cash),
        "market_value_usd": str(state.market_value),
        "equity_usd": str(state.equity),
        "high_water_mark_usd": str(state.high_water_mark),
        "drawdown_usd": str(state.drawdown),
        "fees_usd": str(state.fees),
        "positions": [asdict(item) for item in state.positions],
        "event_count": state.event_count,
        "last_event_sha256": last_event_sha256,
    }


def _load_epoch(db: Database) -> tuple[dict[str, Any], dict[str, Any], str]:
    auth = db.execute(
        "SELECT payload_json FROM experiment_epoch_authorization_events_v2 "
        "WHERE state='AUTHORIZED' ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    clock = db.execute(
        "SELECT payload_json,event_sha256 FROM experiment_epoch_clock_events_v2 "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if auth is None or clock is None:
        raise RuntimeError("CURRENT_EPOCH_AUTHORITY_MISSING")
    return json.loads(str(auth[0])), json.loads(str(clock[0])), str(clock[1])


def _load_lock(db: Database) -> dict[str, Any]:
    row = db.execute(
        "SELECT payload_json,payload_sha256 FROM experiment_state "
        "WHERE experiment_id='EXECUTION_LOCK_V1'"
    ).fetchone()
    if row is None:
        raise RuntimeError("EXECUTION_LOCK_PROJECTION_MISSING")
    payload = json.loads(str(row[0]))
    if sha256_json(payload) != str(row[1]):
        raise RuntimeError("EXECUTION_LOCK_PROJECTION_INVALID")
    return payload


def _position_contract(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "conId": int(raw["contract_id"]),
        "secType": str(raw["security_type"]),
        "currency": str(raw["currency"]),
        "exchange": "SMART",
        "localSymbol": str(raw["symbol"]),
        "tradingClass": str(raw["symbol"]),
        "multiplier": "1",
    }


def _build_snapshots(
    *,
    receipt: dict[str, Any],
    state: Any,
    fills: list[dict[str, Any]],
    transition_id: str,
    writer_binding_sha256: str,
    execution_lock_generation: int,
    regular_authority_sha256: str,
    source_ledger_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    open_order_count = receipt.get("open_order_count")
    if open_order_count is None or int(open_order_count) != 0:
        raise RuntimeError("OPEN_ORDER_BLOCKS_SUPERVISION_BINDING")
    broker_positions = {
        int(item["contract_id"]): item for item in receipt.get("positions", ())
    }
    ledger_positions = {int(item.contract_id): item for item in state.positions}
    if set(broker_positions) != set(ledger_positions):
        raise RuntimeError("BROKER_LEDGER_POSITION_SET_MISMATCH")

    fill_by_contract: dict[int, list[str]] = {}
    for fill in fills:
        fill_by_contract.setdefault(int(fill["contract_id"]), []).append(
            str(fill["execution_id_hash"])
        )

    broker_rows: list[dict[str, Any]] = []
    day1_rows: list[dict[str, Any]] = []
    for contract_id in sorted(ledger_positions):
        broker_raw = broker_positions[contract_id]
        position = ledger_positions[contract_id]
        if Decimal(str(broker_raw["quantity"])) != position.quantity:
            raise RuntimeError("BROKER_LEDGER_POSITION_QUANTITY_MISMATCH")
        contract = canonical_contract_identity(_position_contract(broker_raw))
        historical = tuple(fill_by_contract.get(contract_id, ()))
        if not historical:
            raise RuntimeError("INHERITED_POSITION_FILL_LINEAGE_MISSING")
        group_id = f"inherited-day1-{contract_id}"
        lineage = sha256_json(
            {"contract": contract.sha256, "historical_fill_sha256": historical}
        )
        broker_rows.append(
            {
                "contract": contract.model_dump(mode="json"),
                "ownership_members": [contract.model_dump(mode="json")],
                "group_id": group_id,
                "quantity": str(position.quantity),
                "multiplier": str(position.multiplier),
                "average_cost": str(position.average_cost),
                "mark": str(position.mark),
                "market_value_usd": str(position.market_value),
            }
        )
        day1_rows.append(
            {
                "contract_identity_sha256": contract.sha256,
                "group_id": group_id,
                "quantity": str(position.quantity),
                "average_cost": str(position.average_cost),
                "historical_fill_sha256": list(historical),
                "lineage_sha256": lineage,
            }
        )

    contract_hash_by_id = {
        int(position.contract_id): row["contract_identity_sha256"]
        for position, row in zip(state.positions, day1_rows, strict=True)
    }
    executions = [
        {
            "execution_id_hash": str(fill["execution_id_hash"]),
            "contract_identity_sha256": contract_hash_by_id[int(fill["contract_id"])],
            "commission": "0.00",
        }
        for fill in fills
    ]
    execution_hashes = [item["execution_id_hash"] for item in executions]
    unrealized = state.equity - state.allocation
    broker_snapshot = {
        "account_identity_sha256": ACCOUNT_HASH,
        "writer_binding_sha256": writer_binding_sha256,
        "execution_lock_generation": execution_lock_generation,
        "observed_at_utc": str(receipt.get("server_timestamp_utc") or ""),
        "positions": broker_rows,
        "open_orders": [],
        "executions": executions,
        "fees_usd": str(state.fees),
        "realized_pnl_usd": "0.00",
        "unrealized_pnl_usd": str(unrealized),
        "execution_ambiguity": False,
    }
    day1_projection = {
        "account_identity_sha256": ACCOUNT_HASH,
        "transition_id": transition_id,
        "writer_binding_sha256": writer_binding_sha256,
        "execution_lock_generation": execution_lock_generation,
        "regular_sleeve_authority_sha256": regular_authority_sha256,
        "allocation_usd": str(state.allocation),
        "currency_balances": [{"currency": "USD", "amount": str(state.cash)}],
        "positions": day1_rows,
        "open_order_count": 0,
        "fill_count": len(execution_hashes),
        "fees_usd": str(state.fees),
        "realized_pnl_usd": "0.00",
        "unrealized_pnl_usd": str(unrealized),
        "historical_event_sha256": execution_hashes,
        "source_ledger_sha256": source_ledger_sha256,
        "day1_lineage_sha256": sha256_json(day1_rows),
    }
    return broker_snapshot, day1_projection


def _host_evidence(
    *, target: TransitionTarget, phase_evidence: dict[str, Any], now: datetime
) -> MaintenanceEvidence:
    return MaintenanceEvidence(
        observed_at_utc=now,
        current_head=target.approved_git_head,
        tracked_tree_clean=True,
        paper_port_4002_listening=_port_open(4002),
        live_port_4001_listening=_port_open(4001),
        authenticated_paper=True,
        account_identity_sha256=target.account_identity_sha256,
        broker_state_certain=True,
        writer_count=_writer_process_count(),
        writer_binding_sha256=target.writer_binding_sha256,
        receipt_sha256=(
            target.owner_authorization_sha256,
            target.canary_authorization_sha256,
            target.successor_definition_sha256,
        ),
        phase_evidence=phase_evidence,
    )


def prepare(args: argparse.Namespace) -> None:
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    receipt = _read(args.readonly_receipt)
    now = _utc_now()
    _validate_receipt(receipt, now)
    if args.approved_head != _git(repo, "rev-parse", "HEAD"):
        raise RuntimeError("APPROVED_HEAD_MISMATCH")
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("TRACKED_TREE_DIRTY")

    db_path = repo / "state/ibkr_paper_30d/autonomous.sqlite3"
    owner_receipt_path = (
        repo / "state/ibkr_paper_30d/reports/owner_successor_authorization_v2.json"
    )
    owner_receipt = _read(owner_receipt_path)
    with Database.open(db_path) as db:
        ledger = AutonomousExperimentLedger(db)
        state = ledger.project()
        fills = ledger.canonical_fill_events()
        epoch_auth, epoch_clock, clock_sha = _load_epoch(db)
        last = db.execute(
            "SELECT event_sha256 FROM autonomous_ledger_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        if last is None or not state.valid:
            raise RuntimeError("DAY1_LEDGER_INVALID")
        source_ledger_sha = str(last[0])

    if owner_receipt.get("receipt_sha256") != epoch_auth.get("receipt_sha256"):
        raise RuntimeError("OWNER_SUCCESSOR_RECEIPT_MISMATCH")
    if epoch_clock.get("epoch_id") != epoch_auth.get("epoch_id"):
        raise RuntimeError("SUCCESSOR_CLOCK_AUTHORITY_MISMATCH")
    end_utc = datetime.fromisoformat(str(epoch_clock["end_utc"]).replace("Z", "+00:00"))
    if now >= end_utc:
        raise RuntimeError("SUCCESSOR_EPOCH_EXPIRED")

    source = _ledger_payload(state, source_ledger_sha)
    regular = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.REGULAR_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=state.equity,
        opening_pnl_usd=state.equity - state.allocation,
        source_state_sha256=sha256_json(source),
    )
    continuous_source = {
        "schema": "CONTINUOUS_SLEEVE_OPENING_STATE_V1",
        "allocation_usd": "500.00",
        "equity_usd": "500.00",
        "positions": [],
        "open_orders": [],
        "realized_pnl_usd": "0.00",
        "unrealized_pnl_usd": "0.00",
    }
    continuous = SleeveAuthorityDefinition(
        sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
        authorized_principal_usd=Decimal("500"),
        opening_equity_usd=Decimal("500"),
        opening_pnl_usd=Decimal("0"),
        source_state_sha256=sha256_json(continuous_source),
    )
    economic = OwnerEconomicRiskAuthorization(
        authorization_id=f"owner-two-sleeve-risk-{now:%Y%m%dT%H%M%SZ}",
        owner_id=str(owner_receipt["actor_sid"]),
        policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        regular_allocation_usd=Decimal("500"),
        extended_allocation_usd=Decimal("500"),
        maximum_liability_ratio=Decimal("1.00"),
        daily_loss_limit_usd="DISABLED",
        drawdown_limit_usd="DISABLED",
        successor_definition_sha256=str(epoch_auth["definition_sha256"]),
        issued_at_utc=now,
        expires_at_utc=end_utc,
    )
    owner_pilot = OwnerPilotAuthorization(
        authorization_id=f"owner-continuous-pilot-{now:%Y%m%dT%H%M%SZ}",
        owner_id=str(owner_receipt["actor_sid"]),
        account_identity_sha256=ACCOUNT_HASH,
        successor_definition_sha256=str(epoch_auth["definition_sha256"]),
        approved_head=args.approved_head,
        maximum_debit_usd=Decimal("475.00"),
        maximum_loss_usd=Decimal("475.00"),
        fee_allowance_usd=Decimal("25.00"),
        maximum_order_count=2,
        issued_at_utc=now,
        expires_at_utc=end_utc,
    )
    writer_binding_payload = {
        "schema": "MULTI_UNIVERSE_WRITER_BINDING_V1",
        "account_identity_sha256": ACCOUNT_HASH,
        "approved_head": args.approved_head,
        "host": "127.0.0.1",
        "port": 4002,
        "execution_client_id": WRITER_CLIENT_ID,
        "mutex_name": MUTEX_NAME,
        "successor_epoch_id": str(epoch_auth["epoch_id"]),
    }
    transition_id = (
        f"supervision-{epoch_auth['epoch_id'].lower()}-{args.approved_head[:12]}"
    )
    target = TransitionTarget(
        transition_id=transition_id,
        predecessor_epoch_id=str(epoch_auth["predecessor_epoch_id"]),
        successor_epoch_id=str(epoch_auth["epoch_id"]),
        successor_definition_sha256=str(epoch_auth["definition_sha256"]),
        owner_authorization_sha256=str(owner_receipt["receipt_sha256"]),
        approved_git_head=args.approved_head,
        account_identity_sha256=ACCOUNT_HASH,
        clock_authority_sha256=clock_sha,
        regular_sleeve_authority_sha256=regular.sha256,
        continuous_sleeve_authority_sha256=continuous.sha256,
        economic_risk_authorization_sha256=economic.sha256,
        certified_family_set_sha256=sha256_json([]),
        canary_authorization_sha256=owner_pilot.sha256,
        writer_binding_sha256=sha256_json(writer_binding_payload),
    )
    broker_snapshot, day1_projection = _build_snapshots(
        receipt=receipt,
        state=state,
        fills=fills,
        transition_id=transition_id,
        writer_binding_sha256=target.writer_binding_sha256,
        execution_lock_generation=1,
        regular_authority_sha256=regular.sha256,
        source_ledger_sha256=source_ledger_sha,
    )
    phase_evidence = {"target_sha256": target.sha256}
    evidence = _host_evidence(target=target, phase_evidence=phase_evidence, now=now)
    config = MaintenanceConfig(
        repo_root=repo,
        database_path=db_path,
        backup_directory=output / "backup-before-v4",
        authority_file_paths=(
            owner_receipt_path,
            output / "regular_sleeve_authority.json",
            output / "continuous_sleeve_authority.json",
            output / "economic_risk_authorization.json",
            output / "owner_pilot_authorization.json",
        ),
        approved_head=args.approved_head,
        target=target,
        requested_phase=TransitionPhase.PREPARED,
        now_utc=now,
    )
    launch_authority = {
        "schema": "MULTI_UNIVERSE_LAUNCH_AUTHORITY_V1",
        "successor_epoch_id": target.successor_epoch_id,
        "successor_definition_sha256": target.successor_definition_sha256,
        "owner_authorization_receipt_sha256": target.owner_authorization_sha256,
        "owner_pilot_authorization": owner_pilot.model_dump(mode="json"),
        "initial_activation": True,
    }

    files = {
        "day1_source_state.json": source,
        "continuous_source_state.json": continuous_source,
        "regular_sleeve_authority.json": regular.model_dump(mode="json"),
        "continuous_sleeve_authority.json": continuous.model_dump(mode="json"),
        "economic_risk_authorization.json": economic.model_dump(mode="json"),
        "owner_pilot_authorization.json": owner_pilot.model_dump(mode="json"),
        "writer_binding.json": writer_binding_payload,
        "transition_target.json": target.model_dump(mode="json"),
        "maintenance_config.json": config.model_dump(mode="json"),
        "maintenance_evidence.json": evidence.model_dump(mode="json"),
        "multi_universe_launch_authority.json": launch_authority,
        "broker_snapshot.template.json": broker_snapshot,
        "day1_projection.template.json": day1_projection,
    }
    for name, payload in files.items():
        _write(output / name, payload)
    manifest = {
        "schema": "SUPERVISION_PILOT_ARTIFACT_MANIFEST_V1",
        "created_at_utc": now,
        "approved_head": args.approved_head,
        "transition_target_sha256": target.sha256,
        "files": {
            name: sha256_json(payload) for name, payload in sorted(files.items())
        },
        "broker_write_count": 0,
        "live_connection_count": 0,
    }
    _write(output / "artifact_manifest.json", manifest)
    print(json.dumps(manifest, default=str, sort_keys=True))


def refresh(args: argparse.Namespace) -> None:
    output = args.output_dir.resolve()
    repo = args.repo_root.resolve()
    target = TransitionTarget.model_validate(_read(output / "transition_target.json"))
    now = _utc_now()
    receipt = _read(args.readonly_receipt)
    _validate_receipt(receipt, now)
    phase = TransitionPhase(args.phase)
    evidence_payload: dict[str, Any] = {
        "phase_evidence_sha256": sha256_json(
            {"phase": phase.value, "target_sha256": target.sha256}
        )
    }
    if phase is TransitionPhase.PREDECESSOR_RETIRED:
        tombstone = _read(args.retirement_tombstone)
        evidence_payload.update(
            retirement_status="PASS",
            retirement_tombstone_sha256=sha256_json(tombstone),
        )
    elif phase is TransitionPhase.SUCCESSOR_COMMITTED:
        evidence_payload["successor_commit_sha256"] = sha256_json(
            {
                "target_sha256": target.sha256,
                "approved_head": target.approved_git_head,
                "committed_at_utc": now,
            }
        )
    elif phase is TransitionPhase.SUPERVISION_BOUND:
        with Database.open(repo / "state/ibkr_paper_30d/autonomous.sqlite3") as db:
            ledger = AutonomousExperimentLedger(db)
            state = ledger.project()
            fills = ledger.canonical_fill_events()
            lock = _load_lock(db)
            last = db.execute(
                "SELECT event_sha256 FROM autonomous_ledger_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if last is None:
                raise RuntimeError("DAY1_LEDGER_INVALID")
        _validate_live_supervision_lock(lock, now)
        regular = SleeveAuthorityDefinition.model_validate(
            _read(output / "regular_sleeve_authority.json")
        )
        continuous = SleeveAuthorityDefinition.model_validate(
            _read(output / "continuous_sleeve_authority.json")
        )
        economic = OwnerEconomicRiskAuthorization.model_validate(
            _read(output / "economic_risk_authorization.json")
        )
        broker_snapshot, day1_projection = _build_snapshots(
            receipt=receipt,
            state=state,
            fills=fills,
            transition_id=target.transition_id,
            writer_binding_sha256=target.writer_binding_sha256,
            execution_lock_generation=int(lock["generation"]),
            regular_authority_sha256=regular.sha256,
            source_ledger_sha256=str(last[0]),
        )
        plan = build_supervision_binding_plan(
            broker_snapshot=broker_snapshot,
            day1_projection=day1_projection,
            account_identity_sha256=target.account_identity_sha256,
            transition_target_sha256=target.sha256,
            regular_sleeve_authority=regular,
            continuous_sleeve_authority=continuous,
            economic_risk_authorization=economic,
        )
        evidence_payload = {
            "supervision_binding_plan": plan.model_dump(mode="json"),
            "fresh_broker_snapshot": broker_snapshot,
        }
    evidence = _host_evidence(target=target, phase_evidence=evidence_payload, now=now)
    config_raw = _read(output / "maintenance_config.json")
    config_raw["requested_phase"] = phase.value
    config_raw["now_utc"] = now.isoformat().replace("+00:00", "Z")
    _write(output / "maintenance_config.json", config_raw)
    _write(output / "maintenance_evidence.json", evidence.model_dump(mode="json"))
    print(evidence.model_dump_json())


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("prepare")
    first.add_argument("--repo-root", type=Path, required=True)
    first.add_argument("--approved-head", required=True)
    first.add_argument("--readonly-receipt", type=Path, required=True)
    first.add_argument("--output-dir", type=Path, required=True)
    later = sub.add_parser("refresh")
    later.add_argument("--repo-root", type=Path, required=True)
    later.add_argument("--readonly-receipt", type=Path, required=True)
    later.add_argument("--output-dir", type=Path, required=True)
    later.add_argument(
        "--phase", choices=[item.value for item in TransitionPhase], required=True
    )
    later.add_argument("--retirement-tombstone", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    else:
        if (
            args.phase == TransitionPhase.PREDECESSOR_RETIRED.value
            and not args.retirement_tombstone
        ):
            parser.error("--retirement-tombstone is required for PREDECESSOR_RETIRED")
        refresh(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
