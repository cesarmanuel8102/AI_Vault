"""Smoke test for FRONT-SECURITY-PHASE0-REVERIFY-01."""

import json
import os
import subprocess
from pathlib import Path

EVIDENCE_DIR = "tmp_agent/front_security_phase0_reverify_01"


def test_security_input_inventory_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_input_inventory.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_input_inventory.md")


def test_secrets_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/secrets_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/secrets_reverify.md")


def test_god_mode_p3_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/god_mode_p3_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/god_mode_p3_reverify.md")


def test_selfdev_governance_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/selfdev_governance_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/selfdev_governance_reverify.md")


def test_dev_endpoints_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/dev_endpoints_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/dev_endpoints_reverify.md")


def test_rbac_auth_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/rbac_auth_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/rbac_auth_reverify.md")


def test_patch_application_security_reverify_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/patch_application_security_reverify.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/patch_application_security_reverify.md")


def test_security_delta_matrix_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_delta_matrix.json")
    assert os.path.isfile(f"{EVIDENCE_DIR}/security_delta_matrix.md")


def test_doc_exists():
    assert os.path.isfile("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md")


def test_doc_contains_sec_001():
    with open("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "SEC-001" in content


def test_doc_contains_god_mode_p3():
    with open("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "GOD mode" in content or "P3" in content


def test_doc_contains_rbac():
    with open("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "RBAC" in content


def test_doc_contains_recommended_next_fronts():
    with open("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "FRONT-INGESTION-REGISTRY-01" in content or "FRONT-SECURITY-RBAC-MINIMAL-01" in content


def test_no_memory_semantic_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged, f"memory/semantic staged: {staged}"


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower(), f"FAISS staged: {staged}"


def test_no_patch_application_executed():
    assert os.path.isfile("tmp_agent/materialized_patches/front_real_patch_materialization_01/proposed.patch")
    assert not os.path.isfile("docs/PROPOSED_KNOWLEDGE_READ_API_USAGE.md"), "Patch was unexpectedly applied"


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged, f".env staged: {staged}"


def test_report_redaction_marker_present():
    with open(f"{EVIDENCE_DIR}/secrets_reverify.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("findings"):
        with open("docs/FRONT_SECURITY_PHASE0_REVERIFY_01.md", "r", encoding="utf-8") as f:
            content = f.read()
        assert "REDACTED" in content or "redact" in content.lower()


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0, f"ROADMAP_STATUS.json invalid: {result.stderr}"
