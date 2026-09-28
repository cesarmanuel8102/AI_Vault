"""Epoch manifest + immutable kernel tests (AUTONOMY_EPOCH_1, no Codex)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.epoch_manifest import (
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
        assert entry["path"].startswith("ibkr_paper_30d/") or entry["path"].endswith(
            ".ps1"
        )
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
    mandate = {"objective": "maximize terminal PAPER equity"}
    bootstrap = {"schema": "AUTONOMY_FIRST_PROCESS_BOOTSTRAP_V1"}
    tools = [{"tool": "WORKSPACE"}]
    risk_policy = {"version": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"}
    inputs = EpochManifestInputs(
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256="b" * 64,
        clock_event_sha256="c" * 64,
        created_at_utc="2026-09-28T13:30:00Z",
        git_commit_sha="a" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        mandate_payload=mandate,
        first_process_bootstrap=bootstrap,
        tool_manifest=tools,
        immutable_kernel_manifest_hash="e" * 64,
        market_policy_sha256="f" * 64,
        risk_policy_payload=risk_policy,
        receipt_sha256={
            "owner_authorization": "1" * 64,
            "paper_identity": "2" * 64,
            "auditor": "3" * 64,
            "market_validation": "4" * 64,
        },
        expected_paper_identity_hash="5" * 64,
        quantconnect_capability="OPTIONAL_AVAILABLE",
        self_tooling_enabled=True,
        persistent_workspace_enabled=True,
    )
    manifest = build_epoch_manifest(inputs)
    assert manifest["epoch_id"] == "AUTONOMY_EPOCH_2"
    assert manifest["definition_sha256"] == "b" * 64
    assert manifest["clock_event_sha256"] == "c" * 64
    assert manifest["git_commit_sha"] == "a" * 40
    assert manifest["self_tooling_enabled"] is True
    assert manifest["persistent_workspace_enabled"] is True
    assert manifest["quantconnect_capability"] == "OPTIONAL_AVAILABLE"
    assert manifest["observational_only"] is True
    assert manifest["manifest_state"] == "CREATED"
    assert manifest["service_started"] is False
    assert manifest["effective_payload"] == {
        "mandate": mandate,
        "first_process_bootstrap": bootstrap,
        "tool_manifest": tools,
    }
    assert manifest["effective_payload_sha256"] == sha256_json(
        manifest["effective_payload"]
    )
    assert manifest["mandate_sha256"] == sha256_json(mandate)
    assert manifest["first_process_bootstrap_sha256"] == sha256_json(bootstrap)
    assert manifest["tool_manifest_sha256"] == sha256_json(tools)
    assert manifest["risk_policy_sha256"] == sha256_json(risk_policy)
    # Hashable canonical JSON.
    digest = epoch_manifest_hash(manifest)
    assert len(digest) == 64
    again = epoch_manifest_hash(json.loads(json.dumps(manifest)))
    assert again == digest


def test_epoch_manifest_does_not_influence_strategy():
    inputs = EpochManifestInputs(
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256="b" * 64,
        clock_event_sha256="c" * 64,
        created_at_utc="2026-09-28T13:30:00Z",
        git_commit_sha="a" * 40,
        model="gpt-5.6-sol",
        reasoning_effort="max",
        mandate_payload={"objective": "maximize terminal PAPER equity"},
        first_process_bootstrap={"schema": "BOOTSTRAP"},
        tool_manifest=[],
        immutable_kernel_manifest_hash="e" * 64,
        market_policy_sha256="f" * 64,
        risk_policy_payload={"version": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        receipt_sha256={},
        expected_paper_identity_hash="3" * 64,
        quantconnect_capability="OPTIONAL_UNAVAILABLE",
        self_tooling_enabled=True,
        persistent_workspace_enabled=True,
    )
    manifest = build_epoch_manifest(inputs)
    text = json.dumps(manifest).lower()
    for forbidden in ("must trade", "strategy", "target sharpe", "quota"):
        assert forbidden not in text, forbidden
