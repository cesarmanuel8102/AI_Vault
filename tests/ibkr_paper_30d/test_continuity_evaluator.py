from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_evaluator import (
    ContinuityEvaluationError,
    ContinuityEvaluator,
    ContinuityFactCollector,
    evaluate_condition,
    evaluate_value,
)
from ibkr_paper_30d.continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityCondition,
    ContinuityFactEvidence,
    ContinuityFactName,
    ContinuityFactSnapshot,
    ContinuityValueExpression,
    ExpiryAuthorityMode,
)
from ibkr_paper_30d.provider_lifecycle import BrokerTimeEvidence


UTC = timezone.utc
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


def _predicate(fact: str, comparator: str, value, age: int = 30) -> dict:
    return {
        "operator": "PREDICATE", "fact": fact, "comparator": comparator,
        "value": value, "max_age_seconds": age,
    }


def _state_actions(action: str = "RETAIN") -> dict:
    return {
        state: {"action_type": action}
        for state in (
            "UNFILLED", "PARTIALLY_FILLED", "FILLED", "PENDING_CANCEL",
            "CANCELLED", "REJECTED", "ABSENT",
        )
    }


def _plan(**changes) -> CodexOrderContinuityPlan:
    payload = {
        "schema": "CODEX_ORDER_CONTINUITY_PLAN_V1", "plan_id": "plan-1",
        "plan_version": 1, "created_at_utc": NOW, "created_by_model": "gpt-5.6-sol",
        "model_attestation_sha256": H1, "decision_cycle_id": "cycle-1",
        "invocation_id": "inv-1", "input_bundle_sha256": H2,
        "epoch_id": "AUTONOMY_EPOCH_2", "definition_sha256": H3,
        "clock_event_sha256": H1, "owner_authorization_sha256": H2,
        "predecessor_plan_sha256": None,
        "order_binding": {
            "binding_type": "EXISTING_ORDER", "account_identity_sha256": H1,
            "order_ref": "order-78", "client_order_id": "client-78",
            "ibkr_order_id": 78, "perm_id": 225256222, "execution_client_id": 17,
            "contract_identity_sha256": H2, "action": "BUY", "order_type": "LMT",
            "original_total_quantity": "1", "original_limit_price": "4.90",
            "original_tif": "DAY", "original_good_till_date_utc": None,
            "original_order_state_sha256": H3, "original_intent_sha256": H1,
            "proposal_sha256": None,
        },
        "maximum_authorized_liability": "500", "valid_from_utc": NOW,
        "plan_valid_until": NOW + timedelta(hours=6),
        "session_end_utc": NOW + timedelta(hours=6),
        "epoch_authority_end_utc": NOW + timedelta(days=1),
        "authority_activation_condition": _predicate(
            "PROVIDER_STATE", "EQ", "TIMEOUT_CONFIRMED"
        ),
        "expiry_authority_mode": "WHEN_CONTINUITY_ACTIVE",
        "terminal_disposition": {"action_type": "CANCEL"},
        "contingencies": [
            {
                "contingency_id": "second", "priority": 20,
                "valid_from_utc": NOW, "valid_until_utc": NOW + timedelta(hours=6),
                "condition": _predicate("ORDER_MARK", "LE", "4.50"),
                "state_actions": _state_actions("CANCEL"),
                "unavailable_data_action": {"action_type": "REQUIRES_AGENT", "interim_action": {"action_type": "RETAIN"}},
                "maximum_execution_count": 1, "expectations": ["mark may fall"],
                "why_i_chose_this_contingency": "Cancel at my selected mark.",
            },
            {
                "contingency_id": "first", "priority": 10,
                "valid_from_utc": NOW, "valid_until_utc": NOW + timedelta(hours=6),
                "condition": _predicate("ORDER_REMAINING_QUANTITY", "GT", "0"),
                "state_actions": _state_actions("RETAIN"),
                "unavailable_data_action": {"action_type": "CANCEL"},
                "maximum_execution_count": 2, "expectations": ["remainder may persist"],
                "why_i_chose_this_contingency": "Retain my selected resting order.",
            },
        ],
    }
    payload.update(changes)
    if payload["plan_valid_until"] < NOW:
        payload["created_at_utc"] = payload["plan_valid_until"] - timedelta(hours=2)
        payload["valid_from_utc"] = payload["plan_valid_until"] - timedelta(hours=1)
        payload["session_end_utc"] = payload["plan_valid_until"]
        for contingency in payload["contingencies"]:
            contingency["valid_from_utc"] = payload["valid_from_utc"]
            contingency["valid_until_utc"] = payload["plan_valid_until"]
    return CodexOrderContinuityPlan.model_validate(payload)


