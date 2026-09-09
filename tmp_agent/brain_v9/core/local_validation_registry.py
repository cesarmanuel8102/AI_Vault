"""Pure local validation dataset and experiment receipt registry."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class LocalDatasetReceipt:
    dataset_id: str
    accepted: bool
    reason: str | None


@dataclass(frozen=True)
class ExperimentReceipt:
    dataset_id: str
    strategy_id: str
    experiment_id: str


def register_local_dataset(*, dataset_name: str, source_kind: str, as_of_utc: str, evaluation_cutoff_utc: str, content_sha256: str) -> LocalDatasetReceipt:
    identity = {"dataset_name": dataset_name, "as_of_utc": as_of_utc, "content_sha256": content_sha256}
    if source_kind != "local_file":
        reason = "local_source_required"
    elif len(content_sha256) != 64 or any(c not in "0123456789abcdef" for c in content_sha256):
        reason = "content_sha256_invalid"
    elif as_of_utc > evaluation_cutoff_utc:
        reason = "lookahead_detected"
    else:
        reason = None
    return LocalDatasetReceipt(_digest(identity), reason is None, reason)


def register_experiment(*, dataset_id: str, strategy_id: str) -> ExperimentReceipt:
    return ExperimentReceipt(dataset_id, strategy_id, _digest({"dataset_id": dataset_id, "strategy_id": strategy_id}))


def reject_validation_registry_effect(operation: str) -> None:
    raise ValueError("local_validation_registry_no_effects")
