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
