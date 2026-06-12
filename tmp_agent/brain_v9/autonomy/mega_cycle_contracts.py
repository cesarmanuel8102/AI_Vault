from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "BLOCKED"]
CycleDecision = Literal["implemented", "blocked", "proposal_only", "recorded"]


@dataclass(frozen=True)
class MegaCycleTask:
    cycle_id: str
    batch_id: int
    domain: str
    prompt_profile: str
    objective: str
    expected_artifact: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MegaCycleRecord:
    cycle_id: str
    batch_id: int
    domain: str
    prompt_profile: str
    provider_selected: str
    model_selected: str
    provider_status: str
    fallback_used: bool
    content_non_empty: bool
    risk_level: RiskLevel
    codex_critique: str
    decision: CycleDecision
    implemented: bool
    tests_run: list[str]
    lesson_created: bool
    mistake_created: bool
    promotion_candidate_created: bool
    score_before: float
    score_after: float
    evidence_paths: list[str]
    safety_status: str
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MegaRunSummary:
    target_cycles: int
    cycles_completed: int
    batches_completed: int
    implemented: int
    blocked: int
    provider_success_rate: float
    fallback_rate: float
    lessons_created: int
    mistakes_created: int
    promotion_candidates_created: int
    score_before: float
    score_after: float
    daily_dryrun_ready: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
