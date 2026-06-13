
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / "tmp_agent" / "front_brain_canonical_memory_promotion_scaleup_01"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_required_reports_exist():
    for name in [
        "preflight.json",
        "memory_inventory.json",
        "candidate_scores.json",
        "deduplication_report.json",
        "rollback_snapshot_report.json",
        "shadow_retrieval_smoke.json",
        "final_report.json",
    ]:
        assert (E / name).exists()


def test_no_promotion_needed_keeps_canonical_counts():
    final = read_json(E / "final_report.json")
    safety = read_json(E / "final_safety_verify.json")

    assert final["status"] == "BRAIN_CANONICAL_MEMORY_PROMOTION_SCALEUP_NO_PROMOTION_NEEDED"
    assert final["promotion"]["canonical_promotion_performed"] is False
    assert final["promotion"]["promoted_count"] == 0
    assert safety["semantic_memory_lines"] == 1715
    assert safety["faiss_ids"] == 1616
    assert safety["faiss_ntotal"] == 1616
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False


def test_candidate_scoring_rejected_low_value_templates():
    scores = read_json(E / "candidate_scores.json")
    assert scores["total_candidates"] >= 1
    assert scores["approved_count"] == 0
    assert scores["rejected_count"] == scores["total_candidates"]
    assert all(item["decision"] == "rejected" for item in scores["scores"])


def test_safety_scope_and_governance():
    safety = read_json(E / "final_safety_verify.json")
    assert safety["env_touched"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False
    assert safety["raw_cot_exposed"] is False
    assert safety["secrets_exposed"] is False


def test_roadmap_valid_and_ledger_exists():
    assert isinstance(read_json(ROOT / "ROADMAP_STATUS.json"), dict)
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
