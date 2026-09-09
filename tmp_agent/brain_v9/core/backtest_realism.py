"""Pure local receipts for backtest-realism and walk-forward validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class BacktestRealismReceipt:
    receipt_id: str
    accepted: bool
    reason: str | None


def evaluate_backtest_realism(
    *,
    source_kind: str,
    train_end_utc: str,
    validation_start_utc: str,
    fee_bps: float,
    slippage_bps: float,
    latency_ms: int,
    evaluation_mode: str,
) -> BacktestRealismReceipt:
    identity = {
        "source_kind": source_kind,
        "train_end_utc": train_end_utc,
        "validation_start_utc": validation_start_utc,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "latency_ms": latency_ms,
        "evaluation_mode": evaluation_mode,
    }
    if source_kind != "local_file":
        reason = "local_source_required"
    elif train_end_utc >= validation_start_utc:
        reason = "lookahead_detected"
    elif fee_bps <= 0 or slippage_bps <= 0 or latency_ms < 0:
        reason = "cost_model_required"
    elif evaluation_mode != "walk_forward":
        reason = "walk_forward_required"
    else:
        reason = None
    return BacktestRealismReceipt(_digest(identity), reason is None, reason)


def reject_backtest_realism_effect(operation: str) -> None:
    raise ValueError("backtest_realism_no_effects")
