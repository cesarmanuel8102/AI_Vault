from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .persistence import Database
from .repositories import utc_now
from .types import new_uuid7


EXECUTION_CLIENT_ID = 19761
EXPERIMENT_ORDER_PREFIX = "codex-ibkr-paper-30d"
ACTIONABLE_ORDER_STATUSES = frozenset(
    {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED", "PENDINGCANCEL"}
)
MODIFIABLE_ORDER_STATUSES = frozenset(
    {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED"}
)
CANCELLED_ORDER_STATUSES = frozenset(
    {"CANCELLED", "APICANCELLED", "API CANCELLED"}
)
V2_OWNERSHIP_ANCHOR_KEYS = frozenset(
    {
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
    }
)
V3_OWNERSHIP_ANCHOR_KEYS = V2_OWNERSHIP_ANCHOR_KEYS | {"contract"}


class OpenOrderOwnershipError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def append_order_registry_event(db: Database, payload: dict[str, Any]) -> str:
    """Append one canonical registry event using the caller's transaction."""
    required = {
        "order_ref", "client_order_id", "perm_id", "ibkr_order_id",
        "contract_id", "action", "quantity", "created_at_utc",
    }
    if not required <= payload.keys():
        raise ValueError("order registry payload is incomplete")
    registry_id = str(new_uuid7())
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            registry_id,
            payload["order_ref"],
            payload["client_order_id"],
            payload["perm_id"],
            payload["ibkr_order_id"],
            payload["contract_id"],
            payload["action"],
            str(payload["quantity"]),
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            payload["created_at_utc"],
        ),
    )
    return registry_id


