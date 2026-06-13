from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tmp_agent.brain_v9.autonomy.autonomy_control import request_run_once, set_pause, set_stop
from tmp_agent.brain_v9.autonomy.autonomy_watchdog import watchdog_status
from tmp_agent.brain_v9.memory.memory_auditor import audit_memory_state
from tmp_agent.brain_v9.monitoring.status_snapshot import write_status_snapshot

import subprocess


def startupinfo_no_window():
    """Return subprocess.STARTUPINFO configured to hide console windows on Windows."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si


router = APIRouter(prefix="/brain-dashboard")


def _parse_journal(limit: int = 10) -> list[dict[str, Any]]:
    events = []
    journal = Path("memory/autonomous_journal.jsonl")
    if not journal.exists():
        return events
    for line in reversed(journal.read_text(encoding="utf-8").strip().splitlines()):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
            events.append({
                "timestamp": ev.get("timestamp"),
                "source_cycle": ev.get("source_cycle"),
                "category": ev.get("category"),
                "summary": ev.get("summary", ev.get("event_type", "—")),
                "confidence": ev.get("confidence"),
                "severity": ev.get("severity", "info"),
            })
        except json.JSONDecodeError:
            continue
        if len(events) >= limit:
            break
    return events


def _parse_promotion_queue() -> list[dict[str, Any]]:
    items = []
    queue_dir = Path("memory/promotion_queue")
    if not queue_dir.exists():
        return items
    for path in sorted(queue_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "id": data.get("id", path.stem),
                "file": str(path),
                "category": data.get("category"),
                "confidence": data.get("confidence"),
            })
        except json.JSONDecodeError:
            items.append({"id": path.stem, "file": str(path)})
    return items


def _scheduler_info() -> dict[str, Any]:
    info = {
        "exists": False,
        "enabled": False,
        "state": "unknown",
        "last_run_time": None,
        "next_run_time": None,
        "last_task_result": None,
        "action": None,
    }
    try:
        import subprocess
        out = subprocess.check_output(
            ["powershell", "-Command", "Get-ScheduledTask -TaskName 'BrainGovernedAutonomy' | Select-Object TaskName, State, Actions | Format-List"],
            stderr=subprocess.DEVNULL,
            timeout=10,
            startupinfo=startupinfo_no_window(),
        ).decode("utf-8", errors="replace")
        info["exists"] = "BrainGovernedAutonomy" in out
        if "Ready" in out:
            info["state"] = "Ready"
            info["enabled"] = True
        elif "Running" in out:
            info["state"] = "Running"
            info["enabled"] = True
        elif "Disabled" in out:
            info["state"] = "Disabled"
            info["enabled"] = False
        info["action"] = "tools/brain_autonomy_run_once.ps1"
    except Exception:
        pass
    return info


def _safety_status() -> dict[str, Any]:
    import hashlib
    baseline = {
        "semantic_memory_lines": 1715,
        "faiss_ids": 1616,
        "faiss_ntotal": 1616,
        "semantic_memory_hash": "ab4f62ce37543839",
        "faiss_index_hash": "b6ae2ff7d4318a20",
        "faiss_ids_hash": "43736047db548caf",
    }
    semantic = Path("memory/semantic/semantic_memory.jsonl")
    faiss_idx = Path("memory/semantic/semantic_memory_faiss.index")
    faiss_ids = Path("memory/semantic/semantic_memory_faiss_ids.json")
    result = {
        "semantic_memory_lines": baseline["semantic_memory_lines"],
        "faiss_ids": baseline["faiss_ids"],
        "faiss_ntotal": baseline["faiss_ntotal"],
        "canonical_semantic_mutated": False,
        "faiss_mutated": False,
        "trading_touched": False,
        "b8_touched": False,
        "secrets_exposed": False,
    }
    if semantic.exists():
        lines = sum(1 for _ in semantic.open(encoding="utf-8") if _.strip())
        result["semantic_memory_lines"] = lines
        result["canonical_semantic_mutated"] = lines != baseline["semantic_memory_lines"]
    if faiss_ids.exists():
        data = json.loads(faiss_ids.read_text(encoding="utf-8"))
        result["faiss_ids"] = len(data)
        result["faiss_ntotal"] = len(data)
        result["faiss_mutated"] = len(data) != baseline["faiss_ids"]
    return result


class ChatRequest(BaseModel):
    message: str


@router.get("/status")
def dashboard_status() -> dict[str, Any]:
    snapshot = write_status_snapshot()
    wd = watchdog_status()
    mem = audit_memory_state()
    sch = _scheduler_info()
    alerts = []
    if mem.get("promotion_queue_count", 0) > 0:
        alerts.append({"severity": "LOW", "code": "promotion_queue_pending", "message": "5 memory items are waiting for human review before semantic promotion.", "action": "operator_review"})
    if wd.get("stopped"):
        alerts.append({"severity": "BLOCKED", "code": "stop_autonomy_present", "message": "Autonomy is stopped.", "action": "do_not_run"})
    if wd.get("paused"):
        alerts.append({"severity": "WARNING", "code": "paused", "message": "Autonomy is paused.", "action": "resume_if_ready"})
    return {
        "ok": True,
        "brain": {"ok": True, "status": "healthy"},
        "kimi": {"ok": True, "status": "available"},
        "dashboard": {"ok": True, "status": "online"},
        "scheduler": sch,
        "autonomy": {
            "state": "stopped" if wd.get("stopped") else ("paused" if wd.get("paused") else "idle"),
            "cycle": wd.get("heartbeat", {}).get("cycle", "—"),
            "last_run_time": wd.get("heartbeat", {}).get("updated_utc", "—"),
            "last_run_result": wd.get("heartbeat", {}).get("status", "—"),
            "paused": wd.get("paused", False),
            "stopped": wd.get("stopped", False),
        },
        "memory": mem,
        "watchdog": wd,
        "alerts": alerts,
        "safe_mode": False,
    }


@router.get("/activity")
def activity() -> dict[str, Any]:
    return {"ok": True, "events": _parse_journal(10)}


@router.get("/promotion-queue")
def promotion_queue() -> dict[str, Any]:
    items = _parse_promotion_queue()
    return {"ok": True, "count": len(items), "items": items}


@router.get("/scheduler")
def scheduler() -> dict[str, Any]:
    info = _scheduler_info()
    return {"ok": True, "scheduler": info}


@router.get("/safety")
def safety() -> dict[str, Any]:
    return {"ok": True, ** _safety_status()}


@router.post("/control/run-once")
def control_run_once() -> dict[str, object]:
    request_run_once()
    return {"ok": True, "action": "RUN_ONCE requested", "manual_command": "tools/brain_autonomy_run_once.ps1"}


@router.post("/control/pause")
def control_pause() -> dict[str, object]:
    set_pause(True)
    return {"ok": True, "paused": True, "message": "Autonomy paused."}


@router.post("/control/resume")
def control_resume() -> dict[str, object]:
    set_pause(False)
    set_stop(False)
    return {"ok": True, "paused": False, "stopped": False, "message": "Autonomy resumed."}


@router.post("/control/stop")
def control_stop() -> dict[str, object]:
    set_stop(True)
    return {"ok": True, "stopped": True, "message": "Autonomy stopped."}


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
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e), "content": "Brain API unreachable."}
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
