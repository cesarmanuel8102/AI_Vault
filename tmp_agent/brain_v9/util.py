"""
Brain V9 — util.py
Funciones de utilidad general para el sistema Brain V9.

This module is the SINGLE SOURCE OF TRUTH for skip counting.
The scorecard's ``valid_candidates_skipped`` is kept in sync via
``_sync_skip_counter_to_scorecard()``.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

log = logging.getLogger("util")

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import BRAIN_V9_PATH
from brain_v9.core.state_io import read_json, write_json

# Estado global para skip counter (en memoria + persistencia)
_skips_state: Dict[str, Any] = {
    "consecutive_skips": 0,
    "last_skip_timestamp": None,
    "skip_history": []
}

def _get_skips_file() -> Path:
    """Retorna la ruta del archivo de estado de skips."""
    return BRAIN_V9_PATH / "state" / "autonomy_skip_state.json"

def _load_skips_state() -> Dict[str, Any]:
    """Carga el estado de skips desde disco."""
    global _skips_state
    skips_file = _get_skips_file()
    try:
        loaded = read_json(skips_file, {})
        if loaded:
            _skips_state.update(loaded)
    except Exception as exc:
        log.debug("Failed to load skips state from %s: %s", skips_file, exc)
    return _skips_state

def _save_skips_state() -> None:
    """Guarda el estado de skips en disco."""
    skips_file = _get_skips_file()
    try:
        skips_file.parent.mkdir(parents=True, exist_ok=True)
        write_json(skips_file, _skips_state)
    except Exception as exc:
        log.debug("Failed to save skips state to %s: %s", skips_file, exc)


def _sync_skip_counter_to_scorecard() -> None:
    """Sync the authoritative skip count into the scorecard's seed_metrics.

    This keeps ``valid_candidates_skipped`` in the scorecard aligned with
    ``consecutive_skips`` in util.py, so the blocker check in
    ``utility.py`` always sees the correct value.
    """
    try:
        from brain_v9.core.state_io import read_json, write_json
        scorecard_path = BRAIN_V9_PATH / "state" / "rooms" / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json"
        if not scorecard_path.exists():
            return
        scorecard = read_json(scorecard_path, {})
        seed = scorecard.setdefault("seed_metrics", {})
        seed["valid_candidates_skipped"] = _skips_state.get("consecutive_skips", 0)
        write_json(scorecard_path, scorecard)
    except Exception as exc:
        log.debug("Scorecard sync failed (non-fatal): %s", exc)


def get_consecutive_skips() -> int:
    """
    Obtiene el número de skips consecutivos actuales.
    
    Returns:
        int: Número de skips consecutivos
    """
    _load_skips_state()
    return _skips_state.get("consecutive_skips", 0)

def increment_skips_counter(reason: str = "No execution") -> int:
    """
    Incrementa el contador de skips consecutivos.
    
    Args:
        reason: Razón del skip
        
    Returns:
        int: Nuevo valor del contador
    """
    global _skips_state
    _load_skips_state()
    
    _skips_state["consecutive_skips"] = _skips_state.get("consecutive_skips", 0) + 1
    _skips_state["last_skip_timestamp"] = datetime.now().isoformat()
    
    # Agregar al historial
    if "skip_history" not in _skips_state:
        _skips_state["skip_history"] = []
    
    _skips_state["skip_history"].append({
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "consecutive_count": _skips_state["consecutive_skips"]
    })
    
    # Mantener solo los últimos 100 registros
    if len(_skips_state["skip_history"]) > 100:
        _skips_state["skip_history"] = _skips_state["skip_history"][-100:]
    
    _save_skips_state()
    _sync_skip_counter_to_scorecard()
    return _skips_state["consecutive_skips"]

def reset_skips_counter() -> None:
    """
    Resetea el contador de skips consecutivos a cero.
    Also syncs the reset to the scorecard.
    """
    global _skips_state
    _load_skips_state()
    
    if _skips_state.get("consecutive_skips", 0) > 0:
        _skips_state["consecutive_skips"] = 0
        _skips_state["last_reset_timestamp"] = datetime.now().isoformat()
        _save_skips_state()
        _sync_skip_counter_to_scorecard()

def get_skip_status() -> Dict[str, Any]:
    """
    Obtiene el estado completo del skip counter.
    
    Returns:
        Dict con consecutive_skips, last_skip_timestamp, skip_history
    """
    _load_skips_state()
    return {
        "consecutive_skips": _skips_state.get("consecutive_skips", 0),
        "last_skip_timestamp": _skips_state.get("last_skip_timestamp"),
        "last_reset_timestamp": _skips_state.get("last_reset_timestamp"),
        "total_skips_24h": len([
            s for s in _skips_state.get("skip_history", [])
            if s.get("timestamp") and 
            (datetime.now() - datetime.fromisoformat(s["timestamp"].replace('Z', '+00:00'))).total_seconds() < 86400
        ]),
        "skip_history": _skips_state.get("skip_history", [])[-10:]  # Últimos 10
    }
