"""P4-12: Tests for choose_top_n_candidates() cross-venue diversity selector."""
from __future__ import annotations

import pytest

from brain_v9.trading.strategy_selector import (
    choose_top_n_candidates,
    _is_eligible,
    build_ranking,
    choose_recovery_candidate,
    choose_exploit_candidate,
    choose_explore_candidate,
    choose_probation_candidate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    strategy_id: str,
    venue: str,
    rank_score: float = 0.5,
    execution_ready: bool = True,
    leadership_eligible: bool = True,
    governance_state: str = "paper_candidate",
    context_governance_state: str | None = None,
    freeze_recommended: bool = False,
    archive_state: str | None = None,
    paper_only: bool = True,
    venue_ready: bool = True,
    context_expectancy_score: float = 0.0,
    context_sample_quality: float = 0.0,
    symbol_expectancy_score: float = 0.0,
    symbol_sample_quality: float = 0.0,
    current_context_edge_state: str = "supportive",
    current_context_execution_allowed: bool = True,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "rank_score": rank_score,
        "raw_rank_score": rank_score,
        "execution_ready": execution_ready,
        "leadership_eligible": leadership_eligible,
        "governance_state": governance_state,
        "context_governance_state": context_governance_state,
        "freeze_recommended": freeze_recommended,
        "archive_state": archive_state,
        "paper_only": paper_only,
        "venue_ready": venue_ready,
        "signal_valid": execution_ready,
        "signal_confidence": 0.6 if execution_ready else 0.0,
        "context_expectancy_score": context_expectancy_score,
        "context_sample_quality": context_sample_quality,
        "symbol_expectancy_score": symbol_expectancy_score,
        "symbol_sample_quality": symbol_sample_quality,
        "current_context_edge_state": current_context_edge_state,
        "current_context_execution_allowed": current_context_execution_allowed,
    }


# ---------------------------------------------------------------------------
# _is_eligible
# ---------------------------------------------------------------------------

class TestIsEligible:
    def test_eligible_normal(self):
        c = _make_candidate("s1", "ibkr")
        assert _is_eligible(c) is True

    def test_archived_not_eligible(self):
        c = _make_candidate("s1", "ibkr", archive_state="archived_2025")
        assert _is_eligible(c) is False

    def test_not_execution_ready(self):
        c = _make_candidate("s1", "ibkr", execution_ready=False)
        assert _is_eligible(c) is False

    def test_frozen_not_eligible_by_default(self):
        c = _make_candidate("s1", "ibkr", governance_state="frozen")
        assert _is_eligible(c) is False

    def test_frozen_eligible_when_allow_frozen(self):
        c = _make_candidate("s1", "ibkr", governance_state="frozen")
        assert _is_eligible(c, allow_frozen=True) is True

    def test_freeze_recommended_not_eligible(self):
        c = _make_candidate("s1", "ibkr", freeze_recommended=True)
        assert _is_eligible(c) is False

    def test_context_frozen_not_eligible(self):
        c = _make_candidate("s1", "ibkr", context_governance_state="frozen")
        assert _is_eligible(c) is False

    def test_not_leadership_eligible(self):
        c = _make_candidate("s1", "ibkr", leadership_eligible=False)
        assert _is_eligible(c) is False

    def test_not_leadership_eligible_but_allow_frozen(self):
        """allow_frozen skips governance/leadership checks after archive+exec_ready."""
        c = _make_candidate("s1", "ibkr", leadership_eligible=False)
        # allow_frozen=True bypasses leadership check
        assert _is_eligible(c, allow_frozen=True) is True

    def test_context_blocked_not_eligible(self):
        c = _make_candidate("s1", "ibkr", current_context_execution_allowed=False)
        assert _is_eligible(c) is False


# ---------------------------------------------------------------------------
# choose_top_n_candidates: basic behavior
# ---------------------------------------------------------------------------

