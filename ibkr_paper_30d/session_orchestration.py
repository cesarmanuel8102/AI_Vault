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
from datetime import datetime, timedelta, timezone
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
    next_wake_utc: datetime | None = None

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
            "next_wake_utc": (
                None
                if self.next_wake_utc is None
                else self.next_wake_utc.isoformat().replace("+00:00", "Z")
            ),
        }


MULTI_UNIVERSE_WAKE_HORIZON = timedelta(minutes=15)


def _utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def decide_multi_universe_orchestration(
    *,
    now_utc: datetime,
    family_sessions: dict[str, dict[str, Any]],
    open_orders: Any,
    positions: Any,
    continuity_deadlines: Any,
) -> SessionOrchestrationDecision:
    """Choose one cycle/idle decision across all certified product families."""
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")
    now_utc = now_utc.astimezone(timezone.utc)
    orders = tuple(open_orders or ())
    held_positions = tuple(positions or ())
    deadlines = tuple(
        value
        for raw in (continuity_deadlines or ())
        if (value := _utc_datetime(raw)) is not None
    )
    reasons: list[str] = []
    if orders:
        reasons.append("CONTINUITY_OBLIGATION_OPEN_ORDER")
    if held_positions:
        reasons.append("CONTINUITY_OBLIGATION_OPEN_POSITION")
    if deadlines:
        reasons.append("CONTINUITY_OBLIGATION_DEADLINE")
    obligation = bool(orders or held_positions or deadlines)
    if obligation:
        return SessionOrchestrationDecision(
            action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
            session=MarketSession.UNKNOWN,
            continuity_obligation=True,
            reason_codes=tuple(reasons),
            next_wake_utc=min(deadlines, default=None),
        )

    if not family_sessions:
        return SessionOrchestrationDecision(
            action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
            session=MarketSession.UNKNOWN,
            continuity_obligation=False,
            reason_codes=("SESSION_EVIDENCE_UNAVAILABLE",),
        )

    next_openings: list[tuple[str, datetime]] = []
    for family_sha, evidence in sorted(family_sessions.items()):
        if evidence.get("authenticated") is not True:
            reasons.extend((f"SESSION_EVIDENCE_UNAUTHENTICATED:{family_sha}", "SESSION_EVIDENCE_UNAVAILABLE"))
            return SessionOrchestrationDecision(
                action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
                session=MarketSession.UNKNOWN,
                continuity_obligation=False,
                reason_codes=tuple(reasons),
            )
        raw_session = evidence.get("session")
        session_name = (
            raw_session.value if isinstance(raw_session, MarketSession) else str(raw_session or "UNKNOWN").upper()
        )
        if evidence.get("tradable_now") is True or session_name == MarketSession.REGULAR.value:
            return SessionOrchestrationDecision(
                action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
                session=MarketSession.REGULAR,
                continuity_obligation=False,
                reason_codes=(f"CERTIFIED_FAMILY_OPEN:{family_sha}",),
            )
        if session_name == MarketSession.UNKNOWN.value:
            return SessionOrchestrationDecision(
                action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
                session=MarketSession.UNKNOWN,
                continuity_obligation=False,
                reason_codes=("SESSION_EVIDENCE_UNAVAILABLE",),
            )
        next_open = _utc_datetime(evidence.get("next_open_utc"))
        if next_open is not None and next_open >= now_utc:
            next_openings.append((family_sha, next_open))

    if next_openings:
        family_sha, next_open = min(next_openings, key=lambda item: item[1])
        if next_open <= now_utc + MULTI_UNIVERSE_WAKE_HORIZON:
            return SessionOrchestrationDecision(
                action=OrchestrationAction.RUN_AUTONOMOUS_CYCLE,
                session=MarketSession.PREMARKET,
                continuity_obligation=False,
                reason_codes=(f"FAMILY_OPENING_WITHIN_WAKE_HORIZON:{family_sha}",),
                next_wake_utc=next_open,
            )
    else:
        next_open = None

    return SessionOrchestrationDecision(
        action=OrchestrationAction.MARKET_CLOSED_IDLE,
        session=MarketSession.CLOSED,
        continuity_obligation=False,
        reason_codes=("ALL_CERTIFIED_FAMILIES_CLOSED", "NO_CONTINUITY_OBLIGATION"),
        next_wake_utc=next_open,
    )


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
