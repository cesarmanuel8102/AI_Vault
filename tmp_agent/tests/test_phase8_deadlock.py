"""P8: Tests for Phase 8 — Break the Deadlock.

Covers:
1.  Deadlock detection in utility.py — system_deadlock blocker + top_action override
2.  expand_signal_pipeline dispatch when no top_strategy (Fix 6)
3.  force_unfreeze_best_frozen() in strategy_scorecard.py
4.  force_unfreeze skips retired/archived strategies
5.  force_unfreeze prefers small-sample strategies
6.  generate_strategy_variants() in knowledge_base.py
7.  generate_strategy_variants skips when no frozen sources
8.  generate_strategy_variants avoids duplicate IDs
9.  break_system_deadlock action wired into ACTION_MAP
10. break_system_deadlock wired into manager _TRADING_ACTIONS
11. break_system_deadlock composite action runs all steps
12. No deadlock detected when active strategies exist
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import brain_v9.config as _cfg
import brain_v9.trading.strategy_scorecard as sc
from brain_v9.trading.strategy_scorecard import (
    _recompute,
    _blank_scorecard,
    _utc_now,
    force_unfreeze_best_frozen,
    unfreeze_eligible_strategies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_strategy(strategy_id: str = "strat_01", venue: str = "PocketOption"):
    return {
        "strategy_id": strategy_id,
        "family": "test_family",
        "venue": venue,
        "status": "paper_candidate",
        "universe": ["EURUSD"],
        "timeframes": ["5m"],
        "setup_variants": ["base"],
        "linked_hypotheses": [],
        "success_criteria": {
            "min_resolved_trades": 10,
            "min_expectancy": 0.05,
            "min_win_rate": 0.45,
        },
    }


def _make_frozen_card(
    strategy_id: str = "strat_01",
    expectancy: float = -0.20,
    entries_resolved: int = 10,
    wins: int = 2,
    losses: int = 8,
    gross_profit: float = 1.0,
    gross_loss: float = 4.0,
    net_pnl: float = -3.0,
    freeze_reason: str | None = None,
    freeze_utc: str | None = None,
    archive_state: str | None = None,
) -> dict:
    """Create a frozen scorecard."""
    card = _blank_scorecard(_make_strategy(strategy_id))
    card["governance_state"] = "frozen"
    card["promotion_state"] = "frozen"
    card["wins"] = wins
    card["losses"] = losses
    card["entries_resolved"] = entries_resolved
    card["gross_profit"] = gross_profit
    card["gross_loss"] = gross_loss
    card["net_pnl"] = net_pnl
    card["expectancy"] = expectancy
    if freeze_reason:
        card["freeze_reason"] = freeze_reason
    if freeze_utc:
        card["freeze_utc"] = freeze_utc
    if archive_state:
        card["archive_state"] = archive_state
    return card


def _make_ranking_all_frozen() -> dict:
    """Strategy ranking where all strategies are frozen, no top_strategy."""
    return {
        "schema_version": "ranking_v2",
        "top_strategy": None,
        "ranked": [
            {
                "strategy_id": "strat_a",
                "governance_state": "frozen",
                "promotion_state": "frozen",
                "freeze_recommended": True,
                "rank_score": 0.2,
            },
            {
                "strategy_id": "strat_b",
                "governance_state": "retired",
                "promotion_state": "retired",
                "freeze_recommended": False,
                "rank_score": 0.1,
            },
        ],
    }


def _make_ranking_with_active() -> dict:
    """Strategy ranking with at least one active strategy."""
    return {
        "schema_version": "ranking_v2",
        "top_strategy": {
            "strategy_id": "strat_a",
            "governance_state": "paper_active",
            "promotion_state": "paper_active",
        },
        "ranked": [
            {
                "strategy_id": "strat_a",
                "governance_state": "paper_active",
                "promotion_state": "paper_active",
                "freeze_recommended": False,
                "rank_score": 0.5,
            },
        ],
    }


def _make_ranking_operational_deadlock(hours_since_trade: float = 72) -> dict:
    """Non-frozen strategies exist but no trades for hours_since_trade hours, no top_strategy."""
    last_trade = (datetime.now(timezone.utc) - timedelta(hours=hours_since_trade)).isoformat()
    return {
        "schema_version": "ranking_v2",
        "top_strategy": None,
        "ranked": [
            {
                "strategy_id": "strat_active_but_stuck",
                "governance_state": "paper_active",
                "promotion_state": "paper_active",
                "freeze_recommended": False,
                "rank_score": 0.3,
                "last_trade_utc": last_trade,
            },
            {
                "strategy_id": "strat_candidate_no_signals",
                "governance_state": "paper_candidate",
                "promotion_state": "paper_candidate",
                "freeze_recommended": False,
                "rank_score": 0.1,
                "last_trade_utc": None,
            },
        ],
    }


def _make_base_gate(blockers=None, actions=None) -> dict:
    return {
        "schema_version": "utility_u_promotion_gate_v2",
        "updated_utc": _utc_now(),
        "source_snapshot_path": "test",
        "u_proxy_score": -0.18,
        "verdict": "no_promote",
        "allow_promote": False,
        "blockers": blockers or ["u_proxy_non_positive"],
        "required_next_actions": actions or ["improve_expectancy_or_reduce_penalties"],
    }


def _make_base_snapshot(top_strategy=None) -> dict:
    return {
        "schema_version": "utility_u_proxy_snapshot_v2",
        "updated_utc": _utc_now(),
        "u_proxy_score": -0.18,
        "current_phase": "paper_validation",
        "strategy_context": {
            "top_strategy": top_strategy,
        },
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_scorecard_paths(monkeypatch, tmp_path):
    """Redirect strategy_scorecard module-level paths to tmp_path."""
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")


# ===========================================================================
# 1. force_unfreeze_best_frozen — basic unfreeze
# ===========================================================================

class TestForceUnfreezeBestFrozen:
    def test_unfreezes_best_frozen_strategy(self):
        """Should unfreeze the frozen strategy with highest potential."""
        scorecards = {
            "strat_a": _make_frozen_card("strat_a", expectancy=-0.25, entries_resolved=11),
            "strat_b": _make_frozen_card("strat_b", expectancy=-0.10, entries_resolved=5),
        }
        result = force_unfreeze_best_frozen(scorecards)
        # strat_b has fewer resolved + better expectancy → preferred
        assert result == "strat_b"
        assert scorecards["strat_b"]["governance_state"] == "paper_active"
        assert scorecards["strat_b"]["promotion_state"] == "paper_active"
        assert scorecards["strat_b"]["freeze_recommended"] is False
        assert "deadlock_unfreeze_utc" in scorecards["strat_b"]
        # strat_a should remain frozen
        assert scorecards["strat_a"]["governance_state"] == "frozen"

    def test_skips_archived_refuted(self):
        """Strategies with archive_state=archived_refuted should be skipped."""
        scorecards = {
            "strat_a": _make_frozen_card(
                "strat_a", expectancy=-0.10, entries_resolved=5,
                archive_state="archived_refuted",
            ),
            "strat_b": _make_frozen_card("strat_b", expectancy=-0.30, entries_resolved=44),
        }
        result = force_unfreeze_best_frozen(scorecards)
        # strat_a is archived → skipped, so strat_b gets unfrozen
        assert result == "strat_b"

    def test_skips_retired(self):
        """Retired strategies should be skipped."""
        scorecards = {
            "strat_a": _make_frozen_card("strat_a"),
        }
        scorecards["strat_a"]["governance_state"] = "retired"
        result = force_unfreeze_best_frozen(scorecards)
        assert result is None

    def test_returns_none_when_no_frozen(self):
        """Returns None when no frozen strategies exist."""
        scorecards = {
            "strat_a": _blank_scorecard(_make_strategy("strat_a")),
        }
        scorecards["strat_a"]["governance_state"] = "paper_active"
        result = force_unfreeze_best_frozen(scorecards)
        assert result is None

    def test_prefers_small_sample(self):
        """Strategies with fewer resolved trades get a bonus (+0.5)."""
        scorecards = {
            # Higher expectancy but large sample
            "strat_a": _make_frozen_card("strat_a", expectancy=-0.05, entries_resolved=30),
            # Lower expectancy but tiny sample (< 15) → gets +0.5 bonus
            "strat_b": _make_frozen_card("strat_b", expectancy=-0.20, entries_resolved=5),
        }
        result = force_unfreeze_best_frozen(scorecards)
        # strat_b: -0.20 + 0.5 = 0.30 score
        # strat_a: -0.05 + 0 = -0.05 score
        assert result == "strat_b"

    def test_clears_freeze_fields(self):
        """Should remove freeze_reason and freeze_utc."""
        scorecards = {
            "strat_a": _make_frozen_card(
                "strat_a",
                freeze_reason="drawdown_limit_breached",
                freeze_utc="2026-03-20T00:00:00Z",
            ),
        }
        force_unfreeze_best_frozen(scorecards)
        assert "freeze_reason" not in scorecards["strat_a"]
        assert "freeze_utc" not in scorecards["strat_a"]


# ===========================================================================
# 2. Deadlock detection in utility.py
# ===========================================================================

class TestDeadlockDetection:
    @pytest.fixture(autouse=True)
    def _setup_utility(self, monkeypatch, tmp_path):
        """Redirect utility module paths for deadlock detection tests."""
        import brain_v9.brain.utility as util_mod
        import brain_v9.brain.meta_governance as meta_gov_mod
        state = tmp_path / "tmp_agent" / "state"
        metrics = tmp_path / "60_METRICS"
        state.mkdir(parents=True, exist_ok=True)
        metrics.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(util_mod, "STATE_PATH", state)
        monkeypatch.setattr(util_mod, "METRICS_PATH", metrics)
        monkeypatch.setattr(util_mod, "COMPARISON_RUNS_PATH", state / "comparison_runs")

        # P-OP26: Redirect meta-governance paths so tests don't read real
        # control-layer state from the filesystem.
        control_layer_path = state / "control_layer_status.json"
        _write_json(control_layer_path, {
            "mode": "ACTIVE", "reason": "test", "execution_allowed": True,
        })
        monkeypatch.setattr(meta_gov_mod, "CONTROL_LAYER_STATUS_PATH", control_layer_path)
        monkeypatch.setattr(meta_gov_mod, "META_GOVERNANCE_STATUS_PATH", state / "meta_governance_status_latest.json")
        monkeypatch.setattr(meta_gov_mod, "AUTONOMY_NEXT_ACTIONS_PATH", state / "autonomy_next_actions.json")
        monkeypatch.setattr(meta_gov_mod, "AUTONOMY_CYCLE_LATEST_PATH", state / "next_level_cycle_status_latest.json")
        monkeypatch.setattr(meta_gov_mod, "EDGE_VALIDATION_PATH", state / "strategy_engine" / "edge_validation_latest.json")
        monkeypatch.setattr(meta_gov_mod, "STATE_PATH", state)

        files = {
            "u_latest": state / "utility_u_latest.json",
            "u_gate": state / "utility_u_promotion_gate_latest.json",
            "autonomy_next_actions": state / "autonomy_next_actions.json",
            "cycle": state / "next_level_cycle_status_latest.json",
            "roadmap": state / "roadmap.json",
            "capital": metrics / "capital_state.json",
            "financial_mission": state / "financial_mission.json",
            "scorecard": state / "rooms" / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json",
            "promotion_policy": state / "governed_promotion_policy.json",
            "strategy_ranking": state / "strategy_engine" / "strategy_ranking_latest.json",
            "strategy_ranking_v2": state / "strategy_engine" / "strategy_ranking_v2_latest.json",
            "expectancy_snapshot": state / "strategy_engine" / "expectancy_snapshot_latest.json",
            "meta_improvement": state / "meta_improvement_status_latest.json",
        }
        monkeypatch.setattr(util_mod, "FILES", files)

        # Seed required state files
        _write_json(files["financial_mission"], {"objective_primary": "test", "utility_u": {"name": "U_test"}})
        _write_json(files["scorecard"], {"seed_metrics": {"total_resolved": 20, "total_wins": 10, "total_losses": 10}})
        _write_json(files["capital"], {"current_cash": 10000, "committed_cash": 0, "max_drawdown_pct": 0.05, "status": "paper"})
        _write_json(files["cycle"], {"current_phase": "paper_validation"})
        _write_json(files["roadmap"], {"current_phase": "paper_validation"})
        _write_json(files["promotion_policy"], {"version": "v1"})
        _write_json(files["expectancy_snapshot"], {})

        self._state = state
        self._files = files
        self._util_mod = util_mod

    def test_deadlock_detected_all_frozen(self):
        """When all ranked strategies are frozen and top_strategy is null, deadlock is detected."""
        _write_json(self._files["strategy_ranking_v2"], _make_ranking_all_frozen())
        _write_json(self._files["strategy_ranking"], _make_ranking_all_frozen())

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        assert "system_deadlock" in next_actions["blockers"]
        assert next_actions["top_action"] == "break_system_deadlock"
        assert "break_system_deadlock" in next_actions["recommended_actions"]

    def test_no_deadlock_with_active_strategies(self):
        """When active strategies exist, no deadlock is detected."""
        _write_json(self._files["strategy_ranking_v2"], _make_ranking_with_active())
        _write_json(self._files["strategy_ranking"], _make_ranking_with_active())

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        assert "system_deadlock" not in next_actions["blockers"]
        assert next_actions["top_action"] != "break_system_deadlock"

    def test_expand_signal_pipeline_added_when_no_top_strategy(self):
        """When no top_strategy in snapshot, expand_signal_pipeline should be recommended."""
        # Ranking with NO top_strategy and empty ranked list
        # (this makes snapshot.strategy_context.top_strategy = None)
        ranking = {
            "schema_version": "ranking_v2",
            "top_strategy": None,
            "ranked": [],
        }
        _write_json(self._files["strategy_ranking_v2"], ranking)
        _write_json(self._files["strategy_ranking"], ranking)

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        # No ranked strategies at all → no deadlock (empty), but also no top_strategy
        # The signal pipeline action should be recommended
        assert "improve_signal_capture_and_context_window" in next_actions["recommended_actions"]

    def test_deadlock_writes_to_file(self):
        """Deadlock state should be persisted to autonomy_next_actions.json."""
        _write_json(self._files["strategy_ranking_v2"], _make_ranking_all_frozen())
        _write_json(self._files["strategy_ranking"], _make_ranking_all_frozen())

        self._util_mod.write_utility_snapshots()

        saved = json.loads(self._files["autonomy_next_actions"].read_text(encoding="utf-8"))
        assert "system_deadlock" in saved["blockers"]
        assert saved["top_action"] == "break_system_deadlock"

    def test_operational_deadlock_no_trades_72h(self):
        """Operational deadlock: non-frozen strategies but no trades for 72h, no top_strategy."""
        ranking = _make_ranking_operational_deadlock(hours_since_trade=72)
        _write_json(self._files["strategy_ranking_v2"], ranking)
        _write_json(self._files["strategy_ranking"], ranking)

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        assert "system_deadlock" in next_actions["blockers"]
        assert next_actions["top_action"] == "break_system_deadlock"
        assert "break_system_deadlock" in next_actions["recommended_actions"]

    def test_no_operational_deadlock_recent_trade(self):
        """No deadlock when last trade was only 12 hours ago (< 48h threshold)."""
        ranking = _make_ranking_operational_deadlock(hours_since_trade=12)
        _write_json(self._files["strategy_ranking_v2"], ranking)
        _write_json(self._files["strategy_ranking"], ranking)

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        assert "system_deadlock" not in next_actions["blockers"]
        assert next_actions["top_action"] != "break_system_deadlock"

    def test_no_operational_deadlock_when_top_strategy_exists(self):
        """Even with old trades, if top_strategy exists, no operational deadlock."""
        ranking = _make_ranking_operational_deadlock(hours_since_trade=100)
        ranking["top_strategy"] = {"strategy_id": "strat_active_but_stuck"}
        _write_json(self._files["strategy_ranking_v2"], ranking)
        _write_json(self._files["strategy_ranking"], ranking)

        result = self._util_mod.write_utility_snapshots()
        next_actions = result["next_actions"]
        assert "system_deadlock" not in next_actions["blockers"]


# ===========================================================================
# 3. generate_strategy_variants() in knowledge_base.py
# ===========================================================================

class TestGenerateStrategyVariants:
    @pytest.fixture(autouse=True)
    def _setup_kb(self, monkeypatch, tmp_path):
        import brain_v9.research.knowledge_base as kb
        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(kb, "KB_PATH", kb_path)
        monkeypatch.setattr(kb, "KNOWLEDGE_PATH", kb_path / "knowledge_base.json")
        monkeypatch.setattr(kb, "INDICATORS_PATH", kb_path / "indicator_registry.json")
        monkeypatch.setattr(kb, "STRATEGIES_PATH", kb_path / "strategy_specs.json")
        monkeypatch.setattr(kb, "HYPOTHESES_PATH", kb_path / "hypothesis_queue.json")
        self._kb = kb
        self._kb_path = kb_path

    def _seed_strategies(self, strategies: list):
        _write_json(self._kb.STRATEGIES_PATH, {
            "schema_version": "strategy_specs_v1",
            "updated_utc": _utc_now(),
            "strategies": strategies,
        })

    def _seed_hypotheses(self, hypotheses: list | None = None):
        _write_json(self._kb.HYPOTHESES_PATH, {
            "schema_version": "hypothesis_queue_v1",
            "updated_utc": _utc_now(),
            "top_priority": None,
            "hypotheses": hypotheses or [],
        })

    def test_generates_variants_from_frozen(self, monkeypatch):
        """Should create new strategy variants from frozen strategies."""
        strategies = [
            {
                "strategy_id": "ibkr_breakout_compression_v1",
                "venue_preference": ["ibkr"],
                "asset_classes": ["stocks"],
                "family": "breakout",
                "summary": "test breakout",
                "core_indicators": ["atr_14"],
                "entry_logic": [],
                "invalidators": [],
                "paper_only": True,
                "universe": ["SPY"],
            },
        ]
        self._seed_strategies(strategies)
        self._seed_hypotheses()

        # Mock scorecards to show strategy as frozen
        mock_scorecards = {
            "scorecards": {
                "ibkr_breakout_compression_v1": {
                    "governance_state": "frozen",
                    "entries_resolved": 44,
                },
            },
        }
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: mock_scorecards,
        )

        from brain_v9.research.knowledge_base import generate_strategy_variants
        result = generate_strategy_variants(max_variants=1)

        assert len(result) == 1
        assert "mean_reversion" in result[0]  # breakout → mean_reversion

        # Verify it was written to disk
        saved = json.loads(self._kb.STRATEGIES_PATH.read_text(encoding="utf-8"))
        ids = [s["strategy_id"] for s in saved["strategies"]]
        assert result[0] in ids
        new_strat = next(s for s in saved["strategies"] if s["strategy_id"] == result[0])
        assert new_strat["family"] == "mean_reversion"
        assert new_strat["auto_generated"] is True
        assert new_strat["source_strategy"] == "ibkr_breakout_compression_v1"

        # Verify hypothesis was created
        hyp_data = json.loads(self._kb.HYPOTHESES_PATH.read_text(encoding="utf-8"))
        hyp_ids = [h["id"] for h in hyp_data["hypotheses"]]
        assert f"h_{result[0]}" in hyp_ids

    def test_no_variants_when_nothing_frozen(self, monkeypatch):
        """Should return empty list when no frozen strategies."""
        strategies = [
            {
                "strategy_id": "strat_a",
                "venue_preference": ["ibkr"],
                "asset_classes": ["stocks"],
                "family": "trend_following",
                "summary": "test",
                "core_indicators": ["ema_20_50"],
                "entry_logic": [],
                "invalidators": [],
                "paper_only": True,
            },
        ]
        self._seed_strategies(strategies)
        self._seed_hypotheses()

        mock_scorecards = {
            "scorecards": {
                "strat_a": {
                    "governance_state": "paper_active",
                    "entries_resolved": 15,
                },
            },
        }
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: mock_scorecards,
        )

        from brain_v9.research.knowledge_base import generate_strategy_variants
        result = generate_strategy_variants()
        assert result == []

    def test_avoids_duplicate_ids(self, monkeypatch):
        """Should not create a variant if the ID already exists."""
        strategies = [
            {
                "strategy_id": "po_breakout_v1",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "breakout",
                "summary": "test",
                "core_indicators": ["bollinger_20_2"],
                "entry_logic": [],
                "invalidators": [],
                "paper_only": True,
                "universe": ["AUDNZD_otc"],
            },
            {
                # This ID would collide with the generated variant
                "strategy_id": "po_mean_reversion_v2_auto",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "mean_reversion",
                "summary": "existing",
                "core_indicators": ["rsi_14"],
                "entry_logic": [],
                "invalidators": [],
                "paper_only": True,
            },
        ]
        self._seed_strategies(strategies)
        self._seed_hypotheses()

        mock_scorecards = {
            "scorecards": {
                "po_breakout_v1": {
                    "governance_state": "frozen",
                    "entries_resolved": 20,
                },
                "po_mean_reversion_v2_auto": {
                    "governance_state": "paper_active",
                    "entries_resolved": 0,
                },
            },
        }
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: mock_scorecards,
        )

        from brain_v9.research.knowledge_base import generate_strategy_variants
        result = generate_strategy_variants(max_variants=1)
        # Should use v3_auto or higher since v2_auto exists
        assert len(result) == 1
        assert "po_mean_reversion_v2_auto" not in result
        assert "v3_auto" in result[0] or "v4_auto" in result[0]

    def test_uses_different_symbols(self, monkeypatch):
        """Generated variant should use different symbols from source."""
        strategies = [
            {
                "strategy_id": "po_reversion_v1",
                "venue_preference": ["pocket_option"],
                "asset_classes": ["otc_binary"],
                "family": "mean_reversion",
                "summary": "test",
                "core_indicators": ["rsi_14"],
                "entry_logic": [],
                "invalidators": [],
                "paper_only": True,
                "universe": ["AUDNZD_otc"],
            },
        ]
        self._seed_strategies(strategies)
        self._seed_hypotheses()

        mock_scorecards = {
            "scorecards": {
                "po_reversion_v1": {
                    "governance_state": "frozen",
                    "entries_resolved": 30,
                },
            },
        }
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: mock_scorecards,
        )

        from brain_v9.research.knowledge_base import generate_strategy_variants
        result = generate_strategy_variants(max_variants=1)
        assert len(result) == 1

        saved = json.loads(self._kb.STRATEGIES_PATH.read_text(encoding="utf-8"))
        new_strat = next(s for s in saved["strategies"] if s["strategy_id"] == result[0])
        # Should NOT have AUDNZD_otc (source symbol)
        assert "AUDNZD_otc" not in new_strat.get("universe", [])


# ===========================================================================
# 4. break_system_deadlock in ACTION_MAP
# ===========================================================================

class TestBreakSystemDeadlockWiring:
    def test_action_map_contains_break_system_deadlock(self):
        """break_system_deadlock should be in ACTION_MAP."""
        from brain_v9.autonomy.action_executor import ACTION_MAP
        assert "break_system_deadlock" in ACTION_MAP

    def test_manager_trading_actions_contains_deadlock(self):
        """break_system_deadlock should be in _TRADING_ACTIONS."""
        from brain_v9.autonomy.manager import AutonomyManager
        assert "break_system_deadlock" in AutonomyManager._TRADING_ACTIONS


# ===========================================================================
# 5. break_system_deadlock composite action
# ===========================================================================

class TestBreakSystemDeadlockAction:
    @pytest.fixture(autouse=True)
    def _setup_ae(self, monkeypatch, tmp_path):
        """Redirect action_executor paths to tmp_path."""
        import brain_v9.autonomy.action_executor as ae
        state = tmp_path / "tmp_agent" / "state"
        rooms = state / "rooms"
        engine = state / "strategy_engine"
        for d in [
            state, rooms, engine,
            state / "autonomy_action_jobs",
            rooms / "brain_binary_paper_pb05_journal",
            rooms / "brain_binary_paper_pb04_demo_execution",
            rooms / "brain_financial_ingestion_fi04_structured_api",
            state / "trading_execution_checks",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(ae, "STATE_PATH", state)
        monkeypatch.setattr(ae, "ROOMS_PATH", rooms)
        monkeypatch.setattr(ae, "JOBS_PATH", state / "autonomy_action_jobs")
        monkeypatch.setattr(ae, "JOBS_LEDGER", state / "autonomy_action_ledger.json")
        monkeypatch.setattr(ae, "NEXT_ACTIONS_PATH", state / "autonomy_next_actions.json")
        monkeypatch.setattr(ae, "SCORECARD_PATH", rooms / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json")
        monkeypatch.setattr(ae, "PO_BRIDGE_ARTIFACT", rooms / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json")
        monkeypatch.setattr(ae, "PO_DUE_DILIGENCE_PATH", rooms / "brain_binary_paper_pb01_venue_verification" / "pocketoption_due_diligence.json")
        monkeypatch.setattr(ae, "IBKR_LANE_PATH", rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_readonly_lane.json")
        monkeypatch.setattr(ae, "IBKR_PROBE_PATH", rooms / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json")
        monkeypatch.setattr(ae, "IBKR_ORDER_CHECK_PATH", state / "trading_execution_checks" / "ibkr_paper_order_check_latest.json")
        monkeypatch.setattr(ae, "TRADING_POLICY_PATH", state / "trading_autonomy_policy.json")

        self._ae = ae
        self._state = state

    @pytest.mark.asyncio
    async def test_break_deadlock_calls_all_steps(self, monkeypatch):
        """break_system_deadlock should call unfreeze, generate variants, expand pipeline."""
        from brain_v9.autonomy.action_executor import break_system_deadlock

        # Mock _ensure_trading_policy (needs real files otherwise)
        monkeypatch.setattr(self._ae, "_ensure_trading_policy", lambda: None)

        # Mock refresh_strategy_engine
        monkeypatch.setattr(
            "brain_v9.autonomy.action_executor.refresh_strategy_engine",
            lambda: None,
        )

        # Mock read_scorecards → return frozen scorecards
        mock_scorecards_payload = {
            "scorecards": {
                "strat_a": _make_frozen_card("strat_a", expectancy=-0.10, entries_resolved=5),
            },
            "updated_utc": _utc_now(),
        }
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: mock_scorecards_payload,
        )

        # Mock write_json used inside break_system_deadlock
        written = {}
        original_wj = self._ae.write_json
        def capture_wj(path, data):
            written[str(path)] = data
            return original_wj(path, data)
        monkeypatch.setattr("brain_v9.core.state_io.write_json", capture_wj)

        # Mock generate_strategy_variants
        monkeypatch.setattr(
            "brain_v9.research.knowledge_base.generate_strategy_variants",
            lambda max_variants=2: ["ibkr_mean_reversion_v2_auto"],
        )

        # Mock expand_signal_pipeline
        mock_expand = AsyncMock(return_value={
            "success": True,
            "viable_signal_found": False,
            "trade_executed": False,
        })
        monkeypatch.setattr(self._ae, "expand_signal_pipeline", mock_expand)

        # Mock skip counter
        monkeypatch.setattr("brain_v9.util.get_consecutive_skips", lambda: 5)
        monkeypatch.setattr("brain_v9.util.reset_skips_counter", lambda: None)

        result = await break_system_deadlock()

        assert result["success"] is True
        assert result["action_name"] == "break_system_deadlock"
        assert result["unfrozen_strategy"] == "strat_a"
        assert result["new_variants"] == ["ibkr_mean_reversion_v2_auto"]
        assert result["skips_reset"] is True
        assert "force_unfreeze_best_frozen" in result["steps_completed"]
        assert "generate_strategy_variants" in result["steps_completed"]
        assert "expand_signal_pipeline" in result["steps_completed"]
        mock_expand.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_break_deadlock_handles_no_frozen(self, monkeypatch):
        """Should succeed even when no frozen strategies exist."""
        from brain_v9.autonomy.action_executor import break_system_deadlock

        monkeypatch.setattr(self._ae, "_ensure_trading_policy", lambda: None)
        monkeypatch.setattr(
            "brain_v9.autonomy.action_executor.refresh_strategy_engine",
            lambda: None,
        )
        monkeypatch.setattr(
            "brain_v9.trading.strategy_scorecard.read_scorecards",
            lambda: {"scorecards": {}, "updated_utc": _utc_now()},
        )
        monkeypatch.setattr(
            "brain_v9.research.knowledge_base.generate_strategy_variants",
            lambda max_variants=2: [],
        )
        mock_expand = AsyncMock(return_value={
            "success": True,
            "viable_signal_found": False,
            "trade_executed": False,
        })
        monkeypatch.setattr(self._ae, "expand_signal_pipeline", mock_expand)
        monkeypatch.setattr("brain_v9.util.get_consecutive_skips", lambda: 0)

        result = await break_system_deadlock()

        assert result["success"] is True
        assert result["unfrozen_strategy"] is None
        assert result["new_variants"] == []
        assert result["skips_reset"] is False


# ===========================================================================
# 6. Manager dispatch — break_system_deadlock dispatched as trading action
# ===========================================================================

class TestManagerDeadlockDispatch:
    @pytest.mark.asyncio
    async def test_deadlock_action_dispatched(self, monkeypatch):
        """Manager should dispatch break_system_deadlock when it's in recommended_actions."""
        from brain_v9.autonomy.manager import AutonomyManager, execute_action

        # P-OP26: mock control layer so dispatch is not blocked by filesystem state
        monkeypatch.setattr(
            "brain_v9.autonomy.manager.get_control_layer_status_latest",
            lambda: {"mode": "ACTIVE", "reason": "test", "execution_allowed": True},
        )

        mgr = AutonomyManager()
        gate = {
            "blockers": ["system_deadlock"],
            "required_next_actions": ["break_system_deadlock"],
        }
        snapshot = {"u_proxy_score": -0.18}

        mock_execute = AsyncMock(return_value={"status": "completed"})
        monkeypatch.setattr("brain_v9.autonomy.manager.execute_action", mock_execute)

        await mgr._dispatch_actions(gate, snapshot)
        mock_execute.assert_awaited_once_with("break_system_deadlock")
