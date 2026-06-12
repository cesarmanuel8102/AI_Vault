from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tmp_agent.brain_v9.autonomy.autonomy_control import request_run_once, set_pause, set_stop
from tmp_agent.brain_v9.autonomy.autonomy_watchdog import watchdog_status
from tmp_agent.brain_v9.memory.memory_auditor import audit_memory_state
from tmp_agent.brain_v9.monitoring.status_snapshot import write_status_snapshot

router = APIRouter(prefix="/brain-dashboard")


class ChatRequest(BaseModel):
    message: str


@router.get("/status")
def dashboard_status() -> dict[str, Any]:
    snapshot = write_status_snapshot()
    return {"ok": True, "watchdog": watchdog_status(), "memory": audit_memory_state(), "snapshot": snapshot}


@router.post("/control/run-once")
def control_run_once() -> dict[str, object]:
    request_run_once()
    return {"ok": True, "action": "RUN_ONCE requested", "manual_command": "tools/brain_autonomy_run_once.ps1"}


@router.post("/control/pause")
def control_pause() -> dict[str, object]:
    set_pause(True)
    return {"ok": True, "paused": True}


@router.post("/control/resume")
def control_resume() -> dict[str, object]:
    set_pause(False)
    set_stop(False)
    return {"ok": True, "paused": False, "stopped": False}


@router.post("/control/stop")
def control_stop() -> dict[str, object]:
    set_stop(True)
    return {"ok": True, "stopped": True}


@router.get("/promotion-queue")
def promotion_queue() -> dict[str, object]:
    queue = Path("memory/promotion_queue")
    items = sorted(str(path) for path in queue.glob("*.json")) if queue.exists() else []
    return {"ok": True, "count": len(items), "items": items[:50]}


@router.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")
    body = {
        "model": "brain-v9",
        "messages": [{"role": "user", "content": req.message}],
        "temperature": 0,
        "max_tokens": 256,
        "metadata": {"provider_probe": True, "read_only": True, "evaluation": True},
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8091/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    brain = data.get("brain", {})
    return {
        "ok": True,
        "content": content,
        "provider_selected": brain.get("provider_selected"),
        "model_selected": brain.get("model_selected"),
        "fallback_used": brain.get("fallback_used"),
        "no_cot_leak": brain.get("no_cot_leak"),
    }
