from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json


SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_AST_DEPTH = 8
MAX_AST_NODES = 64
MAX_ACTION_VALUE = Decimal("1000000000")


class ExpiryAuthorityMode(str, Enum):
    WHEN_CONTINUITY_ACTIVE = "WHEN_CONTINUITY_ACTIVE"
    ALWAYS_AT_EXPIRY = "ALWAYS_AT_EXPIRY"


class ContinuityActionType(str, Enum):
    RETAIN = "RETAIN"
    CANCEL = "CANCEL"
    MODIFY_EXISTING_ORDER = "MODIFY_EXISTING_ORDER"
    REQUIRES_AGENT = "REQUIRES_AGENT"


class ProviderInvocationState(str, Enum):
    IDLE = "IDLE"
    IN_FLIGHT = "IN_FLIGHT"
    TIMEOUT_CONFIRMED = "TIMEOUT_CONFIRMED"
    PROCESS_ERROR = "PROCESS_ERROR"
    COMPLETED_UNACCEPTED = "COMPLETED_UNACCEPTED"
    COMPLETED_ACCEPTED = "COMPLETED_ACCEPTED"
    ABANDONED = "ABANDONED"


class ContinuityReviewDisposition(str, Enum):
    ACK_NO_METHOD_CHANGE = "ACK_NO_METHOD_CHANGE"
    REFLECTION_RECORDED = "REFLECTION_RECORDED"
    POLICY_SUPERSEDED = "POLICY_SUPERSEDED"
    MORE_RESEARCH_REQUIRED = "MORE_RESEARCH_REQUIRED"


class ContinuityAuthorityClass(str, Enum):
    NEW_EXPOSURE = "NEW_EXPOSURE"
    INCREASED_MAXIMUM_LIABILITY = "INCREASED_MAXIMUM_LIABILITY"
    EXTENDED_TEMPORAL_AUTHORITY = "EXTENDED_TEMPORAL_AUTHORITY"
    NONEXPANDING_EXISTING_AUTHORITY = "NONEXPANDING_EXISTING_AUTHORITY"
    RECONCILIATION = "RECONCILIATION"
    OBSERVATION = "OBSERVATION"
    CANCEL_ORDER = "CANCEL_ORDER"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    PREAUTHORIZED_CONTINUITY = "PREAUTHORIZED_CONTINUITY"


class ConditionOperator(str, Enum):
    PREDICATE = "PREDICATE"
    ALL = "ALL"
    ANY = "ANY"
    NOT = "NOT"


class PredicateComparator(str, Enum):
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    BETWEEN = "BETWEEN"
    IN = "IN"


class ContinuityFactName(str, Enum):
    BROKER_TIME_UTC = "BROKER_TIME_UTC"
    MARKET_SESSION_STATE = "MARKET_SESSION_STATE"
    PROVIDER_STATE = "PROVIDER_STATE"
    PROVIDER_FAILURE_CODE = "PROVIDER_FAILURE_CODE"
    MODEL_INVOCATION_IN_FLIGHT = "MODEL_INVOCATION_IN_FLIGHT"
    MODEL_INVOCATION_START_UTC = "MODEL_INVOCATION_START_UTC"
    MODEL_INVOCATION_DEADLINE_UTC = "MODEL_INVOCATION_DEADLINE_UTC"
    LAST_ACCEPTED_DECISION_UTC = "LAST_ACCEPTED_DECISION_UTC"
    ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS = (
        "ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS"
    )
    ORDER_STATUS = "ORDER_STATUS"
    ORDER_FILLED_QUANTITY = "ORDER_FILLED_QUANTITY"
    ORDER_REMAINING_QUANTITY = "ORDER_REMAINING_QUANTITY"
    ORDER_TOTAL_QUANTITY = "ORDER_TOTAL_QUANTITY"
    ORDER_BID = "ORDER_BID"
    ORDER_ASK = "ORDER_ASK"
    ORDER_LAST = "ORDER_LAST"
    ORDER_MARK = "ORDER_MARK"
    UNDERLYING_BID = "UNDERLYING_BID"
    UNDERLYING_ASK = "UNDERLYING_ASK"
    UNDERLYING_LAST = "UNDERLYING_LAST"
    UNDERLYING_VOLUME = "UNDERLYING_VOLUME"
    POSITION_EXISTS = "POSITION_EXISTS"
    POSITION_QUANTITY = "POSITION_QUANTITY"
    EXPERIMENT_CASH = "EXPERIMENT_CASH"
    EXPERIMENT_EQUITY = "EXPERIMENT_EQUITY"
    EXPERIMENT_CLOCK_STATE = "EXPERIMENT_CLOCK_STATE"


