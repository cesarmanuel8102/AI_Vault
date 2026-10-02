"""Fail-closed production authority validation immediately before broker writes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .broker_write_coordinator import AuthorizedBrokerCommand, BrokerCommandType
from .canonical import sha256_json
from .continuity_liability import (
    LiabilityValidationResult,
    MaximumLiabilityEvidence,
    validate_resolved_liability_authority,
)
from .continuity_models import SHA256_PATTERN


class ProductionAuthoritySnapshot(BaseModel, frozen=True):
    """One database-authoritative read of every mutable write prerequisite."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    observed_at_utc: datetime
    lock_owned_by_process: bool
    approved_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime_provenance_valid: bool
    environment: str = Field(min_length=1)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    owner_authorization_valid: bool
    epoch_id: str = Field(min_length=1)
    clock_active: bool
    kill_switch_clear: bool
    auditor_gate_pass: bool
    market_data_gate_pass: bool
    continuity_schema_valid: bool
    authority_chains_valid: bool
    active_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    binding_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    provider_state_allows: bool
    accepted_result_sha256: str = Field(pattern=SHA256_PATTERN)
    review_allows: bool
    execution_count: int = Field(ge=0)
    maximum_execution_count: int = Field(gt=0)
    used_execution_keys: tuple[str, ...]
    order_state_sha256: str = Field(pattern=SHA256_PATTERN)
    positions_sha256: str = Field(pattern=SHA256_PATTERN)
    executions_sha256: str = Field(pattern=SHA256_PATTERN)
    experiment_capital_boundary: Decimal
    sqlite_write_transaction_active: bool

    @model_validator(mode="after")
    def validate_snapshot(self) -> "ProductionAuthoritySnapshot":
        if self.observed_at_utc.tzinfo is None or self.observed_at_utc.utcoffset() is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        if len(set(self.used_execution_keys)) != len(self.used_execution_keys):
            raise ValueError("used_execution_keys must be unique")
        return self

    @property
    def sha256(self) -> str:
        return sha256_json(self)

    @property
    def compatibility_sha256(self) -> str:
        values = self.model_dump(mode="json")
        values.pop("snapshot_id")
        values.pop("observed_at_utc")
        return sha256_json(values)


