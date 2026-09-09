from __future__ import annotations
import json
from pathlib import Path
from ...tracing.trace_redactor import sanitize_event

from .schemas import AgentTraceEvent, TRACE_EVENT_TAXONOMY, to_dict
from .state import RAW_COT_MARKERS


def _validate_governed_event(event: AgentTraceEvent) -> None:
    if event.schema_version != 1:
        raise ValueError("trace_schema_version_invalid")
    if not isinstance(event.run_id, str) or not event.run_id.strip():
        raise ValueError("trace_run_id_required")
    if not isinstance(event.event_id, str) or not event.event_id.strip():
        raise ValueError("trace_event_id_required")
    if not isinstance(event.correlation_id, str) or not event.correlation_id.strip():
        raise ValueError("trace_correlation_id_required")
    if event.event_type not in TRACE_EVENT_TAXONOMY:
        raise ValueError("trace_event_type_not_allowed")


def _redact_private_reasoning_markers(payload: dict) -> dict:
    data = payload.get("data", {})
    text = json.dumps(data, ensure_ascii=False, default=str).lower()
    if any(marker in text for marker in RAW_COT_MARKERS):
        payload["data"] = {"redacted": True, "reason": "private_reasoning_marker_blocked"}
    return payload


class TraceStore:
    def __init__(self, run_dir: Path):
        self.path = run_dir / "trace.jsonl"

    def append(self, event: AgentTraceEvent) -> None:
        _validate_governed_event(event)
        payload = _redact_private_reasoning_markers(sanitize_event(to_dict(event)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def read(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
