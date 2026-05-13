from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def make_tool_call(
    *,
    tool_name: str,
    tool_args: Optional[Dict[str, Any]],
    tool_args_hash: str,
    ok: Optional[bool],
    error: Optional[str],
    output_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_args": tool_args or {},
        "tool_args_hash": tool_args_hash,
        "ok": ok,
        "error": error,
        "output_summary": output_summary or {},
    }


def make_episode_event(
    *,
    room_id: str,
    type: str,
    step_id: Optional[str] = None,
    at: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    score: Optional[float] = None,
    verdict: Optional[str] = None,
    violations: Optional[List[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ev = {"type": type, "at": at or now_iso(), "room": room_id}
    if step_id:
        ev["step_id"] = step_id
    if tool_calls is not None:
        ev["tool_calls"] = tool_calls
    if score is not None:
        ev["score"] = score
    if verdict is not None:
        ev["verdict"] = verdict
    if violations is not None:
        ev["violations"] = violations
    if extra:
        ev.update(extra)
    return ev


def append_episode_event(episode_path: Path, event: Dict[str, Any], keep_last: int = 200) -> Dict[str, Any]:
    episode_path.parent.mkdir(parents=True, exist_ok=True)

    if episode_path.exists():
        try:
            obj = json.loads(episode_path.read_text(encoding="utf-8"))
        except Exception:
            obj = {"events": []}
    else:
        obj = {"events": []}

    events = obj.get("events") if isinstance(obj, dict) else None
    if not isinstance(events, list):
        events = []

    events.append(event)
    if len(events) > keep_last:
        events = events[-keep_last:]

    obj = {"events": events}
    episode_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return event
