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
    lifecycle_attempt_exists,
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
            parentId=0,
            ocaGroup="",
            ocaType=0,
            transmit=False,
            conditions=[],
            goodAfterTime="",
            goodTillDate="",
            smartComboRoutingParams=[],
            algoStrategy="",
            algoParams=[],
            orderMiscOptions=[],
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0
        ),
    )


def bag_trade(*, contract_id=28812380):
    value = trade(limit_price="0.90")
    value.contract = SimpleNamespace(
        conId=contract_id,
        symbol="IOVA",
        localSymbol="IOVA",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="",
        comboLegs=[
            SimpleNamespace(
                conId=913925915, ratio=1, action="BUY", exchange="SMART"
            ),
            SimpleNamespace(
                conId=926221865, ratio=1, action="SELL", exchange="SMART"
            ),
        ],
    )
    value.order.orderRef = "codex-ibkr-paper-30d-a-f8da732bc64a"
    value.order.orderId = 13
    value.order.permId = 1401602203
    value.order.totalQuantity = 1
    value.order.lmtPrice = 0.9
    value.orderStatus.status = "PreSubmitted"
    value.orderStatus.filled = 0
    value.orderStatus.remaining = 1
    return value


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


def register_issuance(
    db,
    value,
    *,
    registry_id="registry-test-anchor",
    schema="EXPERIMENT_ORDER_REGISTRY_V2",
    ibkr_order_id=None,
    payload_sha256=None,
    payload_updates=None,
    payload_removals=(),
    lifecycle_event="ISSUED_PRE_SEND",
):
    snapshot = canonical_open_order(value)
    stored_ibkr_order_id = (
        snapshot["orderId"] if ibkr_order_id is None else ibkr_order_id
    )
    payload = {
        "schema": schema,
        "lifecycle_event": lifecycle_event,
        "order_ref": snapshot["orderRef"],
        "client_order_id": snapshot["orderId"],
        "perm_id": snapshot["permId"],
        "ibkr_order_id": stored_ibkr_order_id,
        "contract_id": snapshot["contract"]["conId"],
        "action": snapshot["action"],
        "quantity": snapshot["totalQuantity"],
        "execution_client_id": snapshot["clientId"],
        "account": snapshot["account"],
    }
    payload.update(payload_updates or {})
    for key in payload_removals:
        payload.pop(key)
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            registry_id,
            snapshot["orderRef"],
            snapshot["orderId"],
            snapshot["permId"],
            stored_ibkr_order_id,
            snapshot["contract"]["conId"],
            snapshot["action"],
            snapshot["totalQuantity"],
            canonical_bytes(payload).decode("utf-8"),
            payload_sha256 or sha256_json(payload),
            "2026-09-23T12:00:00Z",
        ),
    )


def register_legacy_zero_bag_anchors(db, live):
    pre_send = deepcopy(live)
    pre_send.contract.conId = 0
    pre_send.order.permId = 0
    register_issuance(
        db,
        pre_send,
        registry_id="bag-pre-send",
    )
    broker_bound = deepcopy(live)
    broker_bound.contract.conId = 0
    register_issuance(
        db,
        broker_bound,
        registry_id="bag-broker-bound",
        lifecycle_event="BROKER_BOUND",
    )


def test_canonical_order_contains_complete_identity_and_hash():
    value = canonical_open_order(trade())

    assert value["orderRef"] == "codex-ibkr-paper-30d-a-cycle"
    assert value["orderId"] == 41
    assert value["permId"] == 9001
    assert value["clientId"] == EXECUTION_CLIENT_ID
    assert value["contract"]["conId"] == 756733
    assert len(value["state_sha256"]) == 64


def test_canonical_bag_order_hash_binds_exact_combo_legs():
    original = bag_trade()
    changed = deepcopy(original)
    changed.contract.comboLegs[1].conId = 999999999

    snapshot = canonical_open_order(original)

    assert snapshot["contract"]["secType"] == "BAG"
    assert snapshot["contract"]["comboLegs"] == [
        {"conId": 913925915, "ratio": 1, "action": "BUY", "exchange": "SMART"},
        {"conId": 926221865, "ratio": 1, "action": "SELL", "exchange": "SMART"},
    ]
    assert canonical_open_order(changed)["state_sha256"] != snapshot["state_sha256"]


