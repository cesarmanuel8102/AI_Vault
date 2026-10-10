"""Bounded PAPER canary authority and lifecycle evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
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


class CanaryLifecycleProjection(_CanaryModel):
    canary_id: str
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
        self, canary_id: str, product_family_sha256: str, contract_identity_sha256: str
    ) -> None:
        self.canary_id = canary_id
        self.product_family_sha256 = product_family_sha256
        self.contract_identity_sha256 = contract_identity_sha256
        self._events: list[tuple[str, str]] = []
        self._terminal_no_fill = False

    @staticmethod
    def _validate_hash(value: str) -> None:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise CanaryLifecycleError("CANARY_EVIDENCE_HASH_INVALID")

    def _record(self, step: str, evidence_sha256: str) -> CanaryLifecycleProjection:
        self._validate_hash(evidence_sha256)
        if self._terminal_no_fill:
            raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
        expected_index = len(self._events)
        if expected_index >= len(self._SEQUENCE) or self._SEQUENCE[expected_index] != step:
            raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
        self._events.append((step, evidence_sha256))
        return self.projection()

    def record_submit(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("SUBMITTED", evidence_sha256)

    def record_bind(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("BROKER_BOUND", evidence_sha256)

    def record_entry_fill(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("ENTRY_FILL", evidence_sha256)

    def record_position(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("POSITION_VISIBLE", evidence_sha256)

    def record_management(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("MANAGEMENT_OBSERVED", evidence_sha256)

    def record_exit_fill(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        return self._record("EXIT_FILL", evidence_sha256)

    def record_flat_state(
        self, evidence_sha256: str, *, open_orders: int, positions: int
    ) -> CanaryLifecycleProjection:
        if open_orders != 0 or positions != 0:
            raise CanaryLifecycleError("CANARY_NOT_FLAT")
        return self._record("FLAT_STATE", evidence_sha256)

    def record_economics(
        self, evidence_sha256: str, *, reconciled: bool
    ) -> CanaryLifecycleProjection:
        if not reconciled:
            raise CanaryLifecycleError("CANARY_ECONOMICS_NOT_RECONCILED")
        return self._record("ECONOMICS_RECONCILED", evidence_sha256)

    def record_terminal_no_fill(self, evidence_sha256: str) -> CanaryLifecycleProjection:
        self._validate_hash(evidence_sha256)
        if tuple(step for step, _ in self._events) != (
            "SUBMITTED",
            "BROKER_BOUND",
        ):
            raise CanaryLifecycleError("LIFECYCLE_STEP_OUT_OF_ORDER")
        self._events.append(("TERMINAL_NO_FILL", evidence_sha256))
        self._terminal_no_fill = True
        return self.projection()

    def projection(self) -> CanaryLifecycleProjection:
        completed = tuple(step for step, _ in self._events)
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
            product_family_sha256=self.product_family_sha256,
            contract_identity_sha256=self.contract_identity_sha256,
            status=status,
            completed_steps=completed,
            full_lifecycle_verified=full,
            flat="FLAT_STATE" in completed,
            terminal_no_fill=self._terminal_no_fill,
            terminal_event_sha256=(None if not self._events else self._events[-1][1]),
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
