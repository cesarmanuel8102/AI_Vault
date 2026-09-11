"""H1 contract: account for H0 candidates without inventing economic evidence."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
H0_INVENTORY = ROOT / "docs/audit/HIVE_NEXT_H0_STATIC_STRATEGY_INVENTORY.json"
H1_AUDIT = ROOT / "docs/audit/HIVE_H1_EXISTING_SLEEVE_ECONOMIC_AUDIT.md"
H1_MATRIX = ROOT / "docs/audit/HIVE_H1_CANDIDATE_ECONOMIC_MATRIX.json"
H1_GAPS = ROOT / "docs/audit/HIVE_H1_EVIDENCE_GAP_MATRIX.md"
H1_PRIORITIES = ROOT / "docs/audit/HIVE_H1_H2_RESEARCH_PRIORITY.md"

REQUIRED_FIELDS = {
    "candidate_id",
    "source_path",
    "strategy_family",
    "current_status",
    "code_lineage",
    "dataset_lineage",
    "qc_project_lineage",
    "backtest_result_lineage",
    "is_interval",
    "oos_interval",
    "walk_forward_evidence",
    "stress_evidence",
    "paper_evidence",
    "execution_evidence",
    "selector_linkage",
    "sleeve_portfolio_linkage",
    "h0_source_bound",
    "dataset_bound",
    "qc_result_bound",
    "is_bound",
    "oos_bound",
    "walk_forward_bound",
    "stress_bound",
    "cost_model_bound",
    "slippage_bound",
    "paper_bound",
    "sleeve_bound",
    "selector_bound",
    "gross_metrics_status",
    "net_metrics_status",
    "drawdown_status",
    "turnover_status",
    "capacity_status",
    "h1_disposition",
    "h2_research_priority",
    "reason",
    "evidence_refs",
}

ALLOWED_DISPOSITIONS = {
    "EXISTING_ECONOMIC_EVIDENCE_BOUND",
    "PARTIALLY_BOUND",
    "CODE_ONLY",
    "DATA_FEASIBILITY_REQUIRED",
    "RESEARCH_REAUDIT_REQUIRED",
    "REJECT_EARLY",
    "DEFERRED",
}

FORBIDDEN_H2_STATES = {
    "VALIDATED_STANDALONE",
    "SLEEVE_CANDIDATE",
    "PAPER_ELIGIBLE",
}


def test_h1_outputs_account_for_every_h0_candidate_without_h2_promotion():
    for output in (H1_AUDIT, H1_MATRIX, H1_GAPS, H1_PRIORITIES):
        assert output.is_file(), f"missing H1 output: {output.name}"

    h0_inventory = json.loads(H0_INVENTORY.read_text(encoding="utf-8"))
    h1_matrix = json.loads(H1_MATRIX.read_text(encoding="utf-8"))

    assert h1_matrix["schema_version"] == "hive_h1_candidate_economic_matrix_v1"
    assert h1_matrix["h0_source_commit"] == h0_inventory["source_commit"]
    assert h1_matrix["audit_base_sha"] == "9525fdda4cd1c03a5286314ece210175208029d7"
    assert h1_matrix["safety"] == {
        "live_trading": False,
        "real_money": False,
        "qc_executed": False,
        "paper_orders_executed": False,
        "broker_interaction": False,
    }

    h0_ids = {candidate["candidate_id"] for candidate in h0_inventory["candidates"]}
    h1_ids = {candidate["candidate_id"] for candidate in h1_matrix["candidates"]}
    assert h1_ids == h0_ids
    assert len(h1_matrix["candidates"]) == len(h0_ids)

    for candidate in h1_matrix["candidates"]:
        assert REQUIRED_FIELDS <= candidate.keys()
        assert candidate["h0_source_bound"] is True
        assert candidate["h1_disposition"] in ALLOWED_DISPOSITIONS
        assert candidate["h1_disposition"] not in FORBIDDEN_H2_STATES
        assert candidate["current_status"] not in FORBIDDEN_H2_STATES
        assert candidate["dataset_bound"] is False
        assert candidate["qc_result_bound"] is False
        assert candidate["is_bound"] is False
        assert candidate["oos_bound"] is False
        assert candidate["walk_forward_bound"] is False
        assert candidate["stress_bound"] is False
        assert candidate["cost_model_bound"] is False
        assert candidate["slippage_bound"] is False
        assert candidate["paper_bound"] is False
        assert candidate["sleeve_bound"] is False
        assert candidate["selector_bound"] is False
        for field in (
            "dataset_lineage",
            "qc_project_lineage",
            "backtest_result_lineage",
            "is_interval",
            "oos_interval",
            "walk_forward_evidence",
            "stress_evidence",
            "paper_evidence",
            "execution_evidence",
            "selector_linkage",
            "sleeve_portfolio_linkage",
            "gross_metrics_status",
            "net_metrics_status",
            "drawdown_status",
            "turnover_status",
            "capacity_status",
        ):
            assert candidate[field] == "UNKNOWN_UNBOUND"


def test_h1_documents_preserve_the_no_promotion_boundary():
    text = "\n".join(
        output.read_text(encoding="utf-8")
        for output in (H1_AUDIT, H1_GAPS, H1_PRIORITIES)
    )

    for required in (
        "UNKNOWN_UNBOUND",
        "H1_IMPLEMENTATION_AUTHORIZED=true",
        "H2_IMPLEMENTATION_AUTHORIZED=false",
        "LIVE_TRADING=false",
        "REAL_MONEY=false",
        "H1 must not produce VALIDATED_STANDALONE, SLEEVE_CANDIDATE, or PAPER_ELIGIBLE",
    ):
        assert required in text
