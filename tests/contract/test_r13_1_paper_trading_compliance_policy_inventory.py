"""R13.1 contract: deterministic paper-only compliance policy inventory."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _evaluate(**overrides):
    from tmp_agent.brain_v9.core.paper_trading_compliance_policy import (
        evaluate_paper_trading_compliance,
    )

    values = {
        "day_trades_in_window": 0,
        "wash_sale_detected": False,
        "market_hours_open": True,
        "restricted_symbol": False,
        "short_sale_permission": True,
        "account_permission": True,
        "jurisdiction_approved": True,
        "data_license_approved": True,
        "paper_only": True,
    }
    values.update(overrides)
    return evaluate_paper_trading_compliance(**values)


def test_compliant_paper_input_produces_immutable_deterministic_receipt():
    first = _evaluate()
    second = _evaluate()

    assert first == second
    assert first.approved is True
    assert first.paper_only is True
    assert first.denial_reasons == ()
    assert first.policy == {
        "max_day_trades_in_window": 3,
        "paper_live_boundary": "paper_only",
    }
    assert len(first.receipt_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.approved = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"day_trades_in_window": 4}, "pdt_threshold_exceeded"),
        ({"wash_sale_detected": True}, "wash_sale_detected"),
        ({"market_hours_open": False}, "market_hours_closed"),
        ({"restricted_symbol": True}, "restricted_symbol"),
        ({"short_sale_permission": False}, "short_sale_permission_missing"),
        ({"account_permission": False}, "account_permission_missing"),
        ({"jurisdiction_approved": False}, "jurisdiction_not_approved"),
        ({"data_license_approved": False}, "data_license_not_approved"),
        ({"paper_only": False}, "paper_only_required"),
    ],
)
def test_each_compliance_or_paper_boundary_failure_denies_the_receipt(overrides, reason):
    result = _evaluate(**overrides)

    assert result.approved is False
    assert result.paper_only is True
    assert result.denial_reasons == (reason,)


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
def test_compliance_inventory_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.paper_trading_compliance_policy import (
        reject_paper_compliance_effect,
    )

    with pytest.raises(ValueError, match="paper_only_compliance_policy_no_effects"):
        reject_paper_compliance_effect(operation)


def test_evidence_and_module_are_paper_only_and_external_effect_free():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R13_1_PAPER_TRADING_COMPLIANCE_POLICY_INVENTORY.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R13.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["compliance_policy_contract"]["paper_only"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())

    source = (ROOT / "tmp_agent/brain_v9/core/paper_trading_compliance_policy.py").read_text(
        encoding="utf-8"
    )
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


def test_closeout_preserves_r13_1_no_deploy_evidence_and_jit_binds_r13_2():
    manifest = json.loads(
        (ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8")
    )
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R13_1_PAPER_TRADING_COMPLIANCE_POLICY_INVENTORY_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["roadmap_items"]["R13.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    successor = manifest["roadmap_items"]["R13.2"]
    assert successor["status"] == "AUTHORIZED_ACTIVE"
    assert successor["dependencies"] == ["R13.1"]
    assert successor["automation"]["front_id"] == (
        "BRAIN-101-R13-2-COMPLIANCE-AUDIT-TAX-LOT-MANUAL-REVIEW-01"
    )
    assert successor["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert closeout["roadmap_item"] == "R13.1"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["successor"]["roadmap_item"] == "R13.2"
    assert all(value is False for value in closeout["runtime_actions"].values())
