"""R16.1 contract: disabled LiveTradingGate design remains pure and fail-closed."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def _valid_values():
    return {
        "human_final_authority": True,
        "operator_confirmation": True,
        "account_binding": "PAPER-ACCOUNT-001",
        "capital_cap": 1000,
        "loss_cap": 100,
        "symbol": "SPY",
        "strategy": "PAPER_VALIDATION",
        "allowed_symbols": ("SPY",),
        "allowed_strategies": ("PAPER_VALIDATION",),
        "within_time_window": True,
        "kill_switch_engaged": False,
        "preview_only": True,
        "broker_action": False,
        "provider_call": False,
        "network_call": False,
        "runtime_execution": False,
        "scheduler_activation": False,
        "live_trading": False,
        "real_money": False,
    }


def test_disabled_live_trading_gate_emits_deterministic_immutable_preview_receipt():
    from tmp_agent.brain_v9.core.live_trading_gate_design import evaluate_disabled_live_trading_gate

    receipt = evaluate_disabled_live_trading_gate(**_valid_values())
    assert receipt == evaluate_disabled_live_trading_gate(**_valid_values())
    assert receipt.accepted is True
    assert receipt.preview_only is True
    assert receipt.audit_recorded is True
    assert receipt.execution_permitted is False
    assert len(receipt.receipt_id) == 64
    with pytest.raises(FrozenInstanceError):
        receipt.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"human_final_authority": False}, "human_final_authority_required"),
        ({"operator_confirmation": False}, "operator_confirmation_required"),
        ({"account_binding": ""}, "account_binding_required"),
        ({"capital_cap": 0}, "capital_cap_required"),
        ({"loss_cap": 0}, "loss_cap_required"),
        ({"symbol": "QQQ"}, "symbol_not_allowlisted"),
        ({"strategy": "OTHER"}, "strategy_not_allowlisted"),
        ({"within_time_window": False}, "time_window_required"),
        ({"kill_switch_engaged": True}, "kill_switch_engaged"),
        ({"preview_only": False}, "preview_only_required"),
        ({"broker_action": True}, "broker_action_forbidden"),
        ({"provider_call": True}, "provider_call_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"runtime_execution": True}, "runtime_execution_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
    ],
)
def test_disabled_live_trading_gate_fails_closed(overrides, reason):
    from tmp_agent.brain_v9.core.live_trading_gate_design import evaluate_disabled_live_trading_gate

    assert evaluate_disabled_live_trading_gate(**(_valid_values() | overrides)).reason == reason


def test_r16_1_evidence_declares_no_deploy_and_disabled_external_effects():
    import json
    from pathlib import Path

    evidence = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/roadmap/evidence/BRAIN_101_R16_1_DISABLED_LIVE_TRADING_GATE_DESIGN.json").read_text(encoding="utf-8")
    )
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["live_trading_enabled"] is False
    assert evidence["real_money_enabled"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())
