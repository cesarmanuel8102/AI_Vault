"""Read-only / dry-run chat excellence proposal routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["chat-excellence-readonly"])


@router.get("/brain/chat_excellence/status")
async def brain_chat_excellence_status():
    """R9.3: Live observability of the chat_excellence self-improvement loop.

    Returns total iterations, latest iteration with full structured fields,
    and a compact history of last 20 iterations (weakness + status only).
    """
    import json
    from pathlib import Path
    from typing import Any, Dict

    from brain_v9.config import BASE_PATH

    payload: Dict[str, Any] = {
        "total_iterations": 0,
        "latest": None,
        "recent": [],
        "parsed_ratio": 0.0,
    }
    try:
        ce_path = BASE_PATH / "tmp_agent" / "state" / "chat_excellence_history.json"
        if not ce_path.exists():
            payload["_note"] = "No iterations yet — loop runs every 60 min, first run in ~60-90s after boot"
            return payload
        with open(ce_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        payload["total_iterations"] = len(history)
        if history:
            payload["latest"] = history[-1]
            parsed_count = sum(1 for h in history if h.get("parsed_ok"))
            payload["parsed_ratio"] = round(parsed_count / len(history), 3)
            payload["recent"] = [
                {
                    "iter": h.get("iter"),
                    "timestamp": h.get("timestamp"),
                    "weakness": (h.get("weakness") or "")[:120],
                    "impact_score": h.get("impact_score"),
                    "status": h.get("status"),
                    "elapsed_s": h.get("elapsed_s"),
                    "parsed_ok": h.get("parsed_ok"),
                }
                for h in history[-20:]
            ]
    except Exception as e:
        payload["_error"] = str(e)
    return payload


@router.get("/brain/chat_excellence/proposals")
async def brain_ce_proposals(status: Optional[str] = None, limit: int = 50):
    """List chat_excellence executor proposals (most recent first)."""
    try:
        from brain_v9.autonomy.chat_excellence_executor import list_proposals, stats
        items = list_proposals(status_filter=status, limit=limit)
        return {"items": items, "count": len(items), "stats": stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce proposals list failed: {e}")


@router.get("/brain/learning/proposals")
async def brain_learning_proposals(status: Optional[str] = None, limit: int = 50):
    """Alias: learning proposals served from chat_excellence source."""
    data = await brain_ce_proposals(status=status, limit=limit)
    return {"ok": True, "route": "/brain/learning/proposals", "canonical": "/brain/chat_excellence/proposals", **data}


@router.get("/brain/chat_excellence/proposals/{proposal_id}")
async def brain_ce_proposal_get(proposal_id: str):
    try:
        from brain_v9.autonomy.chat_excellence_executor import get_proposal
        rec = get_proposal(proposal_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return rec
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce proposal get failed: {e}")


@router.post("/brain/chat_excellence/proposals/{proposal_id}/dry_run")
async def brain_ce_proposal_dry_run(proposal_id: str):
    """R10.2b: genera diff unificado del proposal SIN escribir nada.
    Persiste el diff en el record para revision posterior."""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import dry_run_proposal
        result = dry_run_proposal(proposal_id)
        if not result.get("ok") and result.get("error") == "proposal_not_found":
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce dry_run failed: {e}")


@router.get("/brain/chat_excellence/proposals/{proposal_id}/health_gate_log")
async def brain_ce_proposal_health_gate_log(proposal_id: str, tail: int = 200):
    """R10.2c: lee el log del health gate detached que valida el restart
    post-apply y hace auto-rollback si el brain no recupera. Util para ver
    el progreso/resultado de un apply con auto_restart=true."""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import get_health_gate_log
        return get_health_gate_log(proposal_id, tail=tail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce health gate log failed: {e}")


@router.get("/brain/chat_excellence/proposals/{proposal_id}/evaluation_status")
async def brain_ce_proposal_eval_status(proposal_id: str):
    """R11: lectura rapida del estado de evaluacion sin disparar nueva eval.
    Devuelve {has_baseline, validated, last_eval_at, comparisons, ...}"""
    try:
        from brain_v9.autonomy.chat_excellence_patcher import _load_proposal
        rec = _load_proposal(proposal_id)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "status": rec.get("status"),
            "has_baseline": bool(rec.get("r11_baseline")),
            "baseline_consts": list((rec.get("r11_baseline") or {}).keys()),
            "validated": bool(rec.get("r11_validated")),
            "regression_detected": bool(rec.get("r11_regression_detected")),
            "last_eval_at": rec.get("r11_eval_at"),
            "last_comparisons": rec.get("r11_comparisons") or [],
            "applied_at": rec.get("applied_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ce eval status failed: {e}")
