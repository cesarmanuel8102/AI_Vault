"""P5-08: Tests for strategy spec cleanup — dedup, key normalization,
orphan symbol pruning, and orphan hypothesis pruning.

Covers:
1. _normalize_strategy_specs() — dedup guard skips duplicate strategy_ids
2. _normalize_strategy_specs() — strategies without id are skipped
3. _strategy_seed() — all strategies use 'strategy_id' (not 'id')
4. ensure_scorecards() — prunes symbol scorecards for symbols not in universe
5. ensure_scorecards() — keeps symbol scorecards if strategy has no universe
6. ensure_scorecards() — prunes context scorecards for orphan symbols
7. prune_orphan_hypotheses() — removes hypotheses with non-existent strategy_id
8. prune_orphan_hypotheses() — keeps valid hypotheses untouched
9. prune_orphan_hypotheses() — updates top_priority when pruned
10. ensure_research_foundation() — wires prune_orphan_hypotheses
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_strategy(
    strategy_id: str = "strat_01",
    venue: str = "pocket_option",
    universe: List[str] | None = None,
) -> Dict:
    return {
        "strategy_id": strategy_id,
        "family": "test_family",
        "venue": venue,
        "status": "paper_candidate",
        "universe": universe or ["EURUSD_otc"],
        "timeframes": ["1m"],
        "setup_variants": ["base"],
        "linked_hypotheses": [],
        "success_criteria": {
            "min_resolved_trades": 10,
            "min_expectancy": 0.05,
            "min_win_rate": 0.45,
        },
    }


# ---------------------------------------------------------------------------
# 1. Seed key consistency
# ---------------------------------------------------------------------------

class TestSeedKeyConsistency:
    """P5-08b: All seed strategies use 'strategy_id', not 'id'."""

    def test_strategy_seeds_use_strategy_id_key(self):
        import brain_v9.research.knowledge_base as kb
        seed = kb._strategy_seed()
        for strat in seed["strategies"]:
            assert "strategy_id" in strat, f"Strategy missing 'strategy_id': {strat}"
            assert "id" not in strat, f"Strategy still uses 'id': {strat}"

    def test_strategy_seed_ids_are_unique(self):
        import brain_v9.research.knowledge_base as kb
        seed = kb._strategy_seed()
        ids = [s["strategy_id"] for s in seed["strategies"]]
        assert len(ids) == len(set(ids)), f"Duplicate strategy_ids in seed: {ids}"

    def test_hypothesis_strategy_ids_match_seeds(self):
        import brain_v9.research.knowledge_base as kb
        strat_seed = kb._strategy_seed()
        hyp_seed = kb._hypothesis_seed()
        valid_ids = {s["strategy_id"] for s in strat_seed["strategies"]}
        for hyp in hyp_seed["hypotheses"]:
            assert hyp["strategy_id"] in valid_ids, (
                f"Hypothesis {hyp['id']} references non-existent strategy {hyp['strategy_id']}"
            )


# ---------------------------------------------------------------------------
# 2. Dedup guard in _normalize_strategy_specs()
# ---------------------------------------------------------------------------

class TestNormalizeDedup:
    """P5-08a: _normalize_strategy_specs() deduplicates by strategy_id."""

    def test_duplicate_strategies_kept_first_only(self, monkeypatch, tmp_path):
        import brain_v9.trading.strategy_engine as se

        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(se, "STATE_PATH", tmp_path / "tmp_agent" / "state")
        monkeypatch.setattr(se, "PAPER_ONLY", True)
        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)

        # Two strategies with the same id but different families
        mock_specs = {
            "strategies": [
                {"strategy_id": "dup_strat", "venue": "ibkr", "family": "trend_following", "summary": "first"},
                {"strategy_id": "dup_strat", "venue": "ibkr", "family": "mean_reversion", "summary": "second"},
                {"strategy_id": "unique_strat", "venue": "ibkr", "family": "breakout", "summary": "unique"},
            ],
        }
        monkeypatch.setattr(se, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(se, "read_hypothesis_queue", lambda: {"hypotheses": []})

        result = se._normalize_strategy_specs()
        strats = result["strategies"]
        ids = [s["strategy_id"] for s in strats]
        assert ids.count("dup_strat") == 1, "Duplicate should be deduplicated"
        assert ids.count("unique_strat") == 1
        # First occurrence wins
        dup = next(s for s in strats if s["strategy_id"] == "dup_strat")
        assert dup["family"] == "trend_following"

    def test_strategies_without_id_are_skipped(self, monkeypatch, tmp_path):
        import brain_v9.trading.strategy_engine as se

        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(se, "STATE_PATH", tmp_path / "tmp_agent" / "state")
        monkeypatch.setattr(se, "PAPER_ONLY", True)
        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)

        mock_specs = {
            "strategies": [
                {"venue": "ibkr", "family": "orphan", "summary": "no id"},
                {"strategy_id": "valid_strat", "venue": "ibkr", "family": "trend", "summary": "has id"},
            ],
        }
        monkeypatch.setattr(se, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(se, "read_hypothesis_queue", lambda: {"hypotheses": []})

        result = se._normalize_strategy_specs()
        ids = [s["strategy_id"] for s in result["strategies"]]
        assert "valid_strat" in ids
        assert len(ids) == 1, "Strategy without id should be skipped"

    def test_old_id_field_still_accepted(self, monkeypatch, tmp_path):
        """Backward compat: strategies using 'id' instead of 'strategy_id'."""
        import brain_v9.trading.strategy_engine as se

        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(se, "STATE_PATH", tmp_path / "tmp_agent" / "state")
        monkeypatch.setattr(se, "PAPER_ONLY", True)
        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)

        mock_specs = {
            "strategies": [
                {"id": "legacy_strat", "venue": "pocket_option", "family": "mean_reversion", "summary": "old format"},
            ],
        }
        monkeypatch.setattr(se, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(se, "read_hypothesis_queue", lambda: {"hypotheses": []})

        result = se._normalize_strategy_specs()
        assert result["strategies"][0]["strategy_id"] == "legacy_strat"


# ---------------------------------------------------------------------------
# 3. Orphan-symbol scorecard pruning
# ---------------------------------------------------------------------------

class TestOrphanSymbolPruning:
    """P5-08c: ensure_scorecards() prunes symbol/context keys for symbols
    not in the strategy's current universe."""

    def test_prunes_symbol_scorecard_for_removed_symbol(self, monkeypatch, tmp_path):
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_a", "pocket_option", ["EURUSD_otc"])

        # Pre-populate with a scorecard for a symbol NOT in universe
        orphan_key = "pocket_option::strat_a::GBPUSD_otc"
        valid_key = "pocket_option::strat_a::EURUSD_otc"
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {"strat_a": sc._blank_scorecard(strategy)},
            "symbol_scorecards": {
                orphan_key: {"wins": 5, "losses": 3},
                valid_key: {"wins": 10, "losses": 2},
            },
            "context_scorecards": {},
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strategy], prune_stale=True)

        assert orphan_key not in result["symbol_scorecards"], "Orphan symbol key should be pruned"
        assert valid_key in result["symbol_scorecards"], "Valid symbol key should be kept"

    def test_prunes_context_scorecard_for_removed_symbol(self, monkeypatch, tmp_path):
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_b", "ibkr", ["SPY"])

        orphan_ctx = "ibkr::strat_b::QQQ::5m::base"
        valid_ctx = "ibkr::strat_b::SPY::1m::base"
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {"strat_b": sc._blank_scorecard(strategy)},
            "symbol_scorecards": {},
            "context_scorecards": {
                orphan_ctx: {"wins": 1},
                valid_ctx: {"wins": 2},
            },
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strategy], prune_stale=True)

        assert orphan_ctx not in result["context_scorecards"], "Orphan context key should be pruned"
        assert valid_ctx in result["context_scorecards"], "Valid context key should be kept"

    def test_keeps_symbols_when_no_universe_declared(self, monkeypatch, tmp_path):
        """If a strategy has no universe, keep all symbols by prefix."""
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_c", "ibkr")
        strategy["universe"] = []  # empty universe

        key = "ibkr::strat_c::AAPL"
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {"strat_c": sc._blank_scorecard(strategy)},
            "symbol_scorecards": {key: {"wins": 3}},
            "context_scorecards": {},
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strategy], prune_stale=True)

        assert key in result["symbol_scorecards"], "Should keep symbols when universe is empty"

    def test_prunes_entirely_unknown_strategy_symbols(self, monkeypatch, tmp_path):
        """Symbol scorecards for a completely unknown strategy are pruned."""
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_d", "ibkr", ["SPY"])

        # Pre-populate with a scorecard for a totally unknown strategy
        unknown_key = "ibkr::deleted_strat::SPY"
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {
                "strat_d": sc._blank_scorecard(strategy),
                "deleted_strat": {"wins": 0},
            },
            "symbol_scorecards": {
                unknown_key: {"wins": 0},
                "ibkr::strat_d::SPY": {"wins": 5},
            },
            "context_scorecards": {},
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strategy], prune_stale=True)

        assert unknown_key not in result["symbol_scorecards"]
        assert "deleted_strat" not in result["scorecards"]

    def test_multiple_strategies_mixed_pruning(self, monkeypatch, tmp_path):
        """Multiple strategies: each prunes only its own orphan symbols."""
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strat_a = _make_strategy("strat_a", "ibkr", ["SPY"])
        strat_b = _make_strategy("strat_b", "pocket_option", ["EURUSD_otc"])

        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {
                "strat_a": sc._blank_scorecard(strat_a),
                "strat_b": sc._blank_scorecard(strat_b),
            },
            "symbol_scorecards": {
                "ibkr::strat_a::SPY": {"wins": 5},          # valid
                "ibkr::strat_a::QQQ": {"wins": 2},          # orphan
                "pocket_option::strat_b::EURUSD_otc": {"wins": 3},  # valid
                "pocket_option::strat_b::GBPUSD_otc": {"wins": 1},  # orphan
            },
            "context_scorecards": {},
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strat_a, strat_b], prune_stale=True)
        sym = result["symbol_scorecards"]

        assert "ibkr::strat_a::SPY" in sym
        assert "ibkr::strat_a::QQQ" not in sym
        assert "pocket_option::strat_b::EURUSD_otc" in sym
        assert "pocket_option::strat_b::GBPUSD_otc" not in sym

    def test_rebuilds_aggregate_from_symbol_scorecards(self, monkeypatch, tmp_path):
        """Aggregate strategy counters should be reconciled from ledger entries."""
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_e", "ibkr", ["SPY", "AAPL"])

        # Seed the execution ledger with 5 trades matching the expected totals
        ledger = {
            "entries": [
                {"strategy_id": "strat_e", "venue": "ibkr", "symbol": "SPY", "timeframe": "1m", "setup_variant": "base",
                 "result": "win", "profit": 6.0, "resolved": True, "resolved_utc": "2026-03-27T11:50:00Z"},
                {"strategy_id": "strat_e", "venue": "ibkr", "symbol": "SPY", "timeframe": "1m", "setup_variant": "base",
                 "result": "loss", "profit": -10.0, "resolved": True, "resolved_utc": "2026-03-27T11:55:00Z"},
                {"strategy_id": "strat_e", "venue": "ibkr", "symbol": "SPY", "timeframe": "1m", "setup_variant": "base",
                 "result": "loss", "profit": -10.0, "resolved": True, "resolved_utc": "2026-03-27T12:00:00Z"},
                {"strategy_id": "strat_e", "venue": "ibkr", "symbol": "AAPL", "timeframe": "1m", "setup_variant": "base",
                 "result": "win", "profit": 8.0, "resolved": True, "resolved_utc": "2026-03-27T12:03:00Z"},
                {"strategy_id": "strat_e", "venue": "ibkr", "symbol": "AAPL", "timeframe": "1m", "setup_variant": "base",
                 "result": "loss", "profit": -6.0, "resolved": True, "resolved_utc": "2026-03-27T12:05:00Z"},
            ]
        }
        sc.write_json(tmp_path / "signal_paper_execution_ledger.json", ledger)
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {
                "strat_e": {
                    **sc._blank_scorecard(strategy),
                    "entries_taken": 0,
                    "entries_resolved": 0,
                    "wins": 0,
                    "losses": 0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "net_pnl": 0.0,
                },
            },
            "symbol_scorecards": {
                "ibkr::strat_e::SPY": {
                    **sc._blank_symbol_scorecard(strategy, "SPY"),
                    "entries_taken": 3,
                    "entries_resolved": 3,
                    "wins": 1,
                    "losses": 2,
                    "gross_profit": 6.0,
                    "gross_loss": 20.0,
                    "net_pnl": -14.0,
                    "last_trade_utc": "2026-03-27T12:00:00Z",
                    "recent_5_outcomes": [
                        {"timestamp": "2026-03-27T12:00:00Z", "result": "loss", "profit": -10.0, "resolved": True},
                    ],
                },
                "ibkr::strat_e::AAPL": {
                    **sc._blank_symbol_scorecard(strategy, "AAPL"),
                    "entries_taken": 2,
                    "entries_resolved": 2,
                    "wins": 1,
                    "losses": 1,
                    "gross_profit": 8.0,
                    "gross_loss": 6.0,
                    "net_pnl": 2.0,
                    "last_trade_utc": "2026-03-27T12:05:00Z",
                    "recent_5_outcomes": [
                        {"timestamp": "2026-03-27T12:05:00Z", "result": "win", "profit": 8.0, "resolved": True},
                    ],
                },
            },
            "context_scorecards": {},
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)

        result = sc.ensure_scorecards([strategy], prune_stale=True)
        aggregate = result["scorecards"]["strat_e"]

        assert aggregate["entries_taken"] == 5
        assert aggregate["entries_resolved"] == 5
        assert aggregate["wins"] == 2
        assert aggregate["losses"] == 3
        assert aggregate["gross_profit"] == 14.0
        assert aggregate["gross_loss"] == 26.0
        assert aggregate["net_pnl"] == -12.0
        assert aggregate["last_trade_utc"] == "2026-03-27T12:05:00Z"

    def test_rebuilds_scorecards_from_execution_ledger(self, monkeypatch, tmp_path):
        """ensure_scorecards() should reconcile symbol/context/aggregate from ledger."""
        import brain_v9.trading.strategy_scorecard as sc

        monkeypatch.setattr(sc, "SCORECARDS_PATH", tmp_path / "scorecards.json")

        strategy = _make_strategy("strat_ledger", "pocket_option", ["EURUSD_otc"])
        existing = {
            "schema_version": "strategy_scorecards_v3",
            "updated_utc": "2025-01-01T00:00:00Z",
            "scorecards": {"strat_ledger": sc._blank_scorecard(strategy)},
            "symbol_scorecards": {
                "pocket_option::strat_ledger::EURUSD_otc": sc._blank_symbol_scorecard(strategy, "EURUSD_otc"),
            },
            "context_scorecards": {
                "pocket_option::strat_ledger::EURUSD_otc::1m::base": sc._blank_context_scorecard(strategy, "EURUSD_otc", "1m", "base"),
            },
        }
        sc.write_json(sc.SCORECARDS_PATH, existing)
        sc.write_json(
            sc.SCORECARDS_PATH.parent / "signal_paper_execution_ledger.json",
            {
                "schema_version": "signal_paper_execution_ledger_v1",
                "updated_utc": "2025-01-01T00:00:00Z",
                "entries": [
                    {
                        "timestamp": "2025-01-01T00:00:01Z",
                        "resolved_utc": "2025-01-01T00:00:10Z",
                        "strategy_id": "strat_ledger",
                        "venue": "pocket_option",
                        "symbol": "EURUSD_otc",
                        "direction": "call",
                        "result": "win",
                        "profit": 6.5,
                        "resolved": True,
                        "timeframe": "1m",
                        "setup_variant": "base",
                    },
                    {
                        "timestamp": "2025-01-01T00:00:20Z",
                        "strategy_id": "strat_ledger",
                        "venue": "pocket_option",
                        "symbol": "EURUSD_otc",
                        "direction": "put",
                        "result": "pending_resolution",
                        "profit": 0.0,
                        "resolved": False,
                        "timeframe": "1m",
                        "setup_variant": "base",
                    },
                ],
            },
        )

        result = sc.ensure_scorecards([strategy], prune_stale=True)
        aggregate = result["scorecards"]["strat_ledger"]
        symbol = result["symbol_scorecards"]["pocket_option::strat_ledger::EURUSD_otc"]
        context = result["context_scorecards"]["pocket_option::strat_ledger::EURUSD_otc::1m::base"]

        assert aggregate["entries_taken"] == 2
        assert aggregate["entries_resolved"] == 1
        assert aggregate["entries_open"] == 1
        assert aggregate["wins"] == 1
        assert aggregate["net_pnl"] == 6.5

        assert symbol["entries_taken"] == 2
        assert symbol["entries_resolved"] == 1
        assert symbol["entries_open"] == 1

        assert context["entries_taken"] == 2
        assert context["entries_resolved"] == 1
        assert context["entries_open"] == 1


