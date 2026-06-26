"""
Smoke tests for 08F text-deduplicated batch promotion of 24 validated candidates.
Rules:
- Read-only verification only.
- Canonical memory is already promoted; tests assert the resulting state.
- No new candidate writes, no rollback, no queue/staging mutation.
"""
import sys
import json
import hashlib
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss

ROOT = Path("C:/AI_VAULT_CANONICAL")
ARTIFACT_DIR = ROOT / "tmp_agent" / "front_brain_agent_v2_text_dedup_batch_promotion_08f"
SEMANTIC_ROOT = ROOT / "memory" / "semantic"
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"

EXPECTED_PROMOTED_COUNT = 24


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl_records():
    lines = [line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def test_manifest_has_24_candidates():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    assert len(manifest) == EXPECTED_PROMOTED_COUNT
    print("PASS: manifest_has_24_candidates")


def test_manifest_candidate_ids_unique():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    ids = [m["candidate_id"] for m in manifest]
    assert len(ids) == len(set(ids))
    print("PASS: manifest_candidate_ids_unique")


def test_manifest_text_hashes_unique():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    hashes = [m["normalized_text_sha256"] for m in manifest]
    assert len(hashes) == len(set(hashes))
    print("PASS: manifest_text_hashes_unique")


def test_pre_state_exists_with_baseline():
    pre_state = _load_json(ARTIFACT_DIR / "pre_promotion_memory_state.json")
    assert pre_state["baseline"]["jsonl_records"] > 0
    assert pre_state["baseline"]["faiss_ids_count"] > 0
    assert pre_state["baseline"]["faiss_ntotal"] > 0
    assert pre_state["snapshot_dir"]
    print("PASS: pre_state_exists_with_baseline")


def test_post_verify_report_exists():
    assert (ARTIFACT_DIR / "post_promotion_verify.json").exists()
    print("PASS: post_verify_report_exists")


def test_jsonl_increment_is_24():
    verify = _load_json(ARTIFACT_DIR / "post_promotion_verify.json")
    assert verify["jsonl_increment"] == EXPECTED_PROMOTED_COUNT
    assert verify["jsonl_records_after"] == verify["jsonl_records_before"] + EXPECTED_PROMOTED_COUNT
    print("PASS: jsonl_increment_is_24")


def test_faiss_ids_increment_is_24():
    verify = _load_json(ARTIFACT_DIR / "post_promotion_verify.json")
    assert verify["faiss_ids_increment"] == EXPECTED_PROMOTED_COUNT
    assert verify["faiss_ids_after"] == verify["faiss_ids_before"] + EXPECTED_PROMOTED_COUNT
    print("PASS: faiss_ids_increment_is_24")


def test_faiss_ntotal_increment_is_24():
    verify = _load_json(ARTIFACT_DIR / "post_promotion_verify.json")
    assert verify["faiss_ntotal_increment"] == EXPECTED_PROMOTED_COUNT
    assert verify["faiss_ntotal_after"] == verify["faiss_ntotal_before"] + EXPECTED_PROMOTED_COUNT
    print("PASS: faiss_ntotal_increment_is_24")


def test_live_jsonl_and_ids_counts_match_post_verify():
    records = _load_jsonl_records()
    ids = set(json.loads(IDS_PATH.read_text(encoding="utf-8")))
    verify = _load_json(ARTIFACT_DIR / "post_promotion_verify.json")
    # 08F report assertions remain valid for the historical batch
    assert verify["jsonl_increment"] == EXPECTED_PROMOTED_COUNT
    assert verify["faiss_ids_increment"] == EXPECTED_PROMOTED_COUNT
    # Live counts must be >= 08F post-promotion counts and match latest accepted baseline
    assert len(records) >= verify["jsonl_records_after"]
    assert len(ids) >= verify["faiss_ids_after"]
    # Latest accepted post-09B baseline
    assert len(records) == 1795, f"expected 1795 jsonl records, got {len(records)}"
    assert len(ids) == 1786, f"expected 1786 faiss ids, got {len(ids)}"
    print("PASS: live_jsonl_and_ids_counts_match_post_verify")


def test_all_promoted_ids_present_in_jsonl():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    candidate_ids = {m["candidate_id"] for m in manifest}
    records = _load_jsonl_records()
    jsonl_ids = {r.get("id") for r in records}
    assert candidate_ids.issubset(jsonl_ids)
    print("PASS: all_promoted_ids_present_in_jsonl")


def test_all_promoted_ids_present_in_faiss_ids():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    candidate_ids = {m["candidate_id"] for m in manifest}
    ids = set(json.loads(IDS_PATH.read_text(encoding="utf-8")))
    assert candidate_ids.issubset(ids)
    print("PASS: all_promoted_ids_present_in_faiss_ids")


def test_no_duplicate_texts_among_promoted():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    candidate_ids = {m["candidate_id"] for m in manifest}
    records = _load_jsonl_records()
    promoted_records = [r for r in records if r.get("id") in candidate_ids]
    texts = {r.get("text", "").strip() for r in promoted_records}
    assert len(texts) == len(promoted_records) == EXPECTED_PROMOTED_COUNT
    print("PASS: no_duplicate_texts_among_promoted")


def test_no_blank_text_records_among_promoted():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    candidate_ids = {m["candidate_id"] for m in manifest}
    records = _load_jsonl_records()
    promoted_records = [r for r in records if r.get("id") in candidate_ids]
    assert all((r.get("text") or "").strip() for r in promoted_records)
    print("PASS: no_blank_text_records_among_promoted")


def test_promoted_text_hashes_match_manifest():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    records = _load_jsonl_records()
    record_by_id = {r.get("id"): r for r in records}
    for item in manifest:
        text = record_by_id[item["candidate_id"]].get("text", "")
        assert hashlib.sha256(text.strip().encode("utf-8")).hexdigest() == item["normalized_text_sha256"]
    print("PASS: promoted_text_hashes_match_manifest")


def test_retrieval_sample_passed():
    verify = _load_json(ARTIFACT_DIR / "post_promotion_verify.json")
    assert verify["retrieval_sample_passed"] is True
    assert all(verify["retrieval_sample"].values())
    print("PASS: retrieval_sample_passed")


def test_semantic_retrieval_for_each_promoted_text():
    manifest = _load_json(ARTIFACT_DIR / "promotion_manifest_24_text_unique.json")
    mem = get_semantic_memory_faiss()
    for item in manifest:
        hits = mem.search(item["normalized_text"], top_k=5, min_score=0.1)
        hit_ids = {str(h.get("id")) for h in hits}
        assert item["candidate_id"] in hit_ids
    print("PASS: semantic_retrieval_for_each_promoted_text")


def test_batch_promotion_progress_all_succeeded():
    lines = [line for line in (ARTIFACT_DIR / "batch_promotion_progress.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == EXPECTED_PROMOTED_COUNT
    for line in lines:
        entry = json.loads(line)
        assert entry["ok"] is True
        assert entry["promotion_performed"] is True
        assert entry["write_performed"] is True
        assert entry["validation_errors"] == []
    print("PASS: batch_promotion_progress_all_succeeded")


if __name__ == "__main__":
    test_manifest_has_24_candidates()
    test_manifest_candidate_ids_unique()
    test_manifest_text_hashes_unique()
    test_pre_state_exists_with_baseline()
    test_post_verify_report_exists()
    test_jsonl_increment_is_24()
    test_faiss_ids_increment_is_24()
    test_faiss_ntotal_increment_is_24()
    test_live_jsonl_and_ids_counts_match_post_verify()
    test_all_promoted_ids_present_in_jsonl()
    test_all_promoted_ids_present_in_faiss_ids()
    test_no_duplicate_texts_among_promoted()
    test_no_blank_text_records_among_promoted()
    test_promoted_text_hashes_match_manifest()
    test_retrieval_sample_passed()
    test_semantic_retrieval_for_each_promoted_text()
    test_batch_promotion_progress_all_succeeded()
    print("ALL 08F TEXT-DEDUP BATCH PROMOTION 24 TESTS PASSED")
