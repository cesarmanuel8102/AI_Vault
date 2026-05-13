"""
P4-11 — Tests for run_qc_backtest_validation autonomy action.

Tests cover:
  - ACTION_MAP registration (11 entries now)
  - Successful end-to-end: orchestrator → bridge → strategy_specs
  - Orchestrator failure propagation
  - Round-robin project selection
  - Exception handling
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _patch_action_executor(monkeypatch, base_path):
    """Minimal monkeypatching to make action_executor importable with isolated paths."""
    import brain_v9.config as _cfg
    monkeypatch.setattr(_cfg, "BASE_PATH", base_path)
    # Re-derive paths
    monkeypatch.setattr(_cfg, "BRAIN_V9_PATH", base_path / "tmp_agent")

    from brain_v9.autonomy import action_executor as ae
    monkeypatch.setattr(ae, "BASE_PATH", base_path)
    return ae


# ===========================================================================
# ACTION_MAP registration
# ===========================================================================
class TestActionMapQC:
    def test_action_map_has_12_entries(self):
        from brain_v9.autonomy.action_executor import ACTION_MAP
        assert len(ACTION_MAP) == 12

    def test_qc_action_registered(self):
        from brain_v9.autonomy.action_executor import ACTION_MAP
        assert "run_qc_backtest_validation" in ACTION_MAP

    def test_handler_is_callable(self):
        from brain_v9.autonomy.action_executor import ACTION_MAP
        assert callable(ACTION_MAP["run_qc_backtest_validation"])


# ===========================================================================
# Successful run
# ===========================================================================
class TestRunQcBacktestSuccess:
    def test_returns_success_with_metrics(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        mock_orch_instance = AsyncMock()
        mock_orch_instance.run_backtest = AsyncMock(return_value={
            "success": True,
            "phase": "backtest_complete",
            "backtest_id": "bt-999",
            "metrics": {
                "sharpe_ratio": 1.8,
                "win_rate": 0.65,
                "drawdown": 0.07,
                "total_orders": 50,
                "expectancy": 0.5,
            },
        })

        mock_spec = {
            "strategy_id": "qc_24654779_bt-999ab",
            "status": "qc_backtest_validated",
        }

        with patch(
            "brain_v9.trading.qc_orchestrator.QCBacktestOrchestrator",
            return_value=mock_orch_instance,
        ), patch(
            "brain_v9.trading.qc_strategy_bridge.backtest_to_strategy_spec",
            return_value=mock_spec,
        ), patch(
            "brain_v9.trading.qc_strategy_bridge.merge_qc_strategy",
            return_value={"action": "inserted", "strategy_id": "qc_24654779_bt-999ab"},
        ):
            result = _run(ae.run_qc_backtest_validation())

        assert result["success"] is True
        assert result["action_name"] == "run_qc_backtest_validation"
        assert result["venue"] == "quantconnect"
        assert result["paper_only_enforced"] is True
        assert result["strategy_id"] == "qc_24654779_bt-999ab"
        assert result["merge_action"] == "inserted"
        assert result["metrics"]["sharpe_ratio"] == 1.8


# ===========================================================================
# Failure handling
# ===========================================================================
class TestRunQcBacktestFailure:
    def test_orchestrator_failure_propagated(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        mock_orch_instance = AsyncMock()
        mock_orch_instance.run_backtest = AsyncMock(return_value={
            "success": False,
            "phase": "compile_error",
            "error": "syntax error in main.py",
        })

        with patch(
            "brain_v9.trading.qc_orchestrator.QCBacktestOrchestrator",
            return_value=mock_orch_instance,
        ):
            result = _run(ae.run_qc_backtest_validation())

        assert result["success"] is False
        assert result["phase"] == "compile_error"
        assert "syntax" in result.get("error", "")

    def test_exception_caught(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        mock_orch_instance = AsyncMock()
        mock_orch_instance.run_backtest = AsyncMock(
            side_effect=ConnectionError("QC API unreachable"),
        )

        with patch(
            "brain_v9.trading.qc_orchestrator.QCBacktestOrchestrator",
            return_value=mock_orch_instance,
        ):
            result = _run(ae.run_qc_backtest_validation())

        assert result["success"] is False
        assert "unreachable" in result["error"]


# ===========================================================================
# Round-robin project selection
# ===========================================================================
class TestProjectRoundRobin:
    def test_cycles_through_projects(self, isolated_base_path, monkeypatch):
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        captured_project_ids = []

        original_fn = ae.run_qc_backtest_validation

        async def _capturing_run():
            """Call the real function but capture which project_id was selected."""
            # Read the action state BEFORE the call (it gets updated inside)
            state_path = isolated_base_path / "tmp_agent" / "state" / "qc_backtests" / "action_state.json"
            # Call with mocked orchestrator
            mock_orch_instance = AsyncMock()
            mock_orch_instance.run_backtest = AsyncMock(return_value={
                "success": False, "phase": "compile_error", "error": "test",
            })
            with patch(
                "brain_v9.trading.qc_orchestrator.QCBacktestOrchestrator",
                return_value=mock_orch_instance,
            ):
                result = await ae.run_qc_backtest_validation()
            captured_project_ids.append(result["project_id"])
            return result

        # Run 4 times to verify round-robin cycles
        for _ in range(4):
            _run(_capturing_run())

        # Should cycle: 24654779, 25550271, 24654779, 25550271
        assert captured_project_ids[0] == 24654779
        assert captured_project_ids[1] == 25550271
        assert captured_project_ids[2] == 24654779
        assert captured_project_ids[3] == 25550271
