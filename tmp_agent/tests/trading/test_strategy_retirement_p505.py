"""P5-05: Tests for strategy retirement and recompute race-condition fix.

Covers:
1. _recompute() — retired state is never overridden
2. _recompute() — manual freeze (freeze_reason) is respected
3. _recompute() — manual freeze cleared when expectancy recovers
4. retire_frozen_strategies() — marks frozen strategies as retired after N days
5. retire_frozen_strategies() — ignores non-frozen strategies
6. retire_frozen_strategies() — stamps freeze_utc when missing
7. ensure_scorecards() — auto-retirement wired in
8. strategy_selector — retired strategies excluded from all selectors
9. strategy_selector — _governance_bonus returns heavy penalty for retired
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import brain_v9.config as _cfg
import brain_v9.trading.strategy_scorecard as sc
from brain_v9.trading.strategy_scorecard import (
    _recompute,
    retire_frozen_strategies,
    ensure_scorecards,
    _blank_scorecard,
    _utc_now,
)
from brain_v9.trading.strategy_selector import (
    _governance_bonus,
    _is_eligible,
    choose_top_candidate,
    choose_recovery_candidate,
    choose_exploit_candidate,
    choose_explore_candidate,
    choose_top_n_candidates,
    compute_rank_score,
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


def _make_card(
    strategy_id: str = "strat_01",
    governance_state: str = "frozen",
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
    card = _blank_scorecard(_make_strategy(strategy_id))
    card["governance_state"] = governance_state
    card["promotion_state"] = governance_state
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


def _make_selector_candidate(
    strategy_id: str = "strat_01",
    venue: str = "PocketOption",
    governance_state: str = "paper_active",
    rank_score: float = 0.5,
    execution_ready: bool = True,
    leadership_eligible: bool = True,
    paper_only: bool = True,
    venue_ready: bool = True,
    archive_state: str | None = None,
    freeze_recommended: bool = False,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "governance_state": governance_state,
        "context_governance_state": None,
        "rank_score": rank_score,
        "raw_rank_score": rank_score,
        "execution_ready": execution_ready,
        "leadership_eligible": leadership_eligible,
        "paper_only": paper_only,
        "venue_ready": venue_ready,
        "archive_state": archive_state,
        "freeze_recommended": freeze_recommended,
        "signal_valid": execution_ready,
        "signal_confidence": 0.6 if execution_ready else 0.0,
        "expectancy": 0.1,
        "context_expectancy": 0.1,
        "symbol_expectancy": 0.1,
        "context_expectancy_score": 0.5,
        "context_sample_quality": 0.5,
        "symbol_expectancy_score": 0.3,
        "symbol_sample_quality": 0.3,
    }


@pytest.fixture(autouse=True)
def _patch_scorecard_paths(monkeypatch, tmp_path):
    """Redirect strategy_scorecard module-level paths to tmp_path."""
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")


# ===========================================================================
# 1. _recompute — retired state is immutable
# ===========================================================================

class TestRecomputeRetiredImmutable:
    def test_retired_state_never_overridden_by_good_stats(self):
        """Even if a retired card has great stats, it stays retired."""
        card = _make_card(governance_state="retired")
        card["wins"] = 20
        card["losses"] = 2
        card["entries_resolved"] = 22
        card["gross_profit"] = 10.0
        card["gross_loss"] = 1.0
        card["expectancy"] = 0.40
        card["sample_quality"] = 1.0
        card["win_rate"] = 0.91
        _recompute(card)
        assert card["governance_state"] == "retired"
        assert card["promotion_state"] == "retired"
        assert card["freeze_recommended"] is False
        assert card["promote_candidate"] is False

    def test_retired_state_survives_zero_resolved(self):
        card = _make_card(governance_state="retired")
        card["entries_resolved"] = 0
        _recompute(card)
        assert card["governance_state"] == "retired"

    def test_retired_card_still_gets_metric_fields(self):
        card = _make_card(governance_state="retired")
        _recompute(card)
        assert "min_expectancy_required" in card
        assert "min_win_rate_required" in card
        assert "negative_expectancy_floor" in card
        assert "net_pnl" in card


# ===========================================================================
# 2. _recompute — manual freeze protection
# ===========================================================================

class TestRecomputeManualFreezeProtection:
    def test_manual_freeze_stays_frozen_when_expectancy_bad(self):
        """freeze_reason prevents recompute from overriding frozen state."""
        card = _make_card(
            governance_state="frozen",
            freeze_reason="drawdown_limit_breached_auto_freeze",
            freeze_utc="2026-03-01T00:00:00Z",
            expectancy=-0.20,
        )
        _recompute(card)
        assert card["governance_state"] == "frozen"
        assert card["promotion_state"] == "frozen"
        assert card.get("freeze_reason") == "drawdown_limit_breached_auto_freeze"

    def test_manual_freeze_cleared_when_expectancy_recovers(self):
        """When expectancy recovers above severe floor, freeze is lifted."""
        card = _make_card(
            governance_state="frozen",
            freeze_reason="drawdown_limit_breached_auto_freeze",
            freeze_utc="2026-03-01T00:00:00Z",
        )
        # Set good stats so expectancy recovers
        card["wins"] = 15
        card["losses"] = 5
        card["entries_resolved"] = 20
        card["gross_profit"] = 8.0
        card["gross_loss"] = 2.0
        card["success_criteria"] = {"min_expectancy": 0.05, "min_win_rate": 0.45, "min_resolved_trades": 10}
        # Recompute will recalculate expectancy from wins/losses
        _recompute(card)
        # Expectancy should be positive, freeze should be cleared
        assert card.get("freeze_reason") is None
        assert card.get("freeze_utc") is None
        # Should transition to a normal state (not frozen)
        assert card["governance_state"] != "frozen"

    def test_no_freeze_reason_allows_normal_transition(self):
        """Without freeze_reason, frozen strategies can transition normally."""
        card = _make_card(governance_state="frozen")
        # Give it 0 resolved trades — should become paper_candidate
        card["entries_resolved"] = 0
        card["wins"] = 0
        card["losses"] = 0
        card.pop("freeze_reason", None)
        _recompute(card)
        assert card["governance_state"] == "paper_candidate"


# ===========================================================================
# 3. retire_frozen_strategies()
# ===========================================================================

class TestRetireFrozenStrategies:
    def test_retires_frozen_strategy_past_threshold(self):
        freeze_dt = datetime.now(timezone.utc) - timedelta(days=15)
        cards = {
            "strat_01": _make_card(
                strategy_id="strat_01",
                governance_state="frozen",
                freeze_utc=freeze_dt.isoformat().replace("+00:00", "Z"),
            )
        }
        retired = retire_frozen_strategies(cards)
        assert retired == ["strat_01"]
        assert cards["strat_01"]["governance_state"] == "retired"
        assert cards["strat_01"]["promotion_state"] == "retired"
        assert cards["strat_01"]["archive_state"] == "archived_refuted"
        assert "retired_utc" in cards["strat_01"]
        assert cards["strat_01"]["retirement_reason"] == "auto_retired_frozen_14d"

    def test_does_not_retire_recently_frozen(self):
        freeze_dt = datetime.now(timezone.utc) - timedelta(days=5)
        cards = {
            "strat_01": _make_card(
                strategy_id="strat_01",
                governance_state="frozen",
                freeze_utc=freeze_dt.isoformat().replace("+00:00", "Z"),
            )
        }
        retired = retire_frozen_strategies(cards)
        assert retired == []
        assert cards["strat_01"]["governance_state"] == "frozen"

    def test_ignores_non_frozen_strategies(self):
        cards = {
            "strat_01": _make_card(governance_state="paper_active"),
            "strat_02": _make_card(strategy_id="strat_02", governance_state="paper_watch"),
        }
        retired = retire_frozen_strategies(cards)
        assert retired == []

    def test_stamps_freeze_utc_when_missing(self):
        cards = {
            "strat_01": _make_card(governance_state="frozen"),
        }
        # Remove freeze_utc
        cards["strat_01"].pop("freeze_utc", None)
        retired = retire_frozen_strategies(cards)
        assert retired == []  # not retired yet — just stamped
        assert "freeze_utc" in cards["strat_01"]

    def test_already_retired_not_reprocessed(self):
        """A strategy already retired won't match the 'frozen' check."""
        cards = {
            "strat_01": _make_card(governance_state="retired"),
        }
        retired = retire_frozen_strategies(cards)
        assert retired == []

    def test_respects_config_threshold(self, monkeypatch):
        """Retirement uses AUTONOMY_CONFIG['retirement_frozen_days']."""
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "retirement_frozen_days", 7)
        freeze_dt = datetime.now(timezone.utc) - timedelta(days=8)
        cards = {
            "strat_01": _make_card(
                strategy_id="strat_01",
                governance_state="frozen",
                freeze_utc=freeze_dt.isoformat().replace("+00:00", "Z"),
            )
        }
        retired = retire_frozen_strategies(cards)
        assert retired == ["strat_01"]

    def test_does_not_retire_when_under_custom_threshold(self, monkeypatch):
        monkeypatch.setitem(_cfg.AUTONOMY_CONFIG, "retirement_frozen_days", 30)
        freeze_dt = datetime.now(timezone.utc) - timedelta(days=20)
        cards = {
            "strat_01": _make_card(
                strategy_id="strat_01",
                governance_state="frozen",
                freeze_utc=freeze_dt.isoformat().replace("+00:00", "Z"),
            )
        }
        retired = retire_frozen_strategies(cards)
        assert retired == []

    def test_multiple_strategies_some_retired(self):
        old_freeze = datetime.now(timezone.utc) - timedelta(days=20)
        recent_freeze = datetime.now(timezone.utc) - timedelta(days=3)
        cards = {
            "old": _make_card(
                strategy_id="old",
                governance_state="frozen",
                freeze_utc=old_freeze.isoformat().replace("+00:00", "Z"),
            ),
            "recent": _make_card(
                strategy_id="recent",
                governance_state="frozen",
                freeze_utc=recent_freeze.isoformat().replace("+00:00", "Z"),
            ),
            "active": _make_card(
                strategy_id="active",
                governance_state="paper_active",
            ),
        }
        retired = retire_frozen_strategies(cards)
        assert "old" in retired
        assert "recent" not in retired
        assert "active" not in retired

    def test_handles_malformed_freeze_utc(self):
        cards = {
            "strat_01": _make_card(governance_state="frozen"),
        }
        cards["strat_01"]["freeze_utc"] = "not-a-date"
        retired = retire_frozen_strategies(cards)
        assert retired == []
        # Should have reset to a valid timestamp
        assert cards["strat_01"]["freeze_utc"] != "not-a-date"


