"""Smoke test for FRONT-EXTERNAL-AUDIT-DELTA-RECONCILIATION-01."""

import json
import os
from pathlib import Path

EVIDENCE_DIR = "tmp_agent/front_external_audit_delta_reconciliation_01"


def test_audit_input_inventory_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/audit_input_inventory.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/audit_input_inventory.md")


def test_original_audit_findings_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/original_audit_findings.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/original_audit_findings.md")


def test_completed_fronts_mapping_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/completed_fronts_mapping.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/completed_fronts_mapping.md")


def test_delta_gap_matrix_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/delta_gap_matrix.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/delta_gap_matrix.md")


def test_security_delta_review_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_delta_review.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_delta_review.md")


def test_testing_quality_delta_review_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/testing_quality_delta_review.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/testing_quality_delta_review.md")


def test_architecture_delta_review_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/architecture_delta_review.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/architecture_delta_review.md")


def test_product_console_delta_review_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/product_console_delta_review.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/product_console_delta_review.md")


def test_doc_exists():
    assert os.path.isfile("docs/FRONT_EXTERNAL_AUDIT_DELTA_RECONCILIATION_01.md")


def test_doc_contains_status_categories():
    with open("docs/FRONT_EXTERNAL_AUDIT_DELTA_RECONCILIATION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "closed" in content.lower()
    assert "partial" in content.lower()
    assert "open" in content.lower()


def test_doc_contains_recommended_next_fronts():
    with open("docs/FRONT_EXTERNAL_AUDIT_DELTA_RECONCILIATION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "FRONT-SECURITY-PHASE0-REVERIFY-01" in content
    assert "FRONT-INGESTION-REGISTRY-01" in content
    assert "FRONT-TESTING-CORE-BASELINE-01" in content


def test_no_memory_semantic_staged():
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged, f"memory/semantic staged: {staged}"


def test_no_faiss_staged():
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower(), f"FAISS staged: {staged}"


def test_no_patch_application_executed():
    # This is an audit front; no patch should have been applied
    assert os.path.isfile("tmp_agent/materialized_patches/front_real_patch_materialization_01/proposed.patch")
    # If the patch target file docs/PROPOSED_KNOWLEDGE_READ_API_USAGE.md does NOT exist, patch was not applied
    assert not os.path.isfile("docs/PROPOSED_KNOWLEDGE_READ_API_USAGE.md"), "Patch was unexpectedly applied"


def test_no_trading_or_b8_staged():
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad
