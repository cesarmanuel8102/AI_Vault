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
from typing import Any

from .canonical import sha256_json
from .kernel_manifest import (
    KERNEL_MANIFEST_SCHEMA,
    build_kernel_manifest,
    verify_kernel_manifest,
)

EPOCH_MANIFEST_SCHEMA = "AUTONOMY_EPOCH_MANIFEST_V2"


@dataclass(frozen=True)
class EpochManifestInputs:
    epoch_id: str
    definition_sha256: str
    clock_event_sha256: str
    created_at_utc: str
    git_commit_sha: str
    model: str
    reasoning_effort: str
    mandate_payload: dict[str, Any]
    first_process_bootstrap: dict[str, Any]
    tool_manifest: list[dict[str, Any]]
    immutable_kernel_manifest_hash: str
    market_policy_sha256: str
    risk_policy_payload: dict[str, Any]
    receipt_sha256: dict[str, str]
    expected_paper_identity_hash: str
    quantconnect_capability: str
    self_tooling_enabled: bool
    persistent_workspace_enabled: bool
    model_turn_timeout_seconds: int = 600

    def __post_init__(self) -> None:
        value = self.model_turn_timeout_seconds
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 30 <= value <= 600
        ):
            raise ValueError("MODEL_TURN_TIMEOUT_INVALID")


def build_epoch_manifest(inputs: EpochManifestInputs) -> dict[str, Any]:
    effective_payload = {
        "mandate": inputs.mandate_payload,
        "first_process_bootstrap": inputs.first_process_bootstrap,
        "tool_manifest": inputs.tool_manifest,
    }
    unsigned = {
        "schema": EPOCH_MANIFEST_SCHEMA,
        "epoch_id": inputs.epoch_id,
        "definition_sha256": inputs.definition_sha256,
        "clock_event_sha256": inputs.clock_event_sha256,
        "manifest_state": "CREATED",
        "service_started": False,
        "created_at_utc": inputs.created_at_utc,
        "git_commit_sha": inputs.git_commit_sha,
        "model": inputs.model,
        "reasoning_effort": inputs.reasoning_effort,
        "model_turn_timeout_seconds": inputs.model_turn_timeout_seconds,
        "effective_payload": effective_payload,
        "effective_payload_sha256": sha256_json(effective_payload),
        "mandate_sha256": sha256_json(inputs.mandate_payload),
        "first_process_bootstrap_sha256": sha256_json(inputs.first_process_bootstrap),
        "tool_manifest_sha256": sha256_json(inputs.tool_manifest),
        "immutable_kernel_manifest_hash": inputs.immutable_kernel_manifest_hash,
        "market_policy_sha256": inputs.market_policy_sha256,
        "risk_policy": inputs.risk_policy_payload,
        "risk_policy_sha256": sha256_json(inputs.risk_policy_payload),
        "receipt_sha256": dict(sorted(inputs.receipt_sha256.items())),
        "expected_paper_identity_hash": inputs.expected_paper_identity_hash,
        "quantconnect_capability": inputs.quantconnect_capability,
        "self_tooling_enabled": inputs.self_tooling_enabled,
        "persistent_workspace_enabled": inputs.persistent_workspace_enabled,
        "observational_only": True,
    }
    return {**unsigned, "epoch_manifest_sha256": sha256_json(unsigned)}


def epoch_manifest_hash(manifest: dict[str, Any]) -> str:
    return sha256_json(
        {
            key: value
            for key, value in manifest.items()
            if key != "epoch_manifest_sha256"
        }
    )