def _fact(name: str, value, *, age_seconds: int = 0, max_age: int = 30) -> ContinuityFactEvidence:
    body = {
        "fact": name, "source": "PAPER_BROKER", "collected_at_utc": (NOW - timedelta(seconds=age_seconds)).isoformat(),
        "max_age_seconds": str(max_age), "canonical_value": value,
    }
    return ContinuityFactEvidence(
        fact=name, source="PAPER_BROKER",
        collected_at_utc=NOW - timedelta(seconds=age_seconds), max_age_seconds=max_age,
        canonical_value=value, evidence_sha256=sha256_json(body),
    )


def _snapshot(**values) -> ContinuityFactSnapshot:
    defaults = {
        "PROVIDER_STATE": "TIMEOUT_CONFIRMED", "MODEL_INVOCATION_IN_FLIGHT": False,
        "ORDER_STATUS": "UNFILLED", "ORDER_REMAINING_QUANTITY": "1",
        "ORDER_MARK": "4.25", "UNDERLYING_VOLUME": "1200000",
        "POSITION_QUANTITY": "0", "EXPERIMENT_EQUITY": "500",
        "MARKET_SESSION_STATE": "REGULAR",
        "ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS": "180",
    }
    defaults.update(values)
    facts = tuple(_fact(name, value) for name, value in defaults.items())
    return ContinuityFactSnapshot(
        snapshot_id="snapshot-1", collected_at_utc=NOW, broker_time_utc=NOW,
        facts=facts, evidence_sha256=sha256_json([item.model_dump(mode="json") for item in facts]),
    )


@pytest.mark.parametrize(
    ("comparator", "value", "expected"),
    [
        ("EQ", "4.25", True), ("NE", "4.00", True), ("LT", "5", True),
        ("LE", "4.25", True), ("GT", "4", True), ("GE", "4.25", True),
        ("BETWEEN", ["4", "5"], True), ("IN", ["4.00", "4.25"], True),
    ],
)
def test_condition_comparisons(comparator, value, expected) -> None:
    condition = ContinuityCondition.model_validate(
        _predicate("ORDER_MARK", comparator, value)
    )
    assert evaluate_condition(condition, _snapshot()) is expected


def test_elapsed_boolean_nesting_and_missing_fact_three_valued_logic() -> None:
    condition = ContinuityCondition.model_validate(
        {
            "operator": "ALL",
            "children": [
                _predicate("ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS", "GE", "120"),
                {"operator": "NOT", "children": [_predicate("POSITION_EXISTS", "EQ", True)]},
            ],
        }
    )
    assert evaluate_condition(condition, _snapshot(POSITION_EXISTS=False)) is True
    assert evaluate_condition(condition, _snapshot()) is None


def test_numeric_expression_supports_prices_volume_equity_and_tick_rounding() -> None:
    expression = ContinuityValueExpression.model_validate(
        {
            "operator": "ROUND_TO_TICK", "tick_size": "0.05",
            "operands": [{
                "operator": "ADD", "operands": [
                    {"operator": "FACT", "fact": "ORDER_MARK"},
                    {"operator": "LITERAL", "literal": "0.03"},
                ],
            }],
        }
    )
    assert evaluate_value(expression, _snapshot()) == Decimal("4.30")
    for fact in ("UNDERLYING_VOLUME", "EXPERIMENT_EQUITY", "POSITION_QUANTITY"):
        assert evaluate_value(
            ContinuityValueExpression.model_validate({"operator": "FACT", "fact": fact}),
            _snapshot(),
        ).is_finite()


def test_priority_and_finite_execution_count_are_deterministic() -> None:
    plan = _plan()
    evaluation = ContinuityEvaluator().evaluate(plan, _snapshot())
    assert evaluation.selected_contingency_id == "first"
    assert evaluation.selected_action.action_type.value == "RETAIN"

    exhausted = ContinuityEvaluator(execution_counts={"first": 2}).evaluate(plan, _snapshot())
    assert exhausted.selected_contingency_id == "second"
    assert exhausted.selected_action.action_type.value == "CANCEL"


