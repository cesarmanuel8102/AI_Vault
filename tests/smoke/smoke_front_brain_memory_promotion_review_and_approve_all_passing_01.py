"""
smoke_front_brain_memory_promotion_review_and_approve_all_passing_01.py
Smoke test for review-and-approve front.
"""
import json, os
import pytest

EVIDENCE_DIR = "tmp_agent/front_brain_memory_promotion_review_and_approve_all_passing_01"

def test_01_state_lock_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "state_lock.json"))

def test_02_audit_closeout_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "audit_closeout_verify.json"))

def test_03_candidate_review_decisions_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "candidate_review_decisions.json"))

def test_04_approved_manifest_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json"))

def test_05_held_manifest_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "HELD_FOR_MORE_REVIEW.json"))

def test_06_rejected_manifest_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "REJECTED_AFTER_REVIEW.json"))

def test_07_duplicate_manifest_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "DUPLICATES_AFTER_REVIEW.json"))

def test_08_future_plan_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "FUTURE_CANONICAL_PROMOTION_EXECUTION_PLAN.md"))

def test_09_final_safety_verify_exists():
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, "final_safety_verify.json"))

def test_10_approved_have_source_and_reason():
    with open(os.path.join(EVIDENCE_DIR, "APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json")) as f:
        data = json.load(f)
    for c in data.get("approved_for_future_canonical_promotion", []):
        assert c.get("source_path"), f"Missing source_path for {c.get('candidate_id')}"
        assert c.get("approval_reason"), f"Missing approval_reason for {c.get('candidate_id')}"

def test_11_no_duplicates_approved():
    with open(os.path.join(EVIDENCE_DIR, "APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json")) as f:
        data = json.load(f)
    for c in data.get("approved_for_future_canonical_promotion", []):
        assert c.get("final_review_decision") != "duplicate", f"Duplicate approved: {c.get('candidate_id')}"

def test_12_no_unsafe_approved():
    with open(os.path.join(EVIDENCE_DIR, "APPROVED_FOR_FUTURE_CANONICAL_PROMOTION.json")) as f:
        data = json.load(f)
    for c in data.get("approved_for_future_canonical_promotion", []):
        assert not c.get("safety_flags"), f"Unsafe approved: {c.get('candidate_id')} flags={c.get('safety_flags')}"

def test_13_canonical_promotions_zero():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("canonical_promotions") == 0
    assert data.get("canonical_semantic_mutated") is False
    assert data.get("faiss_mutated") is False

def test_14_semantic_faiss_unchanged():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("semantic_lines_before") == data.get("semantic_lines_after")
    assert data.get("faiss_ids_before") == data.get("faiss_ids_after")
    assert data.get("faiss_ntotal_before") == data.get("faiss_ntotal_after")

def test_15_no_trading_b8_strategies_touched():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("trading_touched") is False
    assert data.get("b8_touched") is False
    assert data.get("strategies_touched") is False

def test_16_no_secrets_raw_cot():
    with open(os.path.join(EVIDENCE_DIR, "final_safety_verify.json")) as f:
        data = json.load(f)
    assert data.get("secrets_exposed") is False
    assert data.get("raw_cot_exposed") is False

def test_17_roamap_valid():
    with open("ROADMAP_STATUS.json") as f:
        data = json.load(f)
    assert isinstance(data.get("completed_fronts"), list)
    assert "FRONT-BRAIN-LLM-GROUNDED-AUTONOMY-CYCLES-02-RETRY-AFTER-KIMI-MITIGATION-02" in data["completed_fronts"]

def test_18_ledger_has_checkpoint():
    with open("docs/MIGRATION_CONTROL_LEDGER.md", encoding="utf-8") as f:
        content = f.read()
    assert "FRONT-BRAIN-MEMORY-PROMOTION-REVIEW-AND-APPROVE-ALL-PASSING-01" in content
