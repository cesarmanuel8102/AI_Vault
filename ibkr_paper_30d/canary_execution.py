"""Bounded canary execution through the sole authoritative broker writer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json
from .canary_authority import (
    CanaryAuthorityValidator,
    CanaryBrokerLifecycleReceipt,
    CanaryExecutionTarget,
    CanaryLifecycleProjection,
    CanaryLifecycleRecorder,
)
from .canary_candidate import CanaryEntryTerms, CanaryFlatReturnPlan
from .multi_universe_models import (
    CanaryAuthorization,
    CanonicalContractIdentity,
    ProductFamilyKey,
    SHA256_PATTERN,
)


class _ExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


class CanaryExecutionRequest(_ExecutionModel):
    canary_id: str = Field(min_length=1)
    durable_sequence: int = Field(gt=0)
    execution_key: str = Field(min_length=1)
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family: ProductFamilyKey
    canonical_contract: CanonicalContractIdentity
    entry_terms: CanaryEntryTerms
    quantity: Decimal = Field(gt=0)
    maximum_debit_usd: Decimal = Field(ge=0)
    maximum_loss_usd: Decimal = Field(ge=0)
    fee_allowance_usd: Decimal = Field(ge=0)
    flat_return_plan: CanaryFlatReturnPlan
    created_at_utc: datetime

    @model_validator(mode="after")
    def _validate_scope(self) -> "CanaryExecutionRequest":
        if self.created_at_utc.tzinfo is None or self.created_at_utc.utcoffset() is None:
            raise ValueError("created_at_utc must be timezone-aware")
        if self.flat_return_plan.quantity != self.quantity:
            raise ValueError("flat-return quantity mismatch")
        if self.flat_return_plan.action == self.entry_terms.action:
            raise ValueError("flat-return action must oppose entry")
        return self


class CanaryExecutionResult(_ExecutionModel):
    status: str
    reason_codes: tuple[str, ...] = ()
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    projection: CanaryLifecycleProjection | None = None
    broker_write_boundary_crossed: bool = False


class CanaryRecoveryAction(str, Enum):
    RESUME_OBSERVATION = "RESUME_OBSERVATION"
    EXACT_RISK_REDUCTION = "EXACT_RISK_REDUCTION"
    TERMINAL_NO_FILL = "TERMINAL_NO_FILL"
    PASS = "PASS"
    UNCERTAIN_FREEZE = "UNCERTAIN_FREEZE"


class CanaryRecoveryDecision(_ExecutionModel):
    action: CanaryRecoveryAction
    reason_codes: tuple[str, ...] = ()
    submit_new_entry: bool = False
    freeze_ordinary_entries: bool = True


class CanaryExecutionAdapter:
    """Validate, invoke the writer-owned broker port, and chain receipts."""

    def __init__(
        self,
        *,
        begin_write: Callable[[str], bool],
        receipt_persister: Callable[[CanaryBrokerLifecycleReceipt], None] | None = None,
        now_utc: Callable[[], datetime] | None = None,
        writer_executor: Callable[
            [CanaryExecutionRequest, Any, Mapping[str, Any]], list[Any]
        ]
        | None = None,
    ) -> None:
        self.begin_write = begin_write
        self.receipt_persister = receipt_persister or (lambda _receipt: None)
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))
        self.writer_executor = writer_executor

    def _authority_reasons(
        self, request: CanaryExecutionRequest, evidence: Mapping[str, Any]
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        checks = (
            (evidence.get("transition_phase") == "CANARY_EXCLUSIVE", "CANARY_EXCLUSIVE_REQUIRED"),
            (evidence.get("ordinary_entry_authority") is False, "ORDINARY_ENTRY_AUTHORITY_MUST_BE_FROZEN"),
            (evidence.get("paper_only") is True, "POSSIBLE_LIVE_CONNECTION"),
            (evidence.get("fresh") is True, "CANARY_EVIDENCE_STALE"),
            (evidence.get("candidate_sha256") == request.candidate_sha256, "CANARY_CANDIDATE_MISMATCH"),
            (evidence.get("authorization_sha256") == request.authorization_sha256, "CANARY_AUTHORIZATION_MISMATCH"),
            (evidence.get("account_identity_sha256") == request.account_identity_sha256, "CANARY_ACCOUNT_MISMATCH"),
            (evidence.get("successor_definition_sha256") == request.successor_definition_sha256, "CANARY_SUCCESSOR_MISMATCH"),
            (evidence.get("writer_binding_sha256") == request.writer_binding_sha256, "CANARY_WRITER_MISMATCH"),
            (evidence.get("request_sha256") == request.sha256, "CANARY_REQUEST_MISMATCH"),
        )
        reasons.extend(reason for passed, reason in checks if not passed)
        authorization = evidence.get("authorization")
        if not isinstance(authorization, CanaryAuthorization):
            reasons.append("CANARY_AUTHORIZATION_MISSING")
        else:
            target = CanaryExecutionTarget(
                endpoint="PAPER" if evidence.get("paper_only") is True else "LIVE",
                account_identity_sha256=request.account_identity_sha256,
                successor_definition_sha256=request.successor_definition_sha256,
                product_family_sha256=request.product_family.sha256,
                contract_identity_sha256=request.canonical_contract.sha256,
                debit_usd=request.maximum_debit_usd,
                maximum_loss_usd=request.maximum_loss_usd,
                estimated_fees_usd=request.fee_allowance_usd,
                order_count=2,
                capital_replenishment_usd=Decimal("0"),
                sleeve_transfer_usd=Decimal("0"),
            )
            receipt = CanaryAuthorityValidator.validate(
                authorization, target, self.now_utc()
            )
            reasons.extend(receipt.reason_codes)
        return tuple(dict.fromkeys(reasons))

    def execute(
        self,
        request: CanaryExecutionRequest,
        broker: Any,
        evidence: Mapping[str, Any],
    ) -> CanaryExecutionResult:
        reasons = self._authority_reasons(request, evidence)
        if reasons:
            return CanaryExecutionResult(
                status="BLOCKED", reason_codes=reasons, request_sha256=request.sha256
            )
        recorder = CanaryLifecycleRecorder(
            request.canary_id,
            request.account_identity_sha256,
            request.product_family.sha256,
            request.canonical_contract.sha256,
        )
        submitted = CanaryBrokerLifecycleReceipt(
            canary_id=request.canary_id,
            step="SUBMITTED",
            endpoint="PAPER",
            account_identity_sha256=request.account_identity_sha256,
            product_family_sha256=request.product_family.sha256,
            contract_identity_sha256=request.canonical_contract.sha256,
            broker_event_id_sha256=sha256_json(
                {"request_sha256": request.sha256, "step": "SUBMITTED"}
            ),
            broker_snapshot_sha256=sha256_json(
                {"request_sha256": request.sha256, "pre_write": True}
            ),
            previous_receipt_sha256=None,
            observed_at_utc=self.now_utc(),
            open_orders=0,
            positions=0,
            economics_reconciled=False,
        )
        try:
            recorder.record(submitted)
            self.receipt_persister(submitted)
        except Exception:
            return CanaryExecutionResult(
                status="BLOCKED",
                reason_codes=("CANARY_ATTEMPT_PERSISTENCE_FAILED",),
                request_sha256=request.sha256,
            )
        if not self.begin_write(request.execution_key):
            return CanaryExecutionResult(
                status="BLOCKED",
                reason_codes=("CANARY_REQUEST_EXPIRED",),
                request_sha256=request.sha256,
            )
        try:
            executor = self.writer_executor or broker.execute_canary_through_writer
            raw_events = list(executor(request, broker, evidence)) if self.writer_executor else list(executor(request, evidence))
        except Exception:
            return CanaryExecutionResult(
                status="UNCERTAIN",
                reason_codes=("CANARY_STATE_UNCERTAIN",),
                request_sha256=request.sha256,
                broker_write_boundary_crossed=True,
            )
        seen: set[str] = set()
        try:
            for index, raw in enumerate(raw_events, 1):
                if raw[0] == "SUBMITTED":
                    continue
                event_key = sha256_json(raw)
                if event_key in seen:
                    continue
                seen.add(event_key)
                step, open_orders, positions, economics = raw
                receipt = CanaryBrokerLifecycleReceipt(
                    canary_id=request.canary_id,
                    step=step,
                    endpoint="PAPER",
                    account_identity_sha256=request.account_identity_sha256,
                    product_family_sha256=request.product_family.sha256,
                    contract_identity_sha256=request.canonical_contract.sha256,
                    broker_event_id_sha256=event_key,
                    broker_snapshot_sha256=sha256_json(
                        {"event": raw, "request_sha256": request.sha256}
                    ),
                    previous_receipt_sha256=recorder.last_receipt_sha256,
                    observed_at_utc=self.now_utc()
                    + timedelta(microseconds=index + 1),
                    open_orders=open_orders,
                    positions=positions,
                    economics_reconciled=economics,
                )
                projection = recorder.record(receipt)
                self.receipt_persister(receipt)
        except Exception:
            return CanaryExecutionResult(
                status="UNCERTAIN",
                reason_codes=("CANARY_STATE_UNCERTAIN",),
                request_sha256=request.sha256,
                projection=recorder.projection(),
                broker_write_boundary_crossed=True,
            )
        projection = recorder.projection()
        status = (
            "PASS"
            if projection.status == "PASS"
            else "TERMINAL_NO_FILL"
            if projection.terminal_no_fill
            else "IN_PROGRESS"
        )
        return CanaryExecutionResult(
            status=status,
            request_sha256=request.sha256,
            projection=projection,
            broker_write_boundary_crossed=True,
        )


def recover_canary(
    db: Any,
    broker_snapshot: Mapping[str, Any],
    request: CanaryExecutionRequest,
) -> CanaryRecoveryDecision:
    del db
    if broker_snapshot.get("identity_exact") is not True:
        return CanaryRecoveryDecision(
            action=CanaryRecoveryAction.UNCERTAIN_FREEZE,
            reason_codes=("CANARY_IDENTITY_AMBIGUOUS",),
        )
    open_order = broker_snapshot.get("open_order") is True
    quantity = Decimal(str(broker_snapshot.get("position_quantity", "0")))
    if open_order and quantity != 0:
        return CanaryRecoveryDecision(
            action=CanaryRecoveryAction.UNCERTAIN_FREEZE,
            reason_codes=("CANARY_ORDER_POSITION_OVERLAP",),
        )
    if open_order:
        return CanaryRecoveryDecision(action=CanaryRecoveryAction.RESUME_OBSERVATION)
    if quantity != 0:
        if abs(quantity) > request.quantity:
            return CanaryRecoveryDecision(
                action=CanaryRecoveryAction.UNCERTAIN_FREEZE,
                reason_codes=("CANARY_POSITION_SIZE_MISMATCH",),
            )
        return CanaryRecoveryDecision(action=CanaryRecoveryAction.EXACT_RISK_REDUCTION)
    if broker_snapshot.get("economics_reconciled") is True:
        return CanaryRecoveryDecision(action=CanaryRecoveryAction.PASS)
    if broker_snapshot.get("terminal_no_fill") is True:
        return CanaryRecoveryDecision(action=CanaryRecoveryAction.TERMINAL_NO_FILL)
    return CanaryRecoveryDecision(
        action=CanaryRecoveryAction.UNCERTAIN_FREEZE,
        reason_codes=("CANARY_DURABLE_STATE_INCOMPLETE",),
    )
