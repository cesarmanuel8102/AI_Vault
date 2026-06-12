from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .operational_memory import OperationalLesson, append_operational_lesson


def load_lessons(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def register_lesson(lesson: OperationalLesson) -> None:
    append_operational_lesson(lesson)
