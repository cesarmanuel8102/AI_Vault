from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(p: Path, default: Any) -> Any:
    try:
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_contract(contract_path: str) -> Dict[str, Any]:
    cp = Path(contract_path).resolve()
    data = _read_json(cp, {})
    if not isinstance(data, dict) or not data:
        raise ValueError(f"CONTRACT_INVALID_OR_EMPTY: {cp}")
    return data


def extract_limits(contract: Dict[str, Any]) -> Dict[str, Any]:
    limits = (((contract.get("risk") or {}).get("limits")) or {})
    # Normalize keys
    return {
        "max_daily_loss_frac": float(limits.get("max_daily_loss_frac", 0.0) or 0.0),
        "max_weekly_drawdown_frac": float(limits.get("max_weekly_drawdown_frac", 0.0) or 0.0),
        "max_total_exposure_frac": float(limits.get("max_total_exposure_frac", 0.0) or 0.0),
        "kill_switch": bool(limits.get("kill_switch", False)),
    }


def extract_kill_policy(contract: Dict[str, Any]) -> Dict[str, Any]:
    pol = ((contract.get("risk") or {}).get("kill_switch_policy")) or {}
    return {
        "auto_on_violation": bool(pol.get("auto_on_violation", False)),
        "manual_override_required": bool(pol.get("manual_override_required", True)),
    }


def assess_snapshot(snapshot: Dict[str, Any], limits: Dict[str, Any]) -> Dict[str, Any]:
    nlv = float(snapshot.get("nlv", 0.0) or 0.0)
    daily_pnl = float(snapshot.get("daily_pnl", 0.0) or 0.0)
    weekly_dd = float(snapshot.get("weekly_drawdown", 0.0) or 0.0)
    exposure = float(snapshot.get("total_exposure", 0.0) or 0.0)

    daily_loss_frac = 0.0
    if nlv > 0 and daily_pnl < 0:
        daily_loss_frac = abs(daily_pnl) / nlv

    violations: List[Dict[str, Any]] = []
    if daily_loss_frac > float(limits.get("max_daily_loss_frac", 0.0) or 0.0):
        violations.append({"type": "MaxDailyLoss", "value": daily_loss_frac, "limit": limits["max_daily_loss_frac"]})
    if weekly_dd > float(limits.get("max_weekly_drawdown_frac", 0.0) or 0.0):
        violations.append({"type": "MaxWeeklyDrawdown", "value": weekly_dd, "limit": limits["max_weekly_drawdown_frac"]})
    if exposure > float(limits.get("max_total_exposure_frac", 0.0) or 0.0):
        violations.append({"type": "MaxTotalExposure", "value": exposure, "limit": limits["max_total_exposure_frac"]})

    verdict = "continue" if not violations else "halt"
    return {
        "verdict": verdict,
        "reason": "OK" if verdict == "continue" else "RISK_LIMIT_VIOLATION",
        "metrics": {
            "nlv": nlv,
            "daily_pnl": daily_pnl,
            "daily_loss_frac": daily_loss_frac,
            "weekly_drawdown": weekly_dd,
            "total_exposure": exposure,
        },
        "violations": violations,
    }


def load_risk_state(risk_state_path: Path) -> Dict[str, Any]:
    st = _read_json(risk_state_path, {})
    if not isinstance(st, dict):
        st = {}
    return st


def persist_assess(
    room_id: str,
    contract_path: str,
    snapshot: Dict[str, Any],
    risk_state_path: Path,
) -> Dict[str, Any]:
    contract = load_contract(contract_path)
    limits = extract_limits(contract)
    kill_pol = extract_kill_policy(contract)

    state = load_risk_state(risk_state_path)

    # effective kill switch = contract.kill_switch OR state.kill_switch (latched)
    latched = bool(state.get("kill_switch", False))
    effective_kill = bool(limits.get("kill_switch", False)) or latched

    assess = assess_snapshot(snapshot, limits)

    # If kill already active -> force halt
    if effective_kill:
        assess = {
            **assess,
            "verdict": "halt",
            "reason": "KILL_SWITCH",
        }

    # Auto-latch kill switch on violation (if configured)
    auto_on_violation = bool(kill_pol.get("auto_on_violation", False))
    manual_override_required = bool(kill_pol.get("manual_override_required", True))
    if (assess.get("verdict") == "halt") and auto_on_violation:
        state["kill_switch"] = True
        state["kill_switch_reason"] = assess.get("reason")
        state["kill_switch_latched_utc"] = utc_iso()

    # Save state
    vio_types = []
    for v in (assess.get("violations") or []):
        t = v.get("type")
        if t and t not in vio_types:
            vio_types.append(t)

    state["room_id"] = room_id
    state["contract_path"] = contract_path
    state["last_assess_utc"] = utc_iso()
    state["last_assess"] = assess
    state["last_violation_types"] = vio_types
    state["kill_switch_policy"] = kill_pol

    _write_json(risk_state_path, state)

    # Response (compact + useful)
    return {
        "ok": True,
        "room_id": room_id,
        "contract_id": contract.get("contract_id"),
        "contract_path": contract_path,
        "limits": limits,
        "kill_switch_policy": kill_pol,
        "risk_state_path": str(risk_state_path),
        "kill_switch_latched": bool(state.get("kill_switch", False)),
        "assess": assess,
    }


def reset_kill_switch(risk_state_path: Path, note: Optional[str] = None) -> Dict[str, Any]:
    state = load_risk_state(risk_state_path)
    state["kill_switch"] = False
    state["kill_switch_reason"] = None
    state["kill_switch_reset_utc"] = utc_iso()
    if note:
        state["kill_switch_reset_note"] = str(note)[:2000]
    _write_json(risk_state_path, state)
    return {"ok": True, "risk_state_path": str(risk_state_path), "kill_switch": False, "ts": utc_iso()}
