"""BR2-2 contract: Brain-side immutable receipt consumer boundary.

Brain may validate and consume immutable receipts produced by HIVE. Brain
must NOT import raw strategy code, mutable QC experiment state, HIVE
optimizer state, or any selector implementation. This module defines ONLY
schema/validator/consumer contracts — no transport, no producer, no
network, no runtime effect.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

_FORBIDDEN_TRANSPORT = frozenset(
    {
        "raw_strategy_code",
        "mutable_qc_experiment_state",
        "hive_optimizer_state",
        "hive_selector_implementation",
        "network_transport",
        "live_trading",
        "real_money",
        "broker_connection",
        "scheduler_mutation",
        "canonical_local_sync",
        "auto_merge",
    }
)


def reject_receipt_transport(operation: str) -> None:
    """Fail closed: nothing mutable or executable may cross this boundary."""
    if operation in _FORBIDDEN_TRANSPORT:
        raise ValueError(f"receipt_boundary_forbidden:{operation}")


@dataclass(frozen=True)
class StrategyValidationReceipt:
    """Immutable HIVE-produced validation outcome consumable by Brain.

    Pure data with provenance bindings. No strategy code, parameters, or
    mutable experiment state may be attached.
    """

    receipt_id: str
    strategy_id: str
    issuer_id: str
    eligibility: str
    validation_window_start: str
    validation_window_end: str
    validation_evidence_sha256: str
    source_commit_sha: str


@dataclass(frozen=True)
class PaperExecutionReceipt:
    """Immutable HIVE-produced paper execution record consumable by Brain."""

    receipt_id: str
    strategy_id: str
    issuer_id: str
    paper_only: bool
    executed_window_start: str
    executed_window_end: str
    execution_evidence_sha256: str
    source_commit_sha: str


def _validate_common(receipt: object, *, expected_type: type) -> None:
    if not isinstance(receipt, expected_type):
        raise ValueError("invalid_receipt_type")
    for field in ("receipt_id", "strategy_id", "issuer_id"):
        _validate_identifier(getattr(receipt, field), field)


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid_{field}")


def _validate_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"invalid_{field}")


def _validate_commit(value: str) -> None:
    if not isinstance(value, str) or not _SHA1.fullmatch(value):
        raise ValueError("invalid_source_commit_sha")


def _validate_window(start: str, end: str) -> None:
    for value, field in ((start, "start"), (end, "end")):
        if not isinstance(value, str) or not _ISO_UTC.fullmatch(value):
            raise ValueError(f"invalid_window_{field}")
    if end < start:
        raise ValueError("invalid_window_order")


def validate_strategy_validation_receipt(receipt: StrategyValidationReceipt) -> StrategyValidationReceipt:
    """Fail-closed validation; returns the immutable receipt unchanged."""
    _validate_common(receipt, expected_type=StrategyValidationReceipt)
    if receipt.eligibility not in ("PAPER_ELIGIBLE", "PAPER_REJECTED"):
        raise ValueError("invalid_eligibility")
    _validate_window(receipt.validation_window_start, receipt.validation_window_end)
    _validate_sha256(receipt.validation_evidence_sha256, "validation_evidence_sha256")
    _validate_commit(receipt.source_commit_sha)
    return receipt


def validate_paper_execution_receipt(receipt: PaperExecutionReceipt) -> PaperExecutionReceipt:
    """Fail-closed validation; a non-paper execution receipt can never pass."""
    _validate_common(receipt, expected_type=PaperExecutionReceipt)
    if receipt.paper_only is not True:
        raise ValueError("paper_only_required")
    _validate_window(receipt.executed_window_start, receipt.executed_window_end)
    _validate_sha256(receipt.execution_evidence_sha256, "execution_evidence_sha256")
    _validate_commit(receipt.source_commit_sha)
    return receipt


def receipt_binding_sha256(receipt: StrategyValidationReceipt | PaperExecutionReceipt) -> str:
    """Canonical byte binding of an immutable receipt for ledger anchoring."""
    payload = json.dumps(
        {field: getattr(receipt, field) for field in receipt.__dataclass_fields__},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(payload.encode("ascii")).hexdigest()