class NumericFactName(str, Enum):
    ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS = (
        "ELAPSED_SINCE_LAST_ACCEPTED_DECISION_SECONDS"
    )
    ORDER_FILLED_QUANTITY = "ORDER_FILLED_QUANTITY"
    ORDER_REMAINING_QUANTITY = "ORDER_REMAINING_QUANTITY"
    ORDER_TOTAL_QUANTITY = "ORDER_TOTAL_QUANTITY"
    ORDER_BID = "ORDER_BID"
    ORDER_ASK = "ORDER_ASK"
    ORDER_LAST = "ORDER_LAST"
    ORDER_MARK = "ORDER_MARK"
    UNDERLYING_BID = "UNDERLYING_BID"
    UNDERLYING_ASK = "UNDERLYING_ASK"
    UNDERLYING_LAST = "UNDERLYING_LAST"
    UNDERLYING_VOLUME = "UNDERLYING_VOLUME"
    POSITION_QUANTITY = "POSITION_QUANTITY"
    EXPERIMENT_CASH = "EXPERIMENT_CASH"
    EXPERIMENT_EQUITY = "EXPERIMENT_EQUITY"


class ValueExpressionOperator(str, Enum):
    LITERAL = "LITERAL"
    FACT = "FACT"
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MULTIPLY = "MULTIPLY"
    MIN = "MIN"
    MAX = "MAX"
    ROUND_TO_TICK = "ROUND_TO_TICK"


class ContinuityOrderState(str, Enum):
    UNFILLED = "UNFILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ABSENT = "ABSENT"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"


class OrderBindingType(str, Enum):
    NEW_PROPOSAL = "NEW_PROPOSAL"
    EXISTING_ORDER = "EXISTING_ORDER"


class RetainAuthority(str, Enum):
    RETAIN_UNTIL_ORDER_TIF = "RETAIN_UNTIL_ORDER_TIF"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    GTD = "GTD"
    IOC = "IOC"
    FOK = "FOK"
    OPG = "OPG"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _bounded_tree(root: Any, child_attr: str) -> tuple[int, int]:
    seen: set[int] = set()

    def visit(node: Any, depth: int) -> tuple[int, int]:
        if depth > MAX_AST_DEPTH:
            raise ValueError(f"expression depth exceeds {MAX_AST_DEPTH}")
        identity = id(node)
        if identity in seen:
            raise ValueError("cyclic expression is forbidden")
        seen.add(identity)
        max_depth = depth
        count = 1
        for child in getattr(node, child_attr):
            child_depth, child_count = visit(child, depth + 1)
            max_depth = max(max_depth, child_depth)
            count += child_count
            if count > MAX_AST_NODES:
                raise ValueError(f"expression node count exceeds {MAX_AST_NODES}")
        seen.remove(identity)
        return max_depth, count

    return visit(root, 1)


