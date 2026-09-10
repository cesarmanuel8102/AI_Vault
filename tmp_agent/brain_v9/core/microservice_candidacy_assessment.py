"""Pure R17.1 selective extraction candidacy assessment with no runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


_FORBIDDEN_EFFECTS = frozenset(
    {
        "service_process_start",
        "container_start",
        "deployment",
        "scheduler_mutation",
        "network_fetch",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class MicroserviceCandidacyReceipt:
    component_id: str
    candidate_eligible: bool
    recommended_action: str
    extraction_authorized: bool
    deployment_permitted: bool
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_microservice_candidacy(
    *,
    component_id: str,
    ownership_stable: bool,
    contract_e2e_verified: bool,
    rollback_evidence_verified: bool,
    operational_justification: bool,
    economic_justification: bool,
    shared_filesystem_dependency: bool,
    distributed_runtime_requested: bool,
    deployment_requested: bool,
    scheduler_activation: bool,
    network_call: bool,
    canonical_local_sync: bool,
    live_trading: bool,
    real_money: bool,
    auto_merge: bool,
) -> MicroserviceCandidacyReceipt:
    """Assess one candidate only; it never authorizes extraction or deployment."""
    values = {
        "ownership_stable": ownership_stable,
        "contract_e2e_verified": contract_e2e_verified,
        "rollback_evidence_verified": rollback_evidence_verified,
        "operational_justification": operational_justification,
        "economic_justification": economic_justification,
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
    reasons: list[str] = [
        f"invalid_{name}" for name, value in values.items() if not isinstance(value, bool)
    ]
    if not isinstance(component_id, str) or not component_id or component_id.strip() != component_id:
        reasons.append("invalid_component_id")

    checks = (
        (not ownership_stable, "ownership_stability_required"),
        (not contract_e2e_verified, "contract_e2e_required"),
        (not rollback_evidence_verified, "rollback_evidence_required"),
        (not operational_justification, "operational_justification_required"),
        (not economic_justification, "economic_justification_required"),
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
    candidate_eligible = not denial_reasons
    recommended_action = "R17_2_CONTAINMENT_REVIEW" if candidate_eligible else "REJECT"
    identity = {
        "component_id": component_id,
        "candidate_eligible": candidate_eligible,
        "recommended_action": recommended_action,
        "denial_reasons": denial_reasons,
        "values": values,
    }
    return MicroserviceCandidacyReceipt(
        component_id=component_id,
        candidate_eligible=candidate_eligible,
        recommended_action=recommended_action,
        extraction_authorized=False,
        deployment_permitted=False,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(identity),
    )


def reject_candidacy_effect(operation: str) -> None:
    """Fail closed because R17.1 is an assessment-only front."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("microservice_candidacy_no_effects")
    raise ValueError("unsupported_microservice_candidacy_operation")
