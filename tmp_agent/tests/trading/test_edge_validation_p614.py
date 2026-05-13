from __future__ import annotations

from brain_v9.trading.edge_validation import build_edge_validation_snapshot


def _candidate(
    strategy_id: str,
    *,
    governance_state: str = "paper_probe",
    archive_state: str | None = None,
    execution_ready_now: bool = True,
    probation_eligible: bool = True,
    venue_ready: bool = True,
    sample_quality: float = 0.1,
    context_sample_quality: float = 0.1,
    symbol_sample_quality: float = 0.1,
    entries_resolved: int = 1,
    context_entries_resolved: int = 1,
    symbol_entries_resolved: int = 1,
    expectancy: float = 0.1,
    context_expectancy: float = 0.1,
    symbol_expectancy: float = 0.1,
    drawdown_penalty: float = 0.1,
    win_rate: float = 0.6,
    freeze_recommended: bool = False,
    success_criteria: dict | None = None,
) -> dict:
    return {
        "strategy_id": strategy_id,
        "venue": "pocket_option",
        "preferred_symbol": "AUDNZD_otc",
        "preferred_timeframe": "1m",
        "preferred_setup_variant": "base",
        "governance_state": governance_state,
        "context_governance_state": None,
        "archive_state": archive_state,
        "execution_ready_now": execution_ready_now,
        "signal_ready": execution_ready_now,
        "governance_ready": governance_state not in {"frozen", "retired", "rejected"},
        "probation_eligible": probation_eligible,
        "venue_ready": venue_ready,
        "sample_quality": sample_quality,
        "context_sample_quality": context_sample_quality,
        "symbol_sample_quality": symbol_sample_quality,
        "entries_resolved": entries_resolved,
        "context_entries_resolved": context_entries_resolved,
        "symbol_entries_resolved": symbol_entries_resolved,
        "expectancy": expectancy,
        "context_expectancy": context_expectancy,
        "symbol_expectancy": symbol_expectancy,
        "drawdown_penalty": drawdown_penalty,
        "win_rate": win_rate,
        "freeze_recommended": freeze_recommended,
        "signal_confidence": 0.8,
        "success_criteria": success_criteria or {
            "probation_min_resolved_trades": 5,
            "min_resolved_trades": 20,
            "min_expectancy": 0.05,
            "min_win_rate": 0.55,
        },
    }


def test_probation_state_for_low_sample_candidate():
    payload = build_edge_validation_snapshot([_candidate("s1")])
    item = payload["items"][0]
    assert item["edge_state"] == "probation"
    assert item["execution_lane"] == "probation"


def test_validated_state_requires_forward_window_and_positive_expectancy():
    payload = build_edge_validation_snapshot([
        _candidate(
            "s1",
            governance_state="paper_active",
            probation_eligible=False,
            sample_quality=0.50,
            context_sample_quality=0.52,
            symbol_sample_quality=0.40,
            entries_resolved=12,
            context_entries_resolved=12,
            symbol_entries_resolved=8,
            expectancy=0.06,
            context_expectancy=0.08,
            symbol_expectancy=0.04,
        )
    ])
    item = payload["items"][0]
    assert item["forward_validated"] is True
    assert item["validated"] is True
    assert item["edge_state"] == "validated"


def test_promotable_state_requires_material_sample_and_governance_readiness():
    payload = build_edge_validation_snapshot([
        _candidate(
            "s1",
            governance_state="promote_candidate",
            probation_eligible=False,
            sample_quality=0.75,
            context_sample_quality=0.82,
            symbol_sample_quality=0.70,
            entries_resolved=24,
            context_entries_resolved=24,
            symbol_entries_resolved=20,
            expectancy=0.08,
            context_expectancy=0.11,
            symbol_expectancy=0.09,
            drawdown_penalty=0.2,
        )
    ])
    item = payload["items"][0]
    assert item["promotable"] is True
    assert item["edge_state"] == "promotable"
    assert payload["summary"]["promotable_count"] == 1


def test_refuted_state_for_archived_candidate():
    payload = build_edge_validation_snapshot([
        _candidate("s1", archive_state="archived_refuted", execution_ready_now=False, probation_eligible=False)
    ])
    item = payload["items"][0]
    assert item["edge_state"] == "refuted"
    assert item["execution_lane"] == "blocked"


def test_degraded_state_for_negative_expectancy_after_probation():
    payload = build_edge_validation_snapshot([
        _candidate(
            "s1",
            governance_state="paper_active",
            probation_eligible=False,
            sample_quality=0.45,
            context_sample_quality=0.45,
            entries_resolved=10,
            context_entries_resolved=10,
            expectancy=-0.04,
            context_expectancy=-0.03,
            symbol_expectancy=-0.05,
        )
    ])
    item = payload["items"][0]
    assert item["edge_state"] == "degraded"
    assert "non_positive_expectancy" in item["blockers"]