def test_legacy_zero_conid_bag_appends_exact_broker_identity_binding(tmp_path):
    live = bag_trade()
    action = open_order_action_from_trade(live)
    with Database.open(tmp_path / "legacy-bag.sqlite3") as db:
        register_legacy_zero_bag_anchors(db, live)

        resolved, snapshot = resolve_owned_open_trade(
            db, [live], action, execution_client_id=EXECUTION_CLIENT_ID
        )
        rows = db.execute(
            "SELECT contract_id,payload_json FROM experiment_order_registry "
            "WHERE order_ref=? ORDER BY sequence",
            (action.order_ref,),
        ).fetchall()

    assert resolved is live
    assert snapshot["contract"]["conId"] == 28812380
    assert [row[0] for row in rows] == [0, 0, 28812380]
    binding = __import__("json").loads(rows[-1][1])
    assert binding["lifecycle_event"] == "BROKER_IDENTITY_BOUND"
    assert binding["contract"]["comboLegs"][0]["conId"] == 913925915
    assert binding["contract"]["comboLegs"][1]["action"] == "SELL"


def test_legacy_bag_requires_positive_broker_bound_perm_anchor(tmp_path):
    live = bag_trade()
    pre_send = deepcopy(live)
    pre_send.contract.conId = 0
    pre_send.order.permId = 0
    with Database.open(tmp_path / "legacy-bag-without-bound.sqlite3") as db:
        register_issuance(db, pre_send, registry_id="bag-pre-send-only")

        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_BROKER_BOUND_REQUIRED",
        ):
            resolve_owned_open_trade(
                db,
                [live],
                open_order_action_from_trade(live),
                execution_client_id=EXECUTION_CLIENT_ID,
            )

        assert db.execute(
            "SELECT COUNT(*) FROM experiment_order_registry"
        ).fetchone()[0] == 1


def test_legacy_bag_binding_rejects_forged_source_hash_list(tmp_path):
    live = bag_trade()
    action = open_order_action_from_trade(live)
    with Database.open(tmp_path / "legacy-bag-forged-source.sqlite3") as db:
        register_legacy_zero_bag_anchors(db, live)
        snapshot = canonical_open_order(live)
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_IDENTITY_BOUND",
            "order_ref": action.order_ref,
            "client_order_id": action.order_id,
            "perm_id": action.perm_id,
            "ibkr_order_id": action.order_id,
            "contract_id": action.contract_id,
            "action": snapshot["action"],
            "quantity": snapshot["totalQuantity"],
            "execution_client_id": action.client_id,
            "account": snapshot["account"],
            "contract": snapshot["contract"],
            "source_anchor_sha256": ["0" * 64],
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "forged-binding",
                action.order_ref,
                action.order_id,
                action.perm_id,
                action.order_id,
                action.contract_id,
                snapshot["action"],
                snapshot["totalQuantity"],
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                "2026-09-29T18:00:00Z",
            ),
        )

        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_BINDING_SOURCE_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [live], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_v3_pre_send_and_broker_bound_bag_resolve_without_reconciliation(tmp_path):
    live = bag_trade()
    pre_send = deepcopy(live)
    pre_send.contract.conId = 0
    pre_send.contract.localSymbol = ""
    pre_send.order.permId = 0
    live_snapshot = canonical_open_order(live)
    pre_send_snapshot = canonical_open_order(pre_send)

    with Database.open(tmp_path / "v3-bag.sqlite3") as db:
        register_issuance(
            db,
            pre_send,
            registry_id="v3-pre-send",
            schema="EXPERIMENT_ORDER_REGISTRY_V3",
            payload_updates={"contract": pre_send_snapshot["contract"]},
        )
        register_issuance(
            db,
            live,
            registry_id="v3-broker-bound",
            schema="EXPERIMENT_ORDER_REGISTRY_V3",
            lifecycle_event="BROKER_BOUND",
            payload_updates={"contract": live_snapshot["contract"]},
        )

        selected, snapshot = resolve_owned_open_trade(
            db,
            [live],
            open_order_action_from_trade(live),
            execution_client_id=EXECUTION_CLIENT_ID,
        )
        row_count = db.execute(
            "SELECT COUNT(*) FROM experiment_order_registry"
        ).fetchone()[0]

    assert selected is live
    assert snapshot["contract"] == live_snapshot["contract"]
    assert row_count == 2


