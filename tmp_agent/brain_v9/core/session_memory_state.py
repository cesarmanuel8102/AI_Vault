from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import brain_v9.config as _cfg

SESSION_MEMORY_ARTIFACT = _cfg.STATE_PATH / "session_memory.json"
_FILE_REF_RE = re.compile(r"[A-Za-z]:\\[^\s`\"']+")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logging.getLogger("brain_v9.core.session_memory_state").debug("Failed to read JSON %s: %s", path, exc)
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_file_refs(messages: List[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    seen = set()
    for item in messages:
        content = str(item.get("content") or "")
        for match in _FILE_REF_RE.findall(content):
            if match not in seen:
                refs.append(match)
                seen.add(match)
    return refs[:20]


def _build_decisions(long_term: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    decisions: List[Dict[str, str]] = []
    for item in long_term[-5:]:
        text = str(item.get("summary") or item.get("note") or "").strip()
        if not text:
            continue
        decisions.append(
            {
                "decision": text[:220],
                "reason": str(item.get("source") or "memory_summary"),
                "timestamp": str(item.get("timestamp") or ""),
            }
        )
    return decisions


def build_session_memory(session_id: str = "default") -> Dict[str, Any]:
    memory_dir = _cfg.MEMORY_PATH / session_id
    short_term = _read_json(memory_dir / "short_term.json", default={})
    long_term = _read_json(memory_dir / "long_term.json", default=[])
    utility = _read_json(_cfg.STATE_PATH / "utility_u_latest.json", default={})
    meta = _read_json(_cfg.STATE_PATH / "meta_governance_status_latest.json", default={})
    security = _read_json(_cfg.STATE_PATH / "security" / "security_posture_latest.json", default={})

    messages = short_term.get("messages") if isinstance(short_term, dict) else []
    if not isinstance(messages, list):
        messages = []
    if not isinstance(long_term, list):
        long_term = []

    recent_messages = messages[-20:]
    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    latest_user = str(user_messages[-1].get("content") or "").strip() if user_messages else ""
    latest_assistant = str(assistant_messages[-1].get("content") or "").strip() if assistant_messages else ""
    latest_summary = ""
    if long_term:
        latest_summary = str(long_term[-1].get("summary") or long_term[-1].get("note") or "").strip()

    blockers = utility.get("blockers") or []
    if not isinstance(blockers, list):
        blockers = []
    current_actionable = (
        ((security.get("secrets_triage") or {}).get("current_actionable_candidate_count")) or 0
    )
    open_risks = [str(x) for x in blockers[:10]]
    if current_actionable:
        open_risks.append(f"security_review_required_count={current_actionable}")

    payload = {
        "updated_utc": _now_utc_iso(),
        "session_id": session_id,
        "objective": latest_user[:240] or "continuar la sesión activa",
        "decisions": _build_decisions(long_term),
        "key_files": _extract_file_refs(recent_messages),
        "important_vars": {
            "message_count": short_term.get("count", len(messages)) if isinstance(short_term, dict) else len(messages),
            "recent_exchange_count": len(recent_messages),
            "current_focus": ((meta.get("current_focus") or {}).get("action")),
            "top_action": meta.get("top_action"),
            "control_layer_mode": meta.get("control_layer_mode"),
        },
        "current_room_context": "",
        "last_state": latest_assistant[:500] or latest_summary[:500] or "sin resumen reciente",
        "open_risks": open_risks,
        "context_window": {
            "recent_messages_preserved": len(recent_messages),
            "long_term_entries": len(long_term),
            "compression_threshold_ratio": 0.75,
            "target_recent_turns": 10,
        },
    }
    _write_json(SESSION_MEMORY_ARTIFACT, payload)
    return payload


def get_session_memory_latest(session_id: str = "default") -> Dict[str, Any]:
    payload = _read_json(SESSION_MEMORY_ARTIFACT, default={})
    if isinstance(payload, dict) and payload and payload.get("session_id") == session_id:
        return payload
    return build_session_memory(session_id=session_id)
