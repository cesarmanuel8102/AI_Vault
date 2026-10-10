from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from .multi_universe_models import CapitalSleeve, OwnerEconomicRiskAuthorization


CENT = Decimal("0.01")


class RiskResult(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    REDUCE_SIZE = "REDUCE_SIZE"


class RiskPolicy(BaseModel, frozen=True):
    """DEPRECATED legacy policy.

    Retained only for backward-compatibility tests and non-autonomous legacy
    paths. The autonomous IBKR experiment MUST use CapitalBoundaryRiskPolicy
    and MUST NOT import or instantiate this class as an execution gate.
    """
    version: str = "MONTH1_V1"
    max_loss_per_trade: Decimal = Decimal("0.05")
    max_position_capital: Decimal = Decimal("0.40")
    max_total_open_risk: Decimal = Decimal("0.15")
    max_concurrent_positions: int = 3
    max_daily_loss: Decimal = Decimal("0.08")
    max_weekly_drawdown: Decimal = Decimal("0.12")
    max_total_drawdown: Decimal = Decimal("0.20")

    @classmethod
    def month1(cls) -> "RiskPolicy":
        return cls()


class RiskInputs(BaseModel, frozen=True):
    experiment_equity: Decimal
    day_start_equity: Decimal
    week_start_equity: Decimal
    high_water_equity: Decimal
    estimated_loss: Decimal
    position_capital: Decimal
    total_open_risk: Decimal
    daily_loss: Decimal
    weekly_drawdown: Decimal
    total_drawdown: Decimal
    concurrent_positions: int
    can_reduce_size: bool = False


class RiskDecision(BaseModel, frozen=True):
    model_config = ConfigDict(use_enum_values=False)

    result: RiskResult
    reason_codes: tuple[str, ...]
    policy_version: str
    maximum_estimated_loss: Decimal
    maximum_position_capital: Decimal
    maximum_total_open_risk: Decimal


class RiskEngine:
    """DEPRECATED legacy percentage-cap engine; not authoritative for autonomous IBKR."""
    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    @classmethod
    def month1(cls) -> "RiskEngine":
        return cls(RiskPolicy.month1())

    @staticmethod
    def _strict_max(basis: Decimal, fraction: Decimal) -> Decimal:
        return (basis * fraction - CENT).quantize(CENT)

    def evaluate(self, inputs: RiskInputs) -> RiskDecision:
        equity = inputs.experiment_equity
        max_loss = self._strict_max(max(equity, Decimal("0")), self.policy.max_loss_per_trade)
        max_position = self._strict_max(
            max(equity, Decimal("0")), self.policy.max_position_capital
        )
        max_open_risk = self._strict_max(
            max(equity, Decimal("0")), self.policy.max_total_open_risk
        )
        reasons: list[str] = []
        if equity <= 0:
            reasons.append("INVALID_EQUITY")
        else:
            if inputs.estimated_loss >= equity * self.policy.max_loss_per_trade:
                reasons.append("MAX_ESTIMATED_LOSS_PER_TRADE")
            if inputs.position_capital >= equity * self.policy.max_position_capital:
                reasons.append("MAX_SINGLE_POSITION_CAPITAL")
            if inputs.total_open_risk >= equity * self.policy.max_total_open_risk:
                reasons.append("MAX_TOTAL_OPEN_RISK")
            if inputs.concurrent_positions >= self.policy.max_concurrent_positions:
                reasons.append("MAX_CONCURRENT_POSITIONS")
            if inputs.daily_loss >= inputs.day_start_equity * self.policy.max_daily_loss:
                reasons.append("MAX_DAILY_LOSS")
            if (
                inputs.weekly_drawdown
                >= inputs.week_start_equity * self.policy.max_weekly_drawdown
            ):
                reasons.append("MAX_WEEKLY_DRAWDOWN")
            if (
                inputs.total_drawdown
                >= inputs.high_water_equity * self.policy.max_total_drawdown
            ):
                reasons.append("MAX_TOTAL_DRAWDOWN")

        reducible = {
            "MAX_ESTIMATED_LOSS_PER_TRADE",
            "MAX_SINGLE_POSITION_CAPITAL",
            "MAX_TOTAL_OPEN_RISK",
        }
        if not reasons:
            result = RiskResult.PASS
        elif inputs.can_reduce_size and set(reasons) <= reducible:
            result = RiskResult.REDUCE_SIZE
        else:
            result = RiskResult.BLOCK
        return RiskDecision(
            result=result,
            reason_codes=tuple(reasons),
            policy_version=self.policy.version,
            maximum_estimated_loss=max_loss,
            maximum_position_capital=max_position,
            maximum_total_open_risk=max_open_risk,
        )


class CapitalBoundaryRiskPolicy(BaseModel, frozen=True):
    """Aggressive experiment policy with no fixed sizing or drawdown caps.

    Full loss of the isolated experimental equity is allowed. The only
    financial boundary is that a proposed position may not create liability
    greater than the current experimental equity.
    """

    version: str = "AGGRESSIVE_CAPITAL_BOUNDARY_V1"
    allow_full_equity_loss: bool = True


class CapitalBoundaryInputs(BaseModel, frozen=True):
    experiment_equity: Decimal
    maximum_loss: Decimal
    liability_is_bounded: bool
    uses_external_capital: bool = False


class CapitalBoundaryDecision(BaseModel, frozen=True):
    model_config = ConfigDict(use_enum_values=False)

    result: RiskResult
    reason_codes: tuple[str, ...]
    policy_version: str
    maximum_allowed_loss: Decimal


class CapitalBoundaryRiskEngine:
    def __init__(self, policy: CapitalBoundaryRiskPolicy | None = None):
        self.policy = policy or CapitalBoundaryRiskPolicy()

    @classmethod
    def aggressive_month1(cls) -> "CapitalBoundaryRiskEngine":
        return cls(CapitalBoundaryRiskPolicy())

    def evaluate(self, inputs: CapitalBoundaryInputs) -> CapitalBoundaryDecision:
        equity = inputs.experiment_equity
        loss = inputs.maximum_loss
        reasons: list[str] = []
        if not equity.is_finite() or equity <= 0:
            reasons.append("INVALID_EQUITY")
        if not loss.is_finite() or loss < 0:
            reasons.append("INVALID_MAXIMUM_LOSS")
        if not inputs.liability_is_bounded:
            reasons.append("UNBOUNDED_LIABILITY")
        if inputs.uses_external_capital:
            reasons.append("EXTERNAL_CAPITAL_FORBIDDEN")
        if (
            equity.is_finite()
            and equity > 0
            and loss.is_finite()
            and loss > equity
        ):
            reasons.append("EXPERIMENT_CAPITAL_BOUNDARY")

        return CapitalBoundaryDecision(
            result=RiskResult.PASS if not reasons else RiskResult.BLOCK,
            reason_codes=tuple(dict.fromkeys(reasons)),
            policy_version=self.policy.version,
            maximum_allowed_loss=max(equity, Decimal("0")),
        )


class SleeveCapitalBoundaryInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    sleeve: CapitalSleeve
    sleeve_equity_usd: Decimal
    reserved_liability_usd: Decimal
    proposed_maximum_loss_usd: Decimal
    aggregate_reserved_after_usd: Decimal
    liability_is_bounded: bool
    uses_external_capital: bool
    uses_other_sleeve_offset: bool
    uses_non_experiment_offset: bool
    owner_id: str
    successor_definition_sha256: str
    evaluated_at_utc: datetime
    daily_loss_usd: Decimal
    drawdown_usd: Decimal
    action_kind: Literal["NEW_RISK", "EXACT_EXIT", "CONTINUITY_ACTION"]
    broker_account_buying_power_usd: Decimal | None = None
    other_sleeve_margin_offset_usd: Decimal = Decimal("0")

    @field_validator("evaluated_at_utc")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
            or value.utcoffset().total_seconds() != 0
        ):
            raise ValueError("evaluated_at_utc must use UTC")
        return value


class SleeveCapitalBoundaryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)

    result: RiskResult
    reason_codes: tuple[str, ...]
    policy_version: str
    sleeve: CapitalSleeve
    available_usd: Decimal
    maximum_allowed_aggregate_liability_usd: Decimal
    new_authority_frozen: bool


class SleeveCapitalBoundaryRiskEngine:
    POLICY_VERSION = "AGGRESSIVE_CAPITAL_BOUNDARY_V1"

    @staticmethod
    def _limit_is_valid(value: object) -> bool:
        if value == "DISABLED":
            return True
        try:
            threshold = Decimal(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, ArithmeticError):
            return False
        return threshold.is_finite() and threshold >= 0

    def evaluate(
        self,
        inputs: SleeveCapitalBoundaryInputs,
        economic_authorization: OwnerEconomicRiskAuthorization | None,
    ) -> SleeveCapitalBoundaryDecision:
        equity = inputs.sleeve_equity_usd
        reserved = inputs.reserved_liability_usd
        proposed = inputs.proposed_maximum_loss_usd
        aggregate = inputs.aggregate_reserved_after_usd
        available = max(Decimal("0"), equity - max(reserved, Decimal("0")))
        reasons: list[str] = []

        authority = economic_authorization
        if authority is None:
            reasons.append("ECONOMIC_AUTHORIZATION_MISSING")
        else:
            if authority.expires_at_utc <= inputs.evaluated_at_utc:
                reasons.append("ECONOMIC_AUTHORIZATION_EXPIRED")
            if authority.issued_at_utc > inputs.evaluated_at_utc:
                reasons.append("ECONOMIC_AUTHORIZATION_NOT_YET_VALID")
            if authority.owner_id != inputs.owner_id:
                reasons.append("ECONOMIC_AUTHORIZATION_OWNER_MISMATCH")
            if (
                authority.regular_allocation_usd != Decimal("500.00")
                or authority.extended_allocation_usd != Decimal("500.00")
            ):
                reasons.append("ECONOMIC_AUTHORIZATION_ALLOCATION_MISMATCH")
            if authority.policy_version != self.POLICY_VERSION:
                reasons.append("ECONOMIC_AUTHORIZATION_POLICY_MISMATCH")
            if authority.maximum_liability_ratio != Decimal("1.00"):
                reasons.append("ECONOMIC_AUTHORIZATION_RATIO_MISMATCH")
            if (
                authority.successor_definition_sha256
                != inputs.successor_definition_sha256
            ):
                reasons.append("ECONOMIC_AUTHORIZATION_SUCCESSOR_MISMATCH")
            if not self._limit_is_valid(authority.daily_loss_limit_usd):
                reasons.append("ECONOMIC_AUTHORIZATION_DAILY_LOSS_UNSPECIFIED")
            if not self._limit_is_valid(authority.drawdown_limit_usd):
                reasons.append("ECONOMIC_AUTHORIZATION_DRAWDOWN_UNSPECIFIED")

        if inputs.action_kind == "NEW_RISK":
            if not equity.is_finite() or equity <= 0:
                reasons.append("INVALID_SLEEVE_EQUITY")
            if not reserved.is_finite() or reserved < 0:
                reasons.append("INVALID_RESERVED_LIABILITY")
            if not proposed.is_finite() or proposed < 0:
                reasons.append("INVALID_PROPOSED_LIABILITY")
            if not aggregate.is_finite() or aggregate < 0:
                reasons.append("INVALID_AGGREGATE_LIABILITY")
            if not inputs.liability_is_bounded:
                reasons.append("UNBOUNDED_LIABILITY")
            if inputs.uses_external_capital:
                reasons.append("EXTERNAL_CAPITAL_FORBIDDEN")
            if (
                inputs.uses_other_sleeve_offset
                or inputs.other_sleeve_margin_offset_usd != 0
            ):
                reasons.append("CROSS_SLEEVE_OFFSET_FORBIDDEN")
            if inputs.uses_non_experiment_offset:
                reasons.append("NON_EXPERIMENT_OFFSET_FORBIDDEN")
            if proposed.is_finite() and proposed > available:
                reasons.append("PROPOSED_LIABILITY_EXCEEDS_AVAILABLE")
            if equity.is_finite() and aggregate.is_finite() and aggregate > equity:
                reasons.append("AGGREGATE_LIABILITY_EXCEEDS_SLEEVE_EQUITY")

            if authority is not None:
                daily_limit = authority.daily_loss_limit_usd
                if (
                    daily_limit != "DISABLED"
                    and self._limit_is_valid(daily_limit)
                    and inputs.daily_loss_usd >= Decimal(daily_limit)
                ):
                    reasons.append("MAX_DAILY_LOSS_REACHED")
                drawdown_limit = authority.drawdown_limit_usd
                if (
                    drawdown_limit != "DISABLED"
                    and self._limit_is_valid(drawdown_limit)
                    and inputs.drawdown_usd >= Decimal(drawdown_limit)
                ):
                    reasons.append("MAX_DRAWDOWN_REACHED")

        unique_reasons = tuple(dict.fromkeys(reasons))
        return SleeveCapitalBoundaryDecision(
            result=RiskResult.PASS if not unique_reasons else RiskResult.BLOCK,
            reason_codes=unique_reasons,
            policy_version=self.POLICY_VERSION,
            sleeve=inputs.sleeve,
            available_usd=available,
            maximum_allowed_aggregate_liability_usd=max(equity, Decimal("0")),
            new_authority_frozen=bool(unique_reasons and inputs.action_kind == "NEW_RISK"),
        )