class ContinuityCondition(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    operator: ConditionOperator
    fact: ContinuityFactName | None = None
    comparator: PredicateComparator | None = None
    value: Any | None = None
    max_age_seconds: Decimal | None = Field(default=None, gt=0, le=86400)
    children: tuple["ContinuityCondition", ...] = ()

    @model_validator(mode="after")
    def validate_shape(self) -> "ContinuityCondition":
        if self.operator == ConditionOperator.PREDICATE:
            if self.fact is None or self.comparator is None or self.max_age_seconds is None:
                raise ValueError(
                    "PREDICATE requires an approved fact, comparator, and freshness"
                )
            if self.children:
                raise ValueError("PREDICATE cannot contain child conditions")
            if self.value is None:
                raise ValueError("PREDICATE requires a comparison value")
            if self.comparator == PredicateComparator.BETWEEN and (
                not isinstance(self.value, (list, tuple)) or len(self.value) != 2
            ):
                raise ValueError("BETWEEN requires exactly two bounds")
            if self.comparator == PredicateComparator.IN and not isinstance(
                self.value, (list, tuple)
            ):
                raise ValueError("IN requires a finite list of values")
        else:
            if any(
                value is not None
                for value in (self.fact, self.comparator, self.value, self.max_age_seconds)
            ):
                raise ValueError("Boolean operators cannot contain predicate fields")
            required = 1 if self.operator == ConditionOperator.NOT else 2
            if len(self.children) < required or (
                self.operator == ConditionOperator.NOT and len(self.children) != 1
            ):
                raise ValueError(f"{self.operator.value} has invalid child count")
        _bounded_tree(self, "children")
        return self


class ContinuityValueExpression(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    operator: ValueExpressionOperator
    literal: Decimal | None = None
    fact: NumericFactName | None = None
    operands: tuple["ContinuityValueExpression", ...] = ()
    tick_size: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_shape(self) -> "ContinuityValueExpression":
        if self.literal is not None and (
            not self.literal.is_finite() or abs(self.literal) > MAX_ACTION_VALUE
        ):
            raise ValueError("literal must be finite and within the action bound")
        if self.tick_size is not None and (
            not self.tick_size.is_finite() or self.tick_size > MAX_ACTION_VALUE
        ):
            raise ValueError("tick_size must be finite and within the action bound")

        if self.operator == ValueExpressionOperator.LITERAL:
            if self.literal is None or self.fact is not None or self.operands or self.tick_size:
                raise ValueError("LITERAL requires only literal")
        elif self.operator == ValueExpressionOperator.FACT:
            if self.fact is None or self.literal is not None or self.operands or self.tick_size:
                raise ValueError("FACT requires only an approved numeric fact")
        elif self.operator == ValueExpressionOperator.ROUND_TO_TICK:
            if len(self.operands) != 1 or self.tick_size is None:
                raise ValueError("ROUND_TO_TICK requires one operand and tick_size")
            if self.literal is not None or self.fact is not None:
                raise ValueError("ROUND_TO_TICK cannot contain literal or fact fields")
        else:
            minimum = 2
            if len(self.operands) < minimum:
                raise ValueError(f"{self.operator.value} requires at least two operands")
            if self.literal is not None or self.fact is not None or self.tick_size is not None:
                raise ValueError("arithmetic operators accept only operands")
        _bounded_tree(self, "operands")
        return self


class ContinuityExecutableAction(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    action_type: ContinuityActionType
    new_total_quantity: ContinuityValueExpression | None = None
    new_limit_price: ContinuityValueExpression | None = None
    new_tif: TimeInForce | None = None
    new_good_till_date_utc: datetime | None = None
    retain_authority: RetainAuthority | None = None
    interim_action: "ContinuityExecutableAction | None" = None

    @model_validator(mode="after")
    def validate_action(self) -> "ContinuityExecutableAction":
        modifications = (
            self.new_total_quantity,
            self.new_limit_price,
            self.new_tif,
            self.new_good_till_date_utc,
        )
        if self.new_good_till_date_utc is not None:
            _require_aware(self.new_good_till_date_utc, "new_good_till_date_utc")
        if self.new_tif == TimeInForce.GTD and self.new_good_till_date_utc is None:
            raise ValueError("GTD requires new_good_till_date_utc")
        if self.new_tif != TimeInForce.GTD and self.new_good_till_date_utc is not None:
            raise ValueError("new_good_till_date_utc requires GTD")

        if self.action_type == ContinuityActionType.MODIFY_EXISTING_ORDER:
            if not any(value is not None for value in modifications):
                raise ValueError("MODIFY_EXISTING_ORDER requires an exact mutable value")
            if self.interim_action is not None or self.retain_authority is not None:
                raise ValueError("MODIFY_EXISTING_ORDER cannot contain interim/retain authority")
        elif self.action_type == ContinuityActionType.REQUIRES_AGENT:
            if any(value is not None for value in modifications) or self.retain_authority:
                raise ValueError("REQUIRES_AGENT cannot directly modify an order")
            if self.interim_action is None:
                raise ValueError("REQUIRES_AGENT requires an exact interim disposition")
            if self.interim_action.action_type == ContinuityActionType.REQUIRES_AGENT:
                raise ValueError("interim action cannot require the agent again")
        else:
            if any(value is not None for value in modifications) or self.interim_action is not None:
                raise ValueError(f"{self.action_type.value} cannot contain order modifications")
            if (
                self.retain_authority is not None
                and self.action_type != ContinuityActionType.RETAIN
            ):
                raise ValueError("retain_authority is valid only for RETAIN")
        return self


class ContinuityContingency(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    contingency_id: str = Field(min_length=1, max_length=128)
    priority: int = Field(ge=0, le=1000000)
    valid_from_utc: datetime
    valid_until_utc: datetime
    condition: ContinuityCondition
    state_actions: dict[ContinuityOrderState, ContinuityExecutableAction]
    unavailable_data_action: ContinuityExecutableAction
    maximum_execution_count: int = Field(gt=0, le=1000)
    expectations: tuple[str, ...] = Field(min_length=1, max_length=32)
    why_i_chose_this_contingency: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_contingency(self) -> "ContinuityContingency":
        _require_aware(self.valid_from_utc, "valid_from_utc")
        _require_aware(self.valid_until_utc, "valid_until_utc")
        if self.valid_until_utc <= self.valid_from_utc:
            raise ValueError("contingency validity interval is empty")
        required = set(ContinuityOrderState) - {
            ContinuityOrderState.EVIDENCE_UNAVAILABLE
        }
        if set(self.state_actions) != required:
            raise ValueError("state_actions must cover every broker order state")
        return self


class ContinuityOrderBinding(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    binding_type: OrderBindingType
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    order_ref: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    ibkr_order_id: int | None = Field(default=None, gt=0)
    perm_id: int | None = Field(default=None, gt=0)
    execution_client_id: int = Field(ge=0)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    action: Literal["BUY", "SELL"]
    order_type: str = Field(min_length=1)
    original_total_quantity: Decimal = Field(gt=0, le=MAX_ACTION_VALUE)
    original_limit_price: Decimal | None = Field(default=None, gt=0, le=MAX_ACTION_VALUE)
    original_tif: TimeInForce
    original_good_till_date_utc: datetime | None = None
    original_order_state_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    original_intent_sha256: str = Field(pattern=SHA256_PATTERN)
    proposal_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    original_maximum_liability: Decimal | None = Field(
        default=None, ge=0, le=MAX_ACTION_VALUE
    )

    @model_validator(mode="after")
    def validate_binding(self) -> "ContinuityOrderBinding":
        if not self.original_total_quantity.is_finite() or (
            self.original_limit_price is not None
            and not self.original_limit_price.is_finite()
        ) or (
            self.original_maximum_liability is not None
            and not self.original_maximum_liability.is_finite()
        ):
            raise ValueError("order numeric values must be finite")
        if self.original_good_till_date_utc is not None:
            _require_aware(
                self.original_good_till_date_utc, "original_good_till_date_utc"
            )
        if self.original_tif == TimeInForce.GTD and self.original_good_till_date_utc is None:
            raise ValueError("GTD binding requires original_good_till_date_utc")
        if self.original_tif != TimeInForce.GTD and self.original_good_till_date_utc is not None:
            raise ValueError("original_good_till_date_utc requires GTD")
        if self.binding_type == OrderBindingType.NEW_PROPOSAL:
            if self.proposal_sha256 is None:
                raise ValueError("NEW_PROPOSAL requires proposal_sha256")
            if any(value is not None for value in (self.ibkr_order_id, self.perm_id)):
                raise ValueError("NEW_PROPOSAL cannot claim broker-bound identifiers")
        else:
            if any(
                value is None
                for value in (
                    self.ibkr_order_id,
                    self.perm_id,
                    self.original_order_state_sha256,
                )
            ):
                raise ValueError("EXISTING_ORDER requires exact broker identity and state")
        return self


def _iter_actions(plan: "CodexOrderContinuityPlan"):
    yield plan.terminal_disposition
    for contingency in plan.contingencies:
        yield contingency.unavailable_data_action
        yield from contingency.state_actions.values()


class CodexOrderContinuityPlan(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["CODEX_ORDER_CONTINUITY_PLAN_V1"]
    plan_id: str = Field(min_length=1, max_length=128)
    plan_version: int = Field(gt=0)
    created_at_utc: datetime
    created_by_model: str = Field(min_length=1)
    model_attestation_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_cycle_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    input_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    epoch_id: str = Field(min_length=1)
    definition_sha256: str = Field(pattern=SHA256_PATTERN)
    clock_event_sha256: str = Field(pattern=SHA256_PATTERN)
    owner_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    predecessor_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    order_binding: ContinuityOrderBinding
    maximum_authorized_liability: Decimal = Field(ge=0, le=MAX_ACTION_VALUE)
    valid_from_utc: datetime
    plan_valid_until: datetime
    session_end_utc: datetime
    epoch_authority_end_utc: datetime
    authority_activation_condition: ContinuityCondition
    expiry_authority_mode: ExpiryAuthorityMode
    terminal_disposition: ContinuityExecutableAction
    contingencies: tuple[ContinuityContingency, ...] = Field(min_length=1, max_length=64)

    @property
    def sha256(self) -> str:
        return sha256_json(self)

    @model_validator(mode="after")
    def validate_plan(self) -> "CodexOrderContinuityPlan":
        for name in (
            "created_at_utc",
            "valid_from_utc",
            "plan_valid_until",
            "session_end_utc",
            "epoch_authority_end_utc",
        ):
            _require_aware(getattr(self, name), name)
        if not self.maximum_authorized_liability.is_finite():
            raise ValueError("maximum_authorized_liability must be finite")
        if (
            self.order_binding.original_maximum_liability is not None
            and self.order_binding.original_maximum_liability
            > self.maximum_authorized_liability
        ):
            raise ValueError(
                "original maximum liability exceeds maximum_authorized_liability"
            )
        if not (
            self.created_at_utc <= self.valid_from_utc < self.plan_valid_until
            <= self.epoch_authority_end_utc
        ):
            raise ValueError("plan validity must remain inside epoch authority")
        if self.session_end_utc > self.epoch_authority_end_utc:
            raise ValueError("session end exceeds epoch authority")
        if len({item.contingency_id for item in self.contingencies}) != len(
            self.contingencies
        ):
            raise ValueError("contingency_id values must be unique")
        if len({item.priority for item in self.contingencies}) != len(
            self.contingencies
        ):
            raise ValueError("contingency priorities must be unique")
        for item in self.contingencies:
            if item.valid_from_utc < self.valid_from_utc or (
                item.valid_until_utc > self.plan_valid_until
            ):
                raise ValueError("contingency validity exceeds plan validity")

        order_expiry = (
            self.order_binding.original_good_till_date_utc
            if self.order_binding.original_tif == TimeInForce.GTD
            else self.session_end_utc
            if self.order_binding.original_tif == TimeInForce.DAY
            else None
        )
        if order_expiry is not None:
            self._validate_order_expiry(order_expiry)
        for action in _iter_actions(self):
            if action.new_good_till_date_utc is not None:
                self._validate_order_expiry(action.new_good_till_date_utc)
        return self

    def _validate_order_expiry(self, order_expiry: datetime) -> None:
        if order_expiry > self.epoch_authority_end_utc:
            raise ValueError("order TIF exceeds epoch authority")
        if order_expiry > self.plan_valid_until and not (
            self.terminal_disposition.action_type == ContinuityActionType.RETAIN
            and self.terminal_disposition.retain_authority
            == RetainAuthority.RETAIN_UNTIL_ORDER_TIF
        ):
            raise ValueError(
                "order TIF beyond plan validity requires RETAIN_UNTIL_ORDER_TIF"
            )


class ContinuityFactEvidence(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    fact: ContinuityFactName
    source: str = Field(min_length=1)
    collected_at_utc: datetime
    max_age_seconds: Decimal = Field(gt=0, le=86400)
    canonical_value: Any
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class ContinuityFactSnapshot(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    collected_at_utc: datetime
    broker_time_utc: datetime
    facts: tuple[ContinuityFactEvidence, ...]
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class ContinuityEvaluation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(min_length=1)
    evaluated_at_utc: datetime
    plan_id: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    fact_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    authority_active: bool | None
    selected_contingency_id: str | None = None
    selected_action: ContinuityExecutableAction | None = None
    execution_ordinal: int | None = Field(default=None, gt=0)
    reason_codes: tuple[str, ...] = ()

    @property
    def action_sha256(self) -> str | None:
        if self.selected_action is None:
            return None
        return sha256_json(self.selected_action)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class ContinuityReview(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["CONTINUITY_REVIEW_V1"] = "CONTINUITY_REVIEW_V1"
    review_id: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    report_sha256: str = Field(pattern=SHA256_PATTERN)
    invocation_id: str = Field(min_length=1)
    accepted_result_sha256: str = Field(pattern=SHA256_PATTERN)
    disposition: ContinuityReviewDisposition
    reflection: str | None = None
    replacement_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


ContinuityCondition.model_rebuild()
ContinuityValueExpression.model_rebuild()
ContinuityExecutableAction.model_rebuild()
