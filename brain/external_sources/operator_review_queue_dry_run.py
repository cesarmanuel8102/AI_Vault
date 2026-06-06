"""Operator review queue for external source candidates - dry-run only.

Builds a visible queue from candidate review gate results without memory,
FAISS, real writes, or promotion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.candidate_review_gate_dry_run import run_candidate_review_gate_dry_run


FORBIDDEN_TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "FRED_API_KEY",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def build_operator_queue_item(review_result: Dict[str, Any]) -> Dict[str, Any]:
    if review_result.get("decision") != "approved_for_operator_review":
        raise ValueError("Only approved_for_operator_review results can become queue items")

    provider = review_result.get("provider", "")
    source_id = review_result.get("source_id", "")
    candidate_id = review_result.get("candidate_id", "")
    reviewed_at = review_result.get("reviewed_at") or now_utc()

    return {
        "queue_item_id": _stable_id("operator_queue", candidate_id, provider, source_id),
        "candidate_id": candidate_id,
        "provider": provider,
        "source_id": source_id,
        "decision": "approved_for_operator_review",
        "review_score": float(review_result.get("review_score", 0.0) or 0.0),
        "operator_status": "pending_operator_review",
        "recommended_operator_action": "review_evidence_and_decide_promotion_plan",
        "reasons": list(review_result.get("reasons", [])),
        "blocking_issues": list(review_result.get("blocking_issues", [])),
        "evidence_summary": {
            "provider": provider,
            "source_id": source_id,
            "reviewed_at": reviewed_at,
            "provenance_present": True,
        },
        "safety_flags": {
            "promotion_allowed": False,
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
        },
        "allowed_actions": [
            "approve_for_promotion_dry_run",
            "request_more_evidence",
            "reject_candidate",
        ],
        "forbidden_actions": [
            "write_memory",
            "write_faiss",
            "real_write",
            "auto_promote",
        ],
        "created_at": now_utc(),
    }


def build_operator_review_queue(review_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    for result in review_results:
        if result.get("decision") == "approved_for_operator_review":
            queue.append(build_operator_queue_item(result))
    return queue


def summarize_operator_review_queue(queue: List[Dict[str, Any]]) -> Dict[str, Any]:
    providers = sorted({item.get("provider", "") for item in queue if item.get("provider")})
    return {
        "ok": len(queue) > 0,
        "queue_items": len(queue),
        "operator_status": "pending_operator_review",
        "providers": providers,
        "promotion_allowed": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_markdown(queue: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# External Source Operator Review Queue - Dry Run",
        "",
        f"- Queue items: {summary['queue_items']}",
        "- Operator status: pending_operator_review",
        "- Memory write performed: false",
        "- FAISS write performed: false",
        "- Real write performed: false",
        "- Promotion performed: false",
        "",
        "## Items",
    ]
    for idx, item in enumerate(queue, 1):
        lines.extend(
            [
                "",
                f"### {idx}. {item['candidate_id']}",
                f"- Provider: {item['provider']}",
                f"- Source ID: {item['source_id']}",
                f"- Review score: {item['review_score']}",
                f"- Operator status: {item['operator_status']}",
                f"- Recommended action: {item['recommended_operator_action']}",
                f"- Reasons: {', '.join(item['reasons']) if item['reasons'] else 'none'}",
                "- Forbidden now: write_memory, write_faiss, real_write, auto_promote",
            ]
        )
    return "\n".join(lines) + "\n"


def _contains_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("operator_review_queue*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_TOKEN_MARKERS):
                return True
    return False


def run_operator_review_queue_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/external_source_operator_review_queue_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)

    review_gate_dir = out / "run_review_gate"
    review_summary = run_candidate_review_gate_dry_run(str(review_gate_dir))
    review_results_path = review_gate_dir / "review_results.json"
    review_results: List[Dict[str, Any]] = []
    if review_results_path.exists():
        review_results = json.loads(review_results_path.read_text(encoding="utf-8"))

    queue = build_operator_review_queue(review_results)
    approved_seen = sum(1 for item in review_results if item.get("decision") == "approved_for_operator_review")
    rejected_or_deferred = len(review_results) - approved_seen
    summary = summarize_operator_review_queue(queue)
    summary.update(
        {
            "approved_candidates_seen": approved_seen,
            "rejected_or_deferred_excluded": rejected_or_deferred,
            "review_gate_summary": review_summary,
            "output_dir": str(out),
        }
    )

    (out / "operator_review_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
    _write_jsonl(out / "operator_review_queue.jsonl", queue)
    (out / "operator_review_queue_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "operator_review_queue.md").write_text(_render_markdown(queue, summary), encoding="utf-8")

    token_leak = _contains_token_marker(out)
    return {
        "ok": bool(queue) and not token_leak,
        "queue_items": len(queue),
        "approved_candidates_seen": approved_seen,
        "rejected_or_deferred_excluded": rejected_or_deferred,
        "operator_status": "pending_operator_review",
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
    }