def test_in_flight_invocation_blocks_unless_model_condition_activates_it() -> None:
    ordinary = ContinuityEvaluator().evaluate(
        _plan(), _snapshot(PROVIDER_STATE="IN_FLIGHT", MODEL_INVOCATION_IN_FLIGHT=True)
    )
    assert ordinary.authority_active is False
    assert ordinary.selected_action is None

    explicit = _plan(
        authority_activation_condition=_predicate(
            "MODEL_INVOCATION_IN_FLIGHT", "EQ", True
        )
    )
    activated = ContinuityEvaluator().evaluate(
        explicit, _snapshot(PROVIDER_STATE="IN_FLIGHT", MODEL_INVOCATION_IN_FLIGHT=True)
    )
    assert activated.authority_active is True
    assert activated.selected_action is not None


def test_expiry_modes_preserve_model_selected_authority() -> None:
    facts = _snapshot(PROVIDER_STATE="COMPLETED_ACCEPTED")
    expired_when_active = _plan(plan_valid_until=NOW - timedelta(seconds=1))
    blocked = ContinuityEvaluator().evaluate(expired_when_active, facts)
    assert blocked.selected_action is None

    expired_always = expired_when_active.model_copy(
        update={"expiry_authority_mode": ExpiryAuthorityMode.ALWAYS_AT_EXPIRY}
    )
    executed = ContinuityEvaluator().evaluate(expired_always, facts)
    assert executed.selected_action.action_type.value == "CANCEL"


def test_missing_or_stale_required_fact_uses_only_authored_unavailable_branch() -> None:
    stale = _snapshot()
    stale_fact = _fact("ORDER_REMAINING_QUANTITY", "1", age_seconds=60, max_age=30)
    stale = stale.model_copy(update={
        "facts": tuple(item for item in stale.facts if item.fact != ContinuityFactName.ORDER_REMAINING_QUANTITY) + (stale_fact,)
    })
    evaluation = ContinuityEvaluator().evaluate(_plan(), stale)
    assert evaluation.selected_contingency_id == "first"
    assert evaluation.selected_action.action_type.value == "CANCEL"
    assert "EVIDENCE_UNAVAILABLE" in evaluation.reason_codes


def test_stale_quote_and_tampered_evidence_are_unavailable_not_host_interpreted() -> None:
    stale_quote = _fact("ORDER_MARK", "4.25", age_seconds=60, max_age=10)
    facts = _snapshot()
    items = tuple(
        item for item in facts.facts if item.fact != ContinuityFactName.ORDER_MARK
    ) + (stale_quote,)
    facts = facts.model_copy(
        update={
            "facts": items,
            "evidence_sha256": sha256_json(
                [item.model_dump(mode="json") for item in items]
            ),
        }
    )
    condition = ContinuityCondition.model_validate(_predicate("ORDER_MARK", "LE", "4.50"))
    assert evaluate_condition(condition, facts) is None

    tampered = stale_quote.model_copy(
        update={"collected_at_utc": NOW, "evidence_sha256": H1}
    )
    tampered_items = tuple(
        item for item in facts.facts if item.fact != ContinuityFactName.ORDER_MARK
    ) + (tampered,)
    tampered_snapshot = facts.model_copy(
        update={
            "facts": tampered_items,
            "evidence_sha256": sha256_json(
                [item.model_dump(mode="json") for item in tampered_items]
            ),
        }
    )
    assert evaluate_condition(condition, tampered_snapshot) is None


def test_duplicate_contingency_priority_is_rejected_before_evaluation() -> None:
    payload = _plan().model_dump(mode="json")
    payload["contingencies"][1]["priority"] = payload["contingencies"][0]["priority"]
    with pytest.raises(ValidationError, match="priorities"):
        CodexOrderContinuityPlan.model_validate(payload)


def test_narrative_and_expectations_do_not_change_selected_action() -> None:
    first = _plan()
    payload = first.model_dump(mode="json")
    payload["contingencies"][1]["expectations"] = ["completely different narrative"]
    payload["contingencies"][1]["why_i_chose_this_contingency"] = "New prose only."
    second = CodexOrderContinuityPlan.model_validate(payload)
    left = ContinuityEvaluator().evaluate(first, _snapshot())
    right = ContinuityEvaluator().evaluate(second, _snapshot())
    assert left.selected_action == right.selected_action
    assert left.selected_contingency_id == right.selected_contingency_id
    assert left.action_sha256 == right.action_sha256


