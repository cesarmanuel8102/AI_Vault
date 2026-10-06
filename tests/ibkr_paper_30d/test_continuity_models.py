from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ibkr_paper_30d.continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityActionType,
    ContinuityCondition,
    ContinuityFactName,
    ContinuityOrderBinding,
    ContinuityOrderState,
    ContinuityValueExpression,
    ExpiryAuthorityMode,
)


UTC = timezone.utc
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _condition(
    fact: str = "PROVIDER_STATE",
    comparator: str = "EQ",
    value: object = "TIMEOUT_CONFIRMED",
) -> dict[str, object]:
    return {
        "operator": "PREDICATE",
        "fact": fact,
        "comparator": comparator,
        "value": value,
        "max_age_seconds": 15,
    }


def _action(action_type: str = "RETAIN", **changes: object) -> dict[str, object]:
    return {"action_type": action_type, **changes}


def _state_actions(action: dict[str, object] | None = None) -> dict[str, object]:
    exact = action or _action()
    return {
        state.value: deepcopy(exact)
        for state in ContinuityOrderState
        if state != ContinuityOrderState.EVIDENCE_UNAVAILABLE
    }


def _valid_plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "CODEX_ORDER_CONTINUITY_PLAN_V1",
        "plan_id": "continuity-plan-1",
        "plan_version": 1,
        "created_at_utc": NOW,
        "created_by_model": "gpt-5-codex",
        "model_attestation_sha256": HASH_A,
        "decision_cycle_id": "cycle-1",
        "invocation_id": "invocation-1",
        "input_bundle_sha256": HASH_B,
        "epoch_id": "AUTONOMY_EPOCH_2",
        "definition_sha256": HASH_C,
        "clock_event_sha256": HASH_A,
        "owner_authorization_sha256": HASH_B,
        "predecessor_plan_sha256": None,
        "order_binding": {
            "binding_type": "EXISTING_ORDER",
            "account_identity_sha256": HASH_A,
            "order_ref": "codex-ibkr-paper-30d-a-000000000001",
            "client_order_id": "codex-order-1",
            "ibkr_order_id": 78,
            "perm_id": 225256222,
            "execution_client_id": 17,
            "contract_identity_sha256": HASH_B,
            "action": "BUY",
            "order_type": "LMT",
            "original_total_quantity": "1",
            "original_limit_price": "4.90",
            "original_tif": "DAY",
            "original_good_till_date_utc": None,
            "original_order_state_sha256": HASH_C,
            "original_intent_sha256": HASH_A,
            "proposal_sha256": None,
        },
        "maximum_authorized_liability": "500",
        "valid_from_utc": NOW,
        "plan_valid_until": NOW + timedelta(hours=6),
        "session_end_utc": NOW + timedelta(hours=6),
        "epoch_authority_end_utc": NOW + timedelta(days=1),
        "authority_activation_condition": _condition(),
        "expiry_authority_mode": "WHEN_CONTINUITY_ACTIVE",
        "terminal_disposition": _action("CANCEL"),
        "contingencies": [
            {
                "contingency_id": "provider-outage",
                "priority": 10,
                "valid_from_utc": NOW,
                "valid_until_utc": NOW + timedelta(minutes=30),
                "condition": _condition(),
                "state_actions": _state_actions(),
                "unavailable_data_action": _action("REQUIRES_AGENT", interim_action=_action("RETAIN")),
                "maximum_execution_count": 1,
                "expectations": ["The resting order may remain unfilled."],
                "why_i_chose_this_contingency": "Preserve my exact resting-order intent during a provider outage.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_accepts_distinct_retain_cancel_and_modify_plans() -> None:
    retain = CodexOrderContinuityPlan.model_validate(_valid_plan())

    cancel_payload = _valid_plan()
    cancel_payload["contingencies"][0]["state_actions"] = _state_actions(_action("CANCEL"))  # type: ignore[index]
    cancel = CodexOrderContinuityPlan.model_validate(cancel_payload)

    modify_payload = _valid_plan()
    modify_payload["contingencies"][0]["state_actions"] = _state_actions(  # type: ignore[index]
        _action(
            "MODIFY_EXISTING_ORDER",
            new_total_quantity={"operator": "LITERAL", "literal": "1"},
            new_limit_price={"operator": "LITERAL", "literal": "4.50"},
            new_tif="DAY",
        )
    )
    modify = CodexOrderContinuityPlan.model_validate(modify_payload)

    assert retain.schema == "CODEX_ORDER_CONTINUITY_PLAN_V1"
    assert {retain.sha256, cancel.sha256, modify.sha256} == {
        retain.sha256,
        cancel.sha256,
        modify.sha256,
    }
    assert len({retain.sha256, cancel.sha256, modify.sha256}) == 3


def test_accepts_provider_failure_decision_age_and_in_flight_activation_conditions() -> None:
    conditions = [
        _condition(),
        _condition("ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS", "GE", "120"),
        _condition("MODEL_INVOCATION_IN_FLIGHT", "EQ", True),
    ]

    plans = [
        CodexOrderContinuityPlan.model_validate(
            _valid_plan(authority_activation_condition=condition)
        )
        for condition in conditions
    ]

    assert len({plan.sha256 for plan in plans}) == 3


def test_accepts_both_expiry_authority_modes() -> None:
    active = CodexOrderContinuityPlan.model_validate(
        _valid_plan(expiry_authority_mode="WHEN_CONTINUITY_ACTIVE")
    )
    always = CodexOrderContinuityPlan.model_validate(
        _valid_plan(expiry_authority_mode="ALWAYS_AT_EXPIRY")
    )

    assert active.expiry_authority_mode == ExpiryAuthorityMode.WHEN_CONTINUITY_ACTIVE
    assert always.expiry_authority_mode == ExpiryAuthorityMode.ALWAYS_AT_EXPIRY
    assert active.sha256 != always.sha256


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.pop("plan_valid_until"),
        lambda p: p.pop("terminal_disposition"),
        lambda p: p["contingencies"][0].pop("unavailable_data_action"),
        lambda p: p["contingencies"][0]["state_actions"].pop("PARTIALLY_FILLED"),
        lambda p: p.pop("input_bundle_sha256"),
        lambda p: p.pop("authority_activation_condition"),
        lambda p: p.pop("expiry_authority_mode"),
        lambda p: p["contingencies"][0].pop("maximum_execution_count"),
    ],
    ids=[
        "validity",
        "terminal-disposition",
        "unavailable-data",
        "partial-fill",
        "provenance",
        "activation",
        "expiry-mode",
        "execution-count",
    ],
)
def test_rejects_incomplete_plan_structure(mutation) -> None:
    payload = _valid_plan()
    mutation(payload)

    with pytest.raises(ValidationError):
        CodexOrderContinuityPlan.model_validate(payload)


