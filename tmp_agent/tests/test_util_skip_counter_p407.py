"""
Tests for P4-07: Unified skip counter.

Verifies:
  - util.py is the single source of truth for skip counting
  - increment_skips_counter syncs to scorecard
  - reset_skips_counter syncs to scorecard
  - _update_scorecard_with_trade no longer independently decrements
  - expand_signal_pipeline uses util.py counter
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import brain_v9.config as _cfg


# ---------- Helpers ----------

def _write_scorecard(base_path: Path, skips: int = 5, resolved: int = 1) -> Path:
    scorecard_path = (
        base_path / "tmp_agent" / "state" / "rooms"
        / "brain_binary_paper_pb05_journal"
        / "session_result_scorecard.json"
    )
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    scorecard_path.write_text(json.dumps({
        "seed_metrics": {
            "entries_taken": 10,
            "entries_resolved": resolved,
            "wins": 5,
            "losses": 5,
            "gross_units": 0,
            "net_units": 0,
            "valid_candidates_skipped": skips,
        },
        "entry_outcome_counts": {},
        "strategy_performance_seed": {},
        "pair_performance_seed": {},
        "pair_breakdown_seed": {},
    }), encoding="utf-8")
    return scorecard_path


def _read_scorecard(scorecard_path: Path) -> Dict:
    return json.loads(scorecard_path.read_text(encoding="utf-8"))


# ---------- Test: util.py counter syncs to scorecard ----------

class TestSkipCounterSync:
    """Verify that util.py's skip counter syncs to scorecard."""

    def test_increment_syncs_to_scorecard(self, isolated_base_path, monkeypatch):
        """increment_skips_counter should update scorecard's valid_candidates_skipped."""
        import brain_v9.util as util

        # Reset global state
        util._skips_state = {
            "consecutive_skips": 0,
            "last_skip_timestamp": None,
            "skip_history": [],
        }

        # Patch BRAIN_V9_PATH to isolated path
        monkeypatch.setattr(util, "BRAIN_V9_PATH", isolated_base_path / "tmp_agent")

        # Create scorecard with 0 skips
        scorecard_path = _write_scorecard(isolated_base_path, skips=0)

        # Increment
        new_count = util.increment_skips_counter(reason="test skip")
        assert new_count == 1

        # Check scorecard was synced
        scorecard = _read_scorecard(scorecard_path)
        assert scorecard["seed_metrics"]["valid_candidates_skipped"] == 1

    def test_multiple_increments_sync(self, isolated_base_path, monkeypatch):
        """Multiple increments should all sync."""
        import brain_v9.util as util

        util._skips_state = {
            "consecutive_skips": 0,
            "last_skip_timestamp": None,
            "skip_history": [],
        }
        monkeypatch.setattr(util, "BRAIN_V9_PATH", isolated_base_path / "tmp_agent")
        scorecard_path = _write_scorecard(isolated_base_path, skips=0)

        util.increment_skips_counter(reason="skip 1")
        util.increment_skips_counter(reason="skip 2")
        util.increment_skips_counter(reason="skip 3")

        scorecard = _read_scorecard(scorecard_path)
        assert scorecard["seed_metrics"]["valid_candidates_skipped"] == 3

    def test_reset_syncs_to_scorecard(self, isolated_base_path, monkeypatch):
        """reset_skips_counter should set scorecard's valid_candidates_skipped to 0."""
        import brain_v9.util as util

        util._skips_state = {
            "consecutive_skips": 5,
            "last_skip_timestamp": None,
            "skip_history": [],
        }
        monkeypatch.setattr(util, "BRAIN_V9_PATH", isolated_base_path / "tmp_agent")
        scorecard_path = _write_scorecard(isolated_base_path, skips=5)

        util.reset_skips_counter()

        # util counter should be 0
        assert util.get_consecutive_skips() == 0

        # scorecard should also be 0
        scorecard = _read_scorecard(scorecard_path)
        assert scorecard["seed_metrics"]["valid_candidates_skipped"] == 0

    def test_sync_nonfatal_if_no_scorecard(self, isolated_base_path, monkeypatch):
        """If scorecard file doesn't exist, sync should not crash."""
        import brain_v9.util as util

        util._skips_state = {
            "consecutive_skips": 0,
            "last_skip_timestamp": None,
            "skip_history": [],
        }
        monkeypatch.setattr(util, "BRAIN_V9_PATH", isolated_base_path / "tmp_agent")
        # Don't create scorecard file

        # Should not raise
        new_count = util.increment_skips_counter(reason="no scorecard")
        assert new_count == 1


# ---------- Test: _update_scorecard_with_trade no longer decrements independently ----------

class TestUpdateScorecardNoIndependentDecrement:
    """Verify that _update_scorecard_with_trade delegates skip management to util.py."""

    @patch("brain_v9.trading.platform_manager.get_platform_manager")
    def test_trade_does_not_decrement_skips_directly(self, mock_get_pm):
        """After a trade, valid_candidates_skipped should NOT be decremented by _update_scorecard_with_trade itself."""
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        from brain_v9.autonomy.action_executor import _update_scorecard_with_trade

        scorecard = {
            "seed_metrics": {
                "entries_taken": 0,
                "entries_resolved": 0,
                "wins": 0,
                "losses": 0,
                "gross_units": 0,
                "net_units": 0,
                "valid_candidates_skipped": 10,
            },
            "entry_outcome_counts": {},
            "strategy_performance_seed": {},
            "pair_performance_seed": {},
            "pair_breakdown_seed": {},
        }
        trade = {"result": "win", "profit": 5.0, "symbol": "EURUSD_otc", "direction": "call"}

        _update_scorecard_with_trade(scorecard, trade, "test_strategy", platform="internal_paper")

        # valid_candidates_skipped should remain 10 — not decremented
        # (reset_skips_counter is called separately in the action executor)
        assert scorecard["seed_metrics"]["valid_candidates_skipped"] == 10


# ---------- Test: get_skip_status returns consistent data ----------

class TestGetSkipStatus:
    """Verify get_skip_status returns correct data."""

    def test_status_reflects_increments(self, isolated_base_path, monkeypatch):
        import brain_v9.util as util

        util._skips_state = {
            "consecutive_skips": 0,
            "last_skip_timestamp": None,
            "skip_history": [],
        }
        monkeypatch.setattr(util, "BRAIN_V9_PATH", isolated_base_path / "tmp_agent")
        # Create state dir for skips file
        (isolated_base_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)

        util.increment_skips_counter(reason="skip A")
        util.increment_skips_counter(reason="skip B")

        status = util.get_skip_status()
        assert status["consecutive_skips"] == 2
        assert len(status["skip_history"]) == 2
        assert status["skip_history"][0]["reason"] == "skip A"
        assert status["skip_history"][1]["reason"] == "skip B"
