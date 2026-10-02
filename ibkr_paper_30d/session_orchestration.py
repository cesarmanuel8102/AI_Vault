"""Deterministic non-trading-session orchestration.

The market-data gate is the authority on whether an observation is usable.
This module is the authority on whether the service should *ask* for one.

It answers a single question from authoritative IBKR calendar evidence
(``contractDetails.liquidHours`` + ``timeZoneId``) and current broker
obligations:

    should the autonomous service run a cycle right now, or idle until the
    next valid trading session?

It grants no authority, produces no receipt, and never relaxes a gate. Idle
is entered only on positive proof of a non-regular session with no surviving
continuity obligation; an unusable calendar leaves existing fail-closed
behaviour untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .market_observation import MarketSession, classify_session


class OrchestrationAction(str, Enum):
    RUN_AUTONOMOUS_CYCLE = "RUN_AUTONOMOUS_CYCLE"
    MARKET_CLOSED_IDLE = "MARKET_CLOSED_IDLE"


@dataclass(frozen=True)
class SessionOrchestrationDecision:
    action: OrchestrationAction
    session: MarketSession
    continuity_obligation: bool
    reason_codes: tuple[str, ...]

    @property
    def should_run_cycle(self) -> bool:
        return self.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE

    def as_event_payload(self) -> dict[str, Any]:
        """Observational payload. Intentionally carries no gate/authority keys."""
        return {
            "action": self.action.value,
            "market_session": self.session.value,
            "continuity_obligation": self.continuity_obligation,
            "reason_codes": list(self.reason_codes),
        }


def decide_session_orchestration(
    *,
    now_utc: datetime,
    liquid_hours: str,
    timezone_id: str,
    has_open_positions: bool,
    has_open_orders: bool,
) -> SessionOrchestrationDecision:
    """Decide whether to run an autonomous cycle or idle until the next session."""
    session = classify_session(now_utc, liquid_hours, timezone_id)
    reasons: list[str] = [f"MARKET_SESSION_{session.value}"]

    if has_open_positions:
        reasons.append("CONTINUITY_OBLIGATION_OPEN_POSITION")
    if has_open_orders:
        reasons.append("CONTINUITY_OBLIGATION_OPEN_ORDER")
    obligation = bool(has_open_positions or has_open_orders)

    if session is MarketSession.REGULAR:
        return SessionOrchestrationDecision(
            action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
            session=session,
            continuity_obligation=obligation,
            reason_codes=tuple(reasons),
        )

    if session is MarketSession.UNKNOWN:
        # No positive proof the market is closed. Never let a calendar failure
        # suppress the experiment or its existing fail-closed gates.
        reasons.append("SESSION_EVIDENCE_UNAVAILABLE")
        return SessionOrchestrationDecision(
            action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
            session=session,
            continuity_obligation=obligation,
            reason_codes=tuple(reasons),
        )

    if obligation:
        # Continuity/order-management obligations survive the regular close.
        return SessionOrchestrationDecision(
            action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
            session=session,
            continuity_obligation=True,
            reason_codes=tuple(reasons),
        )

    reasons.append("NO_CONTINUITY_OBLIGATION")
    return SessionOrchestrationDecision(
        action=OrchestrationAction.MARKET_CLOSED_IDLE,
        session=session,
        continuity_obligation=False,
        reason_codes=tuple(reasons),
    )
