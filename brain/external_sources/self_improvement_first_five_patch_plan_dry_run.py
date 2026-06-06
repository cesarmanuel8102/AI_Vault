"""Patch plan dry-run for first-five self-improvement recommendations.

This module turns dry-run patch recommendations into reviewable patch plans. It
never generates applicable diffs, applies patches, modifies runtime/chat, writes
memory/FAISS, promotes knowledge, or touches trading/B8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_patch_recommendation_dry_run import (
    run_first_five_patch_recommendation_dry_run,
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

CATEGORY_PRIORITY = {
    "security_supply_chain_gap": 1,
    "evaluation_gate_gap": 2,
    "patch_hygiene_gap": 3,
    "orchestration_trace_gap": 4,
    "retrieval_provenance_gap": 5,
    "benchmark_design_gap": 6,
}

SEVERITY_PRIORITY = {"high": 1, "medium": 2, "low": 3}
SCOPE_PRIORITY = {"small": 1, "medium": 2, "large": 3}
EXPECTED_CHANGE_TYPE = {
    "policy_patch": "policy_only",
    "test_patch": "test_only",
    "harness_patch": "harness_only",
    "runtime_readonly_patch": "runtime_readonly_only",
    "documentation_patch": "docs_only",
}
NEXT_SAFE_FRONT = "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-REVIEW-DRY-RUN-01"


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


def load_patch_recommendation_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "recommendations": _read_json(out / "first_five_patch_recommendations.json", []),
        "summary": _read_json(out / "first_five_patch_recommendation_summary.json", {}),
        "roadmap": _read_json(out / "first_five_patch_recommendation_roadmap.json", {}),
        "output_dir": str(out),
    }


def _normalize_patch_type(patch_type: str) -> str:
    allowed = {
        "policy_patch",
        "test_patch",
        "harness_patch",
        "runtime_readonly_patch",
        "documentation_patch",
    }
    return patch_type if patch_type in allowed else "harness_patch"


def _step_id(recommendation_id: str, index: int, description: str) -> str:
    return _stable_id("patch_plan_step", recommendation_id, index, description)


def build_patch_plan_item(recommendation: Dict[str, Any]) -> Dict[str, Any]:
    recommendation_id = recommendation.get("recommendation_id", "")
    patch_type = _normalize_patch_type(recommendation.get("recommended_patch_type", "harness_patch"))
    change_type = EXPECTED_CHANGE_TYPE[patch_type]
    implementation_steps = []
    for index, description in enumerate(recommendation.get("implementation_steps", []), start=1):
        implementation_steps.append(
            {
                "step_id": _step_id(recommendation_id, index, description),
                "description": description,
                "expected_change_type": change_type,
                "allowed_now": False,
            }
        )
    return {
        "patch_plan_id": _stable_id("patch_plan", recommendation_id, recommendation.get("front_id", "")),
        "recommendation_id": recommendation_id,
        "front_id": recommendation.get("front_id", ""),
        "benchmark_id": recommendation.get("benchmark_id", ""),
        "category": recommendation.get("category", "benchmark_design_gap"),
        "severity": recommendation.get("severity", "medium"),
        "title": recommendation.get("title", "Patch plan requires review"),
        "plan_status": "planned_not_executed",
        "patch_type": patch_type,
        "execution_priority": CATEGORY_PRIORITY.get(recommendation.get("category", "benchmark_design_gap"), 6),
        "recommended_scope": recommendation.get("recommended_scope", "medium"),
        "target_files_suggested": list(recommendation.get("target_files_suggested", [])),
        "files_forbidden_to_modify": list(recommendation.get("files_forbidden_to_modify", FORBIDDEN_FILES)) or list(FORBIDDEN_FILES),
        "implementation_steps": implementation_steps,
        "required_tests": list(recommendation.get("required_tests", [])),
        "acceptance_criteria": list(recommendation.get("acceptance_criteria", [])),
        "rollback_plan": {
            "required": True,
            "strategy": "revert_single_commit_or_delete_new_files",
            "must_preserve_existing_dirty_state": True,
        },
        "risk_assessment": {
            "risk_level": recommendation.get("risk_level", "medium"),
            "risk_notes": recommendation.get("risk_notes", "Requires review before implementation."),
            "blocked_until_operator_approval": True,
        },
        "execution_allowed_now": False,
        "operator_approval_required": True,
        "auto_apply_allowed": False,
        "patch_generated": False,
        "patch_applied": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "created_at": now_utc(),
    }


def build_all_patch_plan_items(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [build_patch_plan_item(recommendation) for recommendation in recommendations]


def _sort_key(item: Dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        CATEGORY_PRIORITY.get(item.get("category", "benchmark_design_gap"), 6),
        SEVERITY_PRIORITY.get(item.get("severity", "medium"), 2),
        SCOPE_PRIORITY.get(item.get("recommended_scope", "medium"), 2),
        item.get("patch_plan_id", ""),
    )


def build_patch_plan_execution_order(plan_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = []
    for index, item in enumerate(sorted(plan_items, key=_sort_key), start=1):
        ordered_item = dict(item)
        ordered_item["execution_priority"] = index
        ordered_item["execution_allowed_now"] = False
        ordered.append(ordered_item)
    return ordered


def build_patch_plan_governance(plan_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "governance_id": _stable_id("patch_plan_governance", len(plan_items), "first_five"),
        "status": "plan_only_not_executable",
        "plan_items": len(plan_items),
        "execution_allowed_now": False,
        "requires_operator_approval": True,
        "auto_apply_allowed": False,
        "patches_generated": False,
        "patches_applied": False,
        "writes_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "must_use_small_commits": True,
        "must_separate_code_and_ledger_commits": True,
        "must_run_tests_before_commit": True,
        "must_preserve_dirty_preexisting_files": True,
        "next_safe_front": NEXT_SAFE_FRONT,
    }


def summarize_patch_plan(plan_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in plan_items:
        severity = item.get("severity", "medium")
        counts[severity] = counts.get(severity, 0) + 1
    return {
        "ok": len(plan_items) >= 1,
        "plan_items": len(plan_items),
        "high_priority_count": counts.get("high", 0),
        "medium_priority_count": counts.get("medium", 0),
        "low_priority_count": counts.get("low", 0),
        "execution_allowed_now": False,
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


def _render_report(
    plan_items: List[Dict[str, Any]],
    execution_order: List[Dict[str, Any]],
    governance: Dict[str, Any],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Planes de patch - Dry Run",
        "",
        "## 1. Planes generados",
    ]
    for item in plan_items:
        lines.extend(
            [
                f"### {item['front_id']}",
                f"- Plan: {item['title']}",
                f"- Estado: {item['plan_status']}",
                f"- Categoria: {item['category']}",
                f"- Severidad: {item['severity']}",
                f"- Tipo: {item['patch_type']}",
                f"- Alcance recomendado: {item['recommended_scope']}",
                f"- Riesgo: {item['risk_assessment']['risk_level']} - {item['risk_assessment']['risk_notes']}",
                "- Archivos candidatos:",
            ]
        )
        for target in item["target_files_suggested"]:
            lines.append(f"  - {target}")
        lines.append("- Archivos prohibidos:")
        for forbidden in item["files_forbidden_to_modify"]:
            lines.append(f"  - {forbidden}")
        lines.append("- Tests requeridos:")
        for test in item["required_tests"]:
            lines.append(f"  - {test}")
        lines.append("- Rollback:")
        lines.append(f"  - requerido: {item['rollback_plan']['required']}")
        lines.append(f"  - estrategia: {item['rollback_plan']['strategy']}")
    lines.extend(
        [
            "",
            "## 2. Orden recomendado",
        ]
    )
    for item in execution_order:
        lines.append(f"- {item['execution_priority']}. {item['category']} / {item['front_id']}")
    lines.extend(
        [
            "",
            "## 3. Governance",
            f"- status: {governance['status']}",
            f"- execution_allowed_now: {governance['execution_allowed_now']}",
            f"- requires_operator_approval: {governance['requires_operator_approval']}",
            f"- must_separate_code_and_ledger_commits: {governance['must_separate_code_and_ledger_commits']}",
            "",
            "## 4. Que NO se genero",
            "- No se generaron diffs aplicables.",
            "- No se generaron patches ejecutables.",
            "- No se guardaron raw API bodies ni tokens.",
            "",
            "## 5. Que NO se aplico",
            "- No se aplicaron patches.",
            "- No se modificaron archivos objetivo sugeridos.",
            "- No se modifico runtime/chat.",
            "- No se escribio memory/semantic ni FAISS.",
            "- No se promovio conocimiento.",
            "- No se toco trading ni B8.",
            "",
            "## 6. Por que requiere aprobacion humana",
            "- Cada plan puede alterar governance, harnesses o criterios de calidad futuros.",
            "- Deben revisarse alcance, rollback, tests y preservacion de dirty state antes de implementar.",
            "",
            "## 7. Resumen",
            f"- plan_items: {summary['plan_items']}",
            f"- high_priority_count: {summary['high_priority_count']}",
            f"- medium_priority_count: {summary['medium_priority_count']}",
            f"- low_priority_count: {summary['low_priority_count']}",
            "",
            "## 8. Siguiente paso recomendado",
            NEXT_SAFE_FRONT,
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_patch_plan*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    return False


def _windows_long_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(resolved))
    return resolved


def _run_recommendations_inside_output_dir(out: Path) -> Dict[str, Any]:
    recommendation_dir = out / "run_patch_recommendation"
    long_recommendation_dir = _windows_long_path(recommendation_dir)
    (
        long_recommendation_dir
        / "run_benchmark_harness"
        / "run_benchmark_design"
        / "run_live_validation"
        / "run_utility_evaluation"
        / "run_first_five_ingestion"
    ).mkdir(parents=True, exist_ok=True)
    return run_first_five_patch_recommendation_dry_run(str(long_recommendation_dir))


def run_first_five_patch_plan_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_patch_plan_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    recommendation_dir = out / "run_patch_recommendation"
    recommendation_result = _run_recommendations_inside_output_dir(out)
    artifacts = load_patch_recommendation_artifacts(str(recommendation_dir))
    recommendations = artifacts.get("recommendations", [])
    plan_items = build_all_patch_plan_items(recommendations)
    execution_order = build_patch_plan_execution_order(plan_items)
    governance = build_patch_plan_governance(plan_items)
    summary = summarize_patch_plan(plan_items)
    summary.update(
        {
            "recommendation_result": recommendation_result,
            "governance_status": governance["status"],
            "output_dir": str(out),
        }
    )

    (out / "first_five_patch_plan_items.json").write_text(json.dumps(plan_items, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_patch_plan_items.jsonl", plan_items)
    (out / "first_five_patch_plan_execution_order.json").write_text(
        json.dumps(execution_order, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_plan_governance.json").write_text(
        json.dumps(governance, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_plan_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "first_five_patch_plan_report.md").write_text(
        _render_report(plan_items, execution_order, governance, summary), encoding="utf-8"
    )

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak and len(plan_items) >= 1,
        "plan_items": len(plan_items),
        "high_priority_count": summary["high_priority_count"],
        "medium_priority_count": summary["medium_priority_count"],
        "low_priority_count": summary["low_priority_count"],
        "governance_status": governance["status"],
        "execution_allowed_now": False,
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