@pytest.mark.parametrize(
    "fact",
    ["SHELL_COMMAND", "SQL_QUERY", "NETWORK_REQUEST", "PYTHON_CODE", "MODEL_PROMPT"],
)
def test_rejects_arbitrary_execution_facts(fact: str) -> None:
    with pytest.raises(ValidationError):
        ContinuityCondition.model_validate(_condition(fact))


def test_rejects_qualitative_predicates() -> None:
    with pytest.raises(ValidationError):
        ContinuityCondition.model_validate(_condition(comparator="LOOKS_BAD"))


def test_rejects_cyclic_or_over_depth_expressions() -> None:
    cycle: dict[str, object] = {"operator": "ALL", "children": []}
    cycle["children"] = [cycle]
    with pytest.raises((ValidationError, ValueError, RecursionError)):
        ContinuityCondition.model_validate(cycle)

    nested: dict[str, object] = _condition("ORDER_REMAINING_QUANTITY", "GT", "0")
    for _ in range(10):
        nested = {"operator": "NOT", "children": [nested]}
    with pytest.raises(ValidationError, match="depth"):
        ContinuityCondition.model_validate(nested)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_rejects_non_finite_decimals(value: str) -> None:
    with pytest.raises(ValidationError):
        ContinuityValueExpression.model_validate({"operator": "LITERAL", "literal": value})


def test_rejects_unbounded_action_values() -> None:
    payload = _valid_plan()
    payload["contingencies"][0]["state_actions"] = _state_actions(  # type: ignore[index]
        _action(
            "MODIFY_EXISTING_ORDER",
            new_limit_price={"operator": "FACT", "fact": "ORDER_ASK"},
            new_total_quantity={"operator": "LITERAL", "literal": "1000000001"},
            new_tif="DAY",
        )
    )

    with pytest.raises(ValidationError):
        CodexOrderContinuityPlan.model_validate(payload)


def test_rejects_plan_bound_below_authoritative_original_liability() -> None:
    payload = _valid_plan(maximum_authorized_liability="350")
    payload["order_binding"]["original_maximum_liability"] = "353.82"  # type: ignore[index]

    with pytest.raises(ValidationError, match="original maximum liability"):
        CodexOrderContinuityPlan.model_validate(payload)


def test_accepts_plan_bound_at_authoritative_original_liability() -> None:
    payload = _valid_plan(maximum_authorized_liability="353.82")
    payload["order_binding"]["original_maximum_liability"] = "353.82"  # type: ignore[index]

    plan = CodexOrderContinuityPlan.model_validate(payload)

    assert plan.maximum_authorized_liability == Decimal("353.82")


