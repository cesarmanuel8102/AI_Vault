"""
Brain V9 — Canonical Financial Risk Contract Status
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.brain.control_layer import freeze_control_layer, get_control_layer_status_latest
from brain_v9.config import BASE_PATH, PAPER_ONLY
from brain_v9.core.state_io import read_json, write_json


STATE_PATH = BASE_PATH / "tmp_agent" / "state"
RISK_STATE_DIR = STATE_PATH / "risk"
RISK_STATE_DIR.mkdir(parents=True, exist_ok=True)
RISK_STATUS_PATH = RISK_STATE_DIR / "risk_contract_status_latest.json"
LEDGER_PATH = STATE_PATH / "strategy_engine" / "signal_paper_execution_ledger.json"
CAPITAL_PATH = BASE_PATH / "60_METRICS" / "capital_state.json"
BRIDGE_PATH = STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json"
MISSION_PATH = STATE_PATH / "financial_mission.json"
UTILITY_PATH = STATE_PATH / "utility_u_latest.json"
CONTRACT_PATH = BASE_PATH / "workspace" / "brainlab" / "brainlab" / "contracts" / "financial_motor_contract_v1.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolved_entries() -> List[Dict[str, Any]]:
    payload = read_json(LEDGER_PATH, {"entries": []})
    items = payload.get("entries", []) if isinstance(payload, dict) else []
    resolved: List[Dict[str, Any]] = []
    for entry in items if isinstance(items, list) else []:
        if bool(entry.get("resolved")) or str(entry.get("result") or "").lower() in {"win", "loss", "draw"}:
            resolved.append(entry)
    return resolved


def _base_capital(capital: Dict[str, Any]) -> float:
    starting = _safe_float(capital.get("starting_capital"), 0.0)
    current = _safe_float(capital.get("current_cash"), 0.0)
    committed = _safe_float(capital.get("committed_cash"), 0.0)
    # P-OP3b: Incorporate live PO demo balance from bridge data.
    # capital_state.json was stale (last updated 2026-02-20) and showed $550
    # while the actual PO demo balance is ~$1984.
    bridge = read_json(BRIDGE_PATH, {})
    dom = bridge.get("dom") or bridge  # bridge may be flat or nested
    demo_balance = _safe_float(dom.get("balance_demo"), 0.0)
    return max(starting, current + committed, demo_balance, 1.0)


def _today_realized_pnl(entries: List[Dict[str, Any]], now_utc: datetime) -> float:
    # P-OP3a: Use UTC calendar-day start, not rolling 24h window.
    # The rolling window incorrectly counted yesterday's trades as "today".
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    pnl = 0.0
    for entry in entries:
        resolved_utc = _parse_utc(entry.get("resolved_utc") or entry.get("timestamp"))
        if resolved_utc is None or resolved_utc < start:
            continue
        pnl += _safe_float(entry.get("profit"), 0.0)
    return round(pnl, 4)


def _weekly_drawdown_frac(entries: List[Dict[str, Any]], now_utc: datetime, base_capital: float) -> float:
    start = now_utc - timedelta(days=7)
    weekly = []
    for entry in entries:
        resolved_utc = _parse_utc(entry.get("resolved_utc") or entry.get("timestamp"))
        if resolved_utc is None or resolved_utc < start:
            continue
        weekly.append((resolved_utc, _safe_float(entry.get("profit"), 0.0)))
    weekly.sort(key=lambda item: item[0])
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for _, profit in weekly:
        equity += profit
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return round(max_drawdown / max(base_capital, 1.0), 6)


def build_risk_contract_status(refresh: bool = True) -> Dict[str, Any]:
    contract = read_json(CONTRACT_PATH, {})
    capital = read_json(CAPITAL_PATH, {})
    mission = read_json(MISSION_PATH, {})
    utility = read_json(UTILITY_PATH, {})
    control = get_control_layer_status_latest()
    entries = _resolved_entries()
    now_utc = datetime.now(timezone.utc)

    limits = (((contract.get("risk") or {}).get("limits") or {}) if isinstance(contract, dict) else {}) or {}
    max_daily_loss_frac = _safe_float(limits.get("max_daily_loss_frac"), 0.02)
    max_weekly_drawdown_frac = _safe_float(limits.get("max_weekly_drawdown_frac"), 0.06)
    max_total_exposure_frac = _safe_float(limits.get("max_total_exposure_frac"), 0.70)

    # P-OP3d: In paper_only mode, apply relaxed limits to allow probation
    # testing and data collection.  The contract limits are for live trading;
    # paper-only mode needs wider room because strategies in probation are
    # expected to lose while the system gathers sample data.
    # Live limits remain untouched in the contract JSON.
    if PAPER_ONLY:
        max_daily_loss_frac = max(max_daily_loss_frac, 0.15)       # 15% daily cap
        max_weekly_drawdown_frac = max(max_weekly_drawdown_frac, 0.50)  # 50% weekly cap
    contract_kill_switch = _safe_bool(limits.get("kill_switch"))
    paper_only_required = bool((mission.get("guardrails") or {}).get("require_validation_before_scaling", True))

    current_cash = _safe_float(capital.get("current_cash"), 0.0)
    committed_cash = _safe_float(capital.get("committed_cash"), 0.0)
    total_capital = max(current_cash + committed_cash, 1.0)
    base_capital = _base_capital(capital)
    daily_realized_pnl = _today_realized_pnl(entries, now_utc)
    daily_loss_frac = round(max(0.0, -daily_realized_pnl) / max(base_capital, 1.0), 6)
    weekly_drawdown_frac = _weekly_drawdown_frac(entries, now_utc, base_capital)
    exposure_frac = round(committed_cash / total_capital, 6)

    soft_limit_drawdown = round(max_weekly_drawdown_frac * 0.80, 6)
    warnings: List[str] = []
    hard_violations: List[str] = []

    if contract_kill_switch:
        hard_violations.append("contract_kill_switch_active")
    if not PAPER_ONLY:
        hard_violations.append("paper_only_contract_breached")
    if daily_loss_frac > max_daily_loss_frac:
        hard_violations.append("max_daily_loss_exceeded")
    if weekly_drawdown_frac > max_weekly_drawdown_frac:
        hard_violations.append("max_weekly_drawdown_exceeded")
    elif weekly_drawdown_frac >= soft_limit_drawdown:
        warnings.append("weekly_drawdown_near_limit")
    if exposure_frac > max_total_exposure_frac:
        hard_violations.append("max_total_exposure_exceeded")
    elif exposure_frac >= round(max_total_exposure_frac * 0.80, 6):
        warnings.append("total_exposure_near_limit")
    if str(control.get("mode") or "") == "FROZEN":
        hard_violations.append("control_layer_frozen")

    execution_allowed = len(hard_violations) == 0
    status = "healthy" if execution_allowed and not warnings else "degraded" if execution_allowed else "critical"

    payload = {
        "schema_version": "financial_risk_contract_status_v1",
        "generated_utc": _utc_now(),
        "contract_path": str(CONTRACT_PATH),
        "status": status,
        "execution_allowed": execution_allowed,
        "paper_only": bool(PAPER_ONLY),
        "paper_only_required": paper_only_required,
        "hard_violations": hard_violations,
        "warnings": warnings,
        "limits": {
            "max_daily_loss_frac": max_daily_loss_frac,
            "max_weekly_drawdown_frac": max_weekly_drawdown_frac,
            "max_total_exposure_frac": max_total_exposure_frac,
            "kill_switch": contract_kill_switch,
        },
        "measures": {
            "base_capital": round(base_capital, 4),
            "current_cash": round(current_cash, 4),
            "committed_cash": round(committed_cash, 4),
            "total_capital": round(total_capital, 4),
            "daily_realized_pnl": daily_realized_pnl,
            "daily_loss_frac": daily_loss_frac,
            "weekly_drawdown_frac": weekly_drawdown_frac,
            "total_exposure_frac": exposure_frac,
            "resolved_trades_count": len(entries),
        },
        "control_layer": {
            "mode": control.get("mode"),
            "reason": control.get("reason"),
        },
        "utility": {
            "u_score": utility.get("u_score", utility.get("u_proxy_score")),
            "verdict": utility.get("verdict"),
            "blockers": utility.get("blockers", []),
        },
    }
    write_json(RISK_STATUS_PATH, payload)
    return payload


def read_risk_contract_status() -> Dict[str, Any]:
    payload = read_json(RISK_STATUS_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_risk_contract_status(refresh=True)


def enforce_risk_contract_for_execution(source: str = "strategy_execution") -> Dict[str, Any]:
    status = build_risk_contract_status(refresh=True)
    if status.get("execution_allowed"):
        # P-OP29d: Auto-unfreeze when the risk violation clears, but ONLY if
        # the freeze was caused by a risk_contract_violation (not a manual
        # user freeze or critical_recent_change_failures).
        control = get_control_layer_status_latest()
        if (str(control.get("mode") or "") == "FROZEN"
                and str(control.get("reason") or "").startswith("risk_contract_violation")):
            from brain_v9.brain.control_layer import unfreeze_control_layer
            unfreeze_control_layer(
                reason="risk_contract_cleared_auto_unfreeze",
                source=source,
            )
        return status

    auto_on_violation = _safe_bool((((read_json(CONTRACT_PATH, {}).get("risk") or {}).get("kill_switch_policy") or {}).get("auto_on_violation")))
    if auto_on_violation and str(status.get("control_layer", {}).get("mode") or "") != "FROZEN":
        control = freeze_control_layer(
            reason=f"risk_contract_violation:{','.join(status.get('hard_violations', []))}",
            source=source,
        )
        status["control_layer"] = {
            "mode": control.get("mode"),
            "reason": control.get("reason"),
        }
        status["kill_switch_activated"] = True
    else:
        status["kill_switch_activated"] = False
    write_json(RISK_STATUS_PATH, status)
    return status
