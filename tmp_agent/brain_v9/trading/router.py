"""
Brain Chat V9 — trading/router.py
Todos los endpoints de trading como APIRouter (no como funciones sueltas).
"""
import json
import logging
from pathlib import Path
from typing import Annotated, Dict, List

from fastapi import APIRouter, Depends

from brain_v9.api_security import require_operator_access
from brain_v9.trading.connectors import IBKRReadonlyConnector, PocketOptionBridge, QuantConnectConnector, TiingoConnector
from brain_v9.trading.ibkr_order_executor import check_ibkr_paper_order_api
from brain_v9.trading.platform_dashboard_api import PlatformDashboardAPI, get_platform_dashboard_api
from brain_v9.core.state_io import read_json
import brain_v9.config as _cfg

router = APIRouter(prefix="/trading", tags=["trading"])
TRADING_POLICY_PATH = _cfg.TRADING_POLICY_PATH
log = logging.getLogger("trading.router")
OperatorAccess = Annotated[None, Depends(require_operator_access)]

# Instancias lazy (no bloquean el startup)
_tiingo: TiingoConnector       = None
_qc:     QuantConnectConnector = None
_ibkr:   IBKRReadonlyConnector = None
_po:     PocketOptionBridge    = None
_dashboard: PlatformDashboardAPI = None


def _get_tiingo() -> TiingoConnector:
    global _tiingo
    if _tiingo is None:
        _tiingo = TiingoConnector()
    return _tiingo

def _get_qc() -> QuantConnectConnector:
    global _qc
    if _qc is None:
        _qc = QuantConnectConnector()
    return _qc

def _get_ibkr() -> IBKRReadonlyConnector:
    global _ibkr
    if _ibkr is None:
        _ibkr = IBKRReadonlyConnector()
    return _ibkr

def _get_po() -> PocketOptionBridge:
    global _po
    if _po is None:
        _po = PocketOptionBridge()
    return _po


@router.get("/health")
async def trading_health() -> Dict:
    tiingo = await _get_tiingo().check_health()
    qc     = await _get_qc().check_health()
    ibkr   = await _get_ibkr().check_health()
    po     = await _get_po().check_health()
    return {
        "tiingo":        tiingo,
        "quantconnect":  qc,
        "ibkr":          ibkr,
        "pocket_option": po,
    }


@router.get("/policy")
async def trading_policy() -> Dict:
    try:
        if TRADING_POLICY_PATH.exists():
            return read_json(TRADING_POLICY_PATH, {})
    except Exception as exc:
        log.warning("Error reading trading policy from %s: %s", TRADING_POLICY_PATH, exc)
    return {
        "schema_version": "trading_autonomy_policy_v1",
        "global_rules": {
            "paper_only": True,
            "live_trading_forbidden": True,
            "capital_mutation_forbidden": True,
            "credentials_mutation_forbidden": True,
        },
        "note": "Policy file not generated yet by action executor.",
    }


@router.get("/ibkr/health")
async def ibkr_health() -> Dict:
    from brain_v9.config import IBKR_VIA_QC_CLOUD
    if IBKR_VIA_QC_CLOUD:
        # IBKR is accessed via QC Cloud, not local gateway
        from brain_v9.trading.qc_live_monitor import get_live_state
        state = get_live_state()
        deployed = state.get("deployed", False)
        return {
            "success": True,
            "provider": "ibkr",
            "display_name": "Interactive Brokers (via QC Cloud)",
            "mode": "qc_cloud",
            "port_open": False,
            "data_source": "qc_live_api",
            "data_freshness": "live" if deployed else "inactive",
            "qc_live_deployed": deployed,
            "qc_live_deploy_id": state.get("deploy_id", ""),
            "qc_live_status": state.get("status", ""),
            "last_poll_utc": state.get("last_poll_utc", ""),
            "poll_count": state.get("poll_count", 0),
            "message": "IBKR connected via QC Cloud — local gateway intentionally off",
        }
    return await _get_ibkr().check_health()


