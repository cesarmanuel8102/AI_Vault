"""Utility evaluation for the first five self-improvement fronts - dry-run.

Consumes the first-five ingestion dry-run artifacts, scores each candidate
for real Brain Lab usefulness, and writes only review artifacts under the
provided output directory. No memory, FAISS, real writes, promotion, runtime,
chat, trading, or B8 integration.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_ingestion_dry_run import (
    run_first_five_learning_fronts_dry_run,
)


TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "FRED_API_KEY",
    "api_key=",
)


WEIGHTS = {
    "evidence_strength": 0.20,
    "brain_goal_alignment": 0.20,
    "implementation_actionability": 0.20,
    "measurable_impact": 0.15,
    "governance_safety_alignment": 0.15,
    "current_codebase_fit": 0.10,
}


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


def load_first_five_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "fronts": _read_json(out / "first_five_learning_fronts.json", []),
        "candidates": _read_json(out / "first_five_candidates.json", []),
        "reviews": _read_json(out / "first_five_candidate_reviews.json", []),
        "summary": _read_json(out / "first_five_summary.json", {}),
        "output_dir": str(out),
    }


def _token_leak_suspected(candidate: Dict[str, Any]) -> bool:
    text = json.dumps(candidate, sort_keys=True)
    return any(marker in text for marker in TOKEN_MARKERS)


def _write_or_promotion_requested(candidate: Dict[str, Any]) -> bool:
    return any(
        candidate.get(flag) is True
        for flag in ("promotion_allowed", "memory_write_allowed", "faiss_write_allowed", "real_write_allowed")
    )


def _score_evidence_strength(candidate: Dict[str, Any]) -> float:
    provenance = candidate.get("provenance_bundle") or {}
    evidence_refs = candidate.get("evidence_refs") or []
    score = 0.0
    if provenance:
        score += 0.18
    if evidence_refs:
        score += 0.18
    if provenance.get("content_hash"):
        score += 0.26
    if provenance.get("http_status") == 200:
        score += 0.14
    if provenance.get("url_redacted"):
        score += 0.14
    if candidate.get("provider") != "unknown":
        score += 0.10
    if "local_reference_metadata_only" in candidate.get("warnings", []):
        score -= 0.08
    return round(max(0.0, min(score, 1.0)), 4)


def _score_brain_goal_alignment(candidate: Dict[str, Any]) -> float:
    front_id = candidate.get("front_id", "")
    text = " ".join(
        [
            front_id,
            candidate.get("why_relevant_to_brain", ""),
            candidate.get("how_brain_could_apply_it", ""),
            candidate.get("what_brain_should_learn", ""),
        ]
    ).lower()
    anchors = (
        "brain",
        "self-improvement",
        "planner",
        "executor",
        "evaluator",
        "memory",
        "governance",
        "tools",
        "quality",
        "security",
        "patch",
    )
    hits = sum(1 for anchor in anchors if anchor in text)
    base = float(candidate.get("front_fit_score", 0.0))
    return round(max(0.0, min(max(base, 0.60 + hits * 0.04), 1.0)), 4)


def _score_implementation_actionability(candidate: Dict[str, Any]) -> float:
    text = " ".join(
        [
            candidate.get("how_brain_could_apply_it", ""),
            candidate.get("what_brain_should_learn", ""),
            candidate.get("title", ""),
        ]
    ).lower()
    anchors = ("patch", "test", "benchmark", "policy", "gate", "workflow", "architecture", "validation")
    hits = sum(1 for anchor in anchors if anchor in text)
    base = 0.62 + hits * 0.06
    if candidate.get("source_type") in {"benchmark", "security_guideline", "github_repo"}:
        base += 0.08
    if candidate.get("source_type") == "paper":
        base += 0.04
    return round(max(0.0, min(base, 1.0)), 4)


def _score_measurable_impact(candidate: Dict[str, Any]) -> float:
    front_id = candidate.get("front_id", "")
    source_type = candidate.get("source_type", "")
    base = 0.72
    if "EVALUATION" in front_id or source_type == "benchmark":
        base = 0.94
    elif "SECURITY" in front_id:
        base = 0.88
    elif "AUTO_CODING" in front_id:
        base = 0.84
    elif "MEMORY_RAG" in front_id:
        base = 0.78
    return round(base, 4)


def _score_governance_safety_alignment(candidate: Dict[str, Any]) -> float:
    if _write_or_promotion_requested(candidate):
        return 0.0
    warnings = candidate.get("warnings", [])
    score = 0.80
    if "dry_run_only" in warnings:
        score += 0.08
    if "not_promoted_to_memory" in warnings:
        score += 0.04
    if candidate.get("promotion_allowed") is False:
        score += 0.04
    if candidate.get("memory_write_allowed") is False and candidate.get("faiss_write_allowed") is False:
        score += 0.04
    return round(max(0.0, min(score, 1.0)), 4)


def _score_current_codebase_fit(candidate: Dict[str, Any]) -> float:
    front_id = candidate.get("front_id", "")
    base = 0.82
    if front_id in {"SECURITY_SANDBOXING_SUPPLY_CHAIN", "EVALUATION_BENCHMARKS_QUALITY_GATES"}:
        base = 0.90
    elif front_id == "AUTO_CODING_AGENTS_PATCH_GENERATION":
        base = 0.86
    elif front_id == "MEMORY_RAG_KNOWLEDGE_STRUCTURE":
        base = 0.84
    return round(base, 4)


def _weighted_score(scores: Dict[str, float]) -> float:
    return round(sum(scores[key] * WEIGHTS[key] for key in WEIGHTS), 4)


def _recommended_policy(candidate: Dict[str, Any]) -> str:
    front_id = candidate.get("front_id", "")
    mapping = {
        "MULTI_AGENT_SYSTEMS_ORCHESTRATION": "Design planner/executor/evaluator routing contract with evaluator veto before promotion.",
        "EVALUATION_BENCHMARKS_QUALITY_GATES": "Add before/after regression gate and smoke benchmark before self-improvement promotion.",
        "MEMORY_RAG_KNOWLEDGE_STRUCTURE": "Define provenance-first curated knowledge schema and retrieval precision checks.",
        "SECURITY_SANDBOXING_SUPPLY_CHAIN": "Add policy checks for filesystem guardrails, token hygiene, dependency risk, and operator approval.",
        "AUTO_CODING_AGENTS_PATCH_GENERATION": "Require patch plan, scoped diff review, rollback note, and tests before commit.",
    }
    return mapping.get(front_id, "Create dry-run policy patch before any real promotion.")


def _recommended_metric(candidate: Dict[str, Any]) -> str:
    front_id = candidate.get("front_id", "")
    mapping = {
        "MULTI_AGENT_SYSTEMS_ORCHESTRATION": "task_success_rate_with_evaluator_veto_and_tool_policy_violations",
        "EVALUATION_BENCHMARKS_QUALITY_GATES": "before_after_pass_rate_regression_count_and_quality_delta",
        "MEMORY_RAG_KNOWLEDGE_STRUCTURE": "retrieval_precision_provenance_coverage_and_duplicate_rate",
        "SECURITY_SANDBOXING_SUPPLY_CHAIN": "blocked_unsafe_actions_token_leak_findings_and_policy_bypass_rate",
        "AUTO_CODING_AGENTS_PATCH_GENERATION": "patch_success_rate_test_pass_rate_scope_violations_and_rollback_readiness",
    }
    return mapping.get(front_id, "utility_score_before_after_delta")


def evaluate_candidate_utility(candidate: Dict[str, Any], review: Dict[str, Any] | None = None) -> Dict[str, Any]:
    review = review or {}
    base = {
        "evaluation_id": _stable_id("utility_eval", candidate.get("candidate_id", ""), candidate.get("front_id", "")),
        "candidate_id": candidate.get("candidate_id", ""),
        "front_id": candidate.get("front_id", ""),
        "title": candidate.get("title", ""),
        "utility_score": 0.0,
        "decision": "",
        "scores": {
            "evidence_strength": 0.0,
            "brain_goal_alignment": 0.0,
            "implementation_actionability": 0.0,
            "measurable_impact": 0.0,
            "governance_safety_alignment": 0.0,
            "current_codebase_fit": 0.0,
        },
        "what_brain_learned": candidate.get("what_brain_should_learn", ""),
        "how_brain_can_apply_it": candidate.get("how_brain_could_apply_it", ""),
        "recommended_patch_or_policy": _recommended_policy(candidate),
        "recommended_metric": _recommended_metric(candidate),
        "recommended_next_validation": "live_source_validation_dry_run",
        "requires_live_source_validation": True,
        "requires_benchmark": False,
        "promotion_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "evaluated_at": now_utc(),
    }

    if _write_or_promotion_requested(candidate) or "dry_run_only" not in candidate.get("warnings", []) or _token_leak_suspected(candidate):
        base["decision"] = "reject_policy_or_safety"
        base["recommended_next_validation"] = "reject"
        base["requires_live_source_validation"] = False
        return base

    scores = {
        "evidence_strength": _score_evidence_strength(candidate),
        "brain_goal_alignment": _score_brain_goal_alignment(candidate),
        "implementation_actionability": _score_implementation_actionability(candidate),
        "measurable_impact": _score_measurable_impact(candidate),
        "governance_safety_alignment": _score_governance_safety_alignment(candidate),
        "current_codebase_fit": _score_current_codebase_fit(candidate),
    }
    utility_score = _weighted_score(scores)
    base["scores"] = scores
    base["utility_score"] = utility_score

    offline_catalog = "local_reference_metadata_only" in candidate.get("warnings", [])
    if utility_score < 0.55:
        decision = "reject_low_utility"
        next_validation = "reject"
    elif scores["implementation_actionability"] < 0.60:
        decision = "not_actionable_yet"
        next_validation = "policy_patch_dry_run"
    elif utility_score >= 0.70 and scores["evidence_strength"] < 0.70 and offline_catalog:
        decision = "useful_but_needs_live_evidence"
        next_validation = "live_source_validation_dry_run"
    elif utility_score >= 0.70 and scores["measurable_impact"] < 0.70:
        decision = "useful_but_needs_benchmark"
        next_validation = "benchmark_design_dry_run"
    elif (
        utility_score >= 0.80
        and scores["evidence_strength"] >= 0.70
        and scores["implementation_actionability"] >= 0.75
        and scores["governance_safety_alignment"] >= 0.80
    ):
        decision = "ready_for_live_source_validation"
        next_validation = "live_source_validation_dry_run"
    else:
        decision = "not_actionable_yet"
        next_validation = "policy_patch_dry_run"

    base["decision"] = decision
    base["recommended_next_validation"] = next_validation
    base["requires_live_source_validation"] = decision in {
        "ready_for_live_source_validation",
        "useful_but_needs_live_evidence",
    }
    base["requires_benchmark"] = decision == "useful_but_needs_benchmark"
    if review.get("decision") == "reject_policy_or_safety":
        base["decision"] = "reject_policy_or_safety"
        base["recommended_next_validation"] = "reject"
    return base


def evaluate_all_first_five_utilities(candidates: List[Dict[str, Any]], reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reviews_by_candidate = {review.get("candidate_id", ""): review for review in reviews}
    return [
        evaluate_candidate_utility(candidate, reviews_by_candidate.get(candidate.get("candidate_id", "")))
        for candidate in candidates
    ]


def summarize_utility_evaluation(evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions: Dict[str, int] = {}
    for evaluation in evaluations:
        decision = evaluation.get("decision", "unknown")
        decisions[decision] = decisions.get(decision, 0) + 1
    return {
        "ok": len(evaluations) > 0,
        "candidates_evaluated": len(evaluations),
        "utility_evaluations": len(evaluations),
        "ready_for_live_source_validation": decisions.get("ready_for_live_source_validation", 0),
        "useful_but_needs_live_evidence": decisions.get("useful_but_needs_live_evidence", 0),
        "useful_but_needs_benchmark": decisions.get("useful_but_needs_benchmark", 0),
        "not_actionable_yet": decisions.get("not_actionable_yet", 0),
        "rejected": decisions.get("reject_low_utility", 0) + decisions.get("reject_policy_or_safety", 0),
        "decisions": decisions,
        "live_source_validation_required": sum(1 for item in evaluations if item.get("requires_live_source_validation")),
        "benchmark_required": sum(1 for item in evaluations if item.get("requires_benchmark")),
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "timestamp": now_utc(),
    }


def build_actionability_matrix(evaluations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matrix = []
    for evaluation in evaluations:
        decision = evaluation.get("decision", "")
        if decision in {"ready_for_live_source_validation", "useful_but_needs_live_evidence"}:
            safe_next_step = "live_source_validation_dry_run"
        elif decision == "useful_but_needs_benchmark":
            safe_next_step = "benchmark_design_dry_run"
        elif decision == "not_actionable_yet":
            safe_next_step = "policy_patch_dry_run"
        else:
            safe_next_step = "reject"
        matrix.append(
            {
                "front_id": evaluation.get("front_id", ""),
                "candidate_id": evaluation.get("candidate_id", ""),
                "utility_score": evaluation.get("utility_score", 0.0),
                "decision": decision,
                "next_action": evaluation.get("recommended_next_validation", ""),
                "possible_brain_improvement": evaluation.get("recommended_patch_or_policy", ""),
                "test_or_metric": evaluation.get("recommended_metric", ""),
                "risk_if_applied": "Could contaminate governance or memory if promoted without live evidence and benchmark gates.",
                "safe_next_step": safe_next_step,
            }
        )
    return matrix


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(evaluations: List[Dict[str, Any]], matrix: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# Evaluacion de utilidad de los primeros 5 frentes de automejora - Dry Run",
        "",
        "## 1. Que se evaluo",
        "Se evaluaron los 5 candidatos generados por el dry-run offline de frentes canonicos de automejora.",
        "",
        "## 2. Que aprendio Brain por frente",
    ]
    for evaluation in evaluations:
        lines.extend(
            [
                f"- **{evaluation['front_id']}**",
                f"  - Utilidad: {evaluation['utility_score']}",
                f"  - Decision: {evaluation['decision']}",
                f"  - Aprendizaje: {evaluation['what_brain_learned']}",
                f"  - Aplicacion: {evaluation['how_brain_can_apply_it']}",
            ]
        )
    lines.extend(
        [
            "",
            "## 3. Que tan util parece",
            f"- Ready for live source validation: {summary['ready_for_live_source_validation']}",
            f"- Useful but needs live evidence: {summary['useful_but_needs_live_evidence']}",
            f"- Useful but needs benchmark: {summary['useful_but_needs_benchmark']}",
            f"- Rejected: {summary['rejected']}",
            "",
            "## 4. Que falta para validar utilidad real",
            "- Validar fuentes vivas sin guardar raw bodies.",
            "- Disenar benchmarks/smokes before-after por frente.",
            "- Mantener operator gate antes de cualquier promotion.",
            "",
            "## 5. Patch, politica o test derivable",
        ]
    )
    for row in matrix:
        lines.append(f"- {row['front_id']}: {row['possible_brain_improvement']} Metric: {row['test_or_metric']}")
    lines.extend(
        [
            "",
            "## 6. Candidatos para live source validation",
            f"- Total: {summary['live_source_validation_required']}",
            "",
            "## 7. Candidatos que necesitan benchmark",
            f"- Total: {summary['benchmark_required']}",
            "",
            "## 8. Que sigue",
            "SELF-IMPROVEMENT-FIRST-FIVE-LIVE-SOURCE-VALIDATION-DRY-RUN-01",
            "",
            "## 9. Que NO se escribio todavia",
            "- No memory/semantic",
            "- No FAISS",
            "- No real write",
            "- No promotion",
            "- No runtime/chat integration",
            "- No trading/B8",
        ]
    )
    return "\n".join(lines) + "\n"


def _contains_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_utility*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    for path in output_dir.glob("first_five_actionability*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    return False


def run_first_five_utility_evaluation_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_utility_evaluation_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    ingestion_dir = out / "run_first_five_ingestion"
    ingestion_result = run_first_five_learning_fronts_dry_run(str(ingestion_dir))
    artifacts = load_first_five_artifacts(str(ingestion_dir))
    candidates = artifacts.get("candidates", [])
    reviews = artifacts.get("reviews", [])
    evaluations = evaluate_all_first_five_utilities(candidates, reviews)
    matrix = build_actionability_matrix(evaluations)
    summary = summarize_utility_evaluation(evaluations)
    summary.update(
        {
            "ingestion_result": ingestion_result,
            "actionability_matrix_rows": len(matrix),
            "output_dir": str(out),
        }
    )

    (out / "first_five_utility_evaluations.json").write_text(json.dumps(evaluations, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_utility_evaluations.jsonl", evaluations)
    (out / "first_five_actionability_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    (out / "first_five_utility_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "first_five_utility_report.md").write_text(_render_report(evaluations, matrix, summary), encoding="utf-8")

    token_leak = _contains_token_marker(out)
    return {
        "ok": not token_leak and len(evaluations) == 5 and len(matrix) == 5,
        "candidates_evaluated": len(evaluations),
        "utility_evaluations": len(evaluations),
        "actionability_matrix_rows": len(matrix),
        "ready_for_live_source_validation": summary["ready_for_live_source_validation"],
        "useful_but_needs_live_evidence": summary["useful_but_needs_live_evidence"],
        "useful_but_needs_benchmark": summary["useful_but_needs_benchmark"],
        "rejected": summary["rejected"],
        "live_source_validation_required": summary["live_source_validation_required"],
        "benchmark_required": summary["benchmark_required"],
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
    }
