"""
Tests for P3-09: expand_signal_pipeline — real signal pipeline expansion.

Verifies that the rewritten expand_signal_pipeline():
  - Refreshes the strategy engine and ranking
  - Temporarily widens filter tolerances (confidence_threshold, spread_pct_max)
  - Scans all strategies for executable signals
  - Executes a paper trade when a viable signal is found
  - Restores original filter values after execution
  - Decrements skip counter regardless of trade execution
  - Logs the action in the scorecard
  - Returns correct result structure
"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_action_executor(monkeypatch, tmp_path):
    """Redirect action_executor module-level paths to tmp_path."""
    import brain_v9.autonomy.action_executor as ae

    state = tmp_path / "tmp_agent" / "state"
    rooms = state / "rooms"
    monkeypatch.setattr(ae, "STATE_PATH", state)
    monkeypatch.setattr(ae, "ROOMS_PATH", rooms)
    monkeypatch.setattr(ae, "JOBS_PATH", state / "autonomy_action_jobs")
    monkeypatch.setattr(ae, "JOBS_LEDGER", state / "autonomy_action_ledger.json")
    monkeypatch.setattr(ae, "NEXT_ACTIONS_PATH", state / "autonomy_next_actions.json")
    monkeypatch.setattr(ae, "SCORECARD_PATH",
                        rooms / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json")
    monkeypatch.setattr(ae, "PO_BRIDGE_ARTIFACT",
                        rooms / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json")
    monkeypatch.setattr(ae, "IBKR_LANE_PATH",
                        rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_readonly_lane.json")
    monkeypatch.setattr(ae, "IBKR_PROBE_PATH",
                        rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json")
    monkeypatch.setattr(ae, "IBKR_ORDER_CHECK_PATH",
                        state / "trading_execution_checks" / "ibkr_paper_order_check_latest.json")
    monkeypatch.setattr(ae, "TRADING_POLICY_PATH", state / "trading_autonomy_policy.json")

    # Create required dirs
    (state / "autonomy_action_jobs").mkdir(parents=True, exist_ok=True)
    (rooms / "brain_binary_paper_pb05_journal").mkdir(parents=True, exist_ok=True)

    return ae


def _make_ranked_strategies():
    """Create a minimal ranking payload with 2 strategies."""
    return {
        "schema_version": "strategy_ranking_latest_v2",
        "ranked": [
            {
                "strategy_id": "strat_trend_a",
                "venue": "internal_paper_simulator",
                "family": "trend_following",
                "governance_state": "paper_active",
                "archive_state": "testing",
                "execution_ready": True,
                "signal_valid": True,
                "confidence": 0.55,
            },
            {
                "strategy_id": "strat_breakout_b",
                "venue": "internal_paper_simulator",
                "family": "breakout",
                "governance_state": "paper_candidate",
                "archive_state": "testing",
                "execution_ready": False,
                "signal_valid": False,
                "confidence": 0.30,
            },
        ],
        "top_recovery_candidate": {"strategy_id": "strat_trend_a"},
    }


def _make_strategies():
    """Create normalized strategy specs."""
    return {
        "strategies": [
            {
                "strategy_id": "strat_trend_a",
                "venue": "internal_paper_simulator",
                "family": "trend_following",
                "confidence_threshold": 0.58,
                "filters": {"spread_pct_max": 0.25},
                "universe": ["EURUSD_otc"],
                "timeframes": ["1m"],
                "setup_variants": ["base"],
                "asset_classes": ["otc_binary"],
            },
            {
                "strategy_id": "strat_breakout_b",
                "venue": "internal_paper_simulator",
                "family": "breakout",
                "confidence_threshold": 0.58,
                "filters": {"spread_pct_max": 0.20},
                "universe": ["EURUSD_otc"],
                "timeframes": ["1m"],
                "setup_variants": ["base"],
                "asset_classes": ["otc_binary"],
            },
        ]
    }


def _make_signal_snapshot_with_ready():
    """Signal snapshot where strat_trend_a has a ready signal."""
    return {
        "schema_version": "strategy_signal_snapshot_v1",
        "by_strategy": [
            {
                "strategy_id": "strat_trend_a",
                "best_signal": {
                    "strategy_id": "strat_trend_a",
                    "symbol": "EURUSD_otc",
                    "direction": "call",
                    "execution_ready": True,
                    "signal_valid": True,
                    "confidence": 0.50,
                },
                "execution_ready": True,
            },
            {
                "strategy_id": "strat_breakout_b",
                "best_signal": {
                    "strategy_id": "strat_breakout_b",
                    "symbol": "EURUSD_otc",
                    "direction": "put",
                    "execution_ready": False,
                    "signal_valid": False,
                    "confidence": 0.20,
                },
                "execution_ready": False,
            },
        ],
        "items": [],
    }


def _make_signal_snapshot_none_ready():
    """Signal snapshot where no strategy has a ready signal."""
    return {
        "schema_version": "strategy_signal_snapshot_v1",
        "by_strategy": [
            {
                "strategy_id": "strat_trend_a",
                "best_signal": {
                    "strategy_id": "strat_trend_a",
                    "symbol": "EURUSD_otc",
                    "direction": "call",
                    "execution_ready": False,
                    "signal_valid": False,
                    "confidence": 0.30,
                },
                "execution_ready": False,
            },
        ],
        "items": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestExpandSignalPipelineStructure:

    def test_action_map_includes_signal_pipeline(self, isolated_base_path, monkeypatch):
        """expand_signal_pipeline should be registered in ACTION_MAP."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)
        assert "improve_signal_capture_and_context_window" in ae.ACTION_MAP
        assert ae.ACTION_MAP["improve_signal_capture_and_context_window"] is ae.expand_signal_pipeline

    def test_result_structure_keys(self, isolated_base_path, monkeypatch):
        """Result dict should contain required keys."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        # Mock heavy dependencies
        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value={"strategies": []}), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value={"by_strategy": [], "items": []}):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        assert "action_name" in result
        assert result["action_name"] == "improve_signal_capture_and_context_window"
        assert "paper_only_enforced" in result
        assert result["paper_only_enforced"] is True
        assert "filter_widening_applied" in result
        assert "viable_signal_found" in result
        assert "trade_executed" in result
        assert "reduced_skips_to" in result

    def test_no_todo_in_notes(self, isolated_base_path, monkeypatch):
        """The rewritten function should not have TODO comments in the scorecard notes."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value={"strategies": []}), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value={"by_strategy": [], "items": []}):
            asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_pipeline_notes", [])
        for note in notes:
            assert "TODO" not in note.get("detail", ""), \
                "Stub TODO text should be removed in real implementation"


