from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .operational_memory import append_jsonl

PROMOTION_CANDIDATES_PATH = Path(__file__).resolve().parent / "promotion_candidates.jsonl"


@dataclass(frozen=True)
class PromotionCandidate:
    candidate_id: str
    source_cycle: str
    evidence_path: str
    recommendation: str
    required_tests: list[str]
    semantic_memory_allowed: bool = False
    faiss_write_allowed: bool = False
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_promotion_candidate(candidate: PromotionCandidate, path: Path = PROMOTION_CANDIDATES_PATH) -> None:
    if candidate.semantic_memory_allowed or candidate.faiss_write_allowed:
        raise ValueError("semantic/FAISS promotion must remain blocked in this macro-front")
    append_jsonl(path, candidate.to_dict())
