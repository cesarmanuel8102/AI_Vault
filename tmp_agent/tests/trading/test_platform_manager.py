"""
Tests for brain_v9.trading.platform_manager — Sprint 1 (P4-03).

Covers:
  - PlatformMetrics.calculate_derived_metrics: win_rate, expectancy, sample_quality, drawdown
  - PlatformManager.compute_platform_u: aligned U formula
  - PlatformManager.record_trade: trade recording + U recomputation
  - state_io integration: save/load cycle
  - PlatformU.update / _update_verdict thresholds
  - get_platform_manager singleton
"""
import math
import pytest
from unittest.mock import patch

import brain_v9.config as _cfg
from brain_v9.trading.platform_manager import (
    PlatformManager,
    PlatformMetrics,
    PlatformU,
    _MIN_PLATFORM_RESOLVED,
    _squash_signal,
    _round,
    get_platform_manager,
    STATE_PATH,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_state_path(monkeypatch, isolated_base_path):
    """Redirect PlatformManager's STATE_PATH to the temp dir."""
    import brain_v9.trading.platform_manager as pm_mod
    sp = isolated_base_path / "tmp_agent" / "state" / "platforms"
    sp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pm_mod, "STATE_PATH", sp)
    # Reset singleton so each test starts fresh
    monkeypatch.setattr(pm_mod, "_platform_manager", None)


# ── _squash_signal / _round helpers ──────────────────────────────────────────

def test_squash_signal_zero():
    assert _squash_signal(0.0, 3.0) == 0.0


def test_squash_signal_bounded():
    assert -1.0 <= _squash_signal(100.0, 1.0) <= 1.0
    assert -1.0 <= _squash_signal(-100.0, 1.0) <= 1.0


def test_squash_signal_matches_utility():
    """Must produce same values as utility.py's _squash_signal."""
    expected = max(-1.0, min(1.0, math.tanh(2.5 / 3.0)))
    assert abs(_squash_signal(2.5, 3.0) - expected) < 1e-10


def test_round_precision():
    assert _round(0.123456789) == 0.1235
    assert _round(0.123456789, 2) == 0.12


# ── PlatformMetrics derived calculations ─────────────────────────────────────

def test_metrics_calculate_derived_basic():
    m = PlatformMetrics(platform="test", total_trades=10, winning_trades=7,
                        losing_trades=3, total_profit=15.0)
    m.calculate_derived_metrics()
    assert m.win_rate == 0.7
    assert m.expectancy == 1.5  # 15/10
    assert m.sample_quality == min(1.0, 10 / _MIN_PLATFORM_RESOLVED)


def test_metrics_drawdown_tracking():
    m = PlatformMetrics(platform="test", total_trades=5, winning_trades=3,
                        losing_trades=2, total_profit=10.0, peak_profit=20.0)
    m.calculate_derived_metrics()
    # peak stays at 20 since total_profit < peak_profit
    assert m.peak_profit == 20.0
    assert m.current_drawdown == 10.0  # 20 - 10
    assert m.max_drawdown == 10.0


def test_metrics_peak_profit_updates():
    m = PlatformMetrics(platform="test", total_trades=5, winning_trades=5,
                        total_profit=25.0, peak_profit=20.0)
    m.calculate_derived_metrics()
    assert m.peak_profit == 25.0
    assert m.current_drawdown == 0.0


# ── compute_platform_u (aligned formula) ─────────────────────────────────────

def test_compute_u_below_min_resolved():
    """U must be 0.0 when not enough trades."""
    m = PlatformMetrics(platform="test", total_trades=_MIN_PLATFORM_RESOLVED - 1)
    assert PlatformManager.compute_platform_u(m) == 0.0


def test_compute_u_positive_expectancy_no_drawdown():
    m = PlatformMetrics(platform="test", total_trades=10, winning_trades=8,
                        losing_trades=2, total_profit=20.0, peak_profit=20.0,
                        expectancy=2.0, max_drawdown=0.0, largest_loss_streak=0)
    u = PlatformManager.compute_platform_u(m)
    assert u > 0.0, "Positive expectancy with no drawdown should yield positive U"


def test_compute_u_negative_expectancy():
    m = PlatformMetrics(platform="test", total_trades=10, winning_trades=2,
                        losing_trades=8, total_profit=-15.0, peak_profit=5.0,
                        expectancy=-1.5, max_drawdown=20.0, largest_loss_streak=5)
    u = PlatformManager.compute_platform_u(m)
    assert u < 0.0, "Negative expectancy + large drawdown should yield negative U"


