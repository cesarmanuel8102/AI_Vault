from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.broker_write_coordinator import BrokerCommandType
from ibkr_paper_30d.continuity_executor import (
    ContinuityCommandBuildError,
    ContinuityExecutor,
)
from ibkr_paper_30d.continuity_models import ContinuityEvaluation


NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def _evaluation(plan, action, *, ordinal=1):
    return ContinuityEvaluation(
        evaluation_id="evaluation-1",
        evaluated_at_utc=NOW,
        plan_id=plan.plan_id,
        plan_sha256=plan.sha256,
        fact_snapshot_sha256="8" * 64,
        authority_active=True,
        selected_contingency_id="outage",
        selected_action=action,
        execution_ordinal=ordinal,
        reason_codes=("CONTINGENCY_MATCHED",),
    )


def _binding(plan):
    return {
        "plan_id": plan.plan_id,
        "plan_sha256": plan.sha256,
        "order_ref": plan.order_binding.order_ref,
        "order_id": plan.order_binding.ibkr_order_id or 78,
        "perm_id": plan.order_binding.perm_id or 225256222,
        "execution_client_id": plan.order_binding.execution_client_id,
        "account_identity_sha256": plan.order_binding.account_identity_sha256,
        "contract_identity_sha256": plan.order_binding.contract_identity_sha256,
        "observed_state_sha256": plan.order_binding.original_order_state_sha256
        or "9" * 64,
        "current_total_quantity": "1",
        "current_limit_price": "4.90",
        "current_tif": "DAY",
        "current_good_till_date_utc": None,
        "current_maximum_liability": "353.82",
    }


def _executor(plan, *, gates=lambda authority_class: (), binding_updates=None):
    binding = _binding(plan)
    binding.update(binding_updates or {})
    return ContinuityExecutor(
        plan_reader=lambda plan_id: plan,
        active_binding_reader=lambda plan_id: binding,
        fact_values_reader=lambda digest: {
            "ORDER_TOTAL_QUANTITY": "1",
            "ORDER_MARK": "4.50",
        },
        fresh_gate_checker=gates,
    )


@pytest.mark.parametrize(
    ("action", "command_type"),
    [
        ({"action_type": "RETAIN"}, BrokerCommandType.RETAIN),
        ({"action_type": "CANCEL"}, BrokerCommandType.CANCEL),
    ],
)
def test_builds_exact_retain_and_cancel_commands(
    continuity_plan_factory, action, command_type
):
    plan = continuity_plan_factory()
    evaluation = _evaluation(plan, action)
    command = _executor(plan).build_command(evaluation)

    assert command.command_type == command_type
    assert command.plan_sha256 == plan.sha256
    assert command.order_ref == plan.order_binding.order_ref
    assert command.new_total_quantity is None
    assert command.new_limit_price is None


def test_modify_resolves_only_model_authored_expressions(continuity_plan_factory):
    plan = continuity_plan_factory()
    action = {
        "action_type": "MODIFY_EXISTING_ORDER",
        "new_total_quantity": {"operator": "LITERAL", "literal": "0.75"},
        "new_limit_price": {
            "operator": "ROUND_TO_TICK",
            "operands": [{"operator": "FACT", "fact": "ORDER_MARK"}],
            "tick_size": "0.05",
        },
        "new_tif": "GTD",
        "new_good_till_date_utc": "2026-10-01T19:30:00Z",
    }
    command = _executor(plan).build_command(_evaluation(plan, action))

    assert command.command_type == BrokerCommandType.MODIFY
    assert command.new_total_quantity == Decimal("0.75")
    assert command.new_limit_price == Decimal("4.50")
    assert command.new_tif == "GTD"
    assert command.new_good_till_date_utc == datetime(
        2026, 10, 1, 19, 30, tzinfo=timezone.utc
    )
    assert command.maximum_authorized_liability == plan.maximum_authorized_liability
    assert command.resolved_total_quantity == Decimal("0.75")
    assert command.resolved_limit_price == Decimal("4.50")
    assert command.liability_requirement.plan_sha256 == plan.sha256
    assert command.liability_requirement.proposed_order_sha256 == command.proposed_order_sha256


