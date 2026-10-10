"""Model-authored, read-only discovery contract for the continuous canary."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import sha256_json
from .multi_universe_models import (
    CanaryAuthorization,
    CapitalSleeve,
    CanonicalContractIdentity,
    ContractOwnershipGroup,
    GIT_HEAD_PATTERN,
    ProductFamilyKey,
    SHA256_PATTERN,
)


class _CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @property
    def sha256(self) -> str:
        return sha256_json(self)


def _require_utc(value: datetime, field_name: str) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
        or value.astimezone(timezone.utc).utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be timezone-aware")


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None or result.utcoffset() is None:
        return None
    return result.astimezone(timezone.utc)


class CanaryEntryTerms(_CandidateModel):
    action: Literal["BUY", "SELL"]
    order_type: str = Field(min_length=1)
    limit_price: Decimal | None = Field(default=None, gt=0)
    time_in_force: str = Field(min_length=1)
    outside_regular_hours: bool


class CanaryFlatReturnPlan(_CandidateModel):
    action: Literal["BUY", "SELL"]
    order_type: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    limit_price_rule: str = Field(min_length=1)
    deadline_utc: datetime
    terminal_state: Literal["FLAT"]

    def model_post_init(self, __context: Any) -> None:
        _require_utc(self.deadline_utc, "deadline_utc")


class CanaryCandidateProposal(_CandidateModel):
    candidate_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    invocation_sha256: str = Field(pattern=SHA256_PATTERN)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)
    product_family: ProductFamilyKey
    canonical_contract: CanonicalContractIdentity
    contract_group: ContractOwnershipGroup
    entry_terms: CanaryEntryTerms
    quantity: Decimal = Field(gt=0)
    maximum_debit_usd: Decimal = Field(ge=0)
    maximum_loss_usd: Decimal = Field(ge=0)
    fee_allowance_usd: Decimal = Field(ge=0)
    created_at_utc: datetime
    expires_at_utc: datetime
    flat_return_plan: CanaryFlatReturnPlan

    @model_validator(mode="after")
    def _validate_exact_scope(self) -> "CanaryCandidateProposal":
        _require_utc(self.created_at_utc, "created_at_utc")
        _require_utc(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.created_at_utc:
            raise ValueError("candidate expiry must follow creation")
        if self.flat_return_plan.deadline_utc > self.expires_at_utc:
            raise ValueError("flat-return deadline exceeds candidate expiry")
        if self.contract_group.sleeve is not CapitalSleeve.CONTINUOUS_SLEEVE:
            raise ValueError("canary candidate must use continuous sleeve")
        if self.contract_group.parent_contract != self.canonical_contract:
            raise ValueError("candidate contract group parent mismatch")
        if self.flat_return_plan.quantity != self.quantity:
            raise ValueError("flat-return quantity must equal candidate quantity")
        if self.flat_return_plan.action == self.entry_terms.action:
            raise ValueError("flat-return action must oppose entry action")
        if self.maximum_loss_usd > self.maximum_debit_usd + self.fee_allowance_usd:
            raise ValueError("candidate loss exceeds bounded debit plus fees")
        return self


class CanaryCandidateValidationReceipt(_CandidateModel):
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    proposal_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class OwnerPilotAuthorization(_CandidateModel):
    authorization_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_head: str = Field(pattern=GIT_HEAD_PATTERN)
    maximum_debit_usd: Decimal = Field(ge=0)
    maximum_loss_usd: Decimal = Field(ge=0)
    fee_allowance_usd: Decimal = Field(ge=0)
    maximum_order_count: int = Field(ge=2)
    issued_at_utc: datetime
    expires_at_utc: datetime

    @model_validator(mode="after")
    def _validate_window(self) -> "OwnerPilotAuthorization":
        _require_utc(self.issued_at_utc, "issued_at_utc")
        _require_utc(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("owner pilot authorization window invalid")
        return self


class CanaryDiscoveryOutcome(_CandidateModel):
    decision: Literal["CANDIDATE", "NO_CANDIDATE"]
    invocation_sha256: str = Field(pattern=SHA256_PATTERN)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    transcript_sha256: str = Field(pattern=SHA256_PATTERN)
    proposal: CanaryCandidateProposal | None = None

    @model_validator(mode="after")
    def _validate_decision(self) -> "CanaryDiscoveryOutcome":
        if (self.decision == "CANDIDATE") != (self.proposal is not None):
            raise ValueError("candidate discovery decision/payload mismatch")
        return self


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def validate_canary_candidate(
    proposal: CanaryCandidateProposal,
    *,
    read_only_capability_evidence: Mapping[str, Any],
    now_utc: datetime,
) -> CanaryCandidateValidationReceipt:
    _require_utc(now_utc, "now_utc")
    evidence = dict(read_only_capability_evidence)
    reasons: list[str] = []
    comparisons = (
        ("invocation_id", proposal.invocation_id, "CANARY_INVOCATION_MISMATCH"),
        (
            "invocation_sha256",
            proposal.invocation_sha256,
            "CANARY_INVOCATION_HASH_MISMATCH",
        ),
        ("result_sha256", proposal.result_sha256, "CANARY_RESULT_HASH_MISMATCH"),
        (
            "account_identity_sha256",
            proposal.account_identity_sha256,
            "CANARY_ACCOUNT_MISMATCH",
        ),
        (
            "successor_definition_sha256",
            proposal.successor_definition_sha256,
            "CANARY_SUCCESSOR_MISMATCH",
        ),
        ("approved_head", proposal.approved_head, "CANARY_HEAD_MISMATCH"),
        (
            "product_family_sha256",
            proposal.product_family.sha256,
            "CANARY_FAMILY_MISMATCH",
        ),
        (
            "contract_identity_sha256",
            proposal.canonical_contract.sha256,
            "CANARY_CONTRACT_MISMATCH",
        ),
        (
            "contract_group_sha256",
            proposal.contract_group.sha256,
            "CANARY_CONTRACT_GROUP_MISMATCH",
        ),
        (
            "entry_terms_sha256",
            proposal.entry_terms.sha256,
            "CANARY_ENTRY_TERMS_MISMATCH",
        ),
        (
            "flat_return_plan_sha256",
            proposal.flat_return_plan.sha256,
            "CANARY_FLAT_PLAN_MISMATCH",
        ),
    )
    for field, expected, reason in comparisons:
        if evidence.get(field) != expected:
            reasons.append(reason)
    if _decimal(evidence.get("quantity")) != proposal.quantity:
        reasons.append("CANARY_QUANTITY_MISMATCH")
    if any(
        _decimal(evidence.get(field)) != expected
        for field, expected in (
            ("maximum_debit_usd", proposal.maximum_debit_usd),
            ("maximum_loss_usd", proposal.maximum_loss_usd),
            ("fee_allowance_usd", proposal.fee_allowance_usd),
        )
    ):
        reasons.append("CANARY_ECONOMICS_MISMATCH")
    if evidence.get("paper_only") is not True:
        reasons.append("POSSIBLE_LIVE_CONNECTION")
    if evidence.get("fresh") is not True:
        reasons.append("CANARY_CAPABILITY_EVIDENCE_STALE")
    if int(evidence.get("broker_write_count") or 0) != 0:
        reasons.append("READ_ONLY_DISCOVERY_WRITE_DETECTED")
    if not all(
        evidence.get(field) is True
        for field in (
            "contract_qualified",
            "market_data_verified",
            "broker_feasibility_verified",
        )
    ):
        reasons.append("CANARY_CAPABILITY_INCOMPLETE")
    evidence_observed = _parse_utc(evidence.get("observed_at_utc"))
    evidence_expires = _parse_utc(evidence.get("expires_at_utc"))
    if (
        evidence_observed is None
        or evidence_expires is None
        or not (evidence_observed <= now_utc < evidence_expires)
    ):
        reasons.append("CANARY_CAPABILITY_EVIDENCE_STALE")
    if not (proposal.created_at_utc <= now_utc < proposal.expires_at_utc):
        reasons.append("CANARY_CANDIDATE_EXPIRED")
    unique = tuple(dict.fromkeys(reasons))
    return CanaryCandidateValidationReceipt(
        status="BLOCK" if unique else "PASS",
        reason_codes=unique,
        proposal_sha256=proposal.sha256,
        capability_evidence_sha256=sha256_json(evidence),
    )


def bind_canary_authorization(
    proposal: CanaryCandidateProposal,
    owner_pilot_authorization: OwnerPilotAuthorization,
    now_utc: datetime,
) -> CanaryAuthorization:
    _require_utc(now_utc, "now_utc")
    owner = owner_pilot_authorization
    reasons: list[str] = []
    if not (owner.issued_at_utc <= now_utc < owner.expires_at_utc):
        reasons.append("OWNER_PILOT_AUTHORIZATION_EXPIRED")
    if not (proposal.created_at_utc <= now_utc < proposal.expires_at_utc):
        reasons.append("CANARY_CANDIDATE_EXPIRED")
    if proposal.account_identity_sha256 != owner.account_identity_sha256:
        reasons.append("CANARY_ACCOUNT_MISMATCH")
    if proposal.successor_definition_sha256 != owner.successor_definition_sha256:
        reasons.append("CANARY_SUCCESSOR_MISMATCH")
    if proposal.approved_head != owner.approved_head:
        reasons.append("CANARY_HEAD_MISMATCH")
    if proposal.maximum_debit_usd > owner.maximum_debit_usd:
        reasons.append("CANARY_DEBIT_EXCEEDED")
    if proposal.maximum_loss_usd > owner.maximum_loss_usd:
        reasons.append("CANARY_LOSS_EXCEEDED")
    if proposal.fee_allowance_usd > owner.fee_allowance_usd:
        reasons.append("CANARY_FEES_EXCEEDED")
    if owner.maximum_order_count < 2:
        reasons.append("CANARY_ORDER_COUNT_EXCEEDED")
    if reasons:
        raise ValueError(";".join(dict.fromkeys(reasons)))
    contract_scope = tuple(
        sorted(item.sha256 for item in proposal.contract_group.member_contracts)
    )
    return CanaryAuthorization(
        authorization_id=(
            f"{owner.authorization_id}:candidate:{proposal.sha256}"
        ),
        owner_id=owner.owner_id,
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        product_family_sha256=proposal.product_family.sha256,
        contract_scope_sha256=contract_scope,
        maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        maximum_order_count=2,
        issued_at_utc=now_utc,
        expires_at_utc=min(proposal.expires_at_utc, owner.expires_at_utc),
    )