def test_compute_u_formula_components():
    """Verify the formula matches utility.py structure."""
    m = PlatformMetrics(platform="test", total_trades=10, winning_trades=6,
                        losing_trades=4, total_profit=5.0, peak_profit=10.0,
                        expectancy=0.5, max_drawdown=3.0, largest_loss_streak=2)
    u = PlatformManager.compute_platform_u(m)
    # Manual calculation
    growth = _squash_signal(0.5, 3.0)
    dd_fraction = 3.0 / max(10.0, 1.0)
    dd_penalty = max(0.0, min(2.0, dd_fraction / 0.30))
    tail_penalty = max(0.0, min(2.0, 2.0 / 5.0))
    expected = _round(growth - dd_penalty - tail_penalty)
    assert abs(u - expected) < 1e-8


# ── record_trade integration ─────────────────────────────────────────────────

def test_record_trade_win():
    pm = PlatformManager()
    pm.record_trade("pocket_option", "win", 5.0, symbol="EURUSD", strategy="strat_1")
    m = pm.get_platform_metrics("pocket_option")
    assert m.total_trades == 1
    assert m.winning_trades == 1
    assert m.total_profit == 5.0
    assert m.current_loss_streak == 0


def test_record_trade_loss_streak():
    pm = PlatformManager()
    for _ in range(3):
        pm.record_trade("ibkr", "loss", 2.0)
    m = pm.get_platform_metrics("ibkr")
    assert m.total_trades == 3
    assert m.losing_trades == 3
    assert m.current_loss_streak == 3
    assert m.largest_loss_streak == 3
    assert m.total_profit == -6.0


def test_record_trade_resets_loss_streak_on_win():
    pm = PlatformManager()
    pm.record_trade("ibkr", "loss", 1.0)
    pm.record_trade("ibkr", "loss", 1.0)
    pm.record_trade("ibkr", "win", 5.0)
    m = pm.get_platform_metrics("ibkr")
    assert m.current_loss_streak == 0
    assert m.largest_loss_streak == 2


def test_record_trade_triggers_u_update_at_threshold():
    pm = PlatformManager()
    # Record enough trades to pass _MIN_PLATFORM_RESOLVED
    for _ in range(_MIN_PLATFORM_RESOLVED):
        pm.record_trade("pocket_option", "win", 3.0)
    u = pm.get_platform_u("pocket_option")
    assert u.u_proxy != 0.0, "U should be computed after reaching min resolved"
    assert len(u.history) > 0


# ── state_io save/load cycle ─────────────────────────────────────────────────

def test_save_load_round_trip():
    pm1 = PlatformManager()
    for i in range(6):
        pm1.record_trade("pocket_option", "win" if i % 2 == 0 else "loss", 2.0)

    # Create fresh instance (re-loads from disk)
    pm2 = PlatformManager()
    m1 = pm1.get_platform_metrics("pocket_option")
    m2 = pm2.get_platform_metrics("pocket_option")
    assert m1.total_trades == m2.total_trades
    assert m1.win_rate == m2.win_rate
    assert abs(m1.total_profit - m2.total_profit) < 0.01


# ── PlatformU verdict thresholds ─────────────────────────────────────────────

def test_platform_u_verdict_no_promote():
    pu = PlatformU(platform="test")
    pu.update(-0.1)
    assert pu.verdict == "no_promote"
    assert "u_proxy_non_positive" in pu.blockers


def test_platform_u_verdict_needs_improvement():
    pu = PlatformU(platform="test")
    pu.update(0.15)
    assert pu.verdict == "needs_improvement"
    assert "u_below_threshold" in pu.blockers


def test_platform_u_verdict_ready():
    pu = PlatformU(platform="test")
    pu.update(0.35)
    assert pu.verdict == "ready_for_promotion"
    assert pu.blockers == []


# ── get_platform_manager singleton ───────────────────────────────────────────

def test_singleton_returns_same_instance():
    pm1 = get_platform_manager()
    pm2 = get_platform_manager()
    assert pm1 is pm2


# ── get_all_platforms_status / get_platform_comparison ────────────────────────

def test_get_all_platforms_status_all_idle():
    pm = PlatformManager()
    status = pm.get_all_platforms_status()
    assert set(status.keys()) == {"pocket_option", "ibkr", "internal_paper"}
    for pf_status in status.values():
        assert pf_status["total_trades"] == 0


def test_get_platform_comparison_ranking():
    pm = PlatformManager()
    # Give PO a better U than IBKR
    for _ in range(6):
        pm.record_trade("pocket_option", "win", 5.0)
    for _ in range(6):
        pm.record_trade("ibkr", "loss", 2.0)
    comp = pm.get_platform_comparison()
    assert comp["pocket_option"]["rank"] < comp["ibkr"]["rank"], "PO should rank higher"
