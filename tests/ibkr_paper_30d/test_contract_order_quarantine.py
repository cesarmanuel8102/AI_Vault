from datetime import datetime, timedelta, timezone

import pytest

from ibkr_paper_30d.contract_order_quarantine import (
    ContractOrderQuarantineError,
    ContractOrderQuarantineStore,
)


NOW = datetime(2026, 10, 23, 22, 0, tzinfo=timezone.utc)
HEAD = "b7be6d48c4f744cb5777e3185603db41ec43c30a"
ACCOUNT = "a" * 64


def order(**updates):
    value = {
        "orderId": 955,
        "permId": 399803157,
        "clientId": 19761,
        "orderRef": "codex-ibkr-paper-30d-p-7ca1eec02caa",
        "contract": {"conId": 766137558, "symbol": "SOL"},
        "action": "SELL",
        "totalQuantity": "4.5",
        "status": "PendingCancel",
        "filled": "0",
        "remaining": "4.5",
    }
    value.update(updates)
    return value


def position(quantity="4.5"):
    return {
        "contract_id": 766137558,
        "symbol": "SOL",
        "quantity": quantity,
    }


def store(tmp_path):
    value = ContractOrderQuarantineStore(tmp_path / "quarantine.json")
    value.activate(
        account_identity_sha256=ACCOUNT,
        approved_head=HEAD,
        order=order(),
        position_quantity="4.5",
        authorized_at_utc=NOW,
    )
    return value


def test_exact_pending_cancel_remains_quarantined_and_blocks_only_contract(tmp_path):
    quarantine = store(tmp_path)
    result = quarantine.observe(
        open_orders=[order()], positions=[position()], observed_at_utc=NOW + timedelta(minutes=1)
    )
    assert result.status == "ACTIVE"
    assert quarantine.write_reasons({"canonical_contract": {"con_id": 766137558}}) == (
        "QUARANTINED_CONTRACT_WRITE_BLOCKED",
    )
    assert quarantine.write_reasons({"canonical_contract": {"con_id": 123}}) == ()


@pytest.mark.parametrize(
    "changed",
    [
        order(remaining="4.4"),
        order(filled="0.1", remaining="4.4"),
        order(permId=399803158),
        order(status="Submitted"),
    ],
)
def test_any_quarantined_order_drift_requires_global_pause(tmp_path, changed):
    with pytest.raises(ContractOrderQuarantineError, match="QUARANTINED_ORDER_STATE_CHANGED"):
        store(tmp_path).observe(
            open_orders=[changed], positions=[position()],
            observed_at_utc=NOW + timedelta(minutes=1),
        )


def test_additional_same_contract_order_requires_global_pause(tmp_path):
    with pytest.raises(ContractOrderQuarantineError, match="UNEXPECTED_QUARANTINED_CONTRACT_ORDER"):
        store(tmp_path).observe(
            open_orders=[order(), order(orderId=956, permId=399803159)],
            positions=[position()], observed_at_utc=NOW + timedelta(minutes=1),
        )


def test_release_requires_two_fresh_absent_observations_with_position_unchanged(tmp_path):
    quarantine = store(tmp_path)
    first = quarantine.observe(
        open_orders=[], positions=[position()], observed_at_utc=NOW + timedelta(minutes=1)
    )
    assert first.status == "RELEASE_PENDING"
    assert quarantine.write_reasons({"canonical_contract": {"con_id": 766137558}})
    second = quarantine.observe(
        open_orders=[], positions=[position()], observed_at_utc=NOW + timedelta(minutes=2)
    )
    assert second.status == "RELEASED"
    assert quarantine.write_reasons({"canonical_contract": {"con_id": 766137558}}) == ()


def test_absent_order_with_changed_position_requires_global_pause(tmp_path):
    with pytest.raises(ContractOrderQuarantineError, match="QUARANTINED_POSITION_CHANGED"):
        store(tmp_path).observe(
            open_orders=[], positions=[position("0")],
            observed_at_utc=NOW + timedelta(minutes=1),
        )


def test_service_exposes_contract_scoped_quarantine_without_global_entry_block(tmp_path):
    from ibkr_paper_30d.autonomous_service import AutonomousExperimentService
    from ibkr_paper_30d.trader_invocation import TraderInputBundle

    quarantine = store(tmp_path)
    service = object.__new__(AutonomousExperimentService)
    service.contract_order_quarantine_store = quarantine
    bundle = TraderInputBundle(
        decision_cycle_id="cycle-1", utc_timestamp="2026-10-23T22:01:00Z",
        market_session_state="EXTENDED", reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={}, broker_account_snapshot={},
        positions_snapshot=[position()], open_orders_snapshot=[order()],
        risk_snapshot={}, kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={}, candidate_screen_results=[],
        relevant_previous_immutable_decisions=[], process_policy_version="v1",
        execution_realism_version="v1", benchmark_state={"existing": True},
    )

    updated = service._with_contract_order_quarantine_context(bundle)
    context = updated.benchmark_state["contract_order_quarantine"]
    assert context["scope"] == "EXACT_CONTRACT_AND_ORDER_ONLY"
    assert context["quarantined_contract_id"] == 766137558
    assert context["quarantined_order_ref"] == "codex-ibkr-paper-30d-p-7ca1eec02caa"
    assert context["global_entry_block"] is False
    assert context["other_contract_execution_policy"] == "NORMAL_RUNTIME_GATES_APPLY"
    assert updated.benchmark_state["existing"] is True
