"""P4-15: Tests for QC pattern ingester."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from brain_v9.trading.qc_pattern_ingester import (
    PATTERN_PARAMS,
    apply_patterns_to_spec,
    get_available_patterns,
    ingest_patterns_for_project,
    load_pattern_library,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pattern_library(tmp_path: Path) -> Path:
    """Write a minimal pattern library JSON for testing."""
    lib_dir = tmp_path / "tmp_agent" / "state" / "rooms" / "brain_financial_ingestion_fi07_memory"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_path = lib_dir / "quantconnect_pattern_library.json"
    lib_path.write_text(json.dumps({
        "schema_version": "quantconnect_pattern_library_v1",
        "reusable_patterns": [
            {
                "pattern_id": "qc_objectstore_model_contract",
                "description": "ObjectStore model persistence",
                "reuse_confidence": "high",
            },
            {
                "pattern_id": "qc_temporal_validation_and_calibration",
                "description": "Triple barrier + temporal CV",
                "reuse_confidence": "high",
            },
        ],
    }), encoding="utf-8")
    return lib_path


def _make_qc_spec(
    project_id: int = 24654779,
    backtest_id: str = "abc12345",
    patterns: list[str] | None = None,
) -> Dict[str, Any]:
    """Build a minimal strategy spec like backtest_to_strategy_spec would."""
    return {
        "strategy_id": f"qc_{project_id}_{backtest_id[:8]}",
        "venue": "quantconnect",
        "family": "ml_ensemble",
        "status": "qc_backtest_validated",
        "filters": {
            "spread_pct_max": 0.10,
            "market_regime_allowed": [],
        },
        "execution_profile": {
            "mode": "qc_cloud_backtest",
            "supports_live_signal_resolution": False,
        },
        "success_criteria": {
            "min_resolved_trades": 20,
            "min_expectancy": 0.1,
            "min_win_rate": 0.50,
        },
        "invalidators": ["regime_shift_undetected"],
        "qc_metadata": {
            "project_id": project_id,
            "backtest_id": backtest_id,
            "patterns": patterns if patterns is not None else [
                "qc_objectstore_model_contract",
                "qc_ibkr_execution_lane",
                "qc_options_ml_stack",
                "qc_temporal_validation_and_calibration",
            ],
        },
    }


# ---------------------------------------------------------------------------
# Tests: PATTERN_PARAMS structure
# ---------------------------------------------------------------------------

class TestPatternParams:
    def test_all_four_patterns_defined(self):
        assert "qc_objectstore_model_contract" in PATTERN_PARAMS
        assert "qc_ibkr_execution_lane" in PATTERN_PARAMS
        assert "qc_options_ml_stack" in PATTERN_PARAMS
        assert "qc_temporal_validation_and_calibration" in PATTERN_PARAMS

    def test_objectstore_has_model_persistence(self):
        p = PATTERN_PARAMS["qc_objectstore_model_contract"]
        assert p["model_persistence"] is True
        assert p["retrain_cadence_days"] == 30

    def test_ibkr_has_execution_lane(self):
        p = PATTERN_PARAMS["qc_ibkr_execution_lane"]
        assert p["execution_lane"] == "ibkr"
        assert p["max_portfolio_leverage"] == 1.0

    def test_options_ml_has_dte(self):
        p = PATTERN_PARAMS["qc_options_ml_stack"]
        assert p["min_dte"] == 14
        assert p["max_dte"] == 45

    def test_temporal_validation_has_cv(self):
        p = PATTERN_PARAMS["qc_temporal_validation_and_calibration"]
        assert p["validation_method"] == "temporal_cross_validation"
        assert p["labeling_method"] == "triple_barrier"


# ---------------------------------------------------------------------------
# Tests: load_pattern_library
# ---------------------------------------------------------------------------

class TestLoadPatternLibrary:
    def test_load_existing_library(self, isolated_base_path):
        lib_path = _write_pattern_library(isolated_base_path)
        result = load_pattern_library(lib_path)
        assert result["schema_version"] == "quantconnect_pattern_library_v1"
        assert len(result["reusable_patterns"]) == 2

    def test_load_missing_library_returns_default(self, isolated_base_path):
        missing = isolated_base_path / "nonexistent.json"
        result = load_pattern_library(missing)
        assert result["reusable_patterns"] == []

    def test_get_available_patterns(self, isolated_base_path):
        lib_path = _write_pattern_library(isolated_base_path)
        patterns = get_available_patterns(lib_path)
        assert len(patterns) == 2
        ids = {p["pattern_id"] for p in patterns}
        assert "qc_objectstore_model_contract" in ids


# ---------------------------------------------------------------------------
# Tests: ingest_patterns_for_project
# ---------------------------------------------------------------------------

class TestIngestPatternsForProject:
    def test_merge_all_patterns(self):
        merged = ingest_patterns_for_project(24654779, [
            "qc_objectstore_model_contract",
            "qc_ibkr_execution_lane",
        ])
        assert merged["model_persistence"] is True
        assert merged["execution_lane"] == "ibkr"
        assert "_applied_patterns" in merged
        assert len(merged["_applied_patterns"]) == 2

    def test_empty_patterns(self):
        merged = ingest_patterns_for_project(24654779, [])
        assert merged == {}

    def test_none_patterns(self):
        merged = ingest_patterns_for_project(24654779, None)
        assert merged == {}

    def test_unknown_pattern_skipped(self):
        merged = ingest_patterns_for_project(24654779, [
            "qc_objectstore_model_contract",
            "nonexistent_pattern",
        ])
        assert merged["model_persistence"] is True
        assert "nonexistent_pattern" not in merged.get("_applied_patterns", [])

    def test_later_pattern_overrides_earlier(self):
        """IBKR pattern sets supports_live=True, options_ml doesn't have it,
        temporal_validation doesn't override it."""
        merged = ingest_patterns_for_project(24654779, [
            "qc_ibkr_execution_lane",
            "qc_options_ml_stack",
        ])
        # IBKR set supports_live=True, options_ml doesn't override it
        assert merged["supports_live_signal_resolution"] is True
        # Options ML adds its own params
        assert merged["min_dte"] == 14


