"""
P6-13 — Tests for brain_v9/trading/hypothesis_engine.py

Covers:
  - _utc_now helper
  - evaluate_hypotheses: all 5 outcome branches, strategy_id resolution,
    field extraction, write_json call, payload structure
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from brain_v9.trading.hypothesis_engine import _utc_now, evaluate_hypotheses


# ── _utc_now ────────────────────────────────────────────────────────

class TestUtcNow:
    def test_returns_iso_string(self):
        ts = _utc_now()
        assert isinstance(ts, str)
        assert "T" in ts

    def test_ends_with_z(self):
        ts = _utc_now()
        assert ts.endswith("Z"), f"Expected Z suffix, got {ts!r}"

    def test_no_plus_zero_offset(self):
        ts = _utc_now()
        assert "+00:00" not in ts

    def test_parseable(self):
        ts = _utc_now()
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None


# ── evaluate_hypotheses — outcome branches ──────────────────────────

def _hyp(strategy_id: str = "strat_a", **kw) -> Dict[str, Any]:
    """Convenience builder for a hypothesis dict."""
    base = {"id": "h1", "strategy_id": strategy_id, "objective": "test obj", "success_metric": "expectancy>0"}
    base.update(kw)
    return base


def _card(entries_resolved: int = 0, expectancy: float = 0.0, sample_quality: float = 0.0) -> Dict[str, Any]:
    return {"entries_resolved": entries_resolved, "expectancy": expectancy, "sample_quality": sample_quality}


class TestOutcomeQueued:
    """resolved == 0 → status=queued, result=no_sample"""

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_queued_when_no_scorecard(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {})
        r = out["results"][0]
        assert r["status"] == "queued"
        assert r["result"] == "no_sample"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_queued_when_zero_resolved(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=0)})
        assert out["results"][0]["status"] == "queued"


class TestOutcomeInsufficientSample:
    """resolved > 0 but sample_quality < 1.0 → in_test"""

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_in_test(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=5, sample_quality=0.5)})
        r = out["results"][0]
        assert r["status"] == "in_test"
        assert r["result"] == "insufficient_sample"


class TestOutcomePass:
    """sample_quality >= 1.0 and expectancy > 0 → pass"""

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_pass(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=30, expectancy=0.5, sample_quality=1.2)})
        r = out["results"][0]
        assert r["status"] == "pass"
        assert r["result"] == "positive_expectancy"


class TestOutcomeFail:
    """sample_quality >= 1.0 and expectancy < 0 → fail"""

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_fail(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=30, expectancy=-0.3, sample_quality=1.5)})
        r = out["results"][0]
        assert r["status"] == "fail"
        assert r["result"] == "negative_expectancy"


class TestOutcomeInconclusive:
    """sample_quality >= 1.0 and expectancy == 0 → inconclusive"""

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_inconclusive(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=20, expectancy=0.0, sample_quality=1.0)})
        r = out["results"][0]
        assert r["status"] == "inconclusive"
        assert r["result"] == "flat_expectancy"


# ── evaluate_hypotheses — strategy_id resolution ────────────────────

class TestStrategyIdResolution:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_uses_strategy_id_field(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp(strategy_id="alpha")], {"alpha": _card(entries_resolved=10, sample_quality=1.5, expectancy=1.0)})
        assert out["results"][0]["strategy_id"] == "alpha"
        assert out["results"][0]["status"] == "pass"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_falls_back_to_linked_strategies(self, mock_wj: MagicMock):
        hyp = {"id": "h2", "linked_strategies": ["beta"], "objective": "obj"}
        out = evaluate_hypotheses([hyp], {"beta": _card(entries_resolved=5, sample_quality=0.4)})
        assert out["results"][0]["strategy_id"] == "beta"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_none_strategy_id_when_no_linked(self, mock_wj: MagicMock):
        hyp = {"id": "h3", "objective": "obj"}
        out = evaluate_hypotheses([hyp], {})
        assert out["results"][0]["strategy_id"] is None

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_empty_linked_strategies_falls_to_none(self, mock_wj: MagicMock):
        hyp = {"id": "h4", "linked_strategies": [], "objective": "obj"}
        # ([] or [None])[0] → [None][0] → None
        out = evaluate_hypotheses([hyp], {})
        assert out["results"][0]["strategy_id"] is None


# ── evaluate_hypotheses — field extraction ──────────────────────────

class TestFieldExtraction:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_statement_from_objective(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp(objective="my obj")], {})
        assert out["results"][0]["statement"] == "my obj"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_statement_falls_back_to_statement_key(self, mock_wj: MagicMock):
        hyp = {"id": "h5", "strategy_id": "x", "statement": "my stmt"}
        out = evaluate_hypotheses([hyp], {})
        assert out["results"][0]["statement"] == "my stmt"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_success_metric_extracted(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp(success_metric="pf>1")], {})
        assert out["results"][0]["success_metric"] == "pf>1"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_hypothesis_id_extracted(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp(id="HYP-42")], {})
        assert out["results"][0]["hypothesis_id"] == "HYP-42"


# ── evaluate_hypotheses — None/missing scorecard fields coerced ─────

class TestNoneCoercion:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_none_entries_resolved_treated_as_zero(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": {"entries_resolved": None}})
        assert out["results"][0]["entries_resolved"] == 0
        assert out["results"][0]["status"] == "queued"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_none_expectancy_treated_as_zero(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": {"entries_resolved": 20, "sample_quality": 1.0, "expectancy": None}})
        assert out["results"][0]["expectancy"] == 0.0
        assert out["results"][0]["status"] == "inconclusive"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_none_sample_quality_treated_as_zero(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": {"entries_resolved": 10, "sample_quality": None, "expectancy": 0.5}})
        assert out["results"][0]["sample_quality"] == 0.0
        assert out["results"][0]["status"] == "in_test"


# ── evaluate_hypotheses — payload structure ─────────────────────────

class TestPayloadStructure:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_schema_version(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([], {})
        assert out["schema_version"] == "hypothesis_results_v1"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_updated_utc_present(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([], {})
        assert "updated_utc" in out
        assert isinstance(out["updated_utc"], str)

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_results_is_list(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([], {})
        assert isinstance(out["results"], list)

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_empty_hypotheses_returns_empty_results(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([], {})
        assert out["results"] == []


# ── evaluate_hypotheses — write_json call ───────────────────────────

class TestWriteJson:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_write_json_called_once(self, mock_wj: MagicMock):
        evaluate_hypotheses([_hyp()], {})
        mock_wj.assert_called_once()

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_write_json_receives_payload(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {})
        _, payload = mock_wj.call_args[0]
        assert payload is out

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_write_json_path(self, mock_wj: MagicMock):
        from brain_v9.trading.hypothesis_engine import HYP_RESULTS_PATH
        evaluate_hypotheses([], {})
        path_arg = mock_wj.call_args[0][0]
        assert path_arg == HYP_RESULTS_PATH


# ── evaluate_hypotheses — multiple hypotheses ───────────────────────

class TestMultipleHypotheses:
    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_multiple_results_returned(self, mock_wj: MagicMock):
        hyps = [
            _hyp(id="h1", strategy_id="a"),
            _hyp(id="h2", strategy_id="b"),
            _hyp(id="h3", strategy_id="c"),
        ]
        cards = {
            "a": _card(entries_resolved=0),
            "b": _card(entries_resolved=20, sample_quality=1.5, expectancy=0.3),
            "c": _card(entries_resolved=15, sample_quality=1.0, expectancy=-0.1),
        }
        out = evaluate_hypotheses(hyps, cards)
        assert len(out["results"]) == 3
        assert out["results"][0]["status"] == "queued"
        assert out["results"][1]["status"] == "pass"
        assert out["results"][2]["status"] == "fail"

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_order_preserved(self, mock_wj: MagicMock):
        hyps = [_hyp(id=f"h{i}", strategy_id=f"s{i}") for i in range(5)]
        out = evaluate_hypotheses(hyps, {})
        ids = [r["hypothesis_id"] for r in out["results"]]
        assert ids == [f"h{i}" for i in range(5)]


# ── result item field completeness ──────────────────────────────────

class TestResultItemFields:
    EXPECTED_KEYS = {
        "hypothesis_id", "strategy_id", "statement", "success_metric",
        "entries_resolved", "sample_quality", "expectancy", "status", "result",
    }

    @patch("brain_v9.trading.hypothesis_engine.write_json")
    def test_all_expected_keys_present(self, mock_wj: MagicMock):
        out = evaluate_hypotheses([_hyp()], {"strat_a": _card(entries_resolved=30, sample_quality=1.5, expectancy=0.5)})
        assert set(out["results"][0].keys()) == self.EXPECTED_KEYS
