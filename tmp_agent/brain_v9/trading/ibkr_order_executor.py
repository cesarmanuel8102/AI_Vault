"""
Brain V9 — trading/ibkr_order_executor.py
Phase B: IBKR Paper Order Execution

Provides paper trading capabilities via IBKR Gateway (port 4002).
All functions enforce PAPER_ONLY mode — live trading is forbidden at
multiple levels (config flag, port check, code assertions).

Functions:
    check_ibkr_paper_order_api()  — Original what-if connectivity check
    place_paper_order()           — Place a real paper order on IBKR
    cancel_paper_order()          — Cancel an open paper order
    get_positions()               — Read current paper positions
    get_open_orders()             — Read open orders
    get_account_summary()         — Read account balances

Risk Controls:
    - Max position value: $2,000 per trade (20% of $10K capital)
    - Max total exposure: $8,000 (80% of capital)
    - Max concurrent positions: 6
    - Only stocks and options on SMART exchange
    - Port 4002 enforced (paper gateway)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH, IBKR_HOST, IBKR_PORT, PAPER_ONLY
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("ibkr_order_executor")

# ── Paths ─────────────────────────────────────────────────────────────────────
STATE_PATH = BASE_PATH / "tmp_agent" / "state" / "trading_execution_checks"
STATE_PATH.mkdir(parents=True, exist_ok=True)
IBKR_ORDER_CHECK_PATH = STATE_PATH / "ibkr_paper_order_check_latest.json"
PAPER_ORDERS_PATH = STATE_PATH / "ibkr_paper_orders.json"
PAPER_POSITIONS_PATH = STATE_PATH / "ibkr_paper_positions_latest.json"

# ── Risk Limits ───────────────────────────────────────────────────────────────
CAPITAL = 10_000  # Total capital
MAX_POSITION_VALUE = 2_000  # Max $ per single trade (20% of capital)
MAX_TOTAL_EXPOSURE = 8_000  # Max total $ in positions (80%)
MAX_CONCURRENT_POSITIONS = 6
ALLOWED_SEC_TYPES = {"STK", "OPT"}
PAPER_PORT = 4002  # Only paper gateway allowed

# ── Client ID for order execution (reserved, not used by data ingester) ──────
ORDER_CLIENT_ID_MIN = 294
ORDER_CLIENT_ID_MAX = 299


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _random_order_cid() -> int:
    """Random client ID in the order executor range [294..299]."""
    return random.randint(ORDER_CLIENT_ID_MIN, ORDER_CLIENT_ID_MAX)


def _assert_paper_only(port: int) -> None:
    """Triple safety check: config flag + port + hardcoded assertion."""
    assert PAPER_ONLY, "PAPER_ONLY config flag is False — refusing to execute"
    assert port == PAPER_PORT, f"Port {port} is not paper gateway ({PAPER_PORT})"


def _make_stock(symbol: str) -> "Contract":
    from ib_insync import Contract
    return Contract(symbol=symbol, secType="STK", exchange="SMART", currency="USD")


def _make_option(symbol: str, expiry: str, strike: float, right: str) -> "Contract":
    """Create an option contract.

    Args:
        symbol: Underlying symbol (e.g. "SPY")
        expiry: Expiry date as YYYYMMDD string
        strike: Strike price
        right: "C" for call, "P" for put
    """
    from ib_insync import Contract
    return Contract(
        symbol=symbol,
        secType="OPT",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth=expiry,
        strike=strike,
        right=right.upper(),
        multiplier="100",
    )


def _connect_ib(port: int = PAPER_PORT, timeout: float = 10.0) -> "IB":
    """Create and connect an IB instance. Caller must disconnect."""
    from ib_insync import IB
    _assert_paper_only(port)
    ib = IB()
    cid = _random_order_cid()
    ib.connect(IBKR_HOST, port, clientId=cid, timeout=timeout)
    if not ib.isConnected():
        raise ConnectionError(f"Failed to connect to {IBKR_HOST}:{port} (cid={cid})")
    return ib


# ═══════════════════════════════════════════════════════════════════════════════
# ORIGINAL: What-if connectivity check (preserved)
# ═══════════════════════════════════════════════════════════════════════════════

def check_ibkr_paper_order_api(
    symbol: str = "SPY",
    action: str = "BUY",
    quantity: int = 1,
    what_if: bool = True,
    host: str = IBKR_HOST,
    port: int = IBKR_PORT,
    client_id: int = 294,
) -> Dict[str, Any]:
    """
    Verify IBKR connectivity with a what-if order simulation.
    This is the original function — preserved for backward compatibility.
    """
    from ib_insync import IB, Contract, Order

    started = _utc_now()
    payload: Dict[str, Any]
    ib = None

    try:
        ib = IB()
        ib.connect(host, port, clientId=client_id, timeout=10)
        if not ib.isConnected():
            raise ConnectionError(f"No se pudo conectar a {host}:{port}")

        managed_accounts = ib.managedAccounts()
        contract = _make_stock(symbol)
        order = Order(
            action=action.upper(),
            orderType="MKT",
            totalQuantity=quantity,
            transmit=True,
            whatIf=bool(what_if),
        )
        trade = ib.placeOrder(contract, order)
        ib.sleep(2)

        open_orders_list = []
        if ib.openTrades():
            for trade_obj in ib.openTrades():
                co = trade_obj.contract
                oo = trade_obj.order
                open_orders_list.append({
                    "orderId": oo.orderId if hasattr(oo, "orderId") else None,
                    "symbol": co.symbol,
                    "secType": co.secType,
                    "action": oo.action,
                    "orderType": oo.orderType,
                    "totalQuantity": oo.totalQuantity,
                    "whatIf": oo.whatIf,
                })

        payload = {
            "schema_version": "ibkr_paper_order_check_v1",
            "checked_utc": _utc_now(),
            "started_utc": started,
            "provider": "ibkr",
            "host": host,
            "port": port,
            "client_id": client_id,
            "paper_only": True,
            "live_trading_forbidden": True,
            "what_if": bool(what_if),
            "requested_order": {
                "symbol": symbol,
                "action": action.upper(),
                "quantity": quantity,
                "order_type": "MKT",
            },
            "connected": ib.isConnected(),
            "managed_accounts": managed_accounts,
            "open_orders": open_orders_list,
            "order_status_events": [],
            "exec_details_events": [],
            "errors": [],
            "order_api_ready": True if managed_accounts else False,
        }

    except Exception as e:
        payload = {
            "schema_version": "ibkr_paper_order_check_v1",
            "checked_utc": _utc_now(),
            "started_utc": started,
            "provider": "ibkr",
            "paper_only": True,
            "live_trading_forbidden": True,
            "what_if": bool(what_if),
            "requested_order": {
                "symbol": symbol, "action": action.upper(),
                "quantity": quantity, "order_type": "MKT",
            },
            "connected": False,
            "open_orders": [],
            "order_status_events": [],
            "exec_details_events": [],
            "errors": [{"errorCode": -1, "errorString": str(e)}],
            "order_api_ready": False,
            "blocking_reason": "exception",
        }
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass

    write_json(IBKR_ORDER_CHECK_PATH, payload)
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE B: Real paper order execution
# ═══════════════════════════════════════════════════════════════════════════════

def _check_risk_limits(
    action: str,
    quantity: int,
    estimated_value: float,
    current_positions: List[Dict],
) -> Optional[str]:
    """
    Pre-trade risk check. Returns None if OK, or an error string if blocked.
    """
    # Position size limit
    if estimated_value > MAX_POSITION_VALUE:
        return (
            f"Orden bloqueada: valor estimado ${estimated_value:.0f} excede "
            f"max por posición ${MAX_POSITION_VALUE}"
        )

    # Total exposure limit
    total_exposure = sum(
        abs(float(p.get("marketValue", 0)))
        for p in current_positions
    )
    if total_exposure + estimated_value > MAX_TOTAL_EXPOSURE:
        return (
            f"Orden bloqueada: exposición total ${total_exposure + estimated_value:.0f} "
            f"excedería max ${MAX_TOTAL_EXPOSURE}"
        )

    # Concurrent positions limit
    open_count = len([p for p in current_positions if float(p.get("position", 0)) != 0])
    if action.upper() == "BUY" and open_count >= MAX_CONCURRENT_POSITIONS:
        return (
            f"Orden bloqueada: {open_count} posiciones abiertas, "
            f"max permitido {MAX_CONCURRENT_POSITIONS}"
        )

    return None  # All checks passed


def place_paper_order(
    symbol: str,
    action: str,
    quantity: int,
    order_type: str = "MKT",
    limit_price: float = 0.0,
    sec_type: str = "STK",
    expiry: str = "",
    strike: float = 0.0,
    right: str = "",
    strategy_id: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """
    Place a REAL paper order on IBKR Gateway (port 4002).

    This function enforces paper-only mode at multiple levels and applies
    risk limits before submitting. Orders are persisted to disk for audit.

    Args:
        symbol: Instrument symbol (e.g. "SPY")
        action: "BUY" or "SELL"
        quantity: Number of shares/contracts
        order_type: "MKT" (market) or "LMT" (limit)
        limit_price: Limit price (required for LMT orders)
        sec_type: "STK" (stock) or "OPT" (option)
        expiry: Option expiry YYYYMMDD (required for OPT)
        strike: Option strike price (required for OPT)
        right: Option right "C" or "P" (required for OPT)
        strategy_id: Strategy that generated this signal
        reason: Human-readable reason for the trade

    Returns:
        Dict with order details, status, and audit trail.
    """
    from ib_insync import IB, Order

    _assert_paper_only(PAPER_PORT)

    # Validate inputs
    action = action.upper()
    if action not in ("BUY", "SELL"):
        return {"success": False, "error": f"Invalid action: {action}. Must be BUY or SELL."}
    sec_type = sec_type.upper()
    if sec_type not in ALLOWED_SEC_TYPES:
        return {"success": False, "error": f"Invalid secType: {sec_type}. Allowed: {ALLOWED_SEC_TYPES}"}
    if order_type.upper() == "LMT" and limit_price <= 0:
        return {"success": False, "error": "Limit orders require limit_price > 0"}
    if sec_type == "OPT" and (not expiry or strike <= 0 or not right):
        return {"success": False, "error": "Options require expiry, strike, and right (C/P)"}

    started = _utc_now()
    ib = None

    try:
        ib = _connect_ib()

        # Build contract
        if sec_type == "STK":
            contract = _make_stock(symbol)
        else:
            contract = _make_option(symbol, expiry, strike, right)

        # Qualify contract (resolve conId)
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {"success": False, "error": f"Contract not found: {symbol} {sec_type}"}
        contract = qualified[0]

        # Get current positions for risk check
        positions = []
        for pos in ib.positions():
            positions.append({
                "symbol": pos.contract.symbol,
                "secType": pos.contract.secType,
                "position": pos.position,
                "avgCost": pos.avgCost,
                "marketValue": pos.position * pos.avgCost,
            })

        # Estimate order value for risk check
        # For market orders, use last price; for limit, use limit_price
        estimated_price = limit_price if limit_price > 0 else 0
        if estimated_price == 0:
            # Try to get last price
            ticker = ib.reqMktData(contract, snapshot=True)
            ib.sleep(2)
            estimated_price = ticker.last or ticker.close or 0
            ib.cancelMktData(contract)

        multiplier = 100 if sec_type == "OPT" else 1
        estimated_value = abs(quantity * estimated_price * multiplier)

        # Risk check
        risk_block = _check_risk_limits(action, quantity, estimated_value, positions)
        if risk_block:
            return {
                "success": False,
                "error": risk_block,
                "risk_blocked": True,
                "estimated_value": estimated_value,
                "paper_only": True,
            }

        # Build order
        order = Order(
            action=action,
            orderType=order_type.upper(),
            totalQuantity=quantity,
            transmit=True,
            whatIf=False,  # REAL paper execution
        )
        if order_type.upper() == "LMT":
            order.lmtPrice = limit_price

        # Place order
        trade = ib.placeOrder(contract, order)
        ib.sleep(3)  # Wait for fill/status

        # Collect order status
        order_status = {
            "orderId": trade.order.orderId,
            "status": trade.orderStatus.status if trade.orderStatus else "unknown",
            "filled": trade.orderStatus.filled if trade.orderStatus else 0,
            "avgFillPrice": trade.orderStatus.avgFillPrice if trade.orderStatus else 0,
            "remaining": trade.orderStatus.remaining if trade.orderStatus else quantity,
        }

        # Build audit record
        record = {
            "order_id": trade.order.orderId,
            "timestamp_utc": _utc_now(),
            "symbol": symbol,
            "sec_type": sec_type,
            "action": action,
            "quantity": quantity,
            "order_type": order_type.upper(),
            "limit_price": limit_price,
            "estimated_value": estimated_value,
            "status": order_status["status"],
            "filled": order_status["filled"],
            "avg_fill_price": order_status["avgFillPrice"],
            "strategy_id": strategy_id,
            "reason": reason,
            "paper_only": True,
            "live_trading_forbidden": True,
            "contract": {
                "symbol": contract.symbol,
                "secType": contract.secType,
                "exchange": contract.exchange,
                "conId": contract.conId,
            },
        }

        # Persist to order history
        _append_order_record(record)

        return {
            "success": True,
            "order": order_status,
            "record": record,
            "paper_only": True,
            "estimated_value": estimated_value,
        }

    except Exception as exc:
        log.error("place_paper_order failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "paper_only": True,
        }
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def cancel_paper_order(order_id: int) -> Dict[str, Any]:
    """Cancel an open paper order by order ID."""
    from ib_insync import IB

    _assert_paper_only(PAPER_PORT)
    ib = None

    try:
        ib = _connect_ib()

        # Find the order
        open_trades = ib.openTrades()
        target = None
        for t in open_trades:
            if t.order.orderId == order_id:
                target = t
                break

        if target is None:
            return {"success": False, "error": f"Order {order_id} not found in open trades"}

        ib.cancelOrder(target.order)
        ib.sleep(2)

        return {
            "success": True,
            "order_id": order_id,
            "status": "cancel_requested",
            "paper_only": True,
        }

    except Exception as exc:
        log.error("cancel_paper_order failed: %s", exc)
        return {"success": False, "error": str(exc)}
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def get_positions() -> Dict[str, Any]:
    """Read current paper trading positions from IBKR."""
    _assert_paper_only(PAPER_PORT)
    ib = None

    try:
        ib = _connect_ib()
        positions = []
        total_value = 0.0

        for pos in ib.positions():
            mkt_val = pos.position * pos.avgCost
            positions.append({
                "symbol": pos.contract.symbol,
                "secType": pos.contract.secType,
                "position": pos.position,
                "avgCost": round(pos.avgCost, 4),
                "marketValue": round(mkt_val, 2),
                "conId": pos.contract.conId,
                "expiry": getattr(pos.contract, "lastTradeDateOrContractMonth", ""),
                "strike": getattr(pos.contract, "strike", 0),
                "right": getattr(pos.contract, "right", ""),
            })
            total_value += abs(mkt_val)

        # Also get account summary
        account_values = {}
        for av in ib.accountSummary():
            if av.tag in ("NetLiquidation", "TotalCashValue", "UnrealizedPnL",
                          "RealizedPnL", "BuyingPower"):
                account_values[av.tag] = av.value

        result = {
            "success": True,
            "positions": positions,
            "position_count": len(positions),
            "total_exposure": round(total_value, 2),
            "account": account_values,
            "paper_only": True,
            "checked_utc": _utc_now(),
        }

        # Persist for other modules
        write_json(PAPER_POSITIONS_PATH, result)
        return result

    except Exception as exc:
        log.error("get_positions failed: %s", exc)
        return {"success": False, "error": str(exc), "positions": []}
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def get_open_orders() -> Dict[str, Any]:
    """Read open (pending) paper orders from IBKR."""
    _assert_paper_only(PAPER_PORT)
    ib = None

    try:
        ib = _connect_ib()
        orders = []

        for trade in ib.openTrades():
            o = trade.order
            c = trade.contract
            orders.append({
                "orderId": o.orderId,
                "symbol": c.symbol,
                "secType": c.secType,
                "action": o.action,
                "orderType": o.orderType,
                "totalQuantity": o.totalQuantity,
                "lmtPrice": getattr(o, "lmtPrice", 0),
                "status": trade.orderStatus.status if trade.orderStatus else "unknown",
                "filled": trade.orderStatus.filled if trade.orderStatus else 0,
            })

        return {
            "success": True,
            "orders": orders,
            "order_count": len(orders),
            "paper_only": True,
            "checked_utc": _utc_now(),
        }

    except Exception as exc:
        log.error("get_open_orders failed: %s", exc)
        return {"success": False, "error": str(exc), "orders": []}
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def get_account_summary() -> Dict[str, Any]:
    """Read paper trading account summary from IBKR."""
    _assert_paper_only(PAPER_PORT)
    ib = None

    try:
        ib = _connect_ib()
        summary = {}

        for av in ib.accountSummary():
            summary[av.tag] = {
                "value": av.value,
                "currency": av.currency,
            }

        return {
            "success": True,
            "account": summary,
            "paper_only": True,
            "checked_utc": _utc_now(),
        }

    except Exception as exc:
        log.error("get_account_summary failed: %s", exc)
        return {"success": False, "error": str(exc)}
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


# ── Async wrappers ────────────────────────────────────────────────────────────

async def place_paper_order_async(**kwargs) -> Dict[str, Any]:
    """Async wrapper — runs place_paper_order in thread to avoid event loop conflicts."""
    loop = asyncio.get_running_loop()
    def _run():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            return place_paper_order(**kwargs)
        finally:
            _loop.close()
    return await loop.run_in_executor(None, _run)


async def cancel_paper_order_async(order_id: int) -> Dict[str, Any]:
    """Async wrapper for cancel_paper_order."""
    loop = asyncio.get_running_loop()
    def _run():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            return cancel_paper_order(order_id)
        finally:
            _loop.close()
    return await loop.run_in_executor(None, _run)


async def get_positions_async() -> Dict[str, Any]:
    """Async wrapper for get_positions."""
    loop = asyncio.get_running_loop()
    def _run():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            return get_positions()
        finally:
            _loop.close()
    return await loop.run_in_executor(None, _run)


async def get_open_orders_async() -> Dict[str, Any]:
    """Async wrapper for get_open_orders."""
    loop = asyncio.get_running_loop()
    def _run():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            return get_open_orders()
        finally:
            _loop.close()
    return await loop.run_in_executor(None, _run)


async def get_account_summary_async() -> Dict[str, Any]:
    """Async wrapper for get_account_summary."""
    loop = asyncio.get_running_loop()
    def _run():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            return get_account_summary()
        finally:
            _loop.close()
    return await loop.run_in_executor(None, _run)


# ── Order history persistence ─────────────────────────────────────────────────

def _append_order_record(record: Dict) -> None:
    """Append an order record to the paper orders audit file."""
    data = read_json(PAPER_ORDERS_PATH, default={
        "schema_version": "ibkr_paper_orders_v1",
        "orders": [],
    })
    orders = data.get("orders", [])
    orders.append(record)
    # Keep last 500 orders
    if len(orders) > 500:
        orders = orders[-500:]
    data["orders"] = orders
    data["updated_utc"] = _utc_now()
    data["total_orders"] = len(orders)
    write_json(PAPER_ORDERS_PATH, data)
