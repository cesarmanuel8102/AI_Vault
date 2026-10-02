"""Typed authority for broker-validated maximum liability evidence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .continuity_models import SHA256_PATTERN


class LiabilityEvidenceSource(str, Enum):
    PAPER_WHAT_IF = "PAPER_WHAT_IF"
    PROVEN_EXACT_FORMULA = "PROVEN_EXACT_FORMULA"


class MaximumLiabilityRequirement(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    maximum_authorized_liability: Decimal = Field(ge=0)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    proposed_order_sha256: str = Field(pattern=SHA256_PATTERN)
    required_leg_identity_sha256: tuple[str, ...] = ()
    maximum_evidence_age_seconds: Decimal = Field(gt=0, le=300)

    @model_validator(mode="after")
    def validate_requirement(self) -> "MaximumLiabilityRequirement":
        if not self.maximum_authorized_liability.is_finite():
            raise ValueError("maximum_authorized_liability must be finite")
        if not self.maximum_evidence_age_seconds.is_finite():
            raise ValueError("maximum_evidence_age_seconds must be finite")
        if len(set(self.required_leg_identity_sha256)) != len(
            self.required_leg_identity_sha256
        ):
            raise ValueError("required liability leg identities must be unique")
        for value in self.required_leg_identity_sha256:
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("required liability leg identity must be sha256")
        return self


class MaximumLiabilityEvidence(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source: LiabilityEvidenceSource
    collected_at_utc: datetime
    fresh_until_utc: datetime
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    proposed_order_sha256: str = Field(pattern=SHA256_PATTERN)
    command_sha256: str = Field(pattern=SHA256_PATTERN)
    bounded: bool
    maximum_loss: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    covered_leg_identity_sha256: tuple[str, ...] = ()
    broker_evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_evidence(self) -> "MaximumLiabilityEvidence":
        for name in ("collected_at_utc", "fresh_until_utc"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.fresh_until_utc <= self.collected_at_utc:
            raise ValueError("fresh_until_utc must follow collected_at_utc")
        if self.bounded:
            if self.maximum_loss is None or not self.maximum_loss.is_finite():
                raise ValueError("bounded evidence requires finite maximum_loss")
        elif self.maximum_loss is not None:
            raise ValueError("unbounded evidence cannot claim maximum_loss")
        if len(set(self.covered_leg_identity_sha256)) != len(
            self.covered_leg_identity_sha256
        ):
            raise ValueError("covered liability leg identities must be unique")
        for value in self.covered_leg_identity_sha256:
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("covered liability leg identity must be sha256")
        return self


class LiabilityValidationResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason_codes: tuple[str, ...]
    maximum_loss: Decimal | None = None
    evidence_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


def validate_resolved_liability_authority(
    *,
    requirement: MaximumLiabilityRequirement,
    evidence: MaximumLiabilityEvidence | None,
    command_sha256: str,
    experiment_capital_boundary: Decimal,
    now_utc: datetime,
) -> LiabilityValidationResult:
    """Validate already-collected evidence without performing broker I/O."""

    if evidence is None:
        return LiabilityValidationResult(
            allowed=False,
            reason_codes=("LIABILITY_EVIDENCE_MISSING",),
        )
    reasons: list[str] = []
    if evidence.account_identity_sha256 != requirement.account_identity_sha256:
        reasons.append("LIABILITY_ACCOUNT_MISMATCH")
    if evidence.contract_identity_sha256 != requirement.contract_identity_sha256:
        reasons.append("LIABILITY_CONTRACT_MISMATCH")
    if evidence.proposed_order_sha256 != requirement.proposed_order_sha256:
        reasons.append("LIABILITY_ORDER_MISMATCH")
    if evidence.command_sha256 != command_sha256:
        reasons.append("LIABILITY_COMMAND_MISMATCH")
    if set(evidence.covered_leg_identity_sha256) != set(
        requirement.required_leg_identity_sha256
    ):
        reasons.append("LIABILITY_LEG_COVERAGE_INCOMPLETE")
    age_seconds = Decimal(str((now_utc - evidence.collected_at_utc).total_seconds()))
    if (
        now_utc > evidence.fresh_until_utc
        or age_seconds < 0
        or age_seconds > requirement.maximum_evidence_age_seconds
    ):
        reasons.append("LIABILITY_EVIDENCE_STALE")
    if not evidence.bounded or evidence.maximum_loss is None:
        reasons.append("LIABILITY_UNBOUNDED")
    else:
        if evidence.maximum_loss > requirement.maximum_authorized_liability:
            reasons.append("PLAN_LIABILITY_BOUND_EXCEEDED")
        if (
            not experiment_capital_boundary.is_finite()
            or experiment_capital_boundary < 0
            or evidence.maximum_loss > experiment_capital_boundary
        ):
            reasons.append("EXPERIMENT_CAPITAL_BOUNDARY_EXCEEDED")
    return LiabilityValidationResult(
        allowed=not reasons,
        reason_codes=tuple(reasons),
        maximum_loss=evidence.maximum_loss,
        evidence_sha256=evidence.broker_evidence_sha256,
    )
