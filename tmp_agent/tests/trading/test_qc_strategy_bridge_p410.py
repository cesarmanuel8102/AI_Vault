"""
P4-10 — Tests for QC Strategy Bridge.

Tests cover:
  - backtest_to_strategy_spec: structure, status classification, known/unknown projects
  - merge_qc_strategy: insert, update (upsert), preserves existing strategies
  - list_qc_strategies: filters by venue == quantconnect
"""
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _good_metrics():
    return {
        "sharpe_ratio": 1.5,
        "sortino_ratio": 2.0,
        "compounding_annual_return": 0.20,
        "drawdown": 0.085,
        "net_profit": 0.20,
        "win_rate": 0.60,
        "loss_rate": 0.40,
        "expectancy": 0.45,
        "total_orders": 42,
        "profit_loss_ratio": 1.67,
        "alpha": 0.05,
        "beta": 0.8,
    }


def _marginal_metrics():
    return {
        "sharpe_ratio": 0.5,
        "sortino_ratio": 0.6,
        "compounding_annual_return": 0.05,
        "drawdown": 0.15,
        "net_profit": 0.05,
        "win_rate": 0.45,
        "loss_rate": 0.55,
        "expectancy": 0.02,
        "total_orders": 30,
        "profit_loss_ratio": 0.8,
        "alpha": 0.01,
        "beta": 1.1,
    }


def _write_specs(path: Path, strategies=None):
    data = {
        "schema_version": "strategy_specs_v1_normalized",
        "strategies": strategies or [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ===========================================================================
# backtest_to_strategy_spec
# ===========================================================================
class TestBacktestToStrategySpec:
    def test_structure_has_required_keys(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics())
        required = [
            "strategy_id", "venue", "family", "status", "timeframes",
            "universe", "entry", "exit", "filters", "success_criteria",
            "core_indicators", "summary", "paper_only", "asset_classes",
            "primary_asset_class", "execution_profile", "qc_metadata",
            "qc_backtest_metrics",
        ]
        for key in required:
            assert key in spec, f"Missing key: {key}"

    def test_venue_is_quantconnect(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics())
        assert spec["venue"] == "quantconnect"

    def test_strategy_id_format(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics())
        assert spec["strategy_id"] == "qc_24654779_bt-abc12"

    def test_status_validated_for_good_metrics(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics())
        assert spec["status"] == "qc_backtest_validated"

    def test_status_marginal_for_poor_metrics(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _marginal_metrics())
        assert spec["status"] == "qc_backtest_marginal"

    def test_status_insufficient_for_few_trades(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        m = _good_metrics()
        m["total_orders"] = 3
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", m)
        assert spec["status"] == "qc_backtest_insufficient"

    def test_known_project_gets_metadata(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics())
        assert spec["family"] == "ml_ensemble"
        assert "SPY" in spec["universe"]
        assert spec["qc_metadata"]["project_name"] == "Upgraded Sky Blue Butterfly"

    def test_unknown_project_defaults(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(99999999, "bt-xyz", _good_metrics())
        assert spec["family"] == "unknown"
        assert spec["universe"] == []

    def test_metrics_preserved(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        metrics = _good_metrics()
        spec = backtest_to_strategy_spec(24654779, "bt-abc", metrics)
        bm = spec["qc_backtest_metrics"]
        assert bm["sharpe_ratio"] == pytest.approx(1.5)
        assert bm["win_rate"] == pytest.approx(0.60)
        assert bm["total_orders"] == 42

    def test_paper_only_is_true(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc", _good_metrics())
        assert spec["paper_only"] is True

    def test_qc_metadata_has_backtest_id(self):
        from brain_v9.trading.qc_strategy_bridge import backtest_to_strategy_spec
        spec = backtest_to_strategy_spec(24654779, "bt-abc12345", _good_metrics(), "My BT")
        assert spec["qc_metadata"]["backtest_id"] == "bt-abc12345"
        assert spec["qc_metadata"]["backtest_name"] == "My BT"


# ===========================================================================
# merge_qc_strategy
# ===========================================================================
class TestMergeQcStrategy:
    def test_insert_new(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import (
            backtest_to_strategy_spec, merge_qc_strategy,
        )
        specs_path = tmp_path / "specs.json"
        _write_specs(specs_path, [])
        spec = backtest_to_strategy_spec(24654779, "bt-001", _good_metrics())
        result = merge_qc_strategy(spec, specs_path=specs_path)
        assert result["action"] == "inserted"

        # Verify on disk
        data = json.loads(specs_path.read_text(encoding="utf-8"))
        assert len(data["strategies"]) == 1
        assert data["strategies"][0]["venue"] == "quantconnect"

    def test_upsert_replaces_existing(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import (
            backtest_to_strategy_spec, merge_qc_strategy,
        )
        specs_path = tmp_path / "specs.json"
        _write_specs(specs_path, [])

        spec_v1 = backtest_to_strategy_spec(24654779, "bt-001", _marginal_metrics())
        merge_qc_strategy(spec_v1, specs_path=specs_path)

        spec_v2 = backtest_to_strategy_spec(24654779, "bt-001", _good_metrics())
        # Same strategy_id → should update, not insert
        result = merge_qc_strategy(spec_v2, specs_path=specs_path)
        assert result["action"] == "updated"

        data = json.loads(specs_path.read_text(encoding="utf-8"))
        assert len(data["strategies"]) == 1
        assert data["strategies"][0]["status"] == "qc_backtest_validated"

    def test_preserves_existing_strategies(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import (
            backtest_to_strategy_spec, merge_qc_strategy,
        )
        specs_path = tmp_path / "specs.json"
        existing = {"strategy_id": "ibkr_trend_pullback_v1", "venue": "ibkr", "status": "paper_candidate"}
        _write_specs(specs_path, [existing])

        spec = backtest_to_strategy_spec(24654779, "bt-001", _good_metrics())
        merge_qc_strategy(spec, specs_path=specs_path)

        data = json.loads(specs_path.read_text(encoding="utf-8"))
        assert len(data["strategies"]) == 2
        venues = {s["venue"] for s in data["strategies"]}
        assert venues == {"ibkr", "quantconnect"}


# ===========================================================================
# list_qc_strategies
# ===========================================================================
class TestListQcStrategies:
    def test_returns_only_qc(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import list_qc_strategies
        specs_path = tmp_path / "specs.json"
        _write_specs(specs_path, [
            {"strategy_id": "ibkr_1", "venue": "ibkr"},
            {"strategy_id": "qc_1", "venue": "quantconnect"},
            {"strategy_id": "po_1", "venue": "pocket_option"},
            {"strategy_id": "qc_2", "venue": "quantconnect"},
        ])
        result = list_qc_strategies(specs_path=specs_path)
        assert len(result) == 2
        assert all(s["venue"] == "quantconnect" for s in result)

    def test_empty_when_no_qc(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import list_qc_strategies
        specs_path = tmp_path / "specs.json"
        _write_specs(specs_path, [{"strategy_id": "ibkr_1", "venue": "ibkr"}])
        result = list_qc_strategies(specs_path=specs_path)
        assert result == []

    def test_missing_file_returns_empty(self, tmp_path):
        from brain_v9.trading.qc_strategy_bridge import list_qc_strategies
        specs_path = tmp_path / "nonexistent.json"
        result = list_qc_strategies(specs_path=specs_path)
        assert result == []
