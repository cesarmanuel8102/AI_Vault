from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


class RiskResult(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    REDUCE_SIZE = "REDUCE_SIZE"


class RiskPolicy(BaseModel, frozen=True):
    """
    Capital-boundary policy for the autonomous 30-day experiment.

    Strategy-level percentage limits are intentionally absent.  Codex owns
    sizing, concentration, drawdown tolerance and number of simultaneous
    positions.  The deterministic boundary only prevents the experiment from
    creating a worst-case liability greater than the experimental equity.
    """

    version: str = "CAPITAL_BOUNDARY_V2"
    maximum_experiment_liability_fraction: Decimal = Decimal("1.00")

    @classmethod
    def month1(cls) -> "RiskPolicy":
        # Compatibility alias used by the existing orchestration layer.
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
    maximum_experiment_liability: Decimal
    position_capital_limit_enforced: bool = False
    drawdown_limits_enforced: bool = False
    concurrent_position_limit_enforced: bool = False


class RiskEngine:
    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    @classmethod
    def month1(cls) -> "RiskEngine":
        return cls(RiskPolicy.month1())

    def evaluate(self, inputs: RiskInputs) -> RiskDecision:
        equity = inputs.experiment_equity
        reasons: list[str] = []

        if equity <= 0:
            reasons.append("INVALID_EQUITY")
            liability_limit = Decimal("0")
        else:
            liability_limit = (
                equity * self.policy.maximum_experiment_liability_fraction
            )
            if not inputs.estimated_loss.is_finite() or inputs.estimated_loss < 0:
                reasons.append("INVALID_ESTIMATED_LOSS")
            elif inputs.estimated_loss > liability_limit:
                reasons.append("EXPERIMENT_LIABILITY_EXCEEDS_EQUITY")

            if not inputs.total_open_risk.is_finite() or inputs.total_open_risk < 0:
                reasons.append("INVALID_TOTAL_OPEN_RISK")
            elif inputs.total_open_risk > liability_limit:
                reasons.append("TOTAL_OPEN_RISK_EXCEEDS_EQUITY")

        reducible = {
            "EXPERIMENT_LIABILITY_EXCEEDS_EQUITY",
            "TOTAL_OPEN_RISK_EXCEEDS_EQUITY",
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
            maximum_estimated_loss=liability_limit,
            # Retained for schema compatibility only.  Position notional/capital
            # is no longer capped by policy; broker buying power is authoritative.
            maximum_position_capital=liability_limit,
            maximum_total_open_risk=liability_limit,
            maximum_experiment_liability=liability_limit,
        )
