"""R14.2 contract: deterministic local backtest-realism receipts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides):
    from tmp_agent.brain_v9.core.backtest_realism import evaluate_backtest_realism

    values = {
        "source_kind": "local_file",
        "train_end_utc": "2026-09-01T00:00:00Z",
        "validation_start_utc": "2026-09-02T00:00:00Z",
        "fee_bps": 1.0,
        "slippage_bps": 2.0,
        "latency_ms": 50,
        "evaluation_mode": "walk_forward",
    }
    values.update(overrides)
    return evaluate_backtest_realism(**values)


def test_local_backtest_realism_receipt_is_deterministic_and_immutable():
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
        ({"train_end_utc": "2026-09-02T00:00:00Z"}, "lookahead_detected"),
        ({"fee_bps": 0.0}, "cost_model_required"),
        ({"evaluation_mode": "in_sample"}, "walk_forward_required"),
    ],
)
def test_backtest_realism_rejects_nonlocal_lookahead_costless_and_in_sample_inputs(overrides, reason):
    receipt = _receipt(**overrides)
    assert receipt.accepted is False
    assert receipt.reason == reason


def test_backtest_realism_rejects_effects_and_declares_no_deploy_evidence():
    from tmp_agent.brain_v9.core.backtest_realism import reject_backtest_realism_effect

    with pytest.raises(ValueError, match="backtest_realism_no_effects"):
        reject_backtest_realism_effect("broker_order")
    evidence = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R14_2_BACKTEST_REALISM_WALK_FORWARD_VALIDATION.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_closes_r14_2_and_jit_binds_r14_3_without_deploy():
    manifest = json.loads(
        (ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8")
    )
    closeout = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R14_2_BACKTEST_REALISM_WALK_FORWARD_VALIDATION_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["roadmap_items"]["R14.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    successor = manifest["roadmap_items"]["R14.3"]
    assert successor["status"] == "AUTHORIZED_ACTIVE"
    assert successor["dependencies"] == ["R14.2"]
    assert successor["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["successor"]["roadmap_item"] == "R14.3"
    assert all(value is False for value in closeout["runtime_actions"].values())
