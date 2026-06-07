"""Real patch generation review dry-run for the first five self-improvement fronts.

Reviews inert patch draft proposals and decides which qualify for
materialization planning. Does not generate, apply, modify, stage,
promote, or write any persistent state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_real_patch_generation_dry_run import (
    run_first_five_real_patch_generation_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-DRY-RUN-01"

TOKEN_MARKERS = [
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
]

FORBIDDEN_PATHS = [
    "memory/semantic",
    "memory\\semantic",
    "tmp_agent/strategies",
    "tmp_agent\\strategies",
    "trading",
    "B8",
    "tmp_agent/brain_v9/main.py",
    "tmp_agent/brain_v9/core/session.py",
    "brain/curated_runtime_lookup.py",
]


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


def load_real_patch_draft_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    drafts = _read_json(out / "first_five_real_patch_drafts.json", [])
    governance = _read_json(out / "first_five_real_patch_generation_governance.json", {})
    summary = _read_json(out / "first_five_real_patch_generation_summary.json", {})
    return {
        "drafts": drafts,
        "governance": governance,
        "summary": summary,
        "output_dir": str(out),
    }


def _score_draft_completeness(draft: Dict[str, Any]) -> float:
    checks = [
        draft.get("real_patch_draft_id"),
        draft.get("real_patch_generation_candidate_id"),
        draft.get("real_patch_generation_plan_review_id"),
        draft.get("front_id"),
        draft.get("category"),
        draft.get("patch_type"),
        draft.get("target_files_suggested"),
        draft.get("target_files_not_modified"),
        draft.get("required_tests"),
        draft.get("acceptance_criteria"),
    ]
    points = sum(1 for c in checks if c)
    rp = draft.get("rollback_plan", {})
    if rp.get("required") is True:
        points += 1
    op = draft.get("operator_approval_packet", {})
    if op.get("required") is True:
        points += 1
    return round(min(1.0, points / 12), 4)


def _score_inertness_safety(draft: Dict[str, Any]) -> float:
    checks = [
        draft.get("draft_status") == "inert_patch_draft_dry_run_only",
        draft.get("dry_run_only") is True,
        draft.get("applicable") is False,
        draft.get("not_for_git_apply") is True,
        draft.get("pseudo_diff_is_applicable") is False,
        draft.get("pseudo_diff_header") == "DRY-RUN ONLY — NOT A GIT PATCH",
    ]
    text = draft.get("pseudo_diff_text", "")
    checks.append(not text.startswith("diff --git"))
    checks.append("--- a/" not in text)
    checks.append("+++ b/" not in text)
    checks.append("Do not run git apply" in text)
    checks.append("inert human-review draft" in text)
    return round(sum(checks) / len(checks), 4)


def _score_safety_guards(draft: Dict[str, Any]) -> float:
    checks = [
        draft.get("patch_generation_allowed_now") is False,
        draft.get("diff_generation_allowed_now") is False,
        draft.get("patch_application_allowed_now") is False,
        draft.get("real_patch_application_allowed_now") is False,
        draft.get("patches_generated_for_application") is False,
        draft.get("patches_applied") is False,
        draft.get("patches_staged") is False,
        draft.get("memory_write_allowed") is False,
        draft.get("faiss_write_allowed") is False,
        draft.get("real_write_allowed") is False,
        draft.get("promotion_allowed") is False,
    ]
    return round(1.0 if all(checks) else 0.0, 4)


def _score_scope_protection(draft: Dict[str, Any]) -> float:
    suggested = draft.get("target_files_suggested", [])
    not_modified = draft.get("target_files_not_modified", [])
    if suggested != not_modified:
        return round(0.0, 4)
    text = draft.get("pseudo_diff_text", "")
    for forbidden in FORBIDDEN_PATHS:
        for target in suggested:
            if target.startswith(forbidden):
                return round(0.0, 4)
        if forbidden in text:
            return round(0.0, 4)
    return round(1.0, 4)


def _score_human_review_readiness(draft: Dict[str, Any]) -> float:
    checks = [
        draft.get("human_review_required") is True,
    ]
    op = draft.get("operator_approval_packet", {})
    checks.append(op.get("required") is True)
    checks.append(op.get("approval_does_not_allow_patch_application") is True)
    checks.append(op.get("approval_does_not_allow_git_apply") is True)
    checks.append(op.get("must_review_target_files") is True)
    checks.append(op.get("must_review_tests") is True)
    checks.append(op.get("must_review_rollback") is True)
    rp = draft.get("rollback_plan", {})
    checks.append(rp.get("preserve_dirty_preexisting_files") is True)
    checks.append(bool(draft.get("required_tests")))
    checks.append(bool(draft.get("acceptance_criteria")))
    return round(sum(checks) / len(checks), 4)


def review_inert_patch_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    draft_id = draft.get("real_patch_draft_id", "")
    candidate_id = draft.get("real_patch_generation_candidate_id", "")
    plan_review_id = draft.get("real_patch_generation_plan_review_id", "")
    plan_id = draft.get("real_patch_generation_plan_id", "")
    front_id = draft.get("front_id", "")
    category = draft.get("category", "")
    patch_type = draft.get("patch_type", "")

    completeness = _score_draft_completeness(draft)
    inertness = _score_inertness_safety(draft)
    safety = _score_safety_guards(draft)
    scope = _score_scope_protection(draft)
    readiness = _score_human_review_readiness(draft)

    review_score = round(min(1.0,
        completeness * 0.20 +
        inertness * 0.30 +
        safety * 0.25 +
        scope * 0.15 +
        readiness * 0.10,
    ), 4)

    reasons = []
    blocking = []
    required_before = []

    # Blocking checks
    if draft.get("applicable") is True:
        blocking.append("applicable is true")
    if draft.get("not_for_git_apply") is not True:
        blocking.append("not_for_git_apply is false")
    if draft.get("dry_run_only") is not True:
        blocking.append("dry_run_only is false")
    if draft.get("pseudo_diff_is_applicable") is True:
        blocking.append("pseudo_diff_is_applicable is true")
    if draft.get("patch_generation_allowed_now") is True:
        blocking.append("patch_generation_allowed_now is true")
    if draft.get("diff_generation_allowed_now") is True:
        blocking.append("diff_generation_allowed_now is true")
    if draft.get("patch_application_allowed_now") is True:
        blocking.append("patch_application_allowed_now is true")
    if draft.get("real_patch_application_allowed_now") is True:
        blocking.append("real_patch_application_allowed_now is true")
    if draft.get("patches_generated_for_application") is True:
        blocking.append("patches_generated_for_application is true")
    if draft.get("patches_applied") is True:
        blocking.append("patches_applied is true")
    if draft.get("patches_staged") is True:
        blocking.append("patches_staged is true")
    if draft.get("memory_write_allowed") is True:
        blocking.append("memory_write_allowed is true")
    if draft.get("faiss_write_allowed") is True:
        blocking.append("faiss_write_allowed is true")
    if draft.get("real_write_allowed") is True:
        blocking.append("real_write_allowed is true")
    if draft.get("promotion_allowed") is True:
        blocking.append("promotion_allowed is true")

    op = draft.get("operator_approval_packet", {})
    if op.get("approval_does_not_allow_patch_application") is not True:
        blocking.append("approval allows patch application")
    if op.get("approval_does_not_allow_git_apply") is not True:
        blocking.append("approval allows git apply")

    rp = draft.get("rollback_plan", {})
    if not rp or rp.get("required") is not True:
        blocking.append("rollback_plan missing or not required")

    text = draft.get("pseudo_diff_text", "")
    if text.startswith("diff --git"):
        blocking.append("pseudo_diff starts with diff --git")
    if "--- a/" in text:
        blocking.append("pseudo_diff contains --- a/")
    if "+++ b/" in text:
        blocking.append("pseudo_diff contains +++ b/")

    suggested = draft.get("target_files_suggested", [])
    not_modified = draft.get("target_files_not_modified", [])
    if suggested != not_modified:
        blocking.append("target_files_not_modified mismatch")

    for forbidden in FORBIDDEN_PATHS:
        for target in suggested:
            if target.startswith(forbidden):
                blocking.append(f"target contains forbidden path: {forbidden}")

    # Decision
    if blocking:
        decision = "reject"
        approved = False
    elif not draft.get("required_tests") or not draft.get("acceptance_criteria"):
        decision = "request_more_tests"
        approved = False
        required_before.append("add required tests")
        required_before.append("add acceptance criteria")
    elif review_score >= 0.92 and inertness == 1.0 and safety == 1.0 and scope == 1.0 and readiness >= 0.85:
        decision = "approve_for_materialization_planning"
        approved = True
    elif readiness < 0.85:
        decision = "request_more_tests"
        approved = False
        required_before.append("add required tests")
        required_before.append("add acceptance criteria")
    elif scope < 1.0:
        decision = "request_scope_reduction"
        approved = False
        required_before.append("reduce scope and remove forbidden paths")
    elif inertness < 1.0:
        decision = "request_inertness_fix"
        approved = False
        required_before.append("fix pseudo_diff inertness markers")
    else:
        decision = "request_more_evidence"
        approved = False

    if decision != "approve_for_materialization_planning":
        reasons.append(f"review_score={review_score} below threshold or guards incomplete")

    return {
        "real_patch_generation_review_id": _stable_id("gen_review", draft_id),
        "real_patch_draft_id": draft_id,
        "real_patch_generation_candidate_id": candidate_id,
        "real_patch_generation_plan_review_id": plan_review_id,
        "real_patch_generation_plan_id": plan_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "review_score": review_score,
        "decision": decision,
        "scores": {
            "draft_completeness": completeness,
            "inertness_safety": inertness,
            "safety_guards": safety,
            "scope_protection": scope,
            "human_review_readiness": readiness,
        },
        "reasons": reasons,
        "blocking_issues": blocking,
        "required_before_materialization_planning": required_before,
        "approved_for_materialization_planning": approved,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "operator_approval_required": True,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "required_tests": draft.get("required_tests", []),
        "acceptance_criteria": draft.get("acceptance_criteria", []),
        "risk_level": draft.get("risk_level", "medium"),
        "reviewed_at": now_utc(),
    }


def review_all_inert_patch_drafts(drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [review_inert_patch_draft(d) for d in drafts]


def build_real_patch_materialization_planning_queue(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue = []
    for r in reviews:
        if r.get("decision") != "approve_for_materialization_planning":
            continue
        queue.append({
            "real_patch_materialization_planning_candidate_id": _stable_id("mat_candidate", r["real_patch_generation_review_id"]),
            "real_patch_generation_review_id": r["real_patch_generation_review_id"],
            "real_patch_draft_id": r["real_patch_draft_id"],
            "real_patch_generation_candidate_id": r["real_patch_generation_candidate_id"],
            "real_patch_generation_plan_review_id": r["real_patch_generation_plan_review_id"],
            "front_id": r["front_id"],
            "category": r["category"],
            "patch_type": r["patch_type"],
            "candidate_status": "approved_for_materialization_planning",
            "patch_generation_allowed_now": False,
            "diff_generation_allowed_now": False,
            "patch_application_allowed_now": False,
            "real_patch_application_allowed_now": False,
            "requires_operator_approval": True,
            "required_tests": r.get("required_tests", []),
            "rollback_required": True,
            "next_safe_front": NEXT_SAFE_FRONT,
        })
    return queue


def build_real_patch_generation_review_governance(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    approved = sum(1 for r in reviews if r.get("decision") == "approve_for_materialization_planning")
    return {
        "governance_id": _stable_id("gen_review_governance", len(reviews)),
        "status": "inert_patch_generation_review_only_not_executable",
        "reviews_count": len(reviews),
        "approved_for_materialization_planning": approved,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
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
        "must_not_create_patch_files": True,
        "must_not_run_git_apply": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_real_patch_generation_review(
    reviews: List[Dict[str, Any]],
    queue: List[Dict[str, Any]],
    upstream_empty: bool = False,
) -> Dict[str, Any]:
    decisions = {}
    for r in reviews:
        d = r.get("decision", "unknown")
        decisions[d] = decisions.get(d, 0) + 1

    result = {
        "ok": len(reviews) > 0,
        "reviews_count": len(reviews),
        "approved_for_materialization_planning": decisions.get("approve_for_materialization_planning", 0),
        "rejected": decisions.get("reject", 0),
        "request_more_tests": decisions.get("request_more_tests", 0),
        "request_scope_reduction": decisions.get("request_scope_reduction", 0),
        "request_inertness_fix": decisions.get("request_inertness_fix", 0),
        "request_more_evidence": decisions.get("request_more_evidence", 0),
        "materialization_planning_queue_count": len(queue),
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "timestamp": now_utc(),
    }

    if upstream_empty:
        result["ok"] = False
        result["upstream_empty"] = True
        result["failure_reason"] = "empty_real_patch_drafts"
        result["recommended_next_action"] = "re_run_real_patch_generation_dry_run_to_generate_drafts"
    else:
        result["upstream_empty"] = False
        result["functional_dry_run_passed"] = len(reviews) > 0
        result["recommended_next_action"] = "operator_review_then_proceed_to_materialization_planning_dry_run"

    return result


def _check_token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def _build_report_md(
    reviews: List[Dict[str, Any]],
    queue: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Revision de Patch Drafts Inertes — Dry-Run",
        "",
        "## Resumen",
        f"- Drafts revisados: {summary.get('reviews_count', 0)}",
        f"- Aprobados para materialization planning: {summary.get('approved_for_materialization_planning', 0)}",
        f"- Rechazados: {summary.get('rejected', 0)}",
        f"- Request more tests: {summary.get('request_more_tests', 0)}",
        f"- Request scope reduction: {summary.get('request_scope_reduction', 0)}",
        f"- Request inertness fix: {summary.get('request_inertness_fix', 0)}",
        f"- Request more evidence: {summary.get('request_more_evidence', 0)}",
        f"- Cola de materialization planning: {summary.get('materialization_planning_queue_count', 0)}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Drafts Revisados",
    ]
    for r in reviews:
        lines.append(f"### {r['real_patch_generation_review_id']}")
        lines.append(f"- Draft: {r['real_patch_draft_id']}")
        lines.append(f"- Front: {r['front_id']}")
        lines.append(f"- Categoria: {r['category']}")
        lines.append(f"- Tipo: {r['patch_type']}")
        lines.append(f"- Decision: {r['decision']}")
        lines.append(f"- Score: {r['review_score']}")
        lines.append(f"- Aprobado: {'SI' if r['approved_for_materialization_planning'] else 'NO'}")
        lines.append(f"- Bloqueos: {', '.join(r['blocking_issues']) if r['blocking_issues'] else 'Ninguno'}")
        lines.append(f"- Requerido antes: {', '.join(r['required_before_materialization_planning']) if r['required_before_materialization_planning'] else 'Nada'}")
        lines.append("- Scores:")
        for k, v in r["scores"].items():
            lines.append(f"  - {k}: {v}")
        lines.append("")

    lines.append("## Cola Aprobada para Materialization Planning")
    if queue:
        for q in queue:
            lines.append(f"- {q['real_patch_materialization_planning_candidate_id']} | {q['front_id']} | {q['category']}")
    else:
        lines.append("- Ningun candidato aprobado.")
    lines.append("")

    lines.append("## Gobernanza")
    lines.append(f"- Estado: {governance['status']}")
    lines.append(f"- Reviews contados: {governance['reviews_count']}")
    lines.append(f"- Aprobados: {governance['approved_for_materialization_planning']}")
    lines.append(f"- Patch generation habilitada: {'SI' if governance['patch_generation_allowed_now'] else 'NO'}")
    lines.append(f"- Diff generation habilitada: {'SI' if governance['diff_generation_allowed_now'] else 'NO'}")
    lines.append(f"- Patch application habilitado: {'SI' if governance['patch_application_allowed_now'] else 'NO'}")
    lines.append(f"- Patches aplicados: {'SI' if governance['patches_applied'] else 'NO'}")
    lines.append(f"- Patches staged: {'SI' if governance['patches_staged'] else 'NO'}")
    lines.append(f"- Requiere aprobacion operador: {'SI' if governance['requires_operator_approval'] else 'NO'}")
    lines.append(f"- No crear archivos .patch: {'SI' if governance['must_not_create_patch_files'] else 'NO'}")
    lines.append(f"- No ejecutar git apply: {'SI' if governance['must_not_run_git_apply'] else 'NO'}")
    lines.append(f"- Siguiente frente seguro: {governance['next_safe_front']}")
    lines.append("")

    lines.extend([
        "## Que NO Se Genero",
        "- Diffs aplicables (real diff): NO",
        "- Archivos .patch aplicables: NO",
        "- Patches para staging: NO",
        "- Patches aplicados: NO",
        "- Escrituras a memoria: NO",
        "- Escrituras FAISS: NO",
        "- Promocion: NO",
        "- Implementacion ejecutada: NO",
        "",
        "## Que NO Se Aplico",
        "- Ningun patch fue aplicado a archivos de codigo.",
        "- Ningun archivo objetivo fue modificado.",
        "- Ningun cambio fue commiteado ni pusheado como parte de este frente.",
        "- Ningun plan fue implementado.",
        "",
        "## Que Falta Antes de Materialization Planning",
        "- Revision humana obligatoria para cada draft.",
        "- Solo drafts con inertness perfecta y score >= 0.92 son aprobados.",
        "- Cada candidato aprobado requiere operator approval individual.",
        "",
        "## Por Que Requiere Aprobacion Humana",
        "- Los patch drafts son inertes y deben revisarse manualmente.",
        "- La aprobacion del operador NO autoriza aplicar patches.",
        "- Cada draft debe ser revisado individualmente antes de cualquier paso siguiente.",
        "",
        "## Siguiente Paso Recomendado",
        f"- {NEXT_SAFE_FRONT}",
        "",
        "---",
        "Reporte generado en modo dry-run sin mutaciones persistentes.",
    ])
    return "\n".join(lines)


def run_first_five_real_patch_generation_review_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    gen_out = str(out / "run_patch_generation") if out else None
    gen_result = run_first_five_real_patch_generation_dry_run(output_dir=gen_out)
    artifacts_dir = gen_out or gen_result.get("output_dir", "tmp_agent/run")
    artifacts = load_real_patch_draft_artifacts(artifacts_dir)

    drafts = artifacts.get("drafts", [])
    upstream_empty = len(drafts) == 0

    reviews = review_all_inert_patch_drafts(drafts)
    queue = build_real_patch_materialization_planning_queue(reviews)
    governance = build_real_patch_generation_review_governance(reviews)
    summary = summarize_real_patch_generation_review(reviews, queue, upstream_empty=upstream_empty)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_generation_reviews.json").write_text(
            json.dumps(reviews, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_generation_reviews.jsonl", "w", encoding="utf-8") as fh:
            for r in reviews:
                fh.write(json.dumps(r) + "\n")
        (out / "first_five_real_patch_materialization_planning_queue.json").write_text(
            json.dumps(queue, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_generation_review_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_generation_review_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(reviews, queue, governance, summary)
        (out / "first_five_real_patch_generation_review_report.md").write_text(report, encoding="utf-8")

        all_texts = [json.dumps(reviews), json.dumps(queue), json.dumps(governance), json.dumps(summary), report]
        for text in all_texts:
            if _check_token_leak(text):
                token_leak = True
                break
        summary["token_leak_detected"] = token_leak
    summary["token_leak_detected"] = token_leak
    summary["output_dir"] = str(out) if out else None
    return summary
