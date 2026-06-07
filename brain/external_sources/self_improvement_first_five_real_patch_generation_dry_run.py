"""Real patch generation dry-run for the first five self-improvement fronts.

Generates inert patch draft proposals for human review from the approved
real patch generation queue. Does not apply, stage, or create applicable
patches. Does not modify target files, write memory/FAISS, or promote.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.self_improvement_first_five_real_patch_generation_plan_review_dry_run import (
    run_first_five_real_patch_generation_plan_review_dry_run,
)

NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-REAL-PATCH-GENERATION-REVIEW-DRY-RUN-01"

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


def load_real_patch_generation_queue_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    queue = _read_json(out / "first_five_real_patch_generation_queue.json", [])
    reviews = _read_json(out / "first_five_real_patch_generation_plan_reviews.json", [])
    summary = _read_json(out / "first_five_real_patch_generation_plan_review_summary.json", {})
    governance = _read_json(out / "first_five_real_patch_generation_plan_review_governance.json", {})
    return {
        "queue": queue,
        "reviews": reviews,
        "summary": summary,
        "governance": governance,
        "output_dir": str(out),
    }


def generate_inert_patch_draft(
    candidate: Dict[str, Any],
    review: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate_id = candidate.get("real_patch_generation_candidate_id", "")
    plan_review_id = candidate.get("real_patch_generation_plan_review_id", "")
    plan_id = candidate.get("real_patch_generation_plan_id", "")
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

    draft_id = _stable_id("draft", candidate_id, plan_review_id)

    pseudo_diff_lines = [
        "DRY-RUN ONLY — NOT A GIT PATCH",
        "",
        "This is an inert human-review draft.",
        "Do not run git apply.",
        "Do not paste into patch application tools.",
        "",
        f"Front: {front_id}",
        f"Category: {category}",
        f"Patch type: {patch_type}",
        f"Risk level: {risk_level}",
        "",
        "Suggested target files (metadata only — not modified):",
    ]
    for tf in target_files_suggested:
        pseudo_diff_lines.append(f"  - {tf}")
    pseudo_diff_lines.extend([
        "",
        "Proposed change direction (inert description):",
        f"  - {risk_notes}",
        "",
        "Required tests:",
    ])
    for t in target_files:
        pseudo_diff_lines.append(f"  - {t}")
    pseudo_diff_lines.extend([
        "",
        "Acceptance criteria:",
    ])
    for ac in acceptance_criteria:
        pseudo_diff_lines.append(f"  - {ac}")
    pseudo_diff_lines.extend([
        "",
        "Rollback: discard inert draft artifacts only; preserve all preexisting files.",
        "",
        "Safety flags:",
        "  - dry_run_only: true",
        "  - applicable: false",
        "  - not_for_git_apply: true",
        "  - memory_write_allowed: false",
        "  - faiss_write_allowed: false",
        "  - real_write_allowed: false",
        "  - promotion_allowed: false",
    ])

    pseudo_diff_text = "\n".join(pseudo_diff_lines)

    return {
        "real_patch_draft_id": draft_id,
        "real_patch_generation_candidate_id": candidate_id,
        "real_patch_generation_plan_review_id": plan_review_id,
        "real_patch_generation_plan_id": plan_id,
        "front_id": front_id,
        "category": category,
        "patch_type": patch_type,
        "draft_status": "inert_patch_draft_dry_run_only",
        "dry_run_only": True,
        "applicable": False,
        "not_for_git_apply": True,
        "patch_generation_allowed_now": False,
        "diff_generation_allowed_now": False,
        "patch_application_allowed_now": False,
        "real_patch_application_allowed_now": False,
        "patches_generated_for_application": False,
        "patches_applied": False,
        "patches_staged": False,
        "target_files_suggested": target_files_suggested,
        "target_files_not_modified": target_files_suggested,
        "pseudo_diff_text": pseudo_diff_text,
        "pseudo_diff_is_applicable": False,
        "pseudo_diff_header": "DRY-RUN ONLY — NOT A GIT PATCH",
        "human_review_required": True,
        "operator_approval_packet": {
            "required": True,
            "approval_scope": "inert_patch_draft_only",
            "approval_does_not_allow_patch_application": True,
            "approval_does_not_allow_git_apply": True,
            "must_review_target_files": True,
            "must_review_tests": True,
            "must_review_rollback": True,
        },
        "required_tests": target_files,
        "acceptance_criteria": acceptance_criteria,
        "rollback_plan": {
            "required": True,
            "strategy": "discard_inert_draft_artifacts_only",
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


def generate_all_inert_patch_drafts(
    candidates: List[Dict[str, Any]],
    reviews: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    review_map = {r.get("real_patch_generation_plan_review_id", ""): r for r in reviews}
    return [
        generate_inert_patch_draft(c, review_map.get(c.get("real_patch_generation_plan_review_id", ""), None))
        for c in candidates
    ]


def build_real_patch_generation_governance(drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "governance_id": _stable_id("gen_governance", len(drafts)),
        "status": "inert_patch_generation_dry_run_only_not_executable",
        "generated_patch_drafts_count": len(drafts),
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


def summarize_real_patch_generation(
    drafts: List[Dict[str, Any]],
    upstream_empty: bool = False,
) -> Dict[str, Any]:
    result = {
        "ok": len(drafts) > 0,
        "generated_patch_drafts_count": len(drafts),
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
        result["failure_reason"] = "empty_real_patch_generation_queue"
        result["recommended_next_action"] = "re_run_real_patch_generation_plan_review_to_generate_approved_queue"
    else:
        result["upstream_empty"] = False
        result["functional_dry_run_passed"] = len(drafts) > 0
        result["recommended_next_action"] = "operator_review_then_proceed_to_patch_generation_review_dry_run"

    return result


def _check_token_leak(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def _build_report_md(
    drafts: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Generacion de Patch Drafts Inertes — Dry-Run",
        "",
        "## Resumen",
        f"- Candidatos recibidos: {summary.get('generated_patch_drafts_count', 0)}",
        f"- Drafts creados: {summary.get('generated_patch_drafts_count', 0)}",
        f"- Generacion permitida ahora: {'SI' if summary.get('patch_generation_allowed_now') else 'NO'}",
        f"- Diff generation permitida ahora: {'SI' if summary.get('diff_generation_allowed_now') else 'NO'}",
        f"- Aplicacion de patch permitida ahora: {'SI' if summary.get('patch_application_allowed_now') else 'NO'}",
        f"- Fuga de token detectada: {'SI' if summary.get('token_leak_detected') else 'NO'}",
        "",
        "## Patch Drafts Creados",
    ]
    for d in drafts:
        lines.append(f"### {d['real_patch_draft_id']}")
        lines.append(f"- Front: {d['front_id']}")
        lines.append(f"- Categoria: {d['category']}")
        lines.append(f"- Tipo: {d['patch_type']}")
        lines.append(f"- Estado: {d['draft_status']}")
        lines.append(f"- Riesgo: {d['risk_level']} — {d['risk_notes']}")
        lines.append(f"- Revision humana requerida: {'SI' if d['human_review_required'] else 'NO'}")
        lines.append("- Archivos sugeridos (no modificados):")
        for tf in d["target_files_suggested"]:
            lines.append(f"  - {tf}")
        lines.append("- Tests requeridos:")
        for t in d["required_tests"]:
            lines.append(f"  - {t}")
        lines.append("- Criterios de aceptacion:")
        for ac in d["acceptance_criteria"]:
            lines.append(f"  - {ac}")
        lines.append("- Pseudo-diff inerte:")
        lines.append(f"  ```")
        for pdl in d["pseudo_diff_text"].split("\n")[:8]:
            lines.append(f"  {pdl}")
        lines.append(f"  ... ({len(d['pseudo_diff_text'].split(chr(10)))} lines total)")
        lines.append(f"  ```")
        lines.append("")

    lines.extend([
        "## Gobernanza",
        f"- Estado: {governance['status']}",
        f"- Drafts contados: {governance['generated_patch_drafts_count']}",
        f"- Patch generation habilitada: {'SI' if governance['patch_generation_allowed_now'] else 'NO'}",
        f"- Diff generation habilitada: {'SI' if governance['diff_generation_allowed_now'] else 'NO'}",
        f"- Patch application habilitado: {'SI' if governance['patch_application_allowed_now'] else 'NO'}",
        f"- Patches aplicados: {'SI' if governance['patches_applied'] else 'NO'}",
        f"- Patches staged: {'SI' if governance['patches_staged'] else 'NO'}",
        f"- Requiere aprobacion operador: {'SI' if governance['requires_operator_approval'] else 'NO'}",
        f"- No crear archivos .patch: {'SI' if governance['must_not_create_patch_files'] else 'NO'}",
        f"- No ejecutar git apply: {'SI' if governance['must_not_run_git_apply'] else 'NO'}",
        f"- Siguiente frente seguro: {governance['next_safe_front']}",
        "",
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


def run_first_five_real_patch_generation_dry_run(
    output_dir: str | None = None,
) -> Dict[str, Any]:
    out: Optional[Path] = Path(output_dir) if output_dir else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    review_out = str(out / "run_patch_gen_plan_review") if out else None
    review_result = run_first_five_real_patch_generation_plan_review_dry_run(output_dir=review_out)

    artifacts_dir = review_out or review_result.get("output_dir", "tmp_agent/run")
    artifacts = load_real_patch_generation_queue_artifacts(artifacts_dir)

    queue = artifacts.get("queue", [])
    upstream_empty = len(queue) == 0

    drafts = generate_all_inert_patch_drafts(queue, artifacts.get("reviews", []))
    governance = build_real_patch_generation_governance(drafts)
    summary = summarize_real_patch_generation(drafts, upstream_empty=upstream_empty)

    token_leak = False
    if out is not None:
        (out / "first_five_real_patch_drafts.json").write_text(
            json.dumps(drafts, indent=2), encoding="utf-8"
        )
        with open(out / "first_five_real_patch_drafts.jsonl", "w", encoding="utf-8") as fh:
            for d in drafts:
                fh.write(json.dumps(d) + "\n")
        (out / "first_five_real_patch_generation_governance.json").write_text(
            json.dumps(governance, indent=2), encoding="utf-8"
        )
        (out / "first_five_real_patch_generation_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        report = _build_report_md(drafts, governance, summary)
        (out / "first_five_real_patch_generation_report.md").write_text(report, encoding="utf-8")

        all_texts = [json.dumps(drafts), json.dumps(governance), json.dumps(summary), report]
        for text in all_texts:
            if _check_token_leak(text):
                token_leak = True
                break
        summary["token_leak_detected"] = token_leak
    summary["token_leak_detected"] = token_leak
    summary["output_dir"] = str(out) if out else None
    return summary
