from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .operational_memory import append_jsonl

MISTAKES_PATH = Path(__file__).resolve().parent / "mistakes.jsonl"


@dataclass(frozen=True)
class MistakeRecord:
    mistake_id: str
    source_cycle: str
    evidence_path: str
    severity: str
    summary: str
    prevention_test: str
    status: str = "open"
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_mistake(record: MistakeRecord, path: Path = MISTAKES_PATH) -> None:
    append_jsonl(path, record.to_dict())


def load_mistakes(path: Path = MISTAKES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
