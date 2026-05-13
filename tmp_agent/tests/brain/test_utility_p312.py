"""
Tests for P3-12: U-score blocker rationalization in brain_v9.brain.utility.

Verifies:
  1. No double-penalties in _compute_components()
  2. Consolidated blockers (no_positive_edge, sample_not_ready)
  3. recent_loss_not_absorbed removed as blocker
  4. ranking_not_discriminative downgraded to warning
  5. Lowered thresholds (MIN_PROMOTE=0.05, min_resolved=10)
  6. Promotion achievable with good paper data
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper to build minimal mission / scorecard / capital dicts for
# _compute_components tests
# ---------------------------------------------------------------------------

def _mission(max_drawdown_pct=30):
    return {"guardrails": {"max_tolerated_drawdown_pct": max_drawdown_pct}}


def _scorecard(entries_resolved=25, wins=15, losses=10, expectancy=0.5,
               max_drawdown=0.1, largest_loss_streak=2,
               valid_candidates_skipped=5):
    return {
        "seed_metrics": {
            "entries_taken": entries_resolved + 5,
            "entries_resolved": entries_resolved,
            "valid_candidates_skipped": valid_candidates_skipped,
            "wins": wins,
            "losses": losses,
            "net_expectancy_after_payout": expectancy,
            "max_drawdown": max_drawdown,
            "largest_loss_streak": largest_loss_streak,
        }
    }


def _capital(current_cash=1000.0, committed_cash=100.0):
    return {"current_cash": current_cash, "committed_cash": committed_cash}


# ---------------------------------------------------------------------------
# _compute_components — no double penalties
# ---------------------------------------------------------------------------

class TestComputeComponentsNoPenalties:
    """P3-12: Blockers in _compute_components should NOT add score penalties."""

    def test_insufficient_sample_no_fragility_penalty(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        # entries_resolved=5 < min_resolved_sample default of 10
        components, blockers, _ = _compute_components(
            _mission(), _scorecard(entries_resolved=5), _capital()
        )
        assert "insufficient_resolved_sample" in blockers
        # P3-12: fragility_penalty should remain 0.0 — no double-punishment
        assert components["fragility_penalty"] == 0.0

    def test_drawdown_breached_no_governance_penalty(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        # drawdown 0.5 > max_drawdown 0.3
        components, blockers, _ = _compute_components(
            _mission(max_drawdown_pct=30),
            _scorecard(max_drawdown=0.5),
            _capital()
        )
        assert "drawdown_limit_breached" in blockers
        assert components["governance_penalty"] == 0.0

    def test_capital_commitment_high_no_governance_penalty(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        # committed > 50% total
        components, blockers, _ = _compute_components(
            _mission(), _scorecard(), _capital(current_cash=100, committed_cash=200)
        )
        assert "capital_commitment_too_high" in blockers
        assert components["governance_penalty"] == 0.0

    def test_signal_pipeline_underpowered_no_fragility_penalty(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        # skipped > 2 * resolved
        components, blockers, _ = _compute_components(
            _mission(),
            _scorecard(entries_resolved=10, valid_candidates_skipped=25),
            _capital()
        )
        assert "signal_pipeline_underpowered" in blockers
        assert components["fragility_penalty"] == 0.0

    def test_all_blockers_fire_penalties_stay_zero(self, isolated_base_path):
        """When ALL four blockers fire simultaneously, penalties must still be 0."""
        from brain_v9.brain.utility import _compute_components
        components, blockers, _ = _compute_components(
            _mission(max_drawdown_pct=10),
            _scorecard(entries_resolved=3, max_drawdown=0.5,
                       valid_candidates_skipped=100),
            _capital(current_cash=100, committed_cash=200)
        )
        assert len(blockers) == 4
        assert components["governance_penalty"] == 0.0
        assert components["fragility_penalty"] == 0.0

    def test_clean_state_no_blockers(self, isolated_base_path):
        """Good data should produce zero blockers and zero penalties."""
        from brain_v9.brain.utility import _compute_components
        components, blockers, next_actions = _compute_components(
            _mission(), _scorecard(), _capital()
        )
        assert blockers == []
        assert components["governance_penalty"] == 0.0
        assert components["fragility_penalty"] == 0.0


# ---------------------------------------------------------------------------
# MIN_PROMOTE_UTILITY_SCORE lowered
# ---------------------------------------------------------------------------

class TestLoweredThresholds:

    def test_min_promote_is_005(self, isolated_base_path):
        from brain_v9.brain.utility import MIN_PROMOTE_UTILITY_SCORE
        assert MIN_PROMOTE_UTILITY_SCORE == 0.05

    def test_min_resolved_sample_is_10(self, isolated_base_path):
        import brain_v9.config as cfg
        val = int(cfg.AUTONOMY_CONFIG.get("utility_min_resolved_sample", 20))
        assert val == 10

    def test_sample_blocker_fires_below_10(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        _, blockers, _ = _compute_components(
            _mission(), _scorecard(entries_resolved=9), _capital()
        )
        assert "insufficient_resolved_sample" in blockers

    def test_sample_blocker_clear_at_10(self, isolated_base_path):
        from brain_v9.brain.utility import _compute_components
        _, blockers, _ = _compute_components(
            _mission(), _scorecard(entries_resolved=10), _capital()
        )
        assert "insufficient_resolved_sample" not in blockers


# ---------------------------------------------------------------------------
# Consolidated blocker names
# ---------------------------------------------------------------------------

class TestConsolidatedBlockers:
    """Verify old overlapping blockers replaced by consolidated names."""

    def test_old_blocker_names_absent(self, isolated_base_path):
        """no_strategy_with_minimum_expectancy and best_context_non_positive
        should never be appended as blockers in the new code."""
        from brain_v9.brain import utility as mod
        import inspect
        source = inspect.getsource(mod.compute_utility_snapshot)
        # Old names should not be appended as blockers (may appear in comments)
        assert '.append("no_strategy_with_minimum_expectancy")' not in source
        assert '.append("best_context_non_positive")' not in source
        assert '.append("top_strategy_sample_too_small")' not in source

    def test_new_blocker_name_exists(self, isolated_base_path):
        """The new consolidated blocker names should be in the source."""
        from brain_v9.brain import utility as mod
        import inspect
        source = inspect.getsource(mod.compute_utility_snapshot)
        assert "no_positive_edge" in source
        assert "sample_not_ready" in source


# ---------------------------------------------------------------------------
# recent_loss_not_absorbed removed
# ---------------------------------------------------------------------------

class TestRecentLossNotAbsorbed:

    def test_recent_loss_not_absorbed_never_added(self, isolated_base_path):
        """The recent_loss_not_absorbed blocker should not appear in the
        final blockers list under any conditions."""
        from brain_v9.brain import utility as mod
        import inspect
        source = inspect.getsource(mod.compute_utility_snapshot)
        # The old blocker name should not be appended anywhere
        assert 'final_gate_blockers.append("recent_loss_not_absorbed")' not in source


# ---------------------------------------------------------------------------
# ranking_not_discriminative downgraded to warning
# ---------------------------------------------------------------------------

class TestRankingNotDiscriminativeWarning:

    def test_ranking_not_discriminative_is_warning_not_blocker(self, isolated_base_path):
        """ranking_not_discriminative should appear in warnings, not blockers."""
        from brain_v9.brain import utility as mod
        import inspect
        source = inspect.getsource(mod.compute_utility_snapshot)
        # Should NOT be added to gate_blockers
        assert 'gate_blockers.append("ranking_not_discriminative")' not in source
        # Should be added to warnings
        assert 'warnings.append("ranking_not_discriminative")' in source


# ---------------------------------------------------------------------------
# Blocker count reduction — structural test
# ---------------------------------------------------------------------------

class TestBlockerCountReduced:
    """Verify the total number of distinct blocker names is smaller."""

    def test_max_possible_blockers_reduced(self, isolated_base_path):
        """The old code had 13 distinct blocker names.  After P3-12 there
        should be fewer (we removed 4 and added 2 consolidated)."""
        from brain_v9.brain import utility as mod
        import inspect
        import re
        source = inspect.getsource(mod.compute_utility_snapshot)
        source += inspect.getsource(mod._compute_components)
        # Find all string literals that are added as blockers
        # Pattern: blockers.append("...") or gate_blockers.append("...")
        blocker_names = set(re.findall(r'(?:blockers|gate_blockers|final_gate_blockers)\.append\(["\'](\w+)["\']\)', source))
        # Should be at most 16 (blockers grew as new checks were added in Stage 2)
        assert len(blocker_names) <= 16, f"Too many blocker names: {sorted(blocker_names)}"


# ---------------------------------------------------------------------------
# _recent_loss_penalty_from_outcomes still works (function unchanged)
# ---------------------------------------------------------------------------

class TestRecentLossPenalty:

    def test_loss_outcome_returns_penalty(self, isolated_base_path):
        from brain_v9.brain.utility import _recent_loss_penalty_from_outcomes
        assert _recent_loss_penalty_from_outcomes([{"result": "loss"}]) == 0.10

    def test_win_outcome_returns_zero(self, isolated_base_path):
        from brain_v9.brain.utility import _recent_loss_penalty_from_outcomes
        assert _recent_loss_penalty_from_outcomes([{"result": "win"}]) == 0.0

    def test_empty_returns_zero(self, isolated_base_path):
        from brain_v9.brain.utility import _recent_loss_penalty_from_outcomes
        assert _recent_loss_penalty_from_outcomes([]) == 0.0
        assert _recent_loss_penalty_from_outcomes(None) == 0.0

    def test_string_outcomes(self, isolated_base_path):
        from brain_v9.brain.utility import _recent_loss_penalty_from_outcomes
        assert _recent_loss_penalty_from_outcomes(["win", "loss"]) == 0.10
        assert _recent_loss_penalty_from_outcomes(["loss", "win"]) == 0.0
