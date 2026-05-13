"""
Brain V9 - UtilityReader
Lee Utility U desde la SSOT. Solo lectura.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

log = logging.getLogger("UtilityReader")

_STATE = Path(r"C:\AI_VAULT\tmp_agent\state")
_CAP = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")

FILES = {
    "u_latest": _STATE / "utility_u_latest.json",
    "u_gate": _STATE / "utility_u_promotion_gate_latest.json",
    "cycle": _STATE / "next_level_cycle_status_latest.json",
    "roadmap": _STATE / "roadmap.json",
    "capital": _CAP,
}


def read_utility_state() -> Dict:
    out = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "ssot_readonly",
        "u_score": None,
        "verdict": None,
        "blockers": [],
        "current_phase": None,
        "can_promote": False,
        "capital": {},
        "errors": [],
    }
    for key, path in FILES.items():
        if not path.exists():
            out["errors"].append(f"{key}: no encontrado en {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if key == "u_latest":
                out["u_score"] = data.get("u_proxy_score")
                out["verdict"] = data.get("verdict") or data.get("promotion_gate", {}).get("verdict")
                out["blockers"] = data.get("promotion_gate", {}).get("blockers", [])
            elif key == "u_gate":
                out["can_promote"] = (
                    data.get("verdict") == "promote"
                    and float(data.get("u_proxy_score", -999)) > 0
                )
            elif key == "cycle":
                out["current_phase"] = data.get("current_phase")
            elif key == "capital":
                out["capital"] = {
                    "cash": data.get("current_cash"),
                    "committed": data.get("committed_cash"),
                    "drawdown_max": data.get("max_drawdown_pct"),
                    "status": data.get("status"),
                    "mode": "paper_demo",
                }
        except Exception as e:
            out["errors"].append(f"{key}: {e}")
            log.warning("Error leyendo %s: %s", key, e)
    return out


def is_promotion_safe() -> Tuple[bool, str]:
    state = read_utility_state()
    if state["u_score"] is None:
        return False, "No se pudo leer U score"
    if float(state["u_score"]) <= 0:
        return False, f"U score no positivo: {state['u_score']}"
    if state["verdict"] != "promote":
        return False, f"Verdict no es promote: {state['verdict']}"
    if state["blockers"]:
        return False, f"Blockers activos: {state['blockers']}"
    road = {}
    cyc = {}
    try:
        road = json.loads(FILES["roadmap"].read_text(encoding="utf-8"))
        cyc = json.loads(FILES["cycle"].read_text(encoding="utf-8"))
    except Exception:
        pass
    if road.get("current_phase") != cyc.get("current_phase"):
        return False, f"SSOT inconsistente: roadmap={road.get('current_phase')} cycle={cyc.get('current_phase')}"
    return True, "Todos los gates pasan"
