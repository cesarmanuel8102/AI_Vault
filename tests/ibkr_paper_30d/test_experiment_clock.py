from ibkr_paper_30d.experiment_clock import build_experiment_clock


def test_day_one_clock_exposes_full_remaining_horizon():
    clock = build_experiment_clock(
        "2026-09-21T13:30:00Z",
        observed_at_utc="2026-09-21T13:30:00Z",
    )
    assert clock.status == "ACTIVE"
    assert clock.day_index == 1
    assert clock.days_remaining == 30.0
    assert clock.expired is False


def test_day_twenty_nine_exposes_short_remaining_horizon():
    clock = build_experiment_clock(
        "2026-09-01T00:00:00Z",
        observed_at_utc="2026-09-29T12:00:00Z",
    )
    assert clock.status == "ACTIVE"
    assert clock.day_index == 29
    assert 1.4 < clock.days_remaining < 1.6


def test_horizon_expires_exactly_after_thirty_days():
    clock = build_experiment_clock(
        "2026-09-01T00:00:00Z",
        observed_at_utc="2026-10-01T00:00:00Z",
    )
    assert clock.status == "EXPIRED"
    assert clock.days_remaining == 0
    assert clock.expired is True


def test_prestart_clock_is_not_active():
    clock = build_experiment_clock(
        "2026-09-21T13:30:00Z",
        observed_at_utc="2026-09-21T12:30:00Z",
    )
    assert clock.status == "NOT_STARTED"
    assert clock.day_index == 0
