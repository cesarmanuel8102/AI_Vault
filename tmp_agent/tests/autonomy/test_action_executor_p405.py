"""
Tests for P4-05: expand_signal_pipeline regime widening.

Verifies that expand_signal_pipeline:
  - Saves original market_regime_allowed before widening
  - Adds 'range' and 'mild' to strategies that lack them
  - Does NOT duplicate 'range'/'mild' if already present
  - Restores original regime lists after signal scan
  - Skips frozen/archived strategies
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Any, Dict, List


# ---------- Helpers ----------

def _make_strategy(sid: str, regimes: List[str],
                   spread_max: float | None = None,
                   confidence: float = 0.48) -> Dict[str, Any]:
    return {
        "strategy_id": sid,
        "family": "breakout",
        "venue": "pocket_option",
        "confidence_threshold": confidence,
        "filters": {
            "spread_pct_max": spread_max,
            "market_regime_allowed": list(regimes),
        },
    }


def _make_ranking(strategy_ids: List[str],
                  frozen_ids: set | None = None,
                  archived_ids: set | None = None) -> Dict[str, Any]:
    frozen_ids = frozen_ids or set()
    archived_ids = archived_ids or set()
    ranked = []
    for sid in strategy_ids:
        entry: Dict[str, Any] = {"strategy_id": sid}
        if sid in frozen_ids:
            entry["governance_state"] = "frozen"
        if sid in archived_ids:
            entry["archive_state"] = "archived_cold"
        ranked.append(entry)
    return {"ranked": ranked}


# ---------- Test: Regime widening logic (extracted from expand_signal_pipeline) ----------

class TestRegimeWideningLogic:
    """Test the regime widening/restore logic that P4-05 added."""

    def test_adds_range_and_mild_when_missing(self):
        """Strategies missing 'range' or 'mild' should get them added."""
        strategy = _make_strategy("test_strat", ["trend_mild", "trend_strong"])
        originals: Dict[str, Dict] = {}

        # Simulate the widening loop from expand_signal_pipeline
        sid = strategy["strategy_id"]
        filters = strategy.get("filters") or {}
        originals[sid] = {
            "confidence_threshold": strategy.get("confidence_threshold", 0.48),
            "spread_pct_max": filters.get("spread_pct_max"),
            "market_regime_allowed": list(filters.get("market_regime_allowed") or []),
        }
        regime_list = filters.get("market_regime_allowed")
        if regime_list is not None and isinstance(regime_list, list):
            for fallback_regime in ("range", "mild"):
                if fallback_regime not in regime_list:
                    regime_list.append(fallback_regime)

        # After widening: both 'range' and 'mild' should be added
        assert "range" in strategy["filters"]["market_regime_allowed"]
        assert "mild" in strategy["filters"]["market_regime_allowed"]
        assert len(strategy["filters"]["market_regime_allowed"]) == 4

        # Originals should be preserved
        assert originals[sid]["market_regime_allowed"] == ["trend_mild", "trend_strong"]

    def test_no_duplicates_when_already_present(self):
        """If 'range' and 'mild' are already in the list, don't duplicate them."""
        strategy = _make_strategy("test_strat", ["range", "mild", "trend_mild"])
        filters = strategy.get("filters") or {}
        original_regimes = list(filters.get("market_regime_allowed") or [])

        regime_list = filters.get("market_regime_allowed")
        if regime_list is not None and isinstance(regime_list, list):
            for fallback_regime in ("range", "mild"):
                if fallback_regime not in regime_list:
                    regime_list.append(fallback_regime)

        # Should be unchanged
        assert strategy["filters"]["market_regime_allowed"] == ["range", "mild", "trend_mild"]
        assert len(strategy["filters"]["market_regime_allowed"]) == 3

    def test_restore_removes_added_regimes(self):
        """After restore, regime list should be exactly the original."""
        strategy = _make_strategy("test_strat", ["trend_strong"])
        sid = strategy["strategy_id"]
        filters = strategy.get("filters") or {}

        # Save original
        originals = {
            sid: {
                "confidence_threshold": 0.48,
                "spread_pct_max": None,
                "market_regime_allowed": list(filters.get("market_regime_allowed") or []),
            }
        }

        # Widen
        regime_list = filters.get("market_regime_allowed")
        for fallback_regime in ("range", "mild"):
            if fallback_regime not in regime_list:
                regime_list.append(fallback_regime)

        assert len(strategy["filters"]["market_regime_allowed"]) == 3  # expanded

        # Restore
        original_regimes = originals[sid].get("market_regime_allowed")
        if original_regimes is not None:
            filters["market_regime_allowed"] = original_regimes

        assert strategy["filters"]["market_regime_allowed"] == ["trend_strong"]

    def test_empty_regime_list_gets_range_and_mild(self):
        """An empty regime list should get 'range' and 'mild' added."""
        strategy = _make_strategy("test_strat", [])
        filters = strategy.get("filters") or {}
        regime_list = filters.get("market_regime_allowed")
        if regime_list is not None and isinstance(regime_list, list):
            for fallback_regime in ("range", "mild"):
                if fallback_regime not in regime_list:
                    regime_list.append(fallback_regime)

        assert strategy["filters"]["market_regime_allowed"] == ["range", "mild"]

    def test_none_regime_list_not_modified(self):
        """If market_regime_allowed is None, widening should not crash."""
        strategy = {
            "strategy_id": "test",
            "filters": {"market_regime_allowed": None},
        }
        filters = strategy.get("filters") or {}
        regime_list = filters.get("market_regime_allowed")
        if regime_list is not None and isinstance(regime_list, list):
            for fallback_regime in ("range", "mild"):
                if fallback_regime not in regime_list:
                    regime_list.append(fallback_regime)

        # Should still be None — we don't create a list from nothing
        assert strategy["filters"]["market_regime_allowed"] is None