# ===========================================================================
# 4. ensure_scorecards wires retirement
# ===========================================================================

class TestEnsureScorecardsRetirement:
    def test_ensure_scorecards_retires_old_frozen(self, tmp_path, monkeypatch):
        """ensure_scorecards() calls retire_frozen_strategies()."""
        from brain_v9.core.state_io import write_json

        strategy = _make_strategy()
        freeze_dt = datetime.now(timezone.utc) - timedelta(days=20)

        # Pre-seed scorecards with a frozen strategy
        scorecards_path = tmp_path / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
        card = _blank_scorecard(strategy)
        card["governance_state"] = "frozen"
        card["freeze_utc"] = freeze_dt.isoformat().replace("+00:00", "Z")
        card["entries_resolved"] = 5
        card["losses"] = 5
        card["gross_loss"] = 2.5
        card["expectancy"] = -0.15
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
        assert result_card["archive_state"] == "archived_refuted"


# ===========================================================================
# 5. _governance_bonus for retired state
# ===========================================================================

class TestGovernanceBonusRetired:
    def test_retired_gets_heavy_penalty(self):
        assert _governance_bonus("retired") == -0.50

    def test_retired_penalty_heavier_than_frozen(self):
        assert _governance_bonus("retired") < _governance_bonus("frozen")

    def test_retired_penalty_heavier_than_rejected(self):
        assert _governance_bonus("retired") < _governance_bonus("rejected")


