"""Post-remediation measurement segments.

A segment marks a deployment boundary inside the running experiment. It never
resets the measurement clock, the capital or any ledger: cumulative results
since the allocation and results since the segment start are both reported.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from .persistence import Database
from .repositories import EventRepository
from .sleeve_ledger import SleeveLedgerStore, authoritative_sleeve_equity
from .types import new_uuid7

EVENT_TYPE = "EXPERIMENT_MEASUREMENT_SEGMENT_STARTED"
SLEEVES = ("REGULAR_SLEEVE", "CONTINUOUS_SLEEVE")


class MeasurementSegmentError(RuntimeError):
    pass


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _et(value: datetime) -> str | None:
    try:
        from zoneinfo import ZoneInfo

        return value.astimezone(ZoneInfo("America/New_York")).isoformat()
    except Exception:
        return None


def _parse(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sleeve_states(db: Database) -> dict[str, Any]:
    dumped = SleeveLedgerStore(db).project_all().model_dump(mode="python")
    return {
        "REGULAR_SLEEVE": dumped.get("regular") or {},
        "CONTINUOUS_SLEEVE": dumped.get("continuous") or dumped.get("extended") or {},
    }


def latest_segment(db: Database) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT payload_json FROM state_events WHERE event_type=? ORDER BY sequence DESC LIMIT 1",
        (EVENT_TYPE,),
    ).fetchone()
    return None if row is None else json.loads(str(row[0]))


def record_measurement_segment(
    db: Database,
    *,
    previous_head: str,
    new_head: str,
    reason: str,
    baseline_audit_sha256: str,
    now_utc: datetime,
) -> dict[str, Any]:
    existing = latest_segment(db)
    if existing is not None and existing.get("new_head") == new_head:
        return existing
    sleeves: dict[str, Any] = {}
    for sleeve, state in _sleeve_states(db).items():
        valuation = authoritative_sleeve_equity(state)
        if valuation.equity_usd is None:
            raise MeasurementSegmentError(f"SLEEVE_EQUITY_UNAVAILABLE:{sleeve}")
        allocation = Decimal(str(state.get("allocation_usd") or "0"))
        sleeves[sleeve] = {
            "allocation_usd": str(allocation),
            "segment_start_equity_usd": str(valuation.equity_usd),
            "cumulative_pnl_vs_allocation_usd": str(valuation.equity_usd - allocation),
            "equity_formula": valuation.formula,
        }
    now = now_utc.astimezone(timezone.utc)
    payload = {
        "schema": "EXPERIMENT_MEASUREMENT_SEGMENT_V1",
        "segment_id": f"segment-{new_uuid7()}",
        "segment_start_utc": _iso(now),
        "segment_start_et": _et(now),
        "previous_head": previous_head,
        "new_head": new_head,
        "reason": reason,
        "baseline_audit_sha256": baseline_audit_sha256,
        "sleeves": sleeves,
        "clock_reset": False,
        "capital_reset": False,
        "previous_segment_id": None if existing is None else existing.get("segment_id"),
    }
    EventRepository(db).append(EVENT_TYPE, payload)
    return payload


def measurement_segment_report(
    db: Database, *, current_equity_usd: Mapping[str, Decimal | None]
) -> dict[str, Any] | None:
    segment = latest_segment(db)
    if segment is None:
        return None
    start = _parse(segment.get("segment_start_utc"))
    commissions = {sleeve: Decimal("0") for sleeve in SLEEVES}
    for event in SleeveLedgerStore(db)._events():
        if event.get("event_type") != "MODEL_FILL_IMPORTED":
            continue
        created = _parse(event.get("created_at_utc"))
        if start is None or created is None or created < start:
            continue
        fill = event.get("fill") or {}
        sleeve = str(event.get("sleeve"))
        if sleeve in commissions:
            commissions[sleeve] += Decimal(str(fill.get("commission_usd") or "0"))
    sleeves: dict[str, Any] = {}
    segment_total = Decimal("0")
    cumulative_total = Decimal("0")
    complete = True
    for sleeve in SLEEVES:
        base = (segment.get("sleeves") or {}).get(sleeve) or {}
        current = current_equity_usd.get(sleeve)
        start_equity = Decimal(str(base.get("segment_start_equity_usd") or "0"))
        allocation = Decimal(str(base.get("allocation_usd") or "0"))
        if current is None:
            complete = False
        else:
            segment_total += current - start_equity
            cumulative_total += current - allocation
        sleeves[sleeve] = {
            "segment_start_equity_usd": str(start_equity),
            "current_equity_usd": None if current is None else str(current),
            "segment_pnl_usd": None if current is None else str(current - start_equity),
            "cumulative_pnl_vs_allocation_usd": (
                None if current is None else str(current - allocation)
            ),
            "segment_commissions_usd": str(commissions[sleeve]),
        }
    return {
        "segment_id": segment.get("segment_id"),
        "segment_start_utc": segment.get("segment_start_utc"),
        "previous_head": segment.get("previous_head"),
        "new_head": segment.get("new_head"),
        "reason": segment.get("reason"),
        "baseline_audit_sha256": segment.get("baseline_audit_sha256"),
        "sleeves": sleeves,
        "combined": {
            "segment_pnl_usd": str(segment_total) if complete else None,
            "cumulative_pnl_vs_allocation_usd": str(cumulative_total) if complete else None,
        },
        "clock_reset": False,
        "technical_cost_attribution": "NOT_MEASURED_SEPARATELY",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.measurement_segment")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--previous-head", required=True)
    parser.add_argument("--new-head", required=True)
    parser.add_argument("--reason", default="economic-state-and-availability-remediation")
    parser.add_argument("--baseline-audit-sha256", required=True)
    args = parser.parse_args(argv)
    db_path = args.repo_root / "state" / "ibkr_paper_30d" / "autonomous.sqlite3"
    with Database.open(db_path) as db:
        segment = record_measurement_segment(
            db,
            previous_head=args.previous_head.lower(),
            new_head=args.new_head.lower(),
            reason=args.reason,
            baseline_audit_sha256=args.baseline_audit_sha256.lower(),
            now_utc=datetime.now(timezone.utc),
        )
    print(json.dumps(segment, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
