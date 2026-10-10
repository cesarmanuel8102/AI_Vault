"""Pure evaluation of finite, model-authored continuity plans."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping

from .canonical import sha256_json
from .continuity_models import (
    CodexOrderContinuityPlan,
    ConditionOperator,
    ContinuityCondition,
    ContinuityEvaluation,
    ContinuityFactEvidence,
    ContinuityFactName,
    ContinuityFactSnapshot,
    ContinuityOrderState,
    ContinuityValueExpression,
    ExpiryAuthorityMode,
    PredicateComparator,
    ValueExpressionOperator,
)
from .provider_lifecycle import BrokerTimeEvidence


class ContinuityEvaluationError(RuntimeError):
    pass


def _fact_map(
    facts: ContinuityFactSnapshot | Mapping[ContinuityFactName | str, Any],
) -> tuple[dict[ContinuityFactName, ContinuityFactEvidence], datetime]:
    if isinstance(facts, ContinuityFactSnapshot):
        expected = sha256_json(
            [item.model_dump(mode="json") for item in facts.facts]
        )
        if expected != facts.evidence_sha256:
            return {}, facts.broker_time_utc
        return {item.fact: item for item in facts.facts}, facts.broker_time_utc
    raise ContinuityEvaluationError("FACT_SNAPSHOT_REQUIRED")


def _available_fact(
    name: ContinuityFactName,
    facts: ContinuityFactSnapshot,
    requested_max_age: Decimal | None = None,
) -> ContinuityFactEvidence | None:
    mapping, now = _fact_map(facts)
    evidence = mapping.get(name)
    if evidence is None:
        return None
    evidence_body = {
        "fact": evidence.fact.value,
        "source": evidence.source,
        "collected_at_utc": evidence.collected_at_utc.isoformat(),
        "max_age_seconds": str(evidence.max_age_seconds),
        "canonical_value": evidence.canonical_value,
    }
    if sha256_json(evidence_body) != evidence.evidence_sha256:
        return None
    effective_age = evidence.max_age_seconds
    if requested_max_age is not None:
        effective_age = min(effective_age, requested_max_age)
    age = Decimal(str((now - evidence.collected_at_utc).total_seconds()))
    if age < 0 or age > effective_age:
        return None
    return evidence


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _ordered_pair(left: Any, right: Any) -> tuple[Any, Any]:
    left_decimal, right_decimal = _decimal(left), _decimal(right)
    if left_decimal is not None and right_decimal is not None:
        return left_decimal, right_decimal
    if isinstance(left, str) and isinstance(right, str):
        try:
            return (
                datetime.fromisoformat(left.replace("Z", "+00:00")),
                datetime.fromisoformat(right.replace("Z", "+00:00")),
            )
        except ValueError:
            pass
    return left, right


def _compare(left: Any, comparator: PredicateComparator, expected: Any) -> bool:
    if comparator == PredicateComparator.BETWEEN:
        lower_left, lower = _ordered_pair(left, expected[0])
        upper_left, upper = _ordered_pair(left, expected[1])
        return lower <= lower_left and upper_left <= upper
    if comparator == PredicateComparator.IN:
        return any(_compare(left, PredicateComparator.EQ, item) for item in expected)
    left_value, right_value = _ordered_pair(left, expected)
    if comparator == PredicateComparator.EQ:
        return left_value == right_value
    if comparator == PredicateComparator.NE:
        return left_value != right_value
    if comparator == PredicateComparator.LT:
        return left_value < right_value
    if comparator == PredicateComparator.LE:
        return left_value <= right_value
    if comparator == PredicateComparator.GT:
        return left_value > right_value
    if comparator == PredicateComparator.GE:
        return left_value >= right_value
    raise ContinuityEvaluationError("COMPARATOR_UNSUPPORTED")


def evaluate_condition(
    condition: ContinuityCondition, facts: ContinuityFactSnapshot
) -> bool | None:
    if condition.operator == ConditionOperator.PREDICATE:
        assert condition.fact is not None and condition.comparator is not None
        evidence = _available_fact(
            condition.fact, facts, condition.max_age_seconds
        )
        if evidence is None:
            return None
        try:
            return _compare(
                evidence.canonical_value, condition.comparator, condition.value
            )
        except (TypeError, ValueError):
            return None

    values = [evaluate_condition(child, facts) for child in condition.children]
    if condition.operator == ConditionOperator.NOT:
        return None if values[0] is None else not values[0]
    if condition.operator == ConditionOperator.ALL:
        if False in values:
            return False
        return None if None in values else True
    if condition.operator == ConditionOperator.ANY:
        if True in values:
            return True
        return None if None in values else False
    raise ContinuityEvaluationError("CONDITION_OPERATOR_UNSUPPORTED")


def evaluate_value(
    expression: ContinuityValueExpression, facts: ContinuityFactSnapshot
) -> Decimal:
    if expression.operator == ValueExpressionOperator.LITERAL:
        assert expression.literal is not None
        return expression.literal
    if expression.operator == ValueExpressionOperator.FACT:
        assert expression.fact is not None
        evidence = _available_fact(ContinuityFactName(expression.fact.value), facts)
        value = None if evidence is None else _decimal(evidence.canonical_value)
        if value is None:
            raise ContinuityEvaluationError("NUMERIC_FACT_UNAVAILABLE")
        return value
    values = [evaluate_value(operand, facts) for operand in expression.operands]
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
    raise ContinuityEvaluationError("VALUE_OPERATOR_UNSUPPORTED")


class ContinuityFactCollector:
    def __init__(self, store: Any, broker: Any, ledger: Any, clock: Any) -> None:
        self.store = store
        self.broker = broker
        self.ledger = ledger
        self.clock = clock

    @staticmethod
    def _evidence(
        fact: ContinuityFactName,
        value: Any,
        *,
        source: str,
        collected_at_utc: datetime,
        max_age_seconds: Decimal | int,
    ) -> ContinuityFactEvidence:
        body = {
            "fact": fact.value,
            "source": source,
            "collected_at_utc": collected_at_utc.isoformat(),
            "max_age_seconds": str(max_age_seconds),
            "canonical_value": value,
        }
        return ContinuityFactEvidence(
            fact=fact,
            source=source,
            collected_at_utc=collected_at_utc,
            max_age_seconds=max_age_seconds,
            canonical_value=value,
            evidence_sha256=sha256_json(body),
        )

    def collect(
        self,
        plan: CodexOrderContinuityPlan,
        *,
        broker_time_utc: BrokerTimeEvidence | None,
    ) -> ContinuityFactSnapshot:
        if broker_time_utc is None or broker_time_utc.environment != "PAPER":
            raise ContinuityEvaluationError("AUTHENTICATED_PAPER_BROKER_TIME_REQUIRED")
        if broker_time_utc.authenticated is not True:
            raise ContinuityEvaluationError("AUTHENTICATED_PAPER_BROKER_TIME_REQUIRED")
        try:
            broker_time_utc = BrokerTimeEvidence.model_validate(
                broker_time_utc.model_dump(mode="python")
            )
        except ValueError as exc:
            raise ContinuityEvaluationError(
                "AUTHENTICATED_PAPER_BROKER_TIME_REQUIRED"
            ) from exc
        now = broker_time_utc.time_utc
        if now.tzinfo is None or now.utcoffset() is None:
            raise ContinuityEvaluationError("AUTHENTICATED_PAPER_BROKER_TIME_REQUIRED")
        if getattr(self.broker, "environment", None) != "PAPER":
            raise ContinuityEvaluationError("PAPER_BROKER_REQUIRED")
        if getattr(self.broker, "account_identity_sha256", None) != (
            plan.order_binding.account_identity_sha256
        ):
            raise ContinuityEvaluationError("PAPER_ACCOUNT_IDENTITY_MISMATCH")
        if broker_time_utc.account_identity_sha256 != (
            plan.order_binding.account_identity_sha256
        ):
            raise ContinuityEvaluationError("PAPER_ACCOUNT_IDENTITY_MISMATCH")
        if not getattr(self.broker, "all_order_visibility", False):
            raise ContinuityEvaluationError("ALL_ORDER_VISIBILITY_REQUIRED")

        raw = self.broker.collect_continuity_facts(plan.order_binding, now)
        facts: dict[ContinuityFactName, ContinuityFactEvidence] = {}
        for raw_name, item in raw.items():
            name = ContinuityFactName(raw_name)
            facts[name] = self._evidence(
                name,
                item["value"],
                source=str(item["source"]),
                collected_at_utc=item["collected_at_utc"],
                max_age_seconds=item["max_age_seconds"],
            )

        provider = self.store.latest_provider_projection()
        provider_state = str(provider.get("state", "IDLE"))
        provider_payload = provider.get("payload", {})
        if (
            provider_state == "IN_FLIGHT"
            and provider_payload.get("failure_code") is not None
        ):
            raise ContinuityEvaluationError("PROVIDER_STATE_CONFLICT")
        facts[ContinuityFactName.PROVIDER_STATE] = self._evidence(
            ContinuityFactName.PROVIDER_STATE,
            provider_state,
            source="CONTINUITY_PROVIDER_EVENTS",
            collected_at_utc=now,
            max_age_seconds=30,
        )
        for name, key in (
            (ContinuityFactName.PROVIDER_FAILURE_CODE, "failure_code"),
            (ContinuityFactName.MODEL_INVOCATION_START_UTC, "broker_time_utc"),
            (
                ContinuityFactName.MODEL_INVOCATION_DEADLINE_UTC,
                "declared_deadline_broker_utc",
            ),
        ):
            if provider_payload.get(key) is not None:
                facts[name] = self._evidence(
                    name,
                    provider_payload[key],
                    source="CONTINUITY_PROVIDER_EVENTS",
                    collected_at_utc=now,
                    max_age_seconds=30,
                )
        facts[ContinuityFactName.MODEL_INVOCATION_IN_FLIGHT] = self._evidence(
            ContinuityFactName.MODEL_INVOCATION_IN_FLIGHT,
            provider_state == "IN_FLIGHT",
            source="CONTINUITY_PROVIDER_EVENTS",
            collected_at_utc=now,
            max_age_seconds=30,
        )
        facts[ContinuityFactName.BROKER_TIME_UTC] = self._evidence(
            ContinuityFactName.BROKER_TIME_UTC,
            now.isoformat(),
            source="AUTHENTICATED_PAPER_BROKER_TIME",
            collected_at_utc=now,
            max_age_seconds=5,
        )

        ledger = self.ledger.project()
        getter = ledger.get if isinstance(ledger, dict) else lambda key: getattr(ledger, key)
        for name, key in (
            (ContinuityFactName.EXPERIMENT_CASH, "cash"),
            (ContinuityFactName.EXPERIMENT_EQUITY, "equity"),
        ):
            facts[name] = self._evidence(
                name, str(getter(key)), source="EXPERIMENT_SUBLEDGER",
                collected_at_utc=now, max_age_seconds=30,
            )
        facts[ContinuityFactName.EXPERIMENT_CLOCK_STATE] = self._evidence(
            ContinuityFactName.EXPERIMENT_CLOCK_STATE,
            self.clock.state(),
            source="EXPERIMENT_CLOCK",
            collected_at_utc=now,
            max_age_seconds=30,
        )
        ordered = tuple(facts[name] for name in sorted(facts, key=lambda item: item.value))
        snapshot_hash = sha256_json([item.model_dump(mode="json") for item in ordered])
        return ContinuityFactSnapshot(
            snapshot_id=f"continuity-facts-{snapshot_hash[:24]}",
            collected_at_utc=now,
            broker_time_utc=now,
            facts=ordered,
            evidence_sha256=snapshot_hash,
        )


class ContinuityEvaluator:
    def __init__(self, *, execution_counts: Mapping[str, int] | None = None) -> None:
        self.execution_counts = dict(execution_counts or {})

    def evaluate(
        self, plan: CodexOrderContinuityPlan, facts: ContinuityFactSnapshot
    ) -> ContinuityEvaluation:
        now = facts.broker_time_utc
        if (
            plan.schema == "CODEX_ORDER_CONTINUITY_PLAN_V4"
            and plan.next_decision_deadline_utc is not None
            and now >= plan.next_decision_deadline_utc
        ):
            body = {
                "plan_sha256": plan.sha256,
                "fact_snapshot_sha256": facts.evidence_sha256,
                "selected_contingency_id": None,
                "selected_action": None,
                "reason_codes": ["V4_NEXT_DECISION_DEADLINE_EXPIRED"],
            }
            digest = sha256_json(body)
            return ContinuityEvaluation(
                evaluation_id=f"continuity-evaluation-{digest[:24]}",
                evaluated_at_utc=now,
                plan_id=plan.plan_id,
                plan_sha256=plan.sha256,
                fact_snapshot_sha256=facts.evidence_sha256,
                authority_active=False,
                reason_codes=("V4_NEXT_DECISION_DEADLINE_EXPIRED",),
            )
        activation = evaluate_condition(plan.authority_activation_condition, facts)
        expired = now >= plan.plan_valid_until
        selected_id = None
        selected_action = None
        reason_codes: list[str] = []

        if expired:
            if (
                plan.expiry_authority_mode == ExpiryAuthorityMode.ALWAYS_AT_EXPIRY
                or activation is True
            ):
                selected_action = plan.terminal_disposition
                reason_codes.append("PLAN_EXPIRY_DISPOSITION")
            elif activation is None:
                candidate = self._first_available_contingency(plan, facts)
                if candidate is not None:
                    selected_id = candidate.contingency_id
                    selected_action = candidate.unavailable_data_action
                    reason_codes.append("EVIDENCE_UNAVAILABLE")
            else:
                reason_codes.append("CONTINUITY_AUTHORITY_INACTIVE")
        elif activation is None:
            candidate = self._first_available_contingency(plan, facts)
            if candidate is not None:
                selected_id = candidate.contingency_id
                selected_action = candidate.unavailable_data_action
                reason_codes.append("EVIDENCE_UNAVAILABLE")
        elif activation is False:
            reason_codes.append("CONTINUITY_AUTHORITY_INACTIVE")
        else:
            for contingency in sorted(
                plan.contingencies, key=lambda item: (item.priority, item.contingency_id)
            ):
                if not (
                    contingency.valid_from_utc <= now <= contingency.valid_until_utc
                ):
                    continue
                if self.execution_counts.get(contingency.contingency_id, 0) >= (
                    contingency.maximum_execution_count
                ):
                    continue
                outcome = evaluate_condition(contingency.condition, facts)
                if outcome is None:
                    selected_id = contingency.contingency_id
                    selected_action = contingency.unavailable_data_action
                    reason_codes.append("EVIDENCE_UNAVAILABLE")
                    break
                if not outcome:
                    continue
                status = _available_fact(ContinuityFactName.ORDER_STATUS, facts)
                if status is None:
                    selected_id = contingency.contingency_id
                    selected_action = contingency.unavailable_data_action
                    reason_codes.append("EVIDENCE_UNAVAILABLE")
                    break
                try:
                    state = ContinuityOrderState(str(status.canonical_value))
                except ValueError:
                    selected_id = contingency.contingency_id
                    selected_action = contingency.unavailable_data_action
                    reason_codes.append("EVIDENCE_UNAVAILABLE")
                    break
                selected_id = contingency.contingency_id
                selected_action = contingency.state_actions[state]
                reason_codes.append("CONTINGENCY_MATCHED")
                break
            if selected_action is None:
                reason_codes.append("NO_CONTINGENCY_MATCHED")

        authority_active = activation
        body = {
            "plan_sha256": plan.sha256,
            "fact_snapshot_sha256": facts.evidence_sha256,
            "selected_contingency_id": selected_id,
            "selected_action": None
            if selected_action is None
            else selected_action.model_dump(mode="json"),
            "reason_codes": reason_codes,
        }
        digest = sha256_json(body)
        return ContinuityEvaluation(
            evaluation_id=f"continuity-evaluation-{digest[:24]}",
            evaluated_at_utc=now,
            plan_id=plan.plan_id,
            plan_sha256=plan.sha256,
            fact_snapshot_sha256=facts.evidence_sha256,
            authority_active=authority_active,
            selected_contingency_id=selected_id,
            selected_action=selected_action,
            execution_ordinal=(
                None
                if selected_id is None
                else self.execution_counts.get(selected_id, 0) + 1
            ),
            reason_codes=tuple(reason_codes),
        )

    def _first_available_contingency(
        self, plan: CodexOrderContinuityPlan, facts: ContinuityFactSnapshot
    ):
        now = facts.broker_time_utc
        candidates = [
            item
            for item in plan.contingencies
            if item.valid_from_utc <= now <= item.valid_until_utc
            and self.execution_counts.get(item.contingency_id, 0)
            < item.maximum_execution_count
        ]
        return min(candidates, key=lambda item: (item.priority, item.contingency_id), default=None)