class TestChooseTopN:
    def test_empty_ranked(self):
        assert choose_top_n_candidates([], n=3) == []

    def test_n_zero(self):
        c = _make_candidate("s1", "ibkr")
        assert choose_top_n_candidates([c], n=0) == []

    def test_single_candidate(self):
        c = _make_candidate("s1", "ibkr", rank_score=0.7)
        result = choose_top_n_candidates([c], n=3)
        assert len(result) == 1
        assert result[0]["strategy_id"] == "s1"

    def test_respects_n_limit(self):
        candidates = [
            _make_candidate("s1", "ibkr", rank_score=0.9),
            _make_candidate("s2", "pocket_option", rank_score=0.8),
            _make_candidate("s3", "internal_paper", rank_score=0.7),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Cross-venue diversity
# ---------------------------------------------------------------------------

class TestCrossVenueDiversity:
    def test_prefers_different_venues(self):
        """With 2 IBKR and 1 PO candidate, n=2 should pick one from each venue."""
        candidates = [
            _make_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_candidate("ibkr2", "ibkr", rank_score=0.85),
            _make_candidate("po1", "pocket_option", rank_score=0.5),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        venues = {c["venue"] for c in result}
        assert venues == {"ibkr", "pocket_option"}

    def test_best_per_venue_selected(self):
        """Should pick the highest-ranked from each venue."""
        candidates = [
            _make_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_candidate("po1", "pocket_option", rank_score=0.8),
            _make_candidate("ibkr2", "ibkr", rank_score=0.7),
            _make_candidate("po2", "pocket_option", rank_score=0.3),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        ids = {c["strategy_id"] for c in result}
        assert ids == {"ibkr1", "po1"}

    def test_backfill_same_venue_when_needed(self):
        """If n=3 but only 2 venues, third slot backfills from best remaining."""
        candidates = [
            _make_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_candidate("po1", "pocket_option", rank_score=0.8),
            _make_candidate("ibkr2", "ibkr", rank_score=0.7),
        ]
        result = choose_top_n_candidates(candidates, n=3)
        assert len(result) == 3
        ids = {c["strategy_id"] for c in result}
        assert ids == {"ibkr1", "po1", "ibkr2"}

    def test_three_venues(self):
        """With 3 venues and n=3, should pick one from each."""
        candidates = [
            _make_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_candidate("po1", "pocket_option", rank_score=0.85),
            _make_candidate("int1", "internal_paper", rank_score=0.4),
            _make_candidate("ibkr2", "ibkr", rank_score=0.6),
        ]
        result = choose_top_n_candidates(candidates, n=3)
        venues = {c["venue"] for c in result}
        assert venues == {"ibkr", "pocket_option", "internal_paper"}

    def test_result_sorted_by_rank_score(self):
        """Returned list should be sorted by rank_score descending."""
        candidates = [
            _make_candidate("ibkr1", "ibkr", rank_score=0.5),
            _make_candidate("po1", "pocket_option", rank_score=0.9),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        assert result[0]["strategy_id"] == "po1"
        assert result[1]["strategy_id"] == "ibkr1"


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    def test_skips_ineligible_candidates(self):
        candidates = [
            _make_candidate("s1", "ibkr", rank_score=0.9, governance_state="frozen"),
            _make_candidate("s2", "ibkr", rank_score=0.7),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        assert len(result) == 1
        assert result[0]["strategy_id"] == "s2"

    def test_exclude_strategy_ids(self):
        candidates = [
            _make_candidate("s1", "ibkr", rank_score=0.9),
            _make_candidate("s2", "pocket_option", rank_score=0.8),
        ]
        result = choose_top_n_candidates(candidates, n=2, exclude_strategy_ids=["s1"])
        assert len(result) == 1
        assert result[0]["strategy_id"] == "s2"

    def test_allow_frozen_includes_frozen(self):
        candidates = [
            _make_candidate("s1", "ibkr", rank_score=0.9, governance_state="frozen"),
            _make_candidate("s2", "pocket_option", rank_score=0.8),
        ]
        result = choose_top_n_candidates(candidates, n=2, allow_frozen=True)
        assert len(result) == 2
        ids = {c["strategy_id"] for c in result}
        assert ids == {"s1", "s2"}

    def test_all_ineligible_returns_empty(self):
        candidates = [
            _make_candidate("s1", "ibkr", execution_ready=False),
            _make_candidate("s2", "pocket_option", governance_state="frozen"),
        ]
        result = choose_top_n_candidates(candidates, n=2)
        assert result == []

    def test_exclude_none_strategy_ids(self):
        """exclude_strategy_ids=None should not filter anything."""
        candidates = [_make_candidate("s1", "ibkr", rank_score=0.8)]
        result = choose_top_n_candidates(candidates, n=1, exclude_strategy_ids=None)
        assert len(result) == 1


class TestRecoveryAndExploit:
    def test_top_candidate_skips_candidate_with_blocked_current_context(self):
        blocked = _make_candidate(
            "blocked_top",
            "ibkr",
            rank_score=0.95,
            current_context_edge_state="contradicted",
            current_context_execution_allowed=False,
        )
        backup = _make_candidate(
            "healthy_top",
            "pocket_option",
            rank_score=0.70,
            current_context_edge_state="supportive",
            current_context_execution_allowed=True,
        )
        from brain_v9.trading.strategy_selector import choose_top_candidate
        result = choose_top_candidate([blocked, backup])
        assert result is not None
        assert result["strategy_id"] == "healthy_top"

    def test_recovery_skips_frozen_candidate_without_meaningful_positive_context(self):
        candidate = _make_candidate(
            "po_reversion",
            "pocket_option",
            governance_state="frozen",
            freeze_recommended=True,
            leadership_eligible=False,
            context_expectancy_score=1.0,
            context_sample_quality=0.03,
        )
        assert choose_recovery_candidate([candidate]) is None

    def test_recovery_allows_frozen_candidate_with_meaningful_positive_context(self):
        candidate = _make_candidate(
            "po_reversion",
            "pocket_option",
            governance_state="frozen",
            freeze_recommended=True,
            leadership_eligible=False,
            context_expectancy_score=1.0,
            context_sample_quality=0.15,
        )
        result = choose_recovery_candidate([candidate])
        assert result is not None
        assert result["strategy_id"] == "po_reversion"

    def test_recovery_skips_probation_only_candidate(self):
        candidate = _make_candidate(
            "po_auto",
            "pocket_option",
            governance_state="paper_probe",
            leadership_eligible=False,
        )
        candidate["probation_eligible"] = True
        candidate["execution_ready_now"] = True
        assert choose_recovery_candidate([candidate]) is None

    def test_exploit_does_not_fall_back_to_frozen_recovery_candidate(self):
        frozen_ready = _make_candidate(
            "frozen_candidate",
            "pocket_option",
            governance_state="frozen",
            freeze_recommended=True,
            leadership_eligible=False,
        )
        assert choose_exploit_candidate([frozen_ready]) is None

    def test_exploit_does_not_use_non_leadership_probe_as_fallback(self):
        probe = _make_candidate(
            "probe_candidate",
            "pocket_option",
            governance_state="paper_probe",
            freeze_recommended=False,
            execution_ready=True,
            leadership_eligible=False,
        )
        assert choose_exploit_candidate([probe]) is None

    def test_explore_skips_frozen_negative_candidate_without_recovery_signal(self):
        frozen_negative = _make_candidate(
            "frozen_negative",
            "ibkr",
            governance_state="frozen",
            freeze_recommended=True,
            execution_ready=True,
            leadership_eligible=True,
            context_expectancy_score=0.0,
            context_sample_quality=0.0,
            symbol_expectancy_score=-1.0,
            symbol_sample_quality=0.6,
        )
        assert choose_explore_candidate([frozen_negative]) is None

    def test_exploit_skips_candidate_with_contradicted_current_context(self):
        contradicted = _make_candidate(
            "contradicted_candidate",
            "ibkr",
            current_context_edge_state="contradicted",
            current_context_execution_allowed=False,
        )
        assert choose_exploit_candidate([contradicted]) is None

    def test_explore_allows_frozen_candidate_with_positive_context_and_sample(self):
        frozen_recoverable = _make_candidate(
            "frozen_recoverable",
            "ibkr",
            governance_state="frozen",
            freeze_recommended=True,
            execution_ready=True,
            leadership_eligible=False,
            context_expectancy_score=0.8,
            context_sample_quality=0.2,
        )
        result = choose_explore_candidate([frozen_recoverable])
        assert result is not None
        assert result["strategy_id"] == "frozen_recoverable"


class TestProbationCandidate:
    def test_choose_probation_candidate_prefers_probation_ready_candidate(self):
        active = _make_candidate(
            "ibkr_active",
            "ibkr",
            rank_score=0.9,
            leadership_eligible=True,
        )
        active["probation_eligible"] = False
        active["probation_budget"] = 0

        probation = _make_candidate(
            "po_auto",
            "pocket_option",
            rank_score=0.2,
            leadership_eligible=False,
        )
        probation["probation_eligible"] = True
        probation["probation_budget"] = 3
        probation["signal_confidence"] = 0.81

        result = choose_probation_candidate([active, probation])
        assert result is not None
        assert result["strategy_id"] == "po_auto"

    def test_choose_probation_candidate_skips_contradicted_context(self):
        contradicted = _make_candidate(
            "po_bad",
            "pocket_option",
            leadership_eligible=False,
            current_context_edge_state="contradicted",
            current_context_execution_allowed=False,
        )
        contradicted["probation_eligible"] = True
        contradicted["probation_budget"] = 3
        contradicted["signal_confidence"] = 0.8

        healthy = _make_candidate(
            "po_ok",
            "pocket_option",
            leadership_eligible=False,
            current_context_edge_state="unproven",
            current_context_execution_allowed=True,
        )
        healthy["probation_eligible"] = True
        healthy["probation_budget"] = 2
        healthy["signal_confidence"] = 0.75

        result = choose_probation_candidate([contradicted, healthy])
        assert result is not None
        assert result["strategy_id"] == "po_ok"