class FakeStore:
    def latest_provider_projection(self):
        return {"state": "TIMEOUT_CONFIRMED", "payload": {"broker_time_utc": NOW.isoformat()}}


class ConflictingStore:
    def latest_provider_projection(self):
        return {"state": "IN_FLIGHT", "payload": {"failure_code": "PROVIDER_TIMEOUT"}}


class FakeBroker:
    environment = "PAPER"
    account_identity_sha256 = H1
    all_order_visibility = True

    def collect_continuity_facts(self, binding, broker_time_utc):
        return {
            "ORDER_STATUS": {"value": "UNFILLED", "collected_at_utc": NOW, "source": "PAPER_ALL_OPEN_ORDERS", "max_age_seconds": 10},
            "ORDER_REMAINING_QUANTITY": {"value": "1", "collected_at_utc": NOW, "source": "PAPER_ALL_OPEN_ORDERS", "max_age_seconds": 10},
            "ORDER_MARK": {"value": "4.25", "collected_at_utc": NOW, "source": "PAPER_MARKET_DATA", "max_age_seconds": 10},
        }


class FakeLedger:
    def project(self):
        return {"cash": "500", "equity": "500"}


class FakeClock:
    def state(self):
        return "RUNNING"


def test_collector_hashes_every_fact_and_requires_paper_time_and_all_order_visibility() -> None:
    collector = ContinuityFactCollector(FakeStore(), FakeBroker(), FakeLedger(), FakeClock())
    evidence = BrokerTimeEvidence.create_authenticated_paper(
        time_utc=NOW,
        observed_at_utc=NOW,
        account_identity_sha256=H1,
    )
    snapshot = collector.collect(_plan(), broker_time_utc=evidence)
    assert snapshot.facts
    assert all(item.source and item.max_age_seconds > 0 and item.evidence_sha256 for item in snapshot.facts)
    assert all(item.collected_at_utc.tzinfo is not None for item in snapshot.facts)

    with pytest.raises(ContinuityEvaluationError, match="PAPER"):
        collector.collect(
            _plan(), broker_time_utc=evidence.model_copy(update={"environment": "LIVE"})
        )
    with pytest.raises(ContinuityEvaluationError, match="PAPER"):
        collector.collect(_plan(), broker_time_utc=None)
    bad_broker = FakeBroker()
    bad_broker.all_order_visibility = False
    with pytest.raises(ContinuityEvaluationError, match="ALL_ORDER_VISIBILITY"):
        ContinuityFactCollector(FakeStore(), bad_broker, FakeLedger(), FakeClock()).collect(
            _plan(), broker_time_utc=evidence
        )
    with pytest.raises(ContinuityEvaluationError, match="PROVIDER_STATE_CONFLICT"):
        ContinuityFactCollector(
            ConflictingStore(), FakeBroker(), FakeLedger(), FakeClock()
        ).collect(_plan(), broker_time_utc=evidence)


def test_collector_uses_latest_provider_invocation_not_plan_authoring_invocation() -> None:
    class Store:
        def provider_projection(self, invocation_id):
            raise AssertionError("the authoring invocation is not current provider state")

        def latest_provider_projection(self):
            return {
                "invocation_id": "invocation-current",
                "state": "TIMEOUT_CONFIRMED",
                "payload": {
                    "broker_time_utc": NOW.isoformat(),
                    "failure_code": "PROVIDER_TIMEOUT",
                },
            }

    evidence = BrokerTimeEvidence.create_authenticated_paper(
        time_utc=NOW,
        observed_at_utc=NOW,
        account_identity_sha256=H1,
    )
    snapshot = ContinuityFactCollector(
        Store(), FakeBroker(), FakeLedger(), FakeClock()
    ).collect(_plan(), broker_time_utc=evidence)
    values = {item.fact.value: item.canonical_value for item in snapshot.facts}

    assert values["PROVIDER_STATE"] == "TIMEOUT_CONFIRMED"
    assert values["MODEL_INVOCATION_IN_FLIGHT"] is False


def test_evaluator_source_contains_no_host_trading_policy_constants() -> None:
    source = Path("ibkr_paper_30d/continuity_evaluator.py").read_text(encoding="utf-8")
    forbidden = ("cancel_after_minutes", "repricing_percentage", "universal_timeout", "defensive_modify")
    assert not any(token in source.lower() for token in forbidden)
