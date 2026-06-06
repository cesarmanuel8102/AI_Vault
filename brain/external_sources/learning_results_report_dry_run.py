"""Operator-visible learning results report - dry-run only.

Turns the external source promotion plan dry-run into concrete, reviewable
cards and a markdown report. No runtime integration or memory writes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.promotion_plan_dry_run import run_promotion_plan_dry_run


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


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _candidate_lookup(promotion_plan_output_dir: Path) -> Dict[str, Dict[str, Any]]:
    candidates_path = (
        promotion_plan_output_dir
        / "run_operator_queue"
        / "run_review_gate"
        / "run_ingestion"
        / "curated_candidates.json"
    )
    candidates = _load_json(candidates_path, [])
    return {item.get("candidate_id", ""): item for item in candidates if item.get("candidate_id")}


def _build_card(plan_item: Dict[str, Any], candidate: Dict[str, Any] | None = None) -> Dict[str, Any]:
    candidate = candidate or {}
    candidate_id = plan_item.get("candidate_id", "")
    provider = plan_item.get("provider", "")
    source_id = plan_item.get("source_id", "")
    claim = candidate.get("claim") or f"External source candidate from {provider}:{source_id}"
    text = candidate.get("text") or claim
    evidence_refs = candidate.get("evidence_refs") or [source_id] if source_id else []

    return {
        "card_id": _stable_id("learning_card", candidate_id, source_id),
        "provider": provider,
        "source_id": source_id,
        "candidate_id": candidate_id,
        "status": "ready_for_operator_review",
        "what_was_learned": claim,
        "why_it_matters": f"Creates a reviewable external knowledge candidate for {provider} with operator-gated promotion only.",
        "evidence_status": "provenance_available" if evidence_refs else "provenance_missing",
        "evidence_refs": evidence_refs,
        "source_excerpt": text[:500],
        "next_operator_action": "review_promotion_plan",
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
    }


def build_learning_result_summary(promotion_plan_result: Dict[str, Any], output_dir: str) -> Dict[str, Any]:
    promotion_plan_output_dir = Path(output_dir)
    plan = _load_json(promotion_plan_output_dir / "promotion_plan.json", [])
    queue = _load_json(promotion_plan_output_dir / "run_operator_queue" / "operator_review_queue.json", [])
    review_summary = _load_json(
        promotion_plan_output_dir / "run_operator_queue" / "run_review_gate" / "review_summary.json",
        {},
    )
    ingestion_summary = _load_json(
        promotion_plan_output_dir
        / "run_operator_queue"
        / "run_review_gate"
        / "run_ingestion"
        / "ingestion_summary.json",
        {},
    )
    candidates_by_id = _candidate_lookup(promotion_plan_output_dir)
    cards = [_build_card(item, candidates_by_id.get(item.get("candidate_id", ""))) for item in plan]

    providers = sorted({card.get("provider", "") for card in cards if card.get("provider")})
    return {
        "ok": bool(cards),
        "generated_at": now_utc(),
        "sources_seen": ingestion_summary.get("normalized_records_count", 0),
        "records_normalized": ingestion_summary.get("normalized_records_count", 0),
        "candidates_created": ingestion_summary.get("curated_candidates_count", 0),
        "candidates_approved": review_summary.get("approved_for_operator_review", len(queue)),
        "queue_items": len(queue),
        "promotion_plan_items": len(plan),
        "learning_result_cards": len(cards),
        "providers": providers,
        "cards": cards,
        "promotion_plan_result": promotion_plan_result,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
    }


def build_operator_visible_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# External Source Learning Results - Dry Run",
        "",
        "## What the operator can see now",
        f"- Sources seen: {summary['sources_seen']}",
        f"- Records normalized: {summary['records_normalized']}",
        f"- Candidates created: {summary['candidates_created']}",
        f"- Candidates approved for operator review: {summary['candidates_approved']}",
        f"- Queue items: {summary['queue_items']}",
        f"- Promotion plan items: {summary['promotion_plan_items']}",
        f"- Learning result cards: {summary['learning_result_cards']}",
        "",
        "## What learned means in this phase",
        "The system captured external-source candidates, attached provenance, passed them through review gates, and created dry-run promotion plans. It did not write memory or promote knowledge.",
        "",
        "## Still blocked",
        "- Memory writes",
        "- FAISS writes",
        "- Real writes",
        "- Runtime automatic use",
        "- Trading use",
        "- Auto-promotion",
        "",
        "## Result Cards",
    ]
    for idx, card in enumerate(summary.get("cards", []), 1):
        lines.extend(
            [
                "",
                f"### {idx}. {card['candidate_id']}",
                f"- Provider: {card['provider']}",
                f"- Source ID: {card['source_id']}",
                f"- Status: {card['status']}",
                f"- What was learned: {card['what_was_learned']}",
                f"- Why it matters: {card['why_it_matters']}",
                f"- Evidence status: {card['evidence_status']}",
                f"- Next operator action: {card['next_operator_action']}",
                "- Writes allowed: memory=false, faiss=false, real=false, promotion=false",
            ]
        )
    lines.extend(
        [
            "",
            "## Next recommended step",
            "RUNTIME-READONLY-EXTERNAL-KNOWLEDGE-RESULTS-ENDPOINT-DRY-RUN-01",
        ]
    )
    return "\n".join(lines) + "\n"


def _contains_token_marker(output_dir: Path) -> bool:
    for name in ("learning_results_summary.json", "learning_results_report.md", "learning_results_cards.json", "learning_results_cards.jsonl"):
        path = output_dir / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_TOKEN_MARKERS):
                return True
    return False


def run_learning_results_report_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/external_source_learning_results_report_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)

    promotion_output = out / "run_promotion_plan"
    promotion_result = run_promotion_plan_dry_run(str(promotion_output))
    summary = build_learning_result_summary(promotion_result, str(promotion_output))
    report = build_operator_visible_report(summary)
    cards = summary.get("cards", [])

    (out / "learning_results_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "learning_results_report.md").write_text(report, encoding="utf-8")
    (out / "learning_results_cards.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
    _write_jsonl(out / "learning_results_cards.jsonl", cards)

    token_leak = _contains_token_marker(out)
    return {
        "ok": bool(cards) and not token_leak,
        "learning_result_cards": len(cards),
        "queue_items": summary.get("queue_items", 0),
        "promotion_plan_items": summary.get("promotion_plan_items", 0),
        "sources_seen": summary.get("sources_seen", 0),
        "records_normalized": summary.get("records_normalized", 0),
        "candidates_created": summary.get("candidates_created", 0),
        "candidates_approved": summary.get("candidates_approved", 0),
        "token_leak_detected": token_leak,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "output_dir": str(out),
    }
