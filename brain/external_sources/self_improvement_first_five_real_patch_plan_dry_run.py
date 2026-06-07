"""Real patch plan dry-run for the first five self-improvement fronts.

Takes approved candidates from the previous review front and converts them
into real patch plans with implementation steps, forbidden file lists,
rollback strategies, and execution order.  Nothing is applied, staged,
or written to persistent state.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_patch_generation_review_dry_run import (
    run_first_five_patch_generation_review_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-REVIEW-DRY-RUN-01"

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


def load_real_patch_planning_queue_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    queue = _read_json(out / "first_five_real_patch_planning_queue.json", [])
    reviews = _read_json(out / "first_five_patch_generation_reviews.json", [])
    summary = _read_json(out / "first_five_patch_generation_review_summary.json", {})
    return {
        "queue": queue,
        "reviews": reviews,
        "summary": summary,
        "output_dir": str(out),
    }


def _filter_allowed_targets(targets: List[str]) -> List[str]:
    allowed = []
    for t in targets:
        forbidden = False
        for p in FORBIDDEN_PATHS:
            # Use simple prefix matching for forbidden paths
            if t.startswith(p.rstrip("*")) or t.startswith(p.replace("/", "\\").rstrip("*")):
                forbidden = True
                break
        if not forbidden:
            allowed.append(t)
    return allowed


def build_real_patch_plan(
    candidate: Dict[str, Any],
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate_id = candidate.get("real_patch_planning_candidate_id", "")
    review_id = candidate.get("generation_review_id", "")
    proposal_id = candidate.get("patch_proposal_id", "")
    front_id = candidate.get("front_id", "")
    category = candidate.get("category", "")
    patch_type = candidate.get("patch_type", "")
    risk = candidate.get("risk_level", "medium")
    risk_notes = candidate.get("risk_notes", "")
    targets = candidate.get("target_files_suggested", [])
    required_tests = candidate.get("required_tests", [])
    acceptance_criteria = candidate.get("acceptance_criteria", [])

    # Enrich from review if fields are empty
    if review:
        if not targets:
            targets = review.get("target_files_suggested", review.get("target_files", []))
        if not required_tests:
            required_tests = review.get("required_tests", [])
        if not acceptance_criteria:
            acceptance_criteria = review.get("acceptance_criteria", [])
        if not risk or risk == "medium":
            risk = review.get("risk_level", risk)
        if not risk_notes:
            risk_notes = review.get("risk_notes", "")
        if not category:
            category = review.get("category", "")
        if not patch_type:
            patch_type = review.get("patch_type", "")

    # Fallback defaults if still missing
    if not targets:
        targets = ["tests/smoke/*"]
    if not required_tests:
        required_tests = ["python -m pytest tests/smoke -q"]
    if not acceptance_criteria:
        acceptance_criteria = ["operator must define acceptance criteria before implementation"]
    if not risk_notes:
        risk_notes = "operator review required before implementation"

    allowed = _filter_allowed_targets(targets)

    steps = []
    for idx, target in enumerate(allowed):
        steps.append({
            "step_id": _stable_id("step", candidate_id, idx),
            "description": f"Plan implementation for {target}",
            "allowed_now": False,
            "expected_change_type": _infer_change_type(patch_type),
        })

    if not steps:
        steps.append({
            "step_id": _stable_id("step", candidate_id, "no_target"),
            "description": "No allowed target files remaining after forbidden filter",
            "allowed_now": False,
            "expected_change_type": "policy_only",
        })

    return {
        "real_patch_plan_id": _stable_id("real_patch_plan", candidate_id),
        "real_patch_planning_candidate_id": candidate_id,
        "generation_review_id": review_id,
        "patch_proposal_id": proposal_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "plan_status": "real_patch_plan_dry_run_only",
        "implementation_allowed_now": False,
        "patch_application_allowed_now": False,
        "patch_generated_for_application": False,
        "patch_applied": False,
        "patch_staged": False,
        "target_files_suggested": targets,
        "target_files_allowed_for_future_patch": allowed,
        "files_forbidden_to_modify": FORBIDDEN_PATHS,
        "implementation_steps": steps,
        "required_tests": required_tests,
        "acceptance_criteria": acceptance_criteria,
        "rollback_plan": {
            "required": True,
            "strategy": "single_commit_revert_or_delete_new_files_only",
            "preserve_dirty_preexisting_files": True,
        },
        "risk_level": risk,
        "risk_notes": risk_notes,
        "operator_approval_required": True,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": now_utc(),
    }


def _infer_change_type(patch_type: str) -> str:
    mapping = {
        "test_patch": "test_only",
        "harness_patch": "harness_only",
        "policy_patch": "policy_only",
    }
    return mapping.get(patch_type, "policy_only")


def build_all_real_patch_plans(
    candidates: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    review_map = {r.get("generation_review_id", ""): r for r in reviews}
    return [build_real_patch_plan(c, review_map.get(c.get("generation_review_id", ""), None)) for c in candidates]


def build_real_patch_execution_order(plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
            "execution_order_id": _stable_id("exec_order", p["real_patch_plan_id"], idx),
            "real_patch_plan_id": p["real_patch_plan_id"],
            "front_id": p["front_id"],
            "category": p["category"],
            "patch_type": p["patch_type"],
            "risk_level": p["risk_level"],
            "execution_sequence": idx + 1,
            "implementation_allowed_now": False,
            "patch_application_allowed_now": False,
        })
    return order


def build_real_patch_plan_governance(plans: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "governance_id": _stable_id("real_patch_plan_governance", len(plans)),
        "status": "real_patch_plan_only_not_executable",
        "plans_count": len(plans),
        "implementation_allowed_now": False,
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
        "must_run_tests_before_commit": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_real_patch_plan(plans: List[Dict[str, Any]], order: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "ok": len(plans) > 0,
        "plans_count": len(plans),
        "execution_order_count": len(order),
        "implementation_allowed_now": False,
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


def run_first_five_real_patch_plan_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    # Use output_dir directly; let upstream functions manage their own subdirectories
    review_out = str(out) if out else None
    # Check if upstream artifacts already exist AND are non-empty to avoid regenerating
    if review_out:
        review_path = Path(review_out)
        queue_path = review_path / "first_five_real_patch_planning_queue.json"
        if queue_path.exists():
            # Use existing upstream artifacts only if queue is non-empty
            existing_queue = _read_json(queue_path, [])
            if existing_queue:
                artifacts = load_real_patch_planning_queue_artifacts(review_out)
            else:
                # Queue file exists but is empty (stale from previous run)
                # Clear the upstream directory to force regeneration, ignoring errors
                import shutil
                if review_path.exists():
                    shutil.rmtree(review_path, ignore_errors=True)
                review_result = run_first_five_patch_generation_review_dry_run(output_dir=review_out)
                artifacts = load_real_patch_planning_queue_artifacts(review_out or review_result.get("output_dir", "tmp_agent/run"))
        else:
            # Generate upstream artifacts
            review_result = run_first_five_patch_generation_review_dry_run(output_dir=review_out)
            artifacts = load_real_patch_planning_queue_artifacts(review_out or review_result.get("output_dir", "tmp_agent/run"))
    else:
        review_result = run_first_five_patch_generation_review_dry_run(output_dir=review_out)
        artifacts = load_real_patch_planning_queue_artifacts(review_out or review_result.get("output_dir", "tmp_agent/run"))

    plans = build_all_real_patch_plans(artifacts["queue"], artifacts["reviews"])
    order = build_real_patch_execution_order(plans)
    governance = build_real_patch_plan_governance(plans)
    summary = summarize_real_patch_plan(plans, order)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_plans.json").write_text(
            json.dumps(plans, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_plans.jsonl", "w", encoding="utf-8") as fh:
            for p in plans:
                fh.write(json.dumps(p) + "\n")
        (out / "first_five_real_patch_execution_order.json").write_text(
            json.dumps(order, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_plan_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_plan_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(plans, order, governance, summary)
        (out / "first_five_real_patch_plan_report.md").write_text(report, encoding="utf-8")

        all_texts = [json.dumps(plans), json.dumps(order), json.dumps(governance), json.dumps(summary), report]
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
    plans: List[Dict[str, Any]],
    order: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Reporte de Plan Real de Patch (Dry-Run)",
        "",
        "## Resumen",
        f"- Planes creados: {summary.get('plans_count', 0)}",
        f"- Orden de ejecución: {summary.get('execution_order_count', 0)}",
        f"- Implementacion permitida ahora: {'SI' if summary.get('implementation_allowed_now') else 'NO'}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Candidatos Recibidos",
    ]
    for p in plans:
        lines.append(f"### {p['real_patch_plan_id']}")
        lines.append(f"- Candidato: {p['real_patch_planning_candidate_id']}")
        lines.append(f"- Categoria: {p['category']}")
        lines.append(f"- Tipo de patch: {p['patch_type']}")
        lines.append(f"- Estado: {p['plan_status']}")
        lines.append(f"- Riesgo: {p['risk_level']}")
        lines.append(f"- Archivos sugeridos: {', '.join(p['target_files_suggested'])}")
        lines.append(f"- Archivos permitidos: {', '.join(p['target_files_allowed_for_future_patch'])}")
        lines.append(f"- Tests requeridos: {', '.join(p['required_tests'])}")
        lines.append(f"- Criterios de aceptacion: {', '.join(p['acceptance_criteria'])}")
        lines.append(f"- Requiere aprobacion operador: {'SI' if p['operator_approval_required'] else 'NO'}")
        lines.append(f"- Rollback requerido: {'SI' if p['rollback_plan']['required'] else 'NO'}")
        lines.append("")

    lines.append("## Orden Recomendado")
    if order:
        for o in order:
            lines.append(f"{o['execution_sequence']}. {o['real_patch_plan_id']} | {o['front_id']} | {o['category']} | {o['risk_level']}")
    else:
        lines.append("- Ningun plan en orden de ejecucion.")
    lines.append("")

    lines.append("## Archivos Prohibidos")
    for f in FORBIDDEN_PATHS:
        lines.append(f"- {f}")
    lines.append("")

    lines.append("## Gobernanza")
    lines.append(f"- Estado: {governance['status']}")
    lines.append(f"- Planes contados: {governance['plans_count']}")
    lines.append(f"- Ejecucion habilitada: {'SI' if governance['implementation_allowed_now'] else 'NO'}")
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
    lines.append("")

    lines.append("## Siguiente Paso Recomendado")
    lines.append("- SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-PLAN-REVIEW-DRY-RUN-01")
    lines.append("")
    lines.append("---")
    lines.append("Reporte generado en modo dry-run sin mutaciones persistentes.")
    return "\n".join(lines)