# ---------- Test: Full expand_signal_pipeline integration ----------

class TestExpandSignalPipelineRegimeIntegration:
    """Integration tests verifying expand_signal_pipeline saves/restores regime lists."""

    @pytest.fixture
    def mock_deps(self, isolated_base_path, monkeypatch):
        """Patch all heavy dependencies of expand_signal_pipeline."""
        import brain_v9.autonomy.action_executor as ae

        # Patch module-level paths
        state_path = isolated_base_path / "tmp_agent" / "state"
        state_path.mkdir(parents=True, exist_ok=True)
        scorecard_path = state_path / "rooms" / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json"
        scorecard_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(ae, "SCORECARD_PATH", scorecard_path)

        # Write empty scorecard
        import json
        scorecard_path.write_text(json.dumps({
            "seed_metrics": {"valid_candidates_skipped": 5, "entries_resolved": 1},
        }))

        # Patch trading policy
        monkeypatch.setattr(ae, "_ensure_trading_policy", lambda: None)
        monkeypatch.setattr(ae, "_select_execution_lane", lambda: {
            "selected": {"platform": "pocket_option", "venue": "pocket_option"},
            "candidates": [],
        })

        # Patch strategy engine calls
        test_strategies = [
            _make_strategy("strat_a", ["trend_mild", "trend_strong"]),
            _make_strategy("strat_b", ["range", "mild", "trend_mild"]),
        ]
        test_specs = {"strategies": test_strategies}
        test_ranking = _make_ranking(["strat_a", "strat_b"])

        monkeypatch.setattr(ae, "refresh_strategy_engine", lambda: None)
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: test_ranking)

        # Patch lazy imports inside expand_signal_pipeline
        mock_normalize = MagicMock(return_value=test_specs)
        mock_read_snapshot = MagicMock(return_value={})
        mock_feature_snapshot = MagicMock(return_value={})
        mock_build_signal = MagicMock(return_value={"by_strategy": []})

        monkeypatch.setattr(
            "brain_v9.trading.strategy_engine._normalize_strategy_specs", mock_normalize
        )
        monkeypatch.setattr(
            "brain_v9.trading.strategy_engine.read_signal_snapshot", mock_read_snapshot
        )
        monkeypatch.setattr(
            "brain_v9.trading.signal_engine.build_strategy_signal_snapshot", mock_build_signal
        )
        monkeypatch.setattr(
            "brain_v9.trading.feature_engine.read_market_feature_snapshot", mock_feature_snapshot
        )

        return {
            "strategies": test_strategies,
            "build_signal": mock_build_signal,
        }

    @pytest.mark.asyncio
    async def test_regime_widened_during_signal_scan(self, mock_deps):
        """build_strategy_signal_snapshot should be called with widened regime lists."""
        from brain_v9.autonomy.action_executor import expand_signal_pipeline

        build_signal = mock_deps["build_signal"]

        # Capture what strategies looked like when build_signal was called
        captured_strategies = []
        def capture_call(strategies, features):
            # Deep copy the strategy filters at call time
            import copy
            captured_strategies.extend(copy.deepcopy(strategies))
            return {"by_strategy": []}
        build_signal.side_effect = capture_call

        result = await expand_signal_pipeline()

        # strat_a originally had ["trend_mild", "trend_strong"] — should have range+mild added
        strat_a = next(s for s in captured_strategies if s["strategy_id"] == "strat_a")
        assert "range" in strat_a["filters"]["market_regime_allowed"]
        assert "mild" in strat_a["filters"]["market_regime_allowed"]

        # strat_b originally had ["range", "mild", "trend_mild"] — no duplicates
        strat_b = next(s for s in captured_strategies if s["strategy_id"] == "strat_b")
        assert strat_b["filters"]["market_regime_allowed"].count("range") == 1
        assert strat_b["filters"]["market_regime_allowed"].count("mild") == 1

    @pytest.mark.asyncio
    async def test_regime_restored_after_scan(self, mock_deps):
        """After expand_signal_pipeline returns, strategy regime lists must be restored."""
        from brain_v9.autonomy.action_executor import expand_signal_pipeline

        strategies = mock_deps["strategies"]
        result = await expand_signal_pipeline()

        # strat_a should be restored to original
        strat_a = next(s for s in strategies if s["strategy_id"] == "strat_a")
        assert strat_a["filters"]["market_regime_allowed"] == ["trend_mild", "trend_strong"]

        # strat_b should be restored to original
        strat_b = next(s for s in strategies if s["strategy_id"] == "strat_b")
        assert strat_b["filters"]["market_regime_allowed"] == ["range", "mild", "trend_mild"]

    @pytest.mark.asyncio
    async def test_frozen_strategy_not_widened(self, mock_deps, monkeypatch):
        """Frozen strategies should not have their regime lists widened."""
        import brain_v9.autonomy.action_executor as ae

        frozen_ranking = _make_ranking(["strat_a", "strat_b"], frozen_ids={"strat_a"})
        monkeypatch.setattr(ae, "read_ranking_v2", lambda: frozen_ranking)

        strategies = mock_deps["strategies"]
        build_signal = mock_deps["build_signal"]

        captured_strategies = []
        def capture_call(strats, features):
            import copy
            captured_strategies.extend(copy.deepcopy(strats))
            return {"by_strategy": []}
        build_signal.side_effect = capture_call

        result = await ae.expand_signal_pipeline()

        # strat_a is frozen — should NOT be widened
        strat_a = next(s for s in captured_strategies if s["strategy_id"] == "strat_a")
        assert strat_a["filters"]["market_regime_allowed"] == ["trend_mild", "trend_strong"]

        # strat_b is not frozen — should be widened
        strat_b = next(s for s in captured_strategies if s["strategy_id"] == "strat_b")
        assert "range" in strat_b["filters"]["market_regime_allowed"]
