"""Epoch manifest + immutable kernel tests (AUTONOMY_EPOCH_1, no Codex)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibkr_paper_30d.epoch_manifest import (
    EPOCH_ID,
    EpochManifestInputs,
    build_epoch_manifest,
    build_kernel_manifest,
    epoch_manifest_hash,
    verify_kernel_manifest,
)


REPO = Path(__file__).resolve().parents[2]


def test_kernel_manifest_hashes_every_kernel_file():
    manifest = build_kernel_manifest(REPO)
    assert manifest["schema"] == "IMMUTABLE_EXECUTION_KERNEL_MANIFEST_V2"
    assert manifest["file_count"] >= 20
    for entry in manifest["kernel_files"]:
        assert entry["path"].startswith("ibkr_paper_30d/") or entry[
            "path"
        ].endswith(".ps1")
        assert len(entry["sha256"]) == 64
        assert entry["authority_role"]
    # Execution authority files must be in the kernel.
    paths = {entry["path"] for entry in manifest["kernel_files"]}
    for required in (
        "ibkr_paper_30d/autonomous_execution.py",
        "ibkr_paper_30d/ibkr_readonly_session.py",
        "ibkr_paper_30d/owner_authorization.py",
        "ibkr_paper_30d/execution_lock.py",
        "ibkr_paper_30d/risk.py",
        "ibkr_paper_30d/persistence.py",
        "ibkr_paper_30d/experiment_ledger.py",
    ):
        assert required in paths, required


def test_kernel_manifest_verification_detects_mutation(tmp_path):
    manifest = build_kernel_manifest(REPO)
    ok = verify_kernel_manifest(REPO, manifest)
    assert ok["verified"] is True

    tampered = dict(manifest)
    tampered["kernel_manifest_sha256"] = "0" * 64
    bad = verify_kernel_manifest(REPO, tampered)
    assert bad["verified"] is False


def test_epoch_manifest_is_correct_and_hashable():
    inputs = EpochManifestInputs(
        git_commit_sha="a" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        primary_objective_hash="b" * 64,
        effective_prompt_hash="c" * 64,
        tool_manifest_hash="d" * 64,
        immutable_kernel_manifest_hash="e" * 64,
        market_policy_hash="f" * 64,
        risk_policy_hash="1" * 64,
        authorization_receipt_hash="2" * 64,
        paper_identity_hash="3" * 64,
        quantconnect_capability="OPTIONAL_AVAILABLE",
        self_tooling_enabled=True,
        persistent_workspace_enabled=True,
    )
    manifest = build_epoch_manifest(inputs)
    assert manifest["epoch_id"] == EPOCH_ID == "AUTONOMY_EPOCH_1"
    assert manifest["git_commit_sha"] == "a" * 40
    assert manifest["self_tooling_enabled"] is True
    assert manifest["persistent_workspace_enabled"] is True
    assert manifest["quantconnect_capability"] == "OPTIONAL_AVAILABLE"
    assert manifest["observational_only"] is True
    # Hashable canonical JSON.
    digest = epoch_manifest_hash(manifest)
    assert len(digest) == 64
    again = epoch_manifest_hash(json.loads(json.dumps(manifest)))
    assert again == digest


def test_epoch_manifest_does_not_influence_strategy():
    inputs = EpochManifestInputs(
        git_commit_sha="a" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        primary_objective_hash="b" * 64,
        effective_prompt_hash="c" * 64,
        tool_manifest_hash="d" * 64,
        immutable_kernel_manifest_hash="e" * 64,
        market_policy_hash=None,
        risk_policy_hash=None,
        authorization_receipt_hash=None,
        paper_identity_hash=None,
        quantconnect_capability="OPTIONAL_UNAVAILABLE",
        self_tooling_enabled=True,
        persistent_workspace_enabled=True,
    )
    manifest = build_epoch_manifest(inputs)
    text = json.dumps(manifest).lower()
    for forbidden in ("must trade", "strategy", "target sharpe", "quota"):
        assert forbidden not in text, forbidden
