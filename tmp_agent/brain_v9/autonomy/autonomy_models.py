from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "BLOCKED"]
Decision = Literal["execute", "proposal_only", "block"]


@dataclass(frozen=True)
class AutonomyProposal:
    cycle_id: str
    prompt: str
    proposal: str
    domain: str
    expected_value: str
    evidence_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexCritique:
    cycle_id: str
    risk_level: RiskLevel
    critique: str
    required_gates: list[str]
    blocked_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CycleDecision:
    cycle_id: str
    decision: Decision
    risk_level: RiskLevel
    action_summary: str
    tests_required: list[str]
    rollback_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    decision: Decision
    score: float
    lesson_id: str
    mistake_id: str | None
    promotion_candidate_id: str | None
    evidence_path: str
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
