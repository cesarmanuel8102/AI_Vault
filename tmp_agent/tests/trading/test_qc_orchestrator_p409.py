"""
P4-09 — Tests for QCBacktestOrchestrator.

Tests cover:
  - extract_metrics / _parse_pct / _parse_float helpers
  - compile_and_wait: success, build error, timeout
  - launch_and_wait: success, runtime error, timeout, progress tracking
  - run_backtest: end-to-end lifecycle
  - State persistence across phases
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_orchestrator(tmp_path, connector=None, **kwargs):
    """Build an orchestrator with a tmp state dir and optional mock connector."""
    from brain_v9.trading.qc_orchestrator import QCBacktestOrchestrator
    defaults = dict(
        connector=connector,
        state_dir=tmp_path / "qc_state",
        compile_timeout=10,
        compile_poll=0,       # no delay in tests
        backtest_timeout=10,
        backtest_poll=0,      # no delay in tests
    )
    defaults.update(kwargs)
    return QCBacktestOrchestrator(**defaults)


# ===========================================================================
# Metric extraction helpers
# ===========================================================================
class TestParsePct:
    def test_percentage_string(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("15.2%") == pytest.approx(0.152)

    def test_negative_percentage(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("-8.5%") == pytest.approx(-0.085)

    def test_plain_float_no_percent(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("1.23") == pytest.approx(1.23)

    def test_empty_returns_none(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("") is None

    def test_garbage_returns_none(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("N/A") is None

    def test_dollar_sign_stripped(self):
        from brain_v9.trading.qc_orchestrator import _parse_pct
        assert _parse_pct("$115,234") == pytest.approx(115234.0)


class TestParseFloat:
    def test_simple(self):
        from brain_v9.trading.qc_orchestrator import _parse_float
        assert _parse_float("1.23") == pytest.approx(1.23)

    def test_comma_thousand_separator(self):
        from brain_v9.trading.qc_orchestrator import _parse_float
        assert _parse_float("1,234.56") == pytest.approx(1234.56)

    def test_empty(self):
        from brain_v9.trading.qc_orchestrator import _parse_float
        assert _parse_float("") is None


class TestExtractMetrics:
    def test_full_extraction(self):
        from brain_v9.trading.qc_orchestrator import extract_metrics
        raw = {
            "metrics": {
                "sharpe_ratio": "1.23",
                "sortino_ratio": "1.56",
                "compounding_annual_return": "15.2%",
                "drawdown": "8.5%",
                "net_profit": "15.2%",
                "win_rate": "60%",
                "loss_rate": "40%",
                "expectancy": "0.456",
                "total_orders": "42",
                "profit_loss_ratio": "1.67",
                "alpha": "0.05",
                "beta": "0.8",
            }
        }
        m = extract_metrics(raw)
        assert m["sharpe_ratio"] == pytest.approx(1.23)
        assert m["win_rate"] == pytest.approx(0.60)
        assert m["drawdown"] == pytest.approx(0.085)
        assert m["total_orders"] == 42
        assert m["expectancy"] == pytest.approx(0.456)

    def test_empty_metrics(self):
        from brain_v9.trading.qc_orchestrator import extract_metrics
        m = extract_metrics({})
        assert m["sharpe_ratio"] is None
        assert m["total_orders"] == 0


# ===========================================================================
# compile_and_wait
# ===========================================================================
class TestCompileAndWait:
    def test_compile_success(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
        })
        conn.read_compile = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "BuildSuccess",
            "build_success": True, "build_error": False, "errors": [],
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.compile_and_wait(12345))
        assert result["success"] is True
        assert result["compile_id"] == "c-1"
        assert result["phase"] == "compile_success"

    def test_compile_trigger_failure(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": False, "error": "Unauthorized",
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.compile_and_wait(12345))
        assert result["success"] is False
        assert "compile_failed" in result["phase"]

    def test_compile_build_error(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
        })
        conn.read_compile = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "BuildError",
            "build_success": False, "build_error": True, "errors": ["syntax"],
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.compile_and_wait(12345))
        assert result["success"] is False
        assert result["phase"] == "compile_error"

    def test_compile_timeout(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
        })
        # Always return InQueue → never finishes
        conn.read_compile = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
            "build_success": False, "build_error": False, "errors": [],
        })
        orch = _make_orchestrator(tmp_path, connector=conn, compile_timeout=0)
        result = _run(orch.compile_and_wait(12345))
        assert result["success"] is False
        assert result["phase"] == "compile_timeout"


# ===========================================================================
# launch_and_wait
# ===========================================================================
class TestLaunchAndWait:
    def test_backtest_complete(self, tmp_path):
        conn = AsyncMock()
        conn.create_backtest = AsyncMock(return_value={
            "success": True, "backtest_id": "bt-1",
        })
        conn.read_backtest = AsyncMock(return_value={
            "success": True, "completed": True, "error": "",
            "metrics": {
                "sharpe_ratio": "1.5",
                "sortino_ratio": "",
                "compounding_annual_return": "20%",
                "drawdown": "10%",
                "net_profit": "20%",
                "win_rate": "55%",
                "loss_rate": "45%",
                "expectancy": "0.3",
                "total_orders": "100",
                "profit_loss_ratio": "1.2",
                "alpha": "0.04",
                "beta": "0.9",
            },
            "statistics": {},
            "runtime_statistics": {},
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.launch_and_wait(12345, "c-1", "test"))
        assert result["success"] is True
        assert result["backtest_id"] == "bt-1"
        assert result["metrics"]["sharpe_ratio"] == pytest.approx(1.5)
        assert result["metrics"]["win_rate"] == pytest.approx(0.55)

    def test_backtest_create_failure(self, tmp_path):
        conn = AsyncMock()
        conn.create_backtest = AsyncMock(return_value={
            "success": False, "error": "rate limited",
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.launch_and_wait(12345, "c-1"))
        assert result["success"] is False
        assert "backtest_create_failed" in result["phase"]

    def test_backtest_runtime_error(self, tmp_path):
        conn = AsyncMock()
        conn.create_backtest = AsyncMock(return_value={
            "success": True, "backtest_id": "bt-1",
        })
        conn.read_backtest = AsyncMock(return_value={
            "success": True, "completed": True,
            "error": "NullReferenceException",
            "stacktrace": "at Main.Initialize()",
            "metrics": {},
            "statistics": {},
            "runtime_statistics": {},
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.launch_and_wait(12345, "c-1"))
        assert result["success"] is False
        assert result["phase"] == "backtest_runtime_error"
        assert "NullReference" in result.get("error", "")

    def test_backtest_timeout(self, tmp_path):
        conn = AsyncMock()
        conn.create_backtest = AsyncMock(return_value={
            "success": True, "backtest_id": "bt-1",
        })
        conn.read_backtest = AsyncMock(return_value={
            "success": True, "completed": False, "progress": 0.3,
            "error": "", "metrics": {},
            "statistics": {}, "runtime_statistics": {},
        })
        orch = _make_orchestrator(tmp_path, connector=conn, backtest_timeout=0)
        result = _run(orch.launch_and_wait(12345, "c-1"))
        assert result["success"] is False
        assert result["phase"] == "backtest_timeout"

    def test_progress_saved_to_state(self, tmp_path):
        """While polling, progress updates are persisted to disk."""
        call_count = 0

        async def _polling_read(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return {
                    "success": True, "completed": True, "error": "",
                    "progress": 1.0,
                    "metrics": {
                        "sharpe_ratio": "1.0", "sortino_ratio": "", "compounding_annual_return": "",
                        "drawdown": "", "net_profit": "", "win_rate": "", "loss_rate": "",
                        "expectancy": "", "total_orders": "10", "profit_loss_ratio": "",
                        "alpha": "", "beta": "",
                    },
                    "statistics": {}, "runtime_statistics": {},
                }
            return {
                "success": True, "completed": False, "progress": 0.5,
                "error": "", "metrics": {},
                "statistics": {}, "runtime_statistics": {},
            }

        conn = AsyncMock()
        conn.create_backtest = AsyncMock(return_value={
            "success": True, "backtest_id": "bt-1",
        })
        conn.read_backtest = AsyncMock(side_effect=_polling_read)
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.launch_and_wait(12345, "c-1"))
        assert result["success"] is True
        # State file should exist
        state = orch.load_run_state(12345)
        assert state.get("phase") == "backtest_complete"


# ===========================================================================
# run_backtest (end-to-end)
# ===========================================================================
class TestRunBacktest:
    def test_full_lifecycle(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
        })
        conn.read_compile = AsyncMock(return_value={
            "success": True, "build_success": True, "build_error": False,
            "compile_id": "c-1", "state": "BuildSuccess", "errors": [],
        })
        conn.create_backtest = AsyncMock(return_value={
            "success": True, "backtest_id": "bt-1",
        })
        conn.read_backtest = AsyncMock(return_value={
            "success": True, "completed": True, "error": "",
            "progress": 1.0,
            "metrics": {
                "sharpe_ratio": "2.0", "sortino_ratio": "2.5",
                "compounding_annual_return": "30%", "drawdown": "5%",
                "net_profit": "30%", "win_rate": "70%", "loss_rate": "30%",
                "expectancy": "0.8", "total_orders": "50",
                "profit_loss_ratio": "2.3", "alpha": "0.1", "beta": "0.6",
            },
            "statistics": {}, "runtime_statistics": {},
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.run_backtest(12345, "Auto Backtest"))
        assert result["success"] is True
        assert result["metrics"]["sharpe_ratio"] == pytest.approx(2.0)
        assert result["metrics"]["win_rate"] == pytest.approx(0.70)
        assert result["phase"] == "backtest_complete"

    def test_compile_failure_short_circuits(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": False, "error": "auth fail",
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        result = _run(orch.run_backtest(12345))
        assert result["success"] is False
        assert "compile" in result["phase"]
        # create_backtest should NOT have been called
        conn.create_backtest.assert_not_awaited()


# ===========================================================================
# State persistence
# ===========================================================================
class TestStatePersistence:
    def test_state_saved_and_loaded(self, tmp_path):
        conn = AsyncMock()
        conn.compile_project = AsyncMock(return_value={
            "success": True, "compile_id": "c-1", "state": "InQueue",
        })
        conn.read_compile = AsyncMock(return_value={
            "success": True, "build_success": True, "build_error": False,
            "compile_id": "c-1", "state": "BuildSuccess", "errors": [],
        })
        orch = _make_orchestrator(tmp_path, connector=conn)
        _run(orch.compile_and_wait(99999))
        state = orch.load_run_state(99999)
        assert state["project_id"] == 99999
        assert state["phase"] == "compile_success"
        assert "updated_utc" in state

    def test_empty_state_returns_empty_dict(self, tmp_path):
        orch = _make_orchestrator(tmp_path)
        assert orch.load_run_state(11111) == {}
