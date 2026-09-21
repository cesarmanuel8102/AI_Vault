from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


CENT = Decimal("0.01")


class RiskResult(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    REDUCE_SIZE = "REDUCE_SIZE"


class RiskPolicy(BaseModel, frozen=True):
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
