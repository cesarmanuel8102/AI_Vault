from __future__ import annotations

import json
from pathlib import Path


def audit_memory_state() -> dict[str, object]:
    journal = Path("memory/autonomous_journal.jsonl")
    queue = Path("memory/promotion_queue")
    staging = Path("memory/semantic_staging/semantic_memory_candidate.jsonl")
    audit = Path("memory/semantic/promotion_audit.jsonl")
    return {
        "journal_count": _count_jsonl(journal),
        "promotion_queue_count": len(list(queue.glob("*.json"))) if queue.exists() else 0,
        "semantic_staging_count": _count_jsonl(staging),
        "promotion_audit_count": _count_jsonl(audit),
        "canonical_promotion_performed": False,
    }


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def append_promotion_audit(record: dict[str, object], path: Path = Path("memory/semantic/promotion_audit.jsonl")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
