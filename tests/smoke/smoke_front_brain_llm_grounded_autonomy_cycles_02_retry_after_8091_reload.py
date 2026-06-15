from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_brain_llm_grounded_autonomy_cycles_02_retry_after_8091_reload"


def _json(name: str) -> dict:
    path = EVIDENCE / name
    assert path.exists(), f"missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_preflight_gate_passed_and_prior_summary_exists() -> None:
    preflight = _json("preflight.json")
    assert preflight["hard_gate_pass"] is True
    assert (EVIDENCE / "prior_state_summary.json").exists()
    assert (EVIDENCE / "prior_state_summary.md").exists()


def test_final_report_and_batch_reports_are_consistent() -> None:
    report = _json("final_report.json")
    assert report["status"] in {
        "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_02_RETRY_COMPLETED",
        "FAILED_PROVIDER_STABILITY_GATE",
        "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_02_RETRY_PARTIAL",
    }
    if report["status"] == "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_02_RETRY_COMPLETED":
        assert report["cycles_completed"] >= 30
    assert report["cycles_completed"] >= 10
    for idx in range(1, report["batches_completed"] + 1):
        assert (EVIDENCE / "batches" / f"batch_{idx:02d}.json").exists()
        assert (EVIDENCE / "batches" / f"batch_{idx:02d}.md").exists()


def test_route_never_regressed_to_dry_run() -> None:
    state = _json("cycle_state.json")
    cycles = state["cycles"]
    assert cycles
    assert sum(1 for c in cycles if c.get("dry_run") is True) == 0
    assert all(c.get("route") != "diagnostic_dry_run" for c in cycles)
    successful = [c for c in cycles if c.get("content_non_empty")]
    assert successful
    assert all(c.get("provider_selected") for c in successful)


def test_reports_scores_and_cesar_review_exist() -> None:
    assert (EVIDENCE / "final_report.json").exists()
    assert (EVIDENCE / "final_report.md").exists()
    assert (EVIDENCE / "cesar_review_report.md").exists()
    assert (EVIDENCE / "NEXT_PROMPT_RECOMMENDATION.md").exists()
    assert (EVIDENCE / "score_before.json").exists()
    assert (EVIDENCE / "score_after.json").exists()
    assert (EVIDENCE / "score_delta.md").exists()


def test_semantic_faiss_and_safety_invariants() -> None:
    safety = _json("final_safety_verify.json")
    report = _json("final_report.json")
    assert safety["semantic_lines_before"] == safety["semantic_lines_after"]
    assert safety["faiss_ids_before"] == safety["faiss_ids_after"]
    assert safety["faiss_ntotal_before"] == safety["faiss_ntotal_after"]
    assert safety["semantic_hash_unchanged"] is True
    assert safety["faiss_index_hash_unchanged"] is True
    assert safety["faiss_ids_hash_unchanged"] is True
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False
    assert report["learning"]["canonical_promotions"] == 0
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False
    assert safety["dashboard_status_final_ok"] is True


def test_provider_metrics_present_and_ledger_valid() -> None:
    report = _json("final_report.json")
    provider = report["provider"]
    for key in ["provider_success_rate", "kimi_success_rate", "fallback_rate", "timeout_count", "empty_response_count", "avg_latency_ms", "avg_quality_score"]:
        assert key in provider
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    ledger = ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md"
    assert ledger.exists()
