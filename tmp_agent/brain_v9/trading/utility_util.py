"""
Brain V9 — trading/utility_util.py
Utilidades para gestión de historial de U Score y métricas de utilidad.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

import brain_v9.config as _cfg
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("utility_util")

def get_u_history_file() -> Path:
    """Retorna la ruta del archivo de historial de U."""
    return _cfg.BRAIN_V9_PATH / "state" / "utility_u_history.json"

def update_u_history(
    u_proxy_score: float,
    reason: str = "",
    trades_count: int = 0,
    additional_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Actualiza el historial de U Score.
    
    Args:
        u_proxy_score: Valor actual del U Score
        reason: Razón de la actualización
        trades_count: Número de trades ejecutados
        additional_data: Datos adicionales opcionales
        
    Returns:
        Dict con el estado actualizado
    """
    history_file = get_u_history_file()
    
    # Cargar historial existente
    history = {
        "entries": [],
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "version": "1.0"
        }
    }
    
    if history_file.exists():
        try:
            history = read_json(history_file, history)
            # Compat: brain.utility writes utility_u_history.json as list.
            # Convert list format to dict format expected by utility_util.
            if isinstance(history, list):
                converted_entries = []
                for row in history:
                    if not isinstance(row, dict):
                        continue
                    converted_entries.append({
                        "timestamp": row.get("timestamp"),
                        "u_proxy_score": float(row.get("u_proxy_score", row.get("u_score", 0.0)) or 0.0),
                        "reason": row.get("reason", "legacy_history_entry"),
                        "trades_count": int(row.get("trades_count", 0) or 0),
                    })
                history = {
                    "entries": converted_entries,
                    "metadata": {
                        "created_at": datetime.now().isoformat(),
                        "version": "1.0",
                        "migrated_from_list": True,
                    },
                }
            elif not isinstance(history, dict):
                log.warning("U history file contained %s instead of dict/list, resetting", type(history).__name__)
                history = {
                    "entries": [],
                    "metadata": {
                        "created_at": datetime.now().isoformat(),
                        "version": "1.0"
                    }
                }
        except Exception as exc:
            log.warning("Error loading U history from %s: %s", history_file, exc)
    
    # Crear nueva entrada
    entry = {
        "timestamp": datetime.now().isoformat(),
        "u_proxy_score": float(u_proxy_score),
        "reason": reason,
        "trades_count": int(trades_count)
    }
    
    if additional_data:
        entry["additional_data"] = additional_data
    
    # Agregar al historial
    if "entries" not in history:
        history["entries"] = []
    if "metadata" not in history or not isinstance(history["metadata"], dict):
        history["metadata"] = {"created_at": datetime.now().isoformat(), "version": "1.0"}
    
    history["entries"].append(entry)
    
    # Calcular estadísticas
    entries = history["entries"]
    if len(entries) > 0:
        scores = [e.get("u_proxy_score", 0) for e in entries if e.get("u_proxy_score") is not None]
        if scores:
            history["metadata"]["avg_u_24h"] = sum(scores[-24:]) / min(len(scores), 24) if len(scores) > 0 else 0.0
            history["metadata"]["avg_u_7d"] = sum(scores[-168:]) / min(len(scores), 168) if len(scores) > 0 else 0.0
            history["metadata"]["max_u"] = max(scores)
            history["metadata"]["min_u"] = min(scores)
            history["metadata"]["current_u"] = scores[-1] if scores else 0.0
            history["metadata"]["trend"] = "up" if len(scores) > 1 and scores[-1] > scores[-2] else "down" if len(scores) > 1 and scores[-1] < scores[-2] else "stable"
    
    history["metadata"]["updated_at"] = datetime.now().isoformat()
    history["metadata"]["total_entries"] = len(history["entries"])
    
    # Guardar
    try:
        write_json(history_file, history)
    except Exception as e:
        print(f"Error guardando historial U: {e}")
    
    return history

def get_u_history(limit: int = 100) -> Dict[str, Any]:
    """
    Obtiene el historial de U Score.
    
    Args:
        limit: Número máximo de entradas a retornar
        
    Returns:
        Dict con entries y metadata
    """
    history_file = get_u_history_file()
    
    if not history_file.exists():
        return {
            "entries": [],
            "metadata": {
                "error": "No history file found",
                "total_entries": 0
            }
        }
    
    try:
        history = read_json(history_file, {})
        if not history:
            return {
                "entries": [],
                "metadata": {
                    "error": "No history file found",
                    "total_entries": 0
                }
            }
        # Compat: brain.utility may persist this file as list.
        if isinstance(history, list):
            normalized = []
            for row in history:
                if not isinstance(row, dict):
                    continue
                normalized.append({
                    "timestamp": row.get("timestamp"),
                    "u_proxy_score": float(row.get("u_proxy_score", row.get("u_score", 0.0)) or 0.0),
                    "reason": row.get("reason", "legacy_history_entry"),
                    "trades_count": int(row.get("trades_count", 0) or 0),
                })
            history = {
                "entries": normalized,
                "metadata": {
                    "version": "1.0",
                    "migrated_from_list": True,
                    "total_entries": len(normalized),
                },
            }
        # Limitar entries
        if "entries" in history and len(history["entries"]) > limit:
            history["entries"] = history["entries"][-limit:]
        return history
    except Exception as e:
        return {
            "entries": [],
            "metadata": {
                "error": str(e),
                "total_entries": 0
            }
        }

def get_u_trend(period: str = "24h") -> Dict[str, Any]:
    """
    Calcula la tendencia de U en un período.
    
    Args:
        period: Período de análisis ("1h", "24h", "7d")
        
    Returns:
        Dict con tendencia y estadísticas
    """
    history = get_u_history(limit=_cfg.MAX_LEDGER_ENTRIES)
    entries = history.get("entries", [])
    
    if not entries:
        return {"trend": "unknown", "change": 0.0, "samples": 0}
    
    # Calcular ventana de tiempo
    now = datetime.now()
    if period == "1h":
        cutoff = now - timedelta(hours=1)
    elif period == "24h":
        cutoff = now - timedelta(hours=24)
    elif period == "7d":
        cutoff = now - timedelta(days=7)
    else:
        cutoff = now - timedelta(hours=24)
    
    # Filtrar entradas
    recent_entries = [
        e for e in entries 
        if e.get("timestamp") and datetime.fromisoformat(e["timestamp"].replace('Z', '+00:00')) > cutoff
    ]
    
    if len(recent_entries) < 2:
        return {"trend": "insufficient_data", "change": 0.0, "samples": len(recent_entries)}
    
    scores = [e.get("u_proxy_score", 0) for e in recent_entries]
    first_score = scores[0]
    last_score = scores[-1]
    change = last_score - first_score
    
    trend = "up" if change > 0.01 else "down" if change < -0.01 else "stable"
    
    return {
        "trend": trend,
        "change": change,
        "change_percent": (change / first_score * 100) if first_score != 0 else 0,
        "first_score": first_score,
        "last_score": last_score,
        "samples": len(recent_entries),
        "avg": sum(scores) / len(scores),
        "max": max(scores),
        "min": min(scores)
    }

def clear_u_history() -> bool:
    """
    Limpia el historial de U (usar con cuidado).
    
    Returns:
        True si se limpió exitosamente
    """
    history_file = get_u_history_file()
    if history_file.exists():
        try:
            history_file.unlink()
            return True
        except Exception as exc:
            log.warning("Error deleting U history file %s: %s", history_file, exc)
    return False
