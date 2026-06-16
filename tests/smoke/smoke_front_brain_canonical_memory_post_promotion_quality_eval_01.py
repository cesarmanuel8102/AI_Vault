"""
smoke_front_brain_canonical_memory_post_promotion_quality_eval_01.py
Smoke test for post-promotion quality evaluation front.
"""
import json, os
import pytest

EVIDENCE_DIR = "tmp_agent/front_brain_canonical_memory_post_promotion_quality_eval_01"

def test_01_state_lock_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "state_lock.json"))

def test_02_previous_promotion_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "previous_promotion_verify.json"))

def test_03_canonical_state_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "canonical_state_verify.json"))

def test_04_promoted_record_quality_eval_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "promoted_record_quality_eval.json"))

def test_05_retrieval_quality_eval_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "retrieval_quality_eval.json"))

def test_06_rollback_readiness_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "rollback_readiness_verify.json"))

def test_07_final_safety_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "final_safety_verify.json"))

def test_08_semantic_lines_match():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as f:
        lines = [l for l in f if l.strip()]
    assert len(lines) == 1720

def test_09_faiss_ids_match():
    with open("memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8") as f:
        ids = json.load(f)
    assert len(ids) == 1621

def test_10_faiss_ntotal_match():
    import faiss
    idx = faiss.read_index("memory/semantic/semantic_memory_faiss.index")
    assert idx.ntotal == 1621

def test_11_canonical_promotions_verified_five():
    with open(os.path.join(EVIDENCE_DIR, "previous_promotion_verify.json")) as f:
        data = json.load(f)
    assert data.get("canonical_promotions") == 5

def test_12_additional_promotions_zero():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("additional_promotions_performed") == 0

def test_13_no_rejected_held_duplicate_promoted():
    with open(os.path.join(EVIDENCE_DIR, "previous_promotion_verify.json")) as f:
        data = json.load(f)
    assert data.get("rejected_promoted") == 0
    assert data.get("held_promoted") == 0
    assert data.get("duplicate_promoted") == 0

def test_14_canonical_semantic_not_mutated_this_front():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("canonical_semantic_mutated_this_front") is False

def test_15_faiss_not_mutated_this_front():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("faiss_mutated_this_front") is False

def test_16_no_trading_b8_strategies_touched():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("trading_touched") is False
    assert data.get("b8_touched") is False
    assert data.get("strategies_touched") is False

def test_17_no_secrets_raw_cot():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("secrets_exposed") is False
    assert data.get("raw_cot_exposed") is False

def test_18_roadmap_valid():
    with open("ROADMAP_STATUS.json") as f:
        data = json.load(f)
    assert isinstance(data.get("completed_fronts"), list)

def test_19_ledger_exists():
    assert os.path.isfile("docs/MIGRATION_CONTROL_LEDGER.md")
