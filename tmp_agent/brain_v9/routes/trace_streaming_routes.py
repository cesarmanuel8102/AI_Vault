"""Agent trace streaming routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

import asyncio as _trace_async
import json
from datetime import datetime, timezone
from pathlib import Path as _Path
from typing import Annotated, Iterator

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from brain_v9.api_security import StrictOperatorAccess, require_operator_access

try:
    from brain_v9.tracing.trace_redactor import sanitize_event as _sanitize_event
except Exception:
    def _sanitize_event(event): return event  # type: ignore


router = APIRouter(tags=["agent-trace"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


def _trace_root(room_id: str, run_id: str) -> _Path:
    return _Path("C:/AI_VAULT") / "tmp_agent" / "state" / "rooms" / room_id / "agent_runs" / run_id


def _append_trace_event(event: dict) -> None:
    """Append event to trace.ndjson; sanitize then reject raw_chain_of_thought or private_reasoning."""
    event = _sanitize_event(event)
    body_json = json.dumps(event, default=str)
    if "raw_chain_of_thought" in body_json or "private_reasoning" in body_json:
        raise HTTPException(status_code=400, detail="Trace event rejected: contains raw_chain_of_thought or private_reasoning")
    room_id = event.get("room_id", "default")
    run_id = event.get("run_id", "default")
    root = _trace_root(room_id, run_id)
    root.mkdir(parents=True, exist_ok=True)
    trace_file = root / "trace.ndjson"
    with trace_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def _read_trace_events(room_id: str, run_id: str, limit: int = 200) -> list[dict]:
    root = _trace_root(room_id, run_id)
    trace_file = root / "trace.ndjson"
    if not trace_file.exists():
        return []
    events = []
    with trace_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if limit:
        events = events[-limit:]
    return events


async def _sse_event_publisher(queue) -> Iterator[str]:
    """Async generator yielding SSE lines with heartbeat."""
    while True:
        try:
            msg = await _trace_async.wait_for(queue.get(), timeout=30.0)
            if msg is None:
                break
            yield msg
        except _trace_async.TimeoutError:
            yield "event: heartbeat\ndata: {}\n\n"


def _sse_format(event: dict) -> str:
    ts = event.get("ts", datetime.now(timezone.utc).isoformat())
    return f"id: {ts}\nevent: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


_agent_trace_queues: dict[tuple[str, str], list] = {}


def _broadcast_trace_event(room_id: str, run_id: str, event: dict) -> None:
    key = (room_id, run_id)
    safe_event = _sanitize_event(dict(event))
    msg = _sse_format(safe_event)
    for q in _agent_trace_queues.get(key, []):
        try:
            q.put_nowait(msg)
        except Exception:
            pass


live_event_counter = 0


def _emit_agent_trace_internal(room_id: str, run_id: str, type_: str, title: str, text: str, severity: str = "info", data: dict | None = None):
    """Emit trace event server-side without HTTP token. Bypasses StrictOperatorAccess."""
    global live_event_counter
    live_event_counter += 1
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
        "run_id": run_id,
        "type": type_,
        "title": title,
        "text": text,
        "severity": severity,
        "data": data or {},
    }
    try:
        _append_trace_event(event)
        _broadcast_trace_event(room_id, run_id, event)
    except Exception:
        pass


@router.post("/brain/agent-trace/event")
async def brain_agent_trace_event(
    _operator: StrictOperatorAccess,
    payload: dict = Body(...),
):
    if not isinstance(payload, dict):
        return JSONResponse(content={"error": "Body must be a JSON object"}, status_code=422)
    allowed_types = {"thinking", "tool", "finding", "file", "evidence", "governance", "decision", "status", "health", "warning", "error"}
    evt_type = payload.get("type", "message")
    if evt_type not in allowed_types:
        return JSONResponse(content={"error": f"type {evt_type} not allowed"}, status_code=422)
    body_json = json.dumps(payload, default=str)
    if "raw_chain_of_thought" in body_json.lower() or "private_reasoning" in body_json.lower():
        return JSONResponse(content={"error": "Raw chain-of-thought / private reasoning not allowed"}, status_code=400)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": payload.get("room_id", "default"),
        "run_id": payload.get("run_id", "default"),
        "type": evt_type,
        "title": payload.get("title", ""),
        "text": payload.get("text", ""),
        "severity": payload.get("severity", "info"),
        "data": payload.get("data", {}),
    }
    _append_trace_event(event)
    _broadcast_trace_event(event["room_id"], event["run_id"], event)
    return {"success": True, "stored": True}


@router.get("/brain/agent-trace/latest")
async def brain_agent_trace_latest(
    _operator: OperatorAccess,
    room_id: str = "default",
    run_id: str = "default",
    limit: int = 200,
):
    events = _read_trace_events(room_id, run_id, limit=limit)
    safe_events = [_sanitize_event(dict(e)) for e in events]
    return {"success": True, "count": len(safe_events), "events": safe_events}


@router.get("/brain/agent-trace/stream")
async def brain_agent_trace_stream(
    _operator: OperatorAccess,
    room_id: str = "default",
    run_id: str = "default",
):
    queue: _trace_async.Queue[str] = _trace_async.Queue(maxsize=100)
    key = (room_id, run_id)
    if key not in _agent_trace_queues:
        _agent_trace_queues[key] = []
    _agent_trace_queues[key].append(queue)

    async def _generator():
        while True:
            try:
                msg = await _trace_async.wait_for(queue.get(), timeout=15.0)
                if msg is None:
                    break
                yield msg
            except _trace_async.TimeoutError:
                yield "event: heartbeat\ndata: {}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
