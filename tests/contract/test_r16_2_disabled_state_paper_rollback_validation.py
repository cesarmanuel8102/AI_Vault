"""R16.2 contract: validate disabled live state and paper rollback without effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _validate(**overrides):
    from tmp_agent.brain_v9.core.live_trading_gate_validation import (
        validate_disabled_state_paper_rollback,
    )

    values = {
        "human_final_authority": True,
        "paper_only": True,
        "live_trading_enabled": False,
        "real_money_enabled": False,
        "unauthorized_live_attempt": True,
        "paper_rollback_requested": True,
        "kill_switch_engaged": True,
        "broker_action": False,
        "provider_call": False,
        "network_call": False,
        "runtime_execution": False,
        "scheduler_activation": False,
    }
    values.update(overrides)
    return validate_disabled_state_paper_rollback(**values)


def test_disabled_state_paper_rollback_emits_an_immutable_deterministic_receipt():
    first = _validate()
    second = _validate()

    assert first == second
    assert first.validation_passed is True
    assert first.disabled_state_verified is True
    assert first.unauthorized_live_attempt_denied is True
    assert first.paper_rollback_verified is True
    assert first.kill_switch_receipt is True
    assert first.execution_permitted is False
    assert first.denial_reasons == ("unauthorized_live_attempt_denied",)
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.validation_passed = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"human_final_authority": False}, "human_final_authority_required"),
        ({"paper_only": False}, "paper_only_required"),
        ({"live_trading_enabled": True}, "live_trading_must_remain_disabled"),
        ({"real_money_enabled": True}, "real_money_must_remain_disabled"),
        ({"unauthorized_live_attempt": False}, "live_attempt_denial_evidence_required"),
        ({"paper_rollback_requested": False}, "paper_rollback_required"),
        ({"kill_switch_engaged": False}, "kill_switch_receipt_required"),
        ({"broker_action": True}, "broker_action_forbidden"),
        ({"provider_call": True}, "provider_call_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"runtime_execution": True}, "runtime_execution_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
    ],
)
def test_disabled_state_validation_fails_closed_for_every_missing_invariant(overrides, reason):
    receipt = _validate(**overrides)

    assert receipt.validation_passed is False
    assert receipt.execution_permitted is False
    assert reason in receipt.denial_reasons


def test_missing_live_attempt_never_claims_a_live_attempt_was_denied():
    receipt = _validate(unauthorized_live_attempt=False)

    assert receipt.unauthorized_live_attempt_denied is False
    assert "live_attempt_denial_evidence_required" in receipt.denial_reasons
    assert "unauthorized_live_attempt_denied" not in receipt.denial_reasons


@pytest.mark.parametrize(
    "operation",
    (
        "broker_connect",
        "broker_order",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    ),
)
def test_disabled_state_validation_rejects_every_effectful_operation(operation):
    from tmp_agent.brain_v9.core.live_trading_gate_validation import (
        reject_disabled_state_effect,
    )

    with pytest.raises(ValueError, match="disabled_state_validation_no_effects"):
        reject_disabled_state_effect(operation)


def test_evidence_and_module_are_no_deploy_and_external_effect_free():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R16_2_DISABLED_STATE_PAPER_ROLLBACK_VALIDATION.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R16.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["paper_only"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())

    source = (
        ROOT / "tmp_agent/brain_v9/core/live_trading_gate_validation.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "import financial_autonomy",
        "from financial_autonomy",
        "subprocess",
        "requests",
        "httpx",
        "socket",
        "import trading",
        "from trading",
    ):
        assert forbidden not in source
