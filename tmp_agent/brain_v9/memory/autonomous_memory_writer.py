from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

Category = Literal[
    "provider_behavior",
    "autonomy_lesson",
    "coding_lesson",
    "cei_fdot_lesson",
    "financial_safety_lesson",
    "chat_dashboard_lesson",
    "operator_preference",
    "system_failure",
    "correction",
]

JOURNAL_PATH = Path("memory/autonomous_journal.jsonl")
PROHIBITED_PATTERNS = (
    re.compile(r"<think", re.I),
    re.compile(r"chain[- ]of[- ]thought", re.I),
    re.compile(r"raw reasoning", re.I),
    re.compile(r"sk-[A-Za-z0-9]", re.I),
    re.compile(r"broker api|place order|paper trading|live trading", re.I),
)


@dataclass(frozen=True)
class AutonomousMemoryEvent:
    source_cycle: str
    category: Category
    summary: str
    confidence: float
    evidence_path: str
    retention_class: str = "operational_long_term"
    promotion_status: str = "candidate_pending_review"
    event_id: str = field(default_factory=lambda: f"auto_mem_{uuid4().hex[:12]}")
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_memory_event(event: AutonomousMemoryEvent) -> None:
    if not event.summary.strip():
        raise ValueError("summary required")
    if not 0.0 <= float(event.confidence) <= 1.0:
        raise ValueError("confidence must be 0..1")
    if not event.evidence_path:
        raise ValueError("evidence_path required")
    joined = json.dumps(event.to_dict(), ensure_ascii=False)
    for pattern in PROHIBITED_PATTERNS:
        if pattern.search(joined):
            raise ValueError(f"prohibited memory content: {pattern.pattern}")


def append_autonomous_memory_event(event: AutonomousMemoryEvent, path: Path = JOURNAL_PATH) -> dict[str, Any]:
    validate_memory_event(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
    return event.to_dict()


def load_autonomous_memory_events(path: Path = JOURNAL_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
