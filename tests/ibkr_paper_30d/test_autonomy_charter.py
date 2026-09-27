"""AUTONOMY_EPOCH_1 charter tests.

These tests pin the new autonomy charter: methodological freedom, no
strategic prescription, NO_TRADE as a valid local decision, broad legal
research access, optional QuantConnect, self-tooling visibility, persistent
workspace, and research continuity — while the immutable execution
boundaries stay identical.

None of these tests invoke Codex. The prompt payload is built directly
from the provider's static prompt builder with fake request/bundle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibkr_paper_30d.autonomous_research import (
    AutonomousTradeProposal,
    CodexAutonomousCLIProvider,
)
from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle


REPO = Path(__file__).resolve().parents[2]


def bundle(**updates) -> TraderInputBundle:
    values = dict(
        decision_cycle_id="cycle-epoch1-charter-1",
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
    values.update(updates)
    return TraderInputBundle(**values)


def request(value: TraderInputBundle) -> InvocationRequest:
    return InvocationRequest(
        decision_cycle_id=value.decision_cycle_id,
        invocation_id="inv-epoch1-charter-1",
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


def charter(manifest=None, workspace=None):
    payload = CodexAutonomousCLIProvider._prompt_payload(
        request(bundle()),
        bundle(),
        [],
        manifest or [],
        workspace_context=workspace,
    )
    return payload


def instruction_text(payload):
    return payload["mandate"]["instruction"]


# ---------------------------------------------------------------------------
# 1-2. No predefined strategy, no predefined universe
# ---------------------------------------------------------------------------


def test_charter_has_no_predefined_strategy_or_universe():
    m = charter()["mandate"]
    assert m["predefined_symbol_universe"] is False
    assert m["predefined_strategy_family"] is False
    assert m["predefined_timeframe"] is False
    text = json.dumps(charter()).lower()
    for forbidden in (
        "momentum bias",
        "mean-reversion strategy",
        "preferred asset class",
        "catalyst is required",
        "scan movers",
        "top gainers",
    ):
        assert forbidden not in text, forbidden
    # The only mentions of setup/research sequence are negations of prescription.
    assert "required setup type, required research sequence" in text
    assert "there is no prescribed trading strategy" in text


def test_charter_objective_is_terminal_equity_and_horizon_neutral():
    m = charter()["mandate"]
    assert m["objective"].startswith("Maximize terminal experimental")
    assert "equity" in m["objective"]
    # Horizon must not hardcode the old 30-day wording.
    assert "30-day" not in m["objective"]


# ---------------------------------------------------------------------------
# 3. QuantConnect optional
# ---------------------------------------------------------------------------


def test_quantconnect_is_presented_as_optional_lab():
    payload = charter()
    text = json.dumps(payload).lower()
    assert "quantconnect" in text
    assert "you are not required to use quantconnect" in text
    # Must NOT prescribe its use.
    assert "you must use quantconnect" not in text
    assert "use quantconnect to" not in text


# ---------------------------------------------------------------------------
# 4. Self-tooling capability visible
# ---------------------------------------------------------------------------


def test_self_tooling_capability_is_visible_in_prompt():
    from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox

    class _Base:
        def manifest(self):
            return []

    workspace_root = REPO / "state" / "ibkr_paper_30d" / "autonomy_workspace"
    toolbox = AutonomyToolbox(_Base(), None)
    manifest = toolbox.manifest()
    payload = CodexAutonomousCLIProvider._prompt_payload(
        request(bundle()),
        bundle(),
        [],
        manifest,
    )
    names = [item["tool"] for item in payload["toolbox"]]
    assert "WORKSPACE" in names
    assert "RUN_RESEARCH_SCRIPT" in names
    assert "QUANTCONNECT" in names
    text = json.dumps(payload).lower()
    assert "persistent research workspace" in text


# ---------------------------------------------------------------------------
# 7. Persistent workspace context block
# ---------------------------------------------------------------------------


def test_workspace_context_is_passed_when_present():
    workspace = {
        "summary": "hypothesis H1 pending validation; NVDA vol study incomplete",
        "artifact_count": 4,
    }
    payload = charter(workspace=workspace)
    assert payload["workspace_context"] == workspace


def test_workspace_context_absent_when_none():
    payload = charter(workspace=None)
    assert "workspace_context" not in payload


# ---------------------------------------------------------------------------
# 8. Persistence toward the objective without forced action
# ---------------------------------------------------------------------------


def test_persistence_language_without_forced_trading():
    text = instruction_text(charter()).lower()
    assert "no_trade is a valid local decision whenever it is preferable" in text
    assert "do not trade merely to demonstrate activity" in text
    assert "reconsider assumptions" in text
    assert "replace an ineffective methodology" in text
    for forbidden in (
        "must trade",
        "must take risk",
        "must be aggressive",
        "never accept loss",
        "you are required to trade",
    ):
        assert forbidden not in text, forbidden


def test_counterfactual_ritual_is_no_longer_prescribed():
    text = instruction_text(charter()).lower()
    assert "counterfactual challenge" not in text
    assert "before concluding no_trade" not in text


def test_no_trade_validity_is_unconditional_as_local_decision():
    m = charter()["mandate"]
    assert m["no_trade_is_allowed"] is True
    assert m["no_trade_remains_valid"] is True
    text = instruction_text(charter()).lower()
    assert "no_trade is a valid local decision whenever it is preferable" in text
    # The old conditional-validity wording must be gone.
    assert "no_trade is valid only when" not in text


# ---------------------------------------------------------------------------
# 5. Broad legal research access
# ---------------------------------------------------------------------------


def test_broad_research_access_with_explicit_prohibitions():
    payload = charter()
    text = json.dumps(payload).lower()
    assert "legally permissible" in text
    assert "paid subscriptions" in text
    assert "financial costs" in text
    assert "expose credentials" in text


def test_immutable_boundaries_are_listed_as_environmental_constraints():
    m = charter()["mandate"]
    constraints = m["immutable_environmental_constraints"]
    for boundary in (
        "PAPER account only",
        "LIVE execution prohibited",
        "experimental capital boundary",
        "kill switch",
        "execution authorization",
        "audit integrity",
    ):
        assert any(boundary in item for item in constraints), boundary
    assert m["may_not_modify_boundaries_to_improve_objective"] is True


# ---------------------------------------------------------------------------
# 9. Research continuity
# ---------------------------------------------------------------------------


def test_research_continuity_capability_is_visible():
    text = json.dumps(charter()).lower()
    assert "persist the research objective" in text
    assert "resume" in text
    # It must be a capability, not a duty.
    assert "you must persist" not in text


# ---------------------------------------------------------------------------
# 22. Schema: strategy-prescriptive fields become optional
# ---------------------------------------------------------------------------


def test_proposal_catalyst_and_why_now_are_optional():
    base = dict(
        thesis="t",
        symbol="AAPL",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="MKT",
        capital_required="100",
        maximum_loss="100",
        loss_is_bounded=True,
        probability_profit="0.5",
        probability_loss="0.5",
        expected_gain="10",
        expected_loss="9",
        expected_value="0.5",
        expected_holding_period="1 day",
        entry_condition="e",
        invalidation_condition="i",
        exit_plan="x",
        alternatives_considered=[],
        evidence_used=[],
        disconfirming_evidence=[],
        confidence="0.6",
    )
    proposal = AutonomousTradeProposal(**base)
    assert proposal.catalyst is None
    assert proposal.why_now is None
    # And they remain valid when supplied.
    supplied = AutonomousTradeProposal(**{**base, "catalyst": "c", "why_now": "w"})
    assert supplied.catalyst == "c"


# ---------------------------------------------------------------------------
# 11/12 residual mandate fields
# ---------------------------------------------------------------------------


def test_mandate_keeps_hard_boundary_fields():
    m = charter()["mandate"]
    assert m["capital_can_be_fully_lost"] is True
    assert m["fixed_percent_risk_limits"] is False
    assert m["broker_and_account_permissions_are_authoritative"] is True
    assert "maximum experiment liability" in m["only_external_capital_boundary"]


def test_prompt_is_hashable_canonical_json():
    payload = charter()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) is not None