"""R14.1 contract: deterministic local validation data and experiment registry."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _dataset(**overrides):
    from tmp_agent.brain_v9.core.local_validation_registry import register_local_dataset

    values = {
        "dataset_name": "paper-bars-v1",
        "source_kind": "local_file",
        "as_of_utc": "2026-09-09T00:00:00Z",
        "evaluation_cutoff_utc": "2026-09-10T00:00:00Z",
        "content_sha256": "a" * 64,
    }
    values.update(overrides)
    return register_local_dataset(**values)


def test_local_dataset_and_experiment_receipts_are_deterministic_and_immutable():
    from tmp_agent.brain_v9.core.local_validation_registry import register_experiment

    dataset = _dataset()
    experiment = register_experiment(dataset_id=dataset.dataset_id, strategy_id="mean-reversion-v1")
    assert dataset == _dataset()
    assert dataset.accepted is True
    assert experiment.dataset_id == dataset.dataset_id
    assert len(experiment.experiment_id) == 64
    with pytest.raises(FrozenInstanceError):
        dataset.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"source_kind": "cloud"}, "local_source_required"),
        ({"as_of_utc": "2026-09-11T00:00:00Z"}, "lookahead_detected"),
        ({"content_sha256": "bad"}, "content_sha256_invalid"),
    ],
)
def test_cloud_lookahead_and_invalid_provenance_are_rejected(overrides, reason):
    receipt = _dataset(**overrides)
    assert receipt.accepted is False
    assert receipt.reason == reason


def test_registry_rejects_effectful_operations_and_declares_no_deploy_evidence():
    from tmp_agent.brain_v9.core.local_validation_registry import reject_validation_registry_effect

    with pytest.raises(ValueError, match="local_validation_registry_no_effects"):
        reject_validation_registry_effect("network_fetch")
    evidence = json.loads((ROOT / "docs/roadmap/evidence/BRAIN_101_R14_1_LOCAL_VALIDATION_DATA_EXPERIMENT_REGISTRY.json").read_text())
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert all(value is False for value in evidence["runtime_actions"].values())
