"""Patch generation proposal dry-run for first-five self-improvement candidates.

Generates reviewable patch proposal metadata and non-applicable pseudo-diffs as
artifacts only. It never applies patches, stages generated content, modifies
suggested target files, writes memory/FAISS, promotes knowledge, or touches
runtime/chat/trading/B8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_patch_plan_review_dry_run import (
    run_first_five_patch_plan_review_dry_run,
)

TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
)

FORBIDDEN_FILES = [
    "memory/semantic/*",
    "tmp_agent/strategies/*",
    "trading/*",
    "B8/*",
]
NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-GENERATION-REVIEW-DRY-RUN-01"

CATEGORY_TARGETS = {
    "evaluation_gate_gap": ["tests/smoke/*"],
    "patch_hygiene_gap": ["brain/external_sources/*", "tests/smoke/*"],
    "orchestration_trace_gap": ["brain/external_sources/*", "tests/smoke/*"],
    "retrieval_provenance_gap": ["brain/external_sources/*", "tests/smoke/*"],
    "security_supply_chain_gap": ["brain/external_sources/*", "tests/smoke/*"],
}
CATEGORY_RISK = {
    "security_supply_chain_gap": ("medium", "Security and supply-chain proposals require extra operator scrutiny."),
    "evaluation_gate_gap": ("low", "Test-gate proposal is bounded to test/harness artifacts."),
    "patch_hygiene_gap": ("medium", "Patch hygiene work can affect future commit behavior."),
    "orchestration_trace_gap": ("medium", "Trace proposals must avoid chain-of-thought exposure."),
    "retrieval_provenance_gap": ("medium", "Retrieval proposals must remain read-only and provenance-bound."),
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


def load_patch_candidate_queue_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "candidate_queue": _read_json(out / "first_five_patch_candidate_queue.json", []),
        "reviews": _read_json(out / "first_five_patch_plan_reviews.json", []),
        "summary": _read_json(out / "first_five_patch_plan_review_summary.json", {}),
        "output_dir": str(out),
    }


def _review_by_id(reviews: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(review.get("review_id", "")): review for review in reviews}


def _change_summary(candidate: Dict[str, Any], review: Dict[str, Any] | None) -> str:
    category = candidate.get("category", "unknown")
    front = candidate.get("front_id", "unknown_front")
    decision_note = "approved dry-run candidate"
    if review:
        decision_note = str(review.get("decision", decision_note))
    return f"Create a small, reviewable {category} patch plan for {front} based on {decision_note}; keep it dry-run only."


def build_patch_proposal(candidate: Dict[str, Any], review: Dict[str, Any] | None = None) -> Dict[str, Any]:
    category = candidate.get("category", review.get("category", "unknown") if review else "unknown")
    risk_level, risk_notes = CATEGORY_RISK.get(category, ("medium", "Requires operator review before any implementation."))
    required_tests = list(candidate.get("required_tests") or (review or {}).get("required_tests", []))
    acceptance_criteria = list(candidate.get("acceptance_criteria") or (review or {}).get("acceptance_criteria", []))
    target_files = list(CATEGORY_TARGETS.get(category, ["brain/external_sources/*", "tests/smoke/*"]))
    proposal_id = _stable_id("patch_proposal", candidate.get("patch_candidate_id", ""), candidate.get("patch_plan_id", ""))
    return {
        "patch_proposal_id": proposal_id,
        "patch_candidate_id": candidate.get("patch_candidate_id", ""),
        "review_id": candidate.get("review_id", ""),
        "patch_plan_id": candidate.get("patch_plan_id", ""),
        "front_id": candidate.get("front_id", ""),
        "category": category,
        "patch_type": candidate.get("patch_type", "harness_patch"),
        "proposal_status": "dry_run_patch_proposal_only",
        "target_files_suggested": target_files,
        "files_forbidden_to_modify": list(FORBIDDEN_FILES),
        "proposed_change_summary": _change_summary(candidate, review),
        "pseudo_diff_summary": "Non-applicable textual proposal only; contains no git diff syntax and must not be applied automatically.",
        "pseudo_diff_is_applicable": False,
        "pseudo_diff_generated": True,
        "patch_applied": False,
        "patch_staged": False,
        "operator_review_required": True,
        "required_tests": required_tests,
        "acceptance_criteria": acceptance_criteria,
        "rollback_instructions": [
            "If future implementation is approved, isolate it in one small commit.",
            "Revert the single future commit or delete only newly created files if validation fails.",
            "Preserve all preexisting dirty files and unrelated untracked files.",
        ],
        "risk_level": risk_level,
        "risk_notes": risk_notes,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": now_utc(),
    }


def build_all_patch_proposals(candidates: List[Dict[str, Any]], reviews: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reviews_by_id = _review_by_id(reviews)
    return [build_patch_proposal(candidate, reviews_by_id.get(candidate.get("review_id", ""))) for candidate in candidates]


def render_dry_run_pseudo_diff(proposal: Dict[str, Any]) -> str:
    lines = [
        "--- DRY RUN PATCH PROPOSAL ONLY ---",
        "status: not_applied",
        "status: not_staged",
        "operator_review_required: true",
        "pseudo_diff_is_applicable: false",
        "",
        "NO APLICAR AUTOMATICAMENTE",
        "NO ES UN DIFF EJECUTABLE",
        "REQUIERE APROBACION DEL OPERADOR",
        "",
        "Suggested target files:",
    ]
    lines.extend(f"- {target}" for target in proposal.get("target_files_suggested", []))
    lines.extend(["", "Forbidden files:"])
    lines.extend(f"- {path}" for path in proposal.get("files_forbidden_to_modify", []))
    lines.extend(["", "Proposed changes:", f"- {proposal.get('proposed_change_summary', '')}"])
    lines.extend(["", "Required tests:"])
    lines.extend(f"- {test}" for test in proposal.get("required_tests", []) or ["operator-defined tests required"])
    lines.extend(["", "Acceptance criteria:"])
    lines.extend(f"- {criterion}" for criterion in proposal.get("acceptance_criteria", []) or ["operator-defined acceptance criteria required"])
    lines.extend(["", "Rollback:"])
    lines.extend(f"- {step}" for step in proposal.get("rollback_instructions", []))
    lines.extend(
        [
            "",
            "Safety flags:",
            "- dry_run_patch_proposal_only: true",
            "- not_applied: true",
            "- not_staged: true",
            "- memory_write_allowed: false",
            "- faiss_write_allowed: false",
            "- real_write_allowed: false",
            "- promotion_allowed: false",
        ]
    )
    return "\n".join(lines) + "\n"


def build_operator_review_packet(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "packet_id": _stable_id("operator_review_packet", len(proposals), "first_five_patch_generation"),
        "status": "operator_review_required",
        "proposals_count": len(proposals),
        "execution_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_applied": False,
        "patches_staged": False,
        "requires_operator_approval": True,
        "recommended_review_order": [proposal["patch_proposal_id"] for proposal in proposals],
        "review_questions": [
            "Is the proposed target scope narrow enough for one future commit?",
            "Are the required tests sufficient before implementation?",
            "Is rollback clear and compatible with the dirty worktree?",
            "Should this proposal proceed to a real patch planning prompt?",
        ],
        "approval_options": [
            "approve_one_for_real_patch_planning",
            "request_scope_reduction",
            "request_more_tests",
            "reject",
        ],
        "writes_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "promotion_allowed": False,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_patch_generation(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "ok": len(proposals) >= 1,
        "proposals_count": len(proposals),
        "pseudo_diffs_created": len(proposals),
        "operator_review_required": True,
        "execution_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_applied": False,
        "patches_staged": False,
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


def _render_report(proposals: List[Dict[str, Any]], packet: Dict[str, Any], summary: Dict[str, Any]) -> str:
    lines = [
        "# Generacion de propuestas de patch - Dry Run",
        "",
        "## 1. Candidatos aprobados",
    ]
    for proposal in proposals:
        lines.append(f"- {proposal['front_id']} / {proposal['patch_candidate_id']}")
    lines.extend(["", "## 2. Propuestas generadas"])
    for proposal in proposals:
        lines.extend(
            [
                f"### {proposal['patch_proposal_id']}",
                f"- Estado: {proposal['proposal_status']}",
                f"- Categoria: {proposal['category']}",
                f"- Tipo: {proposal['patch_type']}",
                f"- Resumen: {proposal['proposed_change_summary']}",
                f"- Riesgo: {proposal['risk_level']} - {proposal['risk_notes']}",
                "- Archivos sugeridos:",
            ]
        )
        lines.extend(f"  - {target}" for target in proposal["target_files_suggested"])
        lines.append("- Archivos prohibidos:")
        lines.extend(f"  - {path}" for path in proposal["files_forbidden_to_modify"])
        lines.append("- Tests requeridos:")
        lines.extend(f"  - {test}" for test in proposal["required_tests"])
        lines.append("- Rollback:")
        lines.extend(f"  - {step}" for step in proposal["rollback_instructions"])
    lines.extend(
        [
            "",
            "## 3. Que NO se aplico",
            "- No se aplicaron patches.",
            "- No se modificaron archivos objetivo sugeridos.",
            "- No se escribio memory/semantic ni FAISS.",
            "- No se promovio conocimiento.",
            "- No se toco trading ni B8.",
            "",
            "## 4. Que NO se stageo",
            "- No se stagearon pseudo-diffs ni evidencia.",
            "- No se stageo ningun archivo objetivo sugerido.",
            "",
            "## 5. Por que requiere revision humana",
            "- Los pseudo-diffs no son ejecutables y deben revisarse manualmente.",
            "- La aprobacion del operador es obligatoria antes de cualquier plan de patch real.",
            "",
            "## 6. Operator review packet",
            f"- status: {packet['status']}",
            f"- proposals_count: {packet['proposals_count']}",
            f"- patch_application_allowed_now: {packet['patch_application_allowed_now']}",
            "",
            "## 7. Resumen",
            f"- proposals_count: {summary['proposals_count']}",
            f"- pseudo_diffs_created: {summary['pseudo_diffs_created']}",
            f"- patches_applied: {summary['patches_applied']}",
            f"- patches_staged: {summary['patches_staged']}",
            "",
            "## 8. Siguiente paso recomendado",
            NEXT_SAFE_FRONT,
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    patterns = ["first_five_patch_generation*", "pseudo_diffs/*.txt"]
    for pattern in patterns:
        for path in output_dir.glob(pattern):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                if any(marker in text for marker in TOKEN_MARKERS):
                    return True
    return False


def run_first_five_patch_generation_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_patch_generation_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    review_dir = out / "run_patch_plan_review"
    review_result = run_first_five_patch_plan_review_dry_run(str(review_dir))
    artifacts = load_patch_candidate_queue_artifacts(str(review_dir))
    candidates = artifacts.get("candidate_queue", [])
    reviews = artifacts.get("reviews", [])
    proposals = build_all_patch_proposals(candidates, reviews)
    packet = build_operator_review_packet(proposals)
    summary = summarize_patch_generation(proposals)
    summary.update(
        {
            "review_result": review_result,
            "approved_candidates": len(candidates),
            "packet_status": packet["status"],
            "output_dir": str(out),
        }
    )

    pseudo_dir = out / "pseudo_diffs"
    pseudo_dir.mkdir(parents=True, exist_ok=True)
    for proposal in proposals:
        (pseudo_dir / f"{proposal['patch_proposal_id']}.txt").write_text(
            render_dry_run_pseudo_diff(proposal), encoding="utf-8"
        )

    (out / "first_five_patch_generation_proposals.json").write_text(json.dumps(proposals, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_patch_generation_proposals.jsonl", proposals)
    (out / "first_five_patch_generation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "first_five_patch_generation_operator_review_packet.json").write_text(
        json.dumps(packet, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_generation_report.md").write_text(
        _render_report(proposals, packet, summary), encoding="utf-8"
    )

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak and (len(proposals) >= 1 if len(candidates) > 0 else True),
        "approved_candidates": len(candidates),
        "proposals_count": len(proposals),
        "pseudo_diffs_created": len(proposals),
        "operator_review_required": True,
        "execution_allowed_now": False,
        "patch_application_allowed_now": False,
        "patches_applied": False,
        "patches_staged": False,
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
