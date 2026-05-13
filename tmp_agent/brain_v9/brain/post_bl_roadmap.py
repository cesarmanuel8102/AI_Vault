"""
Brain V9 - Post-BL roadmap
Roadmap canónico de desarrollo continuo una vez completado el roadmap BL.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ROOMS_PATH = STATE_PATH / "rooms"
POST_BL_ROOM = ROOMS_PATH / "brain_post_bl_continual_development"

FILES = {
    "roadmap_governance": STATE_PATH / "roadmap_governance_status.json",
    "meta_improvement": STATE_PATH / "meta_improvement_status_latest.json",
    "utility_governance": STATE_PATH / "utility_governance_status_latest.json",
    "chat_product": STATE_PATH / "chat_product_status_latest.json",
    "status": STATE_PATH / "post_bl_roadmap_status_latest.json",
    "contract": POST_BL_ROOM / "post_bl_roadmap_contract.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _item(
    item_id: str,
    title: str,
    objective: str,
    status: str,
    evidence: List[str],
    next_actions: List[str],
    detail: str,
) -> Dict[str, Any]:
    return {
        "item_id": item_id,
        "title": title,
        "objective": objective,
        "status": status,
        "evidence_paths": evidence,
        "next_actions": next_actions,
        "detail": detail,
    }


def refresh_post_bl_roadmap_status() -> Dict[str, Any]:
    roadmap_governance = read_json(FILES["roadmap_governance"], {})
    meta = read_json(FILES["meta_improvement"], {})
    utility = read_json(FILES["utility_governance"], {})
    chat = read_json(FILES["chat_product"], {})

    bl_done = roadmap_governance.get("promotion", {}).get("promotion_state") == "terminal_phase_accepted"
    utility_score = float(utility.get("u_proxy_score", 0.0) or 0.0)
    utility_blockers = utility.get("blockers", []) or []
    utility_verdict = str(utility.get("verdict") or "").strip().lower()
    utility_next_actions = utility.get("next_actions", []) or []
    playbook_count = int(meta.get("memory", {}).get("summary", {}).get("playbook_count", 0) or 0)
    resolved_gap_count = int(meta.get("memory", {}).get("summary", {}).get("resolved_gap_count", 0) or 0)
    quality_score = float(chat.get("quality_score", 0.0) or 0.0)
    open_gaps = int(meta.get("gap_registry", {}).get("summary", {}).get("open_count", 0) or 0)
    top_gap = meta.get("top_gap") or {}

    utility_completed = (
        utility_score >= 0.15
        and not utility_blockers
        and utility_verdict == "promote"
        and not utility_next_actions
    )

    items = [
        _item(
            "PBL-01",
            "Cerrar sensibilidad y lift fino de Utility",
            "Hacer que Utility U responda de forma coherente a mejoras pequeñas y al mejor contexto ejecutable.",
            "done" if utility_completed else "active",
            utility.get("evidence_paths", []),
            utility_next_actions,
            f"u={utility_score} · verdict={utility_verdict or 'unknown'} · blockers={len(utility_blockers)} · next={len(utility_next_actions)}",
        ),
        _item(
            "PBL-02",
            "Consolidar reutilización de playbooks y métodos meta",
            "Hacer que el Brain reutilice explícitamente métodos efectivos por gap y no recompute desde cero.",
            "done" if playbook_count >= 7 and resolved_gap_count >= 1 else "active",
            [str(STATE_PATH / "brain_self_improvement_memory.json"), str(STATE_PATH / "brain_meta_execution_ledger.json")],
            ["advance_meta_improvement_roadmap"],
            f"playbooks={playbook_count} · resolved_gaps={resolved_gap_count}",
        ),
        _item(
            "PBL-03",
            "Cerrar chat como producto observable y gobernado",
            "Pasar el chat de baseline aceptado a producto observable con checks de continuidad, memoria y telemetría.",
            "done" if chat.get("current_state") == "quality_observable" and quality_score >= 0.8 else "active",
            chat.get("evidence_paths", []),
            chat.get("next_actions", []),
            f"state={chat.get('current_state')} · quality_score={quality_score}",
        ),
        _item(
            "PBL-04",
            "Mantener excelencia continua y preparar el siguiente programa",
            "Seguir cerrando gaps internos de alto beneficio y dejar listo el siguiente roadmap si reaparecen dominios débiles.",
            "done" if bl_done and open_gaps == 0 else "queued",
            [str(FILES["roadmap_governance"]), str(FILES["meta_improvement"])],
            ["advance_meta_improvement_roadmap"] if open_gaps else [],
            f"bl_done={bl_done} · open_gaps={open_gaps} · top_gap={top_gap.get('gap_id')}",
        ),
    ]

    current_focus = next((item for item in items if item["status"] != "done"), None)
    if current_focus:
        current_focus["status"] = "active"
    work_status = "completed" if not current_focus else "active"

    status = {
        "schema_version": "post_bl_roadmap_status_v1",
        "updated_utc": _utc_now(),
        "roadmap_id": "brain_post_bl_continual_development_v1",
        "source_roadmap": roadmap_governance.get("canonical", {}).get("roadmap_id"),
        "enabled": bl_done,
        "work_status": work_status if bl_done else "blocked_until_bl_terminal",
        "title": "Desarrollo continuo post-BL",
        "mission": "mantener al Brain mejorándose después del cierre BL, priorizando gaps internos de más beneficio y mejor evidencia.",
        "current_focus": current_focus,
        "items": items,
        "summary": {
            "done": sum(1 for item in items if item["status"] == "done"),
            "active": sum(1 for item in items if item["status"] == "active"),
            "queued": sum(1 for item in items if item["status"] == "queued"),
        },
        "meta_brain_handoff": "\n".join([
            "roadmap=brain_post_bl_continual_development_v1",
            f"enabled={bl_done}",
            f"work_status={work_status if bl_done else 'blocked_until_bl_terminal'}",
            f"current_focus={current_focus.get('item_id') if current_focus else 'none'}",
            f"title={current_focus.get('title') if current_focus else 'none'}",
            f"objective={current_focus.get('objective') if current_focus else 'none'}",
            f"detail={current_focus.get('detail') if current_focus else 'no_open_items'}",
            f"next_actions={' | '.join(current_focus.get('next_actions', [])) if current_focus else 'none'}",
        ]),
    }
    contract = {
        "schema_version": "post_bl_roadmap_contract_v1",
        "updated_utc": status["updated_utc"],
        "roadmap_id": status["roadmap_id"],
        "enabled": bl_done,
        "work_status": status["work_status"],
        "current_focus": current_focus.get("item_id") if current_focus else None,
        "summary": status["summary"],
    }
    write_json(FILES["status"], status)
    write_json(FILES["contract"], contract)
    return status


def read_post_bl_roadmap_status() -> Dict[str, Any]:
    status = read_json(FILES["status"], {})
    if status:
        return status
    return refresh_post_bl_roadmap_status()
