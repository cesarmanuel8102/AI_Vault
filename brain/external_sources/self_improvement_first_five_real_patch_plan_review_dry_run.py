"""Real patch plan review dry-run for the first five self-improvement fronts.

Reviews real patch plans from the previous front and decides which are ready
for future real patch implementation planning.  Nothing is applied, staged,
or written to persistent state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_real_patch_plan_dry_run import (
    run_first_five_real_patch_plan_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-DRY-RUN-01"

TOKEN_MARKERS = [
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN"
]

FORBIDDEN_PATHS = [
    "memory/semantic/*",
    "memory\\semantic/*",
    "tmp_agent/strategies/*",
    "tmp_agent\\strategies/*",
    "trading/*",
    "B8/*",
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


def load_real_patch_plan_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    plans = _read_json(out / "first_five_real_patch_plans.json", [])
    order = _read_json(out / "first_five_real_patch_execution_order.json", [])
    governance = _read_json(out / "first_five_real_patch_plan_governance.json", {})
    summary = _read_json(out / "first_five_real_patch_plan_summary.json", {})
    return {
        "plans": plans,
        "order": order,
        "governance": governance,
        "summary": summary,
        "output_dir": str(out),
    }


def _score_plan_completeness(plan: Dict[str, Any]) -> float:
    points = 0
    total = 5
    if plan.get("target_files_allowed_for_future_patch"):
        points += 1
    if plan.get("implementation_steps"):
        points += 1
    if plan.get("required_tests"):
        points += 1
    if plan.get("acceptance_criteria"):
        points += 1
    rp = plan.get("rollback_plan", {})
    if rp.get("required") is True:
        points += 1
    return round(points / total, 4)


def _score_safety_guards(plan: Dict[str, Any]) -> float:
    checks = [
        "implementation_allowed_now",
        "patch_application_allowed_now",
        "patch_generated_for_application",
        "patch_applied",
        "patch_staged",
        "memory_write_allowed",
        "faiss_write_allowed",
        "real_write_allowed",
        "promotion_allowed",
    ]
    ok = all(plan.get(k) is False for k in checks)
    return round(1.0 if ok else 0.0, 4)


def _score_forbidden_scope_protection(plan: Dict[str, Any]) -> float:
    forbidden = plan.get("files_forbidden_to_modify", [])
    # Normalize to forward slashes for comparison
    required = list(set(p.replace("\\", "/") for p in FORBIDDEN_PATHS))
    forbidden_norm = [p.replace("\\", "/") for p in forbidden]
    missing = [p for p in required if p not in forbidden_norm]
    if missing:
        return round(0.0, 4)
    allowed = plan.get("target_files_allowed_for_future_patch", [])
    for t in allowed:
        t_norm = t.replace("\\", "/")
        for p in required:
            if t_norm.startswith(p.rstrip("*")):
                return round(0.0, 4)
    return round(1.0, 4)


def _score_test_readiness(plan: Dict[str, Any]) -> float:
    points = 0
    total = 4
    tests = plan.get("required_tests", [])
    criteria = plan.get("acceptance_criteria", [])
    if tests:
        points += 1
    if criteria:
        points += 1
    has_smoke = any("smoke" in str(t).lower() or "pytest" in str(t).lower() for t in tests)
    if has_smoke:
        points += 1
    if plan.get("rollback_plan"):
        points += 1
    return round(points / total, 4)


def _score_implementation_boundedness(plan: Dict[str, Any]) -> float:
    points = 0
    total = 4
    ptype = plan.get("patch_type", "")
    if ptype in ("test_patch", "policy_patch", "harness_patch", "documentation_patch"):
        points += 1
    targets = plan.get("target_files_allowed_for_future_patch", [])
    if len(targets) <= 5:
        points += 1
    if plan.get("risk_level") != "high":
        points += 1
    else:
        risk_notes = plan.get("risk_notes", "")
        if risk_notes and len(risk_notes) > 5:
            points += 1
    if plan.get("operator_approval_required") is True:
        points += 1
    return round(points / total, 4)


def review_real_patch_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    plan_id = plan.get("real_patch_plan_id", "")
    candidate_id = plan.get("real_patch_planning_candidate_id", "")
    front_id = plan.get("front_id", "")
    category = plan.get("category", "")
    patch_type = plan.get("patch_type", "")

    plan_completeness = _score_plan_completeness(plan)
    safety_guards = _score_safety_guards(plan)
    forbidden_scope_protection = _score_forbidden_scope_protection(plan)
    test_readiness = _score_test_readiness(plan)
    implementation_boundedness = _score_implementation_boundedness(plan)

    review_score = round(
        plan_completeness * 0.20 +
        safety_guards * 0.30 +
        forbidden_scope_protection * 0.20 +
        test_readiness * 0.15 +
        implementation_boundedness * 0.15,
        4,
    )

    reasons = []
    blocking = []
    required_before = []

    # Check for immediate reject conditions
    if safety_guards < 1.0:
        blocking.append("write/apply/stage flag is true")
    if forbidden_scope_protection < 1.0:
        blocking.append("target contains forbidden path or missing forbidden list")
    rp = plan.get("rollback_plan", {})
    if not rp or rp.get("required") is not True:
        blocking.append("rollback_plan missing or not required")
    if plan.get("operator_approval_required") is not True:
        blocking.append("operator_approval_required is false")
    if plan.get("real_write_allowed") is True:
        blocking.append("real_write_allowed is true")
    if plan.get("memory_write_allowed") is True:
        blocking.append("memory_write_allowed is true")
    if plan.get("faiss_write_allowed") is True:
        blocking.append("faiss_write_allowed is true")
    if plan.get("promotion_allowed") is True:
        blocking.append("promotion_allowed is true")

    if review_score >= 0.88 and safety_guards == 1.0 and forbidden_scope_protection == 1.0 and test_readiness >= 0.80 and implementation_boundedness >= 0.80 and not blocking:
        decision = "approve_for_real_patch_implementation_planning"
        approved = True
    elif blocking:
        decision = "reject"
        approved = False
    elif not plan.get("required_tests") or not plan.get("acceptance_criteria") or test_readiness < 0.80:
        decision = "request_more_tests"
        approved = False
        required_before.append("add required tests")
        required_before.append("add acceptance criteria")
    elif plan.get("risk_level") == "high":
        decision = "request_risk_mitigation"
        approved = False
        required_before.append("mitigate high risk before proceeding")
    elif len(plan.get("target_files_allowed_for_future_patch", [])) > 5 or implementation_boundedness < 0.80:
        decision = "request_scope_reduction"
        approved = False
        required_before.append("reduce target files to <= 5")
    else:
        decision = "request_more_evidence"
        approved = False

    if decision != "approve_for_real_patch_implementation_planning":
        reasons.append(f"review_score={review_score} below threshold or guards incomplete")

    return {
        "real_patch_plan_review_id": _stable_id("review", plan_id),
        "real_patch_plan_id": plan_id,
        "real_patch_planning_candidate_id": candidate_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "review_score": review_score,
        "decision": decision,
        "scores": {
            "plan_completeness": plan_completeness,
            "safety_guards": safety_guards,
            "forbidden_scope_protection": forbidden_scope_protection,
            "test_readiness": test_readiness,
            "implementation_boundedness": implementation_boundedness,
        },
        "reasons": reasons,
        "blocking_issues": blocking,
        "required_before_implementation_planning": required_before,
        "approved_for_real_patch_implementation_planning": approved,
        "implementation_allowed_now": False,
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


def review_all_real_patch_plans(plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [review_real_patch_plan(p) for p in plans]


def build_real_patch_implementation_planning_queue(reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue = []
    for r in reviews:
        if r.get("decision") != "approve_for_real_patch_implementation_planning":
            continue
        queue.append({
            "real_patch_implementation_planning_candidate_id": _stable_id("impl_plan", r["real_patch_plan_review_id"]),
            "real_patch_plan_review_id": r["real_patch_plan_review_id"],
            "real_patch_plan_id": r["real_patch_plan_id"],
            "front_id": r["front_id"],
            "category": r["category"],
            "patch_type": r["patch_type"],
            "candidate_status": "approved_for_real_patch_implementation_planning",
            "implementation_allowed_now": False,
            "patch_application_allowed_now": False,
            "real_patch_application_allowed_now": False,
            "requires_operator_approval": True,
            "required_tests": r.get("required_tests", []),
            "rollback_required": True,
            "next_safe_front": NEXT_SAFE_FRONT,
        })
    return queue


def build_real_patch_plan_review_governance(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    approved = sum(1 for r in reviews if r.get("decision") == "approve_for_real_patch_implementation_planning")
    return {
        "governance_id": _stable_id("review_governance", len(reviews)),
        "status": "real_patch_plan_review_only_not_executable",
        "reviews_count": len(reviews),
        "approved_for_real_patch_implementation_planning": approved,
        "implementation_allowed_now": False,
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
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_real_patch_plan_review(reviews: List[Dict[str, Any]], queue: List[Dict[str, Any]], upstream_empty: bool = False, missing_upstream: bool = False) -> Dict[str, Any]:
    decisions = {}
    for r in reviews:
        d = r.get("decision", "unknown")
        decisions[d] = decisions.get(d, 0) + 1

    result = {
        "ok": len(reviews) > 0,
        "reviews_count": len(reviews),
        "real_plans_count": len(reviews),
        "approved_for_real_patch_implementation_planning": decisions.get("approve_for_real_patch_implementation_planning", 0),
        "request_more_tests": decisions.get("request_more_tests", 0),
        "request_scope_reduction": decisions.get("request_scope_reduction", 0),
        "request_risk_mitigation": decisions.get("request_risk_mitigation", 0),
        "request_more_evidence": decisions.get("request_more_evidence", 0),
        "rejected": decisions.get("reject", 0),
        "implementation_planning_queue_count": len(queue),
        "implementation_allowed_now": False,
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

    if missing_upstream:
        result["ok"] = False
        result["upstream_empty"] = False
        result["missing_upstream_artifacts"] = True
        result["failure_reason"] = "missing_first_five_real_patch_plans_json"
    elif upstream_empty:
        result["ok"] = False
        result["upstream_empty"] = True
        result["missing_upstream_artifacts"] = False
        result["failure_reason"] = "upstream_real_patch_plan_output_empty"
    else:
        result["upstream_empty"] = False
        result["missing_upstream_artifacts"] = False
        result["functional_dry_run_passed"] = len(reviews) > 0

    return result


def _check_token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def run_first_five_real_patch_plan_review_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    plan_out = str(out / "run_real_patch_plan") if out else None
    plan_result = run_first_five_real_patch_plan_dry_run(output_dir=plan_out)
    artifacts_dir = plan_out or plan_result.get("output_dir", "tmp_agent/run")
    artifacts = load_real_patch_plan_artifacts(artifacts_dir)

    plans = artifacts.get("plans", [])
    upstream_empty = len(plans) == 0
    plans_path = Path(artifacts_dir) / "first_five_real_patch_plans.json"
    missing_upstream = not plans_path.exists()

    reviews = review_all_real_patch_plans(plans)
    queue = build_real_patch_implementation_planning_queue(reviews)
    governance = build_real_patch_plan_review_governance(reviews)
    summary = summarize_real_patch_plan_review(reviews, queue, upstream_empty=upstream_empty, missing_upstream=missing_upstream)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_plan_reviews.json").write_text(
            json.dumps(reviews, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_plan_reviews.jsonl", "w", encoding="utf-8") as fh:
            for r in reviews:
                fh.write(json.dumps(r) + "\n")
        (out / "first_five_real_patch_implementation_planning_queue.json").write_text(
            json.dumps(queue, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_plan_review_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_plan_review_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(reviews, queue, governance, summary)
        (out / "first_five_real_patch_plan_review_report.md").write_text(report, encoding="utf-8")

        all_texts = [json.dumps(reviews), json.dumps(queue), json.dumps(governance), json.dumps(summary), report]
        for text in all_texts:
            if _check_token_leak(text):
                token_leak = True
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
        "# Reporte de Revision de Plan Real de Patch (Dry-Run)",
        "",
        "## Resumen",
        f"- Planes revisados: {summary.get('reviews_count', 0)}",
        f"- Aprobados para implementation planning: {summary.get('approved_for_real_patch_implementation_planning', 0)}",
        f"- Rechazados: {summary.get('rejected', 0)}",
        f"- Request more tests: {summary.get('request_more_tests', 0)}",
        f"- Request scope reduction: {summary.get('request_scope_reduction', 0)}",
        f"- Request risk mitigation: {summary.get('request_risk_mitigation', 0)}",
        f"- Request more evidence: {summary.get('request_more_evidence', 0)}",
        f"- Cola de implementation planning: {summary.get('implementation_planning_queue_count', 0)}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Planes Revisados",
    ]
    for r in reviews:
        lines.append(f"### {r['real_patch_plan_review_id']}")
        lines.append(f"- Plan: {r['real_patch_plan_id']}")
        lines.append(f"- Categoria: {r['category']}")
        lines.append(f"- Decision: {r['decision']}")
        lines.append(f"- Score: {r['review_score']}")
        lines.append(f"- Aprobado: {'SI' if r['approved_for_real_patch_implementation_planning'] else 'NO'}")
        lines.append(f"- Bloqueos: {', '.join(r['blocking_issues']) if r['blocking_issues'] else 'Ninguno'}")
        lines.append(f"- Requerido antes: {', '.join(r['required_before_implementation_planning']) if r['required_before_implementation_planning'] else 'Nada'}")
        lines.append("")

    lines.append("## Cola Aprobada para Implementation Planning")
    if queue:
        for q in queue:
            lines.append(f"- {q['real_patch_implementation_planning_candidate_id']} | {q['front_id']} | {q['category']}")
    else:
        lines.append("- Ningun candidato aprobado.")
    lines.append("")

    lines.append("## Gobernanza")
    lines.append(f"- Estado: {governance['status']}")
    lines.append(f"- Reviews contados: {governance['reviews_count']}")
    lines.append(f"- Aprobados: {governance['approved_for_real_patch_implementation_planning']}")
    lines.append(f"- Ejecucion habilitada: {'SI' if governance['implementation_allowed_now'] else 'NO'}")
    lines.append(f"- Patch application habilitado: {'SI' if governance['patch_application_allowed_now'] else 'NO'}")
    lines.append(f"- Patches aplicados: {'SI' if governance['patches_applied'] else 'NO'}")
    lines.append(f"- Patches staged: {'SI' if governance['patches_staged'] else 'NO'}")
    lines.append(f"- Requiere aprobacion operador: {'SI' if governance['requires_operator_approval'] else 'NO'}")
    lines.append(f"- Siguiente frente seguro: {governance['next_safe_front']}")
    lines.append("")

    lines.append("## Que NO Se Aplico")
    lines.append("- Ningun patch fue aplicado a archivos de codigo.")
    lines.append("- Ningun archivo objetivo fue modificado.")
    lines.append("- Ningun cambio fue commiteado ni pusheado como parte de este frente.")
    lines.append("- Ningun plan fue implementado.")
    lines.append("")

    lines.append("## Por Que Requiere Aprobacion Humana")
    lines.append("- Los planes deben ser revisados por un operador antes de pasar a implementation planning.")
    lines.append("- Solo los planes que cumplen todos los criterios pueden ser aprobados.")
    lines.append("- Los planes rechazados o con advertencias deben ser corregidos primero.")
    lines.append("")

    lines.append("## Siguiente Paso Recomendado")
    lines.append("- SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-DRY-RUN-01")
    lines.append("")
    lines.append("---")
    lines.append("Reporte generado en modo dry-run sin mutaciones persistentes.")
    return "\n".join(lines)