def test_dynamic_modify_expression_does_not_invent_a_liability_formula() -> None:
    payload = _valid_plan(maximum_authorized_liability="500")
    payload["contingencies"][0]["state_actions"] = _state_actions(  # type: ignore[index]
        _action(
            "MODIFY_EXISTING_ORDER",
            new_total_quantity={"operator": "FACT", "fact": "ORDER_REMAINING_QUANTITY"},
            new_limit_price={"operator": "FACT", "fact": "ORDER_MARK"},
        )
    )

    plan = CodexOrderContinuityPlan.model_validate(payload)

    assert plan.maximum_authorized_liability == Decimal("500")


def test_requires_agent_needs_exact_interim_disposition() -> None:
    payload = _valid_plan(terminal_disposition=_action("REQUIRES_AGENT"))

    with pytest.raises(ValidationError, match="interim"):
        CodexOrderContinuityPlan.model_validate(payload)


def test_existing_order_binding_requires_exact_immutable_identity() -> None:
    payload = _valid_plan()
    del payload["order_binding"]["contract_identity_sha256"]  # type: ignore[index]

    with pytest.raises(ValidationError):
        CodexOrderContinuityPlan.model_validate(payload)


def test_new_order_binding_requires_proposal_hash() -> None:
    existing = _valid_plan()["order_binding"]
    new_order = {
        **existing,
        "binding_type": "NEW_PROPOSAL",
        "proposal_sha256": None,
        "ibkr_order_id": None,
        "perm_id": None,
        "original_order_state_sha256": None,
    }

    with pytest.raises(ValidationError, match="proposal_sha256"):
        ContinuityOrderBinding.model_validate(new_order)


def test_new_order_binding_requires_one_identical_intent_hash() -> None:
    existing = _valid_plan()["order_binding"]
    new_order = {
        **existing,
        "binding_type": "NEW_PROPOSAL",
        "proposal_sha256": HASH_B,
        "original_intent_sha256": HASH_C,
        "ibkr_order_id": None,
        "perm_id": None,
        "original_order_state_sha256": None,
    }

    with pytest.raises(ValidationError, match="must equal proposal_sha256"):
        ContinuityOrderBinding.model_validate(new_order)


@pytest.mark.parametrize(
    ("tif", "good_till"),
    [("GTD", None), ("DAY", NOW + timedelta(hours=1))],
)
def test_rejects_inconsistent_good_till_timestamp(tif: str, good_till: datetime | None) -> None:
    payload = _valid_plan()
    payload["contingencies"][0]["state_actions"] = _state_actions(  # type: ignore[index]
        _action(
            "MODIFY_EXISTING_ORDER",
            new_limit_price={"operator": "LITERAL", "literal": "4.50"},
            new_tif=tif,
            new_good_till_date_utc=good_till,
        )
    )

    with pytest.raises(ValidationError):
        CodexOrderContinuityPlan.model_validate(payload)


def test_tif_may_outlive_plan_only_with_exact_retention_disposition() -> None:
    order_expiry = NOW + timedelta(hours=2)
    retained = _valid_plan(
        plan_valid_until=NOW + timedelta(minutes=30),
        terminal_disposition=_action(
            "RETAIN", retain_authority="RETAIN_UNTIL_ORDER_TIF"
        )
    )
    retained["order_binding"].update(  # type: ignore[union-attr]
        original_tif="GTD", original_good_till_date_utc=order_expiry
    )
    plan = CodexOrderContinuityPlan.model_validate(retained)
    assert plan.order_binding.original_good_till_date_utc == order_expiry

    without_authority = deepcopy(retained)
    without_authority["terminal_disposition"] = _action("RETAIN")
    with pytest.raises(ValidationError, match="RETAIN_UNTIL_ORDER_TIF"):
        CodexOrderContinuityPlan.model_validate(without_authority)


def test_rejects_tif_beyond_epoch_authority() -> None:
    payload = _valid_plan(
        plan_valid_until=NOW + timedelta(minutes=30),
        terminal_disposition=_action(
            "RETAIN", retain_authority="RETAIN_UNTIL_ORDER_TIF"
        )
    )
    payload["order_binding"].update(  # type: ignore[union-attr]
        original_tif="GTD",
        original_good_till_date_utc=NOW + timedelta(days=2),
    )

    with pytest.raises(ValidationError, match="epoch"):
        CodexOrderContinuityPlan.model_validate(payload)


def test_fact_enum_contains_runtime_activation_inputs() -> None:
    assert ContinuityFactName.PROVIDER_STATE.value == "PROVIDER_STATE"
    assert ContinuityFactName.MODEL_INVOCATION_IN_FLIGHT.value == "MODEL_INVOCATION_IN_FLIGHT"
    assert ContinuityActionType.REQUIRES_AGENT.value == "REQUIRES_AGENT"
