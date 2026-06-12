from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

OperationStatus = Literal["queued", "running", "done", "blocked", "failed"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "BLOCKED"]


@dataclass(frozen=True)
class GovernedOperation:
    operation_id: str
    title: str
    risk_level: RiskLevel
    status: OperationStatus = "queued"
    evidence_path: str = ""
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
