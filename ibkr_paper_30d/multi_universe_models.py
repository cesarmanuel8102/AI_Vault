"""Immutable authority contracts for the continuous multi-universe runtime."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import sha256_json


SHA256_PATTERN = r"^[0-9a-f]{64}$"
GIT_HEAD_PATTERN = r"^[0-9a-f]{40}$"


class CapitalSleeve(str, Enum):
    REGULAR_SLEEVE = "REGULAR_SLEEVE"
    CONTINUOUS_SLEEVE = "CONTINUOUS_SLEEVE"
    EXTENDED_SLEEVE = "CONTINUOUS_SLEEVE"

    @classmethod
    def _missing_(cls, value: object) -> "CapitalSleeve | None":
        if value == "EXTENDED_SLEEVE":
            return cls.CONTINUOUS_SLEEVE
        return None


class TransitionPhase(str, Enum):
    PREPARED = "PREPARED"
    PREDECESSOR_QUIESCED = "PREDECESSOR_QUIESCED"
    PREDECESSOR_RETIRED = "PREDECESSOR_RETIRED"
    SUCCESSOR_COMMITTED = "SUCCESSOR_COMMITTED"
    SUPERVISION_BOUND = "SUPERVISION_BOUND"
    CANARY_EXCLUSIVE = "CANARY_EXCLUSIVE"
    CANARY_PASS = "CANARY_PASS"
    RUNTIME_BOUND = "RUNTIME_BOUND"
    ACTIVE = "ACTIVE"


class AuthorityModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )

    @property
    def sha256(self) -> str:
        return sha256_json(self)


def _require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must use UTC")
    return value


class CanonicalBagLeg(AuthorityModel):
    con_id: int = Field(gt=0)
    ratio: int = Field(gt=0)
    action: Literal["BUY", "SELL"]
    exchange: str = Field(min_length=1)

    @field_validator("exchange")
    @classmethod
    def _normalize_exchange(cls, value: str) -> str:
        return value.upper()


class CanonicalContractIdentity(AuthorityModel):
    con_id: int = Field(ge=0)
    security_type: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    exchange: str = Field(min_length=1)
    primary_exchange: str | None = None
    local_symbol: str | None = None
    trading_class: str | None = None
    multiplier: Decimal | None = Field(default=None, gt=0)
    bag_legs: tuple[CanonicalBagLeg, ...] = ()

    @field_validator("security_type", "currency", "exchange", "primary_exchange")
    @classmethod
    def _normalize_codes(cls, value: str | None) -> str | None:
        return None if value is None else value.upper()

    @model_validator(mode="after")
    def _validate_identity(self) -> "CanonicalContractIdentity":
        if self.security_type == "CURRENCY_BALANCE":
            raise ValueError("currency balance is not an exclusive contract identity")
        if self.security_type == "BAG":
            if len(self.bag_legs) < 2:
                raise ValueError("BAG identity requires at least two legs")
            leg_ids = [leg.con_id for leg in self.bag_legs]
            if len(leg_ids) != len(set(leg_ids)):
                raise ValueError("duplicate BAG leg con_id")
        else:
            if self.con_id <= 0:
                raise ValueError("non-BAG identity requires positive con_id")
            if self.bag_legs:
                raise ValueError("non-BAG identity cannot contain BAG legs")
        return self

    @property
    def exclusive_ownership_eligible(self) -> bool:
        return True


class ContractOwnershipGroup(AuthorityModel):
    group_id: str = Field(min_length=1)
    sleeve: CapitalSleeve
    parent_contract: CanonicalContractIdentity
    member_contracts: tuple[CanonicalContractIdentity, ...]
    contingent_contracts: tuple[CanonicalContractIdentity, ...] = ()
    generation: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate_contract_sets(self) -> "ContractOwnershipGroup":
        member_hashes = [contract.sha256 for contract in self.member_contracts]
        contingent_hashes = [contract.sha256 for contract in self.contingent_contracts]
        if len(member_hashes) != len(set(member_hashes)):
            raise ValueError("duplicate member contract")
        if len(contingent_hashes) != len(set(contingent_hashes)):
            raise ValueError("duplicate contingent contract")
        if set(member_hashes) & set(contingent_hashes):
            raise ValueError("duplicate contract across member and contingent sets")
        if self.parent_contract.sha256 not in set(member_hashes):
            raise ValueError("parent contract must be a member")
        return self


class ProductFamilyKey(AuthorityModel):
    security_type: str = Field(min_length=1)
    venue_or_routing: str = Field(min_length=1)
    quantity_semantics: str = Field(min_length=1)
    order_representation: str = Field(min_length=1)
    lifecycle_behavior: str = Field(min_length=1)

    @field_validator(
        "security_type",
        "venue_or_routing",
        "quantity_semantics",
        "order_representation",
        "lifecycle_behavior",
    )
    @classmethod
    def _normalize_key(cls, value: str) -> str:
        return value.upper()


class SleeveAuthorityDefinition(AuthorityModel):
    sleeve: CapitalSleeve
    authorized_principal_usd: Decimal = Field(gt=0)
    opening_equity_usd: Decimal
    opening_pnl_usd: Decimal
    source_state_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def _validate_opening_economics(self) -> "SleeveAuthorityDefinition":
        if self.authorized_principal_usd != Decimal("500"):
            raise ValueError("sleeve principal must equal USD 500")
        if self.sleeve is CapitalSleeve.CONTINUOUS_SLEEVE and (
            self.opening_equity_usd != Decimal("500")
            or self.opening_pnl_usd != Decimal("0")
        ):
            raise ValueError("extended sleeve must open at USD 500 and zero P&L")
        return self


RiskLimit = Decimal | Literal["DISABLED"]


class OwnerEconomicRiskAuthorization(AuthorityModel):
    authorization_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    policy_version: Literal["AGGRESSIVE_CAPITAL_BOUNDARY_V1"]
    regular_allocation_usd: Decimal
    extended_allocation_usd: Decimal
    maximum_liability_ratio: Decimal
    daily_loss_limit_usd: RiskLimit
    drawdown_limit_usd: RiskLimit
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    issued_at_utc: datetime
    expires_at_utc: datetime

    @field_validator("daily_loss_limit_usd", "drawdown_limit_usd")
    @classmethod
    def _validate_limit(cls, value: RiskLimit) -> RiskLimit:
        if value == "DISABLED":
            return value
        if Decimal(value) < 0:
            raise ValueError("risk threshold cannot be negative")
        return value

    @model_validator(mode="after")
    def _validate_authority(self) -> "OwnerEconomicRiskAuthorization":
        _require_utc(self.issued_at_utc, "issued_at_utc")
        _require_utc(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("economic authorization must expire after issuance")
        if (
            self.regular_allocation_usd != Decimal("500")
            or self.extended_allocation_usd != Decimal("500")
        ):
            raise ValueError("economic authorization must bind USD 500 per sleeve")
        if self.maximum_liability_ratio != Decimal("1.00"):
            raise ValueError("maximum liability ratio must equal 1.00")
        return self


class CanaryAuthorization(AuthorityModel):
    authorization_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    product_family_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_scope_sha256: tuple[str, ...] = Field(min_length=1)
    maximum_debit_usd: Decimal = Field(ge=0)
    maximum_loss_usd: Decimal = Field(ge=0)
    fee_allowance_usd: Decimal = Field(ge=0)
    maximum_order_count: int = Field(gt=0)
    issued_at_utc: datetime
    expires_at_utc: datetime

    @field_validator("contract_scope_sha256")
    @classmethod
    def _validate_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate canary contract scope")
        if any(len(item) != 64 or any(c not in "0123456789abcdef" for c in item) for item in value):
            raise ValueError("invalid canary contract scope sha256")
        return value

    @model_validator(mode="after")
    def _validate_window(self) -> "CanaryAuthorization":
        _require_utc(self.issued_at_utc, "issued_at_utc")
        _require_utc(self.expires_at_utc, "expires_at_utc")
        if self.expires_at_utc <= self.issued_at_utc:
            raise ValueError("canary authorization must expire after issuance")
        return self


class TransitionTarget(AuthorityModel):
    transition_id: str = Field(min_length=1)
    predecessor_epoch_id: str = Field(min_length=1)
    successor_epoch_id: str = Field(min_length=1)
    successor_definition_sha256: str = Field(pattern=SHA256_PATTERN)
    owner_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    approved_git_head: str = Field(pattern=GIT_HEAD_PATTERN)
    account_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    clock_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    regular_sleeve_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    continuous_sleeve_authority_sha256: str = Field(pattern=SHA256_PATTERN)
    economic_risk_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    certified_family_set_sha256: str = Field(pattern=SHA256_PATTERN)
    canary_authorization_sha256: str = Field(pattern=SHA256_PATTERN)
    writer_binding_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_continuous_binding(cls, value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        legacy = data.pop("extended_sleeve_authority_sha256", None)
        current = data.get("continuous_sleeve_authority_sha256")
        if current is None and legacy is not None:
            data["continuous_sleeve_authority_sha256"] = legacy
        elif legacy is not None and legacy != current:
            raise ValueError("continuous sleeve authority binding conflict")
        return data

    @model_validator(mode="after")
    def _validate_epoch_edge(self) -> "TransitionTarget":
        if self.predecessor_epoch_id == self.successor_epoch_id:
            raise ValueError("successor epoch must differ from predecessor")
        return self

    @property
    def extended_sleeve_authority_sha256(self) -> str:
        return self.continuous_sleeve_authority_sha256
