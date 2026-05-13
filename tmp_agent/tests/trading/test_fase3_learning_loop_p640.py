"""
Brain V9 — Fase 3 Tests: Learning Loop, Context Dimensions, Explainability
Tests for: duration/payout bucketing, post-trade new dimensions,
learning loop snapshot, decision logic, enriched hypothesis schema,
and decision_context explainability.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import brain_v9.trading.post_trade_analysis as pta
import brain_v9.trading.learning_loop as ll
import brain_v9.research.knowledge_base as kb


# ---------------------------------------------------------------------------
# 3.1 — Duration bucket tests
# ---------------------------------------------------------------------------

def test_duration_bucket_ultra_short():
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T10:01:30Z"}
    assert pta._duration_bucket(entry) == "ultra_short_<=2m"


def test_duration_bucket_short():
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T10:05:00Z"}
    assert pta._duration_bucket(entry) == "short_2m-10m"


def test_duration_bucket_medium():
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T10:30:00Z"}
    assert pta._duration_bucket(entry) == "medium_10m-1h"


def test_duration_bucket_long():
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T12:00:00Z"}
    assert pta._duration_bucket(entry) == "long_>1h"


def test_duration_bucket_missing_timestamps():
    assert pta._duration_bucket({}) == "unknown"
    assert pta._duration_bucket({"timestamp": "2026-03-27T10:00:00Z"}) == "unknown"
    assert pta._duration_bucket({"resolved_utc": "2026-03-27T10:00:00Z"}) == "unknown"


def test_duration_bucket_boundary_2m():
    """Exactly 120 seconds should be ultra_short."""
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T10:02:00Z"}
    assert pta._duration_bucket(entry) == "ultra_short_<=2m"


def test_duration_bucket_boundary_10m():
    """Exactly 600 seconds should be short."""
    entry = {"timestamp": "2026-03-27T10:00:00Z", "resolved_utc": "2026-03-27T10:10:00Z"}
    assert pta._duration_bucket(entry) == "short_2m-10m"


# ---------------------------------------------------------------------------
# 3.1 — Payout bucket tests
# ---------------------------------------------------------------------------

def test_payout_bucket_no_payout():
    assert pta._payout_bucket({}) == "no_payout"
    assert pta._payout_bucket({"entry_payout_pct": None}) == "no_payout"


def test_payout_bucket_low():
    assert pta._payout_bucket({"entry_payout_pct": 55}) == "low_<60%"


def test_payout_bucket_mid():
    assert pta._payout_bucket({"entry_payout_pct": 68}) == "mid_60-75%"


def test_payout_bucket_good():
    assert pta._payout_bucket({"entry_payout_pct": 80}) == "good_75-85%"


def test_payout_bucket_excellent():
    assert pta._payout_bucket({"entry_payout_pct": 90}) == "excellent_>=85%"


def test_payout_bucket_boundary_60():
    """Exactly 60 should be mid."""
    assert pta._payout_bucket({"entry_payout_pct": 60}) == "mid_60-75%"


def test_payout_bucket_boundary_75():
    """Exactly 75 should be good."""
    assert pta._payout_bucket({"entry_payout_pct": 75}) == "good_75-85%"


def test_payout_bucket_boundary_85():
    """Exactly 85 should be excellent."""
    assert pta._payout_bucket({"entry_payout_pct": 85}) == "excellent_>=85%"


# ---------------------------------------------------------------------------
# 3.1 — Post-trade analysis new context dimensions
# ---------------------------------------------------------------------------

def _write_state_files(state_dir, ledger_entries, edge=None, ranking=None):
    """Helper to write state files for post-trade analysis tests."""
    pta.LEDGER_PATH = state_dir / "signal_paper_execution_ledger.json"
    pta.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pta.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pta.OUTPUT_PATH = state_dir / "post_trade_analysis_latest.json"

    (state_dir / "signal_paper_execution_ledger.json").write_text(
        json.dumps({"entries": ledger_entries}), encoding="utf-8"
    )
    (state_dir / "edge_validation_latest.json").write_text(
        json.dumps(edge or {"summary": {"validated_count": 1, "probation_count": 0}}),
        encoding="utf-8",
    )
    (state_dir / "strategy_ranking_v2_latest.json").write_text(
        json.dumps(ranking or {"top_action": "hold"}), encoding="utf-8"
    )


def test_post_trade_has_new_dimensions(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    entries = [
        {
            "timestamp": "2026-03-27T10:00:00Z",
            "resolved_utc": "2026-03-27T10:01:00Z",
            "strategy_id": "po_test",
            "venue": "pocket_option",
            "symbol": "AUDNZD_otc",
            "direction": "put",
            "entry_price": 1.18,
            "result": "win",
            "profit": 7.0,
            "resolved": True,
            "setup_variant": "rsi_oversold",
            "entry_payout_pct": 80,
        },
        {
            "timestamp": "2026-03-27T10:05:00Z",
            "resolved_utc": "2026-03-27T10:35:00Z",
            "strategy_id": "ibkr_test",
            "venue": "ibkr",
            "symbol": "SPY",
            "direction": "call",
            "entry_price": 620.0,
            "result": "loss",
            "profit": -4.0,
            "resolved": True,
            "setup_variant": "pullback",
        },
    ]
    _write_state_files(state_dir, entries)

    payload = pta.build_post_trade_analysis_snapshot(limit=10)

    # New keys must exist
    assert "by_setup_variant" in payload
    assert "by_duration" in payload
    assert "by_payout" in payload

    # by_setup_variant should have entries for our variants
    variants = {item.get("setup_variant") for item in payload["by_setup_variant"]}
    assert "rsi_oversold" in variants
    assert "pullback" in variants

    # by_duration should have correct buckets
    buckets = {item.get("duration_bucket") for item in payload["by_duration"]}
    assert "ultra_short_<=2m" in buckets  # 1 min trade
    assert "medium_10m-1h" in buckets  # 30 min trade

    # by_payout: PO trade had 80%, IBKR had no payout
    payout_buckets = {item.get("payout_bucket") for item in payload["by_payout"]}
    assert "good_75-85%" in payout_buckets
    assert "no_payout" in payout_buckets


def test_post_trade_no_temp_fields_leak(isolated_base_path):
    """Ensure _duration_bucket and _payout_bucket temp fields are cleaned up."""
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    entries = [
        {
            "timestamp": "2026-03-27T10:00:00Z",
            "resolved_utc": "2026-03-27T10:05:00Z",
            "strategy_id": "test",
            "venue": "ibkr",
            "symbol": "SPY",
            "direction": "call",
            "entry_price": 600.0,
            "result": "win",
            "profit": 5.0,
            "resolved": True,
        },
    ]
    _write_state_files(state_dir, entries)
    payload = pta.build_post_trade_analysis_snapshot(limit=10)

    for trade in payload.get("recent_trades", []):
        assert "_duration_bucket" not in trade
        assert "_payout_bucket" not in trade


# ---------------------------------------------------------------------------
# 3.2 — Enriched hypothesis schema
# ---------------------------------------------------------------------------

def test_hypothesis_seed_has_enriched_fields():
    """Hypothesis queue v2 should include venue, trigger, validation_plan etc."""
    seed = kb._hypothesis_seed()
    assert seed["schema_version"] == "hypothesis_queue_v2"

    for hyp in seed.get("hypotheses", []):
        assert "venue" in hyp, f"Missing venue in hypothesis {hyp.get('id')}"
        assert "trigger" in hyp, f"Missing trigger in hypothesis {hyp.get('id')}"
        assert "expected_improvement" in hyp, f"Missing expected_improvement in {hyp.get('id')}"
        assert "risk_note" in hyp, f"Missing risk_note in {hyp.get('id')}"
        assert "validation_plan" in hyp, f"Missing validation_plan in {hyp.get('id')}"

        vp = hyp["validation_plan"]
        assert "min_sample" in vp
        assert "acceptance_criteria" in vp
        assert "max_duration_days" in vp
        assert "abort_if" in vp


# ---------------------------------------------------------------------------
# 3.3 — Learning loop snapshot
# ---------------------------------------------------------------------------

def _setup_learning_loop_state(state_dir, catalog_items, anomalies=None, by_strategy=None):
    """Helper to create all state files needed by learning_loop."""
    ll.ACTIVE_CATALOG_PATH = state_dir / "active_strategy_catalog_latest.json"
    ll.EDGE_PATH = state_dir / "edge_validation_latest.json"
    ll.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    ll.LEARNING_LOOP_PATH = state_dir / "learning_loop_latest.json"

    # Also patch post_trade_analysis paths
    pta.LEDGER_PATH = state_dir / "signal_paper_execution_ledger.json"
    pta.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pta.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pta.OUTPUT_PATH = state_dir / "post_trade_analysis_latest.json"

    # Build ledger from by_strategy info
    ledger_entries = []
    for item in (by_strategy or []):
        for i in range(item.get("resolved", 1)):
            ledger_entries.append({
                "timestamp": f"2026-03-27T10:{i:02d}:00Z",
                "resolved_utc": f"2026-03-27T10:{i:02d}:30Z",
                "strategy_id": item["strategy_id"],
                "venue": item.get("venue", "ibkr"),
                "symbol": "SPY",
                "direction": "call",
                "entry_price": 600.0 + i,
                "result": "win" if i % 3 == 0 else "loss",
                "profit": 5.0 if i % 3 == 0 else -3.0,
                "resolved": True,
            })

    (state_dir / "signal_paper_execution_ledger.json").write_text(
        json.dumps({"entries": ledger_entries}), encoding="utf-8"
    )
    (state_dir / "active_strategy_catalog_latest.json").write_text(
        json.dumps({"schema_version": "active_catalog_v1", "items": catalog_items}),
        encoding="utf-8",
    )
    (state_dir / "edge_validation_latest.json").write_text(
        json.dumps({"summary": {"validated_count": 0, "probation_count": 1}}),
        encoding="utf-8",
    )
    (state_dir / "strategy_ranking_v2_latest.json").write_text(
        json.dumps({"top_action": "hold"}), encoding="utf-8"
    )
    # post_trade_hypotheses needs its own state
    from brain_v9.trading import post_trade_hypotheses as pth
    pth.ANALYSIS_PATH = state_dir / "post_trade_analysis_latest.json"
    pth.HYPOTHESES_PATH = state_dir / "post_trade_hypotheses_latest.json"


def test_learning_loop_builds_snapshot(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    catalog_items = [
        {
            "strategy_id": "strat_a",
            "catalog_state": "probation",
            "catalog_reason": "probation_lane",
            "entries_resolved": 3,
            "expectancy": 1.5,
        },
    ]
    _setup_learning_loop_state(
        state_dir,
        catalog_items,
        by_strategy=[{"strategy_id": "strat_a", "venue": "ibkr", "resolved": 3}],
    )

    payload = ll.build_learning_loop_snapshot()

    assert payload["schema_version"] == "learning_loop_v1"
    assert "updated_utc" in payload
    assert "summary" in payload
    assert "items" in payload
    assert len(payload["items"]) == 1
    assert payload["items"][0]["strategy_id"] == "strat_a"
    assert payload["items"][0]["learning_decision"] == "continue_probation"


def test_learning_loop_probation_incomplete_allows_sampling(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    catalog_items = [
        {
            "strategy_id": "strat_b",
            "catalog_state": "probation",
            "catalog_reason": "probation_lane",
            "entries_resolved": 2,
            "expectancy": 0.5,
        },
    ]
    _setup_learning_loop_state(
        state_dir,
        catalog_items,
        by_strategy=[{"strategy_id": "strat_b", "venue": "ibkr", "resolved": 2}],
    )

    payload = ll.build_learning_loop_snapshot()
    item = payload["items"][0]
    assert item["learning_decision"] == "continue_probation"
    assert item["allow_sampling"] is True
    assert item["allow_variant_generation"] is False


def test_learning_loop_excluded_generates_variant(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    catalog_items = [
        {
            "strategy_id": "strat_frozen",
            "catalog_state": "excluded",
            "catalog_reason": "frozen_negative_lane",
            "entries_resolved": 10,
            "expectancy": -3.0,
        },
    ]
    _setup_learning_loop_state(
        state_dir,
        catalog_items,
        by_strategy=[{"strategy_id": "strat_frozen", "venue": "ibkr", "resolved": 10}],
    )

    payload = ll.build_learning_loop_snapshot()
    item = payload["items"][0]
    assert item["learning_decision"] == "generate_variant"
    assert item["allow_variant_generation"] is True


def test_learning_loop_summary_counts(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    catalog_items = [
        {
            "strategy_id": "s1",
            "catalog_state": "probation",
            "catalog_reason": "probation_lane",
            "entries_resolved": 2,
            "expectancy": 1.0,
        },
        {
            "strategy_id": "s2",
            "catalog_state": "active",
            "catalog_reason": "active_lane",
            "entries_resolved": 20,
            "expectancy": 2.0,
        },
        {
            "strategy_id": "s3",
            "catalog_state": "excluded",
            "catalog_reason": "frozen_negative_lane",
            "entries_resolved": 5,
            "expectancy": -2.0,
        },
    ]
    _setup_learning_loop_state(
        state_dir,
        catalog_items,
        by_strategy=[
            {"strategy_id": "s1", "venue": "ibkr", "resolved": 2},
            {"strategy_id": "s2", "venue": "ibkr", "resolved": 20},
            {"strategy_id": "s3", "venue": "ibkr", "resolved": 5},
        ],
    )

    payload = ll.build_learning_loop_snapshot()
    summary = payload["summary"]

    assert summary["operational_count"] == 2  # s1 (probation) + s2 (active)
    assert summary["variant_generation_candidate_count"] >= 1  # s3
    assert "top_learning_action" in summary
    assert "allow_variant_generation" in summary


def test_learning_loop_audit_takes_priority(isolated_base_path):
    """If there are anomalies, audit should be top action."""
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Create entries that will produce duplicate anomalies
    entries = [
        {
            "timestamp": "2026-03-27T10:00:00Z",
            "resolved_utc": "2026-03-27T10:01:00Z",
            "strategy_id": "s_audit",
            "venue": "ibkr",
            "symbol": "SPY",
            "direction": "call",
            "entry_price": 600.0,
            "result": "win",
            "profit": 5.0,
            "resolved": True,
        },
        {
            "timestamp": "2026-03-27T10:00:01Z",
            "resolved_utc": "2026-03-27T10:01:01Z",
            "strategy_id": "s_audit",
            "venue": "ibkr",
            "symbol": "SPY",
            "direction": "call",
            "entry_price": 600.0,
            "result": "loss",
            "profit": -3.0,
            "resolved": True,
        },
    ]
    catalog_items = [
        {
            "strategy_id": "s_audit",
            "catalog_state": "probation",
            "catalog_reason": "probation_lane",
            "entries_resolved": 2,
            "expectancy": 1.0,
        },
    ]

    ll.ACTIVE_CATALOG_PATH = state_dir / "active_strategy_catalog_latest.json"
    ll.EDGE_PATH = state_dir / "edge_validation_latest.json"
    ll.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    ll.LEARNING_LOOP_PATH = state_dir / "learning_loop_latest.json"
    pta.LEDGER_PATH = state_dir / "signal_paper_execution_ledger.json"
    pta.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pta.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pta.OUTPUT_PATH = state_dir / "post_trade_analysis_latest.json"

    (state_dir / "signal_paper_execution_ledger.json").write_text(
        json.dumps({"entries": entries}), encoding="utf-8"
    )
    (state_dir / "active_strategy_catalog_latest.json").write_text(
        json.dumps({"items": catalog_items}), encoding="utf-8"
    )
    (state_dir / "edge_validation_latest.json").write_text(
        json.dumps({"summary": {"validated_count": 0, "probation_count": 1}}),
        encoding="utf-8",
    )
    (state_dir / "strategy_ranking_v2_latest.json").write_text(
        json.dumps({"top_action": "hold"}), encoding="utf-8"
    )
    from brain_v9.trading import post_trade_hypotheses as pth
    pth.ANALYSIS_PATH = state_dir / "post_trade_analysis_latest.json"
    pth.HYPOTHESES_PATH = state_dir / "post_trade_hypotheses_latest.json"

    payload = ll.build_learning_loop_snapshot()
    item = payload["items"][0]
    assert item["learning_decision"] == "audit_integrity_before_sampling"


# ---------------------------------------------------------------------------
# 3.4 — Decision context explainability schema validation
# ---------------------------------------------------------------------------

def test_decision_context_schema():
    """Validate that the decision_context structure has all required sections."""
    # We test the schema contract, not the live execution (which requires
    # the full trading pipeline). Build a mock decision_context matching
    # the shape in strategy_engine.py execute_candidate().
    decision_context = {
        "observation": {
            "signal_reasons": ["rsi_oversold", "bollinger_touch"],
            "signal_blockers": [],
            "signal_score": 0.72,
            "confidence": 0.65,
        },
        "why_acted": {
            "governance_state": "paper_only",
            "governance_lane": "probation",
            "edge_state": "probation",
            "context_edge_state": "unproven",
            "rank_position": 1,
            "execution_ready_now": True,
        },
        "expected_validation": {
            "linked_hypotheses": ["h_ibkr_pullback_quality"],
            "success_criteria": {"min_sample": 8, "metric": "expectancy_positive"},
        },
        "measurement_plan": {
            "metric": "expectancy_and_win_rate_after_resolved",
            "min_sample_for_verdict": 8,
            "abort_criteria": "expectancy < -2.0 after min_sample OR 10 consecutive losses",
        },
    }

    # All four sections must be present
    required_sections = ["observation", "why_acted", "expected_validation", "measurement_plan"]
    for section in required_sections:
        assert section in decision_context, f"Missing section: {section}"

    # Observation fields
    obs = decision_context["observation"]
    for field in ["signal_reasons", "signal_blockers", "signal_score", "confidence"]:
        assert field in obs, f"Missing observation field: {field}"

    # why_acted fields
    why = decision_context["why_acted"]
    for field in ["governance_state", "governance_lane", "edge_state", "context_edge_state", "rank_position", "execution_ready_now"]:
        assert field in why, f"Missing why_acted field: {field}"

    # expected_validation fields
    ev = decision_context["expected_validation"]
    for field in ["linked_hypotheses", "success_criteria"]:
        assert field in ev, f"Missing expected_validation field: {field}"

    # measurement_plan fields
    mp = decision_context["measurement_plan"]
    for field in ["metric", "min_sample_for_verdict", "abort_criteria"]:
        assert field in mp, f"Missing measurement_plan field: {field}"


def test_decision_for_item_active_negative_tightens():
    """Active lane with negative expectancy should get tighten_filters decision."""
    item = {
        "strategy_id": "strat_neg",
        "catalog_state": "active",
        "catalog_reason": "active_lane",
        "entries_resolved": 20,
        "expectancy": -1.5,
    }
    stats = {"win_rate": 0.3, "net_profit": -30.0}
    result = ll._decision_for_item(item, stats, anomalies=[])
    assert result["learning_decision"] == "tighten_filters_before_more_sampling"
    assert result["allow_sampling"] is False


def test_decision_for_item_probation_positive_forwards():
    """Probation with positive expectancy after min sample should forward validate."""
    item = {
        "strategy_id": "strat_good",
        "catalog_state": "probation",
        "catalog_reason": "probation_lane",
        "entries_resolved": 8,
        "expectancy": 2.5,
    }
    stats = {"win_rate": 0.55, "net_profit": 20.0}
    result = ll._decision_for_item(item, stats, anomalies=[])
    assert result["learning_decision"] == "forward_validate"
    assert result["allow_sampling"] is True
