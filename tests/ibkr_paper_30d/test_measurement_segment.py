from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.measurement_segment import (
    MeasurementSegmentError,
    measurement_segment_report,
    record_measurement_segment,
)
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.sleeve_ledger import CurrencyBalance, RegularCarryForward, SleeveLedgerStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2

AUDIT = "cb35747f52ddbd135b399d58a2629cf8730d171b056c051c5cf8986bacae3f06"
OLD = "a" * 40
NEW = "b" * 40
START = datetime(2026, 11, 7, 23, 0, tzinfo=timezone.utc)


@pytest.fixture()
def db(tmp_path):
    database = Database.open(tmp_path / "segment.sqlite3")
    install_successor_schema_v2(database)
    install_continuity_schema_v3(database)
    install_multi_universe_schema_v4(database)
    ledger = SleeveLedgerStore(database)
    ledger.bootstrap_regular(RegularCarryForward(
        allocation_usd=Decimal("500.00"),
        currency_balances=(CurrencyBalance(currency="USD", amount=Decimal("514.2260692")),),
        positions=(), open_order_count=0, fill_count=0, fees_usd=Decimal("0"),
        realized_pnl_usd=Decimal("0"), unrealized_pnl_usd=Decimal("0"),
        historical_event_sha256=(), source_ledger_sha256="a" * 64,
    ))
    ledger.bootstrap_extended()
    ledger.append(CapitalSleeve.CONTINUOUS_SLEEVE, "CURRENCY_DEBIT", {"amount": "36.784886"})
    yield database
    database.close()


def _record(db, **overrides):
    values = dict(previous_head=OLD, new_head=NEW,
                  reason="economic-state-and-availability-remediation",
                  baseline_audit_sha256=AUDIT, now_utc=START)
    values.update(overrides)
    return record_measurement_segment(db, **values)


def test_segment_records_heads_equity_prior_pnl_and_audit_hash(db) -> None:
    segment = _record(db)

    assert segment["segment_start_utc"] == "2026-11-07T23:00:00Z"
    assert segment["segment_start_et"].startswith("2026-11-07T18:00:00")
    assert segment["previous_head"] == OLD and segment["new_head"] == NEW
    assert segment["reason"] == "economic-state-and-availability-remediation"
    assert segment["baseline_audit_sha256"] == AUDIT
    regular = segment["sleeves"]["REGULAR_SLEEVE"]
    continuous = segment["sleeves"]["CONTINUOUS_SLEEVE"]
    assert Decimal(regular["segment_start_equity_usd"]) == Decimal("514.2260692")
    assert Decimal(regular["cumulative_pnl_vs_allocation_usd"]) == Decimal("14.2260692")
    assert Decimal(continuous["segment_start_equity_usd"]) == Decimal("463.215114")
    assert Decimal(continuous["cumulative_pnl_vs_allocation_usd"]) == Decimal("-36.784886")


def test_segment_recording_is_idempotent_per_head_and_preserves_history(db) -> None:
    first = _record(db)
    again = _record(db)

    assert again["segment_id"] == first["segment_id"]
    count = db.execute(
        "SELECT COUNT(*) FROM state_events WHERE event_type='EXPERIMENT_MEASUREMENT_SEGMENT_STARTED'"
    ).fetchone()[0]
    assert count == 1


def test_segment_requires_fresh_sleeve_equity(db) -> None:
    SleeveLedgerStore(db).append(
        CapitalSleeve.REGULAR_SLEEVE, "CURRENCY_CREDIT", {"currency": "EUR", "amount": "5"}
    )

    with pytest.raises(MeasurementSegmentError, match="SLEEVE_EQUITY_UNAVAILABLE"):
        _record(db)


def test_report_keeps_cumulative_and_segment_results_separately(db) -> None:
    _record(db)
    report = measurement_segment_report(
        db,
        current_equity_usd={"REGULAR_SLEEVE": Decimal("520.2260692"),
                            "CONTINUOUS_SLEEVE": Decimal("460.215114")},
    )

    regular = report["sleeves"]["REGULAR_SLEEVE"]
    continuous = report["sleeves"]["CONTINUOUS_SLEEVE"]
    assert Decimal(regular["segment_pnl_usd"]) == Decimal("6.0000000")
    assert Decimal(regular["cumulative_pnl_vs_allocation_usd"]) == Decimal("20.2260692")
    assert Decimal(continuous["segment_pnl_usd"]) == Decimal("-3.000000")
    assert Decimal(report["combined"]["segment_pnl_usd"]) == Decimal("3.0000000")
    assert report["clock_reset"] is False
    assert "segment_commissions_usd" in regular
    assert report["technical_cost_attribution"] == "NOT_MEASURED_SEPARATELY"


def test_report_is_none_without_segment(db) -> None:
    assert measurement_segment_report(db, current_equity_usd={}) is None


def test_bundle_context_exposes_cumulative_and_segment_results(db) -> None:
    from types import SimpleNamespace

    from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder

    _record(db)
    subject = object.__new__(AutonomousStateBuilder)
    subject.db = db

    context = subject._measurement_segment_context({
        "regular": SimpleNamespace(equity_usd=Decimal("514.2260692")),
        "continuous": SimpleNamespace(equity_usd=Decimal("463.215114")),
    })

    assert Decimal(context["sleeves"]["REGULAR_SLEEVE"]["segment_pnl_usd"]) == 0
    assert Decimal(context["sleeves"]["CONTINUOUS_SLEEVE"]["cumulative_pnl_vs_allocation_usd"]) == Decimal("-36.784886")


def test_bundle_context_without_database_has_no_segment() -> None:
    from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder

    subject = object.__new__(AutonomousStateBuilder)

    assert subject._measurement_segment_context({}) is None