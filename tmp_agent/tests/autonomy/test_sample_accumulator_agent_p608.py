"""
P6-08 — Tests for brain_v9/autonomy/sample_accumulator_agent.py

Covers: SampleAccumulatorAgent class (state management, signal merging,
candidate identification, cooldown, unified paper trade execution,
status reporting), module-level singleton helpers.
All I/O and external calls are mocked.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

import brain_v9.autonomy.sample_accumulator_agent as _mod
from brain_v9.autonomy.sample_accumulator_agent import SampleAccumulatorAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(tmp_path, monkeypatch):
    """Create a SampleAccumulatorAgent with BASE_PATH pointing to tmp_path."""
    monkeypatch.setattr(_mod, "BASE_PATH", tmp_path)
    monkeypatch.setattr(_mod, "build_standard_executor", lambda: MagicMock())
    (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)
    return SampleAccumulatorAgent()


def _strategy(
    strategy_id="strat_01",
    venue="pocket_option",
    entries_resolved=5,
    sample_quality=0.2,
    expectancy=0.0,
    signal_valid=True,
    execution_ready=True,
    signal_confidence=0.65,
    signal_direction="call",
    venue_ready=True,
    preferred_symbol="AUDNZD_otc",
    signal_blockers=None,
    indicators=None,
    paper_only=True,
    family="trend",
):
    """Build a strategy dict matching the format the agent expects."""
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "entries_resolved": entries_resolved,
        "sample_quality": sample_quality,
        "expectancy": expectancy,
        "signal_valid": signal_valid,
        "execution_ready": execution_ready,
        "signal_confidence": signal_confidence,
        "signal_direction": signal_direction,
        "venue_ready": venue_ready,
        "preferred_symbol": preferred_symbol,
        "signal_blockers": signal_blockers or [],
        "indicators": indicators or ["rsi", "ema"],
        "paper_only": paper_only,
        "family": family,
    }


# ---------------------------------------------------------------------------
# 1. Init & State management
# ---------------------------------------------------------------------------
class TestInit:
    def test_defaults(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.running is False
        assert agent.session_trades_count == 0
        assert agent.last_trade_time is not None
        assert agent.state_path == tmp_path / "tmp_agent" / "state" / "sample_accumulator.json"

    def test_class_constants(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.MIN_SAMPLE_QUALITY == 0.30
        assert agent.MIN_ENTRIES_RESOLVED == 8
        assert agent.TARGET_ENTRIES == 20
        assert agent.CHECK_INTERVAL_MINUTES == 2
        assert agent.MAX_TRADES_PER_SESSION == 1000
        assert agent.COOLDOWN_MINUTES == 0


class TestLoadState:
    def test_load_existing_state(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        saved = {
            "last_trade_time": "2026-03-20T10:30:00",
            "session_trades_count": 5,
        }
        (state_dir / "sample_accumulator.json").write_text(
            json.dumps(saved), encoding="utf-8"
        )
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.session_trades_count == 5
        assert agent.last_trade_time == datetime.fromisoformat("2026-03-20T10:30:00")

    def test_load_corrupt_json_resets(self, tmp_path, monkeypatch):
        state_dir = tmp_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "sample_accumulator.json").write_text("NOT JSON", encoding="utf-8")
        agent = _make_agent(tmp_path, monkeypatch)
        # Should have reset
        assert agent.session_trades_count == 0

    def test_load_missing_file_resets(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        assert agent.session_trades_count == 0


class TestSaveState:
    def test_save_creates_file(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.last_trade_time = datetime(2026, 3, 20, 12, 0, 0)
        agent.session_trades_count = 3
        agent._save_state()

        data = json.loads(agent.state_path.read_text(encoding="utf-8"))
        assert data["last_trade_time"] == "2026-03-20T12:00:00"
        assert data["session_trades_count"] == 3
        assert "updated_utc" in data

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "BASE_PATH", tmp_path)
        monkeypatch.setattr(_mod, "build_standard_executor", lambda: MagicMock())
        # Ensure state dir does NOT exist
        state_path = tmp_path / "tmp_agent" / "state"
        if state_path.exists():
            import shutil
            shutil.rmtree(state_path)
        (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)
        agent = SampleAccumulatorAgent()
        agent._save_state()
        assert agent.state_path.exists()


class TestResetState:
    def test_reset_zeroes_counters(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 99
        agent.last_trade_time = datetime(2026, 1, 1)
        agent._reset_state()
        assert agent.session_trades_count == 0
        # last_trade_time is set to ~1 hour ago
        delta = datetime.now() - agent.last_trade_time
        assert 50 * 60 <= delta.total_seconds() <= 70 * 60  # ~1 hour


# ---------------------------------------------------------------------------
# 2. Signal merging
# ---------------------------------------------------------------------------
class TestMergeSignalsWithRanking:
    def test_merge_adds_signal_fields(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                {"strategy_id": "s1", "preferred_symbol": "EURUSD"},
            ]
        }
        signals_data = {
            "items": [
                {
                    "strategy_id": "s1",
                    "symbol": "EURUSD",
                    "signal_valid": True,
                    "direction": "put",
                    "confidence": 0.85,
                    "execution_ready": True,
                    "market_regime": "trending",
                    "entry_price": 1.12,
                    "reasons": ["rsi_oversold"],
                    "blockers": [],
                },
            ]
        }
        result = agent._merge_signals_with_ranking(ranking, signals_data)
        s = result["ranked"][0]
        assert s["signal_valid"] is True
        assert s["signal_direction"] == "put"
        assert s["signal_confidence"] == 0.85
        assert s["execution_ready"] is True
        assert s["market_regime"] == "trending"
        assert s["entry_price"] == 1.12
        assert s["signal_reasons"] == ["rsi_oversold"]

    def test_merge_no_match_sets_defaults(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                {"strategy_id": "s_unknown", "preferred_symbol": "GBPJPY"},
            ]
        }
        signals_data = {"items": []}
        result = agent._merge_signals_with_ranking(ranking, signals_data)
        s = result["ranked"][0]
        assert s["signal_valid"] is False
        assert s["signal_direction"] == "call"
        assert s["signal_confidence"] == 0.0
        assert s["execution_ready"] is False

    def test_merge_handles_recovery_candidate(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "top_recovery_candidate": {
                "strategy_id": "rec1",
                "preferred_symbol": "BTCUSD",
            }
        }
        signals_data = {
            "items": [
                {
                    "strategy_id": "rec1",
                    "symbol": "BTCUSD",
                    "signal_valid": True,
                    "direction": "call",
                    "confidence": 0.72,
                    "execution_ready": True,
                },
            ]
        }
        result = agent._merge_signals_with_ranking(ranking, signals_data)
        rc = result["top_recovery_candidate"]
        assert rc["signal_valid"] is True
        assert rc["signal_confidence"] == 0.72

    def test_merge_empty_ranked_list(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {"ranked": []}
        signals_data = {"items": []}
        result = agent._merge_signals_with_ranking(ranking, signals_data)
        assert result["ranked"] == []


# ---------------------------------------------------------------------------
# 3. _has_valid_signal
# ---------------------------------------------------------------------------
class TestHasValidSignal:
    def test_valid_signal(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy()
        assert agent._has_valid_signal(s) is True

    def test_no_signal_valid_flag(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_valid=False)
        assert agent._has_valid_signal(s) is False

    def test_not_execution_ready(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(execution_ready=False)
        assert agent._has_valid_signal(s) is False

    def test_low_confidence(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_confidence=0.49)
        assert agent._has_valid_signal(s) is False

    def test_exactly_threshold_confidence(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_confidence=0.50)
        assert agent._has_valid_signal(s) is True

    def test_venue_not_ready(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(venue_ready=False)
        assert agent._has_valid_signal(s) is False

    def test_critical_blocker_regime(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_blockers=["regime_not_allowed"])
        assert agent._has_valid_signal(s) is False

    def test_critical_blocker_spread(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_blockers=["spread_too_wide"])
        assert agent._has_valid_signal(s) is False

    def test_critical_blocker_symbol(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_blockers=["symbol_not_in_universe"])
        assert agent._has_valid_signal(s) is False

    def test_non_critical_blocker_allowed(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(signal_blockers=["low_volume"])
        assert agent._has_valid_signal(s) is True


# ---------------------------------------------------------------------------
# 4. _calculate_gap
# ---------------------------------------------------------------------------
class TestCalculateGap:
    def test_below_min_entries(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=3, sample_quality=0.5)
        assert agent._calculate_gap(s) == 17  # 20 - 3

    def test_below_min_sample_quality(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=15, sample_quality=0.25)
        assert agent._calculate_gap(s) == 5  # 20 - 15

    def test_both_above_thresholds(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=10, sample_quality=0.40)
        assert agent._calculate_gap(s) == 0  # Both above thresholds

    def test_zero_entries(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=0, sample_quality=0.0)
        assert agent._calculate_gap(s) == 20

    def test_at_exactly_min_entries_and_quality(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        # entries_resolved=8 and sample_quality=0.30 — both at minimum
        s = _strategy(entries_resolved=8, sample_quality=0.30)
        assert agent._calculate_gap(s) == 0  # Not strictly below


# ---------------------------------------------------------------------------
# 5. _calculate_priority
# ---------------------------------------------------------------------------
class TestCalculatePriority:
    def test_basic_priority(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=5, sample_quality=0.2, expectancy=0.0)
        priority = agent._calculate_priority(s)
        gap = 20 - 5  # 15
        sample_penalty = max(0, (0.30 - 0.2) * 10)  # 1.0
        assert priority == gap + 0.0 - sample_penalty  # 14.0

    def test_positive_expectancy_bonus(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=10, sample_quality=0.3, expectancy=5.0)
        priority = agent._calculate_priority(s)
        gap = 20 - 10  # 10
        expectancy_bonus = min(5.0 * 0.1, 2.0)  # 0.5
        sample_penalty = max(0, (0.30 - 0.3) * 10)  # 0.0
        assert priority == gap + expectancy_bonus - sample_penalty  # 10.5

    def test_high_expectancy_capped(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=10, sample_quality=0.3, expectancy=100.0)
        priority = agent._calculate_priority(s)
        gap = 10
        expectancy_bonus = 2.0  # capped
        assert priority == gap + expectancy_bonus  # 12.0

    def test_high_quality_no_penalty(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(entries_resolved=0, sample_quality=0.50, expectancy=0.0)
        priority = agent._calculate_priority(s)
        assert priority == 20.0  # gap=20, no penalty (quality > min)


# ---------------------------------------------------------------------------
# 6. _build_candidate
# ---------------------------------------------------------------------------
class TestBuildCandidate:
    def test_builds_all_fields(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        s = _strategy(
            strategy_id="test_strat",
            venue="ibkr",
            entries_resolved=3,
            sample_quality=0.15,
            signal_direction="put",
            signal_confidence=0.78,
            preferred_symbol="AAPL",
            indicators=["macd", "bb"],
        )
        c = agent._build_candidate(s, gap=17)
        assert c["strategy_id"] == "test_strat"
        assert c["venue"] == "ibkr"
        assert c["entries_resolved"] == 3
        assert c["sample_quality"] == 0.15
        assert c["target_entries"] == 20
        assert c["gap"] == 17
        assert c["signal_valid"] is True
        assert c["signal_direction"] == "put"
        assert c["signal_confidence"] == 0.78
        assert c["preferred_symbol"] == "AAPL"
        assert c["indicators"] == ["macd", "bb"]
        assert isinstance(c["priority"], float)


# ---------------------------------------------------------------------------
# 7. _identify_needy_strategies
# ---------------------------------------------------------------------------
class TestIdentifyNeedyStrategies:
    def test_returns_candidates_with_valid_signal_and_gap(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                _strategy(strategy_id="s1", entries_resolved=5, sample_quality=0.2),
                _strategy(strategy_id="s2", entries_resolved=5, sample_quality=0.2),
            ]
        }
        candidates = agent._identify_needy_strategies(ranking)
        assert len(candidates) == 2
        ids = {c["strategy_id"] for c in candidates}
        assert ids == {"s1", "s2"}

    def test_excludes_strategies_without_signal(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                _strategy(strategy_id="s1", entries_resolved=5, signal_valid=False),
            ]
        }
        candidates = agent._identify_needy_strategies(ranking)
        assert len(candidates) == 0

    def test_excludes_strategies_with_no_gap(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                _strategy(strategy_id="s_full", entries_resolved=10, sample_quality=0.5),
            ]
        }
        candidates = agent._identify_needy_strategies(ranking)
        assert len(candidates) == 0

    def test_includes_recovery_candidate(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "top_recovery_candidate": _strategy(
                strategy_id="recovery", entries_resolved=2, sample_quality=0.1
            ),
            "ranked": [],
        }
        candidates = agent._identify_needy_strategies(ranking)
        assert len(candidates) == 1
        assert candidates[0]["strategy_id"] == "recovery"

    def test_sorted_by_priority_descending(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                # More entries = lower gap = lower priority
                _strategy(strategy_id="low_prio", entries_resolved=7, sample_quality=0.2),
                # Fewer entries = higher gap = higher priority
                _strategy(strategy_id="high_prio", entries_resolved=0, sample_quality=0.0),
            ]
        }
        candidates = agent._identify_needy_strategies(ranking)
        assert candidates[0]["strategy_id"] == "high_prio"
        assert candidates[1]["strategy_id"] == "low_prio"

    def test_empty_ranking(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {"ranked": []}
        candidates = agent._identify_needy_strategies(ranking)
        assert candidates == []


# ---------------------------------------------------------------------------
# 8. _can_execute_trade (cooldown)
# ---------------------------------------------------------------------------
class TestCanExecuteTrade:
    def test_no_last_trade_time(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.last_trade_time = None
        assert agent._can_execute_trade() is True

    def test_with_zero_cooldown_always_true(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.COOLDOWN_MINUTES = 0
        agent.last_trade_time = datetime.now()
        assert agent._can_execute_trade() is True

    def test_cooldown_not_elapsed(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.COOLDOWN_MINUTES = 10
        agent.last_trade_time = datetime.now() - timedelta(minutes=5)
        assert agent._can_execute_trade() is False

    def test_cooldown_elapsed(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.COOLDOWN_MINUTES = 10
        agent.last_trade_time = datetime.now() - timedelta(minutes=15)
        assert agent._can_execute_trade() is True


# ---------------------------------------------------------------------------
# 9. _execute_unified_paper_trade (P6-07)
# ---------------------------------------------------------------------------
class TestExecuteUnifiedPaperTrade:
    def test_calls_execute_paper_trade_correctly(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        mock_ept = MagicMock(return_value={
            "success": True,
            "trade": {"result": "win", "profit": 10.0},
        })
        monkeypatch.setattr(
            "brain_v9.trading.paper_execution.execute_paper_trade",
            mock_ept,
        )

        candidate = {
            "strategy_id": "strat_x",
            "venue": "ibkr",
            "family": "breakout",
            "preferred_symbol": "AAPL",
            "signal_direction": "call",
            "signal_confidence": 0.72,
            "signal_reasons": ["ema_crossover"],
            "signal_blockers": [],
            "entry_price": 150.0,
        }
        result = agent._execute_unified_paper_trade(candidate)

        assert result["success"] is True
        assert mock_ept.call_count == 1

        args = mock_ept.call_args
        strategy_arg, signal_arg, feature_arg = args[0]
        assert strategy_arg["strategy_id"] == "strat_x"
        assert strategy_arg["venue"] == "ibkr"
        assert signal_arg["direction"] == "call"
        assert signal_arg["confidence"] == 0.72
        assert signal_arg["execution_ready"] is True
        assert feature_arg["price_available"] is True
        assert feature_arg["last"] == 150.0

    def test_returns_error_on_failure(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        mock_ept = MagicMock(return_value={
            "success": False,
            "error": "No price data",
            "trade": {},
        })
        monkeypatch.setattr(
            "brain_v9.trading.paper_execution.execute_paper_trade",
            mock_ept,
        )

        candidate = {
            "strategy_id": "strat_fail",
            "venue": "pocket_option",
            "preferred_symbol": "EURUSD",
            "signal_direction": "put",
            "signal_confidence": 0.6,
        }
        result = agent._execute_unified_paper_trade(candidate)
        assert result["success"] is False
        assert result["error"] == "No price data"

    def test_defaults_for_missing_candidate_keys(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        mock_ept = MagicMock(return_value={
            "success": True,
            "trade": {"result": "pending_resolution", "profit": 0.0},
        })
        monkeypatch.setattr(
            "brain_v9.trading.paper_execution.execute_paper_trade",
            mock_ept,
        )
        # Minimal candidate — missing family, entry_price, reasons, blockers
        candidate = {
            "strategy_id": "strat_min",
            "preferred_symbol": "USDJPY",
        }
        result = agent._execute_unified_paper_trade(candidate)
        assert result["success"] is True

        args = mock_ept.call_args
        strategy_arg, signal_arg, feature_arg = args[0]
        assert strategy_arg["venue"] == "unknown"
        assert strategy_arg["family"] == "unknown"
        assert signal_arg["direction"] == "call"
        assert signal_arg["confidence"] == 0.0
        assert feature_arg["last"] is None  # entry_price missing


# ---------------------------------------------------------------------------
# 10. _execute_paper_trades (integration)
# ---------------------------------------------------------------------------
class TestExecutePaperTrades:
    @pytest.mark.asyncio
    async def test_executes_trades_up_to_gap(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0

        mock_unified = MagicMock(return_value={
            "success": True,
            "trade": {"result": "pending_resolution", "profit": 0.0},
        })
        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_unified)

        candidate = {
            "strategy_id": "s1",
            "venue": "pocket_option",
            "gap": 3,
            "signal_direction": "call",
            "signal_confidence": 0.65,
            "indicators": ["rsi"],
            "preferred_symbol": "AUDNZD_otc",
        }
        # Patch asyncio.sleep to avoid real waits
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        await agent._execute_paper_trades(candidate)
        assert mock_unified.call_count == 3
        assert agent.session_trades_count == 3

    @pytest.mark.asyncio
    async def test_respects_max_trades_per_session(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 999  # One slot left

        mock_unified = MagicMock(return_value={
            "success": True,
            "trade": {"result": "win", "profit": 5.0},
        })
        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_unified)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        candidate = {
            "strategy_id": "s1",
            "venue": "ibkr",
            "gap": 5,
            "signal_direction": "put",
            "signal_confidence": 0.8,
            "indicators": [],
            "preferred_symbol": "SPY",
        }
        await agent._execute_paper_trades(candidate)
        assert mock_unified.call_count == 1  # Only 1 trade (max is 1000, started at 999)
        assert agent.session_trades_count == 1000

    @pytest.mark.asyncio
    async def test_handles_failed_trade(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0

        mock_unified = MagicMock(return_value={
            "success": False,
            "error": "No price data",
            "trade": {},
        })
        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_unified)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        candidate = {
            "strategy_id": "s1",
            "venue": "pocket_option",
            "gap": 2,
            "signal_direction": "call",
            "signal_confidence": 0.6,
            "indicators": [],
            "preferred_symbol": "AUDNZD_otc",
        }
        await agent._execute_paper_trades(candidate)
        # Trades attempted but count not incremented on failure
        assert agent.session_trades_count == 0

    @pytest.mark.asyncio
    async def test_handles_exception_in_trade(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0

        mock_unified = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_unified)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        candidate = {
            "strategy_id": "s1",
            "venue": "pocket_option",
            "gap": 1,
            "signal_direction": "call",
            "signal_confidence": 0.6,
            "indicators": [],
            "preferred_symbol": "AUDNZD_otc",
        }
        # Should NOT raise
        await agent._execute_paper_trades(candidate)
        assert agent.session_trades_count == 0

    @pytest.mark.asyncio
    async def test_gap_capped_by_max_trades_per_session(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0
        # Use a small cap to keep the test fast
        agent.MAX_TRADES_PER_SESSION = 10

        call_count = 0

        def mock_trade(c):
            nonlocal call_count
            call_count += 1
            return {"success": True, "trade": {"result": "win", "profit": 1.0}}

        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_trade)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        candidate = {
            "strategy_id": "s1",
            "venue": "ibkr",
            "gap": 50,  # Much more than the patched MAX_TRADES_PER_SESSION (10)
            "signal_direction": "call",
            "signal_confidence": 0.7,
            "indicators": [],
            "preferred_symbol": "AAPL",
        }
        await agent._execute_paper_trades(candidate)
        assert call_count == 10  # Capped at patched MAX_TRADES_PER_SESSION

    @pytest.mark.asyncio
    async def test_saves_state_after_each_trade(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0
        save_spy = MagicMock()
        monkeypatch.setattr(agent, "_save_state", save_spy)

        mock_unified = MagicMock(return_value={
            "success": True,
            "trade": {"result": "win", "profit": 2.0},
        })
        monkeypatch.setattr(agent, "_execute_unified_paper_trade", mock_unified)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        candidate = {
            "strategy_id": "s1",
            "venue": "ibkr",
            "gap": 3,
            "signal_direction": "call",
            "signal_confidence": 0.7,
            "indicators": [],
            "preferred_symbol": "SPY",
        }
        await agent._execute_paper_trades(candidate)
        assert save_spy.call_count == 3  # Saved after each successful trade


# ---------------------------------------------------------------------------
# 11. get_status
# ---------------------------------------------------------------------------
class TestGetStatus:
    def test_status_keys(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        status = agent.get_status()
        expected_keys = {
            "running",
            "last_trade_time",
            "session_trades_count",
            "check_interval_minutes",
            "cooldown_minutes",
            "min_sample_quality",
            "min_entries_resolved",
            "target_entries",
        }
        assert set(status.keys()) == expected_keys

    def test_status_values(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.running = True
        agent.session_trades_count = 7
        status = agent.get_status()
        assert status["running"] is True
        assert status["session_trades_count"] == 7
        assert status["check_interval_minutes"] == 2
        assert status["cooldown_minutes"] == 0
        assert status["min_sample_quality"] == 0.30
        assert status["min_entries_resolved"] == 8
        assert status["target_entries"] == 20

    def test_status_last_trade_time_none(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.last_trade_time = None
        status = agent.get_status()
        assert status["last_trade_time"] is None

    def test_status_last_trade_time_iso(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.last_trade_time = datetime(2026, 3, 25, 14, 30, 0)
        status = agent.get_status()
        assert status["last_trade_time"] == "2026-03-25T14:30:00"


# ---------------------------------------------------------------------------
# 12. start / stop
# ---------------------------------------------------------------------------
class TestStartStop:
    def test_stop(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.running = True
        agent.stop()
        assert agent.running is False

    @pytest.mark.asyncio
    async def test_start_sets_running(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)

        async def fake_check():
            agent.running = False  # Stop after first iteration

        monkeypatch.setattr(agent, "_check_and_accumulate", fake_check)
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        await agent.start()
        # After loop exits, running is False (set by fake_check)
        assert agent.running is False


# ---------------------------------------------------------------------------
# 13. Module-level singleton helpers
# ---------------------------------------------------------------------------
class TestModuleSingleton:
    def test_get_sample_accumulator_creates_instance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "BASE_PATH", tmp_path)
        monkeypatch.setattr(_mod, "build_standard_executor", lambda: MagicMock())
        monkeypatch.setattr(_mod, "_sample_accumulator_instance", None)
        (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)

        instance = _mod.get_sample_accumulator()
        assert isinstance(instance, SampleAccumulatorAgent)

    def test_get_sample_accumulator_returns_same_instance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "BASE_PATH", tmp_path)
        monkeypatch.setattr(_mod, "build_standard_executor", lambda: MagicMock())
        monkeypatch.setattr(_mod, "_sample_accumulator_instance", None)
        (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)

        a = _mod.get_sample_accumulator()
        b = _mod.get_sample_accumulator()
        assert a is b

    def test_stop_sample_accumulator(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "BASE_PATH", tmp_path)
        monkeypatch.setattr(_mod, "build_standard_executor", lambda: MagicMock())
        monkeypatch.setattr(_mod, "_sample_accumulator_instance", None)
        (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)

        instance = _mod.get_sample_accumulator()
        assert instance.running is False  # Not started
        _mod.stop_sample_accumulator()
        assert _mod._sample_accumulator_instance is None

    def test_stop_when_no_instance(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "_sample_accumulator_instance", None)
        # Should not raise
        _mod.stop_sample_accumulator()
        assert _mod._sample_accumulator_instance is None


# ---------------------------------------------------------------------------
# 14. _log_needy_without_signals
# ---------------------------------------------------------------------------
class TestLogNeedyWithoutSignals:
    def test_logs_strategies_without_signal(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "top_recovery_candidate": _strategy(
                strategy_id="rec1",
                entries_resolved=2,
                sample_quality=0.1,
                signal_valid=False,
            ),
            "ranked": [
                _strategy(
                    strategy_id="s1",
                    entries_resolved=3,
                    sample_quality=0.1,
                    signal_valid=False,
                ),
            ],
        }
        # Should not raise; just logs
        agent._log_needy_without_signals(ranking)

    def test_empty_ranking_no_error(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {"ranked": []}
        agent._log_needy_without_signals(ranking)

    def test_skips_strategies_with_signal(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                _strategy(
                    strategy_id="s1",
                    entries_resolved=3,
                    sample_quality=0.1,
                    signal_valid=True,
                ),
            ],
        }
        # Valid signal — should not appear in needy list (just runs without error)
        agent._log_needy_without_signals(ranking)

    def test_skips_strategies_with_no_gap(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {
            "ranked": [
                _strategy(
                    strategy_id="s_full",
                    entries_resolved=20,
                    sample_quality=0.5,
                    signal_valid=False,
                ),
            ],
        }
        agent._log_needy_without_signals(ranking)


# ---------------------------------------------------------------------------
# 15. _check_and_accumulate (integration)
# ---------------------------------------------------------------------------
class TestCheckAndAccumulate:
    @pytest.mark.asyncio
    async def test_no_ranking_returns_early(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        monkeypatch.setattr(agent, "_get_strategy_ranking", AsyncMock(return_value=None))
        # Should not raise
        await agent._check_and_accumulate()

    @pytest.mark.asyncio
    async def test_no_candidates_returns_early(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        ranking = {"ranked": []}
        monkeypatch.setattr(agent, "_get_strategy_ranking", AsyncMock(return_value=ranking))
        log_spy = MagicMock()
        monkeypatch.setattr(agent, "_log_needy_without_signals", log_spy)
        await agent._check_and_accumulate()
        log_spy.assert_called_once_with(ranking)

    @pytest.mark.asyncio
    async def test_full_cycle_executes_trade(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.session_trades_count = 0

        ranking = {
            "ranked": [
                _strategy(strategy_id="s1", entries_resolved=2, sample_quality=0.1),
            ]
        }
        monkeypatch.setattr(agent, "_get_strategy_ranking", AsyncMock(return_value=ranking))
        exec_spy = AsyncMock()
        monkeypatch.setattr(agent, "_execute_paper_trades", exec_spy)

        await agent._check_and_accumulate()
        assert exec_spy.call_count == 1

    @pytest.mark.asyncio
    async def test_cooldown_blocks_execution(self, tmp_path, monkeypatch):
        agent = _make_agent(tmp_path, monkeypatch)
        agent.COOLDOWN_MINUTES = 60
        agent.last_trade_time = datetime.now()  # Just traded

        ranking = {
            "ranked": [
                _strategy(strategy_id="s1", entries_resolved=2, sample_quality=0.1),
            ]
        }
        monkeypatch.setattr(agent, "_get_strategy_ranking", AsyncMock(return_value=ranking))
        exec_spy = AsyncMock()
        monkeypatch.setattr(agent, "_execute_paper_trades", exec_spy)

        await agent._check_and_accumulate()
        assert exec_spy.call_count == 0  # Blocked by cooldown
