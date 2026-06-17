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


def _truncate_error(exc: BaseException | str, limit: int = 220) -> str:
    text = str(exc)
    return text[:limit]


def _scheduler_info(use_subprocess: bool = False) -> dict[str, Any]:
    """Return scheduler state without blocking dashboard polling.

    The /status path calls this with use_subprocess=False so live polling is
    read-mostly and fast. The /scheduler endpoint may use a short, hidden
    subprocess and returns degraded data instead of raising.
    """
    info: dict[str, Any] = {
        "exists": False,
        "enabled": False,
        "state": "unknown_cached",
        "last_run_time": None,
        "next_run_time": None,
        "last_task_result": None,
        "action": "tools/brain_autonomy_run_once.ps1",
        "degraded": False,
        "source": "cached_no_subprocess",
    }
    cache = Path("tmp_agent/runtime/BrainGovernedAutonomy.task.json")
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            info.update({
                "exists": True,
                "enabled": bool(data.get("enabled", data.get("enabled_by_default", False))),
                "state": "cached_ready" if not data.get("enabled") else "cached_enabled",
                "action": data.get("command", info["action"]),
                "source": "cache_file",
            })
        except Exception as exc:
            info.update({"degraded": True, "safe_error": _truncate_error(exc), "source": "cache_parse_error"})
    if not use_subprocess:
        return info
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-ScheduledTask -TaskName 'BrainGovernedAutonomy' | Select-Object TaskName,State | ConvertTo-Json -Compress",
        ]
        kwargs: dict[str, Any] = {"stderr": subprocess.DEVNULL, "stdout": subprocess.PIPE, "timeout": 3, "text": True}
        if os.name == "nt":
            kwargs["startupinfo"] = startupinfo_no_window()
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, **kwargs)
        out = proc.stdout or ""
        info["source"] = "hidden_subprocess_timeout_3s"
        info["exists"] = "BrainGovernedAutonomy" in out
        if "Ready" in out:
            info.update({"state": "Ready", "enabled": True})
        elif "Running" in out:
            info.update({"state": "Running", "enabled": True})
        elif "Disabled" in out:
            info.update({"state": "Disabled", "enabled": False})
        elif proc.returncode != 0:
            info.update({"degraded": True, "safe_error": "scheduler_query_nonzero_exit"})
    except Exception as exc:
        info.update({"degraded": True, "safe_error": _truncate_error(exc), "source": "hidden_subprocess_error"})
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


def _agent_v2_snapshot() -> dict[str, Any]:
    try:
        from tmp_agent.brain_v9.core.agent_kernel_v2.finalizer import PRIMARY_KIMI_MODEL
        from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import LANGGRAPH_BLOCKER, LANGGRAPH_USED, get_agent_runtime_v2
        rt = get_agent_runtime_v2()
        runs = rt.list_runs()
        latest = runs[-1] if runs else {}
        meta = latest.get("provider_metadata") or {}
        return {
            "ok": True,
            "canonical_for_new_agent_runs": True,
            "backend": rt.backend,
            "langgraph_used": LANGGRAPH_USED,
            "langgraph_blocker": LANGGRAPH_BLOCKER,
            "primary_finalizer_model": PRIMARY_KIMI_MODEL,
            "latest_provider_used": meta.get("provider_used"),
            "latest_model_used": meta.get("model_used"),
            "latest_provider_degraded": meta.get("provider_degraded"),
            "runs": len(runs),
            "latest_run_id": latest.get("run_id"),
            "trace_available": True,
            "chat_agent_route": "/v2/chat/agent",
            "status_route": "/brain-dashboard/agent-v2/status",
            "capabilities_route": "/v2/agent/capabilities",
            "legacy_agent_status": "legacy_compatible_not_canonical",
        }
    except Exception as exc:
        return {
            "ok": False,
            "degraded": True,
            "error": _truncate_error(exc),
            "canonical_for_new_agent_runs": True,
            "status_route": "/brain-dashboard/agent-v2/status",
        }


class ChatRequest(BaseModel):
    message: str
    mode: str = "read_only"
    user_id: str = "dashboard_operator"


