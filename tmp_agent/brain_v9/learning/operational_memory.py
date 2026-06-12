from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEARNING_ROOT = Path(__file__).resolve().parent
OPERATIONAL_LESSONS_PATH = LEARNING_ROOT / "operational_lessons.jsonl"
PROTECTED_PATH_MARKERS = ("memory/semantic/", "trading/", "B8/", "tmp_agent/strategies/", ".env")


@dataclass(frozen=True)
class OperationalLesson:
    lesson_id: str
    source_cycle: str
    evidence_path: str
    failure_or_success_type: str
    summary: str
    test_to_prevent_regression: str
    promotion_recommendation: str
    risk_level: str
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _guard_path(path: Path) -> None:
    normalized = path.as_posix()
    if any(marker in normalized for marker in PROTECTED_PATH_MARKERS):
        raise ValueError(f"protected path denied: {normalized}")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    _guard_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def append_operational_lesson(lesson: OperationalLesson, path: Path = OPERATIONAL_LESSONS_PATH) -> None:
    append_jsonl(path, lesson.to_dict())