# ---------------------------------------------------------------------------
# Tests: apply_patterns_to_spec
# ---------------------------------------------------------------------------

class TestApplyPatternsToSpec:
    def test_enriches_spec_with_pattern_params(self):
        spec = _make_qc_spec()
        result = apply_patterns_to_spec(spec)
        assert "qc_pattern_params" in result
        params = result["qc_pattern_params"]
        assert params["model_persistence"] is True
        assert params["execution_lane"] == "ibkr"

    def test_tightens_spread_filter(self):
        """Options ML pattern has max_spread_pct=0.07, spec has 0.10 → should tighten."""
        spec = _make_qc_spec()
        apply_patterns_to_spec(spec)
        assert spec["filters"]["spread_pct_max"] == 0.07

    def test_does_not_widen_spread_filter(self):
        """If spec already has tighter spread, pattern should not widen it."""
        spec = _make_qc_spec()
        spec["filters"]["spread_pct_max"] = 0.03  # Tighter than pattern's 0.07
        apply_patterns_to_spec(spec)
        assert spec["filters"]["spread_pct_max"] == 0.03

    def test_sets_live_signal_resolution(self):
        spec = _make_qc_spec()
        assert spec["execution_profile"]["supports_live_signal_resolution"] is False
        apply_patterns_to_spec(spec)
        assert spec["execution_profile"]["supports_live_signal_resolution"] is True

    def test_raises_min_expectancy(self):
        """Temporal validation sets min_oos_sharpe=0.5, which should raise min_expectancy."""
        spec = _make_qc_spec()
        spec["success_criteria"]["min_expectancy"] = 0.1
        apply_patterns_to_spec(spec)
        assert spec["success_criteria"]["min_expectancy"] == 0.5

    def test_does_not_lower_min_expectancy(self):
        """If spec already has higher min_expectancy, pattern should not lower it."""
        spec = _make_qc_spec()
        spec["success_criteria"]["min_expectancy"] = 1.0
        apply_patterns_to_spec(spec)
        assert spec["success_criteria"]["min_expectancy"] == 1.0

    def test_adds_model_degradation_invalidator(self):
        spec = _make_qc_spec()
        assert "model_degradation" not in spec["invalidators"]
        apply_patterns_to_spec(spec)
        assert "model_degradation" in spec["invalidators"]

    def test_does_not_duplicate_invalidator(self):
        spec = _make_qc_spec()
        spec["invalidators"].append("model_degradation")
        apply_patterns_to_spec(spec)
        count = spec["invalidators"].count("model_degradation")
        assert count == 1

    def test_no_patterns_returns_unchanged(self):
        spec = _make_qc_spec(patterns=[])
        original_spread = spec["filters"]["spread_pct_max"]
        apply_patterns_to_spec(spec)
        assert "qc_pattern_params" not in spec
        assert spec["filters"]["spread_pct_max"] == original_spread

    def test_explicit_pattern_ids_override_metadata(self):
        """If pattern_ids kwarg is given, it overrides qc_metadata.patterns."""
        spec = _make_qc_spec(patterns=["qc_objectstore_model_contract"])
        # Override with different patterns
        apply_patterns_to_spec(spec, pattern_ids=["qc_ibkr_execution_lane"])
        params = spec["qc_pattern_params"]
        assert "execution_lane" in params
        assert "model_persistence" not in params

    def test_applied_patterns_tracked(self):
        spec = _make_qc_spec()
        apply_patterns_to_spec(spec)
        applied = spec["qc_pattern_params"]["_applied_patterns"]
        assert len(applied) == 4
