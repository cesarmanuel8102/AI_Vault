"""P4-14: Tests for multi-action dispatch in AutonomyManager._utility_loop()."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain_v9.autonomy.manager import AutonomyManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gate(actions: list[str | dict]) -> Dict:
    """Build a gate dict like write_utility_snapshots returns."""
    return {
        "verdict": "hold",
        "allow_promote": False,
        "blockers": [],
        "required_next_actions": actions,
    }


def _make_snapshot(u: float = -0.18) -> Dict:
    return {
        "updated_utc": "2026-03-26T15:00:00Z",
        "u_proxy_score": u,
    }


# ---------------------------------------------------------------------------
# Tests: action lane classification
# ---------------------------------------------------------------------------

class TestLaneClassification:
    """Verify trading vs non-trading action classification."""

    def test_trading_actions_set(self):
        mgr = AutonomyManager()
        assert "increase_resolved_sample" in mgr._TRADING_ACTIONS
        assert "select_and_compare_strategies" in mgr._TRADING_ACTIONS
        assert "run_qc_backtest_validation" in mgr._TRADING_ACTIONS

    def test_non_trading_actions_set(self):
        mgr = AutonomyManager()
        assert "advance_meta_improvement_roadmap" in mgr._NON_TRADING_ACTIONS
        assert "synthesize_chat_product_contract" in mgr._NON_TRADING_ACTIONS

    def test_no_overlap(self):
        mgr = AutonomyManager()
        overlap = mgr._TRADING_ACTIONS & mgr._NON_TRADING_ACTIONS
        assert len(overlap) == 0, f"Overlap found: {overlap}"


# ---------------------------------------------------------------------------
# Tests: _dispatch_actions
# ---------------------------------------------------------------------------

class TestDispatchActions:
    """Test the multi-lane dispatch logic."""

    @pytest.fixture(autouse=True)
    def _mock_control_layer(self, monkeypatch):
        """Ensure dispatch tests are not blocked by filesystem control-layer state."""
        monkeypatch.setattr(
            "brain_v9.autonomy.manager.get_control_layer_status_latest",
            lambda: {"mode": "ACTIVE", "reason": "test", "execution_allowed": True},
        )

    @pytest.mark.asyncio
    async def test_single_trading_action(self, monkeypatch):
        """One trading action in the list → dispatched once."""
        mgr = AutonomyManager()
        gate = _make_gate(["increase_resolved_sample"])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_awaited_once_with("increase_resolved_sample")

    @pytest.mark.asyncio
    async def test_single_non_trading_action(self, monkeypatch):
        """One non-trading action → dispatched once."""
        mgr = AutonomyManager()
        gate = _make_gate(["advance_meta_improvement_roadmap"])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_awaited_once_with("advance_meta_improvement_roadmap")

    @pytest.mark.asyncio
    async def test_two_lanes_dispatched_concurrently(self, monkeypatch):
        """One trading + one non-trading → both dispatched (2 calls)."""
        mgr = AutonomyManager()
        gate = _make_gate([
            "increase_resolved_sample",
            "advance_meta_improvement_roadmap",
        ])
        snapshot = _make_snapshot()

        call_order = []
        async def _track_execute(action_name):
            call_order.append(action_name)
            return {"status": "completed"}

        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", _track_execute)

        await mgr._dispatch_actions(gate, snapshot)

        assert set(call_order) == {"increase_resolved_sample", "advance_meta_improvement_roadmap"}
        assert len(call_order) == 2

    @pytest.mark.asyncio
    async def test_two_trading_actions_only_first_dispatched(self, monkeypatch):
        """Two trading actions → only the first one is dispatched (same lane)."""
        mgr = AutonomyManager()
        gate = _make_gate([
            "increase_resolved_sample",
            "select_and_compare_strategies",
        ])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        # Only the first trading action should be dispatched
        mock_execute.assert_awaited_once_with("increase_resolved_sample")

    @pytest.mark.asyncio
    async def test_empty_actions_no_dispatch(self, monkeypatch):
        """Empty action list → nothing dispatched (when no probation candidate ready)."""
        mgr = AutonomyManager()
        gate = _make_gate([])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)
        # P-OP15: Mock read_ranking_v2 to return no probation candidate,
        # so the empty-action path is preserved for this test.
        monkeypatch.setattr(
            "brain_v9.trading.strategy_engine.read_ranking_v2",
            lambda: {"ranked": [], "probation_candidate": None},
        )

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dict_action_format(self, monkeypatch):
        """Actions can be dicts with 'action' key."""
        mgr = AutonomyManager()
        gate = _make_gate([{"action": "increase_resolved_sample"}])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_awaited_once_with("increase_resolved_sample")


# ---------------------------------------------------------------------------
# Tests: per-lane cooldown
# ---------------------------------------------------------------------------

class TestPerLaneCooldown:
    @pytest.fixture(autouse=True)
    def _mock_control_layer(self, monkeypatch):
        """Ensure cooldown tests are not blocked by filesystem control-layer state."""
        monkeypatch.setattr(
            "brain_v9.autonomy.manager.get_control_layer_status_latest",
            lambda: {"mode": "ACTIVE", "reason": "test", "execution_allowed": True},
        )

    def test_no_cooldown_initially(self):
        mgr = AutonomyManager()
        assert mgr._lane_cooldown_active("trading") is False
        assert mgr._lane_cooldown_active("non_trading") is False

    def test_cooldown_after_action(self):
        mgr = AutonomyManager()
        mgr._lane_last_action = {"trading": datetime.now()}
        assert mgr._lane_cooldown_active("trading") is True
        assert mgr._lane_cooldown_active("non_trading") is False

    def test_cooldown_expired(self):
        mgr = AutonomyManager()
        mgr._lane_last_action = {
            "trading": datetime.now() - timedelta(seconds=301),
        }
        assert mgr._lane_cooldown_active("trading") is False

    @pytest.mark.asyncio
    async def test_lane_cooldown_blocks_dispatch(self, monkeypatch):
        """If trading lane is on cooldown, trading action should NOT be dispatched."""
        mgr = AutonomyManager()
        mgr._lane_last_action = {"trading": datetime.now()}  # Active cooldown
        gate = _make_gate(["increase_resolved_sample"])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_lane_cooled_other_not(self, monkeypatch):
        """Trading on cooldown, but non-trading available → only non-trading dispatched."""
        mgr = AutonomyManager()
        mgr._lane_last_action = {"trading": datetime.now()}  # Trading blocked
        gate = _make_gate([
            "increase_resolved_sample",
            "advance_meta_improvement_roadmap",
        ])
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)

        mock_execute.assert_awaited_once_with("advance_meta_improvement_roadmap")

    @pytest.mark.asyncio
    async def test_run_action_updates_lane_cooldown(self, monkeypatch):
        """After _run_action, the lane cooldown should be set."""
        mgr = AutonomyManager()
        snapshot = _make_snapshot()

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._run_action("increase_resolved_sample", "trading", snapshot)

        assert mgr._lane_cooldown_active("trading") is True
        assert mgr._lane_cooldown_active("non_trading") is False
        # Legacy compat
        assert hasattr(mgr, '_last_action_time')


# ---------------------------------------------------------------------------
# Tests: backward compat
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_legacy_action_cooldown_active(self):
        """_action_cooldown_active still works for backward compatibility."""
        mgr = AutonomyManager()
        assert mgr._action_cooldown_active() is False

        mgr._last_action_time = datetime.now()
        assert mgr._action_cooldown_active() is True

        mgr._last_action_time = datetime.now() - timedelta(seconds=301)
        assert mgr._action_cooldown_active() is False
