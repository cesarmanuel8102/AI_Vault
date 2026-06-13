
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / "tmp_agent" / "mega_front_brain_autonomy_stability_status_fix_and_verifiable_cycles_rerun_01"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_preflight_and_live_dashboard_ok():
    pre = read_json(E / "preflight.json")
    final = read_json(E / "final_report.json")
    assert pre["hard_gate_pass"] is True
    assert pre["status_ok"] is True
    assert pre["status_http"] == 200
    assert pre["status_latency_ms"] < 5000
    assert final["dashboard"]["final_status_ok"] is True


def test_cycles_and_batches_exist_for_completed_status():
    final = read_json(E / "final_report.json")
    summary = read_json(E / "cycle_summary.json")
    if final["status"] == "BRAIN_AUTONOMY_STABILITY_STATUS_FIX_AND_VERIFIABLE_CYCLES_RERUN_COMPLETED":
        assert final["autonomy"]["cycles_completed"] >= 120
        assert summary["cycles_completed"] >= 120
    assert len(list((E / "batches").glob("batch_*.json"))) >= 12
    assert len(list((E / "batches").glob("batch_*.md"))) >= 12


def test_reports_and_scores_exist():
    assert (E / "final_report.json").exists()
    assert (E / "final_report.md").exists()
    assert (E / "cesar_review_report.md").exists()
    assert (E / "NEXT_PROMPT_RECOMMENDATION.md").exists()
    assert (E / "score_before.json").exists()
    assert (E / "score_after.json").exists()
    assert (E / "score_delta.md").exists()


def test_safety_invariants_hold():
    safety = read_json(E / "final_safety_verify.json")
    assert safety["semantic_memory_lines"] == 1715
    assert safety["faiss_ids"] == 1616
    assert safety["faiss_ntotal"] == 1616
    assert safety["semantic_memory_hash_unchanged"] is True
    assert safety["faiss_index_hash_unchanged"] is True
    assert safety["faiss_ids_hash_unchanged"] is True
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False
    assert safety["dashboard_status_final_ok"] is True
    assert safety["scheduler_final_ok"] is True
    assert safety["autonomy_final_not_stopped"] is True


def test_roadmap_and_ledger_exist_and_valid():
    roadmap = read_json(ROOT / "ROADMAP_STATUS.json")
    assert isinstance(roadmap, dict)
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
