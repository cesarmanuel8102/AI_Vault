from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ibkr_paper_30d.market_observation import MarketSession
from ibkr_paper_30d.session_orchestration import (
    OrchestrationAction,
    decide_multi_universe_orchestration,
)


NOW = datetime(2026, 10, 9, 20, 5, tzinfo=timezone.utc)
REGULAR_FAMILY = "a" * 64
CONTINUOUS_FAMILY = "b" * 64


def _family(*, session="CLOSED", next_open=None, authenticated=True):
    return {
        "authenticated": authenticated,
        "session": session,
        "next_open_utc": next_open,
    }


def _decide(families, *, orders=(), positions=(), deadlines=()):
    return decide_multi_universe_orchestration(
        now_utc=NOW,
        family_sessions=families,
        open_orders=orders,
        positions=positions,
        continuity_deadlines=deadlines,
    )


def test_regular_closed_continuous_open_runs_one_autonomous_cycle() -> None:
    decision = _decide(
        {
            REGULAR_FAMILY: _family(session="CLOSED"),
            CONTINUOUS_FAMILY: _family(session="REGULAR"),
        }
    )

    assert decision.action is OrchestrationAction.RUN_AUTONOMOUS_CYCLE
    assert decision.session is MarketSession.REGULAR
    assert f"CERTIFIED_FAMILY_OPEN:{CONTINUOUS_FAMILY}" in decision.reason_codes


def test_both_open_run_and_both_closed_idle() -> None:
    both_open = _decide(
        {
            REGULAR_FAMILY: _family(session="REGULAR"),
            CONTINUOUS_FAMILY: _family(session="REGULAR"),
        }
    )
    both_closed = _decide(
        {
            REGULAR_FAMILY: _family(
                session="CLOSED", next_open=NOW + timedelta(hours=12)
            ),
            CONTINUOUS_FAMILY: _family(session="MAINTENANCE"),
        }
    )

    assert both_open.should_run_cycle is True
    assert both_closed.action is OrchestrationAction.MARKET_CLOSED_IDLE
    assert both_closed.next_wake_utc == NOW + timedelta(hours=12)


@pytest.mark.parametrize("obligation", ["order", "position", "deadline"])
def test_closed_markets_never_idle_a_continuity_obligation(obligation) -> None:
    kwargs = {"orders": (), "positions": (), "deadlines": ()}
    if obligation == "order":
        kwargs["orders"] = ({"order_ref": "o-1"},)
    elif obligation == "position":
        kwargs["positions"] = ({"contract_id": 7, "quantity": "1"},)
    else:
        kwargs["deadlines"] = (NOW + timedelta(minutes=5),)

    decision = _decide({CONTINUOUS_FAMILY: _family(session="CLOSED")}, **kwargs)

    assert decision.should_run_cycle is True
    assert decision.continuity_obligation is True


def test_opening_inside_adaptive_wake_horizon_runs_instead_of_long_idle() -> None:
    decision = _decide(
        {
            CONTINUOUS_FAMILY: _family(
                session="CLOSED", next_open=NOW + timedelta(minutes=10)
            )
        }
    )

    assert decision.should_run_cycle is True
    assert (
        f"FAMILY_OPENING_WITHIN_WAKE_HORIZON:{CONTINUOUS_FAMILY}"
        in decision.reason_codes
    )


def test_unknown_or_unauthenticated_calendar_runs_fail_closed() -> None:
    for family in (
        {CONTINUOUS_FAMILY: _family(session="UNKNOWN")},
        {CONTINUOUS_FAMILY: _family(session="CLOSED", authenticated=False)},
    ):
        decision = _decide(family)
        assert decision.should_run_cycle is True
        assert "SESSION_EVIDENCE_UNAVAILABLE" in decision.reason_codes


def test_dst_aware_next_open_is_preserved() -> None:
    next_open = datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)
    decision = decide_multi_universe_orchestration(
        now_utc=datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc),
        family_sessions={
            CONTINUOUS_FAMILY: _family(session="CLOSED", next_open=next_open)
        },
        open_orders=(),
        positions=(),
        continuity_deadlines=(),
    )

    assert decision.action is OrchestrationAction.MARKET_CLOSED_IDLE
    assert decision.next_wake_utc == next_open


def test_open_authenticated_family_is_not_hidden_by_unusable_peer_evidence() -> None:
    decision = _decide(
        {
            REGULAR_FAMILY: _family(session="CLOSED", authenticated=False),
            CONTINUOUS_FAMILY: _family(session="REGULAR", authenticated=True),
        }
    )

    assert decision.should_run_cycle is True
    assert decision.reason_codes == (
        f"CERTIFIED_FAMILY_OPEN:{CONTINUOUS_FAMILY}",
    )
