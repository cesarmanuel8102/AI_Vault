from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CadencePolicy:
    scheduled_market_scan_seconds: float = 300.0
    open_position_review_seconds: float = 60.0


@dataclass(frozen=True)
class SchedulerDecision:
    run_cycle: bool
    trigger: str
    reason: str


class AutonomousScheduler:
    """
    Observation cadence only; this is not a trade-frequency limiter.

    A scheduled discovery cycle occurs every five minutes.  Open positions are
    reconsidered every minute.  Any broker position/order event or any change
    in experimental equity triggers immediate re-evaluation because the
    executable strategy space may have changed.
    """

    def __init__(self, policy: CadencePolicy | None = None) -> None:
        self.policy = policy or CadencePolicy()
        self.last_market_scan_monotonic: float | None = None
        self.last_position_review_monotonic: float | None = None
        self.last_equity: Decimal | None = None

    def evaluate(
        self,
        *,
        now_monotonic: float,
        experimental_equity: Decimal,
        has_open_positions: bool,
        broker_position_event: bool = False,
        broker_order_event: bool = False,
    ) -> SchedulerDecision:
        if self.last_equity is None:
            self.last_equity = experimental_equity
        elif experimental_equity != self.last_equity:
            self.last_equity = experimental_equity
            self.last_market_scan_monotonic = now_monotonic
            return SchedulerDecision(
                True,
                "CAPITAL_STATE_CHANGED",
                "Equity changed; rebuild the broker-executable opportunity set immediately.",
            )

        if broker_position_event or broker_order_event:
            self.last_market_scan_monotonic = now_monotonic
            return SchedulerDecision(
                True,
                "BROKER_EVENT",
                "Position/order state changed; re-evaluate immediately.",
            )

        if has_open_positions:
            due = (
                self.last_position_review_monotonic is None
                or now_monotonic - self.last_position_review_monotonic
                >= self.policy.open_position_review_seconds
            )
            if due:
                self.last_position_review_monotonic = now_monotonic
                return SchedulerDecision(
                    True,
                    "POSITION_REVIEW",
                    "Open-position review cadence reached.",
                )

        due = (
            self.last_market_scan_monotonic is None
            or now_monotonic - self.last_market_scan_monotonic
            >= self.policy.scheduled_market_scan_seconds
        )
        if due:
            self.last_market_scan_monotonic = now_monotonic
            return SchedulerDecision(
                True,
                "SCHEDULED_SCAN",
                "Scheduled autonomous opportunity-discovery cycle.",
            )

        return SchedulerDecision(False, "NONE", "No research cycle is due.")

    def record_cycle(self, *, now_monotonic: float, experimental_equity: Decimal) -> None:
        self.last_market_scan_monotonic = now_monotonic
        self.last_equity = experimental_equity
