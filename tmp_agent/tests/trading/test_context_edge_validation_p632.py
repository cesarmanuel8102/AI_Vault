from __future__ import annotations

from brain_v9.trading.context_edge_validation import build_context_edge_validation_snapshot


def _candidate(
    strategy_id: str,
    *,
    governance_state: str = "paper_probe",
    archive_state: str | None = None,
    signal_ready: bool = True,
    execution_ready_now: bool = True,
    probation_eligible: bool = True,
    current_context_entries_resolved: int = 0,
    current_context_sample_quality: float = 0.0,
    current_context_expectancy: float = 0.0,
    success_criteria: dict | None = None,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": "pocket_option",
        "preferred_symbol": "AUDNZD_otc",
        "preferred_timeframe": "1m",
        "preferred_setup_variant": "base",
        "current_context_key": f"pocket_option::{strategy_id}::AUDNZD_otc::1m::base",
        "governance_state": governance_state,
        "archive_state": archive_state,
        "freeze_recommended": False,
        "signal_ready": signal_ready,
        "execution_ready_now": execution_ready_now,
        "probation_eligible": probation_eligible,
        "current_context_entries_resolved": current_context_entries_resolved,
        "current_context_sample_quality": current_context_sample_quality,
        "current_context_expectancy": current_context_expectancy,
        "success_criteria": success_criteria or {
            "probation_min_resolved_trades": 5,
            "min_resolved_trades": 20,
            "min_expectancy": 0.05,
        },
    }


def test_unproven_context_only_allows_probation():
    payload = build_context_edge_validation_snapshot([_candidate("s1")])
    item = payload["items"][0]
    assert item["current_context_edge_state"] == "unproven"
    assert item["current_context_execution_allowed"] is True
    assert item["decision_impact"] == "probation_only"


def test_contradicted_context_blocks_execution():
    payload = build_context_edge_validation_snapshot([
        _candidate(
            "s1",
            current_context_entries_resolved=6,
            current_context_sample_quality=0.20,
            current_context_expectancy=-0.03,
            probation_eligible=True,
        )
    ])
    item = payload["items"][0]
    assert item["current_context_edge_state"] == "contradicted"
    assert item["current_context_execution_allowed"] is False
    assert "current_context_non_positive_expectancy" in item["blockers"]


def test_validated_context_allows_standard_execution():
    payload = build_context_edge_validation_snapshot([
        _candidate(
            "s1",
            governance_state="paper_active",
            probation_eligible=False,
            current_context_entries_resolved=12,
            current_context_sample_quality=0.35,
            current_context_expectancy=0.08,
        )
    ])
    item = payload["items"][0]
    assert item["current_context_edge_state"] == "validated"
    assert item["current_context_execution_allowed"] is True
    assert item["decision_impact"] == "allow_standard_execution"