def test_v3_zero_parent_broker_bound_appends_positive_identity(tmp_path):
    live = bag_trade()
    zero = deepcopy(live)
    zero.contract.conId = 0
    zero.contract.localSymbol = ""
    zero_snapshot = canonical_open_order(zero)
    pre_send = deepcopy(zero)
    pre_send.order.permId = 0
    pre_send_snapshot = canonical_open_order(pre_send)
    with Database.open(tmp_path / "v3-zero-bound-bag.sqlite3") as db:
        register_issuance(
            db,
            pre_send,
            registry_id="v3-zero-pre-send",
            schema="EXPERIMENT_ORDER_REGISTRY_V3",
            payload_updates={"contract": pre_send_snapshot["contract"]},
        )
        register_issuance(
            db,
            zero,
            registry_id="v3-zero-broker-bound",
            schema="EXPERIMENT_ORDER_REGISTRY_V3",
            lifecycle_event="BROKER_BOUND",
            payload_updates={"contract": zero_snapshot["contract"]},
        )

        resolve_owned_open_trade(
            db,
            [live],
            open_order_action_from_trade(live),
            execution_client_id=EXECUTION_CLIENT_ID,
        )
        rows = db.execute(
            "SELECT contract_id,payload_json FROM experiment_order_registry "
            "ORDER BY sequence"
        ).fetchall()

    assert [row[0] for row in rows] == [0, 0, 28812380]
    binding = __import__("json").loads(rows[-1][1])
    assert binding["lifecycle_event"] == "BROKER_IDENTITY_BOUND"
    assert binding["contract"]["conId"] == 28812380


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("orderRef", "codex-ibkr-paper-30d-a-other", "OPEN_ORDER_REF_MISMATCH"),
        ("orderId", 14, "OPEN_ORDER_ID_MISMATCH"),
        ("permId", 1401602204, "OPEN_ORDER_PERM_ID_MISMATCH"),
        ("clientId", 19762, "OPEN_ORDER_CLIENT_ID_MISMATCH"),
        ("account", "DU7654321", "OPEN_ORDER_ACCOUNT_MISMATCH"),
    ],
)
def test_legacy_zero_conid_bag_transition_keeps_strong_anchors(
    tmp_path, field, replacement, reason
):
    anchor = bag_trade()
    action = open_order_action_from_trade(anchor)
    changed = deepcopy(anchor)
    setattr(changed.order, field, replacement)
    with Database.open(tmp_path / f"legacy-bag-{field}.sqlite3") as db:
        register_legacy_zero_bag_anchors(db, anchor)
        with pytest.raises(OpenOrderOwnershipError, match=reason):
            resolve_owned_open_trade(
                db, [changed], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_legacy_zero_conid_bag_blocks_unrelated_combo_legs(tmp_path):
    anchor = bag_trade()
    unrelated = deepcopy(anchor)
    unrelated.contract.comboLegs[1].conId = 999999999
    unrelated_snapshot = canonical_open_order(unrelated)
    unrelated_action = open_order_action_from_trade(anchor).model_copy(
        update={"observed_state_sha256": unrelated_snapshot["state_sha256"]}
    )
    with Database.open(tmp_path / "legacy-bag-unrelated.sqlite3") as db:
        register_legacy_zero_bag_anchors(db, anchor)

        resolve_owned_open_trade(
            db,
            [anchor],
            open_order_action_from_trade(anchor),
            execution_client_id=EXECUTION_CLIENT_ID,
        )

        with pytest.raises(
            OpenOrderOwnershipError, match="OPEN_ORDER_CONTRACT_IDENTITY_MISMATCH"
        ):
            resolve_owned_open_trade(
                db,
                [unrelated],
                unrelated_action,
                execution_client_id=EXECUTION_CLIENT_ID,
            )


def test_decimal_representation_does_not_change_state_hash():
    assert canonical_open_order(trade(limit_price=10))["state_sha256"] == (
        canonical_open_order(trade(limit_price="10.00"))["state_sha256"]
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("parentId", 88),
        ("ocaGroup", "group-a"),
        ("transmit", True),
        ("conditions", [SimpleNamespace(conId=1, exchange="SMART")]),
        ("goodAfterTime", "20260923 13:30:00 UTC"),
        ("goodTillDate", "20260924 20:00:00 UTC"),
        ("smartComboRoutingParams", [SimpleNamespace(tag="NonGuaranteed", value="1")]),
        ("algoStrategy", "Adaptive"),
        ("algoParams", [SimpleNamespace(tag="adaptivePriority", value="Normal")]),
        ("orderMiscOptions", [SimpleNamespace(tag="foo", value="bar")]),
    ],
)
def test_state_hash_binds_preserved_order_semantics(field, replacement):
    original = trade()
    changed = deepcopy(original)
    setattr(changed.order, field, replacement)

    assert canonical_open_order(changed)["state_sha256"] != (
        canonical_open_order(original)["state_sha256"]
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


def test_namespace_match_requires_prefix_boundary(tmp_path):
    value = trade()
    value.order.orderRef = "codex-ibkr-paper-30devil"
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "namespace.sqlite3") as db:
        register_issuance(db, value)
        with pytest.raises(
            OpenOrderOwnershipError, match="ORDER_REF_NAMESPACE_MISMATCH"
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_registry_payload_hash_must_validate(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "payload-hash.sqlite3") as db:
        register_issuance(db, value, payload_sha256="0" * 64)
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_PAYLOAD_HASH_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_v2_registry_payload_must_bind_every_identity_column(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "payload-identity.sqlite3") as db:
        register_issuance(
            db,
            value,
            payload_updates={"contract_id": 999999},
        )
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_PAYLOAD_IDENTITY_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_ibkr_order_id_must_match_requested_and_live_order(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "conflicting-order-ids.sqlite3") as db:
        register_issuance(db, value, ibkr_order_id=42)
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_IBKR_ORDER_ID_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_pre_send_anchor_without_perm_id_accepts_later_broker_assignment(tmp_path):
    live = trade()
    action = open_order_action_from_trade(live)
    pre_send = deepcopy(live)
    pre_send.order.permId = 0
    with Database.open(tmp_path / "delayed-perm-id.sqlite3") as db:
        register_issuance(db, pre_send)

        selected, snapshot = resolve_owned_open_trade(
            db, [live], action, execution_client_id=EXECUTION_CLIENT_ID
        )

    assert selected is live
    assert snapshot["permId"] == 9001


def test_positive_registry_perm_id_requires_live_order_to_present_it(tmp_path):
    anchor = trade()
    live = deepcopy(anchor)
    live.order.permId = 0
    live_snapshot = canonical_open_order(live)
    action = open_order_action_from_trade(anchor).model_copy(
        update={
            "perm_id": None,
            "observed_state_sha256": live_snapshot["state_sha256"],
        }
    )
    assert action.observed_state_sha256 == live_snapshot["state_sha256"]

    with Database.open(tmp_path / "missing-live-perm-id.sqlite3") as db:
        register_issuance(db, anchor)

        with pytest.raises(
            OpenOrderOwnershipError, match="OPEN_ORDER_PERM_ID_MISMATCH"
        ):
            resolve_owned_open_trade(
                db, [live], action, execution_client_id=EXECUTION_CLIENT_ID
            )


@pytest.mark.parametrize(
    "missing_key",
    [
        "schema",
        "lifecycle_event",
        "order_ref",
        "client_order_id",
        "perm_id",
        "ibkr_order_id",
        "contract_id",
        "action",
        "quantity",
        "execution_client_id",
        "account",
    ],
)
def test_v2_registry_anchor_requires_complete_payload_before_coercion(
    tmp_path, missing_key
):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / f"payload-missing-{missing_key}.sqlite3") as db:
        register_issuance(db, value, payload_removals=(missing_key,))
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_V2_PAYLOAD_INCOMPLETE",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_blank_account_anchor_cannot_borrow_proof_from_later_anchor(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "blank-account.sqlite3") as db:
        register_issuance(
            db,
            value,
            registry_id="registry-blank-account",
            payload_updates={"account": ""},
        )
        register_issuance(
            db,
            value,
            registry_id="registry-account-bound",
        )
        with pytest.raises(
            OpenOrderOwnershipError,
            match="OPEN_ORDER_ACCOUNT_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_v1_registry_anchor_cannot_authorize_lifecycle_write(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    with Database.open(tmp_path / "v1-anchor.sqlite3") as db:
        register_issuance(
            db,
            value,
            schema="EXPERIMENT_ORDER_REGISTRY_V1",
        )
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_V2_OWNERSHIP_REQUIRED",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_conflicting_registry_anchors_are_blocked(tmp_path):
    value = trade()
    action = open_order_action_from_trade(value)
    conflicting = deepcopy(value)
    conflicting.order.orderId = 42
    conflicting.contract.conId = 999999
    with Database.open(tmp_path / "conflicting-anchors.sqlite3") as db:
        register_issuance(db, value)
        register_issuance(
            db,
            conflicting,
            registry_id="registry-conflicting-anchor",
        )
        with pytest.raises(
            OpenOrderOwnershipError,
            match="ORDER_REGISTRY_ORDER_ID_MISMATCH",
        ):
            resolve_owned_open_trade(
                db, [value], action, execution_client_id=EXECUTION_CLIENT_ID
            )


def test_lifecycle_attempt_is_global_to_decision_cycle(tmp_path):
    value = trade()
    snapshot = canonical_open_order(value)
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_LIFECYCLE_V1",
        "lifecycle_event": "CANCEL_ATTEMPT",
        "decision_cycle_id": "cycle-shared",
    }
    with Database.open(tmp_path / "global-cycle.sqlite3") as db:
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "attempt-one",
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

        assert lifecycle_attempt_exists(
            db,
            order_ref="codex-ibkr-paper-30d-a-different-order",
            decision_cycle_id="cycle-shared",
        ) is True


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
