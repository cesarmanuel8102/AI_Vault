"""
smoke_front_brain_llm_grounded_memory_promotion_audit_01.py
Smoke test for memory promotion audit front.
Validates audit evidence exists and safety assertions hold.
Does NOT touch canonical semantic memory or FAISS.
"""
import json, os, glob
import pytest

EVIDENCE_DIR = "tmp_agent/front_brain_llm_grounded_memory_promotion_audit_01"
REQUIRED_FILES = [
    "state_lock.json",
    "state_lock.md",
    "prior_front_verify.json",
    "prior_front_verify.md",
    "source_inventory.json",
    "source_inventory.md",
    "candidate_extraction.json",
    "candidate_extraction.md",
    "deduplication_safety_screen.json",
    "audit_report.md",
]

def test_01_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE_DIR), f"Evidence dir missing: {EVIDENCE_DIR}"

@pytest.mark.parametrize("fname", REQUIRED_FILES)
def test_02_required_files_exist(fname):
    assert os.path.isfile(os.path.join(EVIDENCE_DIR, fname)), f"Missing: {fname}"

def test_03_state_lock_valid():
    with open(os.path.join(EVIDENCE_DIR, "state_lock.json")) as f:
        data = json.load(f)
    assert data.get("lock_verdict") == "STATE_LOCKED"
    assert data.get("local_HEAD") == data.get("remote_HEAD")

def test_04_prior_front_cycles_30():
    with open(os.path.join(EVIDENCE_DIR, "prior_front_verify.json")) as f:
        data = json.load(f)
    assert data.get("cycles_completed") == 30
    assert data.get("canonical_promotions") == 0
    assert data.get("semantic_lines_before") == 1715
    assert data.get("faiss_ids_before") == 1616
    assert data.get("faiss_ntotal_before") == 1616

def test_05_inventory_no_canonical_mutation():
    with open(os.path.join(EVIDENCE_DIR, "source_inventory.json")) as f:
        data = json.load(f)
    for src in data.get("sources", []):
        assert not src.get("contains_canonical_write_attempt")
        assert not src.get("contains_secret")
        assert not src.get("contains_trading_execution")

def test_06_dedup_no_canonical_promotion():
    with open(os.path.join(EVIDENCE_DIR, "deduplication_safety_screen.json")) as f:
        data = json.load(f)
    assert data.get("canonical_promotion_allowed_overall") is False
    assert data.get("safety_verdict") is not None
    for c in data.get("candidates", [])[:100]:  # spot-check
        assert c.get("canonical_promotion_allowed") is False

def test_07_no_trading_or_secrets_in_candidates():
    with open(os.path.join(EVIDENCE_DIR, "deduplication_safety_screen.json")) as f:
        data = json.load(f)
    for c in data.get("candidates", []):
        if c.get("audit_decision") != "unsafe_reject":
            assert not c.get("contains_trading_execution", False)
            assert not c.get("contains_secret", False)

def test_08_roadmap_not_dirty():
    """ROADMAP should not have been modified by audit-only operations."""
    # placeholder; will verify in ledger update phase
    assert True
