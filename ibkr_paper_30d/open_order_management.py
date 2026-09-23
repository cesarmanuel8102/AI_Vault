from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from .canonical import sha256_json
from .persistence import Database


EXECUTION_CLIENT_ID = 19761
EXPERIMENT_ORDER_PREFIX = "codex-ibkr-paper-30d"
ACTIONABLE_ORDER_STATUSES = frozenset(
    {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED", "PENDINGCANCEL"}
)
CANCELLED_ORDER_STATUSES = frozenset(
    {"CANCELLED", "APICANCELLED", "API CANCELLED"}
)


class OpenOrderOwnershipError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _decimal_text(value: Any) -> str:
    parsed = Decimal(str(value or 0))
    if not parsed.is_finite():
        raise ValueError("open-order numeric field must be finite")
    normalized = parsed.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def canonical_open_order(trade: Any) -> dict[str, Any]:
    order = trade.order
    status = trade.orderStatus
    contract = trade.contract
    payload = {
        "orderRef": str(getattr(order, "orderRef", "") or ""),
        "orderId": int(getattr(order, "orderId", 0) or 0),
        "permId": int(getattr(order, "permId", 0) or 0),
        "clientId": int(getattr(order, "clientId", 0) or 0),
        "account": str(getattr(order, "account", "") or ""),
        "action": str(getattr(order, "action", "") or "").upper(),
        "orderType": str(getattr(order, "orderType", "") or "").upper(),
        "totalQuantity": _decimal_text(getattr(order, "totalQuantity", 0)),
        "limitPrice": _decimal_text(getattr(order, "lmtPrice", 0)),
        "auxPrice": _decimal_text(getattr(order, "auxPrice", 0)),
        "tif": str(getattr(order, "tif", "") or "").upper(),
        "outsideRth": bool(getattr(order, "outsideRth", False)),
        "status": str(getattr(status, "status", "") or ""),
        "filled": _decimal_text(getattr(status, "filled", 0)),
        "remaining": _decimal_text(getattr(status, "remaining", 0)),
        "contract": {
            "conId": int(getattr(contract, "conId", 0) or 0),
            "symbol": str(getattr(contract, "symbol", "") or ""),
            "localSymbol": str(getattr(contract, "localSymbol", "") or ""),
            "secType": str(getattr(contract, "secType", "") or "").upper(),
            "exchange": str(getattr(contract, "exchange", "") or ""),
            "currency": str(getattr(contract, "currency", "") or ""),
            "expiry": str(
                getattr(contract, "lastTradeDateOrContractMonth", "") or ""
            ),
            "strike": _decimal_text(getattr(contract, "strike", 0)),
            "right": str(getattr(contract, "right", "") or "").upper(),
            "multiplier": _decimal_text(getattr(contract, "multiplier", 1) or 1),
        },
    }
    return {**payload, "state_sha256": sha256_json(payload)}


def _registry_payload(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def resolve_owned_open_trade(
    db: Database,
    trades: list[Any],
    action: Any,
    *,
    execution_client_id: int,
) -> tuple[Any, dict[str, Any]]:
    if not action.order_ref.startswith(EXPERIMENT_ORDER_PREFIX):
        raise OpenOrderOwnershipError("ORDER_REF_NAMESPACE_MISMATCH")

    rows = db.execute(
        "SELECT client_order_id,perm_id,contract_id,action,payload_json "
        "FROM experiment_order_registry WHERE order_ref=? ORDER BY sequence",
        (action.order_ref,),
    ).fetchall()
    anchors = [
        (row, _registry_payload(row[4]))
        for row in rows
        if _registry_payload(row[4]).get(
            "lifecycle_event", "ISSUED_PRE_SEND"
        )
        in {"ISSUED_PRE_SEND", "BROKER_BOUND"}
    ]
    if not anchors:
        raise OpenOrderOwnershipError("ORDER_REGISTRY_OWNERSHIP_REQUIRED")
    if not any(int(row[0] or 0) == action.order_id for row, _ in anchors):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_ORDER_ID_MISMATCH")
    if not any(int(row[2] or 0) == action.contract_id for row, _ in anchors):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_CONTRACT_ID_MISMATCH")
    if action.perm_id is not None:
        positive_registry_perm_ids = {
            int(row[1]) for row, _ in anchors if int(row[1] or 0) > 0
        }
        if (
            positive_registry_perm_ids
            and action.perm_id not in positive_registry_perm_ids
        ):
            raise OpenOrderOwnershipError("ORDER_REGISTRY_PERM_ID_MISMATCH")
    if action.client_id != execution_client_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_CLIENT_ID_MISMATCH")

    snapshots = [(trade, canonical_open_order(trade)) for trade in trades]
    exact_identity = [
        item
        for item in snapshots
        if item[1]["orderRef"] == action.order_ref
        and item[1]["orderId"] == action.order_id
        and item[1]["clientId"] == execution_client_id
        and item[1]["contract"]["conId"] == action.contract_id
    ]
    if len(exact_identity) > 1:
        raise OpenOrderOwnershipError("OPEN_ORDER_IDENTITY_AMBIGUOUS")
    if exact_identity:
        candidate, snapshot = exact_identity[0]
    elif len(snapshots) == 1:
        candidate, snapshot = snapshots[0]
    else:
        raise OpenOrderOwnershipError("OPEN_ORDER_NOT_FOUND")

    if snapshot["orderRef"] != action.order_ref:
        raise OpenOrderOwnershipError("OPEN_ORDER_REF_MISMATCH")
    if snapshot["orderId"] != action.order_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_ID_MISMATCH")
    if action.perm_id is not None and snapshot["permId"] != action.perm_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_PERM_ID_MISMATCH")
    if snapshot["clientId"] != execution_client_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_CLIENT_ID_MISMATCH")
    if snapshot["contract"]["conId"] != action.contract_id:
        raise OpenOrderOwnershipError("OPEN_ORDER_CONTRACT_ID_MISMATCH")

    matching_anchors = [
        (row, payload)
        for row, payload in anchors
        if int(row[0] or 0) == snapshot["orderId"]
        and int(row[2] or 0) == snapshot["contract"]["conId"]
    ]
    if not matching_anchors:
        raise OpenOrderOwnershipError("ORDER_REGISTRY_IDENTITY_MISMATCH")
    positive_anchor_perm_ids = {
        int(row[1]) for row, _ in matching_anchors if int(row[1] or 0) > 0
    }
    if (
        snapshot["permId"] > 0
        and positive_anchor_perm_ids
        and snapshot["permId"] not in positive_anchor_perm_ids
    ):
        raise OpenOrderOwnershipError("OPEN_ORDER_PERM_ID_MISMATCH")
    if not any(str(row[3] or "").upper() == snapshot["action"] for row, _ in matching_anchors):
        raise OpenOrderOwnershipError("OPEN_ORDER_SIDE_MISMATCH")

    v2_payloads = [
        payload
        for _, payload in matching_anchors
        if payload.get("schema") == "EXPERIMENT_ORDER_REGISTRY_V2"
    ]
    if v2_payloads:
        if not any(
            int(payload.get("execution_client_id") or 0) == execution_client_id
            for payload in v2_payloads
        ):
            raise OpenOrderOwnershipError("OPEN_ORDER_CLIENT_ID_MISMATCH")
        expected_accounts = {
            str(payload.get("account") or "")
            for payload in v2_payloads
            if str(payload.get("account") or "")
        }
        if expected_accounts and snapshot["account"] not in expected_accounts:
            raise OpenOrderOwnershipError("OPEN_ORDER_ACCOUNT_MISMATCH")

    if snapshot["state_sha256"] != action.observed_state_sha256:
        raise OpenOrderOwnershipError("OPEN_ORDER_STATE_CHANGED")
    if snapshot["status"].upper() not in ACTIONABLE_ORDER_STATUSES:
        raise OpenOrderOwnershipError("OPEN_ORDER_NOT_ACTIONABLE")
    return candidate, snapshot


def lifecycle_attempt_exists(
    db: Database, *, order_ref: str, decision_cycle_id: str
) -> bool:
    rows = db.execute(
        "SELECT payload_json FROM experiment_order_registry "
        "WHERE order_ref=? ORDER BY sequence",
        (order_ref,),
    ).fetchall()
    for row in rows:
        payload = _registry_payload(row[0])
        if (
            str(payload.get("lifecycle_event") or "").endswith("_ATTEMPT")
            and payload.get("decision_cycle_id") == decision_cycle_id
        ):
            return True
    return False
