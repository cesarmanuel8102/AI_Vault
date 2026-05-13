"""
Brain V9 — trading/ibkr_performance_tracker.py
IBKR Performance Tracker: Polls paper positions & P&L → feeds scorecards.

Closes Gap: IBKR P&L feedback → governance decisions.

The tracker:
1. Periodically reads IBKR paper positions via ibkr_order_executor
2. Maps positions to strategy_id (via order audit trail)
3. Updates scorecard P&L fields (realized, unrealized, net)
4. Triggers governance recompute → freeze/degrade if losing
5. Persists position snapshots for historical analysis

Usage:
    # One-shot (from agent tool or scheduler)
    result = await poll_ibkr_performance()

    # Background loop
    tracker = IBKRPerformanceTracker(interval=300)
    await tracker.start()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH, PAPER_ONLY
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("IBKRPerformanceTracker")

# ── Paths ─────────────────────────────────────────────────────────────────────
_STATE_DIR = BASE_PATH / "tmp_agent" / "state" / "ibkr_performance"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_SNAPSHOTS_PATH = _STATE_DIR / "position_snapshots.json"
_TRACKER_STATE_PATH = _STATE_DIR / "tracker_state.json"
_SCORECARD_PATH = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
_ORDER_AUDIT_PATH = BASE_PATH / "tmp_agent" / "state" / "trading_execution_checks" / "ibkr_paper_orders.json"

# ── Risk thresholds for auto-degradation ──────────────────────────────────────
MAX_LOSS_PER_STRATEGY = -500.0       # $500 loss → freeze
MAX_LOSS_PCT_PER_STRATEGY = -0.10    # 10% of capital → freeze
MAX_PORTFOLIO_LOSS = -1000.0         # $1K total loss → freeze all
CAPITAL = 10_000


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_order_to_strategy_map() -> Dict[str, str]:
    """Build order_id → strategy_id mapping from order audit trail."""
    audit = read_json(_ORDER_AUDIT_PATH) if _ORDER_AUDIT_PATH.exists() else {}
    orders = audit.get("orders", [])
    mapping = {}
    for o in orders:
        oid = str(o.get("order_id", ""))
        sid = o.get("strategy_id", "")
        if oid and sid:
            mapping[oid] = sid
    return mapping


def _map_position_to_strategy(position: Dict, order_map: Dict[str, str]) -> str:
    """Try to map an IBKR position to a strategy_id."""
    # Direct match via order_id in position metadata
    oid = str(position.get("order_id", ""))
    if oid in order_map:
        return order_map[oid]

    # Fallback: match by symbol + sec_type against strategy specs
    symbol = position.get("symbol", "").upper()
    sec_type = position.get("sec_type", "").upper()

    from brain_v9.trading.qc_strategy_bridge import BRAIN_OPTIONS_V1_STRATEGIES
    for sid, spec in BRAIN_OPTIONS_V1_STRATEGIES.items():
        if spec.get("underlying", "").upper() == symbol:
            return sid

    return f"unmatched_{symbol}_{sec_type}"


async def poll_ibkr_performance() -> Dict[str, Any]:
    """
    One-shot poll: read IBKR paper positions + account → update scorecards.

    Returns summary of what was found and what was updated.
    """
    assert PAPER_ONLY, "PAPER_ONLY must be True"

    result = {
        "success": False,
        "timestamp": _now_utc(),
        "positions_found": 0,
        "strategies_updated": [],
        "degradations": [],
        "account_summary": {},
        "errors": [],
    }

    try:
        from brain_v9.trading.ibkr_order_executor import (
            get_positions, get_account_summary,
        )
    except ImportError as e:
        result["errors"].append(f"Import error: {e}")
        return result

    # ── 1. Read positions ─────────────────────────────────────────────────
    try:
        pos_result = get_positions()
        if not pos_result.get("success"):
            result["errors"].append(f"get_positions failed: {pos_result.get('error', 'unknown')}")
            return result
    except Exception as e:
        result["errors"].append(f"get_positions exception: {e}")
        return result

    positions = pos_result.get("positions", [])
    account = pos_result.get("account", {})
    result["positions_found"] = len(positions)
    result["account_summary"] = {
        "net_liquidation": account.get("NetLiquidation", 0),
        "total_cash": account.get("TotalCashValue", 0),
        "unrealized_pnl": account.get("UnrealizedPnL", 0),
        "realized_pnl": account.get("RealizedPnL", 0),
        "buying_power": account.get("BuyingPower", 0),
    }

    # ── 2. Read account summary for portfolio-level metrics ───────────────
    try:
        acct_result = get_account_summary()
        if acct_result.get("success"):
            acct_data = acct_result.get("summary", {})
            result["account_summary"].update({
                "gross_position_value": acct_data.get("GrossPositionValue", 0),
                "maintenance_margin": acct_data.get("MaintMarginReq", 0),
            })
    except Exception as e:
        result["errors"].append(f"get_account_summary warn: {e}")

    # ── 3. Map positions to strategies ────────────────────────────────────
    order_map = _load_order_to_strategy_map()
    strategy_pnl: Dict[str, Dict] = {}

    for pos in positions:
        sid = _map_position_to_strategy(pos, order_map)
        if sid not in strategy_pnl:
            strategy_pnl[sid] = {
                "unrealized_pnl": 0.0,
                "realized_pnl": 0.0,
                "position_value": 0.0,
                "contracts": 0,
                "positions": [],
            }
        sp = strategy_pnl[sid]
        sp["unrealized_pnl"] += float(pos.get("unrealized_pnl", 0))
        sp["realized_pnl"] += float(pos.get("realized_pnl", 0))
        sp["position_value"] += abs(float(pos.get("market_value", 0)))
        sp["contracts"] += abs(int(pos.get("quantity", 0)))
        sp["positions"].append({
            "symbol": pos.get("symbol"),
            "sec_type": pos.get("sec_type"),
            "quantity": pos.get("quantity"),
            "avg_cost": pos.get("avg_cost"),
            "market_price": pos.get("market_price"),
            "market_value": pos.get("market_value"),
            "unrealized_pnl": pos.get("unrealized_pnl"),
        })

    # ── 4. Update scorecards with real IBKR P&L ──────────────────────────
    if not _SCORECARD_PATH.exists():
        result["errors"].append("scorecards file not found")
        result["success"] = True
        return result

    sc_data = read_json(_SCORECARD_PATH)
    scorecards = sc_data.get("scorecards", {})
    updated = []
    degradations = []

    for sid, pnl_info in strategy_pnl.items():
        if sid.startswith("unmatched_"):
            continue

        card = scorecards.get(sid)
        if not card:
            continue

        # Only update strategies in live_paper state
        gov_state = card.get("governance_state", "")
        if gov_state != "live_paper":
            continue

        # Update P&L fields
        card["ibkr_unrealized_pnl"] = pnl_info["unrealized_pnl"]
        card["ibkr_realized_pnl"] = pnl_info["realized_pnl"]
        card["ibkr_net_pnl"] = pnl_info["unrealized_pnl"] + pnl_info["realized_pnl"]
        card["ibkr_position_value"] = pnl_info["position_value"]
        card["ibkr_contracts_open"] = pnl_info["contracts"]
        card["ibkr_last_poll_utc"] = _now_utc()
        card["ibkr_positions"] = pnl_info["positions"]

        net_pnl = card["ibkr_net_pnl"]
        pnl_pct = net_pnl / CAPITAL if CAPITAL > 0 else 0

        updated.append({
            "strategy_id": sid,
            "net_pnl": net_pnl,
            "pnl_pct": pnl_pct,
            "positions": pnl_info["contracts"],
        })

        # ── 5. Check degradation rules ────────────────────────────────────
        should_freeze = False
        freeze_reason = ""

        if net_pnl <= MAX_LOSS_PER_STRATEGY:
            should_freeze = True
            freeze_reason = f"ibkr_loss_absolute: ${net_pnl:.2f} <= ${MAX_LOSS_PER_STRATEGY}"
        elif pnl_pct <= MAX_LOSS_PCT_PER_STRATEGY:
            should_freeze = True
            freeze_reason = f"ibkr_loss_pct: {pnl_pct:.1%} <= {MAX_LOSS_PCT_PER_STRATEGY:.0%}"

        if should_freeze:
            card["governance_state"] = "frozen"
            card["freeze_reason"] = freeze_reason
            card["frozen_utc"] = _now_utc()
            card["frozen_from"] = "live_paper"
            degradations.append({
                "strategy_id": sid,
                "reason": freeze_reason,
                "net_pnl": net_pnl,
            })
            log.warning(
                "FROZEN %s from live_paper: %s (P&L=$%.2f)",
                sid, freeze_reason, net_pnl,
            )

    # ── 6. Portfolio-level check ──────────────────────────────────────────
    total_unrealized = float(result["account_summary"].get("unrealized_pnl", 0))
    total_realized = float(result["account_summary"].get("realized_pnl", 0))
    total_pnl = total_unrealized + total_realized

    if total_pnl <= MAX_PORTFOLIO_LOSS:
        # Freeze ALL live_paper strategies
        for sid, card in scorecards.items():
            if card.get("governance_state") == "live_paper":
                card["governance_state"] = "frozen"
                card["freeze_reason"] = f"portfolio_loss: ${total_pnl:.2f} <= ${MAX_PORTFOLIO_LOSS}"
                card["frozen_utc"] = _now_utc()
                card["frozen_from"] = "live_paper"
                degradations.append({
                    "strategy_id": sid,
                    "reason": f"portfolio_loss_emergency: ${total_pnl:.2f}",
                })
                log.critical(
                    "EMERGENCY FREEZE ALL: portfolio loss $%.2f — froze %s",
                    total_pnl, sid,
                )

    # ── 7. Save updated scorecards ────────────────────────────────────────
    if updated or degradations:
        sc_data["scorecards"] = scorecards
        sc_data["updated_utc"] = _now_utc()
        write_json(_SCORECARD_PATH, sc_data)

    # ── 8. Save position snapshot ─────────────────────────────────────────
    snapshot = {
        "timestamp": _now_utc(),
        "positions": positions,
        "account": result["account_summary"],
        "strategy_pnl": {
            sid: {k: v for k, v in info.items() if k != "positions"}
            for sid, info in strategy_pnl.items()
        },
        "degradations": degradations,
    }

    snapshots = read_json(_SNAPSHOTS_PATH) if _SNAPSHOTS_PATH.exists() else {"snapshots": []}
    snapshots["snapshots"].append(snapshot)
    # Keep last 500 snapshots
    if len(snapshots["snapshots"]) > 500:
        snapshots["snapshots"] = snapshots["snapshots"][-500:]
    write_json(_SNAPSHOTS_PATH, snapshots)

    result["success"] = True
    result["strategies_updated"] = updated
    result["degradations"] = degradations

    log.info(
        "IBKR performance poll: %d positions, %d strategies updated, %d degradations",
        len(positions), len(updated), len(degradations),
    )

    return result


# ── Async wrapper ─────────────────────────────────────────────────────────────
async def poll_ibkr_performance_async() -> Dict[str, Any]:
    """Async wrapper for poll_ibkr_performance."""
    return await poll_ibkr_performance()


# ── Background Tracker Class ─────────────────────────────────────────────────
class IBKRPerformanceTracker:
    """Background task that polls IBKR positions/P&L every N seconds."""

    def __init__(self, interval: int = 300):
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            log.warning("IBKRPerformanceTracker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("IBKRPerformanceTracker started (interval=%ds)", self.interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("IBKRPerformanceTracker stopped")

    async def _loop(self):
        while self._running:
            try:
                result = await poll_ibkr_performance()
                if not result.get("success"):
                    log.warning("Performance poll failed: %s", result.get("errors"))
            except Exception as e:
                log.error("Performance tracker error: %s", e)
            await asyncio.sleep(self.interval)

    def status(self) -> Dict:
        state = read_json(_TRACKER_STATE_PATH) if _TRACKER_STATE_PATH.exists() else {}
        return {
            "running": self._running,
            "interval_seconds": self.interval,
            "last_poll": state.get("last_poll"),
        }
