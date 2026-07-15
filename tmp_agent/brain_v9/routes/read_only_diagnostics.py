from __future__ import annotations

import json
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["read-only-diagnostics"])


@router.get("/brain/rsi")
async def brain_rsi():
    from brain_v9.brain.rsi import RSIManager
    return await RSIManager().run_strategic_analysis()


@router.get("/brain/learned/patterns")
async def brain_learned_patterns():
    """List all learned failure correction patterns."""
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        patterns = learner.list_all()
        return {
            "count": len(patterns),
            "patterns": patterns,
        }
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "patterns": []}


@router.get("/brain/learned/patterns/{pattern_id}")
async def brain_learned_pattern_detail(pattern_id: str):
    try:
        from brain_v9.agent.failure_learner import FailureLearner
        learner = FailureLearner.get()
        p = learner.get_pattern(pattern_id)
        if not p:
            raise HTTPException(status_code=404, detail=f"pattern {pattern_id} not found")
        return p.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/brain/health_gate/status")
async def brain_health_gate_status():
    """Get status of health gate monitoring sessions."""
    try:
        from brain_v9.agent.health_gate import HealthGate
        gate = HealthGate.get()
        return {"active_sessions": gate.list_active()}
    except Exception as exc:
        return {"_error": str(exc), "active_sessions": []}


@router.get("/brain/reasoning/history")
async def brain_reasoning_history(limit: int = 20):
    """Get recent reasoning correction attempts."""
    try:
        from brain_v9.agent.reasoning_corrector import ReasoningCorrector
        corrector = ReasoningCorrector.get()
        history = corrector.get_correction_history(limit)
        return {"count": len(history), "corrections": history}
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "corrections": []}


@router.get("/brain/proactive/status")
async def brain_proactive_status():
    """R9.2: Live observability of ProactiveScheduler.

    Returns running flag, all configured tasks (with last_run / next_run /
    enabled / interval), recent execution history, and unacknowledged alerts.
    No disk hit -- reads in-memory state from the singleton.
    """
    payload: Dict[str, Any] = {
        "running": False,
        "tasks": [],
        "recent_history": [],
        "alerts_unack": [],
        "total_history": 0,
    }
    try:
        from brain_v9.autonomy.proactive_scheduler import get_proactive_scheduler
        import time as _time
        sched = get_proactive_scheduler()
        payload["running"] = sched.running
        now = _time.time()
        for t in sched.tasks:
            tid = t.get("id", "")
            last = sched._last_run.get(tid, 0)
            interval_s = int(t.get("interval_minutes", 60)) * 60
            next_due = (last + interval_s) if last else now
            payload["tasks"].append({
                "id": tid,
                "description": t.get("description", ""),
                "interval_minutes": t.get("interval_minutes"),
                "enabled": t.get("enabled", True),
                "last_run_ts": last if last else None,
                "last_run_age_s": int(now - last) if last else None,
                "next_run_in_s": int(max(0, next_due - now)) if last else 0,
                "is_due": (now - last) >= interval_s if last else True,
            })
        payload["total_history"] = len(sched._history)
        payload["recent_history"] = sched._history[-20:]
        try:
            from brain_v9.config import BASE_PATH
            alerts_path = BASE_PATH / "tmp_agent" / "state" / "scheduler_alerts.json"
            if alerts_path.exists():
                with open(alerts_path, "r", encoding="utf-8") as f:
                    all_alerts = json.load(f)
                payload["alerts_unack"] = [a for a in all_alerts if not a.get("acknowledged")][-20:]
        except Exception as _e:
            payload["alerts_unack"] = [{"_error": str(_e)}]
    except Exception as e:
        payload["_error"] = str(e)
    return payload


@router.get("/brain/llm/circuit_breaker")
async def brain_llm_circuit_breaker():
    """Live snapshot of per-model circuit breaker, chain health and latency p50/p95/p99."""
    try:
        from brain_v9.core.llm import LLMManager
        mgr = LLMManager()
        cb_payload: Dict[str, Any] = {}
        cb_state = getattr(mgr, "_cb_state", {}) or {}
        for model_key, cb in cb_state.items():
            try:
                is_open = mgr._cb_is_open(model_key)
            except Exception:
                is_open = None
            cb_payload[model_key] = {
                "is_open": is_open,
                "fails": cb.get("fails", 0),
                "open_until": cb.get("open_until", 0),
                "open_in_s": max(0, int(cb.get("open_until", 0) - time.time())),
            }
        latency_payload: Dict[str, Any] = {}
        try:
            latency_payload = mgr.latency_percentiles()
        except Exception as e:
            latency_payload = {"_error": str(e)}
        chain_health: Any = {}
        try:
            chain_health = mgr.chain_health_snapshot()
        except Exception as e:
            chain_health = {"_error": str(e)}
        return {
            "circuit_breaker": cb_payload,
            "chain_health": chain_health,
            "latency_per_model": latency_payload,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cb snapshot failed: {e}")