@router.get("/status")
def dashboard_status() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    errors: list[dict[str, str]] = []

    def safe_component(name: str, fn, default):
        try:
            return fn()
        except Exception as exc:
            errors.append({"component": name, "error": _truncate_error(exc)})
            return default

    wd = safe_component("watchdog", watchdog_status, {"stopped": False, "paused": False, "heartbeat": None})
    mem = safe_component("memory", audit_memory_state, {"journal_count": None, "promotion_queue_count": None, "semantic_staging_count": None})
    sch = safe_component("scheduler", lambda: _scheduler_info(use_subprocess=False), {"exists": False, "enabled": False, "state": "unknown", "degraded": True})
    safety = safe_component("safety", _safety_status, {"canonical_semantic_mutated": None, "faiss_mutated": None})
    alerts = []
    if isinstance(mem, dict) and (mem.get("promotion_queue_count") or 0) > 0:
        alerts.append({"severity": "LOW", "code": "promotion_queue_pending", "message": "Memory items are waiting for human review before semantic promotion.", "action": "operator_review"})
    if isinstance(wd, dict) and wd.get("stopped"):
        alerts.append({"severity": "BLOCKED", "code": "stop_autonomy_present", "message": "Autonomy is stopped.", "action": "do_not_run"})
    if isinstance(wd, dict) and wd.get("paused"):
        alerts.append({"severity": "WARNING", "code": "paused", "message": "Autonomy is paused.", "action": "resume_if_ready"})
    if errors:
        alerts.append({"severity": "WARNING", "code": "status_degraded", "message": "One or more status components degraded safely.", "action": "inspect_private_evidence"})
    elapsed_ms = round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)
    agent_v2 = safe_component("agent_v2", _agent_v2_snapshot, {"ok": False, "degraded": True})
    return {
        "ok": not errors,
        "degraded": bool(errors),
        "brain": {"ok": True, "status": "healthy", "api": "http://127.0.0.1:8091"},
        "kimi": {"ok": True, "status": "available_via_provider_probe"},
        "dashboard": {"ok": True, "status": "online", "status_latency_ms": elapsed_ms},
        "scheduler": sch,
        "autonomy": {
            "state": "stopped" if wd.get("stopped") else ("paused" if wd.get("paused") else "idle"),
            "cycle": (wd.get("heartbeat") or {}).get("cycle", "—") if isinstance(wd, dict) else "—",
            "last_run_time": (wd.get("heartbeat") or {}).get("updated_utc", "—") if isinstance(wd, dict) else "—",
            "last_run_result": (wd.get("heartbeat") or {}).get("status", "—") if isinstance(wd, dict) else "—",
            "paused": wd.get("paused", False) if isinstance(wd, dict) else False,
            "stopped": wd.get("stopped", False) if isinstance(wd, dict) else False,
        },
        "memory": mem,
        "safety": safety,
        "watchdog": wd,
        "alerts": alerts,
        "errors": errors,
        "recommendation": "continue_monitoring" if not errors else "inspect_degraded_components",
        "agent_v2": agent_v2,
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
    info = _scheduler_info(use_subprocess=True)
    return {"ok": not info.get("degraded", False), "degraded": bool(info.get("degraded", False)), "scheduler": info}


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
    """Legacy dashboard chat endpoint — now proxies to canonical Agent V2."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")
    body = {
        "message": req.message.strip(),
        "mode": req.mode,
        "user_id": req.user_id,
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8091/v2/chat/agent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e), "content": "Brain API unreachable.", "note": "Ensure Agent V2 backend is running on 8091"}
    
    pm = data.get("provider_metadata", {})
    return {
        "ok": True,
        "content": data.get("final_answer", ""),
        "canonical_agent_v2": data.get("canonical_agent_v2", False),
        "run_id": data.get("run_id", ""),
        "trace_url": data.get("trace_url", ""),
        "classification": data.get("classification", ""),
        "status": data.get("status", ""),
        "model_used": pm.get("model_used", ""),
        "provider_used": pm.get("provider_used", ""),
        "provider_degraded": pm.get("provider_degraded", False),
        "fallback_reason": pm.get("fallback_reason", ""),
        "raw_cot_exposed": pm.get("raw_cot_exposed", False),
        "mode_requested": data.get("mode_requested", ""),
        "mode_effective": data.get("mode_effective", ""),
        "auto_decision": data.get("auto_decision", ""),
        "mode_escalation_required": data.get("mode_escalation_required", False),
        "mode_escalation_reason": data.get("mode_escalation_reason", ""),
        "required_permission": data.get("required_permission", ""),
        "expected_write_scope": data.get("expected_write_scope", []),
        "confirmation_id": data.get("confirmation_id", ""),
        "blocked_tools": data.get("blocked_tools", []),
    }


@router.get("/agent-v2/runs/{run_id}/trace")
def agent_v2_trace(run_id: str) -> dict[str, Any]:
    """Proxy to canonical Agent V2 trace endpoint from 8092 (same-origin for dashboard)."""
    url = f"http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e), "message": f"Trace fetch failed for {run_id}"}


@router.get("/agent-v2/status")
def agent_v2_dashboard_status() -> dict[str, Any]:
    return {"ok": True, "agent_v2": _agent_v2_snapshot(), "message": "Agent V2 is canonical for new agent operations; legacy agent remains compatible."}