class ProductionBrokerEvidence(BaseModel, frozen=True):
    """Fresh, authenticated PAPER state collected outside a DB write transaction."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    collected_at_utc: datetime
    broker_time_utc: datetime
    fresh_until_utc: datetime
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    all_order_visibility: bool
    open_orders_sha256: str = Field(pattern=SHA256_PATTERN)
    positions_sha256: str = Field(pattern=SHA256_PATTERN)
    executions_sha256: str = Field(pattern=SHA256_PATTERN)
    target_order_state_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_evidence(self) -> "ProductionBrokerEvidence":
        for name in ("collected_at_utc", "broker_time_utc", "fresh_until_utc"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.fresh_until_utc <= self.collected_at_utc:
            raise ValueError("fresh_until_utc must follow collected_at_utc")
        return self


class ProductionAuthorityDecision(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason_codes: tuple[str, ...]
    authority_snapshot: ProductionAuthoritySnapshot
    authority_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    broker_evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    liability_result: LiabilityValidationResult | None = None


class ProductionAuthorityValidator:
    """Re-read mutable authority and validate already-collected broker evidence."""

    def __init__(
        self,
        *,
        snapshot_reader: Callable[[Any], ProductionAuthoritySnapshot],
        expected_approved_head: str | None = None,
    ) -> None:
        if expected_approved_head is not None and (
            len(expected_approved_head) != 40
            or any(character not in "0123456789abcdef" for character in expected_approved_head)
        ):
            raise ValueError("expected_approved_head must be a git sha1")
        self._snapshot_reader = snapshot_reader
        self._expected_approved_head = expected_approved_head

    def validate_before_write(
        self,
        *,
        request: Any,
        broker_evidence: ProductionBrokerEvidence,
        liability_evidence: MaximumLiabilityEvidence | None,
        now_utc: datetime,
        prior_authority_snapshot: ProductionAuthoritySnapshot | None = None,
    ) -> ProductionAuthorityDecision:
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError("now_utc must be timezone-aware")
        snapshot = self._snapshot_reader(request)
        if not isinstance(snapshot, ProductionAuthoritySnapshot):
            raise TypeError("snapshot_reader must return ProductionAuthoritySnapshot")

        reasons: list[str] = []
        self._validate_snapshot(request=request, snapshot=snapshot, reasons=reasons)
        self._validate_broker(
            request=request,
            snapshot=snapshot,
            evidence=broker_evidence,
            now_utc=now_utc,
            reasons=reasons,
        )

        liability_result: LiabilityValidationResult | None = None
        if isinstance(request, AuthorizedBrokerCommand) and request.command_type == BrokerCommandType.MODIFY:
            liability_result = validate_resolved_liability_authority(
                requirement=request.liability_requirement,
                evidence=liability_evidence,
                command_sha256=request.sha256,
                experiment_capital_boundary=snapshot.experiment_capital_boundary,
                now_utc=now_utc,
            )
            reasons.extend(liability_result.reason_codes)

        if (
            prior_authority_snapshot is not None
            and snapshot.compatibility_sha256
            != prior_authority_snapshot.compatibility_sha256
        ):
            reasons.append("AUTHORITY_STATE_CHANGED_DURING_VALIDATION")

        reason_codes = tuple(dict.fromkeys(reasons))
        return ProductionAuthorityDecision(
            allowed=not reason_codes,
            reason_codes=reason_codes,
            authority_snapshot=snapshot,
            authority_snapshot_sha256=snapshot.sha256,
            broker_evidence_sha256=broker_evidence.evidence_sha256,
            liability_result=liability_result,
        )

    def _validate_snapshot(
        self,
        *,
        request: Any,
        snapshot: ProductionAuthoritySnapshot,
        reasons: list[str],
    ) -> None:
        request_head = getattr(request, "approved_head", self._expected_approved_head)
        accepted_result_sha256 = getattr(request, "accepted_result_sha256", None)
        checks = (
            (not snapshot.lock_owned_by_process, "EXECUTION_LOCK_NOT_OWNED"),
            (request_head is None, "APPROVED_HEAD_BINDING_MISSING"),
            (
                request_head is not None and snapshot.approved_head != request_head,
                "APPROVED_HEAD_MISMATCH",
            ),
            (not snapshot.runtime_provenance_valid, "RUNTIME_PROVENANCE_BLOCK"),
            (snapshot.environment != "PAPER", "PAPER_ENVIRONMENT_REQUIRED"),
            (
                snapshot.account_identity_sha256 != request.account_identity_sha256,
                "PAPER_ACCOUNT_MISMATCH",
            ),
            (not snapshot.owner_authorization_valid, "OWNER_AUTHORIZATION_BLOCK"),
            (snapshot.epoch_id != request.epoch_id, "EPOCH_BINDING_MISMATCH"),
            (not snapshot.clock_active, "EXPERIMENT_CLOCK_BLOCK"),
            (not snapshot.kill_switch_clear, "KILL_SWITCH_TRIGGERED"),
            (not snapshot.auditor_gate_pass, "AUDITOR_GATE_BLOCK"),
            (not snapshot.market_data_gate_pass, "MARKET_DATA_GATE_BLOCK"),
            (not snapshot.continuity_schema_valid, "CONTINUITY_SCHEMA_BLOCK"),
            (not snapshot.authority_chains_valid, "AUTHORITY_CHAIN_BLOCK"),
            (not snapshot.provider_state_allows, "PROVIDER_STATE_BLOCK"),
            (
                accepted_result_sha256 is not None
                and snapshot.accepted_result_sha256 != accepted_result_sha256,
                "ACCEPTED_DECISION_MISMATCH",
            ),
            (not snapshot.review_allows, "CONTINUITY_REVIEW_BLOCK"),
            (
                snapshot.execution_count >= snapshot.maximum_execution_count,
                "MAXIMUM_EXECUTION_COUNT_REACHED",
            ),
            (
                request.execution_key in snapshot.used_execution_keys,
                "EXECUTION_KEY_ALREADY_USED",
            ),
            (
                snapshot.sqlite_write_transaction_active,
                "SQLITE_WRITE_TRANSACTION_ACTIVE",
            ),
        )
        reasons.extend(reason for failed, reason in checks if failed)

        try:
            capital = Decimal(snapshot.experiment_capital_boundary)
            valid_capital = capital.is_finite() and capital > 0
        except (InvalidOperation, TypeError, ValueError):
            valid_capital = False
        if not valid_capital:
            reasons.append("EXPERIMENT_CAPITAL_BOUNDARY_INVALID")

        if isinstance(request, AuthorizedBrokerCommand):
            if snapshot.active_plan_sha256 != request.plan_sha256:
                reasons.append("ACTIVE_PLAN_MISMATCH")
            if snapshot.binding_plan_sha256 != request.plan_sha256:
                reasons.append("PLAN_BINDING_MISMATCH")
            if snapshot.order_state_sha256 != request.observed_state_sha256:
                reasons.append("ORDER_STATE_CHANGED")

    @staticmethod
    def _validate_broker(
        *,
        request: Any,
        snapshot: ProductionAuthoritySnapshot,
        evidence: ProductionBrokerEvidence,
        now_utc: datetime,
        reasons: list[str],
    ) -> None:
        if now_utc < evidence.collected_at_utc or now_utc > evidence.fresh_until_utc:
            reasons.append("BROKER_EVIDENCE_STALE")
        if not evidence.all_order_visibility:
            reasons.append("ALL_ORDER_VISIBILITY_UNCERTAIN")
        if evidence.account_identity_sha256 != request.account_identity_sha256:
            reasons.append("BROKER_ACCOUNT_MISMATCH")
        if evidence.positions_sha256 != snapshot.positions_sha256:
            reasons.append("BROKER_POSITIONS_CHANGED")
        if evidence.executions_sha256 != snapshot.executions_sha256:
            reasons.append("BROKER_EXECUTIONS_CHANGED")
        if isinstance(request, AuthorizedBrokerCommand):
            if evidence.target_order_state_sha256 != request.observed_state_sha256:
                reasons.append("BROKER_ORDER_STATE_CHANGED")
            if evidence.target_order_state_sha256 != snapshot.order_state_sha256:
                reasons.append("BROKER_DATABASE_ORDER_STATE_MISMATCH")
