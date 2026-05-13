"""
P5-01: Platform Dashboard API endpoint tests.

Tests that the 6 new /trading/platforms/* endpoints are registered,
delegate to PlatformDashboardAPI methods, and return expected structures.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_dashboard():
    """Return a mock PlatformDashboardAPI with realistic return values."""
    mock = MagicMock()

    mock.get_all_platforms_summary.return_value = {
        "generated_utc": datetime.now().isoformat(),
        "platforms": {
            "pocket_option": {"platform": "pocket_option", "u_score": {"current": 0.12}},
            "ibkr": {"platform": "ibkr", "u_score": {"current": -0.03}},
            "internal_paper": {"platform": "internal_paper", "u_score": {"current": 0.0}},
        },
        "comparison": {},
        "recommendations": [],
    }

    mock.get_platform_summary.return_value = {
        "platform": "pocket_option",
        "timestamp": datetime.now().isoformat(),
        "u_score": {"current": 0.12, "verdict": "needs_improvement"},
        "metrics": {"total_trades": 5, "win_rate": 60.0, "last_trade_time": "2026-03-27T17:26:42Z"},
        "accumulator": {"running": False, "last_trade": "2026-03-27T11:20:11.859109"},
        "execution": {"last_trade_time": "2026-03-27T17:26:42Z", "last_browser_command_utc": "2026-03-27T17:26:42Z"},
        "status": "active",
    }

    mock.get_platform_u_history.return_value = [
        {"timestamp": "2026-03-20T12:00:00", "u_score": 0.05, "reason": "trade"},
        {"timestamp": "2026-03-21T12:00:00", "u_score": 0.12, "reason": "trade"},
    ]

    mock.get_platform_trade_history.return_value = [
        {"trade_id": "t1", "outcome": "win", "profit": 0.85},
    ]

    mock.compare_platforms.return_value = {
        "generated_utc": datetime.now().isoformat(),
        "ranking": [
            {"rank": 1, "platform": "pocket_option", "u_score": 0.12},
            {"rank": 2, "platform": "ibkr", "u_score": -0.03},
        ],
        "best_performer": "pocket_option",
        "worst_performer": "ibkr",
        "summary": {"total_platforms": 3, "active_platforms": 1, "average_u": 0.03},
    }

    mock.get_platform_signals_analysis.return_value = {
        "platform": "pocket_option",
        "total_signals": 3,
        "valid_signals": 2,
        "execution_ready": 1,
        "avg_confidence": 0.55,
        "problems": [],
        "recommendations": [],
    }

    return mock


@pytest.fixture()
def mock_dashboard():
    """Patch the _dashboard singleton in router so endpoints use our mock."""
    mock = _make_mock_dashboard()
    with patch("brain_v9.trading.router._dashboard", mock), \
         patch("brain_v9.trading.router.get_platform_dashboard_api", return_value=mock):
        yield mock


# ---------------------------------------------------------------------------
# Route registration tests
# ---------------------------------------------------------------------------

class TestRouteRegistration:
    """Verify the 6 new endpoints are on the trading router."""

    def _paths(self):
        from brain_v9.trading.router import router
        return [r.path for r in router.routes]

    def test_router_has_platforms_summary(self):
        assert "/trading/platforms/summary" in self._paths()

    def test_router_has_platform_name_summary(self):
        assert "/trading/platforms/{platform_name}/summary" in self._paths()

    def test_router_has_u_history(self):
        assert "/trading/platforms/{platform_name}/u-history" in self._paths()

    def test_router_has_trades(self):
        assert "/trading/platforms/{platform_name}/trades" in self._paths()

    def test_router_has_compare(self):
        assert "/trading/platforms/compare" in self._paths()

    def test_router_has_signals(self):
        assert "/trading/platforms/{platform_name}/signals" in self._paths()

    def test_all_six_platform_routes_present(self):
        paths = self._paths()
        expected = [
            "/trading/platforms/summary",
            "/trading/platforms/{platform_name}/summary",
            "/trading/platforms/{platform_name}/u-history",
            "/trading/platforms/{platform_name}/trades",
            "/trading/platforms/compare",
            "/trading/platforms/{platform_name}/signals",
        ]
        for ep in expected:
            assert ep in paths, f"Missing route: {ep}"


# ---------------------------------------------------------------------------
# Endpoint delegation tests
# ---------------------------------------------------------------------------

class TestPlatformsSummary:
    @pytest.mark.asyncio
    async def test_returns_all_platforms(self, mock_dashboard):
        from brain_v9.trading.router import platforms_summary
        result = await platforms_summary()
        assert "platforms" in result
        assert "pocket_option" in result["platforms"]
        assert "ibkr" in result["platforms"]
        mock_dashboard.get_all_platforms_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_has_recommendations_key(self, mock_dashboard):
        from brain_v9.trading.router import platforms_summary
        result = await platforms_summary()
        assert "recommendations" in result


class TestSinglePlatformSummary:
    @pytest.mark.asyncio
    async def test_returns_platform_data(self, mock_dashboard):
        from brain_v9.trading.router import platform_summary
        result = await platform_summary("pocket_option")
        assert result["platform"] == "pocket_option"
        mock_dashboard.get_platform_summary.assert_called_once_with("pocket_option")

    @pytest.mark.asyncio
    async def test_has_u_score_key(self, mock_dashboard):
        from brain_v9.trading.router import platform_summary
        result = await platform_summary("ibkr")
        assert "u_score" in result

    @pytest.mark.asyncio
    async def test_summary_can_expose_execution_timestamps(self, mock_dashboard):
        from brain_v9.trading.router import platform_summary
        result = await platform_summary("pocket_option")
        assert result["execution"]["last_trade_time"] == "2026-03-27T17:26:42Z"


class TestUHistory:
    @pytest.mark.asyncio
    async def test_returns_list(self, mock_dashboard):
        from brain_v9.trading.router import platform_u_history
        result = await platform_u_history("pocket_option")
        assert isinstance(result, list)
        assert len(result) == 2
        mock_dashboard.get_platform_u_history.assert_called_once_with("pocket_option", 100)

    @pytest.mark.asyncio
    async def test_custom_limit(self, mock_dashboard):
        from brain_v9.trading.router import platform_u_history
        await platform_u_history("ibkr", limit=50)
        mock_dashboard.get_platform_u_history.assert_called_once_with("ibkr", 50)


class TestPlatformTrades:
    @pytest.mark.asyncio
    async def test_returns_trade_list(self, mock_dashboard):
        from brain_v9.trading.router import platform_trades
        result = await platform_trades("pocket_option")
        assert isinstance(result, list)
        assert result[0]["trade_id"] == "t1"
        mock_dashboard.get_platform_trade_history.assert_called_once_with("pocket_option", 50)

    @pytest.mark.asyncio
    async def test_custom_limit(self, mock_dashboard):
        from brain_v9.trading.router import platform_trades
        await platform_trades("pocket_option", limit=20)
        mock_dashboard.get_platform_trade_history.assert_called_once_with("pocket_option", 20)


class TestPlatformsCompare:
    @pytest.mark.asyncio
    async def test_returns_ranking(self, mock_dashboard):
        from brain_v9.trading.router import platforms_compare
        result = await platforms_compare()
        assert "ranking" in result
        assert result["best_performer"] == "pocket_option"
        mock_dashboard.compare_platforms.assert_called_once()

    @pytest.mark.asyncio
    async def test_has_summary(self, mock_dashboard):
        from brain_v9.trading.router import platforms_compare
        result = await platforms_compare()
        assert result["summary"]["total_platforms"] == 3


class TestPlatformSignals:
    @pytest.mark.asyncio
    async def test_returns_signal_analysis(self, mock_dashboard):
        from brain_v9.trading.router import platform_signals
        result = await platform_signals("pocket_option")
        assert result["total_signals"] == 3
        assert result["valid_signals"] == 2
        mock_dashboard.get_platform_signals_analysis.assert_called_once_with("pocket_option")


# ---------------------------------------------------------------------------
# Lazy init tests
# ---------------------------------------------------------------------------

class TestLazyDashboardInit:
    def test_get_dashboard_returns_instance(self):
        """_get_dashboard() creates the singleton on first call."""
        from brain_v9.trading import router as router_mod
        # Reset the global
        original = router_mod._dashboard
        try:
            router_mod._dashboard = None
            with patch.object(router_mod, "get_platform_dashboard_api") as mock_factory:
                mock_factory.return_value = MagicMock()
                result = router_mod._get_dashboard()
                mock_factory.assert_called_once()
                assert result is mock_factory.return_value
        finally:
            router_mod._dashboard = original

    def test_get_dashboard_reuses_singleton(self):
        """Second call returns same instance without calling factory."""
        from brain_v9.trading import router as router_mod
        original = router_mod._dashboard
        try:
            sentinel = MagicMock()
            router_mod._dashboard = sentinel
            with patch.object(router_mod, "get_platform_dashboard_api") as mock_factory:
                result = router_mod._get_dashboard()
                mock_factory.assert_not_called()
                assert result is sentinel
        finally:
            router_mod._dashboard = original


# ---------------------------------------------------------------------------
# Unit tests for get_platform_trade_history (reads from real ledger)
# ---------------------------------------------------------------------------

class TestGetPlatformTradeHistoryUnit:
    """Test the actual get_platform_trade_history logic against the real ledger."""

    def _make_api(self):
        """Create PlatformDashboardAPI with mocked manager/accumulator."""
        with patch("brain_v9.trading.platform_dashboard_api.get_platform_manager"), \
             patch("brain_v9.trading.platform_dashboard_api.get_multi_platform_accumulator"):
            from brain_v9.trading.platform_dashboard_api import PlatformDashboardAPI
            return PlatformDashboardAPI()

    def _write_ledger(self, tmp_path, entries):
        import json
        ledger_dir = tmp_path / "tmp_agent" / "state" / "strategy_engine"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_file = ledger_dir / "signal_paper_execution_ledger.json"
        ledger_file.write_text(json.dumps({
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": entries,
        }))
        return ledger_file

    def test_returns_trades_for_pocket_option(self, tmp_path):
        entries = [
            {"venue": "pocket_option", "symbol": "AUDNZD_otc", "profit": -10.0, "resolved": True},
            {"venue": "ibkr", "symbol": "SPY", "profit": -10.0, "resolved": True},
            {"venue": "pocket_option", "symbol": "EURUSD_otc", "profit": 7.1, "resolved": True},
        ]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("pocket_option")
        assert len(result) == 2
        # Most recent first
        assert result[0]["symbol"] == "EURUSD_otc"
        assert result[1]["symbol"] == "AUDNZD_otc"
        assert result[0]["execution_type"] == "paper_shadow_only"

    def test_returns_trades_for_ibkr(self, tmp_path):
        entries = [
            {"venue": "pocket_option", "symbol": "X", "profit": 0},
            {"venue": "ibkr", "symbol": "SPY", "profit": -10.0},
            {"venue": "ibkr", "symbol": "QQQ", "profit": 5.0},
        ]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("ibkr")
        assert len(result) == 2
        assert result[0]["symbol"] == "QQQ"
        assert result[0]["execution_type"] == "unknown"

    def test_internal_paper_maps_to_internal_venue(self, tmp_path):
        entries = [
            {"venue": "internal", "symbol": "TEST", "profit": 1.0},
        ]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("internal_paper")
        assert len(result) == 1
        assert result[0]["venue"] == "internal"

    def test_respects_limit(self, tmp_path):
        entries = [{"venue": "ibkr", "symbol": f"SYM{i}", "profit": 0} for i in range(10)]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("ibkr", limit=3)
        assert len(result) == 3
        # Most recent (last in ledger) should be first in result
        assert result[0]["symbol"] == "SYM9"

    def test_returns_empty_when_no_ledger(self, tmp_path):
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("pocket_option")
        assert result == []

    def test_returns_empty_for_unknown_platform(self, tmp_path):
        entries = [{"venue": "pocket_option", "symbol": "X", "profit": 0}]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("unknown_platform")
        assert result == []

    def test_marks_click_only_vs_ui_confirmed_for_pocket_option(self, tmp_path):
        entries = [
            {
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "profit": 0.0,
                "browser_command_dispatched": True,
                "browser_order": {"click_submitted": True, "ui_trade_confirmed": False},
            },
            {
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "profit": 0.0,
                "browser_command_dispatched": True,
                "browser_trade_confirmed": True,
                "browser_order": {"click_submitted": True, "ui_trade_confirmed": True},
            },
        ]
        self._write_ledger(tmp_path, entries)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path):
            result = api.get_platform_trade_history("pocket_option", limit=2)
        assert result[0]["execution_type"] == "browser_ui_confirmed"
        assert result[1]["execution_type"] == "browser_click_unverified"


class TestComparePlatformsUnit:
    def _make_api(self):
        with patch("brain_v9.trading.platform_dashboard_api.get_platform_manager"), \
             patch("brain_v9.trading.platform_dashboard_api.get_multi_platform_accumulator"):
            from brain_v9.trading.platform_dashboard_api import PlatformDashboardAPI
            return PlatformDashboardAPI()

    def test_best_performer_uses_performance_not_only_active_status(self):
        api = self._make_api()
        fake = {
            "pocket_option": {
                "status": "active",
                "u_score": {"current": -2.99},
                "metrics": {"total_profit": -200.0, "win_rate": 3.0, "total_trades": 20},
                "ready_signals": 0,
            },
            "ibkr": {
                "status": "degraded",
                "u_score": {"current": -2.50},
                "metrics": {"total_profit": -100.0, "win_rate": 20.0, "total_trades": 20},
                "ready_signals": 0,
            },
            "internal_paper": {
                "status": "idle",
                "u_score": {"current": 0.0},
                "metrics": {"total_profit": 0.0, "win_rate": 0.0, "total_trades": 0},
                "ready_signals": 0,
            },
        }
        with patch.object(api, "get_platform_summary", side_effect=lambda platform: fake[platform]):
            result = api.compare_platforms()
        assert result["best_performer"] == "ibkr"

    def test_compare_preserves_na_u_and_does_not_rank_it_as_zero(self):
        api = self._make_api()
        fake = {
            "pocket_option": {
                "status": "active",
                "u_score": {"current": -4.6332, "display_basis": "lifetime_performance", "verdict": "no_promote"},
                "metrics": {"total_profit": 0.0, "win_rate": 0.0, "total_trades": 0},
                "ready_signals": 0,
            },
            "ibkr": {
                "status": "active",
                "u_score": {"current": None, "display_basis": "live_positions_no_resolved_sample", "verdict": "monitoring_live_positions"},
                "metrics": {"total_profit": 0.0, "win_rate": 0.0, "total_trades": 0},
                "ready_signals": 2,
            },
            "internal_paper": {
                "status": "idle",
                "u_score": {"current": None, "display_basis": "inactive", "verdict": "inactive"},
                "metrics": {"total_profit": 0.0, "win_rate": 0.0, "total_trades": 0},
                "ready_signals": 0,
            },
        }
        with patch.object(api, "get_platform_summary", side_effect=lambda platform: fake[platform]):
            result = api.compare_platforms()
        assert result["ranking"][0]["platform"] == "pocket_option"
        assert result["ranking"][1]["platform"] == "ibkr"
        assert result["ranking"][1]["u_score"] is None
        assert result["ranking"][1]["u_basis"] == "live_positions_no_resolved_sample"
        assert result["summary"]["average_u"] == -4.6332

    def test_compare_uses_reference_metrics_not_short_resolved_sample_when_basis_is_lifetime(self):
        api = self._make_api()
        fake = {
            "pocket_option": {
                "status": "active",
                "u_score": {"current": -4.6332, "display_basis": "lifetime_performance", "verdict": "no_promote"},
                "metrics": {
                    "total_profit": -20.8,
                    "win_rate": 25.0,
                    "total_trades": 4,
                    "reference_total_profit": -1666.29,
                    "reference_win_rate": 49.31,
                    "reference_total_trades": 730,
                    "reference_basis": "lifetime_performance",
                },
                "ready_signals": 0,
            },
            "ibkr": {
                "status": "active",
                "u_score": {"current": None, "display_basis": "live_positions_no_resolved_sample", "verdict": "monitoring_live_positions"},
                "metrics": {
                    "total_profit": 0.0,
                    "win_rate": 0.0,
                    "total_trades": 0,
                    "reference_total_profit": None,
                    "reference_win_rate": None,
                    "reference_total_trades": None,
                    "reference_basis": "live_positions_no_resolved_sample",
                },
                "ready_signals": 2,
            },
            "internal_paper": {
                "status": "idle",
                "u_score": {"current": None, "display_basis": "inactive", "verdict": "inactive"},
                "metrics": {
                    "total_profit": 0.0,
                    "win_rate": 0.0,
                    "total_trades": 0,
                    "reference_total_profit": None,
                    "reference_win_rate": None,
                    "reference_total_trades": None,
                    "reference_basis": "inactive",
                },
                "ready_signals": 0,
            },
        }
        with patch.object(api, "get_platform_summary", side_effect=lambda platform: fake[platform]):
            result = api.compare_platforms()
        assert result["ranking"][0]["platform"] == "pocket_option"
        assert result["ranking"][0]["win_rate"] == 49.31
        assert result["ranking"][0]["profit"] == -1666.29
        assert result["ranking"][0]["trades"] == 730
        assert result["ranking"][0]["metrics_basis"] == "lifetime_performance"


class TestPlatformSummaryCanonicalStateUnit:
    def _make_api(self):
        with patch("brain_v9.trading.platform_dashboard_api.get_platform_manager"), \
             patch("brain_v9.trading.platform_dashboard_api.get_multi_platform_accumulator"):
            from brain_v9.trading.platform_dashboard_api import PlatformDashboardAPI
            return PlatformDashboardAPI()

    def _write_strategy_engine_state(self, tmp_path):
        import json
        engine_dir = tmp_path / "tmp_agent" / "state" / "strategy_engine"
        engine_dir.mkdir(parents=True, exist_ok=True)
        (engine_dir / "signal_paper_execution_ledger.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
        (engine_dir / "strategy_scorecards.json").write_text(json.dumps({"scorecards": {}}), encoding="utf-8")
        (engine_dir / "strategy_signal_snapshot_latest.json").write_text(json.dumps({"items": []}), encoding="utf-8")
        (engine_dir / "market_feature_snapshot_latest.json").write_text(json.dumps({"items": []}), encoding="utf-8")
        (engine_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps({"ranked": []}), encoding="utf-8")

    def _write_platform_state(self, tmp_path, platform_name, u_proxy=-0.05, total_trades=0, **metric_overrides):
        import json
        pdir = tmp_path / "tmp_agent" / "state" / "platforms"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / f"{platform_name}_u.json").write_text(json.dumps({
            "platform": platform_name,
            "u_proxy": u_proxy,
            "verdict": "no_promote",
            "blockers": ["u_proxy_non_positive", "needs_samples"],
            "trend_24h": "stable",
            "history": [{"timestamp": "2026-04-01T23:00:00", "u_score": u_proxy, "reason": "Skip: No valid signals"}],
        }), encoding="utf-8")
        metrics_payload = {
            "platform": platform_name,
            "total_trades": total_trades,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_profit": 0.0,
            "peak_profit": 0.0,
            "largest_loss_streak": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "sample_quality": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "last_trade_time": None,
        }
        metrics_payload.update(metric_overrides)
        (pdir / f"{platform_name}_metrics.json").write_text(json.dumps(metrics_payload), encoding="utf-8")

    def test_platform_summary_uses_platform_u_state_not_zero_recompute(self, tmp_path):
        self._write_strategy_engine_state(tmp_path)
        self._write_platform_state(
            tmp_path,
            "pocket_option",
            u_proxy=-0.05,
            total_trades=726,
            winning_trades=360,
            losing_trades=366,
            total_profit=-1626.292199999997,
            peak_profit=10.4,
            largest_loss_streak=19,
            win_rate=0.49586776859504134,
            expectancy=-2.240071900826442,
            sample_quality=1.0,
            max_drawdown=1636.692199999997,
        )
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path), \
             patch.object(api, "_platform_accumulator", return_value={}), \
             patch.object(api, "_platform_status", return_value={"status": "active", "detail": "demo_bridge_live", "data_age_seconds": 1.0, "ready_signals": 0, "validated_ready_signals": 0, "probation_ready_signals": 0}):
            result = api.get_platform_summary("pocket_option")
        assert result["u_score"]["current"] == -4.6332
        assert result["u_score"]["verdict"] == "no_promote"
        assert result["u_score"]["display_basis"] == "lifetime_performance"
        assert result["u_score"]["runtime_current"] == -0.05
        assert result["u_score"]["performance_current"] == -4.6332
        assert result["metrics"]["total_trades"] == 0
        assert result["metrics"]["lifetime_total_trades"] == 726
        assert result["metrics"]["reference_basis"] == "lifetime_performance"
        assert result["metrics"]["reference_total_trades"] == 726
        assert result["metrics"]["reference_win_rate"] == 49.59
        assert result["metrics"]["reference_total_profit"] == -1626.2922

    def test_ibkr_summary_surfaces_live_positions_even_if_probe_file_is_disconnected(self, tmp_path):
        import json
        self._write_strategy_engine_state(tmp_path)
        self._write_platform_state(tmp_path, "ibkr", u_proxy=-0.05, total_trades=0)
        probe_path = tmp_path / "ibkr_marketdata_probe_status.json"
        probe_path.write_text(json.dumps({
            "connected": False,
            "managed_accounts": "",
            "checked_utc": "2026-04-02T03:00:00Z",
        }), encoding="utf-8")
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path), \
             patch("brain_v9.trading.platform_dashboard_api.IBKR_PROBE_ARTIFACT", probe_path), \
             patch.object(api, "_platform_accumulator", return_value={}), \
             patch.object(api, "_read_ibkr_live_snapshot", return_value={
                 "connected": True,
                 "managed_accounts": ["DUM891854"],
                 "positions_count": 4,
                 "open_trades_count": 0,
                 "checked_utc": "2026-04-02T03:10:00Z",
                 "error": None,
             }):
            result = api.get_platform_summary("ibkr")
        assert result["status"] == "active"
        assert result["execution"]["live_positions_count"] == 4
        assert result["execution"]["managed_accounts"] == ["DUM891854"]
        assert result["u_score"]["current"] is None
        assert result["u_score"]["display_basis"] == "live_positions_no_resolved_sample"
        assert result["u_score"]["verdict"] == "monitoring_live_positions"
        assert result["u_score"]["runtime_current"] == -0.05

    def test_internal_paper_unused_returns_inactive_u(self, tmp_path):
        self._write_strategy_engine_state(tmp_path)
        self._write_platform_state(tmp_path, "internal_paper", u_proxy=-0.05, total_trades=0)
        api = self._make_api()
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path), \
             patch.object(api, "_platform_accumulator", return_value={}), \
             patch.object(api, "_platform_status", return_value={"status": "idle", "detail": "no_live_connector", "data_age_seconds": None, "ready_signals": 0, "validated_ready_signals": 0, "probation_ready_signals": 0}):
            result = api.get_platform_summary("internal_paper")
            history = api.get_platform_u_history("internal_paper")
        assert result["u_score"]["current"] is None
        assert result["u_score"]["verdict"] == "inactive"
        assert history == []

    def test_ibkr_trade_history_falls_back_to_live_positions_when_ledger_empty(self, tmp_path):
        import json
        self._write_strategy_engine_state(tmp_path)
        self._write_platform_state(tmp_path, "ibkr", u_proxy=-0.05, total_trades=0)
        probe_path = tmp_path / "ibkr_marketdata_probe_status.json"
        probe_path.write_text(json.dumps({"connected": True, "managed_accounts": "DUM891854", "checked_utc": "2026-04-02T03:00:00Z"}), encoding="utf-8")
        api = self._make_api()
        live_snapshot = {
            "connected": True,
            "managed_accounts": ["DUM891854"],
            "positions_count": 2,
            "open_trades_count": 0,
            "positions": [
                {"account": "DUM891854", "symbol": "SPY", "secType": "OPT", "position": 1.0, "avgCost": 100.0},
                {"account": "DUM891854", "symbol": "QQQ", "secType": "OPT", "position": -1.0, "avgCost": 120.0},
            ],
            "checked_utc": "2026-04-02T03:10:00Z",
            "error": None,
        }
        with patch("brain_v9.trading.platform_dashboard_api.BASE_PATH", tmp_path), \
             patch("brain_v9.trading.platform_dashboard_api.IBKR_PROBE_ARTIFACT", probe_path), \
             patch.object(api, "_platform_accumulator", return_value={}), \
             patch.object(api, "_read_ibkr_live_snapshot", return_value=live_snapshot):
            result = api.get_platform_trade_history("ibkr", limit=10)
        assert len(result) == 2
        assert result[0]["execution_type"] == "broker_position"
        assert result[0]["symbol"] == "SPY"
