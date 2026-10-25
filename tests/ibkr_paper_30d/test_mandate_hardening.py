"""Mandate invariants for the AUTONOMY_EPOCH_1 charter.

The pre-epoch mandate tests pinned strategic prescription (counterfactual
ritual, per-cycle active-search duty, conditional NO_TRADE validity).
The Epoch-1 charter intentionally removes those prescriptions; these
tests now pin the charter's guarantees: the hard boundaries, the
objective, freedom fields, and the absence of forced action.
"""

from __future__ import annotations

import json
from pathlib import Path

from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle


REPO = Path(__file__).resolve().parents[2]


def bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-mandate-epoch1",
        utc_timestamp="2026-09-25T22:00:00Z",
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
        invocation_id="inv-mandate-epoch1",
        utc_timestamp="2026-09-25T22:00:01Z",
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
    assert mandate()["objective"].startswith("Maximize terminal experimental")
    assert "PAPER equity" in mandate()["objective"]
    assert "30-day" not in mandate()["objective"]


def test_no_trade_remains_valid():
    m = mandate()
    assert m["no_trade_is_allowed"] is True
    assert m["no_trade_remains_valid"] is True


def test_activity_narratives_are_explicitly_not_success():
    m = mandate()
    assert m["trading_frequency_is_not_success"] is True
    assert m["inactivity_is_not_success"] is True
    assert m["cash_preservation_is_not_success_by_itself"] is True
    assert m["risk_taking_is_not_success_by_itself"] is True


def test_avoidable_opportunity_cost_is_failure():
    assert mandate()["avoidable_opportunity_cost_is_failure"] is True


def test_scarcity_and_optionality_are_part_of_expected_terminal_equity_reasoning():
    m = mandate()
    assert m["capital_and_remaining_time_are_scarce"] is True
    assert m["destroying_optionality_can_reduce_expected_terminal_equity"] is True
    assert m[
        "failing_to_exploit_superior_positive_expectancy_opportunity_can_reduce_expected_terminal_equity"
    ] is True


def test_terminal_equity_stretch_benchmark_is_aspirational_not_threshold_utility():
    benchmark = mandate()["terminal_equity_stretch_benchmark"]

    assert benchmark == {
        "kind": "ASPIRATIONAL_NON_THRESHOLD",
        "per_sleeve_starting_allocation_usd": "500.00",
        "per_sleeve_terminal_target_usd": "1000.00",
        "aggregate_starting_allocation_usd": "1000.00",
        "aggregate_terminal_target_usd": "2000.00",
        "does_not_override_expected_value": True,
        "does_not_create_minimum_activity": True,
    }


def test_attention_policy_preserves_self_direction_while_preventing_local_stagnation():
    policy = mandate()["autonomous_attention_policy"]

    assert policy == {
        "optimize_each_sleeve_and_aggregate": True,
        "position_management_does_not_suspend_other_sleeve_discovery": True,
        "research_cadence": "MODEL_SELECTED_BY_EXPECTED_INFORMATION_VALUE",
        "no_opportunity_claims_require_sufficiently_recent_evidence": True,
        "track_idle_capital_opportunity_cost": True,
        "adapt_methodology_when_trajectory_is_insufficient": True,
    }

    text = instruction().lower()
    assert "aspirational benchmark" in text
    assert "must not sacrifice expected terminal equity" in text
    assert "does not suspend responsibility for the other sleeve" in text
    assert "you choose the cadence" in text
    assert "fresh replacement proposal" in text
    assert "active search for superior opportunities every cycle" not in text


def test_immutable_constraints_are_environmental_not_strategic():
    m = mandate()
    assert isinstance(m["immutable_environmental_constraints"], list)
    assert m["may_not_modify_boundaries_to_improve_objective"] is True
    constraints = " ".join(m["immutable_environmental_constraints"]).lower()
    assert "live execution prohibited" in constraints
    assert "paper account only" in constraints


def test_persistence_toward_objective_without_per_cycle_duty():
    text = instruction().lower()
    assert "if your current process is not producing useful progress" in text
    assert "replace an ineffective methodology" in text
    # The old per-cycle "active search" duty is gone.
    assert "active search for superior opportunities every cycle" not in text


def test_counterfactual_ritual_is_retired():
    text = instruction().lower()
    assert "counterfactual challenge" not in text
    assert "before concluding no_trade" not in text


def test_optionality_reasoning_is_expected_value_not_risk_limit():
    text = json.dumps(mandate()).lower()
    assert "destroying_optionality_can_reduce_expected_terminal_equity" in text


def test_no_forced_trades_and_no_manufactured_activity():
    text = instruction().lower()
    assert "do not trade merely to demonstrate activity" in text
    assert "must trade" not in text
    assert "must take risk" not in text
    assert "must be aggressive" not in text


def test_stagnation_redirects_to_methodology_not_trading():
    text = instruction().lower()
    assert "diagnose the cause" in text
    assert "reconsider assumptions" in text
    assert "replace an ineffective methodology" in text


def test_position_reductions_use_their_exact_host_validator_not_new_trade_feasibility():
    text = instruction().lower()

    assert "broker_feasibility is the research validator for new trade proposals" in text
    assert "close_position or reduce_position" in text
    assert "does not require a prior broker_feasibility research request" in text
    assert "the host performs an exact exposure-reducing broker validation" in text
    assert "missing or sentinel margin fields from a generic feasibility request" in text
    assert "do not prove that an exposure-reducing position action is unavailable" in text


def test_methodological_freedom_dimensions_are_open():
    text = instruction().lower()
    for freedom in (
        "what markets to investigate",
        "what strategies to formulate",
        "when to trade",
        "when not to trade",
        "what tools to build",
    ):
        assert freedom in text, freedom


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
    assert "maximum experiment liability" in m["only_external_capital_boundary"]
