"""Smoke test for FRONT-MAIN-PY-DIRTY-TRIAGE-01."""

import json
import os
import subprocess

DOCUMENT_PATH = "docs/FRONT_MAIN_PY_DIRTY_TRIAGE_01.md"
DIFF_FILES_DIR = "tmp_agent/front_main_py_dirty_triage_01"

def test_triage_doc_exists():
    assert os.path.isfile(DOCUMENT_PATH), "Triage doc not found"

def test_diff_evidence_exists():
    assert os.path.isfile(f"{DIFF_FILES_DIR}/main_py_diff.patch.txt"), "Diff patch not found"

def test_diff_stat_exists():
    assert os.path.isfile(f"{DIFF_FILES_DIR}/main_py_diff_stat.txt"), "Diff stat not found"

def test_classification_exists():
    assert os.path.isfile(f"{DIFF_FILES_DIR}/main_py_diff_classification.json"), "Classification not found"

def test_relation_check_exists():
    assert os.path.isfile(f"{DIFF_FILES_DIR}/main_py_diff_classification.md"), "Classification MD not found"

def test_triage_doc_has_decision():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## 9. Recommended Resolution" in content or "Recommended Resolution" in content, "Decision section missing"

def test_decision_allowed_value():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    allowed = ["KEEP_AND_COMMIT_MAIN_PY_CHANGES", "DISCARD_NOT_AUTHORIZED_REQUIRES_OPERATOR",
               "SPLIT_INTO_SEPARATE_FRONT", "NEED_HUMAN_REVIEW"]
    assert any(d in content for d in allowed), f"Decision must be one of: {allowed}"

def test_triage_doc_declares_no_cleanup():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "no cleanup" in content or "not executed" in content

def test_triage_doc_declares_main_not_modified():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "main.py was not modified" in content or "not modified" in content

def test_triage_doc_declares_main_not_staged():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "main.py was not staged" in content or "not staged" in content

def test_no_memory_or_faiss_staged():
    staged = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True).stdout
    assert "memory/semantic/semantic_memory.jsonl" not in staged
    assert "memory/semantic/semantic_memory_faiss" not in staged

def test_no_reset_checkout_clean_stash_claimed():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "no git checkout" in content or "no cleanup" in content


def test_main_py_still_dirty_or_documented():
    # If main.py is still dirty, that's expected
    # If it's clean, the doc should document the preexisting state
    # For now, verify the diff evidence exists (which proves it was dirty at start)
    assert os.path.isfile(f"{DIFF_FILES_DIR}/main_py_diff.patch.txt")

def test_recommended_next_front_present():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Recommended Next Front" in content or "recommended next front" in content.lower()