@router.post("/ibkr/paper-order-check")
async def ibkr_paper_order_check(_operator: OperatorAccess, symbol: str = "SPY", action: str = "BUY", quantity: int = 1, what_if: bool = True) -> Dict:
    # P-OP28e: ib_insync uses blocking I/O (connect + sleep); run in executor
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: check_ibkr_paper_order_api(symbol=symbol, action=action, quantity=quantity, what_if=what_if),
    )


@router.get("/market/{symbol}")
async def market_data(symbol: str, source: str = "tiingo", days: int = 30) -> Dict:
    if source == "tiingo":
        return await _get_tiingo().get_historical_data(symbol, days)
    elif source == "quantconnect":
        return await _get_qc().get_historical_data(symbol, days)
    return {"success": False, "error": f"Fuente desconocida: {source}"}


@router.get("/balance")
async def balance() -> Dict:
    return await _get_po().get_balance()


@router.get("/trades/open")
async def open_trades() -> Dict:
    return await _get_po().get_open_trades()


@router.get("/trades/history")
async def trade_history(limit: int = 100) -> Dict:
    return await _get_po().get_trade_history(limit)


@router.post("/trade")
async def place_trade(_operator: OperatorAccess, symbol: str, direction: str, amount: float, duration: int) -> Dict:
    """direction: 'call' o 'put'"""
    return await _get_po().place_trade(symbol, direction, amount, duration)


@router.post("/pocket-option/demo-order-check")
async def pocket_option_demo_order_check(_operator: OperatorAccess, symbol: str = "EURUSD_otc", direction: str = "call", amount: float = 10.0, duration: int = 60) -> Dict:
    result = await _get_po().place_trade(symbol, direction, amount, duration)
    return {
        "paper_only": True,
        "live_trading_forbidden": True,
        "requested_order": {
            "symbol": symbol,
            "direction": direction,
            "amount": amount,
            "duration": duration,
        },
        "result": result,
        "demo_order_api_ready": bool(result.get("success")),
        "blocking_reason": None if result.get("success") else result.get("reason") or result.get("error") or result.get("status"),
    }


# ── Platform Dashboard Endpoints ─────────────────────────────────────

def _get_dashboard() -> PlatformDashboardAPI:
    global _dashboard
    if _dashboard is None:
        _dashboard = get_platform_dashboard_api()
    return _dashboard


@router.get("/platforms/summary")
async def platforms_summary() -> Dict:
    """All platforms: U scores, metrics, accumulators, recommendations."""
    return _get_dashboard().get_all_platforms_summary()


@router.get("/platforms/{platform_name}/summary")
async def platform_summary(platform_name: str) -> Dict:
    """Single platform summary (U score, metrics, accumulator status)."""
    return _get_dashboard().get_platform_summary(platform_name)


@router.get("/platforms/{platform_name}/u-history")
async def platform_u_history(platform_name: str, limit: int = 100) -> List:
    """U-score history for a platform (most recent entries)."""
    return _get_dashboard().get_platform_u_history(platform_name, limit)


@router.get("/platforms/{platform_name}/trades")
async def platform_trades(platform_name: str, limit: int = 50) -> List:
    """Recent trade history for a platform."""
    return _get_dashboard().get_platform_trade_history(platform_name, limit)


@router.get("/platforms/compare")
async def platforms_compare() -> Dict:
    """Cross-platform ranking and comparison."""
    return _get_dashboard().compare_platforms()


@router.get("/platforms/{platform_name}/signals")
async def platform_signals(platform_name: str) -> Dict:
    """Signal pipeline analysis for a platform."""
    return _get_dashboard().get_platform_signals_analysis(platform_name)


