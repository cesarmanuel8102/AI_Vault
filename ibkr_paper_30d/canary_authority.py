"""Bounded PAPER canary authority and lifecycle evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json
from .multi_universe_models import CanaryAuthorization, SHA256_PATTERN


class _CanaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class CanaryExecutionTarget(_CanaryModel):
    endpoint: str = Field(min_length=1)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    debit_usd: Decimal = Field(ge=0)
    maximum_loss_usd: Decimal = Field(ge=0)
    estimated_fees_usd: Decimal = Field(ge=0)
    order_count: int = Field(gt=0)
    capital_replenishment_usd: Decimal = Field(ge=0)
    sleeve_transfer_usd: Decimal = Field(ge=0)


class CanaryAuthorityReceipt(_CanaryModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    authorization_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    target_sha256: str = Field(pattern=SHA256_PATTERN)
    freeze_new_order_authority: bool


class CanaryAuthorityValidator:
    @staticmethod
    def validate(
        authorization: CanaryAuthorization | None,
        target: CanaryExecutionTarget,
        now_utc: datetime,
    ) -> CanaryAuthorityReceipt:
        reasons: set[str] = set()
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            reasons.add("CANARY_TIME_INVALID")
        if target.endpoint.upper() != "PAPER":
            reasons.add("POSSIBLE_LIVE_CONNECTION")
        if authorization is None:
            reasons.add("CANARY_AUTHORIZATION_MISSING")
        else:
            if now_utc < authorization.issued_at_utc or now_utc >= authorization.expires_at_utc:
                reasons.add("CANARY_AUTHORIZATION_EXPIRED")
            if target.account_identity_sha256 != authorization.account_identity_sha256:
                reasons.add("CANARY_ACCOUNT_MISMATCH")
            if (
                target.successor_definition_sha256
                != authorization.successor_definition_sha256
            ):
                reasons.add("CANARY_SUCCESSOR_MISMATCH")
            if target.product_family_sha256 != authorization.product_family_sha256:
                reasons.add("CANARY_FAMILY_MISMATCH")
            if target.contract_identity_sha256 not in set(
                authorization.contract_scope_sha256
            ):
                reasons.add("CANARY_CONTRACT_SCOPE_MISMATCH")
            if target.debit_usd > authorization.maximum_debit_usd:
                reasons.add("CANARY_DEBIT_EXCEEDED")
            if target.maximum_loss_usd > authorization.maximum_loss_usd:
                reasons.add("CANARY_LOSS_EXCEEDED")
            if target.estimated_fees_usd > authorization.fee_allowance_usd:
                reasons.add("CANARY_FEES_EXCEEDED")
            if target.order_count > authorization.maximum_order_count:
                reasons.add("CANARY_ORDER_COUNT_EXCEEDED")
        if target.capital_replenishment_usd != 0:
            reasons.add("CANARY_REPLENISHMENT_FORBIDDEN")
        if target.sleeve_transfer_usd != 0:
            reasons.add("CANARY_SLEEVE_TRANSFER_FORBIDDEN")
        reason_codes = tuple(sorted(reasons))
        return CanaryAuthorityReceipt(
            status="BLOCK" if reason_codes else "PASS",
            reason_codes=reason_codes,
            authorization_sha256=None if authorization is None else authorization.sha256,
            target_sha256=target.sha256,
            freeze_new_order_authority=bool(reason_codes),
        )


class CanaryLifecycleError(RuntimeError):
    pass


CanaryLifecycleStep = Literal[
    "SUBMITTED",
    "BROKER_BOUND",
    "ENTRY_FILL",
    "POSITION_VISIBLE",
    "MANAGEMENT_OBSERVED",
    "EXIT_FILL",
    "FLAT_STATE",
    "ECONOMICS_RECONCILED",
    "TERMINAL_NO_FILL",
]


class CanaryBrokerLifecycleReceipt(_CanaryModel):
    schema: Literal["CANARY_BROKER_LIFECYCLE_RECEIPT_V1"] = (
        "CANARY_BROKER_LIFECYCLE_RECEIPT_V1"
    )
    canary_id: str = Field(min_length=1)
    step: CanaryLifecycleStep
    endpoint: Literal["PAPER"]
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_event_id_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    previous_receipt_sha256: str | None = Field(
        default=None, pattern=SHA256_PATTERN
    )
    observed_at_utc: datetime
    open_orders: int = Field(ge=0)
    positions: int = Field(ge=0)
    economics_reconciled: bool = False

    @model_validator(mode="after")
    def validate_broker_state(self) -> "CanaryBrokerLifecycleReceipt":
        if (
            self.observed_at_utc.tzinfo is None
            or self.observed_at_utc.utcoffset() is None
            or self.observed_at_utc.astimezone(timezone.utc).utcoffset()
            != timedelta(0)
        ):
            raise ValueError("observed_at_utc must be timezone-aware")
        if self.step in {"FLAT_STATE", "ECONOMICS_RECONCILED"} and (
            self.open_orders != 0 or self.positions != 0
        ):
            raise ValueError("terminal canary receipt must prove flat state")
        if self.step == "ECONOMICS_RECONCILED":
            if self.economics_reconciled is not True:
                raise ValueError("economics receipt must prove reconciliation")
        elif self.economics_reconciled:
            raise ValueError("only economics receipt may claim reconciliation")
        if self.step == "TERMINAL_NO_FILL" and (
            self.open_orders != 0 or self.positions != 0
        ):
            raise ValueError("terminal no-fill receipt must prove flat state")
        return self


class CanaryLifecycleProjection(_CanaryModel):
    canary_id: str
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["EMPTY", "IN_PROGRESS", "TRANSMIT_ONLY", "PASS"]
    completed_steps: tuple[str, ...]
    full_lifecycle_verified: bool
    flat: bool
    terminal_no_fill: bool
    terminal_event_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class CanaryLifecycleRecorder:
    _SEQUENCE = (
        "SUBMITTED",
        "BROKER_BOUND",
        "ENTRY_FILL",
        "POSITION_VISIBLE",
        "MANAGEMENT_OBSERVED",
        "EXIT_FILL",
        "FLAT_STATE",
        "ECONOMICS_RECONCILED",
    )

    def __init__(
        self,
        canary_id: str,
        account_identity_sha256: str,
        product_family_sha256: str,
        contract_identity_sha256: str,
    ) -> None:
        self.canary_id = canary_id
        self.account_identity_sha256 = account_identity_sha256
        self.product_family_sha256 = product_family_sha256
        self.contract_identity_sha256 = contract_identity_sha256
        self._events: list[CanaryBrokerLifecycleReceipt] = []
        self._terminal_no_fill = False

    @property
    def sequence(self) -> tuple[str, ...]:
        return self._SEQUENCE

    @property
    def last_receipt_sha256(self) -> str | None:
        return None if not self._events else self._events[-1].sha256

    def record(
        self, receipt: CanaryBrokerLifecycleReceipt
    ) -> CanaryLifecycleProjection:
        if not isinstance(receipt, CanaryBrokerLifecycleReceipt):
            raise TypeError("CanaryBrokerLifecycleReceipt required")
        if self._terminal_no_fill:
            raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
        if (
            receipt.canary_id != self.canary_id
            or receipt.account_identity_sha256 != self.account_identity_sha256
            or receipt.product_family_sha256 != self.product_family_sha256
            or receipt.contract_identity_sha256 != self.contract_identity_sha256
        ):
            raise CanaryLifecycleError("CANARY_RECEIPT_IDENTITY_MISMATCH")
        if receipt.previous_receipt_sha256 != self.last_receipt_sha256:
            raise CanaryLifecycleError("CANARY_RECEIPT_CHAIN_MISMATCH")
        if self._events and receipt.observed_at_utc <= self._events[-1].observed_at_utc:
            raise CanaryLifecycleError("CANARY_RECEIPT_TIME_NOT_MONOTONIC")
        if receipt.step == "TERMINAL_NO_FILL":
            if tuple(item.step for item in self._events) != (
                "SUBMITTED",
                "BROKER_BOUND",
            ):
                raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
            self._events.append(receipt)
            self._terminal_no_fill = True
            return self.projection()
        expected_index = len(self._events)
        if (
            expected_index >= len(self._SEQUENCE)
            or self._SEQUENCE[expected_index] != receipt.step
        ):
            raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
        self._events.append(receipt)
        return self.projection()

    def projection(self) -> CanaryLifecycleProjection:
        completed = tuple(item.step for item in self._events)
        full = completed == self._SEQUENCE
        status = (
            "PASS"
            if full
            else "TRANSMIT_ONLY"
            if self._terminal_no_fill
            else "IN_PROGRESS"
            if completed
            else "EMPTY"
        )
        return CanaryLifecycleProjection(
            canary_id=self.canary_id,
            account_identity_sha256=self.account_identity_sha256,
            product_family_sha256=self.product_family_sha256,
            contract_identity_sha256=self.contract_identity_sha256,
            status=status,
            completed_steps=completed,
            full_lifecycle_verified=full,
            flat="FLAT_STATE" in completed,
            terminal_no_fill=self._terminal_no_fill,
            terminal_event_sha256=self.last_receipt_sha256,
        )


class RollbackDecision(_CanaryModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    total_required_seconds: Decimal
    earliest_deadline_seconds: Decimal


class RollbackEnvelope:
    @staticmethod
    def evaluate(
        detection_latency: timedelta,
        restoration_latency: timedelta,
        safety_margin: timedelta,
        earliest_deadline: timedelta,
    ) -> RollbackDecision:
        values = (
            detection_latency.total_seconds(),
            restoration_latency.total_seconds(),
            safety_margin.total_seconds(),
            earliest_deadline.total_seconds(),
        )
        total = sum(values[:3])
        safe = all(value >= 0 for value in values) and total < values[3]
        return RollbackDecision(
            status="PASS" if safe else "BLOCK",
            reason_codes=() if safe else ("ROLLBACK_ENVELOPE_UNSAFE",),
            total_required_seconds=Decimal(str(total)),
            earliest_deadline_seconds=Decimal(str(values[3])),
        )


class MaintenanceSafetyState(_CanaryModel):
    day1_open_order_count: int = Field(ge=0)
    day1_uncovered_position_count: int = Field(ge=0)
    writer_count: int = Field(ge=0)
    broker_state_certain: bool


class MaintenanceDecision(_CanaryModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    day1_liquidation_permitted: Literal[False] = False
    freeze_new_order_authority: bool


class CanaryMaintenanceGate:
    @staticmethod
    def evaluate(state: MaintenanceSafetyState) -> MaintenanceDecision:
        reasons: list[str] = []
        if state.day1_open_order_count:
            reasons.append("DAY1_OPEN_ORDER_PRESENT")
        if state.day1_uncovered_position_count:
            reasons.append("DAY1_UNCOVERED_POSITION_PRESENT")
        if state.writer_count != 1:
            reasons.append("SECOND_WRITER_PRESENT")
        if not state.broker_state_certain:
            reasons.append("BROKER_STATE_UNCERTAIN")
        return MaintenanceDecision(
            status="BLOCK" if reasons else "PASS",
            reason_codes=tuple(reasons),
            freeze_new_order_authority=bool(reasons),
        )
