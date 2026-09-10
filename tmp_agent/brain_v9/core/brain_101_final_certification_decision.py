"""Pure R19.3 final-evidence decision with no self-certification capability."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class FinalEvidenceCertificationDecisionReceipt:
    decision: str
    brain_101_certified: bool
    runtime_permitted: bool
    human_final_authority_required: bool
    mandatory_gates: tuple[tuple[str, bool], ...]
    deferred_capabilities: tuple[str, ...]
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_final_evidence_certification_decision(
    *,
    r19_1_gate_matrix_verified: bool,
    r19_2_adversarial_resilience_verified: bool,
    all_governed_roadmap_evidence_verified: bool,
    persistent_agent_loop_deferred: bool,
    live_trading: bool,
    real_money: bool,
    canonical_local_sync: bool,
    auto_merge: bool,
    runtime_action_requested: bool,
    certification_claim_requested: bool,
    human_final_authority_asserted: bool,
) -> FinalEvidenceCertificationDecisionReceipt:
    """Verify final evidence while reserving certification to a governed human closeout."""
    mandatory_values = {
        "r19_1_gate_matrix": r19_1_gate_matrix_verified,
        "r19_2_adversarial_resilience": r19_2_adversarial_resilience_verified,
        "governed_roadmap_evidence": all_governed_roadmap_evidence_verified,
    }
    control_values = {
        "persistent_agent_loop_deferred": persistent_agent_loop_deferred,
        "live_trading": live_trading,
        "real_money": real_money,
        "canonical_local_sync": canonical_local_sync,
        "auto_merge": auto_merge,
        "runtime_action_requested": runtime_action_requested,
        "certification_claim_requested": certification_claim_requested,
        "human_final_authority_asserted": human_final_authority_asserted,
    }
    values = {**mandatory_values, **control_values}
    reasons = [f"invalid_{name}_verified" for name, value in mandatory_values.items() if not isinstance(value, bool)]
    reasons.extend(f"invalid_{name}" for name, value in control_values.items() if not isinstance(value, bool))
    reasons.extend(f"{name}_verification_required" for name, value in mandatory_values.items() if value is not True)
    reasons.extend(
        reason
        for invalid, reason in (
            (persistent_agent_loop_deferred is not True, "persistent_agent_loop_must_remain_deferred"),
            (live_trading is not False, "live_trading_forbidden"),
            (real_money is not False, "real_money_forbidden"),
            (canonical_local_sync is not False, "canonical_local_sync_forbidden"),
            (auto_merge is not False, "auto_merge_forbidden"),
            (runtime_action_requested is not False, "runtime_action_forbidden"),
            (certification_claim_requested is not False, "certification_claim_requires_human_final_authority"),
            (human_final_authority_asserted is not False, "human_final_authority_requires_governed_closeout"),
        )
        if invalid
    )
    denial_reasons = tuple(sorted(set(reasons)))
    decision = "FINAL_CERTIFICATION_EVIDENCE_VERIFIED" if not denial_reasons else "REJECT"
    deferred_capabilities = ("persistent_agent_loop",) if persistent_agent_loop_deferred is True else ()
    mandatory_gates = tuple(mandatory_values.items())
    return FinalEvidenceCertificationDecisionReceipt(
        decision=decision,
        brain_101_certified=False,
        runtime_permitted=False,
        human_final_authority_required=True,
        mandatory_gates=mandatory_gates,
        deferred_capabilities=deferred_capabilities,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(
            {
                "decision": decision,
                "brain_101_certified": False,
                "runtime_permitted": False,
                "human_final_authority_required": True,
                "mandatory_gates": mandatory_gates,
                "deferred_capabilities": deferred_capabilities,
                "denial_reasons": denial_reasons,
                "values": values,
            }
        ),
    )
