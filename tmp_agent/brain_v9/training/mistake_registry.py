from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


ALLOWED_MISTAKE_STATUSES = {"open", "mitigated", "regression_guarded", "closed"}
ALLOWED_SEVERITIES = {"low", "medium", "high"}


@dataclass(frozen=True)
class MistakeEntry:
    mistake_id: str
    domain: str
    severity: str
    detection_rule: str
    recurrence_count: int
    linked_lesson_id: str
    regression_test: str
    status: str = "open"

    def validate(self) -> None:
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity}")
        if self.status not in ALLOWED_MISTAKE_STATUSES:
            raise ValueError(f"invalid status: {self.status}")
        if self.recurrence_count < 0:
            raise ValueError("recurrence_count must be non-negative")
        for value in (self.mistake_id, self.domain, self.detection_rule, self.linked_lesson_id, self.regression_test):
            if not str(value).strip():
                raise ValueError("mistake entry required fields must be non-empty")

    def to_dict(self) -> Dict[str, object]:
        self.validate()
        return asdict(self)


@dataclass
class MistakeRegistry:
    entries: List[MistakeEntry] = field(default_factory=list)

    def add(self, entry: MistakeEntry) -> None:
        entry.validate()
        if any(existing.mistake_id == entry.mistake_id for existing in self.entries):
            raise ValueError(f"duplicate mistake_id: {entry.mistake_id}")
        self.entries.append(entry)

    def find(self, mistake_id: str) -> Optional[MistakeEntry]:
        return next((entry for entry in self.entries if entry.mistake_id == mistake_id), None)

    def to_list(self) -> List[Dict[str, object]]:
        return [entry.to_dict() for entry in self.entries]
