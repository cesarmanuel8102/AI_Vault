from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ibkr_paper_30d.decision_diagnostics import build_risk_diagnostics
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.persistence import Database


REPO = Path(__file__).resolve().parents[2]


def _fill(symbol, side, qty, price, commission="1.00", con_id=1, sec_type="STK"):
    return {
        "contract": {"conId": con_id, "symbol": symbol, "secType": sec_type, "multiplier": "1"},
        "side": side,
        "quantity": str(qty),
        "price": str(price),
        "commission": commission,
        "orderRef": "codex-ibkr-paper-30d-test",
        "permId": 9000 + con_id,
        "orderId": 100 + con_id,
        "clientId": 19761,
        "execution_time": "2026-09-23T15:00:00Z",
    }


def ledger_with_fills(tmp_path, fills, marks=None, allocation="500.00"):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(
            db, allocation=Decimal(allocation)
        )
        for fill in fills:
            ledger.record_fill(fill)
        for contract_id, price in (marks or {}).items():
            ledger.record_mark(
                contract_id=contract_id, price=Decimal(str(price))
            )
        state = ledger.project()
    return state, fills


def test_diagnostics_reports_continuous_metrics_from_real_fills(tmp_path):
    state, fills = ledger_with_fills(
        tmp_path,
        fills=[_fill("AAPL", "BUY", 2, "100.00", con_id=265598)],
        marks={265598: "110.00"},
    )

    diagnostics = build_risk_diagnostics(state, fills=fills)

    assert diagnostics["current_equity"] == "519.00"
    assert diagnostics["realized_pnl"] == "0.00"
    assert diagnostics["unrealized_pnl"] == "19.00"
    assert diagnostics["max_drawdown"] == "0.00"
    assert diagnostics["gross_exposure"] == "220.00"
    assert diagnostics["net_exposure"] == "220.00"
    assert diagnostics["turnover"] == "0.40"
    assert diagnostics["win_count"] == 0
    assert diagnostics["loss_count"] == 0
    assert diagnostics["largest_position_fraction"] == "1.00"
    assert diagnostics["capital_utilization"] == "0.44"
    assert diagnostics["diagnostic_status"] == "OBSERVATION_ONLY"


def test_diagnostics_counts_closed_trades_win_and_loss(tmp_path):
    state, fills = ledger_with_fills(
        tmp_path,
        fills=[
            _fill("A", "BUY", 1, "100.00", con_id=1),
            _fill("A", "SELL", 1, "120.00", con_id=1),
            _fill("B", "BUY", 1, "50.00", con_id=2),
            _fill("B", "SELL", 1, "40.00", con_id=2),
        ],
    )

    diagnostics = build_risk_diagnostics(state, fills=fills)

    assert diagnostics["win_count"] == 1
    assert diagnostics["loss_count"] == 1
    assert diagnostics["realized_pnl"] == "6.00"
    assert diagnostics["payoff_asymmetry"] == "1.50"


def test_diagnostics_marks_unclosed_history_as_unavailable(tmp_path):
    state, fills = ledger_with_fills(tmp_path, fills=[])

    diagnostics = build_risk_diagnostics(state, fills=fills)

    assert diagnostics["equity_variability"] == "unavailable"
    assert diagnostics["time_under_water"] == "unavailable"
    assert diagnostics["realized_pnl"] == "0.00"


def test_diagnostics_without_fill_events_reports_realized_as_unavailable(tmp_path):
    """Without the ledger's fill events, per-trade realized P&L cannot be
    computed honestly. It must be reported as unavailable — never relabeled
    as unrealized or fabricated from equity alone."""

    state, _ = ledger_with_fills(
        tmp_path,
        fills=[_fill("AAPL", "BUY", 2, "100.00", con_id=265598)],
        marks={265598: "110.00"},
    )

    diagnostics = build_risk_diagnostics(state)

    assert diagnostics["realized_pnl"] == "unavailable"
    assert diagnostics["unrealized_pnl"] == "unavailable"
    assert diagnostics["win_count"] == "unavailable"
    assert diagnostics["loss_count"] == "unavailable"
    assert diagnostics["payoff_asymmetry"] == "unavailable"
    assert diagnostics["largest_winner_contribution"] == "unavailable"
    assert diagnostics["largest_loser_contribution"] == "unavailable"
    assert diagnostics["profit_concentration"] == "unavailable"
    # Continuous exposure metrics remain computable from the projection.
    assert diagnostics["current_equity"] == "519.00"
    assert diagnostics["gross_exposure"] == "220.00"
    assert diagnostics["capital_utilization"] == "0.44"


def test_no_invented_threshold_flags(tmp_path):
    state, fills = ledger_with_fills(
        tmp_path,
        fills=[_fill("AAPL", "BUY", 2, "100.00", con_id=265598)],
        marks={265598: "110.00"},
    )

    diagnostics = build_risk_diagnostics(state, fills=fills)

    for forbidden in ("concentration_flag", "risk_flag", "exposure_flag"):
        assert forbidden not in diagnostics, forbidden


def test_diagnostics_are_never_optimization_targets():
    import ibkr_paper_30d.decision_diagnostics as module
    import inspect

    source = inspect.getsource(module)
    assert '"OBSERVATION_ONLY"' in source or "OBSERVATION_ONLY" in source
    assert "sharpe" not in source.lower()
    assert "target" not in source.lower().replace("telemetry_source", "")


def test_diagnostics_not_consumed_by_validation_or_authorization_modules():
    allowed = {
        "ibkr_paper_30d/decision_diagnostics.py",
        "ibkr_paper_30d/autonomous_runtime.py",
        "ibkr_paper_30d/cli.py",
    }
    for path in (REPO / "ibkr_paper_30d").glob("*.py"):
        rel = f"ibkr_paper_30d/{path.name}"
        if rel in allowed or path.name.startswith("test_"):
            continue
        source = path.read_text(encoding="utf-8")
        assert "build_risk_diagnostics" not in source, (
            f"{rel} must not consume risk diagnostics"
        )


def test_diagnostics_output_is_canonical_serializable(tmp_path):
    state, fills = ledger_with_fills(
        tmp_path,
        fills=[_fill("AAPL", "BUY", 2, "100.00", con_id=265598)],
        marks={265598: "110.00"},
    )

    encoded = json.dumps(build_risk_diagnostics(state), sort_keys=True)
    assert json.loads(encoded)["diagnostic_status"] == "OBSERVATION_ONLY"


def test_peak_gross_exposure_is_continuous(tmp_path):
    state, fills = ledger_with_fills(
        tmp_path,
        fills=[
            _fill("AAPL", "BUY", 2, "100.00", con_id=1),
            _fill("MSFT", "BUY", 1, "300.00", con_id=2),
        ],
    )

    diagnostics = build_risk_diagnostics(state, fills=fills)

    assert diagnostics["gross_exposure"] == "500.00"
    assert diagnostics["peak_gross_exposure_ratio"] == "1.00"
