from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ibkr_paper_30d.continuity_models import CodexOrderContinuityPlan


WINDOWS_ONLY_FILES = {
    "test_auditor_provisioning.py",
    "test_auditor_runtime.py",
    "test_auditor_runtime_v2.py",
    "test_execution_lock.py",
    "test_prerequisite_finalizer.py",
}


@pytest.fixture
def continuity_plan_factory():
    now = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)

    def build(**overrides):
        payload = {
            "schema": "CODEX_ORDER_CONTINUITY_PLAN_V1",
            "plan_id": "plan-test-1",
            "plan_version": 1,
            "created_at_utc": now,
            "created_by_model": "gpt-5.6-sol",
            "model_attestation_sha256": "a" * 64,
            "decision_cycle_id": "cycle-test-1",
            "invocation_id": "inv-test-1",
            "input_bundle_sha256": "b" * 64,
            "epoch_id": "AUTONOMY_EPOCH_2",
            "definition_sha256": "c" * 64,
            "clock_event_sha256": "d" * 64,
            "owner_authorization_sha256": "e" * 64,
            "predecessor_plan_sha256": None,
            "order_binding": {
                "binding_type": "EXISTING_ORDER",
                "account_identity_sha256": "f" * 64,
                "order_ref": "order-78",
                "client_order_id": "client-order-78",
                "ibkr_order_id": 78,
                "perm_id": 225256222,
                "execution_client_id": 17,
                "contract_identity_sha256": "1" * 64,
                "action": "BUY",
                "order_type": "LMT",
                "original_total_quantity": "1",
                "original_limit_price": "4.90",
                "original_tif": "DAY",
                "original_good_till_date_utc": None,
                "original_order_state_sha256": "2" * 64,
                "original_intent_sha256": "3" * 64,
                "proposal_sha256": None,
            },
            "maximum_authorized_liability": "500",
            "valid_from_utc": now,
            "plan_valid_until": now + timedelta(hours=6),
            "session_end_utc": now + timedelta(hours=6),
            "epoch_authority_end_utc": now + timedelta(days=1),
            "authority_activation_condition": {
                "operator": "PREDICATE",
                "fact": "PROVIDER_STATE",
                "comparator": "EQ",
                "value": "TIMEOUT_CONFIRMED",
                "max_age_seconds": 30,
            },
            "expiry_authority_mode": "WHEN_CONTINUITY_ACTIVE",
            "terminal_disposition": {"action_type": "CANCEL"},
            "contingencies": [
                {
                    "contingency_id": "outage",
                    "priority": 10,
                    "valid_from_utc": now,
                    "valid_until_utc": now + timedelta(hours=6),
                    "condition": {
                        "operator": "PREDICATE",
                        "fact": "ORDER_REMAINING_QUANTITY",
                        "comparator": "GT",
                        "value": "0",
                        "max_age_seconds": 30,
                    },
                    "state_actions": {
                        state: {"action_type": "RETAIN"}
                        for state in (
                            "UNFILLED", "PARTIALLY_FILLED", "FILLED",
                            "PENDING_CANCEL", "CANCELLED", "REJECTED", "ABSENT",
                        )
                    },
                    "unavailable_data_action": {"action_type": "CANCEL"},
                    "maximum_execution_count": 1,
                    "expectations": ["The order may remain unfilled."],
                    "why_i_chose_this_contingency": "Preserve exact prior intent.",
                }
            ],
        }
        binding_overrides = overrides.pop("order_binding", None)
        payload.update(overrides)
        if binding_overrides:
            payload["order_binding"].update(binding_overrides)
        return CodexOrderContinuityPlan.model_validate(payload)

    return build


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    marker = pytest.mark.skip(reason="Windows-only IBKR/Auditor host-boundary test")
    for item in items:
        if Path(str(item.fspath)).name in WINDOWS_ONLY_FILES:
            item.add_marker(marker)
