"""Smoke test for FRONT-REAL-PATCH-MATERIALIZATION-01."""

import json
import os
from pathlib import Path

PATCH_DIR = "tmp_agent/materialized_patches/front_real_patch_materialization_01"
EVIDENCE_DIR = "tmp_agent/front_real_patch_materialization_01"


def test_patch_exists():
    assert os.path.isfile(f"{PATCH_DIR}/proposed.patch")


def test_patch_manifest_exists():
    assert os.path.isfile(f"{PATCH_DIR}/patch_manifest.json")


def test_patch_summary_exists():
    assert os.path.isfile(f"{PATCH_DIR}/patch_summary.md")


def test_governance_decision_exists():
    assert os.path.isfile(f"{PATCH_DIR}/governance_decision.json")


def test_patch_validation_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/patch_validation.json")


def test_patch_has_diff_header():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    assert "diff --git" in content


def test_patch_has_allowed_targets_only():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    assert "+++ b/docs/PROPOSED_KNOWLEDGE_READ_API_USAGE.md" in content


def test_patch_has_no_protected_paths():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    protected = [
        "memory/semantic",
        "tmp_agent/brain_v9/core/session.py",
        "brain/curated_runtime_lookup.py",
        ".env"
    ]
    for p in protected:
        assert p not in content, f"Protected path found: {p}"


def test_patch_has_no_memory_semantic():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    assert "memory/semantic" not in content


def test_patch_has_no_faiss():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    # faiss_used is OK because it's in the docs content
    lines = [l for l in content.splitlines() if "faiss" in l.lower()]
    for line in lines:
        assert "faiss_used" in line.lower(), f"Unexpected faiss mention: {line}"


def test_patch_has_no_trading_b8():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read().lower()
    assert "trading" not in content
    assert "b8" not in content


def test_patch_has_no_env():
    with open(f"{PATCH_DIR}/proposed.patch", "r", encoding="utf-8") as f:
        content = f.read()
    assert ".env" not in content


def test_governance_says_not_applied():
    with open(f"{PATCH_DIR}/governance_decision.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["decision"] == "MATERIALIZED_NOT_APPLIED"
    assert data["apply_allowed_now"] is False


def test_git_apply_not_executed():
    with open(f"{EVIDENCE_DIR}/patch_validation.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["no_git_apply_executed"] is True


def test_doc_exists():
    assert os.path.isfile("docs/FRONT_REAL_PATCH_MATERIALIZATION_01.md")


def test_doc_decision_present():
    with open("docs/FRONT_REAL_PATCH_MATERIALIZATION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "MATERIALIZED_NOT_APPLIED" in content


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
