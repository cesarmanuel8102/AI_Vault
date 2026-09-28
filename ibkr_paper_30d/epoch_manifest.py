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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .canonical import sha256_json
from .kernel_manifest import (
    KERNEL_MANIFEST_SCHEMA,
    build_kernel_manifest,
    verify_kernel_manifest,
)


EPOCH_MANIFEST_SCHEMA = "AUTONOMY_EPOCH_MANIFEST_V1"
EPOCH_ID = "AUTONOMY_EPOCH_1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")




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
