"""Pure R19.1 BRAIN-101 certification gate matrix with no runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class CertificationGateMatrixReceipt:
    decision: str
    brain_101_certified: bool
    runtime_permitted: bool
    mandatory_gates: tuple[tuple[str, bool], ...]
    deferred_capabilities: tuple[str, ...]
    denial_reasons: tuple[str, ...]
    receipt_sha256: str


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def assess_brain_101_certification_gate_matrix(
    *,
    security_verified: bool,
    architecture_verified: bool,
    runtime_verified: bool,
    memory_verified: bool,
    operations_verified: bool,
    ux_verified: bool,
    paper_validation_verified: bool,
    persistent_agent_loop_deferred: bool,
    live_trading: bool,
    real_money: bool,
    canonical_local_sync: bool,
    auto_merge: bool,
    runtime_action_requested: bool,
) -> CertificationGateMatrixReceipt:
    """Assess certification evidence while refusing final certification and runtime effects."""
    values = {
        "security_verified": security_verified,
        "architecture_verified": architecture_verified,
        "runtime_verified": runtime_verified,
        "memory_verified": memory_verified,
        "operations_verified": operations_verified,
        "ux_verified": ux_verified,
        "paper_validation_verified": paper_validation_verified,
        "persistent_agent_loop_deferred": persistent_agent_loop_deferred,
        "live_trading": live_trading,
        "real_money": real_money,
        "canonical_local_sync": canonical_local_sync,
        "auto_merge": auto_merge,
        "runtime_action_requested": runtime_action_requested,
    }
    mandatory_gates = (
        ("architecture", architecture_verified),
        ("memory", memory_verified),
        ("operations", operations_verified),
        ("paper_validation", paper_validation_verified),
        ("runtime", runtime_verified),
        ("security", security_verified),
        ("ux", ux_verified),
    )
    reasons = [f"invalid_{name}" for name, value in values.items() if not isinstance(value, bool)]
    reasons.extend(f"{name}_verification_required" for name, verified in mandatory_gates if not verified)
    checks = (
        (not persistent_agent_loop_deferred, "persistent_agent_loop_must_remain_deferred"),
        (live_trading, "live_trading_forbidden"),
        (real_money, "real_money_forbidden"),
        (canonical_local_sync, "canonical_local_sync_forbidden"),
        (auto_merge, "auto_merge_forbidden"),
        (runtime_action_requested, "runtime_action_forbidden"),
    )
    reasons.extend(reason for invalid, reason in checks if invalid)
    denial_reasons = tuple(sorted(set(reasons)))
    decision = "CERTIFICATION_MATRIX_VERIFIED" if not denial_reasons else "REJECT"
    deferred_capabilities = ("persistent_agent_loop",) if persistent_agent_loop_deferred is True else ()
    return CertificationGateMatrixReceipt(
        decision=decision,
        brain_101_certified=False,
        runtime_permitted=False,
        mandatory_gates=mandatory_gates,
        deferred_capabilities=deferred_capabilities,
        denial_reasons=denial_reasons,
        receipt_sha256=_canonical_sha256(
            {
                "decision": decision,
                "brain_101_certified": False,
                "runtime_permitted": False,
                "mandatory_gates": mandatory_gates,
                "deferred_capabilities": deferred_capabilities,
                "denial_reasons": denial_reasons,
                "values": values,
            }
        ),
    )
