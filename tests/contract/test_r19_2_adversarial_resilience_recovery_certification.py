"""R19.2 contract: adversarial resilience evidence remains pure and no-deploy."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

MANDATORY_GATES = (
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


def _assess(**overrides):
    from tmp_agent.brain_v9.core.brain_101_adversarial_resilience_recovery_certification import (
        assess_adversarial_resilience_recovery_certification,
    )

    values = {f"{gate}_verified": True for gate in MANDATORY_GATES}
    values.update(
        persistent_agent_loop_deferred=True,
        live_trading=False,
        real_money=False,
        canonical_local_sync=False,
        auto_merge=False,
        runtime_action_requested=False,
    )
    values.update(overrides)
    return assess_adversarial_resilience_recovery_certification(**values)


def test_complete_adversarial_matrix_is_immutable_deterministic_and_not_final_certification():
    first, second = _assess(), _assess()
    assert first == second
    assert first.decision == "ADVERSARIAL_RESILIENCE_RECOVERY_VERIFIED"
    assert first.brain_101_certified is False
    assert first.runtime_permitted is False
    assert first.denial_reasons == ()
    assert first.mandatory_gates == tuple((gate, True) for gate in MANDATORY_GATES)
    assert first.deferred_capabilities == ("persistent_agent_loop",)
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"secret_safety_verified": False}, "secret_safety_verification_required"),
        ({"p3_replay_scope_verified": False}, "p3_replay_scope_verification_required"),
        ({"provider_resilience_verified": False}, "provider_resilience_verification_required"),
        ({"broker_paper_resilience_verified": False}, "broker_paper_resilience_verification_required"),
        ({"faiss_resilience_verified": False}, "faiss_resilience_verification_required"),
        ({"duplicate_effect_resilience_verified": False}, "duplicate_effect_resilience_verification_required"),
        ({"kill_switch_verified": False}, "kill_switch_verification_required"),
        ({"persistent_agent_loop_deferred": False}, "persistent_agent_loop_must_remain_deferred"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
        ({"runtime_action_requested": True}, "runtime_action_forbidden"),
        ({"rollback_verified": "true"}, "invalid_rollback_verified"),
    ],
)
def test_adversarial_matrix_fails_closed_for_omitted_gates_or_runtime_effects(overrides, reason):
    receipt = _assess(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.brain_101_certified is False
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


@pytest.mark.parametrize("gate", MANDATORY_GATES)
def test_every_mandatory_adversarial_gate_is_independently_required(gate):
    receipt = _assess(**{f"{gate}_verified": False})
    assert receipt.decision == "REJECT"
    assert f"{gate}_verification_required" in receipt.denial_reasons


def test_evidence_records_all_mandatory_gates_without_runtime_actions():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R19_2_ADVERSARIAL_RESILIENCE_RECOVERY_CERTIFICATION.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["roadmap_item"] == "R19.2"
    assert evidence["decision"] == "ADVERSARIAL_RESILIENCE_RECOVERY_VERIFIED"
    assert evidence["brain_101_certified"] is False
    assert tuple(evidence["mandatory_gates"]) == MANDATORY_GATES
    assert evidence["deferred_capabilities"] == ["persistent_agent_loop"]
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_closes_r19_2_and_jit_binds_r19_3_without_final_certification():
    closeout = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R19_2_ADVERSARIAL_RESILIENCE_RECOVERY_CERTIFICATION_CLOSEOUT.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    scorecard = json.loads((ROOT / "docs/roadmap/BRAIN_101_SCORECARD.json").read_text(encoding="utf-8"))
    assert manifest["roadmap_items"]["R19.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert [item_id for item_id, item in manifest["roadmap_items"].items() if item["status"] == "AUTHORIZED_ACTIVE"] == ["R19.3"]
    binding = manifest["roadmap_items"]["R19.3"]["automation"]
    assert binding["front_id"] == "BRAIN-101-R19-3-FINAL-EVIDENCE-CERTIFICATION-DECISION-01"
    assert binding["work_branch"] == "control-plane/r19-3-final-evidence-certification-decision"
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["closeout"]["risk"] in {"LOW", "MEDIUM"}
    assert closeout["implementation_merge"] == "aca1929abb8e981dadc3caec377bc24bd46bd09d"
    assert closeout["brain_101_certified"] is False
    assert all(value is False for value in closeout["runtime_actions"].values())
    r19 = next(phase for phase in scorecard["phases"] if phase["id"] == "R19")
    assert r19["percent"] == 67
    assert r19["status"] == "OPEN"
