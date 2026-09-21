from decimal import Decimal

from ibkr_paper_30d.autonomous_scheduler import AutonomousScheduler


def test_equity_change_triggers_immediate_research():
    scheduler = AutonomousScheduler()
    scheduler.record_cycle(now_monotonic=100.0, experimental_equity=Decimal("500"))
    decision = scheduler.evaluate(
        now_monotonic=101.0,
        experimental_equity=Decimal("735"),
        has_open_positions=False,
    )
    assert decision.run_cycle is True
    assert decision.trigger == "CAPITAL_STATE_CHANGED"


def test_open_position_is_reviewed_each_minute():
    scheduler = AutonomousScheduler()
    scheduler.record_cycle(now_monotonic=100.0, experimental_equity=Decimal("500"))
    first = scheduler.evaluate(
        now_monotonic=101.0,
        experimental_equity=Decimal("500"),
        has_open_positions=True,
    )
    assert first.trigger == "POSITION_REVIEW"
    second = scheduler.evaluate(
        now_monotonic=150.0,
        experimental_equity=Decimal("500"),
        has_open_positions=True,
    )
    assert second.run_cycle is False
    third = scheduler.evaluate(
        now_monotonic=161.0,
        experimental_equity=Decimal("500"),
        has_open_positions=True,
    )
    assert third.trigger == "POSITION_REVIEW"


def test_flat_account_scans_every_five_minutes():
    scheduler = AutonomousScheduler()
    scheduler.record_cycle(now_monotonic=100.0, experimental_equity=Decimal("500"))
    assert scheduler.evaluate(
        now_monotonic=399.0,
        experimental_equity=Decimal("500"),
        has_open_positions=False,
    ).run_cycle is False
    assert scheduler.evaluate(
        now_monotonic=400.0,
        experimental_equity=Decimal("500"),
        has_open_positions=False,
    ).trigger == "SCHEDULED_SCAN"