class TestExpandSignalPipelineFilterWidening:

    def test_confidence_threshold_widened(self, isolated_base_path, monkeypatch):
        """Strategies should get confidence_threshold=0.35 during scan."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranked_strategies)

        captured_strategies = []

        def mock_build_signal(strategies, feature_snap):
            # Capture the strategies during the widened phase
            for s in strategies:
                captured_strategies.append({
                    "strategy_id": s["strategy_id"],
                    "confidence_threshold": s.get("confidence_threshold"),
                    "spread_pct_max": (s.get("filters") or {}).get("spread_pct_max"),
                })
            return _make_signal_snapshot_none_ready()

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    side_effect=mock_build_signal):
            asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        # Check widened values
        assert len(captured_strategies) == 2
        for cs in captured_strategies:
            assert cs["confidence_threshold"] == 0.48, \
                f"Confidence threshold should be lowered to 0.48, got {cs['confidence_threshold']}"

    def test_spread_filter_widened(self, isolated_base_path, monkeypatch):
        """spread_pct_max should be widened by 30% during scan."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranked_strategies)

        captured_spreads = {}

        def mock_build_signal(strategies, feature_snap):
            for s in strategies:
                captured_spreads[s["strategy_id"]] = (s.get("filters") or {}).get("spread_pct_max")
            return _make_signal_snapshot_none_ready()

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    side_effect=mock_build_signal):
            asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        # strat_trend_a: 0.25 * 1.30 = 0.325
        assert abs(captured_spreads["strat_trend_a"] - 0.325) < 0.001
        # strat_breakout_b: 0.20 * 1.30 = 0.26
        assert abs(captured_spreads["strat_breakout_b"] - 0.26) < 0.001

    def test_frozen_strategies_not_widened(self, isolated_base_path, monkeypatch):
        """Frozen strategies should not have their filters widened."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        ranking = _make_ranked_strategies()
        ranking["ranked"][0]["governance_state"] = "frozen"

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: ranking)

        captured_thresholds = {}

        def mock_build_signal(strategies, feature_snap):
            for s in strategies:
                captured_thresholds[s["strategy_id"]] = s.get("confidence_threshold")
            return _make_signal_snapshot_none_ready()

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    side_effect=mock_build_signal):
            asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        # strat_trend_a is frozen, should keep original 0.58
        assert captured_thresholds["strat_trend_a"] == 0.58
        # strat_breakout_b is not frozen, should be widened to 0.48
        assert captured_thresholds["strat_breakout_b"] == 0.48


class TestExpandSignalPipelineExecution:

    def test_trade_executed_when_signal_found(self, isolated_base_path, monkeypatch):
        """When a viable signal is found, a paper trade should be executed."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranked_strategies)

        mock_batch = AsyncMock(return_value={
            "success": True,
            "artifact": "",
            "total_profit": 0.85,
        })

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value=_make_signal_snapshot_with_ready()), \
             patch("brain_v9.trading.strategy_engine.execute_candidate_batch",
                    mock_batch):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        assert result["viable_signal_found"] is True
        mock_batch.assert_called_once_with("strat_trend_a", 1, allow_frozen=False)

    def test_no_trade_when_no_signal(self, isolated_base_path, monkeypatch):
        """When no viable signal exists, no trade should be attempted."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranked_strategies)

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value=_make_signal_snapshot_none_ready()):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        assert result["viable_signal_found"] is False
        assert result["trade_executed"] is False
        assert result["trade"] is None


class TestExpandSignalPipelineSkipCounter:

    def test_skip_counter_decremented(self, isolated_base_path, monkeypatch):
        """Skip counter should be decremented regardless of trade execution."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        # Write a scorecard with skips=5
        _write_json(ae.SCORECARD_PATH, {
            "seed_metrics": {"valid_candidates_skipped": 5},
        })

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value={"strategies": []}), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value={"by_strategy": [], "items": []}):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        assert result["reduced_skips_to"] == 0

    def test_skip_counter_does_not_go_negative(self, isolated_base_path, monkeypatch):
        """Skip counter should not go below 0."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        _write_json(ae.SCORECARD_PATH, {
            "seed_metrics": {"valid_candidates_skipped": 0},
        })

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value={"strategies": []}), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value={"by_strategy": [], "items": []}):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        assert result["reduced_skips_to"] == 0

    def test_pipeline_notes_capped(self, isolated_base_path, monkeypatch):
        """Pipeline notes should be capped at 100 entries (pruned to 50)."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: {"ranked": []})

        # Write scorecard with 101 notes
        _write_json(ae.SCORECARD_PATH, {
            "seed_metrics": {"valid_candidates_skipped": 1},
            "autonomy_pipeline_notes": [{"i": i} for i in range(101)],
        })

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value={"strategies": []}), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value={"by_strategy": [], "items": []}):
            asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        scorecard = _read_json(ae.SCORECARD_PATH)
        notes = scorecard.get("autonomy_pipeline_notes", [])
        assert len(notes) <= 51  # 50 kept + 1 new


