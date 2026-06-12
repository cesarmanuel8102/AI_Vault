from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict


ALLOWED_PROMOTION_STATUSES = {"candidate", "validated", "promoted", "blocked", "deprecated"}


@dataclass(frozen=True)
class LessonCard:
    lesson_id: str
    domain: str
    mistake_observed: str
    correct_behavior: str
    example_prompt: str
    bad_response_summary: str
    good_response_target: str
    test_to_prevent_regression: str
    promotion_status: str = "candidate"

    def validate(self) -> None:
        required = [
            self.lesson_id,
            self.domain,
            self.mistake_observed,
            self.correct_behavior,
            self.example_prompt,
            self.good_response_target,
            self.test_to_prevent_regression,
        ]
        if any(not str(value).strip() for value in required):
            raise ValueError("lesson card required fields must be non-empty")
        if self.promotion_status not in ALLOWED_PROMOTION_STATUSES:
            raise ValueError(f"invalid promotion_status: {self.promotion_status}")

    def to_dict(self) -> Dict[str, str]:
        self.validate()
        return asdict(self)
