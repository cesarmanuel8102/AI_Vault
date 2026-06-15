import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "front_brain_llm_grounded_autonomy_cycles_01"


def load_json(name: str):
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_preflight_and_prior_summary_exist():
    preflight = load_json("preflight.json")
    assert preflight["hard_gate_pass"] is True
    assert (EVIDENCE / "prior_state_summary.json").exists()
    assert (EVIDENCE / "prior_state_summary.md").exists()


def test_final_report_and_batch_reports_are_consistent():
    report = load_json("final_report.json")
    assert (EVIDENCE / "final_report.md").exists()
    assert (EVIDENCE / "cesar_review_report.md").exists()
    assert (EVIDENCE / "score_before.json").exists()
    assert (EVIDENCE / "score_after.json").exists()
    assert report["status"] in {
        "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_COMPLETED",
        "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_PARTIAL",
        "FAILED_PROVIDER_STABILITY_GATE",
        "FAILED_SAFETY_MUTATION_STOP",
    }
    batch_files = sorted((EVIDENCE / "batches").glob("batch_*.json"))
    assert len(batch_files) == report["batches_completed"]
    if report["status"] == "BRAIN_LLM_GROUNDED_AUTONOMY_CYCLES_COMPLETED":
        assert report["cycles_completed"] >= 30
    if report["status"] == "FAILED_PROVIDER_STABILITY_GATE":
        assert report["cycles_completed"] >= 10
        assert report["provider"]["fallback_rate"] > 0.50


def test_provider_metrics_present():
    report = load_json("final_report.json")
    provider = report["provider"]
    for key in [
        "primary_provider",
        "kimi_used",
        "provider_success_rate",
        "fallback_rate",
        "timeout_count",
        "empty_response_count",
        "avg_latency_ms",
        "avg_quality_score",
    ]:
        assert key in provider
    assert provider["provider_success_rate"] >= 0.0
    assert provider["fallback_rate"] >= 0.0


def test_canonical_memory_and_faiss_unchanged():
    safety = load_json("final_safety_verify.json")
    assert safety["semantic_lines_before"] == safety["semantic_lines_after"]
    assert safety["faiss_ids_before"] == safety["faiss_ids_after"]
    assert safety["faiss_ntotal_before"] == safety["faiss_ntotal_after"]
    assert safety["semantic_hash_unchanged"] is True
    assert safety["faiss_index_hash_unchanged"] is True
    assert safety["faiss_ids_hash_unchanged"] is True
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False


def test_safety_flags_and_dashboard():
    report = load_json("final_report.json")
    safety = report["safety"]
    assert report["learning"]["canonical_promotions"] == 0
    assert safety["env_touched"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False
    assert safety["raw_cot_exposed"] is False
    assert safety["secrets_exposed"] is False
    assert report["dashboard"]["status_final_ok"] is True
    assert report["dashboard"]["safety_ok"] is True


def test_roadmap_json_and_ledger_exist():
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
