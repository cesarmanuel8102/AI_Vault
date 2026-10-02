"""Build immutable broker commands from evaluated model-authored authority."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

from .broker_write_coordinator import AuthorizedBrokerCommand, BrokerCommandType
from .broker_write_coordinator import BrokerWriteCoordinator
from .canonical import sha256_json
from .continuity_liability import MaximumLiabilityRequirement
from .continuity_models import (
    CodexOrderContinuityPlan,
    ContinuityActionType,
    ContinuityAuthorityClass,
    ContinuityEvaluation,
    ContinuityExecutableAction,
    ContinuityValueExpression,
    TimeInForce,
    ValueExpressionOperator,
)


class ContinuityCommandBuildError(RuntimeError):
    pass


def _parse_order_expiry(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(raw, "%Y%m%d %H:%M:%S UTC").replace(
                    tzinfo=timezone.utc
                )
            except ValueError as exc:
                raise ContinuityCommandBuildError(
                    "CURRENT_ORDER_EXPIRY_INVALID"
                ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContinuityCommandBuildError("CURRENT_ORDER_EXPIRY_INVALID")
    return parsed.astimezone(timezone.utc)


class ContinuityExecutor:
    def __init__(
        self,
        *,
        plan_reader: Callable[[str], CodexOrderContinuityPlan],
        active_binding_reader: Callable[[str], dict[str, Any]],
        fact_values_reader: Callable[[str], dict[str, Any]],
        fresh_gate_checker: Callable[[ContinuityAuthorityClass], tuple[str, ...]],
        durable_sequence_allocator: Callable[[], int] | None = None,
    ) -> None:
        self.plan_reader = plan_reader
        self.active_binding_reader = active_binding_reader
        self.fact_values_reader = fact_values_reader
        self.fresh_gate_checker = fresh_gate_checker
        self.durable_sequence_allocator = durable_sequence_allocator

    def _value(
        self, expression: ContinuityValueExpression, facts: dict[str, Any]
    ) -> Decimal:
        if expression.operator == ValueExpressionOperator.LITERAL:
            assert expression.literal is not None
            return expression.literal
        if expression.operator == ValueExpressionOperator.FACT:
            assert expression.fact is not None
            try:
                value = Decimal(str(facts[expression.fact.value]))
            except (KeyError, ValueError) as exc:
                raise ContinuityCommandBuildError("NUMERIC_FACT_UNAVAILABLE") from exc
            if not value.is_finite():
                raise ContinuityCommandBuildError("NUMERIC_FACT_UNAVAILABLE")
            return value
        values = [self._value(item, facts) for item in expression.operands]
        if expression.operator == ValueExpressionOperator.ADD:
            return sum(values, Decimal("0"))
        if expression.operator == ValueExpressionOperator.SUBTRACT:
            return values[0] - sum(values[1:], Decimal("0"))
        if expression.operator == ValueExpressionOperator.MULTIPLY:
            result = Decimal("1")
            for value in values:
                result *= value
            return result
        if expression.operator == ValueExpressionOperator.MIN:
            return min(values)
        if expression.operator == ValueExpressionOperator.MAX:
            return max(values)
        if expression.operator == ValueExpressionOperator.ROUND_TO_TICK:
            assert expression.tick_size is not None
            return (
                values[0] / expression.tick_size
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * expression.tick_size
        raise ContinuityCommandBuildError("VALUE_OPERATOR_UNSUPPORTED")

    @staticmethod
    def _command_type(action: ContinuityExecutableAction) -> BrokerCommandType:
        if action.action_type == ContinuityActionType.RETAIN:
            return BrokerCommandType.RETAIN
        if action.action_type == ContinuityActionType.CANCEL:
            return BrokerCommandType.CANCEL
        if action.action_type == ContinuityActionType.MODIFY_EXISTING_ORDER:
            return BrokerCommandType.MODIFY
        if (
            action.action_type == ContinuityActionType.REQUIRES_AGENT
            and action.interim_action is not None
        ):
            return ContinuityExecutor._command_type(action.interim_action)
        raise ContinuityCommandBuildError("ACTION_REQUIRES_AGENT")

    def build_command(
        self, evaluation: ContinuityEvaluation
    ) -> AuthorizedBrokerCommand:
        if evaluation.authority_active is not True:
            raise ContinuityCommandBuildError("AUTHORITY_INACTIVE")
        if evaluation.selected_action is None or evaluation.execution_ordinal is None:
            raise ContinuityCommandBuildError("EXECUTABLE_ACTION_REQUIRED")
        plan = self.plan_reader(evaluation.plan_id)
        if plan.sha256 != evaluation.plan_sha256:
            raise ContinuityCommandBuildError("PLAN_HASH_MISMATCH")
        binding = self.active_binding_reader(evaluation.plan_id)
        if (
            binding.get("plan_id") != plan.plan_id
            or binding.get("plan_sha256") != plan.sha256
        ):
            raise ContinuityCommandBuildError("ACTIVE_BINDING_MISMATCH")
        action = evaluation.selected_action
        if (
            action.action_type == ContinuityActionType.REQUIRES_AGENT
            and action.interim_action is not None
        ):
            action = action.interim_action
        facts = self.fact_values_reader(evaluation.fact_snapshot_sha256)
        new_total = (
            self._value(action.new_total_quantity, facts)
            if action.new_total_quantity is not None
            else None
        )
        new_limit = (
            self._value(action.new_limit_price, facts)
            if action.new_limit_price is not None
            else None
        )
        if new_total is not None and new_total <= 0:
            raise ContinuityCommandBuildError("ORDER_TOTAL_INVALID")
        if new_limit is not None and new_limit <= 0:
            raise ContinuityCommandBuildError("ORDER_LIMIT_INVALID")
        if (
            action.new_good_till_date_utc is not None
            and action.new_good_till_date_utc > plan.epoch_authority_end_utc
        ):
            raise ContinuityCommandBuildError("EPOCH_AUTHORITY_OVERRUN")

        current_total = Decimal(str(binding["current_total_quantity"]))
        current_limit = Decimal(str(binding["current_limit_price"]))
        resolved_total = new_total if new_total is not None else current_total
        resolved_limit = new_limit if new_limit is not None else current_limit
        increases_liability = (
            new_total is not None and new_total > current_total
        ) or (
            plan.order_binding.action == "BUY"
            and new_limit is not None
            and new_limit > current_limit
        )
        extends_time = False
        if action.new_tif is not None:
            current_tif = TimeInForce(str(binding["current_tif"]))
            if action.new_tif == TimeInForce.GTC:
                extends_time = current_tif != TimeInForce.GTC
            elif action.new_tif == TimeInForce.GTD:
                if action.new_good_till_date_utc is None:
                    raise ContinuityCommandBuildError("NEW_ORDER_EXPIRY_REQUIRED")
                if current_tif == TimeInForce.GTD:
                    current_expiry = _parse_order_expiry(
                        binding.get("current_good_till_date_utc")
                    )
                    extends_time = action.new_good_till_date_utc > current_expiry
                elif current_tif == TimeInForce.GTC:
                    extends_time = False
                else:
                    extends_time = (
                        action.new_good_till_date_utc > plan.session_end_utc
                    )
        if increases_liability:
            authority_class = ContinuityAuthorityClass.INCREASED_MAXIMUM_LIABILITY
        elif extends_time:
            authority_class = ContinuityAuthorityClass.EXTENDED_TEMPORAL_AUTHORITY
        elif action.action_type == ContinuityActionType.CANCEL:
            authority_class = ContinuityAuthorityClass.CANCEL_ORDER
        else:
            authority_class = ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY
        reasons = tuple(self.fresh_gate_checker(authority_class))
        if reasons:
            raise ContinuityCommandBuildError("|".join(reasons))

        now = datetime.now(timezone.utc)
        command_type = self._command_type(action)
        proposed_order_sha256 = sha256_json(
            {
                "order_ref": str(binding["order_ref"]),
                "order_id": int(binding["order_id"]),
                "perm_id": int(binding["perm_id"]),
                "execution_client_id": int(binding["execution_client_id"]),
                "contract_identity_sha256": str(
                    binding["contract_identity_sha256"]
                ),
                "action": plan.order_binding.action,
                "command_type": command_type.value,
                "resolved_total_quantity": resolved_total,
                "resolved_limit_price": resolved_limit,
                "new_tif": action.new_tif,
                "new_good_till_date_utc": action.new_good_till_date_utc,
            }
        )
        leg_hashes = tuple(
            str(value)
            for value in binding.get(
                "contract_leg_identity_sha256",
                (str(binding["contract_identity_sha256"]),),
            )
        )
        liability_requirement = MaximumLiabilityRequirement(
            plan_id=plan.plan_id,
            plan_sha256=plan.sha256,
            maximum_authorized_liability=plan.maximum_authorized_liability,
            account_identity_sha256=str(binding["account_identity_sha256"]),
            contract_identity_sha256=str(binding["contract_identity_sha256"]),
            proposed_order_sha256=proposed_order_sha256,
            required_leg_identity_sha256=leg_hashes,
            maximum_evidence_age_seconds=Decimal("30"),
        )
        durable_sequence = (
            evaluation.execution_ordinal
            if self.durable_sequence_allocator is None
            else self.durable_sequence_allocator()
        )
        return AuthorizedBrokerCommand(
            command_id=f"continuity-command:{evaluation.evaluation_id}",
            durable_sequence=durable_sequence,
            execution_key=(
                f"{plan.sha256}:{evaluation.evaluation_id}:"
                f"{evaluation.execution_ordinal}"
            ),
            source="WATCHDOG",
            command_type=command_type,
            evaluation_id=evaluation.evaluation_id,
            evaluation_sha256=evaluation.sha256,
            plan_id=plan.plan_id,
            plan_sha256=plan.sha256,
            fact_snapshot_sha256=evaluation.fact_snapshot_sha256,
            order_ref=str(binding["order_ref"]),
            order_id=int(binding["order_id"]),
            perm_id=int(binding["perm_id"]),
            execution_client_id=int(binding["execution_client_id"]),
            account_identity_sha256=str(binding["account_identity_sha256"]),
            contract_identity_sha256=str(binding["contract_identity_sha256"]),
            observed_state_sha256=str(binding["observed_state_sha256"]),
            epoch_id=plan.epoch_id,
            definition_sha256=plan.definition_sha256,
            owner_authorization_sha256=plan.owner_authorization_sha256,
            authority_class=authority_class,
            new_total_quantity=new_total,
            new_limit_price=new_limit,
            new_tif=action.new_tif,
            new_good_till_date_utc=action.new_good_till_date_utc,
            resolved_total_quantity=resolved_total,
            resolved_limit_price=resolved_limit,
            proposed_order_sha256=proposed_order_sha256,
            maximum_authorized_liability=plan.maximum_authorized_liability,
            liability_requirement=liability_requirement,
            created_at_utc=now,
        )

    def submit(
        self,
        evaluation: ContinuityEvaluation,
        coordinator: BrokerWriteCoordinator,
        *,
        source: str = "WATCHDOG",
    ):
        command = self.build_command(evaluation)
        if source != command.source:
            command = AuthorizedBrokerCommand.model_validate(
                {**command.model_dump(mode="python"), "source": source}
            )
        return coordinator.submit(command)
