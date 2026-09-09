"""R11.2 contract: paper-only financial autonomy audit and rollback remain inert."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_paper_only_audit_emits_deterministic_immutable_audit_and_rollback_receipts():
    from tmp_agent.brain_v9.core.financial_autonomy_paper_audit import (
        evaluate_paper_only_financial_autonomy_audit,
    )

    kwargs = {
        "audit_id": "r11_2_audit_001",
        "broker_gateway_id": "paper_gateway_001",
        "risk_gate_state": "PAPER_ONLY_APPROVED",
    }
    first = evaluate_paper_only_financial_autonomy_audit(**kwargs)
    second = evaluate_paper_only_financial_autonomy_audit(**kwargs)

    assert first == second
    assert first.audit_event.audit_id == "r11_2_audit_001"
    assert first.audit_event.broker_gateway_id == "paper_gateway_001"
    assert first.audit_event.risk_gate_state == "PAPER_ONLY_APPROVED"
    assert first.audit_event.paper_only is True
    assert first.audit_event.broker_connection_permitted is False
    assert first.audit_event.order_action_permitted is False
    assert first.audit_event.provider_calls_permitted is False
    assert first.audit_event.network_permitted is False
    assert first.rollback_receipt.rollback_validated is True
    assert first.rollback_receipt.runtime_change_applied is False
    assert len(first.audit_event.event_sha256) == 64
    assert len(first.rollback_receipt.receipt_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.audit_event.audit_id = "changed"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"audit_id": "bad id"}, "invalid_audit_id"),
        ({"broker_gateway_id": "bad id"}, "invalid_broker_gateway_id"),
        ({"risk_gate_state": "OPEN"}, "invalid_risk_gate_state"),
    ],
)
def test_paper_only_audit_rejects_invalid_audit_provenance(kwargs, error):
    from tmp_agent.brain_v9.core.financial_autonomy_paper_audit import (
        evaluate_paper_only_financial_autonomy_audit,
    )

    valid = {
        "audit_id": "r11_2_audit_001",
        "broker_gateway_id": "paper_gateway_001",
        "risk_gate_state": "PAPER_ONLY_APPROVED",
    }
    valid.update(kwargs)
    with pytest.raises(ValueError, match=error):
        evaluate_paper_only_financial_autonomy_audit(**valid)


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
        "configuration_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    ),
)
def test_paper_only_audit_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.financial_autonomy_paper_audit import (
        reject_financial_autonomy_audit_effect,
    )

    with pytest.raises(ValueError, match="paper_only_audit_no_effects"):
        reject_financial_autonomy_audit_effect(operation)


def test_evidence_records_no_deploy_and_no_financial_runtime_actions():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R11_2_FINANCIAL_AUTONOMY_PAPER_ONLY_AUDIT_ROLLBACK_WIRING.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R11.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["audit_contract"]["paper_only"] is True
    assert evidence["audit_contract"]["broker_connection_permitted"] is False
    assert evidence["audit_contract"]["order_action_permitted"] is False
    assert evidence["audit_contract"]["rollback_validation_only"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_module_source_has_no_financial_runtime_or_external_effect_imports():
    source = (
        ROOT / "tmp_agent/brain_v9/core/financial_autonomy_paper_audit.py"
    ).read_text(encoding="utf-8")

    assert "import financial_autonomy" not in source
    assert "from financial_autonomy" not in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "socket" not in source
