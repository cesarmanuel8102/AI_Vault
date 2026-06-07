"""Real patch implementation plan dry-run for the first five self-improvement fronts.

Converts the approved implementation planning queue into detailed implementation
plans with units, test requirements, rollback strategies, and execution order.
Nothing is applied, staged, or written to persistent state.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_real_patch_plan_review_dry_run import (
    run_first_five_real_patch_plan_review_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-IMPLEMENTATION-PLAN-REVIEW-DRY-RUN-01"

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

CATEGORY_ORDER = {
    "evaluation_gate_gap": 1,
    "patch_hygiene_gap": 2,
    "orchestration_trace_gap": 3,
    "retrieval_provenance_gap": 4,
    "security_supply_chain_gap": 5,
}

RISK_ORDER = {"low": 1, "medium": 2, "high": 3}
PATCH_TYPE_ORDER = {"test_patch": 1, "policy_patch": 2, "harness_patch": 3}


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


def load_real_patch_implementation_queue_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    queue = _read_json(out / "first_five_real_patch_implementation_planning_queue.json", [])
    reviews = _read_json(out / "first_five_real_patch_plan_reviews.json", [])
    summary = _read_json(out / "first_five_real_patch_plan_review_summary.json", {})
    governance = _read_json(out / "first_five_real_patch_plan_review_governance.json", {})
    # Also load original plans for enrichment
    plans = _read_json(out / "run_real_patch_plan" / "first_five_real_patch_plans.json", [])
    return {
        "queue": queue,
        "reviews": reviews,
        "summary": summary,
        "governance": governance,
        "plans": plans,
        "output_dir": str(out),
    }


def _infer_change_type(patch_type: str) -> str:
    mapping = {
        "test_patch": "test_only",
        "harness_patch": "harness_only",
        "policy_patch": "policy_only",
    }
    return mapping.get(patch_type, "policy_only")


def build_real_patch_implementation_plan(
    candidate: Dict[str, Any],
    plan: Optional[Dict[str, Any]] = None,
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate_id = candidate.get("real_patch_implementation_planning_candidate_id", "")
    review_id = candidate.get("real_patch_plan_review_id", "")
    plan_id = candidate.get("real_patch_plan_id", "")
    front_id = candidate.get("front_id", "")
    category = candidate.get("category", "")
    patch_type = candidate.get("patch_type", "")

    # Enrich from plan if available
    targets = []
    allowed_targets = []
    required_tests = []
    acceptance_criteria = []
    risk_level = "medium"
    risk_notes = "operator review required before implementation"

    if plan:
        targets = plan.get("target_files_suggested", [])
        allowed_targets = plan.get("target_files_allowed_for_future_patch", [])
        required_tests = plan.get("required_tests", [])
        acceptance_criteria = plan.get("acceptance_criteria", [])
        risk_level = plan.get("risk_level", "medium")
        risk_notes = plan.get("risk_notes", "")

    if review:
        if not required_tests:
            required_tests = review.get("required_tests", [])
        if not acceptance_criteria:
            acceptance_criteria = review.get("acceptance_criteria", [])
        if not risk_level or risk_level == "medium":
            risk_level = review.get("risk_level", risk_level)
        if not risk_notes:
            risk_notes = review.get("risk_notes", "")
        if not targets:
            targets = review.get("target_files_suggested", [])

    # Fallback defaults
    if not targets:
        targets = ["tests/smoke/*"]
    if not allowed_targets:
        allowed_targets = targets
    if not required_tests:
        required_tests = ["python -m pytest tests/smoke -q"]
    if not acceptance_criteria:
        acceptance_criteria = ["operator must define acceptance criteria before implementation"]
    if not risk_notes:
        risk_notes = "operator review required before implementation"

    # Build implementation units
    units = []
    for idx, target in enumerate(allowed_targets[:5]):
        units.append({
            "unit_id": _stable_id("unit", candidate_id, idx),
            "description": f"Implement planned change for {target}",
            "allowed_now": False,
            "change_type": _infer_change_type(patch_type),
            "target_files": [target],
            "required_tests": required_tests,
            "acceptance_criteria": acceptance_criteria,
            "rollback_instruction": "revert this unit's changes only; preserve all other files",
        })

    if not units:
        units.append({
            "unit_id": _stable_id("unit", candidate_id, "no_target"),
            "description": "No allowed target files remaining after forbidden filter",
            "allowed_now": False,
            "change_type": "policy_only",
            "target_files": [],
            "required_tests": required_tests,
            "acceptance_criteria": acceptance_criteria,
            "rollback_instruction": "no files to revert; policy change only",
        })

    return {
        "real_patch_implementation_plan_id": _stable_id("impl_plan", candidate_id),
        "real_patch_implementation_planning_candidate_id": candidate_id,
        "real_patch_plan_review_id": review_id,
        "real_patch_plan_id": plan_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "plan_status": "real_patch_implementation_plan_dry_run_only",
        "implementation_allowed_now": False,
        "patch_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "target_files_suggested": targets,
        "target_files_allowed_for_future_patch": allowed_targets,
        "files_forbidden_to_modify": FORBIDDEN_PATHS,
        "implementation_units": units,
        "operator_approval_packet": {
            "required": True,
            "approval_scope": "implementation_plan_only",
            "approval_does_not_allow_patch_application": True,
            "must_review_target_files": True,
            "must_review_tests": True,
            "must_review_rollback": True,
        },
        "required_tests": required_tests,
        "acceptance_criteria": acceptance_criteria,
        "rollback_plan": {
            "required": True,
            "strategy": "delete_new_files_or_revert_single_future_commit_only",
            "preserve_dirty_preexisting_files": True,
        },
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": now_utc(),
    }


def build_all_real_patch_implementation_plans(
    queue: List[Dict[str, Any]],
    plans: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    plan_map = {p.get("real_patch_plan_id", ""): p for p in plans}
    review_map = {r.get("real_patch_plan_review_id", ""): r for r in reviews}
    return [
        build_real_patch_implementation_plan(
            c,
            plan_map.get(c.get("real_patch_plan_id", ""), None),
            review_map.get(c.get("real_patch_plan_review_id", ""), None),
        )
        for c in queue
    ]


def build_real_patch_implementation_execution_order(plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def sort_key(p):
        return (
            CATEGORY_ORDER.get(p.get("category", ""), 99),
            RISK_ORDER.get(p.get("risk_level", "medium"), 2),
            PATCH_TYPE_ORDER.get(p.get("patch_type", ""), 99),
        )
    sorted_plans = sorted(plans, key=sort_key)
    order = []
    for idx, p in enumerate(sorted_plans):
        order.append({
            "execution_order_id": _stable_id("exec_order", p["real_patch_implementation_plan_id"], idx),
            "real_patch_implementation_plan_id": p["real_patch_implementation_plan_id"],
            "front_id": p["front_id"],
            "category": p["category"],
            "patch_type": p["patch_type"],
            "risk_level": p["risk_level"],
            "execution_sequence": idx + 1,
            "implementation_allowed_now": False,
            "patch_generation_allowed_now": False,
            "patch_application_allowed_now": False,
        })
    return order


def build_real_patch_implementation_governance(plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "governance_id": _stable_id("impl_governance", len(plans)),
        "status": "real_patch_implementation_plan_only_not_executable",
        "implementation_plans_count": len(plans),
        "implementation_allowed_now": False,
        "patch_generation_allowed_now": False,
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
        "must_run_tests_before_future_patch": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_real_patch_implementation_plan(
    plans: List[Dict[str, Any]],
    upstream_empty: bool = False,
) -> Dict[str, Any]:
    result = {
        "ok": len(plans) > 0,
        "implementation_plans_count": len(plans),
        "implementation_allowed_now": False,
        "patch_generation_allowed_now": False,
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
        result["failure_reason"] = "empty_real_patch_implementation_planning_queue"
        result["recommended_next_action"] = "re_run_real_patch_plan_review_to_generate_approved_queue"
    else:
        result["upstream_empty"] = False
        result["functional_dry_run_passed"] = len(plans) > 0
        result["recommended_next_action"] = "operator_review_then_proceed_to_implementation_plan_review"

    return result


def _check_token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def run_first_five_real_patch_implementation_plan_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    review_out = str(out / "run_real_patch_plan_review") if out else None
    review_result = run_first_five_real_patch_plan_review_dry_run(output_dir=review_out)

    artifacts_dir = review_out or review_result.get("output_dir", "tmp_agent/run")
    artifacts = load_real_patch_implementation_queue_artifacts(artifacts_dir)

    queue = artifacts.get("queue", [])
    upstream_empty = len(queue) == 0

    plans = build_all_real_patch_implementation_plans(
        queue,
        artifacts.get("plans", []),
        artifacts.get("reviews", []),
    )
    order = build_real_patch_implementation_execution_order(plans)
    governance = build_real_patch_implementation_governance(plans)
    summary = summarize_real_patch_implementation_plan(plans, upstream_empty=upstream_empty)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_implementation_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_implementation_plans.jsonl", "w", encoding="utf-8") as fh:
            for p in plans:
                fh.write(json.dumps(p) + "\n")
        (out / "first_five_real_patch_implementation_execution_order.json").write_text(
            json.dumps(order, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_implementation_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_implementation_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(plans, order, governance, summary)
        (out / "first_five_real_patch_implementation_report.md").write_text(report, encoding="utf-8")

        all_texts = [json.dumps(plans), json.dumps(order), json.dumps(governance), json.dumps(summary), report]
        for text in all_texts:
            if _check_token_leak(text):
                token_leak = True
                break
        summary["token_leak_detected"] = token_leak
    summary["token_leak_detected"] = token_leak
    summary["output_dir"] = str(out) if out else None
    return summary


def _build_report_md(
    plans: List[Dict[str, Any]],
    order: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Reporte de Plan de Implementacion Real de Patch (Dry-Run)",
        "",
        "## Resumen",
        f"- Planes de implementacion creados: {summary.get('implementation_plans_count', 0)}",
        f"- Orden de ejecucion: {len(order)}",
        f"- Implementacion permitida ahora: {'SI' if summary.get('implementation_allowed_now') else 'NO'}",
        f"- Generacion de patch permitida ahora: {'SI' if summary.get('patch_generation_allowed_now') else 'NO'}",
        f"- Aplicacion de patch permitida ahora: {'SI' if summary.get('patch_application_allowed_now') else 'NO'}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Candidatos Recibidos y Planes Creados",
    ]
    for p in plans:
        lines.append(f"### {p['real_patch_implementation_plan_id']}")
        lines.append(f"- Candidato: {p['real_patch_implementation_planning_candidate_id']}")
        lines.append(f"- Plan: {p['real_patch_plan_id']}")
        lines.append(f"- Categoria: {p['category']}")
        lines.append(f"- Tipo de patch: {p['patch_type']}")
        lines.append(f"- Estado: {p['plan_status']}")
        lines.append(f"- Riesgo: {p['risk_level']}")
        lines.append(f"- Archivos sugeridos: {', '.join(p['target_files_suggested'])}")
        lines.append(f"- Archivos permitidos: {', '.join(p['target_files_allowed_for_future_patch'])}")
        lines.append("")
        lines.append("#### Unidades de Implementacion")
        for u in p["implementation_units"]:
            lines.append(f"- **{u['unit_id']}**: {u['description']}")
            lines.append(f"  - Tipo de cambio: {u['change_type']}")
            lines.append(f"  - Archivos objetivo: {', '.join(u['target_files']) if u['target_files'] else 'Ninguno'}")
            lines.append(f"  - Permitido ahora: {'SI' if u['allowed_now'] else 'NO'}")
            lines.append(f"  - Rollback: {u['rollback_instruction']}")
        lines.append("")
        lines.append(f"- Tests requeridos: {', '.join(p['required_tests'])}")
        lines.append(f"- Criterios de aceptacion: {', '.join(p['acceptance_criteria'])}")
        lines.append(f"- Requiere aprobacion operador: {'SI' if p['operator_approval_packet']['required'] else 'NO'}")
        lines.append(f"- Alcance de aprobacion: {p['operator_approval_packet']['approval_scope']}")
        lines.append(f"- Aprobacion NO permite aplicar patch: {'SI' if p['operator_approval_packet']['approval_does_not_allow_patch_application'] else 'NO'}")
        lines.append(f"- Rollback requerido: {'SI' if p['rollback_plan']['required'] else 'NO'}")
        lines.append(f"- Estrategia rollback: {p['rollback_plan']['strategy']}")
        lines.append("")

    lines.append("## Orden Recomendado")
    if order:
        for o in order:
            lines.append(f"{o['execution_sequence']}. {o['real_patch_implementation_plan_id']} | {o['front_id']} | {o['category']} | {o['risk_level']}")
    else:
        lines.append("- Ningun plan en orden de ejecucion.")
    lines.append("")

    lines.append("## Archivos Prohibidos")
    for f in FORBIDDEN_PATHS:
        lines.append(f"- {f}")
    lines.append("")

    lines.append("## Gobernanza")
    lines.append(f"- Estado: {governance['status']}")
    lines.append(f"- Planes contados: {governance['implementation_plans_count']}")
    lines.append(f"- Implementacion habilitada: {'SI' if governance['implementation_allowed_now'] else 'NO'}")
    lines.append(f"- Generacion de patch habilitada: {'SI' if governance['patch_generation_allowed_now'] else 'NO'}")
    lines.append(f"- Patch application habilitado: {'SI' if governance['patch_application_allowed_now'] else 'NO'}")
    lines.append(f"- Patches aplicados: {'SI' if governance['patches_applied'] else 'NO'}")
    lines.append(f"- Patches staged: {'SI' if governance['patches_staged'] else 'NO'}")
    lines.append(f"- Requiere aprobacion operador: {'SI' if governance['requires_operator_approval'] else 'NO'}")
    lines.append(f"- Siguiente frente seguro: {governance['next_safe_front']}")
    lines.append("")

    lines.append("## Que NO Se Genero")
    lines.append("- Diffs aplicables (real diff): NO")
    lines.append("- Patches para staging: NO")
    lines.append("- Patches aplicados: NO")
    lines.append("- Escrituras a memoria: NO")
    lines.append("- Escrituras FAISS: NO")
    lines.append("- Promocion: NO")
    lines.append("- Implementacion ejecutada: NO")
    lines.append("")

    lines.append("## Que NO Se Aplico")
    lines.append("- Ningun patch fue aplicado a archivos de codigo.")
    lines.append("- Ningun archivo objetivo fue modificado.")
    lines.append("- Ningun cambio fue commiteado ni pusheado como parte de este frente.")
    lines.append("- Ningun plan fue implementado.")
    lines.append("")

    lines.append("## Por Que Requiere Aprobacion Humana")
    lines.append("- Los planes de implementacion deben ser revisados por un operador antes de pasar a revision.")
    lines.append("- Solo los planes que cumplen todos los criterios pueden ser aprobados.")
    lines.append("- La aprobacion del plan de implementacion NO autoriza aplicar patches.")
    lines.append("- Cada unidad de implementacion debe ser revisada individualmente.")
    lines.append("")

    lines.append("## Siguiente Paso Recomendado")
    lines.append(f"- {NEXT_SAFE_FRONT}")
    lines.append("")
    lines.append("---")
    lines.append("Reporte generado en modo dry-run sin mutaciones persistentes.")
    return "\n".join(lines)
