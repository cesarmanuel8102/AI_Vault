from __future__ import annotations
import json
from pathlib import Path
from .schemas import AgentTraceEvent, to_dict
from .state import RAW_COT_MARKERS


def sanitize_payload(data):
    text = json.dumps(data, ensure_ascii=False, default=str).lower()
    if any(marker in text for marker in RAW_COT_MARKERS):
        return {"redacted": True, "reason": "raw_cot_marker_blocked"}
    return data


class TraceStore:
    def __init__(self, run_dir: Path):
        self.path = run_dir / "trace.jsonl"

    def append(self, event: AgentTraceEvent) -> None:
        payload = to_dict(event)
        payload["data"] = sanitize_payload(payload.get("data", {}))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def read(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
