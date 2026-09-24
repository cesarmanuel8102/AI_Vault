from __future__ import annotations

import inspect
import re
from pathlib import Path

from ibkr_paper_30d import cli
from ibkr_paper_30d.market_observation_collector import ObservationConfig
from ibkr_paper_30d.market_policy import MarketPolicyFreezer


REPO = Path(__file__).resolve().parents[2]
GATE_SCRIPT = REPO / "RUN_IBKR_MARKET_DATA_GATE.ps1"


def test_canonical_policy_collection_cadence_is_four_seconds() -> None:
    """5 sec cadence left only 21 rejections of headroom per symbol on
    2026-09-24 (201 raw/symbol vs 180 accepted required). The canonical
    PRE-FREEZE policy collection cadence is 4 sec: floor(330/4)+1 = 84
    samples per window per symbol, giving calibration-only headroom for
    timestamp-skew rejections."""

    source = inspect.getsource(cli.observe_market_data)
    match = re.search(r"cadence_seconds: float = (\d+(?:\.\d+)?)", source)
    assert match is not None
    assert float(match.group(1)) == 4.0

    cli_main_source = inspect.getsource(cli.main)
    assert re.search(
        r'"--cadence-seconds", type=float, default=4\)', cli_main_source
    ), "CLI default for observe-market-data must be 4"


def test_gate_script_uses_canonical_cadence_and_window() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert '"--cadence-seconds", "4"' in text
    assert '"--window-seconds", "330"' in text
    # The pre-freeze collection must never regress to 5 seconds silently.
    assert '"--cadence-seconds", "5"' not in text


def test_policy_collection_protocol_geometry_is_unchanged() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "3x5min_windows_31min_start_separation" in text
    assert "$Starts[$Index - 1].AddMinutes(31)" in text
    assert '"SPY", "QQQ", "IEF"' in text


def test_theoretical_raw_capacity_per_required_symbol() -> None:
    # floor(330 / 4) + 1 = 83 per window per symbol -> 3 windows = 249.
    per_window = int(330 // 4) + 1
    assert per_window == 83
    assert per_window * 3 == 249
    assert per_window * 3 * 3 == 747


def test_policy_thresholds_are_unchanged() -> None:
    source = inspect.getsource(MarketPolicyFreezer._protocol_reasons)
    assert "len(accepted) < 540" in source
    assert "counts.get(symbol, 0) < 180" in source
    assert MarketPolicyFreezer.REQUIRED_SYMBOLS == frozenset({"SPY", "QQQ", "IEF"})


def test_clock_skew_validation_is_unchanged() -> None:
    from ibkr_paper_30d.market_observation import corrected_quote_age_ms

    source = inspect.getsource(corrected_quote_age_ms)
    assert "corrected < -uncertainty" in source
    assert "timestamp_resolution_ms + clock_sample.round_trip_ms // 2" in source
    collector_source = (
        REPO / "ibkr_paper_30d" / "market_observation_collector.py"
    ).read_text(encoding="utf-8")
    assert '"CLOCK_SKEW_UNCERTAIN"' in collector_source


def test_no_broker_write_surface_is_added_by_cadence_change() -> None:
    gate_text = GATE_SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "placeOrder",
        "cancelOrder",
        "reqGlobalCancel",
        "FINALIZE_IBKR_PREREQUISITES",
    ):
        assert forbidden not in gate_text, forbidden
    cli_source = inspect.getsource(cli.observe_market_data)
    for forbidden in ("placeOrder", "cancelOrder", "reqGlobalCancel"):
        assert forbidden not in cli_source, forbidden


def test_required_symbols_remain_calibration_evidence_not_trading_whitelist() -> None:
    """SPY/QQQ/IEF are market-data calibration evidence only; they are not
    a trading universe and must never gate the autonomous experiment."""

    freezer_source = inspect.getsource(MarketPolicyFreezer)
    assert "REQUIRED_SYMBOLS" in freezer_source
    # The autonomous research path must not consume the freezer's symbols.
    research_source = (
        REPO / "ibkr_paper_30d" / "ibkr_research_tools.py"
    ).read_text(encoding="utf-8")
    assert "REQUIRED_SYMBOLS" not in research_source
    assert 'frozenset({"SPY", "QQQ", "IEF"})' not in research_source
    # The mandate keeps its no-universe guarantees.
    from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider

    payload = CodexAutonomousCLIProvider._prompt_payload(
        _minimal_request(), _minimal_bundle(), [], []
    )
    assert payload["mandate"]["predefined_symbol_universe"] is False


def _minimal_bundle():
    from ibkr_paper_30d.trader_invocation import TraderInputBundle

    return TraderInputBundle(
        decision_cycle_id="cycle-cadence-1",
        utc_timestamp="2026-09-24T20:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"buying_power": "500.00"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )


def _minimal_request():
    from ibkr_paper_30d.trader_invocation import InvocationRequest

    return InvocationRequest(
        decision_cycle_id="cycle-cadence-1",
        invocation_id="inv-cadence-1",
        utc_timestamp="2026-09-24T20:00:01Z",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        model_configuration={"mode": "autonomous_research"},
        reasoning_effort="max",
        input_bundle_sha256="a" * 64,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id="paper-30d",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=60,
    )


def test_fresh_runtime_gate_cadence_is_a_distinct_operational_path() -> None:
    """The runtime fresh-market snapshot gate (cli.py validate-real-market-data
    and runtime_integrity.py) is a different route; it must remain untouched
    by the policy-collection cadence change."""

    cli_source = inspect.getsource(cli)
    runtime_source = (
        REPO / "ibkr_paper_30d" / "runtime_integrity.py"
    ).read_text(encoding="utf-8")
    # Fresh runtime gate keeps its own 5-second cadence.
    validate_fn = inspect.getsource(cli.validate_real_market_data)
    assert re.search(r"cadence_seconds=5", validate_fn)
    assert "cadence_seconds=5" in runtime_source
    # And the pre-freeze collection default is 4.
    observe_fn = inspect.getsource(cli.observe_market_data)
    assert re.search(r"cadence_seconds: float = 4", observe_fn)