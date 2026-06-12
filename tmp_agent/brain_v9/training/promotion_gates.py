from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class PromotionGate:
    gate_id: str
    metric_name: str
    baseline: float
    target: float
    current: Optional[float] = None
    rollback_required: bool = False

    @property
    def pass_fail(self) -> str:
        if self.current is None:
            return "not_measured"
        return "pass" if self.current >= self.target else "fail"

    def to_dict(self) -> Dict[str, object]:
        if not self.gate_id.strip() or not self.metric_name.strip():
            raise ValueError("gate_id and metric_name are required")
        payload = asdict(self)
        payload["pass_fail"] = self.pass_fail
        return payload
