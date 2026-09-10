"""Pure R17.2 containment decision with no distributed runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class MicroserviceContainmentReceipt:
    component_id: str
    decision: str
    containment_required: bool
    extraction_authorized: bool
    deployment_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def decide_microservice_containment(
    *,
    component_id: str,
    candidate_eligible: bool,
    source_evidence_verified: bool,
    feature_flag_required: bool,
    versioned_api_required: bool,
    shared_filesystem_dependency: bool,
    distributed_runtime_requested: bool,
    deployment_requested: bool,
    scheduler_activation: bool,
    network_call: bool,
    canonical_local_sync: bool,
    live_trading: bool,
    real_money: bool,
    auto_merge: bool,
) -> MicroserviceContainmentReceipt:
    """Contain an evidence-backed candidate; never authorize extraction or effects."""
    values = {
        "candidate_eligible": candidate_eligible,
        "source_evidence_verified": source_evidence_verified,
        "feature_flag_required": feature_flag_required,
        "versioned_api_required": versioned_api_required,
        "shared_filesystem_dependency": shared_filesystem_dependency,
        "distributed_runtime_requested": distributed_runtime_requested,
        "deployment_requested": deployment_requested,
        "scheduler_activation": scheduler_activation,
        "network_call": network_call,
        "canonical_local_sync": canonical_local_sync,
        "live_trading": live_trading,
        "real_money": real_money,
        "auto_merge": auto_merge,
    }
    reasons = [
        f"invalid_{name}" for name, value in values.items() if not isinstance(value, bool)
    ]
    if not isinstance(component_id, str) or not component_id or component_id.strip() != component_id:
        reasons.append("invalid_component_id")

    checks = (
        (not candidate_eligible, "eligible_candidate_required"),
        (not source_evidence_verified, "source_evidence_required"),
        (not feature_flag_required, "feature_flag_required"),
        (not versioned_api_required, "versioned_api_required"),
        (shared_filesystem_dependency, "shared_filesystem_dependency_forbidden"),
        (distributed_runtime_requested, "distributed_runtime_forbidden"),
        (deployment_requested, "deployment_forbidden"),
        (scheduler_activation, "scheduler_activation_forbidden"),
        (network_call, "network_call_forbidden"),
        (canonical_local_sync, "canonical_local_sync_forbidden"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
        (auto_merge, "auto_merge_forbidden"),
    )
    reasons.extend(reason for invalid, reason in checks if invalid)
    denial_reasons = tuple(sorted(set(reasons)))
    decision = "JUSTIFIABLY_DEFERRED" if not denial_reasons else "REJECT"
    identity = {
        "component_id": component_id,
        "decision": decision,
        "containment_required": True,
        "extraction_authorized": False,
        "deployment_permitted": False,
        "denial_reasons": denial_reasons,
        "values": values,
    }
    return MicroserviceContainmentReceipt(
        component_id=component_id,
        decision=decision,
        containment_required=True,
        extraction_authorized=False,
        deployment_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(identity),
    )
