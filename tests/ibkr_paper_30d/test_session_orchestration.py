"""Deterministic post-market orchestration tests.

The market-data gate correctly failed closed after the 2026-10-02 regular
close (INITIAL_REALTIME_QUOTE_TIMEOUT). The defect was orchestration: the
service kept waking and re-running new-trade research cycles against a
closed market. These tests pin the orchestration decision only; they do not
relax any market-data validation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.market_observation import MarketSession
from ibkr_paper_30d.session_orchestration import (
    OrchestrationAction,
    decide_session_orchestration,
)


NY = "US/Eastern"

# Authoritative IBKR contractDetails.liquidHours fixtures.
REGULAR_DAY = "20261002:0930-20261002:1600"
WEEKEND_DAY = "20261004:CLOSED"
HOLIDAY_DAY = "20261126:CLOSED"  # US Thanksgiving 2026
EARLY_CLOSE_DAY = "20261127:0930-20261127:1300"  # day after Thanksgiving
DST_FALLBACK_DAY = "20261101:CLOSED"  # DST transition weekend


def _utc(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _decide(now_utc, liquid_hours, *, positions=False, orders=False):
    return decide_session_orchestration(
        now_utc=now_utc,
        liquid_hours=liquid_hours,
        timezone_id=NY,
        has_open_positions=positions,
        has_open_orders=orders,
    )


def test_regular_session_runs_autonomous_cycle():
    # 2026-10-02 14:00Z == 10:00 ET, inside regular session.
    decision = _decide(_utc(2026, 10, 2, 14, 0), REGULAR_DAY)

    assert decision.session is MarketSession.REGULAR
    assert decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert decision.should_run_cycle is True
    assert decision.continuity_obligation is False


def test_closed_session_flat_and_no_open_orders_idles():
    # 2026-10-02 21:00Z == 17:00 ET, after the 16:00 regular close.
    decision = _decide(_utc(2026, 10, 2, 21, 0), REGULAR_DAY)

    assert decision.session is MarketSession.AFTER_HOURS
    assert decision.action is OrchestrationAction.MARKET_CLOSED_IDLE
    assert decision.should_run_cycle is False
    assert "MARKET_SESSION_AFTER_HOURS" in decision.reason_codes
    assert "NO_CONTINUITY_OBLIGATION" in decision.reason_codes


def test_closed_session_with_open_position_keeps_continuity_available():
    decision = _decide(_utc(2026, 10, 2, 21, 0), REGULAR_DAY, positions=True)

    assert decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert decision.should_run_cycle is True
    assert decision.continuity_obligation is True
    assert "CONTINUITY_OBLIGATION_OPEN_POSITION" in decision.reason_codes


def test_closed_session_with_open_order_keeps_continuity_available():
    decision = _decide(_utc(2026, 10, 2, 21, 0), REGULAR_DAY, orders=True)

    assert decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert decision.continuity_obligation is True
    assert "CONTINUITY_OBLIGATION_OPEN_ORDER" in decision.reason_codes


def test_weekend_idles():
    # 2026-10-04 is a Sunday.
    decision = _decide(_utc(2026, 10, 4, 15, 0), WEEKEND_DAY)

    assert decision.session is MarketSession.CLOSED
    assert decision.action is OrchestrationAction.MARKET_CLOSED_IDLE
    assert "MARKET_SESSION_CLOSED" in decision.reason_codes


def test_us_market_holiday_idles():
    decision = _decide(_utc(2026, 11, 26, 16, 0), HOLIDAY_DAY)

    assert decision.session is MarketSession.CLOSED
    assert decision.action is OrchestrationAction.MARKET_CLOSED_IDLE


def test_early_close_session_runs_before_close_and_idles_after():
    # 13:00 ET early close. 17:00Z == 12:00 ET (open), 18:30Z == 13:30 ET (closed).
    open_decision = _decide(_utc(2026, 11, 27, 17, 0), EARLY_CLOSE_DAY)
    closed_decision = _decide(_utc(2026, 11, 27, 18, 30), EARLY_CLOSE_DAY)

    assert open_decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert closed_decision.session is MarketSession.AFTER_HOURS
    assert closed_decision.action is OrchestrationAction.MARKET_CLOSED_IDLE


def test_premarket_before_next_session_idles_then_resumes_at_open():
    # 12:00Z == 08:00 ET premarket; 13:35Z == 09:35 ET regular.
    premarket = _decide(_utc(2026, 10, 2, 12, 0), REGULAR_DAY)
    regular = _decide(_utc(2026, 10, 2, 13, 35), REGULAR_DAY)

    assert premarket.session is MarketSession.PREMARKET
    assert premarket.action is OrchestrationAction.MARKET_CLOSED_IDLE
    assert regular.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE


def test_daylight_saving_transition_day_is_classified_from_calendar():
    decision = _decide(_utc(2026, 11, 1, 15, 0), DST_FALLBACK_DAY)

    assert decision.session is MarketSession.CLOSED
    assert decision.action is OrchestrationAction.MARKET_CLOSED_IDLE


@pytest.mark.parametrize(
    "liquid_hours",
    ("", "garbage", "20261002:0930-20261002:1600;20261002:0930-20261002:1600"),
)
def test_unknown_session_never_suppresses_existing_gates(liquid_hours):
    """Idle requires positive proof of a non-regular session.

    An unusable calendar must not silently stop the experiment; the existing
    fail-closed market-data gate remains the authority in that case.
    """
    decision = _decide(_utc(2026, 10, 2, 21, 0), liquid_hours)

    assert decision.session is MarketSession.UNKNOWN
    assert decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert "MARKET_SESSION_UNKNOWN" in decision.reason_codes


def test_idle_decision_carries_no_authority_and_no_receipt():
    """Idle is an orchestration decision only; it grants nothing."""
    decision = _decide(_utc(2026, 10, 2, 21, 0), REGULAR_DAY)

    payload = decision.as_event_payload()
    forbidden = {
        "gate_status",
        "receipt_sha256",
        "order_authority",
        "market_data_gate",
        "authorized",
        "passed",
    }
    assert forbidden.isdisjoint(payload)
    assert payload["action"] == "MARKET_CLOSED_IDLE"
    assert payload["market_session"] == "AFTER_HOURS"
