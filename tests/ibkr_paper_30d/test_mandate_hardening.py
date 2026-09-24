from __future__ import annotations

import json
from pathlib import Path

from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle


REPO = Path(__file__).resolve().parents[2]


def bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-mandate-1",
        utc_timestamp="2026-09-23T20:00:00Z",
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


def request(value: TraderInputBundle) -> InvocationRequest:
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="inv-mandate-1",
        utc_timestamp="2026-09-23T20:00:01Z",
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        model_configuration={"mode": "autonomous_research"},
        reasoning_effort="max",
        input_bundle_sha256=value.sha256,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id="paper-30d",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=60,
    )


def mandate() -> dict:
    payload = CodexAutonomousCLIProvider._prompt_payload(
        request(bundle()), bundle(), [], [{"tool": "MARKET_SCANNER"}]
    )
    return payload["mandate"]


def instruction() -> str:
    return mandate()["instruction"]


def test_primary_objective_remains_maximize_terminal_experimental_equity():
    assert mandate()["objective"].startswith("Maximize terminal experimental equity")


def test_no_trade_remains_valid():
    assert mandate()["no_trade_is_allowed"] is True
    assert mandate()["no_trade_remains_valid"] is True


def test_activity_narratives_are_explicitly_not_success():
    m = mandate()
    assert m["trading_frequency_is_not_success"] is True
    assert m["inactivity_is_not_success"] is True
    assert m["cash_preservation_is_not_success_by_itself"] is True
    assert m["risk_taking_is_not_success_by_itself"] is True


def test_shallow_habitual_no_trade_is_explicitly_unacceptable():
    m = mandate()
    assert m["shallow_research_with_habitual_no_trade_is_not_acceptable"] is True
    assert m["avoidable_opportunity_cost_is_failure"] is True


def test_scarcity_and_optionality_are_part_of_expected_terminal_equity_reasoning():
    m = mandate()
    assert m["capital_and_remaining_time_are_scarce"] is True
    assert m["destroying_optionality_can_reduce_expected_terminal_equity"] is True
    assert m[
        "failing_to_exploit_superior_positive_expectancy_opportunity_can_reduce_expected_terminal_equity"
    ] is True


def test_instruction_requires_active_search_and_search_process_change():
    text = instruction().lower()
    assert "active search" in text
    assert "search process" in text
    assert "change the search process" in text


def test_instruction_requires_counterfactual_challenge_before_no_trade():
    text = instruction().lower()
    assert "counterfactual" in text
    assert "best feasible alternative" in text


def test_instruction_requires_optionality_survival_reasoning():
    text = instruction().lower()
    assert "optionality" in text


def test_instruction_forbids_manufactured_trades():
    text = instruction().lower()
    assert "never manufacture trades" in text


def test_stagnation_redirects_to_search_process_never_forced_trading():
    text = instruction().lower()
    assert "reconsider the search process" in text
    assert "never force" in text or "not forced" in text


def test_instruction_permits_broadening_discovery_dimensions():
    text = instruction().lower()
    for dimension in (
        "instruments",
        "asset classes",
        "strategies",
        "horizons",
        "regions",
        "sessions",
    ):
        assert dimension in text


def test_mandate_contains_no_quantitative_activity_targets():
    payload_text = json.dumps(mandate()).lower()
    for forbidden in (
        "minimum trades",
        "min_trades",
        "trade quota",
        "minimum exposure",
        "min_exposure",
        "fixed exposure",
        "mandatory scanner",
        "required symbols",
        "symbols per",
        "trades per day",
    ):
        assert forbidden not in payload_text, forbidden


def test_no_new_numeric_activity_targets_across_autonomous_modules():
    combined = "\n".join(
        (REPO / path).read_text(encoding="utf-8")
        for path in (
            "ibkr_paper_30d/autonomous_research.py",
            "ibkr_paper_30d/autonomous_runtime.py",
            "ibkr_paper_30d/autonomous_service.py",
            "ibkr_paper_30d/ibkr_research_tools.py",
        )
    )
    for forbidden in (
        "min_trades",
        "min_exposure",
        "trade_quota",
        "mandatory_scanner",
        "minimum_research",
        "required_symbols",
    ):
        assert forbidden not in combined, forbidden


def test_mandate_preserves_existing_native_freedom_fields():
    m = mandate()
    assert m["predefined_symbol_universe"] is False
    assert m["predefined_strategy_family"] is False
    assert m["predefined_timeframe"] is False
    assert m["broker_and_account_permissions_are_authoritative"] is True
    assert m["capital_can_be_fully_lost"] is True
    assert m["fixed_percent_risk_limits"] is False
    assert "trader_style" not in m