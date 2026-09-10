"""Pure R19.2 adversarial resilience certification with no runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


_MANDATORY_GATE_NAMES = (
    "secret_safety",
    "p3_replay_scope",
    "prompt_resilience",
    "provider_resilience",
    "github_resilience",
    "broker_paper_resilience",
    "disk_resilience",
    "json_resilience",
    "faiss_resilience",
    "stale_data_resilience",
    "duplicate_effect_resilience",
    "crash_recovery",
    "scheduler_resilience",
    "rollback",
    "restore",
    "kill_switch",
)


@dataclass(frozen=True)
class AdversarialResilienceRecoveryCertificationReceipt:
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


def assess_adversarial_resilience_recovery_certification(
    *,
    secret_safety_verified: bool,
    p3_replay_scope_verified: bool,
    prompt_resilience_verified: bool,
    provider_resilience_verified: bool,
    github_resilience_verified: bool,
    broker_paper_resilience_verified: bool,
    disk_resilience_verified: bool,
    json_resilience_verified: bool,
    faiss_resilience_verified: bool,
    stale_data_resilience_verified: bool,
    duplicate_effect_resilience_verified: bool,
    crash_recovery_verified: bool,
    scheduler_resilience_verified: bool,
    rollback_verified: bool,
    restore_verified: bool,
    kill_switch_verified: bool,
    persistent_agent_loop_deferred: bool,
    live_trading: bool,
    real_money: bool,
    canonical_local_sync: bool,
    auto_merge: bool,
    runtime_action_requested: bool,
) -> AdversarialResilienceRecoveryCertificationReceipt:
    """Validate certification evidence without permitting runtime effects."""
    verification_values = {
        name: value
        for name, value in (
            ("secret_safety", secret_safety_verified),
            ("p3_replay_scope", p3_replay_scope_verified),
            ("prompt_resilience", prompt_resilience_verified),
            ("provider_resilience", provider_resilience_verified),
            ("github_resilience", github_resilience_verified),
            ("broker_paper_resilience", broker_paper_resilience_verified),
            ("disk_resilience", disk_resilience_verified),
            ("json_resilience", json_resilience_verified),
            ("faiss_resilience", faiss_resilience_verified),
            ("stale_data_resilience", stale_data_resilience_verified),
            ("duplicate_effect_resilience", duplicate_effect_resilience_verified),
            ("crash_recovery", crash_recovery_verified),
            ("scheduler_resilience", scheduler_resilience_verified),
            ("rollback", rollback_verified),
            ("restore", restore_verified),
            ("kill_switch", kill_switch_verified),
        )
    }
    control_values = {
        "persistent_agent_loop_deferred": persistent_agent_loop_deferred,
        "live_trading": live_trading,
        "real_money": real_money,
        "canonical_local_sync": canonical_local_sync,
        "auto_merge": auto_merge,
        "runtime_action_requested": runtime_action_requested,
    }
    all_values = {**verification_values, **control_values}
    reasons = [f"invalid_{name}_verified" for name, value in verification_values.items() if not isinstance(value, bool)]
    reasons.extend(f"invalid_{name}" for name, value in control_values.items() if not isinstance(value, bool))
    mandatory_gates = tuple((name, verification_values[name]) for name in _MANDATORY_GATE_NAMES)
    reasons.extend(f"{name}_verification_required" for name, verified in mandatory_gates if verified is not True)
    reasons.extend(
        reason
        for invalid, reason in (
            (persistent_agent_loop_deferred is not True, "persistent_agent_loop_must_remain_deferred"),
            (live_trading is not False, "live_trading_forbidden"),
            (real_money is not False, "real_money_forbidden"),
            (canonical_local_sync is not False, "canonical_local_sync_forbidden"),
            (auto_merge is not False, "auto_merge_forbidden"),
            (runtime_action_requested is not False, "runtime_action_forbidden"),
        )
        if invalid
    )
    denial_reasons = tuple(sorted(set(reasons)))
    decision = "ADVERSARIAL_RESILIENCE_RECOVERY_VERIFIED" if not denial_reasons else "REJECT"
    deferred_capabilities = ("persistent_agent_loop",) if persistent_agent_loop_deferred is True else ()
    return AdversarialResilienceRecoveryCertificationReceipt(
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
                "values": all_values,
            }
        ),
    )