def test_command_cannot_omit_or_raise_model_authored_liability_bound(
    continuity_plan_factory,
):
    plan = continuity_plan_factory()
    command = _executor(plan).build_command(
        _evaluation(plan, {"action_type": "CANCEL"})
    )
    payload = command.model_dump(mode="python")
    payload.pop("maximum_authorized_liability")

    with pytest.raises(Exception):
        type(command).model_validate(payload)

    raised = command.model_dump(mode="python")
    raised["maximum_authorized_liability"] = Decimal("501")
    with pytest.raises(Exception, match="liability bound"):
        type(command).model_validate(raised)


def test_liability_increase_requires_all_fresh_gates(continuity_plan_factory):
    plan = continuity_plan_factory()
    action = {
        "action_type": "MODIFY_EXISTING_ORDER",
        "new_total_quantity": {"operator": "LITERAL", "literal": "2"},
    }
    evaluation = _evaluation(plan, action)
    executor = _executor(
        plan,
        gates=lambda authority_class: ("RUNTIME_INTEGRITY_BLOCK",),
    )

    with pytest.raises(ContinuityCommandBuildError, match="RUNTIME_INTEGRITY_BLOCK"):
        executor.build_command(evaluation)


def test_nonexpanding_action_is_classified_by_delta_not_label(
    continuity_plan_factory,
):
    plan = continuity_plan_factory()
    action = {
        "action_type": "MODIFY_EXISTING_ORDER",
        "new_total_quantity": {"operator": "LITERAL", "literal": "0.5"},
    }
    command = _executor(plan).build_command(_evaluation(plan, action))

    assert command.authority_class == "NONEXPANDING_EXISTING_AUTHORITY"


def test_gtd_cannot_exceed_epoch_authority(continuity_plan_factory):
    plan = continuity_plan_factory()
    action = {
        "action_type": "MODIFY_EXISTING_ORDER",
        "new_tif": "GTD",
        "new_good_till_date_utc": "2026-10-03T19:30:00Z",
    }

    with pytest.raises(ContinuityCommandBuildError, match="EPOCH_AUTHORITY"):
        _executor(plan).build_command(_evaluation(plan, action))


def test_gtd_extension_is_measured_against_current_order_expiry(
    continuity_plan_factory,
):
    plan = continuity_plan_factory()
    action = {
        "action_type": "MODIFY_EXISTING_ORDER",
        "new_tif": "GTD",
        "new_good_till_date_utc": "2026-10-01T18:30:00Z",
    }

    with pytest.raises(ContinuityCommandBuildError, match="REVIEW_REQUIRED"):
        _executor(
            plan,
            binding_updates={
                "current_tif": "GTD",
                "current_good_till_date_utc": "2026-10-01T18:00:00Z",
            },
            gates=lambda authority_class: (
                ("REVIEW_REQUIRED",)
                if authority_class.value == "EXTENDED_TEMPORAL_AUTHORITY"
                else ()
            ),
        ).build_command(_evaluation(plan, action))


def test_inactive_or_hash_mismatched_evaluation_cannot_build(
    continuity_plan_factory,
):
    plan = continuity_plan_factory()
    inactive = _evaluation(plan, {"action_type": "CANCEL"}).model_copy(
        update={"authority_active": False}
    )
    wrong_hash = _evaluation(plan, {"action_type": "CANCEL"}).model_copy(
        update={"plan_sha256": "0" * 64}
    )

    with pytest.raises(ContinuityCommandBuildError, match="AUTHORITY_INACTIVE"):
        _executor(plan).build_command(inactive)
    with pytest.raises(ContinuityCommandBuildError, match="PLAN_HASH_MISMATCH"):
        _executor(plan).build_command(wrong_hash)