def _decimal_text(value: Any) -> str:
    parsed = Decimal(str(value or 0))
    if not parsed.is_finite():
        raise ValueError("open-order numeric field must be finite")
    normalized = parsed.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _semantic_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (Decimal, float)):
        return _decimal_text(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _semantic_value(value.value)
    if isinstance(value, dict):
        return {
            str(key): _semantic_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_semantic_value(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _semantic_value(getattr(value, field.name))
            for field in fields(value)
        }
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return {
            str(key): _semantic_value(item)
            for key, item in sorted(attributes.items())
            if not str(key).startswith("_")
        }
    return str(value)


def _semantic_attributes(value: Any, decimal_fields: frozenset[str]) -> Any:
    attributes = _semantic_value(value)
    if not isinstance(attributes, dict):
        return attributes
    for name in decimal_fields:
        if name not in attributes:
            continue
        raw = getattr(value, name, None)
        if raw is None or raw == "":
            continue
        try:
            attributes[name] = _decimal_text(raw)
        except (ValueError, TypeError):
            pass
    return attributes


def canonical_contract_identity(contract: Any) -> dict[str, Any]:
    attributes = _semantic_attributes(contract, frozenset({"strike", "multiplier"}))
    if isinstance(attributes, dict):
        for explicit_field in {
            "conId",
            "symbol",
            "localSymbol",
            "secType",
            "exchange",
            "currency",
            "lastTradeDateOrContractMonth",
            "strike",
            "right",
            "multiplier",
            "comboLegs",
        }:
            attributes.pop(explicit_field, None)
    combo_legs = [
        {
            "conId": int(getattr(leg, "conId", 0) or 0),
            "ratio": int(getattr(leg, "ratio", 0) or 0),
            "action": str(getattr(leg, "action", "") or "").upper(),
            "exchange": str(getattr(leg, "exchange", "") or ""),
        }
        for leg in list(getattr(contract, "comboLegs", None) or [])
    ]
    symbol = str(getattr(contract, "symbol", "") or "")
    sec_type = str(getattr(contract, "secType", "") or "").upper()
    local_symbol = str(getattr(contract, "localSymbol", "") or "")
    if sec_type == "BAG":
        local_symbol = symbol
    return {
        "conId": int(getattr(contract, "conId", 0) or 0),
        "symbol": symbol,
        "localSymbol": local_symbol,
        "secType": sec_type,
        "exchange": str(getattr(contract, "exchange", "") or ""),
        "currency": str(getattr(contract, "currency", "") or ""),
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", "") or ""),
        "strike": _decimal_text(getattr(contract, "strike", 0)),
        "right": str(getattr(contract, "right", "") or "").upper(),
        "multiplier": _decimal_text(getattr(contract, "multiplier", 1) or 1),
        "comboLegs": combo_legs,
        "attributes": attributes,
    }


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
        "orderAttributes": _semantic_attributes(
            order,
            frozenset(
                {
                    "totalQuantity",
                    "lmtPrice",
                    "auxPrice",
                    "cashQty",
                    "discretionaryAmt",
                    "percentOffset",
                    "trailStopPrice",
                    "trailingPercent",
                    "competeAgainstBestOffset",
                    "midOffsetAtWhole",
                    "midOffsetAtHalf",
                }
            ),
        ),
        "status": str(getattr(status, "status", "") or ""),
        "filled": _decimal_text(getattr(status, "filled", 0)),
        "remaining": _decimal_text(getattr(status, "remaining", 0)),
        "contract": canonical_contract_identity(contract),
    }
    return {**payload, "state_sha256": sha256_json(payload)}


def preserved_open_order_sha256(snapshot: dict[str, Any]) -> str:
    preserved = {
        key: value
        for key, value in snapshot.items()
        if key
        not in {
            "state_sha256",
            "status",
            "filled",
            "remaining",
            "totalQuantity",
            "limitPrice",
        }
    }
    order_attributes = dict(preserved.get("orderAttributes") or {})
    order_attributes.pop("totalQuantity", None)
    order_attributes.pop("lmtPrice", None)
    preserved["orderAttributes"] = order_attributes
    return sha256_json(preserved)


def _registry_payload(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _contract_identity_matches(
    expected: dict[str, Any], actual: dict[str, Any], *, allow_zero_parent: bool
) -> bool:
    is_bag = (
        str(expected.get("secType") or "").upper() == "BAG"
        and str(actual.get("secType") or "").upper() == "BAG"
    )
    if is_bag:
        stable_parent_fields = {
            "conId",
            "symbol",
            "secType",
            "exchange",
            "currency",
            "expiry",
            "strike",
            "multiplier",
            "comboLegs",
        }
        if allow_zero_parent and int(expected.get("conId") or 0) == 0:
            stable_parent_fields.remove("conId")
        return all(expected.get(key) == actual.get(key) for key in stable_parent_fields)
    return expected == actual


def _append_broker_identity_binding(
    db: Database,
    *,
    action: Any,
    snapshot: dict[str, Any],
    source_hashes: list[str],
    execution_client_id: int,
) -> None:
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": "BROKER_IDENTITY_BOUND",
        "order_ref": action.order_ref,
        "client_order_id": action.order_id,
        "perm_id": snapshot["permId"],
        "ibkr_order_id": action.order_id,
        "contract_id": snapshot["contract"]["conId"],
        "action": snapshot["action"],
        "quantity": snapshot["totalQuantity"],
        "execution_client_id": execution_client_id,
        "account": snapshot["account"],
        "contract": snapshot["contract"],
        "source_anchor_sha256": source_hashes,
        "created_at_utc": utc_now(),
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(new_uuid7()),
            action.order_ref,
            action.order_id,
            snapshot["permId"],
            action.order_id,
            snapshot["contract"]["conId"],
            snapshot["action"],
            snapshot["totalQuantity"],
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            payload["created_at_utc"],
        ),
    )


def resolve_owned_open_trade(
    db: Database,
    trades: list[Any],
    action: Any,
    *,
    execution_client_id: int,
) -> tuple[Any, dict[str, Any]]:
    if not action.order_ref.startswith(f"{EXPERIMENT_ORDER_PREFIX}-"):
        raise OpenOrderOwnershipError("ORDER_REF_NAMESPACE_MISMATCH")

    rows = db.execute(
        "SELECT client_order_id,perm_id,ibkr_order_id,contract_id,action,"
        "quantity,payload_json,payload_sha256 "
        "FROM experiment_order_registry WHERE order_ref=? ORDER BY sequence",
        (action.order_ref,),
    ).fetchall()
    anchors = []
    for row in rows:
        payload = _registry_payload(row[6])
        lifecycle_event = payload.get("lifecycle_event")
        if lifecycle_event not in {
            "ISSUED_PRE_SEND",
            "BROKER_BOUND",
            "BROKER_IDENTITY_BOUND",
        }:
            if (
                payload.get("schema") == "EXPERIMENT_ORDER_REGISTRY_V2"
                and "lifecycle_event" not in payload
            ):
                if sha256_json(payload) != str(row[7] or ""):
                    raise OpenOrderOwnershipError(
                        "ORDER_REGISTRY_PAYLOAD_HASH_MISMATCH"
                    )
                raise OpenOrderOwnershipError(
                    "ORDER_REGISTRY_V2_PAYLOAD_INCOMPLETE"
                )
            continue
        if sha256_json(payload) != str(row[7] or ""):
            raise OpenOrderOwnershipError("ORDER_REGISTRY_PAYLOAD_HASH_MISMATCH")
        schema = payload.get("schema")
        required_keys = (
            V3_OWNERSHIP_ANCHOR_KEYS
            if schema == "EXPERIMENT_ORDER_REGISTRY_V3"
            else V2_OWNERSHIP_ANCHOR_KEYS
        )
        if not required_keys.issubset(payload):
            raise OpenOrderOwnershipError(
                "ORDER_REGISTRY_V2_PAYLOAD_INCOMPLETE"
            )
        payload_identity_matches = (
            str(payload.get("order_ref") or "") == action.order_ref
            and int(payload.get("client_order_id") or 0) == int(row[0] or 0)
            and int(payload.get("perm_id") or 0) == int(row[1] or 0)
            and int(payload.get("ibkr_order_id") or 0) == int(row[2] or 0)
            and int(payload.get("contract_id") or 0) == int(row[3] or 0)
            and str(payload.get("action") or "").upper()
            == str(row[4] or "").upper()
            and _decimal_text(payload.get("quantity")) == _decimal_text(row[5])
            and (
                schema != "EXPERIMENT_ORDER_REGISTRY_V3"
                or int((payload.get("contract") or {}).get("conId") or 0)
                == int(payload.get("contract_id") or 0)
            )
        )
        if not payload_identity_matches:
            raise OpenOrderOwnershipError(
                "ORDER_REGISTRY_PAYLOAD_IDENTITY_MISMATCH"
            )
        if not str(payload.get("account") or ""):
            raise OpenOrderOwnershipError("OPEN_ORDER_ACCOUNT_MISMATCH")
        anchors.append((row, payload))
    if not anchors:
        raise OpenOrderOwnershipError("ORDER_REGISTRY_OWNERSHIP_REQUIRED")
    if any(
        payload.get("schema")
        not in {"EXPERIMENT_ORDER_REGISTRY_V2", "EXPERIMENT_ORDER_REGISTRY_V3"}
        for _, payload in anchors
    ):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_V2_OWNERSHIP_REQUIRED")
    source_anchor_hashes = [
        str(row[7] or "")
        for row, payload in anchors
        if payload.get("lifecycle_event") != "BROKER_IDENTITY_BOUND"
    ]
    if any(
        payload.get("source_anchor_sha256") != source_anchor_hashes
        for _, payload in anchors
        if payload.get("lifecycle_event") == "BROKER_IDENTITY_BOUND"
    ):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_BINDING_SOURCE_MISMATCH")
    if any(int(row[0] or 0) != action.order_id for row, _ in anchors):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_ORDER_ID_MISMATCH")
    if any(int(row[2] or 0) != action.order_id for row, _ in anchors):
        raise OpenOrderOwnershipError("ORDER_REGISTRY_IBKR_ORDER_ID_MISMATCH")
    if action.perm_id is not None:
        positive_registry_perm_ids = {
            int(row[1]) for row, _ in anchors if int(row[1] or 0) > 0
        }
        if (
            positive_registry_perm_ids
            and positive_registry_perm_ids != {action.perm_id}
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

    is_bag = snapshot["contract"]["secType"] == "BAG"
    registry_contract_ids = {int(row[3] or 0) for row, _ in anchors}
    if is_bag:
        if any(
            value not in {0, action.contract_id} for value in registry_contract_ids
        ):
            raise OpenOrderOwnershipError("ORDER_REGISTRY_CONTRACT_ID_MISMATCH")
    elif registry_contract_ids != {action.contract_id}:
        raise OpenOrderOwnershipError("ORDER_REGISTRY_CONTRACT_ID_MISMATCH")

    v3_contracts = [
        payload.get("contract")
        for _, payload in anchors
        if payload.get("schema") == "EXPERIMENT_ORDER_REGISTRY_V3"
    ]
    if any(
        not isinstance(contract, dict)
        or not _contract_identity_matches(
            contract,
            snapshot["contract"],
            allow_zero_parent=is_bag,
        )
        for contract in v3_contracts
    ):
        raise OpenOrderOwnershipError("OPEN_ORDER_CONTRACT_IDENTITY_MISMATCH")

    positive_anchor_perm_ids = {
        int(row[1]) for row, _ in anchors if int(row[1] or 0) > 0
    }
    if positive_anchor_perm_ids and positive_anchor_perm_ids != {
        snapshot["permId"]
    }:
        raise OpenOrderOwnershipError("OPEN_ORDER_PERM_ID_MISMATCH")
    if any(str(row[4] or "").upper() != snapshot["action"] for row, _ in anchors):
        raise OpenOrderOwnershipError("OPEN_ORDER_SIDE_MISMATCH")

    if any(
        int(payload.get("execution_client_id") or 0) != execution_client_id
        for _, payload in anchors
    ):
        raise OpenOrderOwnershipError("OPEN_ORDER_CLIENT_ID_MISMATCH")
    expected_accounts = {
        str(payload.get("account") or "") for _, payload in anchors
    }
    if expected_accounts != {snapshot["account"]}:
        raise OpenOrderOwnershipError("OPEN_ORDER_ACCOUNT_MISMATCH")

    if snapshot["state_sha256"] != action.observed_state_sha256:
        raise OpenOrderOwnershipError("OPEN_ORDER_STATE_CHANGED")
    if snapshot["status"].upper() not in ACTIONABLE_ORDER_STATUSES:
        raise OpenOrderOwnershipError("OPEN_ORDER_NOT_ACTIONABLE")
    has_positive_v3_contract = any(
        isinstance(contract, dict) and int(contract.get("conId") or 0) > 0
        for contract in v3_contracts
    )
    if is_bag and not has_positive_v3_contract:
        broker_bound_perm_ids = {
            int(row[1] or 0)
            for row, payload in anchors
            if payload.get("lifecycle_event") == "BROKER_BOUND"
            and int(row[1] or 0) > 0
        }
        if broker_bound_perm_ids != {snapshot["permId"]}:
            raise OpenOrderOwnershipError("ORDER_REGISTRY_BROKER_BOUND_REQUIRED")
        _append_broker_identity_binding(
            db,
            action=action,
            snapshot=snapshot,
            source_hashes=[
                str(row[7] or "")
                for row, payload in anchors
                if payload.get("lifecycle_event") != "BROKER_IDENTITY_BOUND"
            ],
            execution_client_id=execution_client_id,
        )
    return candidate, snapshot


def lifecycle_attempt_exists(
    db: Database, *, order_ref: str, decision_cycle_id: str
) -> bool:
    rows = db.execute(
        "SELECT payload_json FROM experiment_order_registry "
        "ORDER BY sequence",
    ).fetchall()
    for row in rows:
        payload = _registry_payload(row[0])
        if (
            str(payload.get("lifecycle_event") or "").endswith("_ATTEMPT")
            and payload.get("decision_cycle_id") == decision_cycle_id
        ):
            return True
    return False
