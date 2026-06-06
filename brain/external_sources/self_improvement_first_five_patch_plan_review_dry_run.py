"""Patch plan review dry-run for first-five self-improvement patch plans.

Reviews non-executable patch plans and creates a future candidate queue. It never
produces applicable diffs, applies patches, modifies runtime/chat, writes
memory/FAISS, promotes knowledge, or touches trading/B8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_patch_plan_dry_run import (
    run_first_five_patch_plan_dry_run,
)


TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
)

FORBIDDEN_TARGET_MARKERS = (
    "memory/semantic",
    "tmp_agent/strategies",
    "trading",
    "b8",
)
ALLOWED_PATCH_TYPES = {"test_patch", "harness_patch", "policy_patch", "documentation_patch"}
NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-DRY-RUN-01"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def load_patch_plan_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "plan_items": _read_json(out / "first_five_patch_plan_items.json", []),
        "summary": _read_json(out / "first_five_patch_plan_summary.json", {}),
        "governance": _read_json(out / "first_five_patch_plan_governance.json", {}),
        "output_dir": str(out),
    }


def _target_files(plan_item: Dict[str, Any]) -> List[str]:
    return [str(item) for item in plan_item.get("target_files_suggested", [])]


def _has_forbidden_target(plan_item: Dict[str, Any]) -> bool:
    targets = "\n".join(_target_files(plan_item)).lower().replace("\\", "/")
    return any(marker in targets for marker in FORBIDDEN_TARGET_MARKERS)


def _has_runtime_or_memory_dependency(plan_item: Dict[str, Any]) -> bool:
    targets = "\n".join(_target_files(plan_item)).lower().replace("\\", "/")
    text = json.dumps(plan_item, sort_keys=True).lower()
    return any(marker in targets for marker in ("tmp_agent/brain_v9/main.py", "session.py", "memory/semantic")) or "runtime/chat" in text


def _score_scope_clarity(plan_item: Dict[str, Any]) -> float:
    score = 0.0
    if plan_item.get("implementation_steps"):
        score += 0.35
    if plan_item.get("target_files_suggested"):
        score += 0.25
    if plan_item.get("patch_type"):
        score += 0.25
    if plan_item.get("recommended_scope") in {"small", "medium", "large"}:
        score += 0.15
    return min(score, 1.0)


def _score_safety_compliance(plan_item: Dict[str, Any]) -> float:
    score = 1.0
    for field in ("memory_write_allowed", "faiss_write_allowed", "real_write_allowed", "promotion_allowed"):
        if plan_item.get(field) is not False:
            score -= 0.20
    forbidden = plan_item.get("files_forbidden_to_modify", [])
    if not forbidden or "memory/semantic/*" not in forbidden:
        score -= 0.20
    if _has_forbidden_target(plan_item):
        score -= 0.50
    return max(round(score, 4), 0.0)


def _score_testability(plan_item: Dict[str, Any]) -> float:
    score = 0.0
    if plan_item.get("required_tests"):
        score += 0.40
    if plan_item.get("acceptance_criteria"):
        score += 0.35
    if plan_item.get("rollback_plan", {}).get("required") is True:
        score += 0.25
    return min(score, 1.0)


def _score_risk_acceptability(plan_item: Dict[str, Any]) -> float:
    risk = plan_item.get("risk_assessment", {}).get("risk_level", "medium")
    if risk == "low":
        return 1.0
    if risk == "medium":
        return 0.82
    if risk == "high":
        return 0.45
    return 0.70


def _score_implementation_readiness(plan_item: Dict[str, Any]) -> float:
    scope = plan_item.get("recommended_scope", "medium")
    score = {"small": 1.0, "medium": 0.85, "large": 0.45}.get(scope, 0.65)
    if _has_runtime_or_memory_dependency(plan_item):
        score -= 0.35
    if len(plan_item.get("target_files_suggested", [])) > 5:
        score -= 0.20
    return max(round(score, 4), 0.0)


def _weighted_score(scores: Dict[str, float]) -> float:
    return round(
        scores["scope_clarity"] * 0.20
        + scores["safety_compliance"] * 0.25
        + scores["testability"] * 0.20
        + scores["risk_acceptability"] * 0.15
        + scores["implementation_readiness"] * 0.20,
        4,
    )


def review_patch_plan_item(plan_item: Dict[str, Any]) -> Dict[str, Any]:
    scores = {
        "scope_clarity": _score_scope_clarity(plan_item),
        "safety_compliance": _score_safety_compliance(plan_item),
        "testability": _score_testability(plan_item),
        "risk_acceptability": _score_risk_acceptability(plan_item),
        "implementation_readiness": _score_implementation_readiness(plan_item),
    }
    review_score = _weighted_score(scores)
    reasons: List[str] = []
    blocking: List[str] = []
    required: List[str] = []

    missing_steps = not bool(plan_item.get("implementation_steps"))
    missing_tests = not bool(plan_item.get("required_tests"))
    missing_criteria = not bool(plan_item.get("acceptance_criteria"))
    forbidden_target = _has_forbidden_target(plan_item)
    risk_level = plan_item.get("risk_assessment", {}).get("risk_level", "medium")
    patch_type = plan_item.get("patch_type", "")
    too_many_targets = len(plan_item.get("target_files_suggested", [])) > 5
    large_scope = plan_item.get("recommended_scope") == "large"

    if missing_steps:
        blocking.append("missing_implementation_steps")
    if missing_tests:
        blocking.append("missing_required_tests")
    if missing_criteria:
        blocking.append("missing_acceptance_criteria")
    if forbidden_target:
        blocking.append("forbidden_target_file")
    if too_many_targets:
        blocking.append("too_many_target_files")

    if forbidden_target or risk_level == "high":
        decision = "reject_too_risky"
        reasons.append("Risk or target scope is too high for patch candidate promotion.")
        required.append("Reduce risk and remove forbidden/protected targets before implementation review.")
    elif missing_steps or missing_tests or missing_criteria:
        decision = "reject_not_actionable"
        reasons.append("Plan is missing implementation, test, or acceptance detail.")
        required.append("Add concrete steps, required tests, and acceptance criteria.")
    elif large_scope or too_many_targets:
        decision = "request_scope_reduction"
        reasons.append("Plan scope is too broad for safe implementation candidate status.")
        required.append("Split into smaller patch candidates with narrower file scope.")
    elif (
        review_score >= 0.80
        and scores["safety_compliance"] >= 0.95
        and scores["testability"] >= 0.75
        and patch_type in ALLOWED_PATCH_TYPES
        and not forbidden_target
    ):
        decision = "approve_for_patch_candidate"
        reasons.append("Plan is clear, testable, bounded, and dry-run safe.")
        required.append("Obtain operator approval before future patch generation dry-run.")
    elif review_score >= 0.65 and risk_level in {"medium", "high"}:
        decision = "request_more_evidence"
        reasons.append("Plan is plausible but needs stronger evidence before candidate status.")
        required.append("Add evidence references and tighter acceptance criteria.")
    else:
        decision = "reject_not_actionable"
        reasons.append("Plan is not ready enough for future patch generation.")
        required.append("Clarify scope, tests, rollback, and acceptance evidence.")

    patch_candidate_allowed = decision == "approve_for_patch_candidate"
    return {
        "review_id": _stable_id("patch_plan_review", plan_item.get("patch_plan_id", ""), decision),
        "patch_plan_id": plan_item.get("patch_plan_id", ""),
        "recommendation_id": plan_item.get("recommendation_id", ""),
        "front_id": plan_item.get("front_id", ""),
        "category": plan_item.get("category", ""),
        "severity": plan_item.get("severity", ""),
        "patch_type": patch_type,
        "review_score": review_score,
        "decision": decision,
        "scores": scores,
        "reasons": reasons,
        "blocking_issues": blocking,
        "required_before_implementation": required,
        "patch_candidate_allowed": patch_candidate_allowed,
        "execution_allowed_now": False,
        "patch_generated": False,
        "patch_applied": False,
        "operator_approval_required": True,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "required_tests": list(plan_item.get("required_tests", [])),
        "acceptance_criteria": list(plan_item.get("acceptance_criteria", [])),
        "rollback_required": bool(plan_item.get("rollback_plan", {}).get("required", True)),
        "reviewed_at": now_utc(),
    }


def review_all_patch_plan_items(plan_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [review_patch_plan_item(item) for item in plan_items]


def build_patch_candidate_queue(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue = []
    for review in reviews:
        if review.get("decision") != "approve_for_patch_candidate":
            continue
        queue.append(
            {
                "patch_candidate_id": _stable_id("patch_candidate", review.get("review_id", "")),
                "review_id": review.get("review_id", ""),
                "patch_plan_id": review.get("patch_plan_id", ""),
                "front_id": review.get("front_id", ""),
                "category": review.get("category", ""),
                "patch_type": review.get("patch_type", ""),
                "candidate_status": "approved_for_future_patch_generation",
                "execution_allowed_now": False,
                "patch_generation_allowed_now": False,
                "requires_operator_approval": True,
                "required_tests": list(review.get("required_tests", [])),
                "acceptance_criteria": list(review.get("acceptance_criteria", [])),
                "rollback_required": bool(review.get("rollback_required", True)),
                "next_safe_front": NEXT_SAFE_FRONT,
            }
        )
    return queue


def build_review_governance(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    approved = sum(1 for review in reviews if review.get("decision") == "approve_for_patch_candidate")
    return {
        "governance_id": _stable_id("patch_plan_review_governance", len(reviews), approved),
        "status": "review_only_not_executable",
        "reviews_count": len(reviews),
        "approved_candidates": approved,
        "execution_allowed_now": False,
        "patch_generation_allowed_now": False,
        "patches_generated": False,
        "patches_applied": False,
        "requires_operator_approval": True,
        "writes_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "must_preserve_dirty_preexisting_files": True,
        "must_keep_code_and_ledger_commits_separate": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_patch_plan_review(reviews: List[Dict[str, Any]], queue: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions: Dict[str, int] = {}
    for review in reviews:
        decision = review.get("decision", "unknown")
        decisions[decision] = decisions.get(decision, 0) + 1
    rejected = decisions.get("reject_too_risky", 0) + decisions.get("reject_not_actionable", 0)
    return {
        "ok": len(reviews) >= 1,
        "reviews_count": len(reviews),
        "approved_candidates": len(queue),
        "approve_for_patch_candidate": decisions.get("approve_for_patch_candidate", 0),
        "request_more_evidence": decisions.get("request_more_evidence", 0),
        "request_scope_reduction": decisions.get("request_scope_reduction", 0),
        "rejected": rejected,
        "execution_allowed_now": False,
        "patch_generation_allowed_now": False,
        "patches_generated": False,
        "patches_applied": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "next_safe_front": NEXT_SAFE_FRONT,
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(reviews: List[Dict[str, Any]], queue: List[Dict[str, Any]], governance: Dict[str, Any], summary: Dict[str, Any]) -> str:
    lines = [
        "# Revision de planes de patch - Dry Run",
        "",
        "## 1. Planes revisados",
    ]
    for review in reviews:
        lines.extend(
            [
                f"### {review['front_id']}",
                f"- Decision: {review['decision']}",
                f"- Score: {review['review_score']}",
                f"- Categoria: {review['category']}",
                f"- Tipo: {review['patch_type']}",
                "- Razones:",
            ]
        )
        for reason in review["reasons"]:
            lines.append(f"  - {reason}")
        lines.append("- Issues bloqueantes:")
        for issue in review["blocking_issues"] or ["ninguno"]:
            lines.append(f"  - {issue}")
        lines.append("- Falta antes de implementar:")
        for item in review["required_before_implementation"]:
            lines.append(f"  - {item}")
    lines.extend(["", "## 2. Candidatos aprobados"])
    if queue:
        for candidate in queue:
            lines.append(f"- {candidate['front_id']} / {candidate['patch_candidate_id']}")
    else:
        lines.append("- Ninguno")
    lines.extend(
        [
            "",
            "## 3. Governance",
            f"- status: {governance['status']}",
            f"- reviews_count: {governance['reviews_count']}",
            f"- approved_candidates: {governance['approved_candidates']}",
            f"- patch_generation_allowed_now: {governance['patch_generation_allowed_now']}",
            "",
            "## 4. Que falta antes de generar patches",
            "- Aprobacion explicita del operador.",
            "- Revision de scope, tests, rollback y preservacion de dirty state.",
            "- Un frente separado de generacion dry-run, sin aplicacion real.",
            "",
            "## 5. Que NO se genero",
            "- No se generaron diffs aplicables.",
            "- No se generaron patches ejecutables.",
            "- No se guardaron raw API bodies ni tokens.",
            "",
            "## 6. Que NO se aplico",
            "- No se aplicaron patches.",
            "- No se modificaron archivos objetivo sugeridos.",
            "- No se modifico runtime/chat.",
            "- No se escribio memory/semantic ni FAISS.",
            "- No se promovio conocimiento.",
            "- No se toco trading ni B8.",
            "",
            "## 7. Por que requiere aprobacion humana",
            "- La cola de candidatos solo autoriza una futura generacion dry-run, no ejecucion real.",
            "- Cada candidato puede afectar governance, tests o harnesses futuros.",
            "",
            "## 8. Resumen",
            f"- reviews_count: {summary['reviews_count']}",
            f"- approved_candidates: {summary['approved_candidates']}",
            f"- request_more_evidence: {summary['request_more_evidence']}",
            f"- request_scope_reduction: {summary['request_scope_reduction']}",
            f"- rejected: {summary['rejected']}",
            "",
            "## 9. Siguiente paso recomendado",
            NEXT_SAFE_FRONT,
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_patch_plan_review*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    for path in output_dir.glob("first_five_patch_candidate_queue.json"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    return False


def run_first_five_patch_plan_review_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_patch_plan_review_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    plan_dir = out / "run_patch_plan"
    plan_result = run_first_five_patch_plan_dry_run(str(plan_dir))
    artifacts = load_patch_plan_artifacts(str(plan_dir))
    plan_items = artifacts.get("plan_items", [])
    reviews = review_all_patch_plan_items(plan_items)
    queue = build_patch_candidate_queue(reviews)
    governance = build_review_governance(reviews)
    summary = summarize_patch_plan_review(reviews, queue)
    summary.update(
        {
            "plan_result": plan_result,
            "governance_status": governance["status"],
            "output_dir": str(out),
        }
    )

    (out / "first_five_patch_plan_reviews.json").write_text(json.dumps(reviews, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_patch_plan_reviews.jsonl", reviews)
    (out / "first_five_patch_candidate_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
    (out / "first_five_patch_plan_review_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_plan_review_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_plan_review_report.md").write_text(
        _render_report(reviews, queue, governance, summary), encoding="utf-8"
    )

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak and len(reviews) >= 1,
        "reviews_count": len(reviews),
        "approved_candidates": len(queue),
        "request_more_evidence": summary["request_more_evidence"],
        "request_scope_reduction": summary["request_scope_reduction"],
        "rejected": summary["rejected"],
        "governance_status": governance["status"],
        "execution_allowed_now": False,
        "patch_generation_allowed_now": False,
        "patches_generated": False,
        "patches_applied": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
        "next_safe_front": NEXT_SAFE_FRONT,
    }
