from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import AutonomousOpenOrderAction
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.open_order_management import (
    EXECUTION_CLIENT_ID,
    OpenOrderOwnershipError,
    canonical_open_order,
    resolve_owned_open_trade,
)
from ibkr_paper_30d.persistence import Database


def trade(*, limit_price=10):
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=EXECUTION_CLIENT_ID,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=limit_price,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0
        ),
    )


def open_order_action_from_trade(value):
    snapshot = canonical_open_order(value)
    return AutonomousOpenOrderAction(
        order_ref=snapshot["orderRef"],
        order_id=snapshot["orderId"],
        perm_id=snapshot["permId"],
        client_id=snapshot["clientId"],
        contract_id=snapshot["contract"]["conId"],
        observed_state_sha256=snapshot["state_sha256"],
        new_total_quantity=None,
        new_limit_price=None,
        reason="Cancel the selected resting experiment order.",
    )


def register_issuance(db, value):
    snapshot = canonical_open_order(value)
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
        "lifecycle_event": "ISSUED_PRE_SEND",
        "order_ref": snapshot["orderRef"],
        "execution_client_id": snapshot["clientId"],
        "account": snapshot["account"],
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-test-anchor",
            snapshot["orderRef"],
            snapshot["orderId"],
            snapshot["permId"],
            snapshot["orderId"],
            snapshot["contract"]["conId"],
            snapshot["action"],
            snapshot["totalQuantity"],
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-23T12:00:00Z",
        ),
    )


def test_canonical_order_contains_complete_identity_and_hash():
    value = canonical_open_order(trade())

    assert value["orderRef"] == "codex-ibkr-paper-30d-a-cycle"
    assert value["orderId"] == 41
    assert value["permId"] == 9001
    assert value["clientId"] == EXECUTION_CLIENT_ID
    assert value["contract"]["conId"] == 756733
    assert len(value["state_sha256"]) == 64


def test_decimal_representation_does_not_change_state_hash():
    assert canonical_open_order(trade(limit_price=10))["state_sha256"] == (
        canonical_open_order(trade(limit_price="10.00"))["state_sha256"]
    )


def test_execution_client_is_outside_research_client_range():
    assert EXECUTION_CLIENT_ID == 19761
    assert not 19800 <= EXECUTION_CLIENT_ID <= 19899


def test_registry_and_live_identity_must_resolve_exactly_one_trade(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "orders.sqlite3") as db:
        register_issuance(db, value)
        resolved, snapshot = resolve_owned_open_trade(
            db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
        )

    assert resolved.order.orderId == 41
    assert snapshot["state_sha256"] == action.observed_state_sha256


def test_prefix_spoof_without_registry_anchor_is_blocked(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "orders.sqlite3") as db:
        with pytest.raises(
            OpenOrderOwnershipError, match="ORDER_REGISTRY_OWNERSHIP_REQUIRED"
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_duplicate_live_identity_is_ambiguous(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "orders.sqlite3") as db:
        register_issuance(db, value)
        with pytest.raises(
            OpenOrderOwnershipError, match="OPEN_ORDER_IDENTITY_AMBIGUOUS"
        ):
            resolve_owned_open_trade(
                db,
                [value, deepcopy(value)],
                action,
                execution_client_id=EXECUTION_CLIENT_ID,
            )


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("orderRef", "codex-ibkr-paper-30d-a-other", "OPEN_ORDER_REF_MISMATCH"),
        ("orderId", 42, "OPEN_ORDER_ID_MISMATCH"),
        ("permId", 9002, "OPEN_ORDER_PERM_ID_MISMATCH"),
        ("clientId", 19762, "OPEN_ORDER_CLIENT_ID_MISMATCH"),
        ("account", "DU7654321", "OPEN_ORDER_ACCOUNT_MISMATCH"),
        ("action", "SELL", "OPEN_ORDER_SIDE_MISMATCH"),
    ],
)
def test_live_identity_mismatch_has_stable_reason(
    tmp_path, field, replacement, reason
):
    anchor = trade()
    action = open_order_action_from_trade(anchor)
    changed = deepcopy(anchor)
    setattr(changed.order, field, replacement)
    with Database.open(tmp_path / f"{field}.sqlite3") as db:
        register_issuance(db, anchor)
        with pytest.raises(OpenOrderOwnershipError, match=reason):
            resolve_owned_open_trade(
                db, [changed], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_live_contract_mismatch_has_stable_reason(tmp_path):
    anchor = trade()
    action = open_order_action_from_trade(anchor)
    changed = deepcopy(anchor)
    changed.contract.conId = 999999
    with Database.open(tmp_path / "contract.sqlite3") as db:
        register_issuance(db, anchor)
        with pytest.raises(
            OpenOrderOwnershipError, match="OPEN_ORDER_CONTRACT_ID_MISMATCH"
        ):
            resolve_owned_open_trade(
                db, [changed], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_stale_observed_state_is_blocked(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value).model_copy(
        update={"observed_state_sha256": "b" * 64}
    )
    with Database.open(tmp_path / "stale.sqlite3") as db:
        register_issuance(db, value)
        with pytest.raises(OpenOrderOwnershipError, match="OPEN_ORDER_STATE_CHANGED"):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )
