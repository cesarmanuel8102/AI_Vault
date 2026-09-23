from __future__ import annotations

from decimal import Decimal
from typing import Any

from .canonical import sha256_json


EXECUTION_CLIENT_ID = 19761
EXPERIMENT_ORDER_PREFIX = "codex-ibkr-paper-30d"
ACTIONABLE_ORDER_STATUSES = frozenset(
    {"PENDINGSUBMIT", "PRESUBMITTED", "SUBMITTED", "PENDINGCANCEL"}
)
CANCELLED_ORDER_STATUSES = frozenset(
    {"CANCELLED", "APICANCELLED", "API CANCELLED"}
)


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
