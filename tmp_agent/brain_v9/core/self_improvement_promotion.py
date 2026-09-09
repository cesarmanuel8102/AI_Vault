"""Deterministic, human-authorized promotion decisions for BRAIN-101 R10.3."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_EFFECTS = frozenset(
    {
        "patch_apply",
        "filesystem_write",
        "runtime_mutation",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class PromotionDecision:
    proposal_id: str
    proposal_sha256: str
    human_approval_id: str
    human_final_authority: bool
    apply_permitted: bool
    decision_sha256: str


@dataclass(frozen=True)
class RollbackReceipt:
    decision_sha256: str
    rollback_required: bool
    receipt_sha256: str


@dataclass(frozen=True)
class PromotionGateResult:
    decision: PromotionDecision
    rollback_receipt: RollbackReceipt


def _canonical_sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("ascii")).hexdigest()


def evaluate_self_improvement_promotion(
    *,
    proposal_id: str,
    proposal_sha256: str,
    human_approval_id: str,
    approved_proposal_sha256: str,
) -> PromotionGateResult:
    """Seal an explicit Owner decision; never apply the candidate it evaluates."""
    if not isinstance(proposal_id, str) or not _IDENTIFIER.fullmatch(proposal_id):
        raise ValueError("invalid_proposal_id")
    if not isinstance(proposal_sha256, str) or not _SHA256.fullmatch(proposal_sha256):
        raise ValueError("invalid_proposal_sha256")
    if not isinstance(human_approval_id, str) or not _IDENTIFIER.fullmatch(human_approval_id):
        raise ValueError("invalid_human_approval_id")
    if approved_proposal_sha256 != proposal_sha256:
        raise ValueError("human_approval_provenance_mismatch")

    decision_payload = {
        "apply_permitted": False,
        "human_approval_id": human_approval_id,
        "human_final_authority": True,
        "proposal_id": proposal_id,
        "proposal_sha256": proposal_sha256,
    }
    decision = PromotionDecision(
        **decision_payload,
        decision_sha256=_canonical_sha256(decision_payload),
    )
    receipt_payload = {
        "decision_sha256": decision.decision_sha256,
        "rollback_required": True,
    }
    return PromotionGateResult(
        decision=decision,
        rollback_receipt=RollbackReceipt(
            **receipt_payload,
            receipt_sha256=_canonical_sha256(receipt_payload),
        ),
    )


def reject_promotion_effect(operation: str) -> None:
    """Fail closed: R10.3 may decide and record rollback only, never cause effects."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("promotion_gate_only")
    raise ValueError("unsupported_promotion_operation")
