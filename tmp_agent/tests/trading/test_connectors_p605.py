"""
P6-05 — Tests for brain_v9/trading/connectors.py
Covers: _safe_read_json, _mtime_utc, _SessionMixin, TiingoConnector,
        QuantConnectConnector, IBKRReadonlyConnector, PocketOptionBridge.
All network I/O and filesystem reads are mocked.
"""
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import _safe_read_json, _mtime_utc


class TestSafeReadJson:
    def test_reads_valid_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        assert _safe_read_json(f) == {"a": 1}

    def test_missing_file_returns_empty(self, tmp_path):
        assert _safe_read_json(tmp_path / "nope.json") == {}

    def test_corrupt_json_returns_empty(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        assert _safe_read_json(f) == {}

    def test_directory_path_returns_empty(self, tmp_path):
        assert _safe_read_json(tmp_path) == {}


class TestMtimeUtc:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hi", encoding="utf-8")
        result = _mtime_utc(f)
        assert result is not None
        assert result.endswith("Z")

    def test_missing_file_returns_none(self, tmp_path):
        assert _mtime_utc(tmp_path / "nope") is None


# ---------------------------------------------------------------------------
# _SessionMixin
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import _SessionMixin


class TestSessionMixin:
    @pytest.mark.asyncio
    async def test_get_session_creates_new(self):
        mixin = _SessionMixin()
        with patch("brain_v9.trading.connectors.ClientSession") as mock_cls:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_cls.return_value = mock_session
            s = await mixin._get_session(timeout=5)
            assert s is mock_session
            mock_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_reuses_open(self):
        mixin = _SessionMixin()
        mock_session = MagicMock()
        mock_session.closed = False
        mixin._session = mock_session
        with patch("brain_v9.trading.connectors.ClientSession") as mock_cls:
            s = await mixin._get_session()
            assert s is mock_session
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_session_replaces_closed(self):
        mixin = _SessionMixin()
        old = MagicMock()
        old.closed = True
        mixin._session = old
        with patch("brain_v9.trading.connectors.ClientSession") as mock_cls:
            new_sess = MagicMock()
            new_sess.closed = False
            mock_cls.return_value = new_sess
            s = await mixin._get_session()
            assert s is new_sess

    @pytest.mark.asyncio
    async def test_close_when_open(self):
        mixin = _SessionMixin()
        mock_session = AsyncMock()
        mock_session.closed = False
        mixin._session = mock_session
        await mixin.close()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_when_already_closed(self):
        mixin = _SessionMixin()
        mock_session = AsyncMock()
        mock_session.closed = True
        mixin._session = mock_session
        await mixin.close()
        mock_session.close.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_when_none(self):
        mixin = _SessionMixin()
        mixin._session = None
        await mixin.close()  # should not raise


# ---------------------------------------------------------------------------
# Helper: fake aiohttp response context manager
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload or {}

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


def _fake_session(responses: dict):
    """Return a mock session where .get/.post(url, ...) returns matching _FakeResponse."""
    session = MagicMock()

    def _route(method):
        def handler(url, **kw):
            for pattern, resp in responses.items():
                if pattern in url:
                    return resp
            return _FakeResponse(status=404, payload={"error": "not mocked"})
        return handler

    session.get = MagicMock(side_effect=_route("GET"))
    session.post = MagicMock(side_effect=_route("POST"))
    return session


# ---------------------------------------------------------------------------
# TiingoConnector
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import TiingoConnector


class TestTiingoConnectorInit:
    def test_explicit_token(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="my_token")
        assert tc.token == "my_token"

    def test_token_from_secrets_file(self, tmp_path):
        f = tmp_path / "tiingo.json"
        f.write_text('{"token": "file_token"}', encoding="utf-8")
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": f, "quantconnect": tmp_path / "nope.json"}):
            tc = TiingoConnector()
        assert tc.token == "file_token"

    def test_no_token_warns(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector()
        assert tc.token == ""

    def test_headers_include_token(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="abc123")
        h = tc._headers()
        assert h["Authorization"] == "Token abc123"
        assert "application/json" in h["Content-Type"]


class TestTiingoCheckHealth:
    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        sess = _fake_session({"/api/test": _FakeResponse(200, {})})
        tc._get_session = AsyncMock(return_value=sess)
        result = await tc.check_health()
        assert result["success"] is True
        assert result["mode"] == "read_only"
        assert result["current_capability"] == "daily_and_intraday_features"
        assert result["paper_trading_allowed"] is False
        assert result["live_trading_allowed"] is False

    @pytest.mark.asyncio
    async def test_auth_failure(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="bad")
        sess = _fake_session({"/api/test": _FakeResponse(401, {})})
        tc._get_session = AsyncMock(return_value=sess)
        result = await tc.check_health()
        assert result["success"] is False
        assert result["current_capability"] == "auth_failed"

    @pytest.mark.asyncio
    async def test_network_error(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        tc._get_session = AsyncMock(side_effect=Exception("timeout"))
        result = await tc.check_health()
        assert result["success"] is False
        assert "timeout" in result["error"]


class TestTiingoData:
    @pytest.mark.asyncio
    async def test_get_intraday_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        bars = [{"close": 100}]
        sess = _fake_session({"/iex/AAPL": _FakeResponse(200, bars)})
        tc._get_session = AsyncMock(return_value=sess)
        result = await tc.get_intraday_data("AAPL")
        assert result["success"] is True
        assert result["data"] == bars
        assert result["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_intraday_http_error(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        sess = _fake_session({"/iex/SPY": _FakeResponse(500, {})})
        tc._get_session = AsyncMock(return_value=sess)
        result = await tc.get_intraday_data("SPY")
        assert result["success"] is False
        assert "HTTP 500" in result["error"]

    @pytest.mark.asyncio
    async def test_get_historical_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        data = [{"date": "2026-01-01", "close": 150}]
        sess = _fake_session({"/tiingo/daily/AAPL/prices": _FakeResponse(200, data)})
        tc._get_session = AsyncMock(return_value=sess)
        result = await tc.get_historical_data("AAPL", days=10)
        assert result["success"] is True
        assert result["days"] == 10

    @pytest.mark.asyncio
    async def test_get_historical_exception(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "nope.json", "quantconnect": tmp_path / "nope2.json"}):
            tc = TiingoConnector(token="tok")
        tc._get_session = AsyncMock(side_effect=ConnectionError("refused"))
        result = await tc.get_historical_data("AAPL")
        assert result["success"] is False
        assert "refused" in result["error"]


# ---------------------------------------------------------------------------
# QuantConnectConnector
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import QuantConnectConnector


class TestQCInit:
    def test_explicit_creds(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="123", token="abc")
        assert qc.user_id == "123"
        assert qc.token == "abc"

    def test_creds_from_file(self, tmp_path):
        f = tmp_path / "qc.json"
        f.write_text('{"user_id": "U1", "token": "T1"}', encoding="utf-8")
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": f}):
            qc = QuantConnectConnector()
        assert qc.user_id == "U1"
        assert qc.token == "T1"

    def test_no_creds_warns(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector()
        assert qc.user_id == ""
        assert qc.token == ""


class TestQCHeaders:
    def test_header_structure(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="secret")
        h = qc._headers()
        assert h["Authorization"].startswith("Basic ")
        assert "Timestamp" in h
        assert h["Content-Type"] == "application/json"

    def test_auth_contains_userid(self, tmp_path):
        """Decoded basic auth should start with user_id:"""
        from base64 import b64decode
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="secret")
        h = qc._headers()
        decoded = b64decode(h["Authorization"].split(" ", 1)[1]).decode("utf-8")
        assert decoded.startswith("42:")


class TestQCCheckHealth:
    @pytest.mark.asyncio
    async def test_success_with_projects(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        sess = _fake_session({
            "/authenticate": _FakeResponse(200, {"success": True}),
            "/projects/read": _FakeResponse(200, {"projects": [{"id": 1}, {"id": 2}]}),
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.check_health()
        assert result["success"] is True
        assert result["projects_count"] == 2
        assert result["mode"] == "research_only"
        assert result["paper_trading_allowed"] is False

    @pytest.mark.asyncio
    async def test_auth_failure(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="bad")
        sess = _fake_session({
            "/authenticate": _FakeResponse(401, {"success": False}),
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.check_health()
        assert result["success"] is False
        assert result["current_capability"] == "auth_failed"

    @pytest.mark.asyncio
    async def test_exception(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        qc._get_session = AsyncMock(side_effect=Exception("network"))
        result = await qc.check_health()
        assert result["success"] is False
        assert "network" in result["error"]


class TestQCProjects:
    @pytest.mark.asyncio
    async def test_get_projects_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        projects = [{"projectId": 1, "name": "P1"}]
        sess = _fake_session({"/projects/read": _FakeResponse(200, {"projects": projects})})
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.get_projects()
        assert result["success"] is True
        assert result["projects_count"] == 1

    @pytest.mark.asyncio
    async def test_get_project_file_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        files = [{"name": "main.py", "content": "# algo"}]
        sess = _fake_session({"/files/read": _FakeResponse(200, {"files": files})})
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.get_project_file(project_id=100, name="main.py")
        assert result["success"] is True
        assert result["files_count"] == 1

    @pytest.mark.asyncio
    async def test_get_historical_data_delegates_to_projects(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        projects = [{"projectId": 1}]
        sess = _fake_session({"/projects/read": _FakeResponse(200, {"projects": projects})})
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.get_historical_data("AAPL", days=10)
        assert result["mode"] == "research_only"
        assert result["symbol"] == "AAPL"
        assert result["projects_count"] == 1


class TestQCCompileBacktest:
    @pytest.mark.asyncio
    async def test_compile_project_success(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        sess = _fake_session({
            "/compile/create": _FakeResponse(200, {"success": True, "compileId": "C1", "state": "BuildSuccess"})
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.compile_project(100)
        assert result["success"] is True
        assert result["compile_id"] == "C1"

    @pytest.mark.asyncio
    async def test_compile_project_failure(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        qc._get_session = AsyncMock(side_effect=Exception("boom"))
        result = await qc.compile_project(100)
        assert result["success"] is False
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_read_compile(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        sess = _fake_session({
            "/compile/read": _FakeResponse(200, {"success": True, "compileId": "C1", "state": "BuildSuccess"})
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.read_compile(100, "C1")
        assert result["build_success"] is True
        assert result["build_error"] is False

    @pytest.mark.asyncio
    async def test_create_backtest(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        sess = _fake_session({
            "/backtests/create": _FakeResponse(200, {
                "success": True,
                "backtest": {"backtestId": "BT1", "name": "Test", "completed": False, "status": "Running", "progress": 0.5, "error": ""}
            })
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.create_backtest(100, "C1", "Test")
        assert result["success"] is True
        assert result["backtest_id"] == "BT1"

    @pytest.mark.asyncio
    async def test_read_backtest(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        stats = {"Sharpe Ratio": "1.5", "Win Rate": "60%"}
        sess = _fake_session({
            "/backtests/read": _FakeResponse(200, {
                "success": True,
                "backtest": {
                    "backtestId": "BT1", "name": "Test", "completed": True,
                    "status": "Completed", "progress": 1, "error": "",
                    "statistics": stats,
                    "runtimeStatistics": {},
                    "totalPerformance": {"portfolioStatistics": {}, "tradeStatistics": {}},
                }
            })
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.read_backtest(100, "BT1")
        assert result["success"] is True
        assert result["completed"] is True
        assert result["metrics"]["sharpe_ratio"] == "1.5"

    @pytest.mark.asyncio
    async def test_list_backtests(self, tmp_path):
        with patch("brain_v9.trading.connectors.SECRETS", {"tiingo": tmp_path / "n.json", "quantconnect": tmp_path / "nope.json"}):
            qc = QuantConnectConnector(user_id="42", token="tok")
        sess = _fake_session({
            "/backtests/list": _FakeResponse(200, {
                "success": True, "count": 2,
                "backtests": [{"backtestId": "B1"}, {"backtestId": "B2"}]
            })
        })
        qc._get_session = AsyncMock(return_value=sess)
        result = await qc.list_backtests(100)
        assert result["success"] is True
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# IBKRReadonlyConnector
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import IBKRReadonlyConnector


def _ibkr_with_artifacts(tmp_path, lane=None, probe=None, probe_status=None, order_check=None):
    """Create an IBKRReadonlyConnector with artifact files in tmp_path."""
    connector = IBKRReadonlyConnector.__new__(IBKRReadonlyConnector)
    connector.logger = MagicMock()
    connector.host = "127.0.0.1"
    connector.port = 4002

    def _write(name, data):
        f = tmp_path / name
        f.write_text(json.dumps(data or {}), encoding="utf-8")
        return f

    connector.lane_artifact = _write("lane.json", lane)
    connector.probe_artifact = _write("probe.json", probe)
    connector.probe_status_artifact = _write("probe_status.json", probe_status)
    connector.order_check_artifact = _write("order_check.json", order_check)
    return connector


class TestIBKRHealthOrderCheckReady:
    """When order_check.order_api_ready is True, use file artifacts path."""

    @pytest.mark.asyncio
    async def test_order_api_ready_fresh(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            lane={"mode": "paper_ready"},
            probe={"connected": True, "checked_utc": now, "errors": []},
            order_check={"order_api_ready": True, "checked_utc": now},
        )
        result = await c.check_health()
        assert result["success"] is True
        assert result["order_api_ready"] is True
        assert result["paper_trading_allowed"] is True
        assert result["live_trading_allowed"] is False
        assert result["data_freshness"] == "fresh"
        assert result["status"] == "available"

    @pytest.mark.asyncio
    async def test_order_api_ready_stale(self, tmp_path):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            lane={},
            probe={"connected": True, "checked_utc": old, "errors": []},
            order_check={"order_api_ready": True, "checked_utc": old},
        )
        result = await c.check_health()
        assert result["success"] is True
        assert result["data_freshness"] == "stale"

    @pytest.mark.asyncio
    async def test_subscription_errors_block_market_data(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            probe={"connected": True, "checked_utc": now, "errors": [{"errorCode": 10089}]},
            order_check={"order_api_ready": True, "checked_utc": now},
        )
        result = await c.check_health()
        assert result["market_data_api_ready"] is False
        assert result["order_api_ready"] is True


class TestIBKRHealthSocketFallback:
    """When order_check is not ready, falls through to socket path."""

    @pytest.mark.asyncio
    async def test_no_artifacts_socket_closed(self, tmp_path):
        """No file artifacts, socket connection fails."""
        c = _ibkr_with_artifacts(tmp_path)
        with patch("brain_v9.trading.connectors.socket") as mock_socket:
            sock_inst = MagicMock()
            sock_inst.connect_ex.return_value = 111  # refused
            mock_socket.socket.return_value = sock_inst
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            result = await c.check_health()
        assert result["success"] is True
        assert result["port_open"] is False
        assert result["status"] == "port_closed"

    @pytest.mark.asyncio
    async def test_socket_open_no_order_api(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            probe={"connected": True, "checked_utc": now, "errors": []},
            order_check={"order_api_ready": False},
        )
        with patch("brain_v9.trading.connectors.socket") as mock_socket:
            sock_inst = MagicMock()
            sock_inst.connect_ex.return_value = 0  # open
            mock_socket.socket.return_value = sock_inst
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            result = await c.check_health()
        assert result["success"] is True
        assert result["port_open"] is True
        assert result["market_data_api_ready"] is True
        assert result["order_api_ready"] is False

    @pytest.mark.asyncio
    async def test_socket_exception_with_probe_fallback(self, tmp_path):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            probe={"connected": True, "checked_utc": now, "errors": []},
            order_check={"order_api_ready": False},
        )
        with patch("brain_v9.trading.connectors.socket") as mock_socket:
            mock_socket.socket.return_value.settimeout.side_effect = Exception("socket error")
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            result = await c.check_health()
        assert result["success"] is True
        assert result["data_source"] == "file_artifacts_fallback"

    @pytest.mark.asyncio
    async def test_socket_exception_no_probe_returns_failure(self, tmp_path):
        c = _ibkr_with_artifacts(tmp_path)
        with patch("brain_v9.trading.connectors.socket") as mock_socket:
            mock_socket.socket.return_value.settimeout.side_effect = Exception("socket error")
            mock_socket.AF_INET = 2
            mock_socket.SOCK_STREAM = 1
            result = await c.check_health()
        assert result["success"] is False
        assert "socket error" in result["error"]

    @pytest.mark.asyncio
    async def test_port_closed_with_order_check_fallback(self, tmp_path):
        """Port closed but order_check.order_api_ready => file_artifacts_port_closed."""
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        c = _ibkr_with_artifacts(
            tmp_path,
            probe={"connected": True, "checked_utc": now, "errors": []},
            order_check={"order_api_ready": True, "checked_utc": now},
        )
        # Because order_check.order_api_ready is True, it goes through the
        # first branch, not the socket fallback. Verify that path.
        result = await c.check_health()
        assert result["success"] is True
        assert "file_artifacts" in result["data_source"]


class TestIBKRInit:
    def test_explicit_host_port(self):
        c = IBKRReadonlyConnector(host="1.2.3.4", port=9999)
        assert c.host == "1.2.3.4"
        assert c.port == 9999

    def test_default_host_port_matches_config(self):
        """Defaults come from config constants bound at class definition."""
        from brain_v9.config import IBKR_HOST, IBKR_PORT
        c = IBKRReadonlyConnector()
        assert c.host == IBKR_HOST
        assert c.port == IBKR_PORT


# ---------------------------------------------------------------------------
# PocketOptionBridge
# ---------------------------------------------------------------------------
from brain_v9.trading.connectors import PocketOptionBridge


def _po_with_artifacts(tmp_path, bridge=None, feed=None, dd=None, cmd_result=None, bridge_url="http://fake:8765"):
    """Create PocketOptionBridge with artifact files in tmp_path."""
    connector = PocketOptionBridge.__new__(PocketOptionBridge)
    connector.logger = MagicMock()
    connector.bridge_url = bridge_url

    def _write(name, data):
        f = tmp_path / name
        f.write_text(json.dumps(data or {}), encoding="utf-8")
        return f

    connector.browser_bridge_artifact = _write("bridge.json", bridge)
    connector.browser_feed_artifact = _write("feed.json", feed)
    connector.due_diligence_artifact = _write("dd.json", dd)
    connector.last_command_result_artifact = _write("cmd.json", cmd_result)
    return connector


class TestPOHealthFileBased:
    """When browser_bridge has current.symbol, uses file-based path."""

    @pytest.mark.asyncio
    async def test_success_with_command(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={
                "current": {"symbol": "EURUSD", "price": 1.08},
                "dom": {"payout_pct": 92, "expiry_seconds": 60},
                "ws": {},
            },
            cmd_result={"result": {"success": True, "accepted_click": True, "ui_trade_confirmed": True, "evidence": {}}},
            dd={"brain_decision": {"venue_classification": "demo_only"}},
        )
        result = await c.check_health()
        assert result["success"] is True
        assert result["provider"] == "pocket_option"
        assert result["data_source"] == "browser_bridge_files"
        assert result["current_symbol"] == "EURUSD"
        assert result["demo_order_api_ready"] is True
        assert result["paper_trading_allowed"] is True
        assert result["live_trading_allowed"] is False

    @pytest.mark.asyncio
    async def test_manual_test_blocks(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={"current": {"symbol": "X"}, "dom": {}, "ws": {}},
            cmd_result={"result": {"success": True, "evidence": {"manual_test": True}}},
        )
        result = await c.check_health()
        assert result["demo_order_api_ready"] is False
        assert result["demo_order_api_blocking_reason"] == "browser_extension_not_reloaded_or_not_polling"

    @pytest.mark.asyncio
    async def test_top_up_button_blocks(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={"current": {"symbol": "X"}, "dom": {}, "ws": {}},
            cmd_result={"result": {"success": True, "evidence": {"button_text": "Top Up"}}},
        )
        result = await c.check_health()
        assert result["demo_order_api_ready"] is False
        assert result["demo_order_api_blocking_reason"] == "invalid_button_detected_top_up"

    @pytest.mark.asyncio
    async def test_no_command_success_blocks(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={"current": {"symbol": "X"}, "dom": {}, "ws": {}},
            cmd_result={"result": {"success": False, "evidence": {}}},
        )
        result = await c.check_health()
        assert result["demo_order_api_ready"] is False


class TestPOHealthHTTPFallback:
    """When no bridge data, falls through to HTTP bridge."""

    @pytest.mark.asyncio
    async def test_http_success(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={},  # no current.symbol => triggers HTTP
            cmd_result={"result": {"success": True, "evidence": {}}},
        )
        sess = _fake_session({
            "/health": _FakeResponse(200, {"status": "available", "connected": True})
        })
        c._get_session = AsyncMock(return_value=sess)
        result = await c.check_health()
        assert result["success"] is True
        assert result["data_source"] == "http_bridge"

    @pytest.mark.asyncio
    async def test_http_exception(self, tmp_path):
        c = _po_with_artifacts(
            tmp_path,
            bridge={},
            cmd_result={},
        )
        c._get_session = AsyncMock(side_effect=Exception("refused"))
        result = await c.check_health()
        assert result["success"] is False
        assert result["status"] == "disconnected"
        assert result["data_source"] == "none"
        assert result["demo_order_api_ready"] is False


class TestPOBridgeActions:
    @pytest.mark.asyncio
    async def test_get_balance(self, tmp_path):
        c = _po_with_artifacts(tmp_path)
        sess = _fake_session({"/balance": _FakeResponse(200, {"balance": 10000, "currency": "USD"})})
        c._get_session = AsyncMock(return_value=sess)
        result = await c.get_balance()
        assert result["success"] is True
        assert result["balance"] == 10000

    @pytest.mark.asyncio
    async def test_get_balance_error(self, tmp_path):
        c = _po_with_artifacts(tmp_path)
        c._get_session = AsyncMock(side_effect=Exception("fail"))
        result = await c.get_balance()
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_trade_history(self, tmp_path):
        c = _po_with_artifacts(tmp_path)
        trades = [{"id": 1}, {"id": 2}]
        sess = _fake_session({"/trades/history": _FakeResponse(200, {"trades": trades})})
        c._get_session = AsyncMock(return_value=sess)
        result = await c.get_trade_history(limit=50)
        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_get_open_trades(self, tmp_path):
        c = _po_with_artifacts(tmp_path)
        sess = _fake_session({"/trades/open": _FakeResponse(200, {"trades": [{"id": 1}], "count": 1})})
        c._get_session = AsyncMock(return_value=sess)
        result = await c.get_open_trades()
        assert result["success"] is True
        assert result["count"] == 1


class TestPOPlaceTrade:
    @pytest.mark.asyncio
    async def test_place_trade_immediate_complete(self, tmp_path):
        """Command queued, then immediately completed on first poll."""
        c = _po_with_artifacts(tmp_path)

        call_count = 0

        def _route_get(url, **kw):
            if "/commands/status/" in url:
                    return _FakeResponse(200, {
                    "command": {"status": "completed", "result": {"success": True, "reason": "ok", "accepted_click": True, "ui_trade_confirmed": True}}
                })
            return _FakeResponse(404, {})

        def _route_post(url, **kw):
            if "/trade" in url:
                return _FakeResponse(200, {"success": True, "command_id": "CMD1"})
            return _FakeResponse(404, {})

        sess = MagicMock()
        sess.get = MagicMock(side_effect=_route_get)
        sess.post = MagicMock(side_effect=_route_post)
        c._get_session = AsyncMock(return_value=sess)

        with patch("brain_v9.trading.connectors.asyncio.sleep", new_callable=AsyncMock):
            result = await c.place_trade("EURUSD", "call", 1.0, 60)

        assert result["success"] is True
        assert result["trade_id"] == "CMD1"
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_place_trade_failed_on_queue(self, tmp_path):
        c = _po_with_artifacts(tmp_path)

        def _route_post(url, **kw):
            if "/trade" in url:
                return _FakeResponse(200, {"success": False, "reason": "not_ready"})
            return _FakeResponse(404, {})

        sess = MagicMock()
        sess.post = MagicMock(side_effect=_route_post)
        c._get_session = AsyncMock(return_value=sess)
        result = await c.place_trade("EURUSD", "call", 1.0, 60)
        assert result["success"] is False
        assert result["reason"] == "not_ready"

    @pytest.mark.asyncio
    async def test_place_trade_exception(self, tmp_path):
        c = _po_with_artifacts(tmp_path)
        c._get_session = AsyncMock(side_effect=Exception("down"))
        result = await c.place_trade("X", "call", 1.0, 60)
        assert result["success"] is False
        assert "down" in result["error"]

    @pytest.mark.asyncio
    async def test_place_trade_command_failed(self, tmp_path):
        c = _po_with_artifacts(tmp_path)

        def _route_get(url, **kw):
            if "/commands/status/" in url:
                return _FakeResponse(200, {
                    "command": {"status": "failed", "result": {"success": False, "reason": "button_not_found"}}
                })
            return _FakeResponse(404, {})

        def _route_post(url, **kw):
            if "/trade" in url:
                return _FakeResponse(200, {"success": True, "command_id": "CMD2"})
            return _FakeResponse(404, {})

        sess = MagicMock()
        sess.get = MagicMock(side_effect=_route_get)
        sess.post = MagicMock(side_effect=_route_post)
        c._get_session = AsyncMock(return_value=sess)

        with patch("brain_v9.trading.connectors.asyncio.sleep", new_callable=AsyncMock):
            result = await c.place_trade("EURUSD", "put", 1.0, 60)

        assert result["success"] is False
        assert result["status"] == "failed"


class TestPOInit:
    def test_explicit_bridge_url(self):
        c = PocketOptionBridge(bridge_url="http://test:1234")
        assert c.bridge_url == "http://test:1234"

    def test_default_bridge_url_matches_config(self):
        """Default comes from config constant bound at class definition."""
        from brain_v9.config import POCKETOPTION_BRIDGE_URL
        c = PocketOptionBridge()
        assert c.bridge_url == POCKETOPTION_BRIDGE_URL