# ---------------------------------------------------------------------------
# 4. Orphan hypothesis pruning
# ---------------------------------------------------------------------------

class TestOrphanHypothesisPruning:
    """P5-08d: prune_orphan_hypotheses() removes stale hypothesis entries."""

    def _setup_kb_paths(self, monkeypatch, tmp_path):
        import brain_v9.research.knowledge_base as kb

        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(kb, "KB_PATH", kb_path)
        monkeypatch.setattr(kb, "KNOWLEDGE_PATH", kb_path / "knowledge_base.json")
        monkeypatch.setattr(kb, "INDICATORS_PATH", kb_path / "indicator_registry.json")
        monkeypatch.setattr(kb, "STRATEGIES_PATH", kb_path / "strategy_specs.json")
        monkeypatch.setattr(kb, "HYPOTHESES_PATH", kb_path / "hypothesis_queue.json")
        return kb, kb_path

    def test_prunes_hypothesis_with_nonexistent_strategy(self, monkeypatch, tmp_path):
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        # Write strategies with only one valid id
        strategies = {
            "schema_version": "strategy_specs_v1",
            "strategies": [{"strategy_id": "valid_strat", "family": "test"}],
        }
        hypotheses = {
            "schema_version": "hypothesis_queue_v1",
            "top_priority": "valid_strat",
            "hypotheses": [
                {"id": "h_valid", "strategy_id": "valid_strat", "objective": "test"},
                {"id": "h_orphan", "strategy_id": "deleted_strat", "objective": "orphan"},
            ],
        }
        kb.write_json(kb.STRATEGIES_PATH, strategies)
        kb.write_json(kb.HYPOTHESES_PATH, hypotheses)

        pruned = kb.prune_orphan_hypotheses()

        assert pruned == ["h_orphan"]
        reloaded = kb.read_json(kb.HYPOTHESES_PATH, {})
        assert len(reloaded["hypotheses"]) == 1
        assert reloaded["hypotheses"][0]["id"] == "h_valid"

    def test_keeps_all_valid_hypotheses(self, monkeypatch, tmp_path):
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        strategies = {
            "strategies": [
                {"strategy_id": "s1"},
                {"strategy_id": "s2"},
            ],
        }
        hypotheses = {
            "hypotheses": [
                {"id": "h1", "strategy_id": "s1"},
                {"id": "h2", "strategy_id": "s2"},
            ],
        }
        kb.write_json(kb.STRATEGIES_PATH, strategies)
        kb.write_json(kb.HYPOTHESES_PATH, hypotheses)

        pruned = kb.prune_orphan_hypotheses()
        assert pruned == []

    def test_updates_top_priority_when_pruned(self, monkeypatch, tmp_path):
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        strategies = {
            "strategies": [{"strategy_id": "survivor"}],
        }
        hypotheses = {
            "top_priority": "deleted_strat",
            "hypotheses": [
                {"id": "h_survivor", "strategy_id": "survivor"},
                {"id": "h_gone", "strategy_id": "deleted_strat"},
            ],
        }
        kb.write_json(kb.STRATEGIES_PATH, strategies)
        kb.write_json(kb.HYPOTHESES_PATH, hypotheses)

        kb.prune_orphan_hypotheses()

        reloaded = kb.read_json(kb.HYPOTHESES_PATH, {})
        assert reloaded["top_priority"] == "survivor"

    def test_clears_top_priority_when_all_pruned(self, monkeypatch, tmp_path):
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        strategies = {"strategies": []}
        hypotheses = {
            "top_priority": "gone",
            "hypotheses": [
                {"id": "h1", "strategy_id": "gone"},
            ],
        }
        kb.write_json(kb.STRATEGIES_PATH, strategies)
        kb.write_json(kb.HYPOTHESES_PATH, hypotheses)

        pruned = kb.prune_orphan_hypotheses()
        assert len(pruned) == 1

        reloaded = kb.read_json(kb.HYPOTHESES_PATH, {})
        assert reloaded["top_priority"] is None
        assert reloaded["hypotheses"] == []

    def test_ensure_research_foundation_wires_pruning(self, monkeypatch, tmp_path):
        """ensure_research_foundation() calls prune_orphan_hypotheses()."""
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        # Seed files will be created by ensure_research_foundation
        # Then we inject an orphan hypothesis after seeding
        kb.ensure_research_foundation()

        # Now add an orphan hypothesis
        hyp_data = kb.read_json(kb.HYPOTHESES_PATH, {})
        hyp_data["hypotheses"].append({
            "id": "h_injected_orphan",
            "strategy_id": "nonexistent_strategy",
            "objective": "should be pruned",
        })
        kb.write_json(kb.HYPOTHESES_PATH, hyp_data)

        # Re-run ensure — it should prune the orphan
        kb.ensure_research_foundation()

        reloaded = kb.read_json(kb.HYPOTHESES_PATH, {})
        ids = [h["id"] for h in reloaded["hypotheses"]]
        assert "h_injected_orphan" not in ids

    def test_backward_compat_with_old_id_field(self, monkeypatch, tmp_path):
        """Strategies using 'id' instead of 'strategy_id' are recognized."""
        kb, kb_path = self._setup_kb_paths(monkeypatch, tmp_path)

        strategies = {
            "strategies": [{"id": "old_format_strat", "family": "test"}],
        }
        hypotheses = {
            "hypotheses": [
                {"id": "h1", "strategy_id": "old_format_strat"},
                {"id": "h2", "strategy_id": "nonexistent"},
            ],
        }
        kb.write_json(kb.STRATEGIES_PATH, strategies)
        kb.write_json(kb.HYPOTHESES_PATH, hypotheses)

        pruned = kb.prune_orphan_hypotheses()
        assert pruned == ["h2"]
        reloaded = kb.read_json(kb.HYPOTHESES_PATH, {})
        assert len(reloaded["hypotheses"]) == 1
        assert reloaded["hypotheses"][0]["strategy_id"] == "old_format_strat"
