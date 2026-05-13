"""P5-06: Tests for strategy unfreeze mechanism.

Covers:
1. unfreeze_eligible_strategies() — unfreezes when expectancy recovers
2. unfreeze_eligible_strategies() — respects minimum cooling period for manual freezes
3. unfreeze_eligible_strategies() — ignores non-frozen strategies
4. unfreeze_eligible_strategies() — ignores retired strategies
5. _recompute() — manual freeze with cooling period enforcement
6. ensure_scorecards() — unfreeze runs before retirement
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import brain_v9.config as _cfg
import brain_v9.trading.strategy_scorecard as sc
from brain_v9.trading.strategy_scorecard import (
    _recompute,
    unfreeze_eligible_strategies,
    retire_frozen_strategies,
    ensure_scorecards,
    _blank_scorecard,
    _utc_now,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(strategy_id: str = "strat_01", venue: str = "PocketOption"):
    return {
        "strategy_id": strategy_id,
        "family": "test_family",
        "venue": venue,
        "status": "paper_candidate",
        "universe": ["EURUSD"],
        "timeframes": ["5m"],
        "setup_variants": ["base"],
        "linked_hypotheses": [],
        "success_criteria": {
            "min_resolved_trades": 10,
            "min_expectancy": 0.05,
            "min_win_rate": 0.45,
        },
    }


def _make_frozen_card(
    strategy_id: str = "strat_01",
    freeze_reason: str | None = None,
    freeze_utc: str | None = None,
    expectancy: float = -0.20,
    wins: int = 2,
    losses: int = 8,
    entries_resolved: int = 10,
    gross_profit: float = 1.0,
    gross_loss: float = 4.0,
    net_pnl: float = -3.0,
) -> dict:
    """Create a frozen scorecard with configurable stats."""
    card = _blank_scorecard(_make_strategy(strategy_id))
    card["governance_state"] = "frozen"
    card["promotion_state"] = "frozen"
    card["wins"] = wins
    card["losses"] = losses
    card["entries_resolved"] = entries_resolved
    card["gross_profit"] = gross_profit
    card["gross_loss"] = gross_loss
    card["net_pnl"] = net_pnl
    card["expectancy"] = expectancy
    if freeze_reason:
        card["freeze_reason"] = freeze_reason
    if freeze_utc:
        card["freeze_utc"] = freeze_utc
    return card


def _make_recovered_card(
    strategy_id: str = "strat_01",
    freeze_reason: str | None = "drawdown_limit_breached_auto_freeze",
    freeze_utc: str | None = None,
) -> dict:
    """Create a frozen card with stats that indicate recovery."""
    card = _make_frozen_card(
        strategy_id=strategy_id,
        freeze_reason=freeze_reason,
        freeze_utc=freeze_utc,
        wins=15,
        losses=5,
        entries_resolved=20,
        gross_profit=8.0,
        gross_loss=2.0,
        net_pnl=6.0,
    )
    # These will be recalculated by _recompute, but set expectancy
    # above the severe_negative_floor to allow unfreeze
    card["expectancy"] = 0.10
    return card


@pytest.fixture(autouse=True)
def _patch_scorecard_paths(monkeypatch, tmp_path):
    """Redirect strategy_scorecard module-level paths to tmp_path."""
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")


# ===========================================================================
# 1. unfreeze_eligible_strategies — computed freeze, expectancy recovers
# ===========================================================================

class TestUnfreezeComputedFreeze:
    def test_unfreezes_when_expectancy_recovers(self):
        """A computed-frozen strategy unfreezes when expectancy improves."""
        card = _make_frozen_card(
            strategy_id="s1",
            # No freeze_reason = computed freeze
            wins=12,
            losses=3,
            entries_resolved=15,
            gross_profit=6.0,
            gross_loss=1.0,
        )
        # Expectancy will be recalculated by _recompute
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert "s1" in unfrozen
        assert cards["s1"]["governance_state"] != "frozen"

    def test_stays_frozen_when_expectancy_still_bad(self):
        """A computed-frozen strategy stays frozen with bad stats."""
        card = _make_frozen_card(strategy_id="s1")
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []
        assert cards["s1"]["governance_state"] == "frozen"

    def test_ignores_non_frozen(self):
        card = _blank_scorecard(_make_strategy("s1"))
        card["governance_state"] = "paper_active"
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []

    def test_ignores_retired(self):
        card = _blank_scorecard(_make_strategy("s1"))
        card["governance_state"] = "retired"
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []


# ===========================================================================
# 2. unfreeze_eligible_strategies — manual freeze with cooling period
# ===========================================================================

class TestUnfreezeManualFreeze:
    def test_unfreezes_manual_after_cooldown_and_recovery(self):
        """Manual freeze lifted after cooling period + recovery."""
        old_freeze = datetime.now(timezone.utc) - timedelta(days=5)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=old_freeze.isoformat().replace("+00:00", "Z"),
        )
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert "s1" in unfrozen
        assert cards["s1"]["governance_state"] != "frozen"
        assert "freeze_reason" not in cards["s1"]

    def test_stays_frozen_during_cooldown_even_with_recovery(self):
        """Manual freeze not lifted until cooling period elapses."""
        recent_freeze = datetime.now(timezone.utc) - timedelta(hours=12)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=recent_freeze.isoformat().replace("+00:00", "Z"),
        )
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []
        assert cards["s1"]["governance_state"] == "frozen"
        # freeze_reason should still be present
        assert "freeze_reason" in cards["s1"]

    def test_stays_frozen_if_expectancy_still_bad_after_cooldown(self):
        """Even after cooldown, no unfreeze if expectancy still bad."""
        old_freeze = datetime.now(timezone.utc) - timedelta(days=5)
        card = _make_frozen_card(
            strategy_id="s1",
            freeze_reason="drawdown_limit_breached_auto_freeze",
            freeze_utc=old_freeze.isoformat().replace("+00:00", "Z"),
            # Bad stats — expectancy stays severely negative
        )
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []
        assert cards["s1"]["governance_state"] == "frozen"

    def test_respects_custom_cooldown_days(self, monkeypatch):
        """Uses AUTONOMY_CONFIG['unfreeze_min_frozen_days']."""
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "unfreeze_min_frozen_days", 10)
        freeze_5d_ago = datetime.now(timezone.utc) - timedelta(days=5)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=freeze_5d_ago.isoformat().replace("+00:00", "Z"),
        )
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        # 5 days < 10 day cooldown — should still be frozen
        assert unfrozen == []
        assert cards["s1"]["governance_state"] == "frozen"

    def test_zero_cooldown_unfreezes_immediately(self, monkeypatch):
        """Setting cooldown to 0 allows immediate unfreeze."""
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "unfreeze_min_frozen_days", 0)
        recent_freeze = datetime.now(timezone.utc) - timedelta(minutes=5)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=recent_freeze.isoformat().replace("+00:00", "Z"),
        )
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert "s1" in unfrozen


# ===========================================================================
# 3. _recompute cooldown enforcement
# ===========================================================================

class TestRecomputeCooldownEnforcement:
    def test_recompute_keeps_manual_freeze_during_cooldown(self):
        """_recompute respects cooling period for manual freeze."""
        recent_freeze = datetime.now(timezone.utc) - timedelta(hours=6)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=recent_freeze.isoformat().replace("+00:00", "Z"),
        )
        _recompute(card)
        assert card["governance_state"] == "frozen"
        assert card.get("freeze_reason") is not None

    def test_recompute_clears_manual_freeze_after_cooldown(self):
        """_recompute clears manual freeze after cooling period."""
        old_freeze = datetime.now(timezone.utc) - timedelta(days=5)
        card = _make_recovered_card(
            strategy_id="s1",
            freeze_utc=old_freeze.isoformat().replace("+00:00", "Z"),
        )
        _recompute(card)
        assert card["governance_state"] != "frozen"
        assert card.get("freeze_reason") is None

    def test_recompute_keeps_freeze_bad_expectancy_after_cooldown(self):
        """After cooldown but with bad stats, stays frozen."""
        old_freeze = datetime.now(timezone.utc) - timedelta(days=5)
        card = _make_frozen_card(
            strategy_id="s1",
            freeze_reason="drawdown_limit_breached_auto_freeze",
            freeze_utc=old_freeze.isoformat().replace("+00:00", "Z"),
        )
        _recompute(card)
        assert card["governance_state"] == "frozen"


class TestProbationWindow:
    def test_recompute_keeps_positive_low_sample_strategy_in_probe(self, monkeypatch):
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "probation_min_resolved_trades", 5)
        card = _blank_scorecard(_make_strategy("s1"))
        card["wins"] = 1
        card["losses"] = 0
        card["entries_resolved"] = 1
        card["gross_profit"] = 8.0
        card["gross_loss"] = 0.0
        card["net_pnl"] = 8.0
        _recompute(card)
        assert card["governance_state"] == "paper_probe"
        assert card["promotion_state"] == "paper_probe"

    def test_recompute_allows_active_after_probation_window(self, monkeypatch):
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "probation_min_resolved_trades", 5)
        card = _blank_scorecard(_make_strategy("s1"))
        card["wins"] = 4
        card["losses"] = 1
        card["entries_resolved"] = 5
        card["gross_profit"] = 16.0
        card["gross_loss"] = 2.0
        card["net_pnl"] = 14.0
        _recompute(card)
        assert card["governance_state"] in {"paper_active", "paper_watch", "promote_candidate"}


# ===========================================================================
# 4. ensure_scorecards runs unfreeze before retirement
# ===========================================================================

class TestEnsureScorecardsUnfreezeOrder:
    def test_unfreeze_runs_before_retirement(self, tmp_path, monkeypatch):
        """A recoverable strategy is unfrozen, not retired."""
        from brain_v9.core.state_io import write_json

        strategy = _make_strategy()
        # Frozen 20 days ago (past retirement threshold) but recoverable
        old_freeze = datetime.now(timezone.utc) - timedelta(days=20)

        card = _blank_scorecard(strategy)
        card["governance_state"] = "frozen"
        card["freeze_reason"] = "drawdown_limit_breached_auto_freeze"
        card["freeze_utc"] = old_freeze.isoformat().replace("+00:00", "Z")
        # Good stats — should recover
        card["wins"] = 15
        card["losses"] = 5
        card["entries_resolved"] = 20
        card["gross_profit"] = 8.0
        card["gross_loss"] = 2.0
        card["net_pnl"] = 6.0

        scorecards_path = tmp_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        write_json(scorecards_path, {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": _utc_now(),
            "scorecards": {strategy["strategy_id"]: card},
            "symbol_scorecards": {},
            "context_scorecards": {},
        })

        payload = ensure_scorecards([strategy])
        result_card = payload["scorecards"][strategy["strategy_id"]]
        # Should be unfrozen, NOT retired — unfreeze runs first
        assert result_card["governance_state"] != "retired"
        assert result_card["governance_state"] != "frozen"

    def test_unreoverable_strategy_gets_retired(self, tmp_path, monkeypatch):
        """A non-recoverable frozen strategy still gets retired."""
        from brain_v9.core.state_io import write_json

        strategy = _make_strategy()
        old_freeze = datetime.now(timezone.utc) - timedelta(days=20)

        card = _blank_scorecard(strategy)
        card["governance_state"] = "frozen"
        card["freeze_utc"] = old_freeze.isoformat().replace("+00:00", "Z")
        # Bad stats — won't recover
        card["wins"] = 1
        card["losses"] = 9
        card["entries_resolved"] = 10
        card["gross_profit"] = 0.5
        card["gross_loss"] = 5.0
        card["net_pnl"] = -4.5

        scorecards_path = tmp_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        write_json(scorecards_path, {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": _utc_now(),
            "scorecards": {strategy["strategy_id"]: card},
            "symbol_scorecards": {},
            "context_scorecards": {},
        })

        payload = ensure_scorecards([strategy])
        result_card = payload["scorecards"][strategy["strategy_id"]]
        assert result_card["governance_state"] == "retired"


# ===========================================================================
# 5. Multiple strategies mix
# ===========================================================================

class TestUnfreezeMultipleStrategies:
    def test_mix_of_recoverable_and_unrecoverable(self):
        """Only recoverable frozen strategies get unfrozen."""
        old_freeze = datetime.now(timezone.utc) - timedelta(days=5)
        freeze_str = old_freeze.isoformat().replace("+00:00", "Z")

        # Recoverable
        good_card = _make_recovered_card(
            strategy_id="good",
            freeze_utc=freeze_str,
        )
        # Not recoverable
        bad_card = _make_frozen_card(
            strategy_id="bad",
            freeze_reason="drawdown_limit_breached_auto_freeze",
            freeze_utc=freeze_str,
        )
        # Not frozen
        active_card = _blank_scorecard(_make_strategy("active"))
        active_card["governance_state"] = "paper_active"

        cards = {"good": good_card, "bad": bad_card, "active": active_card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert "good" in unfrozen
        assert "bad" not in unfrozen
        assert "active" not in unfrozen

    def test_returns_empty_when_no_frozen(self):
        card = _blank_scorecard(_make_strategy("s1"))
        card["governance_state"] = "paper_active"
        cards = {"s1": card}
        unfrozen = unfreeze_eligible_strategies(cards)
        assert unfrozen == []
