"""
P5-02: Platform accumulator _update_scorecard() actually updates scorecards.

Tests that the previously-stubbed method now calls update_strategy_scorecard
with the correct trade dict shape.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


@pytest.fixture()
def accumulator(tmp_path, monkeypatch):
    """Create a PlatformSampleAccumulator for pocket_option with isolated state."""
    import brain_v9.config as _cfg
    monkeypatch.setattr(_cfg, "BASE_PATH", tmp_path)
    # Ensure state directory exists
    (tmp_path / "tmp_agent" / "state" / "platform_accumulators").mkdir(parents=True, exist_ok=True)

    from brain_v9.autonomy.platform_accumulators import PlatformSampleAccumulator, Platform
    acc = PlatformSampleAccumulator(Platform.POCKET_OPTION)
    return acc


class TestUpdateScorecardCallsReal:
    """Verify _update_scorecard delegates to strategy_scorecard.update_strategy_scorecard."""

    @pytest.mark.asyncio
    async def test_calls_update_strategy_scorecard(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("strat_a", "EURUSD", "call", "win", 0.85)
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_strategy_dict(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("strat_x", "GBPJPY", "put", "loss", -1.0)
        call_args = mock_update.call_args
        assert call_args.kwargs["strategy"] == {"strategy_id": "strat_x", "venue": "pocket_option"}

    @pytest.mark.asyncio
    async def test_trade_dict_has_required_keys(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("strat_b", "AUDNZD_otc", "call", "win", 0.80)
        trade = mock_update.call_args.kwargs["trade"]
        required = {"strategy_id", "symbol", "direction", "venue", "result", "profit", "timestamp", "resolved"}
        assert required.issubset(trade.keys())

    @pytest.mark.asyncio
    async def test_trade_resolved_true_for_win(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "SPY", "call", "win", 1.0)
        trade = mock_update.call_args.kwargs["trade"]
        assert trade["resolved"] is True

    @pytest.mark.asyncio
    async def test_trade_resolved_false_for_pending(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "SPY", "call", "pending_resolution", 0.0)
        trade = mock_update.call_args.kwargs["trade"]
        assert trade["resolved"] is False

    @pytest.mark.asyncio
    async def test_venue_matches_platform(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "EURUSD", "put", "loss", -1.0)
        trade = mock_update.call_args.kwargs["trade"]
        assert trade["venue"] == "pocket_option"

    @pytest.mark.asyncio
    async def test_timestamp_is_iso_format(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "EURUSD", "call", "win", 0.5)
        trade = mock_update.call_args.kwargs["trade"]
        # Should parse without error
        datetime.fromisoformat(trade["timestamp"])


class TestUpdateScorecardErrorHandling:
    """Verify _update_scorecard is non-fatal if scorecard update fails."""

    @pytest.mark.asyncio
    async def test_exception_is_caught(self, accumulator):
        """Scorecard failure must not propagate — it's non-fatal."""
        with patch(
            "brain_v9.trading.strategy_scorecard.update_strategy_scorecard",
            side_effect=RuntimeError("disk full"),
        ):
            # Should NOT raise
            await accumulator._update_scorecard("s1", "EURUSD", "call", "win", 0.5)

    @pytest.mark.asyncio
    async def test_import_failure_is_caught(self, accumulator):
        """If the import itself fails, the except block catches it."""
        with patch(
            "brain_v9.trading.strategy_scorecard.update_strategy_scorecard",
            side_effect=ImportError("module not found"),
        ):
            await accumulator._update_scorecard("s1", "EURUSD", "call", "win", 0.5)


class TestUpdateScorecardProfit:
    """Verify profit values flow through correctly."""

    @pytest.mark.asyncio
    async def test_positive_profit_on_win(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "X", "call", "win", 0.85)
        assert mock_update.call_args.kwargs["trade"]["profit"] == 0.85

    @pytest.mark.asyncio
    async def test_negative_profit_on_loss(self, accumulator):
        mock_update = MagicMock(return_value={"aggregate": {}, "symbol": {}, "context": {}})
        with patch("brain_v9.trading.strategy_scorecard.update_strategy_scorecard", mock_update):
            await accumulator._update_scorecard("s1", "X", "put", "loss", -1.0)
        assert mock_update.call_args.kwargs["trade"]["profit"] == -1.0
