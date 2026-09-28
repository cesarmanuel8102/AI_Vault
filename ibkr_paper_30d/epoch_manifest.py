"""AUTONOMY_EPOCH_1 manifests: immutable kernel + epoch provenance.

The immutable execution kernel manifest enumerates the files that form
the execution authority boundary of the experiment. It is generated from
the repository at runtime (never hardcoded content) so an auditor can
recompute it and prove the kernel matches the epoch that started.

The epoch manifest is observational provenance for an epoch launch: it
records which objective, prompt, tools and policies were in effect. It
must never influence strategy; it documents what existed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, sha256_json


KERNEL_MANIFEST_SCHEMA = "IMMUTABLE_EXECUTION_KERNEL_MANIFEST_V1"
EPOCH_MANIFEST_SCHEMA = "AUTONOMY_EPOCH_MANIFEST_V1"
EPOCH_ID = "AUTONOMY_EPOCH_1"

# The immutable execution kernel: every module that participates in
# PAPER/LIVE boundary enforcement, identity, authorization, execution,
# capital, locking, audit integrity and market-data gating.
IMMUTABLE_KERNEL_FILES: tuple[str, ...] = (
    "ibkr_paper_30d/autonomous_research.py",
    "ibkr_paper_30d/autonomous_runtime.py",
    "ibkr_paper_30d/autonomous_service.py",
    "ibkr_paper_30d/day1_launch.py",
    "ibkr_paper_30d/autonomous_execution.py",
    "ibkr_paper_30d/ibkr_readonly_session.py",
    "ibkr_paper_30d/ibkr_readonly.py",
    "ibkr_paper_30d/ibkr_research_tools.py",
    "ibkr_paper_30d/owner_authorization.py",
    "ibkr_paper_30d/execution_lock.py",
    "ibkr_paper_30d/experiment_control.py",
    "ibkr_paper_30d/experiment_ledger.py",
    "ibkr_paper_30d/risk.py",
    "ibkr_paper_30d/reconciliation.py",
    "ibkr_paper_30d/state_machine.py",
    "ibkr_paper_30d/persistence.py",
    "ibkr_paper_30d/evidence.py",
    "ibkr_paper_30d/market_policy.py",
    "ibkr_paper_30d/market_data.py",
    "ibkr_paper_30d/market_observation.py",
    "ibkr_paper_30d/market_observation_collector.py",
    "ibkr_paper_30d/open_order_management.py",
    "ibkr_paper_30d/auditor.py",
    "ibkr_paper_30d/auditor_gate_v2.py",
    "ibkr_paper_30d/auditor_runtime_v2.py",
    "ibkr_paper_30d/redaction.py",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_kernel_manifest(repo_root: str | Path) -> dict[str, Any]:
    """Hash every immutable kernel file at manifest build time."""

    root = Path(repo_root)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relative in IMMUTABLE_KERNEL_FILES:
        if relative in seen:
            continue
        seen.add(relative)
        target = root / relative
        if not target.exists():
            raise FileNotFoundError(f"kernel file missing: {relative}")
        entries.append(
            {
                "path": relative,
                "sha256": _file_sha256(target),
                "size_bytes": target.stat().st_size,
            }
        )
    return {
        "schema": KERNEL_MANIFEST_SCHEMA,
        "generated_at_utc": _utc_now(),
        "kernel_files": entries,
        "kernel_manifest_sha256": sha256_json(entries),
        "file_count": len(entries),
    }


def verify_kernel_manifest(
    repo_root: str | Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Recompute and compare; used at launch to refuse mutated kernels."""

    current = build_kernel_manifest(repo_root)
    return {
        "schema": "IMMUTABLE_KERNEL_VERIFICATION_V1",
        "verified": current["kernel_manifest_sha256"]
        == manifest.get("kernel_manifest_sha256"),
        "expected_sha256": manifest.get("kernel_manifest_sha256"),
        "actual_sha256": current["kernel_manifest_sha256"],
    }


@dataclass(frozen=True)
class EpochManifestInputs:
    git_commit_sha: str
    model: str
    reasoning_effort: str
    primary_objective_hash: str
    effective_prompt_hash: str
    tool_manifest_hash: str
    immutable_kernel_manifest_hash: str
    market_policy_hash: str | None
    risk_policy_hash: str | None
    authorization_receipt_hash: str | None
    paper_identity_hash: str | None
    quantconnect_capability: str
    self_tooling_enabled: bool
    persistent_workspace_enabled: bool


def build_epoch_manifest(inputs: EpochManifestInputs) -> dict[str, Any]:
    return {
        "schema": EPOCH_MANIFEST_SCHEMA,
        "epoch_id": EPOCH_ID,
        "epoch_start_utc": _utc_now(),
        "git_commit_sha": inputs.git_commit_sha,
        "model": inputs.model,
        "reasoning_effort": inputs.reasoning_effort,
        "primary_objective_hash": inputs.primary_objective_hash,
        "effective_prompt_hash": inputs.effective_prompt_hash,
        "tool_manifest_hash": inputs.tool_manifest_hash,
        "immutable_kernel_manifest_hash": inputs.immutable_kernel_manifest_hash,
        "market_policy_hash": inputs.market_policy_hash,
        "risk_policy_hash": inputs.risk_policy_hash,
        "authorization_receipt_hash": inputs.authorization_receipt_hash,
        "paper_identity_hash": inputs.paper_identity_hash,
        "quantconnect_capability": inputs.quantconnect_capability,
        "self_tooling_enabled": inputs.self_tooling_enabled,
        "persistent_workspace_enabled": inputs.persistent_workspace_enabled,
        "observational_only": True,
    }


def epoch_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_json(manifest)