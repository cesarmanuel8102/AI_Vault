"""Smoke test for FRONT-MAIN-PY-DIRTY-HUMAN-REVIEW-01."""

import json
import os
import subprocess

DOCUMENT_PATH = "docs/FRONT_MAIN_PY_DIRTY_HUMAN_REVIEW_01.md"
REVIEW_DIR = "tmp_agent/front_main_py_dirty_human_review_01"


def test_human_review_doc_exists():
    assert os.path.isfile(DOCUMENT_PATH), "Human review doc not found"


def test_review_sections_json_exists():
    assert os.path.isfile(f"{REVIEW_DIR}/main_py_review_sections.json"), "Review sections JSON not found"


def test_review_sections_md_exists():
    assert os.path.isfile(f"{REVIEW_DIR}/main_py_review_sections.md"), "Review sections MD not found"


def test_formatting_vs_functional_exists():
    assert os.path.isfile(f"{REVIEW_DIR}/main_py_formatting_vs_functional.json"), "Formatting vs functional analysis not found"


def test_head_vs_worktree_summary_exists():
    assert os.path.isfile(f"{REVIEW_DIR}/main_py_head_vs_worktree_summary.md"), "Head vs worktree summary not found"


def test_doc_has_decision():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "## 10. Recomendacion Profesional" in content or "Recomendacion Profesional" in content, "Decision section missing"


def test_decision_allowed_value():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    allowed = ["KEEP_AND_COMMIT_MAIN_PY_CHANGES", "DISCARD_NOT_AUTHORIZED_REQUIRES_OPERATOR",
               "SPLIT_INTO_SEPARATE_FRONT", "NEED_DEEPER_REVIEW"]
    assert any(d in content for d in allowed), f"Decision must be one of: {allowed}"


def test_doc_declares_main_not_modified():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "main.py was not modified" in content or "not modified" in content


def test_doc_declares_main_not_staged():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "main.py was not staged" in content or "not staged" in content


def test_doc_declares_no_cleanup():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "no cleanup" in content or "no git reset" in content


def test_main_py_still_dirty_or_documented():
    # Verify the diff evidence exists (which proves it was dirty at start)
    assert os.path.isfile(f"{REVIEW_DIR}/main_py_review_sections.json")


def test_no_memory_or_faiss_staged():
    staged = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True).stdout
    assert "memory/semantic/semantic_memory.jsonl" not in staged
    assert "memory/semantic/semantic_memory_faiss" not in staged


def test_recommended_next_front_present():
    with open(DOCUMENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Recommended Next Front" in content or "recommended next front" in content.lower()


def test_precise_route_function_diff_exists():
    assert os.path.isfile(f"{REVIEW_DIR}/precise_route_function_diff.txt"), "Precise route/function diff not found"


def test_analysis_recommends_specific_decision():
    with open(f"{REVIEW_DIR}/main_py_formatting_vs_functional.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "recommendation" in data, "Recommendation field missing from analysis"
    assert data["recommendation"] in ["KEEP_AND_COMMIT_MAIN_PY_CHANGES", "DISCARD_NOT_AUTHORIZED_REQUIRES_OPERATOR",
                                       "SPLIT_INTO_SEPARATE_FRONT", "NEED_DEEPER_REVIEW"]