class TestExpandSignalPipelineHighestConfidence:

    def test_selects_highest_confidence_signal(self, isolated_base_path, monkeypatch):
        """When multiple ready signals exist, picks the one with highest confidence."""
        ae = _patch_action_executor(monkeypatch, isolated_base_path)

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: {})
        monkeypatch.setattr(ae, "read_ranking_v2", _make_ranked_strategies)

        # Both strategies have ready signals, but B has higher confidence
        signal_snap = {
            "by_strategy": [
                {
                    "strategy_id": "strat_trend_a",
                    "best_signal": {
                        "execution_ready": True,
                        "confidence": 0.55,
                    },
                    "execution_ready": True,
                },
                {
                    "strategy_id": "strat_breakout_b",
                    "best_signal": {
                        "execution_ready": True,
                        "confidence": 0.72,
                    },
                    "execution_ready": True,
                },
            ],
            "items": [],
        }

        mock_batch = AsyncMock(return_value={"success": True, "artifact": ""})

        with patch("brain_v9.trading.strategy_engine._normalize_strategy_specs",
                    return_value=_make_strategies()), \
             patch("brain_v9.trading.feature_engine.read_market_feature_snapshot",
                    return_value={"items": []}), \
             patch("brain_v9.trading.signal_engine.build_strategy_signal_snapshot",
                    return_value=signal_snap), \
             patch("brain_v9.trading.strategy_engine.execute_candidate_batch",
                    mock_batch):
            result = asyncio.get_event_loop().run_until_complete(ae.expand_signal_pipeline())

        # Should pick strat_breakout_b (higher confidence)
        mock_batch.assert_called_once_with("strat_breakout_b", 1, allow_frozen=False)
        assert result["strategy_tag"] == "strat_breakout_b"