# ═══════════════════════════════════════════════════════════════════════════════
# CLOSED-LOOP TRADING ENDPOINTS (Phase 9)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/closed-loop/status")
async def closed_loop_status() -> Dict:
    """Full closed-loop pipeline status: QC loop + IBKR loop + governance."""
    from brain_v9.core.state_io import read_json
    from pathlib import Path
    base = _cfg.BASE_PATH / "tmp_agent" / "state"

    # QC pipeline status
    qc_state = {}
    qc_ingestion_path = base / "qc_backtests" / "ingestion_state.json"
    if qc_ingestion_path.exists():
        qc_state = read_json(qc_ingestion_path)

    # QC iteration history
    iter_path = base / "qc_iterations" / "iteration_history.json"
    iter_data = read_json(iter_path) if iter_path.exists() else {}
    iter_summary = {
        sid: len(iters) for sid, iters in iter_data.get("iterations", {}).items()
    }

    # IBKR signal engine status
    signal_state_path = base / "ibkr_signals" / "engine_state.json"
    signal_state = read_json(signal_state_path) if signal_state_path.exists() else {}

    # IBKR performance tracker
    perf_path = base / "ibkr_performance" / "tracker_state.json"
    perf_state = read_json(perf_path) if perf_path.exists() else {}

    # Strategy scorecards summary
    sc_path = base / "strategy_engine" / "strategy_scorecards.json"
    sc_data = read_json(sc_path) if sc_path.exists() else {}
    scorecards = sc_data.get("scorecards", {})

    state_counts = {}
    for card in scorecards.values():
        gov = card.get("governance_state", "unknown")
        state_counts[gov] = state_counts.get(gov, 0) + 1

    # IBKR paper orders audit
    orders_path = base / "trading_execution_checks" / "ibkr_paper_orders.json"
    orders_data = read_json(orders_path) if orders_path.exists() else {}
    orders = orders_data.get("orders", [])

    return {
        "qc_loop": {
            "ingestion": {
                "last_poll_utc": qc_state.get("last_poll_utc"),
                "total_backtests_processed": qc_state.get("total_processed", 0),
                "projects_monitored": qc_state.get("projects_monitored", 3),
            },
            "iteration": {
                "strategies_iterated": len(iter_summary),
                "total_iterations": sum(iter_summary.values()) if iter_summary else 0,
                "per_strategy": iter_summary,
            },
        },
        "ibkr_loop": {
            "signal_engine": {
                "last_scan_utc": signal_state.get("last_scan_utc"),
                "total_signals": signal_state.get("total_signals", 0),
            },
            "performance_tracker": {
                "last_poll_utc": perf_state.get("last_poll"),
            },
            "paper_orders": {
                "total_orders": len(orders),
                "recent_orders": [
                    {
                        "order_id": o.get("order_id"),
                        "symbol": o.get("symbol"),
                        "action": o.get("action"),
                        "quantity": o.get("quantity"),
                        "status": o.get("status"),
                        "strategy_id": o.get("strategy_id"),
                        "timestamp": o.get("timestamp"),
                    }
                    for o in orders[-10:]
                ],
            },
        },
        "governance": {
            "total_strategies": len(scorecards),
            "state_distribution": state_counts,
        },
    }


@router.get("/closed-loop/strategies")
async def closed_loop_strategies() -> Dict:
    """All strategies with full lifecycle info for the closed-loop dashboard."""
    base = _cfg.BASE_PATH / "tmp_agent" / "state"
    sc_path = base / "strategy_engine" / "strategy_scorecards.json"
    sc_data = read_json(sc_path) if sc_path.exists() else {}
    scorecards = sc_data.get("scorecards", {})

    strategies = []
    for sid, card in scorecards.items():
        strategies.append({
            "id": sid,
            "name": card.get("name", sid),
            "family": card.get("family"),
            "venue": card.get("venue"),
            "governance_state": card.get("governance_state"),
            "win_rate": card.get("win_rate", 0),
            "expectancy": card.get("expectancy", 0),
            "net_pnl": card.get("net_pnl", 0),
            "sharpe_ratio": card.get("sharpe_ratio", 0),
            "max_drawdown": card.get("max_drawdown", 0),
            "profit_factor": card.get("profit_factor", 0),
            "entries_resolved": card.get("entries_resolved", 0),
            "ibkr_net_pnl": card.get("ibkr_net_pnl"),
            "ibkr_unrealized_pnl": card.get("ibkr_unrealized_pnl"),
            "ibkr_contracts_open": card.get("ibkr_contracts_open", 0),
            "promoted_utc": card.get("promoted_utc"),
            "frozen_utc": card.get("frozen_utc"),
            "freeze_reason": card.get("freeze_reason"),
        })

    return {
        "count": len(strategies),
        "strategies": strategies,
        "updated_utc": sc_data.get("updated_utc"),
    }


