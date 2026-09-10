"""R19.1 contract: deterministic certification gates without runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _assess(**overrides):
    from tmp_agent.brain_v9.core.brain_101_certification_gate_matrix import (
        assess_brain_101_certification_gate_matrix,
    )

    values = {
        "security_verified": True,
        "architecture_verified": True,
        "runtime_verified": True,
        "memory_verified": True,
        "operations_verified": True,
        "ux_verified": True,
        "paper_validation_verified": True,
        "persistent_agent_loop_deferred": True,
        "live_trading": False,
        "real_money": False,
        "canonical_local_sync": False,
        "auto_merge": False,
        "runtime_action_requested": False,
    }
    values.update(overrides)
    return assess_brain_101_certification_gate_matrix(**values)


def test_complete_matrix_is_immutable_deterministic_and_not_final_certification():
    first, second = _assess(), _assess()
    assert first == second
    assert first.decision == "CERTIFICATION_MATRIX_VERIFIED"
    assert first.brain_101_certified is False
    assert first.runtime_permitted is False
    assert first.denial_reasons == ()
    assert first.deferred_capabilities == ("persistent_agent_loop",)
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"security_verified": False}, "security_verification_required"),
        ({"architecture_verified": False}, "architecture_verification_required"),
        ({"runtime_verified": False}, "runtime_verification_required"),
        ({"memory_verified": False}, "memory_verification_required"),
        ({"operations_verified": False}, "operations_verification_required"),
        ({"ux_verified": False}, "ux_verification_required"),
        ({"paper_validation_verified": False}, "paper_validation_verification_required"),
        ({"persistent_agent_loop_deferred": False}, "persistent_agent_loop_must_remain_deferred"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
        ({"runtime_action_requested": True}, "runtime_action_forbidden"),
        ({"security_verified": "true"}, "invalid_security_verified"),
    ],
)
def test_matrix_fails_closed_for_incomplete_gates_or_disallowed_effects(overrides, reason):
    receipt = _assess(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.brain_101_certified is False
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_records_truthful_deferred_inventory_without_runtime_actions():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R19_1_CERTIFICATION_GATE_MATRIX.json").read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R19.1"
    assert evidence["decision"] == "CERTIFICATION_MATRIX_VERIFIED"
    assert evidence["brain_101_certified"] is False
    assert evidence["mandatory_gates"] == {
        "architecture": True,
        "memory": True,
        "operations": True,
        "paper_validation": True,
        "runtime": True,
        "security": True,
        "ux": True,
    }
    assert evidence["deferred_capabilities"] == ["persistent_agent_loop"]
    assert all(value is False for value in evidence["runtime_actions"].values())
