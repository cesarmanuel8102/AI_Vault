"""Real patch materialization plan dry-run for the first five self-improvement fronts.

Creates detailed materialization plans that describe how an inert patch draft
would be turned into an actual patch. The plans themselves remain non-executable;
patch creation, git apply, and target file modification remain blocked.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_real_patch_generation_review_dry_run import (
    run_first_five_real_patch_generation_review_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-MATERIALIZATION-PLAN-REVIEW-DRY-RUN-01"

TOKEN_MARKERS = [
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
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


def _now_utc() -> str:
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


def load_materialization_planning_queue_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    queue = _read_json(out / "first_five_real_patch_materialization_planning_queue.json", [])
    reviews = _read_json(out / "first_five_real_patch_generation_reviews.json", [])
    summary = _read_json(out / "first_five_real_patch_generation_review_summary.json", {})
    governance = _read_json(out / "first_five_real_patch_generation_review_governance.json", {})
    return {
        "queue": queue,
        "reviews": reviews,
        "summary": summary,
        "governance": governance,
        "output_dir": str(out),
    }


def _infer_unit_type(patch_type: str) -> str:
    mapping = {
        "test_patch": "test_materialization_plan",
        "harness_patch": "harness_materialization_plan",
        "policy_patch": "policy_materialization_plan",
    }
    return mapping.get(patch_type, "policy_materialization_plan")


def build_materialization_plan(
    candidate: Dict[str, Any],
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate_id = candidate.get("real_patch_materialization_planning_candidate_id", "")
    review_id = candidate.get("real_patch_generation_review_id", "")
    draft_id = candidate.get("real_patch_draft_id", "")
    plan_review_id = candidate.get("real_patch_generation_plan_review_id", "")
    front_id = candidate.get("front_id", "")
    category = candidate.get("category", "")
    patch_type = candidate.get("patch_type", "")

    target_files = candidate.get("required_tests", [])
    if not target_files:
        target_files = review.get("required_tests", []) if review else []
    if not target_files:
        target_files = ["tests/smoke/*"]

    acceptance_criteria = candidate.get("acceptance_criteria", [])
    if not acceptance_criteria:
        acceptance_criteria = review.get("acceptance_criteria", []) if review else []
    if not acceptance_criteria:
        acceptance_criteria = ["operator must define acceptance criteria before patch generation"]

    risk_level = candidate.get("risk_level", "")
    if not risk_level:
        risk_level = review.get("risk_level", "") if review else ""
    if not risk_level:
        risk_level = "medium"

    risk_notes = candidate.get("risk_notes", "")
    if not risk_notes:
        risk_notes = review.get("risk_notes", "") if review else ""
    if not risk_notes:
        risk_notes = "operator review required before patch generation"

    target_files_suggested = candidate.get("target_files_allowed_for_future_patch", [])
    if not target_files_suggested:
        target_files_suggested = ["tests/smoke/*"]

    units = []
    for idx, target in enumerate(target_files_suggested[:5]):
        units.append({
            "unit_id": _stable_id("unit", candidate_id, idx),
            "description": f"Materialize patch plan for {target}",
            "allowed_now": False,
            "unit_type": _infer_unit_type(patch_type),
            "target_files": [target],
            "required_tests": target_files,
            "acceptance_criteria": acceptance_criteria,
            "materialization_constraints": [
                "no_patch_file_creation",
                "no_git_apply",
                "no_target_file_modification",
                "no_stage",
                "no_memory_write",
                "no_faiss_write",
                "no_token_logging",
            ],
            "rollback_instruction": "discard materialization plan artifacts only; preserve all preexisting files",
        })

    if not units:
        units.append({
            "unit_id": _stable_id("unit", candidate_id, "no_target"),
            "description": "No allowed target files for patch materialization planning",
            "allowed_now": False,
            "unit_type": "policy_materialization_plan",
            "target_files": [],
            "required_tests": target_files,
            "acceptance_criteria": acceptance_criteria,
            "materialization_constraints": [
                "no_patch_file_creation",
                "no_git_apply",
                "no_target_file_modification",
                "no_stage",
                "no_memory_write",
                "no_faiss_write",
                "no_token_logging",
            ],
            "rollback_instruction": "no artifacts to discard; policy-only plan",
        })

    return {
        "real_patch_materialization_plan_id": _stable_id("mat_plan", candidate_id),
        "real_patch_materialization_planning_candidate_id": candidate_id,
        "real_patch_generation_review_id": review_id,
        "real_patch_draft_id": draft_id,
        "real_patch_generation_candidate_id": candidate.get("real_patch_generation_candidate_id", ""),
        "real_patch_generation_plan_review_id": plan_review_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "plan_status": "materialization_plan_dry_run_only",
        "dry_run_only": True,
        "materialization_allowed_now": False,
        "patch_file_creation_allowed_now": False,
        "git_apply_allowed_now": False,
        "target_file_modification_allowed_now": False,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "target_files_suggested": target_files_suggested,
        "target_files_not_modified": target_files_suggested,
        "materialization_units": units,
        "operator_approval_packet": {
            "required": True,
            "approval_scope": "materialization_plan_only",
            "approval_does_not_allow_patch_file_creation": True,
            "approval_does_not_allow_git_apply": True,
            "approval_does_not_allow_target_file_modification": True,
            "approval_does_not_allow_patch_application": True,
            "must_review_target_files": True,
            "must_review_tests": True,
            "must_review_rollback": True,
        },
        "required_tests": target_files,
        "acceptance_criteria": acceptance_criteria,
        "rollback_plan": {
            "required": True,
            "strategy": "discard_materialization_plan_artifacts_only",
            "preserve_dirty_preexisting_files": True,
        },
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": _now_utc(),
    }


def build_all_materialization_plans(candidates: List[Dict], reviews: List[Dict]) -> List[Dict]:
    review_map = {r.get("real_patch_generation_review_id", ""): r for r in reviews}
    return [
        build_materialization_plan(c, review_map.get(c.get("real_patch_generation_review_id", ""), None))
        for c in candidates
    ]


def build_materialization_execution_order(plans: List[Dict]) -> List[Dict]:
    """Sort plans by category, risk level, and patch type, producing an execution order."""
    def _sort_key(p):
        return (
            CATEGORY_ORDER.get(p.get("category", ""), 99),
            RISK_ORDER.get(p.get("risk_level", "medium"), 2),
            PATCH_TYPE_ORDER.get(p.get("patch_type", ""),99),
        )

    sorted_plans = sorted(plans, key=_sort_key)
    order = []
    for idx, p in enumerate(sorted_plans):
        order.append({
            "execution_order_id": _stable_id("exec", p["real_patch_materialization_plan_id"], idx),
            "real_patch_materialization_plan_id": p["real_patch_materialization_plan_id"],
            "front_id": p["front_id"],
            "category": p["category"],
            "patch_type": p["patch_type"],
            "risk_level": p["risk_level"],
            "execution_sequence": idx + 1,
            "materialization_allowed_now": False,
            "patch_file_creation_allowed_now": False,
            "git_apply_allowed_now": False,
            "target_file_modification_allowed_now": False,
            "patch_application_allowed_now": False,
        })
    return order


def build_materialization_plan_governance(plans: List[Dict]) -> Dict:
    return {
        "governance_id": _stable_id("gov", len(plans)),
        "status": "materialization_plan_only_not_executable",
        "materialization_plans_count": len(plans),
        "materialization_allowed_now": False,
        "patch_file_creation_allowed_now": False,
        "git_apply_allowed_now": False,
        "target_file_modification_allowed_now": False,
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
        "must_not_modify_target_files": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_materialization_plan(plans: List[Dict], upstream_empty: bool = False) -> Dict:
    result = {
        "ok": len(plans) > 0,
        "materialization_plans_count": len(plans),
        "materialization_allowed_now": False,
        "patch_file_creation_allowed_now": False,
        "git_apply_allowed_now": False,
        "target_file_modification_allowed_now": False,
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
        "timestamp": _now_utc(),
    }

    if upstream_empty:
        result["ok"] = False
        result["upstream_empty"] = True
        result["failure_reason"] = "empty_real_patch_materialization_planning_queue"
        result["recommended_next_action"] = "re_run_real_patch_generation_review_dry_run_to_generate_approved_queue"
    else:
        result["upstream_empty"] = False
        result["functional_dry_run_passed"] = len(plans) > 0
        result["recommended_next_action"] = "operator_review_then_proceed_to_materialization_plan_review_dry_run"

    return result


# ─── helpers ─────────────────────────────────────────────────────────────────


def _token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def _report_md(plans, order, gov, summary) -> str:
    lines = [
        "# Plan de Materializacion de Patch — Dry-Run",
        "",
        "## Resumen",
        f"- Planes de materializacion creados: {summary.get('materialization_plans_count', 0)}",
        f"- Orden de ejecucion: {len(order)}",
        f"- Materializacion permitida ahora: {'SI' if summary.get('materialization_allowed_now') else 'NO'}",
        f"- Creacion de archivos .patch permitida: {'SI' if summary.get('patch_file_creation_allowed_now') else 'NO'}",
        f"- git apply permitido: {'SI' if summary.get('git_apply_allowed_now') else 'NO'}",
        f"- Modificacion de target files permitida: {'SI' if summary.get('target_file_modification_allowed_now') else 'NO'}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Candidatos Recibidos y Planes Creados",
    ]

    for p in plans:
        lines.append(f"### {p['real_patch_materialization_plan_id']}")
        lines.append(f"- Candidato: {p['real_patch_materialization_planning_candidate_id']}")
        lines.append(f"- Revision: {p['real_patch_generation_review_id']}")
        lines.append(f"- Draft: {p['real_patch_draft_id']}")
        lines.append(f"- Front: {p['front_id']}")
        lines.append(f"- Categoria: {p['category']}")
        lines.append(f"- Tipo: {p['patch_type']}")
        lines.append(f"- Estado: {p['plan_status']}")
        lines.append(f"- Riesgo: {p['risk_level']} — {p['risk_notes']}")
        lines.append(f"- Dry-run only: {'SI' if p['dry_run_only'] else 'NO'}")
        lines.append("- Archivos sugeridos (no modificados):")
        for tf in p["target_files_suggested"]:
            lines.append(f"  - {tf}")
        lines.append("- Unidades de materializacion:")
        for u in p["materialization_units"]:
            lines.append(f"  - {u['unit_id']}: {u['description']}")
            lines.append(f"    - Tipo: {u['unit_type']}")
            lines.append(f"    - Target files: {', '.join(u['target_files'])}")
            lines.append(f"    - Permitido ahora: {'SI' if u['allowed_now'] else 'NO'}")
            lines.append(f"    - Restricciones: {', '.join(u['materialization_constraints'])}")
        lines.append(f"- Tests requeridos: {', '.join(p['required_tests'])}")
        lines.append(f"- Criterios de aceptacion: {', '.join(p['acceptance_criteria'])}")
        lines.append(f"- Requiere aprobacion operador: {'SI' if p['operator_approval_packet']['required'] else 'NO'}")
        lines.append(f"- Rollback requerido: {'SI' if p['rollback_plan']['required'] else 'NO'} — {p['rollback_plan']['strategy']}")
        lines.append("")

    lines.extend([
        "## Orden Recomendado",
    ])
    if order:
        for o in order:
            lines.append(f"{o['execution_sequence']}. {o['real_patch_materialization_plan_id']} | {o['front_id']} | {o['category']} | {o['risk_level']}")
    else:
        lines.append("- Ningun plan en orden de ejecucion.")
    lines.append("")

    lines.extend([
        "## Archivos Prohibidos",
    ])
    for f in FORBIDDEN_PATHS:
        lines.append(f"- {f}")
    lines.append("")

    lines.extend([
        "## Gobernanza",
        f"- Estado: {gov['status']}",
        f"- Planes contados: {gov['materialization_plans_count']}",
        f"- Materializacion habilitada: {'SI' if gov['materialization_allowed_now'] else 'NO'}",
        f"- Creacion de archivos .patch habilitada: {'SI' if gov['patch_file_creation_allowed_now'] else 'NO'}",
        f"- git apply habilitado: {'SI' if gov['git_apply_allowed_now'] else 'NO'}",
        f"- Modificacion de target files habilitada: {'SI' if gov['target_file_modification_allowed_now'] else 'NO'}",
        f"- Patch application habilitado: {'SI' if gov['patch_application_allowed_now'] else 'NO'}",
        f"- Patches aplicados: {'SI' if gov['patches_applied'] else 'NO'}",
        f"- Patches staged: {'SI' if gov['patches_staged'] else 'NO'}",
        f"- Requiere aprobacion operador: {'SI' if gov['requires_operator_approval'] else 'NO'}",
        f"- No crear archivos .patch: {'SI' if gov['must_not_create_patch_files'] else 'NO'}",
        f"- No ejecutar git apply: {'SI' if gov['must_not_run_git_apply'] else 'NO'}",
        f"- No modificar target files: {'SI' if gov['must_not_modify_target_files'] else 'NO'}",
        f"- Siguiente frente seguro: {gov['next_safe_front']}",
        "",
        "## Que NO Se Creo",
        "- Archivos .patch: NO",
        "- Diffs aplicables: NO",
        "- Patches aplicados: NO",
        "- Patches staged: NO",
        "- Escrituras a memoria: NO",
        "- Escrituras FAISS: NO",
        "- Promocion: NO",
        "",
        "## Que NO Se Aplico",
        "- Ningun patch fue aplicado a archivos de codigo.",
        "- Ningun archivo objetivo fue modificado.",
        "- Ningun cambio fue commiteado ni pusheado como parte de este frente.",
        "- Ningun plan fue implementado.",
        "",
        "## Que NO Se Stageo",
        "- Ningun archivo .patch.",
        "- Ningun diff aplicable.",
        "- Ningun target file modificado.",
        "",
        "## Por Que Requiere Aprobacion Humana",
        "- Los planes de materializacion no son ejecutables y deben revisarse manualmente.",
        "- La aprobacion del operador NO autoriza crear archivos .patch ni modificar targets.",
        "- Cada plan debe ser revisado individualmente antes de cualquier paso siguiente.",
        "",
        "## Siguiente Paso Recomendado",
        f"- {NEXT_SAFE_FRONT}",
        "",
        "---",
        "Reporte generado en modo dry-run sin mutaciones persistentes.",
    ])
    return "\n".join(lines)


# ─── entry point ──────────────────────────────────────────────────────────────


def run_first_five_real_patch_materialization_plan_dry_run(output_dir=None) -> Dict:
    import sys
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    review_out = str(out / "run_patch_generation_review") if out else None
    review_result = run_first_five_real_patch_generation_review_dry_run(output_dir=review_out)

    artifacts_dir = review_out or review_result.get("output_dir", "tmp_agent/run")
    artifacts = load_materialization_planning_queue_artifacts(artifacts_dir)

    queue = artifacts.get("queue", [])
    upstream_empty = len(queue) == 0

    plans = build_all_materialization_plans(queue, artifacts.get("reviews", []))
    order = build_materialization_execution_order(plans)
    gov = build_materialization_plan_governance(plans)
    summary = summarize_materialization_plan(plans, upstream_empty=upstream_empty)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_materialization_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_materialization_plans.jsonl", "w", encoding="utf-8") as fh:
            for p in plans:
                fh.write(json.dumps(p) + "\n")
        (out / "first_five_real_patch_materialization_execution_order.json").write_text(
            json.dumps(order, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_materialization_plan_governance.json").write_text(
            json.dumps(gov, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_materialization_plan_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _report_md(plans, order, gov, summary)
        (out / "first_five_real_patch_materialization_plan_report.md").write_text(report, encoding="utf-8")

        all_texts = [
            json.dumps(plans), json.dumps(order), json.dumps(gov), json.dumps(summary), report
        ]
        for text in all_texts:
            if _token_leak(text):
                token_leak = True
                break
        summary["token_leak_detected"] = token_leak

    summary["token_leak_detected"] = token_leak
    summary["output_dir"] = str(out) if out else None
    return summary
