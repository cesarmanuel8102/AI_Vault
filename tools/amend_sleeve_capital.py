#!/usr/bin/env python3
"""Inspect or atomically increase both PAPER experiment sleeve allocations."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psutil

from ibkr_paper_30d.capital_amendment import amend_two_sleeve_capital
from ibkr_paper_30d.experiment_control import ExperimentClockStore
from ibkr_paper_30d.multi_universe_authority import MultiUniverseAuthorityStore
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.successor_epoch import current_epoch_definition


def _active_writer_processes() -> list[int]:
    markers = (
        "ibkr_paper_30d.day1_launch",
        "ibkr_paper_30d.autonomous_service",
        "run_ibkr_multi_universe_service",
        "run_ibkr_day1_service",
    )
    excluded = {os.getpid()}
    try:
        excluded.update(parent.pid for parent in psutil.Process().parents())
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        raise SystemExit("PROCESS_LIVENESS_AMBIGUOUS")
    active: list[int] = []
    for process in psutil.process_iter(("pid", "cmdline")):
        if process.info["pid"] in excluded:
            continue
        try:
            command = " ".join(process.info.get("cmdline") or ()).lower()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if any(marker in command for marker in markers):
            active.append(int(process.info["pid"]))
    return active


def _summary(db: Database) -> dict[str, object]:
    ledger = SleeveLedgerStore(db)
    authority = MultiUniverseAuthorityStore(db)
    states = {
        sleeve: ledger.project(sleeve)
        for sleeve in (
            CapitalSleeve.REGULAR_SLEEVE,
            CapitalSleeve.CONTINUOUS_SLEEVE,
        )
    }
    economic = authority.economic_authorization()
    return {
        "sleeves": {
            sleeve.value: {
                "allocation_usd": str(state.allocation_usd),
                "usd_balance": str(state.balance("USD")),
                "realized_pnl_usd": str(state.realized_pnl_usd),
                "unrealized_pnl_usd": str(state.unrealized_pnl_usd),
                "fees_usd": str(state.fees_usd),
                "positions": len(state.positions),
                "open_order_count": state.open_order_count,
                "reserved_liability_usd": str(state.reserved_liability_usd),
                "authority_principal_usd": str(
                    authority.sleeve_authority(sleeve).authorized_principal_usd
                ),
            }
            for sleeve, state in states.items()
        },
        "economic_authorization_sha256": None if economic is None else economic.sha256,
        "economic_regular_allocation_usd": (
            None if economic is None else str(economic.regular_allocation_usd)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--target", type=Decimal, default=Decimal("10000"))
    parser.add_argument("--amendment-id", required=True)
    parser.add_argument("--previous-head", required=True)
    parser.add_argument("--new-head", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    if not args.db.is_file():
        raise SystemExit("DATABASE_NOT_FOUND")
    with Database.open(args.db) as db:
        current_epoch = current_epoch_definition(db)
        if current_epoch is None:
            raise SystemExit("CURRENT_EPOCH_NOT_FOUND")
        clock_before = ExperimentClockStore(db).clock_for_epoch(current_epoch.epoch_id)
        before = _summary(db)
        result: dict[str, object] = {
            "status": "INSPECT" if not args.apply else "PENDING",
            "database": str(args.db.resolve()),
            "epoch_id": current_epoch.epoch_id,
            "clock_event_sha256": clock_before.event_sha256,
            "clock_start_utc": clock_before.start_utc.isoformat(),
            "clock_end_utc": clock_before.end_utc.isoformat(),
            "target_principal_usd": str(args.target),
            "before": before,
        }
        if args.apply:
            writers = _active_writer_processes()
            if writers:
                raise SystemExit(
                    "AUTONOMOUS_WRITER_STILL_RUNNING:" + ",".join(map(str, writers))
                )
            now = datetime.now(timezone.utc)
            result["amendment"] = amend_two_sleeve_capital(
                db,
                target_principal_usd=args.target,
                amendment_id=args.amendment_id,
                now_utc=now,
                expires_at_utc=clock_before.end_utc,
                previous_head=args.previous_head.lower(),
                new_head=args.new_head.lower(),
            )
            clock_after = ExperimentClockStore(db).clock_for_epoch(
                current_epoch.epoch_id
            )
            if clock_after != clock_before:
                raise SystemExit("EXPERIMENT_CLOCK_CHANGED")
            result["after"] = _summary(db)
            result["status"] = "PASS"
            result["clock_unchanged"] = True
        rendered = json.dumps(result, indent=2, sort_keys=True)
        if args.receipt is not None:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
