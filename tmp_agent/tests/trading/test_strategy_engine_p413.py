"""P4-13: Tests for parallel cross-venue execute_comparison_cycle()."""
from __future__ import annotations

import asyncio
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import brain_v9.trading.strategy_engine as se


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ranked_candidate(
    strategy_id: str,
    venue: str,
    rank_score: float = 0.5,
    execution_ready: bool = True,
    leadership_eligible: bool = True,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": "breakout",
        "rank_score": rank_score,
        "raw_rank_score": rank_score,
        "priority_score": rank_score,
        "execution_ready": execution_ready,
        "leadership_eligible": leadership_eligible,
        "governance_state": "paper_candidate",
        "context_governance_state": None,
        "freeze_recommended": False,
        "archive_state": None,
        "paper_only": True,
        "venue_ready": True,
        "signal_valid": execution_ready,
        "signal_confidence": 0.6,
        "preferred_symbol": f"SYM_{strategy_id}",
        "preferred_timeframe": "5m",
        "preferred_setup_variant": "base",
        "recommended_iterations": 1,
        "expectancy": 0.02,
        "context_expectancy": 0.03,
        "sample_quality": 0.4,
    }


def _mock_refresh(ranked: List[Dict]):
    """Return a refresh_strategy_engine mock that yields the given ranked list."""
    ranking = {
        "ranked": ranked,
        "top_strategy": ranked[0] if ranked else None,
        "top_recovery_candidate": ranked[0] if ranked else None,
        "exploit_candidate": ranked[0] if ranked else None,
        "explore_candidate": ranked[1] if len(ranked) > 1 else None,
    }
    return {
        "ranking": ranking,
        "signals": {"items": []},
        "features": {"items": []},
        "archive": {"archived": []},
    }


