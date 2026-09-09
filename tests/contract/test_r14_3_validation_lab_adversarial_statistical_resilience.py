"""R14.3 contract: deterministic local validation-resilience receipts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides):
    from tmp_agent.brain_v9.core.validation_resilience import evaluate_validation_resilience

    values = {
        "source_kind": "local_file",
        "bootstrap_seed": 17,
        "stale_age_minutes": 5,
        "max_stale_age_minutes": 15,
        "gap_count": 0,
        "max_gap_count": 1,
        "reproducible": True,
    }
    values.update(overrides)
    return evaluate_validation_resilience(**values)


def test_validation_resilience_receipt_is_deterministic_and_immutable():
    receipt = _receipt()
    assert receipt == _receipt()
    assert receipt.accepted is True
    assert len(receipt.receipt_id) == 64
    with pytest.raises(FrozenInstanceError):
        receipt.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"source_kind": "cloud"}, "local_source_required"),
        ({"stale_age_minutes": 16}, "stale_data_detected"),
        ({"gap_count": 2}, "data_gap_detected"),
        ({"reproducible": False}, "reproducibility_required"),
    ],
)
def test_validation_resilience_rejects_external_stale_gap_and_unrepeatable_inputs(overrides, reason):
    receipt = _receipt(**overrides)
    assert receipt.accepted is False
    assert receipt.reason == reason


def test_validation_resilience_rejects_effects_and_declares_no_deploy_evidence():
    from tmp_agent.brain_v9.core.validation_resilience import reject_validation_resilience_effect

    with pytest.raises(ValueError, match="validation_resilience_no_effects"):
        reject_validation_resilience_effect("provider_call")
    evidence = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R14_3_VALIDATION_LAB_ADVERSARIAL_STATISTICAL_RESILIENCE.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_closes_r14_3_and_jit_binds_r15_1_without_deploy():
    manifest = json.loads(
        (ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8")
    )
    closeout = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R14_3_VALIDATION_LAB_ADVERSARIAL_STATISTICAL_RESILIENCE_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["roadmap_items"]["R14.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    successor = manifest["roadmap_items"]["R15.1"]
    assert successor["status"] == "AUTHORIZED_ACTIVE"
    assert successor["dependencies"] == ["R14.3"]
    assert successor["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["successor"]["roadmap_item"] == "R15.1"
    assert all(value is False for value in closeout["runtime_actions"].values())
