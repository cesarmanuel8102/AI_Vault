"""
P4-08 — Tests for QuantConnectConnector compile + backtest lifecycle methods.

All API calls are mocked (no real HTTP); we verify request construction,
response parsing, and error handling for:
  compile_project, read_compile, create_backtest, read_backtest, list_backtests
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector(monkeypatch):
    """Return a QuantConnectConnector with fake credentials (no disk read)."""
    monkeypatch.setattr(
        "brain_v9.trading.connectors.SECRETS",
        {"quantconnect": MagicMock(exists=MagicMock(return_value=False))},
    )
    from brain_v9.trading.connectors import QuantConnectConnector
    qc = QuantConnectConnector(user_id="test_user", token="test_token")
    return qc


def _mock_response(payload: dict, status: int = 200):
    """Create a mock aiohttp response context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# compile_project
# ===========================================================================
class TestCompileProject:
    def test_success(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "compileId": "abc-123",
            "state": "InQueue",
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.compile_project(24654779))
        assert result["success"] is True
        assert result["compile_id"] == "abc-123"
        assert result["state"] == "InQueue"
        assert result["errors"] == []

    def test_api_failure_returns_false(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {"success": False, "errors": ["Unauthorized"]}
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload, status=401))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.compile_project(24654779))
        assert result["success"] is False

    def test_network_error(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        qc._get_session = AsyncMock(side_effect=Exception("timeout"))

        result = _run(qc.compile_project(24654779))
        assert result["success"] is False
        assert "timeout" in result["error"]


# ===========================================================================
# read_compile
# ===========================================================================
class TestReadCompile:
    def test_build_success(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "compileId": "abc-123",
            "state": "BuildSuccess",
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_compile(24654779, "abc-123"))
        assert result["success"] is True
        assert result["build_success"] is True
        assert result["build_error"] is False

    def test_build_error(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "compileId": "abc-123",
            "state": "BuildError",
            "errors": ["Syntax error line 42"],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_compile(24654779, "abc-123"))
        assert result["build_success"] is False
        assert result["build_error"] is True
        assert len(result["errors"]) == 1

    def test_still_in_queue(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {"success": True, "compileId": "abc-123", "state": "InQueue", "errors": []}
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_compile(24654779, "abc-123"))
        assert result["build_success"] is False
        assert result["build_error"] is False
        assert result["state"] == "InQueue"


# ===========================================================================
# create_backtest
# ===========================================================================
class TestCreateBacktest:
    def test_success(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "backtest": {
                "backtestId": "bt-001",
                "name": "Brain V9 Backtest",
                "completed": False,
                "status": "In Queue...",
                "progress": 0,
                "error": "",
            },
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.create_backtest(24654779, "abc-123", "Brain V9 Backtest"))
        assert result["success"] is True
        assert result["backtest_id"] == "bt-001"
        assert result["completed"] is False
        assert result["progress"] == 0

    def test_missing_backtest_key(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        # API returns success but no backtest object (edge case)
        payload = {"success": True, "errors": []}
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.create_backtest(24654779, "abc-123"))
        assert result["success"] is True
        assert result["backtest_id"] == ""

    def test_network_error(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        qc._get_session = AsyncMock(side_effect=ConnectionError("refused"))

        result = _run(qc.create_backtest(24654779, "abc-123"))
        assert result["success"] is False
        assert "refused" in result["error"]


# ===========================================================================
# read_backtest
# ===========================================================================
class TestReadBacktest:
    def test_completed_with_metrics(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "backtest": {
                "backtestId": "bt-001",
                "name": "Test BT",
                "completed": True,
                "status": "Completed.",
                "progress": 1.0,
                "error": "",
                "stacktrace": "",
                "hasInitializeError": False,
                "statistics": {
                    "Sharpe Ratio": "1.23",
                    "Sortino Ratio": "1.56",
                    "Compounding Annual Return": "15.2%",
                    "Drawdown": "8.5%",
                    "Net Profit": "15.2%",
                    "Win Rate": "60%",
                    "Loss Rate": "40%",
                    "Expectancy": "0.456",
                    "Total Orders": "42",
                    "Profit-Loss Ratio": "1.67",
                    "Alpha": "0.05",
                    "Beta": "0.8",
                },
                "runtimeStatistics": {
                    "Equity": "$115,234.00",
                    "Return": "15.23%",
                },
                "totalPerformance": {
                    "portfolioStatistics": {"sharpeRatio": "1.23"},
                    "tradeStatistics": {"totalNumberOfTrades": 42},
                },
            },
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_backtest(24654779, "bt-001"))
        assert result["success"] is True
        assert result["completed"] is True
        assert result["metrics"]["sharpe_ratio"] == "1.23"
        assert result["metrics"]["win_rate"] == "60%"
        assert result["metrics"]["drawdown"] == "8.5%"
        assert result["metrics"]["expectancy"] == "0.456"
        assert result["metrics"]["total_orders"] == "42"
        assert result["portfolio_statistics"]["sharpeRatio"] == "1.23"
        assert result["trade_statistics"]["totalNumberOfTrades"] == 42

    def test_in_progress(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "backtest": {
                "backtestId": "bt-001",
                "name": "Running",
                "completed": False,
                "status": "In Progress...",
                "progress": 0.45,
                "error": "",
                "stacktrace": "",
                "hasInitializeError": False,
                "statistics": {},
                "runtimeStatistics": {},
                "totalPerformance": {},
            },
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_backtest(24654779, "bt-001"))
        assert result["completed"] is False
        assert result["progress"] == 0.45
        assert result["metrics"]["sharpe_ratio"] == ""

    def test_runtime_error(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "backtest": {
                "backtestId": "bt-001",
                "name": "Failed",
                "completed": True,
                "status": "Runtime Error",
                "progress": 0.1,
                "error": "NullReferenceException",
                "stacktrace": "at Main.Initialize()",
                "hasInitializeError": True,
                "statistics": {},
                "runtimeStatistics": {},
                "totalPerformance": {},
            },
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.read_backtest(24654779, "bt-001"))
        assert result["completed"] is True
        assert result["error"] == "NullReferenceException"
        assert result["has_initialize_error"] is True


# ===========================================================================
# list_backtests
# ===========================================================================
class TestListBacktests:
    def test_returns_list(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {
            "success": True,
            "count": 2,
            "backtests": [
                {"backtestId": "bt-001", "name": "First", "sharpeRatio": 1.2},
                {"backtestId": "bt-002", "name": "Second", "sharpeRatio": 0.8},
            ],
            "errors": [],
        }
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.list_backtests(24654779))
        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["backtests"]) == 2
        assert result["backtests"][0]["backtestId"] == "bt-001"

    def test_empty_project(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        payload = {"success": True, "count": 0, "backtests": [], "errors": []}
        session = AsyncMock()
        session.post = MagicMock(return_value=_mock_response(payload))
        qc._get_session = AsyncMock(return_value=session)

        result = _run(qc.list_backtests(25550271))
        assert result["success"] is True
        assert result["count"] == 0
        assert result["backtests"] == []

    def test_network_error(self, monkeypatch):
        qc = _make_connector(monkeypatch)
        qc._get_session = AsyncMock(side_effect=TimeoutError("request timeout"))

        result = _run(qc.list_backtests(24654779))
        assert result["success"] is False
        assert "timeout" in result["error"]
