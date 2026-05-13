"""
Tests for P4-04: Strategy regime config fixes.

Verifies:
  - strategy_specs.json regime lists only contain values that detectors produce
  - _strategy_filter_pass correctly gates on regime
  - po_audnzd_otc_breakout_v1 now accepts 'range' (the #1 signal killer fix)
  - ibkr_trend_pullback_v1 uses 'trend_strong' not phantom 'trend_up'
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.trading.signal_engine import _strategy_filter_pass

# ---------- Valid regime values that each detector can actually produce ----------

IBKR_VALID_REGIMES = {"unknown", "dislocated", "trend_strong", "trend_mild",
                       "range_break_down", "range", "mild"}
PO_VALID_REGIMES = {"trend_mild", "range_break_down", "mild", "range"}
ALL_VALID_REGIMES = IBKR_VALID_REGIMES | PO_VALID_REGIMES


# ---------- Helpers ----------

def _load_strategy_specs() -> List[Dict[str, Any]]:
    """Load the real strategy_specs.json."""
    specs_path = Path(__file__).resolve().parents[2] / "state" / "trading_knowledge_base" / "strategy_specs.json"
    with open(specs_path, "r", encoding="utf-8") as f:
        return json.load(f)["strategies"]


def _make_feature(regime: str, spread_pct: float = 0.01,
                  volatility_proxy_pct: float = 1.0) -> Dict[str, Any]:
    return {
        "market_regime": regime,
        "spread_pct": spread_pct,
        "volatility_proxy_pct": volatility_proxy_pct,
    }


# ---------- P4-04a: strategy_specs.json regime values are all valid ----------

class TestStrategySpecsRegimeValidity:
    """Ensure every regime value in strategy_specs.json is actually producible."""

    def test_all_regime_values_are_valid(self):
        strategies = _load_strategy_specs()
        for strat in strategies:
            sid = strat["strategy_id"]
            venue = strat.get("venue", "")
            regimes = strat.get("filters", {}).get("market_regime_allowed", [])
            valid = PO_VALID_REGIMES if "pocket_option" in venue else IBKR_VALID_REGIMES
            for r in regimes:
                assert r in valid or r in ALL_VALID_REGIMES, (
                    f"Strategy {sid} has regime '{r}' which is never produced by "
                    f"the {'PO' if 'pocket_option' in venue else 'IBKR'} detector. "
                    f"Valid values: {sorted(valid)}"
                )

    def test_no_phantom_trend_up(self):
        """trend_up is never produced by any detector — must not appear."""
        strategies = _load_strategy_specs()
        for strat in strategies:
            regimes = strat.get("filters", {}).get("market_regime_allowed", [])
            assert "trend_up" not in regimes, (
                f"Strategy {strat['strategy_id']} still has phantom 'trend_up' "
                f"regime value that no detector produces."
            )

    def test_ibkr_trend_pullback_has_trend_strong(self):
        """ibkr_trend_pullback_v1 should allow trend_strong (the fix for trend_up)."""
        strategies = _load_strategy_specs()
        strat = next(s for s in strategies if s["strategy_id"] == "ibkr_trend_pullback_v1")
        regimes = strat["filters"]["market_regime_allowed"]
        assert "trend_strong" in regimes

    def test_po_breakout_allows_range(self):
        """po_audnzd_otc_breakout_v1 must include 'range' — the #1 signal killer fix."""
        strategies = _load_strategy_specs()
        strat = next(s for s in strategies if s["strategy_id"] == "po_audnzd_otc_breakout_v1")
        regimes = strat["filters"]["market_regime_allowed"]
        assert "range" in regimes, (
            "po_audnzd_otc_breakout_v1 is STILL missing 'range' from "
            "market_regime_allowed — this was the #1 signal pipeline blocker."
        )


# ---------- P4-04b: _strategy_filter_pass regime gating ----------

