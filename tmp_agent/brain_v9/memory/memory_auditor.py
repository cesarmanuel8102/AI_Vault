from __future__ import annotations

import json
from pathlib import Path


def audit_memory_state() -> dict[str, object]:
    journal = Path("memory/autonomous_journal.jsonl")
    queue = Path("memory/promotion_queue")
    staging = Path("memory/semantic_staging/semantic_memory_candidate.jsonl")
    audit = Path("memory/semantic/promotion_audit.jsonl")
    queue_metrics = _promotion_queue_metrics(queue)
    return {
        "journal_count": _count_jsonl(journal),
        "promotion_queue_count": queue_metrics["raw_file_count"],
        "promotion_queue_active_review_required_count": queue_metrics["active_review_required_count"],
        "promotion_queue_resolved_count": queue_metrics["resolved_count"],
        "promotion_queue_terminal_status_counts": queue_metrics["terminal_status_counts"],
        "semantic_staging_count": _count_jsonl(staging),
        "promotion_audit_count": _count_jsonl(audit),
        "canonical_promotion_performed": False,
    }


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _promotion_queue_metrics(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "raw_file_count": 0,
            "active_review_required_count": 0,
            "resolved_count": 0,
            "terminal_status_counts": {},
        }

    raw_files = list(path.glob("*.json"))
    active_review_required = 0
    resolved_count = 0
    terminal_status_counts: dict[str, int] = {}
    for item in raw_files:
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            terminal_status_counts["parse_error"] = terminal_status_counts.get("parse_error", 0) + 1
            continue
        if data.get("review_required") is True:
            active_review_required += 1
        if data.get("resolved_utc"):
            resolved_count += 1
        terminal_status = str(data.get("terminal_status") or "<missing>")
        terminal_status_counts[terminal_status] = terminal_status_counts.get(terminal_status, 0) + 1
    return {
        "raw_file_count": len(raw_files),
        "active_review_required_count": active_review_required,
        "resolved_count": resolved_count,
        "terminal_status_counts": terminal_status_counts,
    }


def append_promotion_audit(record: dict[str, object], path: Path = Path("memory/semantic/promotion_audit.jsonl")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
