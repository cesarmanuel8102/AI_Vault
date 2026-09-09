"""R11.1 contract: financial autonomy inventory remains deterministic, paper-only, and inert."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_paper_only_inventory_is_deterministic_immutable_and_non_executable():
    from tmp_agent.brain_v9.core.financial_autonomy_paper_inventory import (
        build_paper_only_financial_autonomy_inventory,
    )

    first = build_paper_only_financial_autonomy_inventory()
    second = build_paper_only_financial_autonomy_inventory()

    assert first == second
    assert first.mode == "PAPER_ONLY"
    assert first.execution_enabled is False
    assert first.real_money_enabled is False
    assert first.live_trading_enabled is False
    assert first.provider_calls_enabled is False
    assert first.network_enabled is False
    assert first.runtime_imports_enabled is False
    assert first.capabilities == (
        "market_data_observation",
        "strategy_research",
        "portfolio_state_modeling",
        "risk_precheck_modeling",
        "order_intent_modeling",
    )
    assert len(first.inventory_sha256) == 64

    with pytest.raises(FrozenInstanceError):
        first.mode = "LIVE"


@pytest.mark.parametrize(
    "operation",
    (
        "broker_connect",
        "broker_order",
        "order_submit",
        "order_cancel",
        "live_trading",
        "real_money",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "auto_merge",
    ),
)
def test_paper_only_inventory_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.financial_autonomy_paper_inventory import (
        reject_financial_autonomy_effect,
    )

    with pytest.raises(ValueError, match="paper_only_inventory_no_effects"):
        reject_financial_autonomy_effect(operation)


def test_evidence_records_no_deploy_and_no_runtime_financial_actions():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R11_1_FINANCIAL_AUTONOMY_PAPER_ONLY_RUNTIME_INVENTORY.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R11.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["inventory_contract"]["paper_only"] is True
    assert evidence["inventory_contract"]["runtime_import_permitted"] is False
    assert evidence["inventory_contract"]["broker_action_permitted"] is False
    assert evidence["inventory_contract"]["order_action_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_module_source_does_not_import_financial_autonomy_runtime():
    source_path = ROOT / "tmp_agent/brain_v9/core/financial_autonomy_paper_inventory.py"
    source = source_path.read_text(encoding="utf-8")

    assert "import financial_autonomy" not in source
    assert "from financial_autonomy" not in source
    assert "subprocess" not in source
    assert "requests" not in source
    assert "httpx" not in source
