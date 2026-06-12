from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

QUEUE_DIR = Path("memory/promotion_queue")
STAGING_PATH = Path("memory/semantic_staging/semantic_memory_candidate.jsonl")
MAX_CANONICAL_BATCH = 5
BLOCK_PATTERNS = (
    re.compile(r"<think", re.I),
    re.compile(r"chain[- ]of[- ]thought", re.I),
    re.compile(r"raw reasoning", re.I),
    re.compile(r"sk-[A-Za-z0-9]", re.I),
    re.compile(r"broker api|place order|paper trading|live trading", re.I),
)


@dataclass(frozen=True)
class SemanticPromotionCandidate:
    text: str
    source_event_id: str
    source_cycle: str
    category: str
    confidence: float
    evidence_path: str
    candidate_id: str = field(default_factory=lambda: f"sem_cand_{uuid4().hex[:12]}")
    semantic_memory_allowed: bool = False
    faiss_write_allowed: bool = False
    created_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_promotion_candidate(candidate: SemanticPromotionCandidate, confidence_threshold: float = 0.78) -> list[str]:
    reasons: list[str] = []
    if candidate.confidence < confidence_threshold:
        reasons.append("confidence_below_threshold")
    if not candidate.evidence_path:
        reasons.append("missing_evidence_path")
    if candidate.semantic_memory_allowed or candidate.faiss_write_allowed:
        reasons.append("canonical_write_flags_must_be_false_for_queue")
    payload = json.dumps(candidate.to_dict(), ensure_ascii=False)
    for pattern in BLOCK_PATTERNS:
        if pattern.search(payload):
            reasons.append(f"blocked_pattern:{pattern.pattern}")
    return reasons


def enqueue_promotion_candidate(candidate: SemanticPromotionCandidate, queue_dir: Path = QUEUE_DIR) -> dict[str, Any]:
    reasons = validate_promotion_candidate(candidate)
    if reasons:
        raise ValueError("promotion candidate rejected: " + ",".join(reasons))
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{candidate.candidate_id}.json"
    path.write_text(json.dumps(candidate.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"candidate_id": candidate.candidate_id, "queue_path": str(path)}


def write_staging_candidates(candidates: list[SemanticPromotionCandidate], staging_path: Path = STAGING_PATH) -> int:
    staging_path.parent.mkdir(parents=True, exist_ok=True)
    with staging_path.open("a", encoding="utf-8") as handle:
        for candidate in candidates:
            reasons = validate_promotion_candidate(candidate)
            if reasons:
                raise ValueError(f"candidate {candidate.candidate_id} rejected: {reasons}")
            handle.write(json.dumps(candidate.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
    return len(candidates)


def canonical_batch_allowed(candidates: list[SemanticPromotionCandidate]) -> bool:
    return len(candidates) <= MAX_CANONICAL_BATCH and all(not validate_promotion_candidate(c) for c in candidates)
