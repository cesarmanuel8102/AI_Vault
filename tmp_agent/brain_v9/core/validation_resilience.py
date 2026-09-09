"""Pure, local-only validation resilience receipts for BRAIN-101 R14.3."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ValidationResilienceReceipt:
    receipt_id: str
    accepted: bool
    reason: str


def _receipt_id(**values: object) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def evaluate_validation_resilience(
    *,
    source_kind: str,
    bootstrap_seed: int,
    stale_age_minutes: int,
    max_stale_age_minutes: int,
    gap_count: int,
    max_gap_count: int,
    reproducible: bool,
) -> ValidationResilienceReceipt:
    """Evaluate supplied local validation metadata without external effects."""
    values = {
        "source_kind": source_kind,
        "bootstrap_seed": bootstrap_seed,
        "stale_age_minutes": stale_age_minutes,
        "max_stale_age_minutes": max_stale_age_minutes,
        "gap_count": gap_count,
        "max_gap_count": max_gap_count,
        "reproducible": reproducible,
    }
    if source_kind != "local_file":
        reason = "local_source_required"
    elif stale_age_minutes > max_stale_age_minutes:
        reason = "stale_data_detected"
    elif gap_count > max_gap_count:
        reason = "data_gap_detected"
    elif not reproducible:
        reason = "reproducibility_required"
    else:
        reason = "accepted"
    return ValidationResilienceReceipt(
        receipt_id=_receipt_id(**values), accepted=reason == "accepted", reason=reason
    )


def reject_validation_resilience_effect(_: str) -> None:
    """R14.3 is receipt-only and never performs external operations."""
    raise ValueError("validation_resilience_no_effects")
