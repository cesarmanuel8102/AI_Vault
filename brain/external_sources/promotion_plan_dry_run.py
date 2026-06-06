"""Promotion plan builder for external source queue items - dry-run only.

Creates an operator-reviewable promotion plan without memory, FAISS,
runtime, real writes, trading use, or promotion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.operator_review_queue_dry_run import run_operator_review_queue_dry_run


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


def build_promotion_plan_item(queue_item: Dict[str, Any]) -> Dict[str, Any]:
    if queue_item.get("operator_status") != "pending_operator_review":
        raise ValueError("Only pending_operator_review queue items can be planned")

    queue_item_id = queue_item.get("queue_item_id", "")
    candidate_id = queue_item.get("candidate_id", "")
    provider = queue_item.get("provider", "")
    source_id = queue_item.get("source_id", "")

    return {
        "promotion_plan_item_id": _stable_id("promotion_plan", queue_item_id, candidate_id, source_id),
        "queue_item_id": queue_item_id,
        "candidate_id": candidate_id,
        "provider": provider,
        "source_id": source_id,
        "promotion_status": "planned_dry_run_only",
        "target_layer": "curated_external_knowledge",
        "promotion_decision": "eligible_for_future_operator_approval",
        "required_operator_action": "explicit_approval_required_before_any_write",
        "write_plan": {
            "memory_write_planned": False,
            "faiss_write_planned": False,
            "real_write_planned": False,
            "runtime_integration_planned": False,
        },
        "safety_checks": {
            "operator_review_required": True,
            "source_provenance_required": True,
            "token_leak_check_required": True,
            "rollback_required_before_real_write": True,
        },
        "forbidden_now": [
            "write_memory",
            "write_faiss",
            "runtime_auto_use",
            "trading_use",
            "auto_promote",
        ],
        "created_at": now_utc(),
    }


def build_promotion_plan(queue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    plan: List[Dict[str, Any]] = []
    for item in queue:
        if item.get("operator_status") == "pending_operator_review":
            plan.append(build_promotion_plan_item(item))
    return plan


def summarize_promotion_plan(plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    providers = sorted({item.get("provider", "") for item in plan if item.get("provider")})
    return {
        "ok": len(plan) > 0,
        "promotion_plan_items": len(plan),
        "eligible_for_future_operator_approval": len(plan),
        "providers": providers,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "trading_used": False,
        "b8_touched": False,
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_markdown(plan: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# External Source Promotion Plan - Dry Run",
        "",
        f"- Promotion plan items: {summary['promotion_plan_items']}",
        f"- Eligible for future operator approval: {summary['eligible_for_future_operator_approval']}",
        "- Memory write performed: false",
        "- FAISS write performed: false",
        "- Real write performed: false",
        "- Promotion performed: false",
        "- Trading used: false",
        "",
        "## Plan Items",
    ]
    for idx, item in enumerate(plan, 1):
        lines.extend(
            [
                "",
                f"### {idx}. {item['candidate_id']}",
                f"- Provider: {item['provider']}",
                f"- Source ID: {item['source_id']}",
                f"- Status: {item['promotion_status']}",
                f"- Target layer: {item['target_layer']}",
                f"- Required operator action: {item['required_operator_action']}",
                "- Writes planned now: memory=false, faiss=false, real=false, runtime=false",
                "- Forbidden now: write_memory, write_faiss, runtime_auto_use, trading_use, auto_promote",
            ]
        )
    return "\n".join(lines) + "\n"


def _contains_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("promotion_plan*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_TOKEN_MARKERS):
                return True
    return False


def run_promotion_plan_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/external_source_promotion_plan_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)

    queue_dir = out / "run_operator_queue"
    queue_result = run_operator_review_queue_dry_run(str(queue_dir))
    queue_path = queue_dir / "operator_review_queue.json"
    queue: List[Dict[str, Any]] = []
    if queue_path.exists():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))

    plan = build_promotion_plan(queue)
    summary = summarize_promotion_plan(plan)
    summary.update(
        {
            "queue_items_seen": len(queue),
            "operator_queue_result": queue_result,
            "output_dir": str(out),
        }
    )

    (out / "promotion_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    _write_jsonl(out / "promotion_plan.jsonl", plan)
    (out / "promotion_plan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "promotion_plan.md").write_text(_render_markdown(plan, summary), encoding="utf-8")

    token_leak = _contains_token_marker(out)
    return {
        "ok": bool(plan) and not token_leak,
        "promotion_plan_items": len(plan),
        "eligible_for_future_operator_approval": len(plan),
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "token_leak_detected": token_leak,
        "trading_used": False,
        "b8_touched": False,
        "output_dir": str(out),
    }