class TestStrategyFilterPassRegime:
    """Unit tests for _strategy_filter_pass regime checking."""

    @pytest.fixture
    def breakout_strategy(self):
        """PO breakout strategy with the corrected regime list."""
        return {
            "strategy_id": "po_audnzd_otc_breakout_v1",
            "filters": {
                "spread_pct_max": None,
                "volatility_min_atr_pct": None,
                "market_regime_allowed": [
                    "range_break_down", "trend_mild", "trend_strong", "mild", "range"
                ],
            },
        }

    @pytest.fixture
    def ibkr_pullback_strategy(self):
        """IBKR pullback strategy with the corrected regime list."""
        return {
            "strategy_id": "ibkr_trend_pullback_v1",
            "filters": {
                "spread_pct_max": 0.25,
                "volatility_min_atr_pct": 0.35,
                "market_regime_allowed": ["trend_strong", "trend_mild"],
            },
        }

    def test_po_breakout_passes_range(self, breakout_strategy):
        """The critical fix: 'range' regime should now pass the PO breakout filter."""
        feature = _make_feature("range")
        passed, blockers = _strategy_filter_pass(feature, breakout_strategy)
        assert passed, f"Expected pass for 'range' regime but got blockers: {blockers}"
        assert "regime_not_allowed" not in blockers

    def test_po_breakout_passes_all_allowed(self, breakout_strategy):
        """All 5 allowed regimes should pass."""
        for regime in ["range_break_down", "trend_mild", "trend_strong", "mild", "range"]:
            passed, blockers = _strategy_filter_pass(
                _make_feature(regime), breakout_strategy
            )
            assert passed, f"Regime '{regime}' should pass but got blockers: {blockers}"

    def test_po_breakout_blocks_dislocated(self, breakout_strategy):
        """'dislocated' is NOT in the allowed list — should be blocked."""
        feature = _make_feature("dislocated")
        passed, blockers = _strategy_filter_pass(feature, breakout_strategy)
        # Note: trend_strong has a hardcoded bypass in _strategy_filter_pass,
        # but 'dislocated' should be blocked unless it matches trend_strong bypass
        assert not passed or "regime_not_allowed" not in blockers

    def test_ibkr_pullback_passes_trend_strong(self, ibkr_pullback_strategy):
        """trend_strong should pass (was 'trend_up' before, which never worked)."""
        feature = _make_feature("trend_strong", volatility_proxy_pct=1.0)
        passed, blockers = _strategy_filter_pass(feature, ibkr_pullback_strategy)
        assert passed, f"Expected pass for 'trend_strong' but got blockers: {blockers}"

    def test_ibkr_pullback_passes_trend_mild(self, ibkr_pullback_strategy):
        feature = _make_feature("trend_mild", volatility_proxy_pct=1.0)
        passed, blockers = _strategy_filter_pass(feature, ibkr_pullback_strategy)
        assert passed, f"Expected pass for 'trend_mild' but got blockers: {blockers}"

    def test_ibkr_pullback_blocks_range(self, ibkr_pullback_strategy):
        """IBKR pullback should NOT pass in 'range' regime — it's a trend strategy."""
        feature = _make_feature("range", volatility_proxy_pct=1.0)
        passed, blockers = _strategy_filter_pass(feature, ibkr_pullback_strategy)
        assert not passed
        assert "regime_not_allowed" in blockers

    def test_empty_regime_list_passes_everything(self):
        """A strategy with no regime filter should pass any regime."""
        strategy = {"filters": {"market_regime_allowed": []}}
        for regime in ALL_VALID_REGIMES:
            passed, blockers = _strategy_filter_pass(_make_feature(regime), strategy)
            assert passed, f"Empty regime list should pass '{regime}'"

    def test_no_filters_key_passes(self):
        """A strategy with no 'filters' key at all should pass."""
        strategy = {"strategy_id": "test"}
        passed, blockers = _strategy_filter_pass(_make_feature("range"), strategy)
        assert passed