@router.get("/closed-loop/signals")
async def closed_loop_signals() -> Dict:
    """Recent signal log from IBKR signal engine."""
    base = _cfg.BASE_PATH / "tmp_agent" / "state"
    log_path = base / "ibkr_signals" / "signal_log.json"
    log_data = read_json(log_path) if log_path.exists() else {}
    signals = log_data.get("signals", [])
    return {
        "total": len(signals),
        "recent": signals[-30:],
    }


@router.get("/closed-loop/positions")
async def closed_loop_positions() -> Dict:
    """Current IBKR paper positions and account."""
    base = _cfg.BASE_PATH / "tmp_agent" / "state"
    snap_path = base / "ibkr_performance" / "position_snapshots.json"
    snapshots = read_json(snap_path) if snap_path.exists() else {}
    entries = snapshots.get("snapshots", [])
    latest = entries[-1] if entries else {}
    return {
        "latest_snapshot": latest,
        "history_count": len(entries),
    }


@router.get("/closed-loop/iterations")
async def closed_loop_iterations() -> Dict:
    """QC iteration history for all strategies."""
    base = _cfg.BASE_PATH / "tmp_agent" / "state"
    iter_path = base / "qc_iterations" / "iteration_history.json"
    data = read_json(iter_path) if iter_path.exists() else {}
    iterations = data.get("iterations", {})
    return {
        "strategies_iterated": len(iterations),
        "total_iterations": sum(len(v) for v in iterations.values()),
        "per_strategy": {
            sid: {
                "count": len(iters),
                "last": iters[-1] if iters else None,
            }
            for sid, iters in iterations.items()
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# QC LIVE MONITORING ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

from brain_v9.trading.qc_live_monitor import (
    get_live_state,
    get_all_snapshots,
    get_alerts as get_live_alerts,
    get_brain_actions,
    poll_live_status,
    set_live_deployed,
    set_live_stopped,
    start_monitor,
    stop_monitor,
)


@router.get("/qc-live/status")
async def qc_live_status() -> Dict:
    """Current QC Live deployment status, latest metrics, active alerts."""
    state = get_live_state()
    return {
        "deployed": state.get("deployed", False),
        "deploy_id": state.get("deploy_id", ""),
        "project_id": state.get("project_id", 0),
        "node_id": state.get("node_id", ""),
        "strategy_name": state.get("strategy_name", ""),
        "status": state.get("status", "not_deployed"),
        "launched_utc": state.get("launched_utc", ""),
        "last_poll_utc": state.get("last_poll_utc", ""),
        "poll_count": state.get("poll_count", 0),
        "latest_metrics": state.get("latest_metrics", {}),
        "alerts_active": state.get("alerts_active", []),
        "backtest_reference": state.get("backtest_reference", {}),
    }


@router.get("/qc-live/performance")
async def qc_live_performance(days: int = 1) -> Dict:
    """Historical snapshots for equity curve rendering."""
    snapshots = get_all_snapshots(days=days)
    state = get_live_state()

    # Extract equity curve points for Chart.js
    equity_curve = [
        {"t": s.get("timestamp_utc", ""), "y": s.get("equity")}
        for s in snapshots
        if s.get("equity") is not None
    ]
    drawdown_curve = [
        {"t": s.get("timestamp_utc", ""), "y": s.get("drawdown")}
        for s in snapshots
        if s.get("drawdown") is not None
    ]
    win_rate_curve = [
        {"t": s.get("timestamp_utc", ""), "y": s.get("win_rate")}
        for s in snapshots
        if s.get("win_rate") is not None
    ]

    return {
        "strategy_name": state.get("strategy_name", ""),
        "deployed": state.get("deployed", False),
        "snapshots_count": len(snapshots),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "win_rate_curve": win_rate_curve,
        "latest": snapshots[-1] if snapshots else {},
        "backtest_reference": state.get("backtest_reference", {}),
    }


@router.get("/qc-live/positions")
async def qc_live_positions() -> Dict:
    """Current holdings from QC Live portfolio endpoint (detailed per-symbol)."""
    state = get_live_state()
    if not state.get("deployed"):
        return {"deployed": False, "holdings_count": 0, "holdings": {}}

    qc = _get_qc()
    project_id = state.get("project_id", 29490680)
    portfolio = await qc.read_live_holdings(project_id)

    latest = state.get("latest_metrics", {})
    return {
        "deployed": True,
        "holdings_count": portfolio.get("holdings_count", 0),
        "holdings": portfolio.get("holdings", {}),
        "cash": portfolio.get("cash", {}),
        "equity": latest.get("equity"),
        "unrealized": latest.get("unrealized"),
        "runtime_statistics": latest.get("runtime_statistics", {}),
    }


@router.get("/qc-live/trades")
async def qc_live_trades(limit: int = 50) -> Dict:
    """Recent trade log from QC Live."""
    trade_log_path = _cfg.STATE_PATH / "qc_live" / "trades" / "trade_log.json"
    data = read_json(trade_log_path) if trade_log_path.exists() else {"trades": []}
    trades = data.get("trades", [])
    return {
        "total": len(trades),
        "trades": trades[-limit:],
    }


@router.get("/qc-live/alerts")
async def qc_live_alerts_endpoint(limit: int = 50) -> Dict:
    """Alert history."""
    alerts = get_live_alerts(limit=limit)
    # Separate by severity
    critical = [a for a in alerts if a.get("severity") == "critical"]
    warnings = [a for a in alerts if a.get("severity") == "warn"]
    return {
        "total": len(alerts),
        "critical_count": len(critical),
        "warn_count": len(warnings),
        "alerts": alerts,
    }


@router.get("/qc-live/brain-actions")
async def qc_live_brain_actions(limit: int = 50) -> Dict:
    """Brain auto-adjustment actions log (APLICADO/PENDIENTE/RECHAZADO)."""
    actions = get_brain_actions(limit=limit)
    applied = [a for a in actions if a.get("status") == "APLICADO"]
    pending = [a for a in actions if a.get("status") == "PENDIENTE"]
    rejected = [a for a in actions if a.get("status") == "RECHAZADO"]
    return {
        "total": len(actions),
        "applied_count": len(applied),
        "pending_count": len(pending),
        "rejected_count": len(rejected),
        "actions": actions,
    }


@router.post("/qc-live/refresh")
async def qc_live_refresh(_operator: OperatorAccess) -> Dict:
    """Force an immediate poll of QC Live status (bypass 5-min interval)."""
    state = get_live_state()
    if not state.get("deployed"):
        return {"success": False, "reason": "no_active_deployment"}
    qc = _get_qc()
    result = await poll_live_status(qc)
    return result


@router.post("/qc-live/deploy")
async def qc_live_deploy(
    _operator: OperatorAccess,
    compile_id: str = "",
    node_id: str = "",
    ib_user_name: str = "",
    ib_password: str = "",
    ib_account: str = "DUM891854",
    ib_weekly_restart_utc_time: str = "22:00:00",
    project_id: int = 29490680,
) -> Dict:
    """Deploy V10.13b as QC Live algorithm.

    Requires IBKR credentials. Will fail if already deployed.
    """
    state = get_live_state()
    if state.get("deployed"):
        return {"success": False, "reason": "already_deployed", "deploy_id": state.get("deploy_id")}

    if not compile_id or not node_id:
        return {"success": False, "reason": "missing_compile_id_or_node_id"}

    if not ib_user_name or not ib_password:
        # Try loading from secrets file
        ibkr_secrets_path = _cfg.BASE_PATH / "tmp_agent" / "Secrets" / "ibkr_access.json"
        if ibkr_secrets_path.exists():
            ibkr_creds = read_json(ibkr_secrets_path, {})
            ib_user_name = ib_user_name or ibkr_creds.get("ib_user_name", "")
            ib_password = ib_password or ibkr_creds.get("ib_password", "")
            ib_account = ib_account or ibkr_creds.get("ib_account", "DUM891854")
            ib_weekly_restart_utc_time = ib_weekly_restart_utc_time or ibkr_creds.get("ib_weekly_restart_utc_time", "22:00:00")
        if not ib_user_name or not ib_password:
            return {"success": False, "reason": "missing_ibkr_credentials"}

    qc = _get_qc()
    brokerage = {
        "id": "InteractiveBrokersBrokerage",
        "ib-user-name": ib_user_name,
        "ib-account": ib_account,
        "ib-password": ib_password,
        "ib-weekly-restart-utc-time": ib_weekly_restart_utc_time,
    }

    result = await qc.deploy_live(
        project_id=project_id,
        compile_id=compile_id,
        node_id=node_id,
        brokerage=brokerage,
    )

    if result.get("success"):
        deploy_id = result.get("deploy_id", "")
        set_live_deployed(
            deploy_id=deploy_id,
            project_id=project_id,
            node_id=node_id,
            strategy_name="V10.13b (Determined Sky Blue Galago)",
        )
        # Start monitor background task
        start_monitor(qc)
        return {"success": True, "deploy_id": deploy_id, "status": result.get("status", "")}

    return result


@router.post("/qc-live/register")
async def qc_live_register(
    _operator: OperatorAccess,
    deploy_id: str = "",
    project_id: int = 29490680,
    node_id: str = "LN-64d4787830461ee45574254f643f69b3",
    strategy_name: str = "V10.13b (Determined Sky Blue Galago)",
) -> Dict:
    """Register an externally-created live deployment (e.g. manual web UI deploy).

    Use this when the deploy was done outside Brain (QC web UI) and the
    monitor needs to know about it so it can start polling.
    """
    if not deploy_id:
        return {"success": False, "reason": "deploy_id is required"}

    state = get_live_state()
    if state.get("deployed"):
        return {
            "success": False,
            "reason": "already_deployed",
            "existing_deploy_id": state.get("deploy_id"),
        }

    set_live_deployed(
        deploy_id=deploy_id,
        project_id=project_id,
        node_id=node_id,
        strategy_name=strategy_name,
    )
    # Start monitor if not already running
    qc = _get_qc()
    start_monitor(qc)
    return {"success": True, "deploy_id": deploy_id, "message": "External deploy registered, monitor started"}


@router.post("/qc-live/stop")
async def qc_live_stop(_operator: OperatorAccess) -> Dict:
    """Stop the running QC Live algorithm."""
    state = get_live_state()
    if not state.get("deployed"):
        return {"success": False, "reason": "no_active_deployment"}

    qc = _get_qc()
    result = await qc.stop_live(state["project_id"])

    if result.get("success"):
        set_live_stopped()
        stop_monitor()
        return {"success": True, "message": "QC Live stopped"}

    return result


@router.post("/qc-live/liquidate")
async def qc_live_liquidate(_operator: OperatorAccess) -> Dict:
    """Liquidate all positions and stop the QC Live algorithm."""
    state = get_live_state()
    if not state.get("deployed"):
        return {"success": False, "reason": "no_active_deployment"}

    qc = _get_qc()
    result = await qc.liquidate_live(state["project_id"])

    if result.get("success"):
        set_live_stopped()
        stop_monitor()
        return {"success": True, "message": "QC Live liquidated and stopped"}

    return result