def _make_batch_result(strategy_id: str, success: bool = True) -> Dict:
    return {
        "success": success,
        "run_id": f"run_{strategy_id}",
        "strategy_id": strategy_id,
        "paper_only": True,
        "successful_executions": 1 if success else 0,
        "failed_executions": 0 if success else 1,
        "total_profit": 0.05 if success else 0.0,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParallelComparisonCycle:
    """Test the P4-13 parallel cross-venue dispatch in execute_comparison_cycle."""

    @pytest.fixture(autouse=True)
    def _patch_engine(self, isolated_base_path, monkeypatch):
        """Patch strategy_engine module-level paths and heavy functions."""
        engine_path = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        engine_path.mkdir(parents=True, exist_ok=True)
        comp_path = engine_path / "comparison_runs"
        comp_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(se, "ENGINE_PATH", engine_path)
        monkeypatch.setattr(se, "COMPARISON_RUNS_PATH", comp_path)
        monkeypatch.setattr(se, "REPORTS_PATH", engine_path / "reports.ndjson")

    @pytest.mark.asyncio
    async def test_cross_venue_candidates_dispatched_in_parallel(self, monkeypatch):
        """When candidates span 2 venues, asyncio.gather should be called with 2 tasks."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.8),
        ]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["success"] is True
        assert result["selected_candidates"] == 2
        # Both strategies executed
        executed_ids = {row["strategy_id"] for row in result["comparison_rows"]}
        assert executed_ids == {"ibkr1", "po1"}

    @pytest.mark.asyncio
    async def test_same_venue_candidates_run_sequentially(self, monkeypatch):
        """When both candidates are same venue, they should run in order (not parallel)."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("ibkr2", "ibkr", rank_score=0.7),
        ]
        refresh_result = _mock_refresh(ranked)

        call_order = []
        async def _track_batch(sid, iters, allow_frozen=False):
            call_order.append(sid)
            return _make_batch_result(sid)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", _track_batch)

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["success"] is True
        # Within the same venue group, execution order follows rank order
        assert call_order == ["ibkr1", "ibkr2"]

    @pytest.mark.asyncio
    async def test_cross_venue_diversity_in_selection(self, monkeypatch):
        """With 2 IBKR + 1 PO, max_candidates=2 should pick one from each venue."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("ibkr2", "ibkr", rank_score=0.85),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.5),
        ]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=2)

        executed_ids = {row["strategy_id"] for row in result["comparison_rows"]}
        assert executed_ids == {"ibkr1", "po1"}

    @pytest.mark.asyncio
    async def test_partial_venue_failure_doesnt_crash_cycle(self, monkeypatch):
        """If one venue group fails, the other venue's results should still appear."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.8),
        ]
        refresh_result = _mock_refresh(ranked)

        async def _failing_batch(sid, iters, allow_frozen=False):
            if sid == "po1":
                raise RuntimeError("PO connector down")
            return _make_batch_result(sid)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", _failing_batch)

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["success"] is True
        # Only the IBKR result should be present
        executed_ids = {row["strategy_id"] for row in result["comparison_rows"]}
        assert "ibkr1" in executed_ids
        # PO group crashed, so po1 should NOT be in results
        assert "po1" not in executed_ids

    @pytest.mark.asyncio
    async def test_single_candidate_works(self, monkeypatch):
        """Edge case: only 1 eligible candidate."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
        ]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["success"] is True
        assert result["selected_candidates"] == 1
        assert result["comparison_rows"][0]["strategy_id"] == "ibkr1"

    @pytest.mark.asyncio
    async def test_no_eligible_candidates(self, monkeypatch):
        """Edge case: all candidates frozen, none eligible."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9, execution_ready=False),
        ]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["success"] is True
        assert result["selected_candidates"] == 0
        assert result["comparison_rows"] == []

    @pytest.mark.asyncio
    async def test_three_venues_parallel(self, monkeypatch):
        """Three different venues should create 3 parallel tasks."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.8),
            _make_ranked_candidate("int1", "internal_paper", rank_score=0.7),
        ]
        refresh_result = _mock_refresh(ranked)

        executed_sids = []
        async def _track(sid, iters, allow_frozen=False):
            executed_sids.append(sid)
            return _make_batch_result(sid)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", _track)

        result = await se.execute_comparison_cycle(max_candidates=3)

        assert result["success"] is True
        assert result["selected_candidates"] == 3
        assert set(executed_sids) == {"ibkr1", "po1", "int1"}

    @pytest.mark.asyncio
    async def test_comparison_roles_assigned(self, monkeypatch):
        """First candidate should be exploit, second explore, rest ranked_fill."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.8),
            _make_ranked_candidate("int1", "internal_paper", rank_score=0.7),
        ]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=3)

        roles = {row["strategy_id"]: row["comparison_role"] for row in result["comparison_rows"]}
        assert roles["ibkr1"] == "exploit"
        assert roles["po1"] == "explore"
        assert roles["int1"] == "ranked_fill"

    @pytest.mark.asyncio
    async def test_artifact_written(self, isolated_base_path, monkeypatch):
        """Comparison cycle should write result artifact to disk."""
        ranked = [_make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9)]
        refresh_result = _mock_refresh(ranked)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", AsyncMock(
            side_effect=lambda sid, iters, allow_frozen=False: _make_batch_result(sid)
        ))

        result = await se.execute_comparison_cycle(max_candidates=1)

        assert result["success"] is True
        artifact_path = result.get("artifact")
        assert artifact_path is not None
        from pathlib import Path
        assert Path(artifact_path).exists()

    @pytest.mark.asyncio
    async def test_iterations_capped(self, monkeypatch):
        """iterations_per_candidate should be capped at 3."""
        ranked = [_make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9)]
        refresh_result = _mock_refresh(ranked)

        captured_iters = []
        async def _capture(sid, iters, allow_frozen=False):
            captured_iters.append(iters)
            return _make_batch_result(sid)

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", _capture)

        await se.execute_comparison_cycle(max_candidates=1, iterations_per_candidate=10)
        # Iterations capped to 3
        assert captured_iters[0] == 3

    @pytest.mark.asyncio
    async def test_total_profit_aggregated(self, monkeypatch):
        """Total profit from all candidates should be summed."""
        ranked = [
            _make_ranked_candidate("ibkr1", "ibkr", rank_score=0.9),
            _make_ranked_candidate("po1", "pocket_option", rank_score=0.8),
        ]
        refresh_result = _mock_refresh(ranked)

        async def _profit_batch(sid, iters, allow_frozen=False):
            result = _make_batch_result(sid)
            result["total_profit"] = 0.10
            return result

        monkeypatch.setattr(se, "refresh_strategy_engine", lambda: refresh_result)
        monkeypatch.setattr(se, "execute_candidate_batch", _profit_batch)

        result = await se.execute_comparison_cycle(max_candidates=2)

        assert result["total_profit"] == pytest.approx(0.20, abs=0.001)
