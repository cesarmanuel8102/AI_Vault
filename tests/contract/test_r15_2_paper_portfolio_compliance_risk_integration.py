"""R15.2 contract: deterministic paper-only portfolio compliance and risk receipts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides):
    from tmp_agent.brain_v9.core.paper_portfolio_compliance_risk_integration import (
        evaluate_paper_portfolio_compliance_risk,
    )

    values = {
        "portfolio_id": "paper-portfolio-001",
        "proposed_weight_bps": 1200,
        "risk_limit_bps": 1500,
        "compliance_approved": True,
        "audit_event_id": "paper-audit-001",
        "rollback_reference": "paper-rollback-001",
        "paper_only": True,
        "broker_action": False,
        "provider_call": False,
        "network_call": False,
        "runtime_execution": False,
        "scheduler_activation": False,
        "live_trading": False,
        "real_money": False,
    }
    values.update(overrides)
    return evaluate_paper_portfolio_compliance_risk(**values)


def test_paper_portfolio_compliance_risk_receipt_is_deterministic_and_immutable():
    receipt = _receipt()
    assert receipt == _receipt()
    assert receipt.accepted is True
    assert receipt.compliance_status == "APPROVED"
    assert receipt.risk_status == "WITHIN_LIMIT"
    assert receipt.audit_recorded is True
    assert receipt.rollback_validated is True
    assert receipt.paper_only is True
    assert len(receipt.receipt_id) == 64
    with pytest.raises(FrozenInstanceError):
        receipt.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"paper_only": False}, "paper_only_required"),
        ({"proposed_weight_bps": 1501}, "risk_limit_exceeded"),
        ({"compliance_approved": False}, "compliance_rejected"),
        ({"audit_event_id": ""}, "audit_event_required"),
        ({"rollback_reference": ""}, "rollback_reference_required"),
        ({"broker_action": True}, "broker_action_forbidden"),
        ({"provider_call": True}, "provider_action_forbidden"),
        ({"network_call": True}, "network_action_forbidden"),
        ({"runtime_execution": True}, "runtime_execution_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
    ],
)
def test_paper_portfolio_compliance_risk_fails_closed(overrides, reason):
    receipt = _receipt(**overrides)
    assert receipt.accepted is False
    assert receipt.reason == reason


def test_paper_portfolio_compliance_risk_rejects_effects_and_declares_no_deploy_evidence():
    from tmp_agent.brain_v9.core.paper_portfolio_compliance_risk_integration import (
        reject_paper_portfolio_compliance_risk_effect,
    )

    with pytest.raises(ValueError, match="paper_portfolio_compliance_risk_no_effects"):
        reject_paper_portfolio_compliance_risk_effect("broker_order")
    evidence = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R15_2_PAPER_PORTFOLIO_COMPLIANCE_RISK_INTEGRATION.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert all(value is False for value in evidence["runtime_actions"].values())
