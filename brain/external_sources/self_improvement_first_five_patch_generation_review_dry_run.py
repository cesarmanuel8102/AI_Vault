"""Patch generation review dry-run for first five self-improvement fronts.

Revises synthetic patch proposals from the previous front and decides which
ones qualify for real patch planning without applying, modifying, promoting,
or writing any persistent state.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_patch_generation_dry_run import (
    run_first_five_patch_generation_dry_run,
    TOKEN_MARKERS,
    FORBIDDEN_FILES,
    NEXT_SAFE_FRONT,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def load_patch_generation_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    proposals = _read_json(out / "first_five_patch_generation_proposals.json", [])
    summary = _read_json(out / "first_five_patch_generation_summary.json", {})
    packet = _read_json(out / "first_five_patch_generation_operator_review_packet.json", {})
    pseudo_dir = out / "pseudo_diffs"
    pseudo_diffs = {}
    if pseudo_dir.exists():
        for p in pseudo_dir.iterdir():
            if p.is_file() and p.suffix == ".txt":
                try:
                    pseudo_diffs[p.stem] = p.read_text(encoding="utf-8")
                except OSError:
                    continue
    return {
        "proposals": proposals,
        "summary": summary,
        "packet": packet,
        "pseudo_diffs": pseudo_diffs,
        "output_dir": str(out),
    }


def _contains_forbidden_pseudo_markers(text: Optional[str]) -> List[str]:
    issues = []
    if not text:
        return issues
    if "diff --git" in text:
        issues.append("contains 'diff --git'")
    if "+++ b/" in text:
        issues.append("contains '+++ b/'")
    if "--- a/" in text:
        issues.append("contains '--- a/'")
    return issues


def _score_pseudo_diff_safety(proposal: Dict[str, Any], pseudo_diff_text: Optional[str] = None) -> float:
    # proposal flags
    if proposal.get("pseudo_diff_is_applicable") is True:
        return round(0.0, 4)
    if proposal.get("pseudo_diff_generated") is not True:
        return round(0.0, 4)
    if pseudo_diff_text is not None:
        forbidden = _contains_forbidden_pseudo_markers(pseudo_diff_text)
        if forbidden:
            return round(0.0, 4)
    return round(1.0, 4)


def _score_safety_flags(proposal: Dict[str, Any]) -> float:
    flags = [
        proposal.get("patch_applied", True) is False,
        proposal.get("patch_staged", True) is False,
        proposal.get("memory_write_allowed", True) is False,
        proposal.get("faiss_write_allowed", True) is False,
        proposal.get("real_write_allowed", True) is False,
        proposal.get("promotion_allowed", True) is False,
    ]
    if all(flags):
        return round(1.0, 4)
    return round(0.0, 4)


def _score_scope_fit(proposal: Dict[str, Any]) -> float:
    targets = proposal.get("target_files_suggested", [])
    if not targets:
        return round(1.0, 4)
    # dry-run patches target only allowed paths; treat forbidden patterns as scope violations
    out_of_scope = 0
    total = len(targets)
    for t in targets:
        # Use fnmatch for glob-style matching
        for pattern in FORBIDDEN_FILES:
            if fnmatch.fnmatch(t, pattern) or t.startswith(pattern.rstrip("/*")):
                out_of_scope += 1
                break
    score = max(0.0, 1.0 - (out_of_scope / total))
    return round(score, 4)


def _score_review_readiness(proposal: Dict[str, Any]) -> float:
    if proposal.get("operator_review_required") is not True:
        return round(0.0, 4)
    if proposal.get("proposal_status") != "dry_run_patch_proposal_only":
        return round(0.0, 4)
    risk = proposal.get("risk_level")
    memo = proposal.get("risk_notes", "").strip()
    if not risk or not memo:
        return round(0.5, 4)
    return round(1.0, 4)


def _score_proposal_completeness(proposal: Dict[str, Any]) -> float:
    points = 0.0
    total = 4.0
    if proposal.get("target_files_suggested", []):
        points += 1.0
    if proposal.get("required_tests", []):
        points += 1.0
    if proposal.get("acceptance_criteria", []):
        points += 1.0
    if proposal.get("rollback_instructions", []):
        points += 1.0
    return round(points / total, 4)


def review_patch_proposal(
    proposal: Dict[str, Any],
    pseudo_diff_text: Optional[str] = None,
) -> Dict[str, Any]:
    review_id = _stable_id("generation_review", proposal.get("patch_proposal_id", ""))
    scores = {
        "proposal_completeness": _score_proposal_completeness(proposal),
        "pseudo_diff_safety": _score_pseudo_diff_safety(proposal, pseudo_diff_text),
        "safety_flags": _score_safety_flags(proposal),
        "scope_fit": _score_scope_fit(proposal),
        "review_readiness": _score_review_readiness(proposal),
    }
    review_score_raw = (
        scores["proposal_completeness"] * 0.20
        + scores["pseudo_diff_safety"] * 0.25
        + scores["safety_flags"] * 0.25
        + scores["scope_fit"] * 0.15
        + scores["review_readiness"] * 0.15
    )
    review_score = round(review_score_raw, 4)

    reasons = []
    blocking = []
    required = []
    decision = ""
    approved = False

    # Immediate rejections
    safety_val = scores["safety_flags"]
    pseudo_val = scores["pseudo_diff_safety"]
    scope_val = scores["scope_fit"]

    if safety_val < 1.0:
        reasons.append("rejected: safety flags not all True (patch_applied/patch_staged/write/promotion)")
        decision = "reject"
        approved = False

    if pseudo_val < 1.0:
        reasons.append("rejected: pseudo-diff safety failed (applicable markers or executable diff fragments)")
        decision = "reject"
        approved = False

    if scope_val < 0.95:
        reasons.append("rejected: scope fit below 0.95 (targets forbidden files or out-of-scope)")
        if not decision:
            decision = "reject"
        approved = False

    # If not already rejected, proceed to scoring gates
    if not decision:
        if not proposal.get("required_tests", []):
            reasons.append("request_more_tests: required_tests empty")
            decision = "request_more_tests"
            approved = False
        elif scores["proposal_completeness"] < 0.75:
            reasons.append("request_more_tests: proposal_completeness < 0.75")
            decision = "request_more_tests"
            approved = False
        elif review_score >= 0.85 and pseudo_val == 1.0 and safety_val == 1.0 and scope_val >= 0.95:
            decision = "approve_for_real_patch_planning"
            approved = True
        elif review_score >= 0.70 and review_score < 0.85:
            reasons.append("request_more_evidence: review_score between 0.70 and 0.85")
            decision = "request_more_evidence"
            approved = False
        else:
            reasons.append("reject: review_score below thresholds")
            decision = "reject"
            approved = False

    # Build required items if approved
    if approved:
        if scores["proposal_completeness"] < 1.0:
            required.append("complete_proposal_before_planning")
        if scores["review_readiness"] < 1.0:
            required.append("provide_risk_notes_and_operator_review_requirement")

    # Build blocking issues list
    for k, v in scores.items():
        if v < 1.0:
            blocking.append(f"{k}={v}")

    return {
        "generation_review_id": review_id,
        "patch_proposal_id": proposal.get("patch_proposal_id", ""),
        "patch_candidate_id": proposal.get("patch_candidate_id", ""),
        "front_id": proposal.get("front_id", ""),
        "category": proposal.get("category", ""),
        "patch_type": proposal.get("patch_type", ""),
        "review_score": review_score,
        "decision": decision,
        "scores": scores,
        "reasons": reasons,
        "blocking_issues": blocking,
        "required_before_real_patch_planning": required,
        "approved_for_real_patch_planning": approved,
        "execution_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "operator_approval_required": True,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "reviewed_at": now_utc(),
    }


def review_all_patch_proposals(
    proposals: List[Dict[str, Any]],
    pseudo_diffs: Dict[str, str],
) -> List[Dict[str, Any]]:
    return [review_patch_proposal(p, pseudo_diffs.get(p.get("patch_proposal_id", ""), None)) for p in proposals]


def build_real_patch_planning_queue(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    approved = [r for r in reviews if r.get("approved_for_real_patch_planning") is True]
    queue = []
    for r in approved:
        queue.append({
            "real_patch_planning_candidate_id": _stable_id(
                "real_patch_planning", r["generation_review_id"], r["patch_proposal_id"]
            ),
            "generation_review_id": r["generation_review_id"],
            "patch_proposal_id": r["patch_proposal_id"],
            "front_id": r["front_id"],
            "category": r["category"],
            "patch_type": r["patch_type"],
            "candidate_status": "approved_for_real_patch_planning",
            "review_score": r["review_score"],
            "execution_allowed_now": False,
            "real_patch_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "requires_operator_approval": True,
            "required_tests": r.get("required_tests", ["python -m pytest tests/smoke -q"]),
            "acceptance_criteria": r.get("acceptance_criteria", []),
            "target_files_suggested": r.get("target_files_suggested", []),
            "risk_level": r.get("risk_level", "medium"),
            "risk_notes": r.get("risk_notes", ""),
            "rollback_required": True,
            "next_safe_front": "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-DRY-RUN-01",
        })
    return queue


def build_generation_review_governance(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    approved = [r for r in reviews if r.get("approved_for_real_patch_planning") is True]
    return {
        "governance_id": _stable_id("generation_review_governance", len(reviews)),
        "status": "generation_review_only_not_executable",
        "reviews_count": len(reviews),
        "approved_for_real_patch_planning": len(approved),
        "execution_allowed_now": False,
        "real_patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
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


def summarize_generation_review(
    reviews: List[Dict[str, Any]],
    queue: List[Dict[str, Any]],
) -> Dict[str, Any]:
    decisions = {}
    for r in reviews:
        d = r["decision"]
        decisions[d] = decisions.get(d, 0) + 1
    return {
        "ok": len(reviews) > 0,
        "reviews_count": len(reviews),
        "approved_for_real_patch_planning": decisions.get("approve_for_real_patch_planning", 0),
        "request_scope_reduction": decisions.get("request_scope_reduction", 0),
        "request_more_tests": decisions.get("request_more_tests", 0),
        "request_more_evidence": decisions.get("request_more_evidence", 0),
        "rejected": decisions.get("reject", 0),
        "real_patch_planning_queue_count": len(queue),
        "execution_allowed_now": False,
        "real_patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "timestamp": now_utc(),
    }


def _check_token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def run_first_five_patch_generation_review_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    generation_out = str(out / "run_patch_generation") if out else None
    gen_result = run_first_five_patch_generation_dry_run(output_dir=generation_out)
    artifacts = load_patch_generation_artifacts(generation_out or gen_result.get("output_dir", "tmp_agent/run"))
    reviews = review_all_patch_proposals(
        artifacts["proposals"], artifacts["pseudo_diffs"]
    )
    queue = build_real_patch_planning_queue(reviews)
    governance = build_generation_review_governance(reviews)
    summary = summarize_generation_review(reviews, queue)

    token_leak = False
    if out is not None:
        # Write outputs
        (out / "first_five_patch_generation_reviews.json").write_text(
            json.dumps(reviews, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_patch_generation_reviews.jsonl", "w", encoding="utf-8") as fh:
            for r in reviews:
                fh.write(json.dumps(r) + "\n")
        (out / "first_five_real_patch_planning_queue.json").write_text(
            json.dumps(queue, indent=2), encoding="utf-8"
        )
        (out / "first_five_patch_generation_review_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_patch_generation_review_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(reviews, queue, governance, summary)
        (out / "first_five_patch_generation_review_report.md").write_text(
            report, encoding="utf-8"
        )
        # Token leak
        all_texts = [json.dumps(reviews), json.dumps(queue), json.dumps(governance), json.dumps(summary), report]
        for text in all_texts:
            if _check_token_leak(text):
                token_leak = True
                summary["token_leak_detected"] = True
                break
        summary["token_leak_detected"] = token_leak
    summary["token_leak_detected"] = token_leak
    summary["output_dir"] = str(out) if out else None
    return summary


def _build_report_md(
    reviews: List[Dict[str, Any]],
    queue: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Reporte de Revision de Propuestas de Patch (Dry-Run)",
        "",
        "## Resumen",
        f"- Propuestas revisadas: {summary.get('reviews_count', 0)}",
        f"- Aprobadas para planificacion real: {summary.get('approved_for_real_patch_planning', 0)}",
        f"- Rechazadas: {summary.get('rejected', 0)}",
        f"- Solicitar mas tests: {summary.get('request_more_tests', 0)}",
        f"- Solicitar mas evidencia: {summary.get('request_more_evidence', 0)}",
        f"- Solicitar reduccion de scope: {summary.get('request_scope_reduction', 0)}",
        f"- Cola de planificacion real: {summary.get('real_patch_planning_queue_count', 0)}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Propuestas Revisadas",
    ]
    for r in reviews:
        lines.append(f"### {r['patch_proposal_id']}")
        lines.append(f"- Decision: {r['decision']}")
        lines.append(f"- Score: {r['review_score']}")
        if r["reasons"]:
            lines.append(f"- Razones: {', '.join(r['reasons'])}")
        if r["blocking_issues"]:
            lines.append(f"- Issues bloqueantes: {', '.join(r['blocking_issues'])}")
        lines.append("")
    lines.append("## Cola Aprobada para Planificacion Real")
    if queue:
        for q in queue:
            lines.append(f"- {q['real_patch_planning_candidate_id']} | {q['front_id']} | {q['category']}")
    else:
        lines.append("- Ninguna propuesta aprobada.")
    lines.append("")
    lines.append("## Gobernanza")
    lines.append(f"- Estado: {governance['status']}")
    lines.append(f"- Ejecucion habilitada: {'SI' if governance['execution_allowed_now'] else 'NO'}")
    lines.append(f"- Patch generation habilitado: {'SI' if governance['real_patch_generation_allowed_now'] else 'NO'}")
    lines.append(f"- Patch application habilitado: {'SI' if governance['patch_application_allowed_now'] else 'NO'}")
    lines.append(f"- Patches aplicados: {'SI' if governance['patches_applied'] else 'NO'}")
    lines.append(f"- Patches staged: {'SI' if governance['patches_staged'] else 'NO'}")
    lines.append(f"- Requiere aprobacion operador: {'SI' if governance['requires_operator_approval'] else 'NO'}")
    lines.append("")
    lines.append("## Que NO Se Genero")
    lines.append("- Diffs aplicables (real diff): NO")
    lines.append("- Patches para staging: NO")
    lines.append("- Patches aplicados: NO")
    lines.append("- Escrituras a memoria: NO")
    lines.append("- Escrituras FAISS: NO")
    lines.append("- Promocion: NO")
    lines.append("")
    lines.append("## Siguiente Paso Recomendado")
    lines.append("- SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-DRY-RUN-01")
    lines.append("")
    lines.append("---")
    lines.append("Reporte generado en modo dry-run sin mutaciones persistentes.")
    return "\n".join(lines)
