"""
Brain Chat V9 — trading/qc_live_monitor.py
QC Live Algorithm Monitor — polls QC API every 5 minutes, stores snapshots,
compares live vs backtest expectations, and detects anomalies.

This is the BACKEND ONLY — no LLM calls, no auto-adjustment.
The analyzer (qc_live_analyzer.py) reads snapshots and makes decisions.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from brain_v9.core.state_io import read_json, write_json
import brain_v9.config as _cfg

log = logging.getLogger("qc_live_monitor")

# ── Paths ────────────────────────────────────────────────────────────────────
QC_LIVE_STATE_DIR = _cfg.STATE_PATH / "qc_live"
SNAPSHOTS_DIR = QC_LIVE_STATE_DIR / "snapshots"
TRADES_DIR = QC_LIVE_STATE_DIR / "trades"
ALERTS_DIR = QC_LIVE_STATE_DIR / "alerts"
ANALYSIS_DIR = QC_LIVE_STATE_DIR / "analysis"

# Main state file — tracks current deployment info and latest metrics
LIVE_STATE_PATH = QC_LIVE_STATE_DIR / "live_state.json"
# Cumulative trade log
TRADE_LOG_PATH = TRADES_DIR / "trade_log.json"
# Alert log
ALERT_LOG_PATH = ALERTS_DIR / "alert_log.json"
# Brain actions log (auto-adjustments documented for César)
BRAIN_ACTIONS_PATH = QC_LIVE_STATE_DIR / "brain_actions_log.json"

# ── Backtest reference metrics (V10.13b champion) ───────────────────────────
# These are the "expected" metrics from the champion backtest.
# Used for live-vs-backtest comparison and degradation detection.
BACKTEST_REFERENCE = {
    "strategy_id": "V10.13b",
    "strategy_name": "Determined Sky Blue Galago",
    "backtest_id": "d3e0b637785c228df84420acccae54ac",
    "project_id": 29490680,
    "sharpe_ratio": 0.899,
    "cagr": 0.265,           # 26.5%
    "max_drawdown": 0.166,    # 16.6%
    "win_rate": 0.69,         # 69%
    "expectancy": 0.886,
    "profit_factor": 2.90,
    "total_trades": 153,
    "capital": 10000,
}

# ── Polling config ───────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 300  # 5 minutes
MAX_SNAPSHOTS_KEPT = 2000    # ~7 days at 5-min intervals

# ── Alert thresholds ─────────────────────────────────────────────────────────
ALERT_THRESHOLDS = {
    # Drawdown: warn at 80% of backtest max DD, critical at 100%
    "drawdown_warn_pct": 0.80,
    "drawdown_critical_pct": 1.00,
    # Win rate: warn if live WR drops 15% below backtest, critical at 25% below
    "win_rate_warn_delta": 0.15,
    "win_rate_critical_delta": 0.25,
    # Equity divergence: warn if live equity diverges > 5% from backtest trajectory
    "equity_divergence_warn_pct": 0.05,
    "equity_divergence_critical_pct": 0.10,
    # Consecutive losses
    "consecutive_losses_warn": 5,
    "consecutive_losses_critical": 8,
}


def _ensure_dirs():
    """Create state directories if they don't exist."""
    for d in [QC_LIVE_STATE_DIR, SNAPSHOTS_DIR, TRADES_DIR, ALERTS_DIR, ANALYSIS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_pct(val: str) -> Optional[float]:
    """Parse a percentage string like '26.5%' to 0.265."""
    if not val:
        return None
    try:
        return float(val.replace("%", "").replace(",", "").strip()) / 100
    except (ValueError, TypeError):
        return None


def _parse_currency(val: str) -> Optional[float]:
    """Parse a currency string like '$12,345.67' to float."""
    if not val:
        return None
    try:
        return float(val.replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def get_live_state() -> Dict:
    """Read current QC Live deployment state."""
    _ensure_dirs()
    return read_json(LIVE_STATE_PATH, {
        "deployed": False,
        "deploy_id": "",
        "project_id": 0,
        "node_id": "",
        "strategy_name": "",
        "launched_utc": "",
        "last_poll_utc": "",
        "poll_count": 0,
        "status": "not_deployed",
        "latest_metrics": {},
        "alerts_active": [],
    })


def set_live_deployed(
    deploy_id: str,
    project_id: int,
    node_id: str,
    strategy_name: str = "V10.13b",
) -> Dict:
    """Record a new live deployment."""
    _ensure_dirs()
    state = {
        "deployed": True,
        "deploy_id": deploy_id,
        "project_id": project_id,
        "node_id": node_id,
        "strategy_name": strategy_name,
        "launched_utc": _now_utc(),
        "last_poll_utc": "",
        "poll_count": 0,
        "status": "deploying",
        "latest_metrics": {},
        "alerts_active": [],
        "backtest_reference": BACKTEST_REFERENCE,
    }
    write_json(LIVE_STATE_PATH, state)
    log.info("QC Live deployment recorded: deploy_id=%s project=%s", deploy_id, project_id)
    return state


def set_live_stopped():
    """Mark deployment as stopped."""
    state = get_live_state()
    state["deployed"] = False
    state["status"] = "stopped"
    state["stopped_utc"] = _now_utc()
    write_json(LIVE_STATE_PATH, state)
    log.info("QC Live deployment marked stopped")


async def poll_live_status(qc_connector) -> Dict:
    """Poll QC API for live algorithm status. Store snapshot.

    Parameters
    ----------
    qc_connector : QuantConnectConnector
        Authenticated connector instance.

    Returns
    -------
    dict
        The snapshot with metrics, alerts, and comparison data.
    """
    _ensure_dirs()
    state = get_live_state()
    if not state.get("deployed") or not state.get("deploy_id"):
        return {"success": False, "reason": "no_active_deployment"}

    deploy_id = state["deploy_id"]
    project_id = state["project_id"]

    # Poll QC — main status + detailed holdings
    live_data = await qc_connector.read_live(project_id, deploy_id)
    if not live_data.get("success"):
        _record_alert("poll_failed", f"QC API returned error: {live_data.get('error', live_data.get('errors', ''))}")
        return {"success": False, "reason": "qc_api_error", "detail": live_data}

    # Also fetch detailed holdings from /live/portfolio/read
    holdings_data = {}
    try:
        portfolio_resp = await qc_connector.read_live_holdings(project_id)
        if portfolio_resp.get("success"):
            holdings_data = portfolio_resp.get("holdings", {})
    except Exception as exc:
        log.warning("Failed to fetch detailed holdings: %s", exc)

    # Build snapshot
    metrics = live_data.get("metrics", {})
    runtime = live_data.get("runtime_statistics", {})
    snapshot = {
        "timestamp_utc": _now_utc(),
        "deploy_id": deploy_id,
        "state": live_data.get("state", ""),
        "equity": _parse_currency(metrics.get("equity", "")),
        "net_profit": _parse_currency(metrics.get("net_profit", "")),
        "return_pct": _parse_pct(metrics.get("return_pct", "")),
        "unrealized": _parse_currency(metrics.get("unrealized", "")),
        "holdings_value": _parse_currency(metrics.get("holdings_value", "")),
        "sharpe_ratio": _parse_pct(metrics.get("sharpe_ratio", "")),
        "drawdown": _parse_pct(metrics.get("drawdown", "")),
        "win_rate": _parse_pct(metrics.get("win_rate", "")),
        "total_orders": metrics.get("total_orders", ""),
        "holdings_count": len(holdings_data) if holdings_data else live_data.get("holdings_count", 0),
        "holdings": holdings_data,
        "runtime_statistics": runtime,
        "equity_curve_points": len(live_data.get("equity_curve", [])),
    }

    # Store snapshot
    _store_snapshot(snapshot)

    # Compare with backtest reference
    comparison = _compare_with_backtest(snapshot)
    snapshot["backtest_comparison"] = comparison

    # Check for alerts
    alerts = _check_alerts(snapshot, comparison)
    snapshot["new_alerts"] = alerts

    # Update state
    state["last_poll_utc"] = _now_utc()
    state["poll_count"] = state.get("poll_count", 0) + 1
    state["status"] = live_data.get("state", state.get("status", "unknown"))
    state["latest_metrics"] = snapshot
    state["alerts_active"] = alerts
    write_json(LIVE_STATE_PATH, state)

    log.info(
        "QC Live poll #%d: state=%s equity=%s return=%s DD=%s",
        state["poll_count"],
        snapshot["state"],
        snapshot.get("equity"),
        snapshot.get("return_pct"),
        snapshot.get("drawdown"),
    )
    return {"success": True, "snapshot": snapshot}


def _store_snapshot(snapshot: Dict):
    """Append snapshot to daily file + maintain rolling window."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_path = SNAPSHOTS_DIR / f"snapshots_{today}.json"
    data = read_json(daily_path, {"date": today, "snapshots": []})
    data["snapshots"].append(snapshot)

    # Trim if too many in one day
    if len(data["snapshots"]) > MAX_SNAPSHOTS_KEPT:
        data["snapshots"] = data["snapshots"][-MAX_SNAPSHOTS_KEPT:]

    write_json(daily_path, data)


def _compare_with_backtest(snapshot: Dict) -> Dict:
    """Compare live metrics against backtest reference."""
    ref = BACKTEST_REFERENCE
    comparison = {"reference": ref}

    # Drawdown comparison
    live_dd = snapshot.get("drawdown")
    if live_dd is not None:
        dd_ratio = abs(live_dd) / ref["max_drawdown"] if ref["max_drawdown"] else 0
        comparison["drawdown"] = {
            "live": live_dd,
            "backtest": ref["max_drawdown"],
            "ratio": round(dd_ratio, 3),
            "status": "ok" if dd_ratio < 0.8 else ("warn" if dd_ratio < 1.0 else "critical"),
        }

    # Win rate comparison
    live_wr = snapshot.get("win_rate")
    if live_wr is not None:
        wr_delta = ref["win_rate"] - live_wr
        comparison["win_rate"] = {
            "live": live_wr,
            "backtest": ref["win_rate"],
            "delta": round(wr_delta, 3),
            "status": "ok" if wr_delta < 0.15 else ("warn" if wr_delta < 0.25 else "critical"),
        }

    # Return comparison
    live_return = snapshot.get("return_pct")
    if live_return is not None:
        comparison["return"] = {
            "live": live_return,
            "backtest_cagr": ref["cagr"],
        }

    # Sharpe comparison
    live_sharpe = snapshot.get("sharpe_ratio")
    if live_sharpe is not None:
        sharpe_ratio = live_sharpe / ref["sharpe_ratio"] if ref["sharpe_ratio"] else 0
        comparison["sharpe"] = {
            "live": live_sharpe,
            "backtest": ref["sharpe_ratio"],
            "ratio": round(sharpe_ratio, 3),
            "status": "ok" if sharpe_ratio > 0.7 else ("warn" if sharpe_ratio > 0.5 else "critical"),
        }

    return comparison


def _check_alerts(snapshot: Dict, comparison: Dict) -> list:
    """Check snapshot against thresholds and return list of active alerts."""
    alerts = []
    thresholds = ALERT_THRESHOLDS

    # Drawdown alerts
    dd_comp = comparison.get("drawdown", {})
    if dd_comp.get("status") == "critical":
        alerts.append(_create_alert(
            "drawdown_critical",
            f"Drawdown {dd_comp.get('live', 0):.1%} exceeds backtest max {dd_comp.get('backtest', 0):.1%}",
            severity="critical",
        ))
    elif dd_comp.get("status") == "warn":
        alerts.append(_create_alert(
            "drawdown_warn",
            f"Drawdown {dd_comp.get('live', 0):.1%} approaching backtest max {dd_comp.get('backtest', 0):.1%}",
            severity="warn",
        ))

    # Win rate alerts
    wr_comp = comparison.get("win_rate", {})
    if wr_comp.get("status") == "critical":
        alerts.append(_create_alert(
            "win_rate_critical",
            f"Win rate {wr_comp.get('live', 0):.1%} is {wr_comp.get('delta', 0):.1%} below backtest {wr_comp.get('backtest', 0):.1%}",
            severity="critical",
        ))
    elif wr_comp.get("status") == "warn":
        alerts.append(_create_alert(
            "win_rate_warn",
            f"Win rate {wr_comp.get('live', 0):.1%} below backtest {wr_comp.get('backtest', 0):.1%}",
            severity="warn",
        ))

    # Sharpe alerts
    sharpe_comp = comparison.get("sharpe", {})
    if sharpe_comp.get("status") == "critical":
        alerts.append(_create_alert(
            "sharpe_degraded",
            f"Sharpe {sharpe_comp.get('live', 0):.3f} is <50% of backtest {sharpe_comp.get('backtest', 0):.3f}",
            severity="critical",
        ))
    elif sharpe_comp.get("status") == "warn":
        alerts.append(_create_alert(
            "sharpe_warn",
            f"Sharpe {sharpe_comp.get('live', 0):.3f} is <70% of backtest {sharpe_comp.get('backtest', 0):.3f}",
            severity="warn",
        ))

    # Algorithm state alert
    algo_state = snapshot.get("state", "")
    if algo_state and algo_state.lower() in ("runtimeerror", "stopped", "liquidated"):
        alerts.append(_create_alert(
            "algo_state_abnormal",
            f"Algorithm state is '{algo_state}' — needs immediate attention",
            severity="critical",
        ))

    # Record all alerts
    for alert in alerts:
        _record_alert(alert["type"], alert["message"], alert["severity"])

    return alerts


def _create_alert(alert_type: str, message: str, severity: str = "warn") -> Dict:
    return {
        "type": alert_type,
        "message": message,
        "severity": severity,
        "timestamp_utc": _now_utc(),
    }


def _record_alert(alert_type: str, message: str, severity: str = "warn"):
    """Persist alert to alert log."""
    _ensure_dirs()
    log_data = read_json(ALERT_LOG_PATH, {"alerts": []})
    log_data["alerts"].append({
        "type": alert_type,
        "message": message,
        "severity": severity,
        "timestamp_utc": _now_utc(),
    })
    # Keep last 500 alerts
    if len(log_data["alerts"]) > 500:
        log_data["alerts"] = log_data["alerts"][-500:]
    write_json(ALERT_LOG_PATH, log_data)


def get_all_snapshots(days: int = 1) -> list:
    """Read snapshots from the last N days."""
    _ensure_dirs()
    all_snapshots = []
    from datetime import timedelta
    for i in range(days):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        path = SNAPSHOTS_DIR / f"snapshots_{date}.json"
        if path.exists():
            data = read_json(path, {"snapshots": []})
            all_snapshots.extend(data.get("snapshots", []))
    return sorted(all_snapshots, key=lambda s: s.get("timestamp_utc", ""))


def get_alerts(limit: int = 50) -> list:
    """Read recent alerts."""
    _ensure_dirs()
    data = read_json(ALERT_LOG_PATH, {"alerts": []})
    return data.get("alerts", [])[-limit:]


def get_brain_actions(limit: int = 50) -> list:
    """Read brain auto-adjustment actions log."""
    _ensure_dirs()
    data = read_json(BRAIN_ACTIONS_PATH, {"actions": []})
    return data.get("actions", [])[-limit:]


def record_brain_action(
    action_type: str,
    description: str,
    evidence: str,
    change_detail: Dict,
    status: str = "APLICADO",
) -> Dict:
    """Record a Brain auto-adjustment action with full documentation.

    Parameters
    ----------
    action_type : str
        E.g. "sizing_reduction", "threshold_adjustment".
    description : str
        Human-readable description of what was changed.
    evidence : str
        The data/metrics that justified the change.
    change_detail : dict
        Before/after values.
    status : str
        "APLICADO", "PENDIENTE", "RECHAZADO".
    """
    _ensure_dirs()
    action = {
        "id": f"BA-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "timestamp_utc": _now_utc(),
        "action_type": action_type,
        "description": description,
        "evidence": evidence,
        "change_detail": change_detail,
        "status": status,
    }
    data = read_json(BRAIN_ACTIONS_PATH, {"actions": []})
    data["actions"].append(action)
    if len(data["actions"]) > 200:
        data["actions"] = data["actions"][-200:]
    write_json(BRAIN_ACTIONS_PATH, data)
    log.info("Brain action recorded: [%s] %s — %s", status, action_type, description)
    return action


# ── Background polling task ──────────────────────────────────────────────────

_poll_task: Optional[asyncio.Task] = None


async def _poll_loop(qc_connector):
    """Background loop: poll QC Live every POLL_INTERVAL_SECONDS."""
    log.info("QC Live monitor started (interval=%ds)", POLL_INTERVAL_SECONDS)
    while True:
        try:
            state = get_live_state()
            if state.get("deployed"):
                await poll_live_status(qc_connector)
            else:
                log.debug("QC Live monitor: no active deployment, skipping poll")
        except Exception as exc:
            log.error("QC Live poll error: %s", exc, exc_info=True)
            _record_alert("poll_exception", str(exc), severity="warn")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_monitor(qc_connector):
    """Start background polling task (call once from FastAPI startup)."""
    global _poll_task
    if _poll_task is not None and not _poll_task.done():
        log.warning("QC Live monitor already running, not starting duplicate")
        return
    _poll_task = asyncio.create_task(_poll_loop(qc_connector))
    log.info("QC Live monitor background task created")


def stop_monitor():
    """Cancel background polling task."""
    global _poll_task
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
        log.info("QC Live monitor stopped")
    _poll_task = None