# ===========================================================================
# 6. Selector functions exclude retired strategies
# ===========================================================================

class TestSelectorExcludesRetired:
    def test_choose_top_candidate_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        active = _make_selector_candidate(strategy_id="a1", governance_state="paper_active", rank_score=0.5)
        result = choose_top_candidate([retired, active])
        assert result is not None
        assert result["strategy_id"] == "a1"

    def test_choose_top_candidate_allow_frozen_still_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        frozen = _make_selector_candidate(
            strategy_id="f1", governance_state="frozen", rank_score=0.7,
            freeze_recommended=True,
        )
        result = choose_top_candidate([retired, frozen], allow_frozen=True)
        assert result is not None
        assert result["strategy_id"] == "f1"

    def test_choose_top_candidate_all_retired_returns_none(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired")
        result = choose_top_candidate([retired])
        assert result is None

    def test_is_eligible_returns_false_for_retired(self):
        retired = _make_selector_candidate(governance_state="retired")
        assert _is_eligible(retired) is False
        assert _is_eligible(retired, allow_frozen=True) is False

    def test_choose_top_n_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        active = _make_selector_candidate(strategy_id="a1", venue="ibkr", rank_score=0.5)
        results = choose_top_n_candidates([retired, active], n=2)
        assert len(results) == 1
        assert results[0]["strategy_id"] == "a1"

    def test_choose_recovery_candidate_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        active = _make_selector_candidate(strategy_id="a1", governance_state="paper_active", rank_score=0.5)
        result = choose_recovery_candidate([retired, active])
        assert result is not None
        assert result["strategy_id"] == "a1"

    def test_choose_exploit_candidate_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        active = _make_selector_candidate(strategy_id="a1", governance_state="paper_active", rank_score=0.5)
        result = choose_exploit_candidate([retired, active])
        assert result is not None
        assert result["strategy_id"] == "a1"

    def test_choose_explore_candidate_skips_retired(self):
        retired = _make_selector_candidate(strategy_id="r1", governance_state="retired", rank_score=0.9)
        active = _make_selector_candidate(strategy_id="a1", governance_state="paper_active", rank_score=0.5)
        result = choose_explore_candidate([retired, active])
        assert result is not None
        assert result["strategy_id"] == "a1"


# ===========================================================================
# 7. compute_rank_score includes retired_penalty
# ===========================================================================

class TestComputeRankScoreRetired:
    def test_retired_candidate_gets_penalty_in_breakdown(self):
        candidate = _make_selector_candidate(governance_state="retired")
        # Add required fields for compute_rank_score
        candidate.update({
            "expectancy_score": 0.5,
            "win_rate_score": 0.5,
            "profit_factor_score": 0.5,
            "sample_quality": 0.5,
            "consistency_score": 0.5,
            "drawdown_penalty": 0.0,
            "venue_health_score": 0.5,
            "regime_alignment_score": 0.5,
            "context_consistency_score": 0.5,
            "signal_blockers": [],
            "recent_5_outcomes": [],
            "entries_resolved": 15,
            "context_entries_resolved": 10,
            "symbol_entries_resolved": 10,
            "context_sample_quality": 0.5,
        })
        scoring = compute_rank_score(candidate, None)
        assert scoring["score_breakdown"]["retired_penalty"] == 1.0

    def test_active_candidate_no_retired_penalty(self):
        candidate = _make_selector_candidate(governance_state="paper_active")
        candidate.update({
            "expectancy_score": 0.5,
            "win_rate_score": 0.5,
            "profit_factor_score": 0.5,
            "sample_quality": 0.5,
            "consistency_score": 0.5,
            "drawdown_penalty": 0.0,
            "venue_health_score": 0.5,
            "regime_alignment_score": 0.5,
            "context_consistency_score": 0.5,
            "signal_blockers": [],
            "recent_5_outcomes": [],
            "entries_resolved": 15,
            "context_entries_resolved": 10,
            "symbol_entries_resolved": 10,
            "context_sample_quality": 0.5,
        })
        scoring = compute_rank_score(candidate, None)
        assert scoring["score_breakdown"]["retired_penalty"] == 0.0

    def test_retired_reason_in_reasons(self):
        candidate = _make_selector_candidate(governance_state="retired")
        candidate.update({
            "expectancy_score": 0.5,
            "win_rate_score": 0.5,
            "profit_factor_score": 0.5,
            "sample_quality": 0.5,
            "consistency_score": 0.5,
            "drawdown_penalty": 0.0,
            "venue_health_score": 0.5,
            "regime_alignment_score": 0.5,
            "context_consistency_score": 0.5,
            "signal_blockers": [],
            "recent_5_outcomes": [],
            "entries_resolved": 15,
            "context_entries_resolved": 10,
            "symbol_entries_resolved": 10,
            "context_sample_quality": 0.5,
        })
        scoring = compute_rank_score(candidate, None)
        assert "strategy_retired" in scoring["reasons"]
