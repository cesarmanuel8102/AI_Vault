"""Patch recommendation dry-run for first-five self-improvement fronts.

Reads synthetic benchmark harness scorecards and produces patch/policy/test
recommendations only. It never generates applicable diffs, applies patches,
modifies runtime, writes memory/FAISS, promotes knowledge, or touches trading/B8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_benchmark_harness_dry_run import (
    run_first_five_benchmark_harness_dry_run,
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

FRONT_RECOMMENDATIONS: Dict[str, Dict[str, Any]] = {
    "MULTI_AGENT_SYSTEMS_ORCHESTRATION": {
        "category": "orchestration_trace_gap",
        "title": "Add dry-run orchestration trace harness recommendations",
        "problem": "Planner/executor/evaluator handoff needs measurable traces without exposing raw chain-of-thought.",
        "patch_type": "harness_patch",
        "scope": "medium",
        "targets": ["brain/external_sources/*", "tests/smoke/*", "docs/*"],
        "steps": [
            "Define trace event schema for planner, executor, evaluator, tool, and governance events.",
            "Add dry-run trace fixtures that use summaries, not raw chain-of-thought.",
            "Score trace completeness and evaluator veto behavior.",
        ],
        "tests": ["smoke orchestration trace fixture", "no chain-of-thought exposure scan", "governance event coverage test"],
        "criteria": ["trace summary exists", "evaluator veto captured", "no raw reasoning stored", "no runtime mutation"],
        "risk": "medium",
        "risk_notes": "Trace design can leak reasoning if implemented without explicit redaction.",
    },
    "EVALUATION_BENCHMARKS_QUALITY_GATES": {
        "category": "evaluation_gate_gap",
        "title": "Strengthen before/after quality gate recommendation",
        "problem": "Quality gates need materialized before/after baselines before real self-improvement patches.",
        "patch_type": "test_patch",
        "scope": "small",
        "targets": ["brain/external_sources/*", "tests/smoke/*", "docs/*"],
        "steps": [
            "Define good patch, bad patch, broken test, and incomplete evidence fixtures.",
            "Require before/after test delta and stage scope evidence.",
            "Block recommendation execution when tests fail.",
        ],
        "tests": ["smoke before/after gate", "regression fixture", "stage scope validation"],
        "criteria": ["bad patch blocked", "good patch passes", "regression detected", "no commit if tests fail"],
        "risk": "low",
        "risk_notes": "Low risk if kept in dry-run harness; risk rises only if gate controls real commits.",
    },
    "MEMORY_RAG_KNOWLEDGE_STRUCTURE": {
        "category": "retrieval_provenance_gap",
        "title": "Add provenance and stale-knowledge scoring recommendation",
        "problem": "Retrieval/provenance scoring is not connected to a real read-only fixture corpus.",
        "patch_type": "harness_patch",
        "scope": "medium",
        "targets": ["brain/external_sources/*", "tests/smoke/*", "docs/*"],
        "steps": [
            "Create read-only curated fixture corpus outside memory/semantic.",
            "Score citation presence, provenance completeness, stale detection, and hallucination guard.",
            "Keep memory writes blocked until promotion gate and rollback exist.",
        ],
        "tests": ["readonly retrieval fixture", "missing provenance rejection", "stale knowledge detection"],
        "criteria": ["source/evidence required", "stale warning emitted", "no memory write", "no hallucinated provenance"],
        "risk": "medium",
        "risk_notes": "Moderate risk because retrieval work can accidentally become memory write work.",
    },
    "SECURITY_SANDBOXING_SUPPLY_CHAIN": {
        "category": "security_supply_chain_gap",
        "title": "Add supply-chain and token leak enforcement recommendation",
        "problem": "Guardrails are strong, but dependency and supply-chain scoring remains synthetic.",
        "patch_type": "policy_patch",
        "scope": "medium",
        "targets": ["brain/external_sources/*", "tests/smoke/*", "docs/*"],
        "steps": [
            "Define forbidden path, token print, tmp_agent stage, suspicious dependency, and dangerous shell fixtures.",
            "Add dry-run dependency risk classification.",
            "Require token leak and forbidden path scans in future patch gates.",
        ],
        "tests": ["token leak scan", "forbidden path scan", "dependency risk fixture", "dangerous shell policy fixture"],
        "criteria": ["secret redacted", "protected paths blocked", "raw body storage blocked", "unsafe command blocked"],
        "risk": "high",
        "risk_notes": "High priority because bypass would affect secrets, protected paths, or unsafe execution.",
    },
    "AUTO_CODING_AGENTS_PATCH_GENERATION": {
        "category": "patch_hygiene_gap",
        "title": "Add patch hygiene policy recommendation",
        "problem": "Patch quality needs repo fixtures and diff hygiene scoring before real self-improvement patches.",
        "patch_type": "policy_patch",
        "scope": "medium",
        "targets": ["brain/external_sources/*", "tests/smoke/*", "docs/*"],
        "steps": [
            "Define simple bug, small refactor, missing test, out-of-scope change, and rollback fixtures.",
            "Score diff minimality, test-first compliance, rollback readiness, and commit hygiene.",
            "Require separate code and ledger commits.",
        ],
        "tests": ["patch scope fixture", "test-before-commit fixture", "rollback plan fixture", "code-ledger separation check"],
        "criteria": ["patch minimum scope", "tests pass", "rollback plan present", "no code+ledger mixing"],
        "risk": "medium",
        "risk_notes": "Medium risk because poor hygiene can mix unrelated dirty changes or skip rollback.",
    },
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


def load_benchmark_harness_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "scorecard": _read_json(out / "first_five_benchmark_scorecard.json", []),
        "summary": _read_json(out / "first_five_benchmark_harness_summary.json", {}),
        "results": _read_json(out / "first_five_benchmark_harness_results.json", []),
        "output_dir": str(out),
    }


def classify_weakness(scorecard_entry: Dict[str, Any]) -> Dict[str, Any]:
    front_id = scorecard_entry.get("front_id", "")
    benchmark_id = scorecard_entry.get("benchmark_id", "")
    score = float(scorecard_entry.get("average_benchmark_score", 0.0))
    passed = bool(scorecard_entry.get("passed", False))
    pass_rate = float(scorecard_entry.get("pass_rate", 0.0))
    config = FRONT_RECOMMENDATIONS.get(front_id, {})
    category = config.get("category", "benchmark_design_gap")
    secondary_categories: List[str] = []
    if "partially_validated" in json.dumps(scorecard_entry):
        secondary_categories.append("insufficient_live_evidence")
    if score < 0.60:
        severity = "high"
    elif score < 0.80:
        severity = "medium"
    elif not passed or pass_rate < 0.80:
        severity = "medium" if pass_rate < 0.50 else "low"
    else:
        severity = "low"
    safe = bool(scorecard_entry.get("front_id") and benchmark_id and "average_benchmark_score" in scorecard_entry)
    return {
        "weakness_id": _stable_id("weakness", front_id, benchmark_id, score),
        "front_id": front_id,
        "benchmark_id": benchmark_id,
        "category": category,
        "secondary_categories": secondary_categories,
        "severity": severity,
        "score": score,
        "reason": scorecard_entry.get("weakness", config.get("problem", "benchmark weakness requires review")),
        "evidence_from_harness": [
            f"average_benchmark_score={score}",
            f"passed={passed}",
            f"pass_rate={pass_rate}",
            f"recommended_action={scorecard_entry.get('recommended_action', '')}",
        ],
        "safe_to_recommend_patch": safe,
    }


def build_patch_recommendation(scorecard_entry: Dict[str, Any], weakness: Dict[str, Any]) -> Dict[str, Any]:
    front_id = scorecard_entry.get("front_id", "")
    config = FRONT_RECOMMENDATIONS.get(front_id, FRONT_RECOMMENDATIONS["AUTO_CODING_AGENTS_PATCH_GENERATION"])
    risk_level = config["risk"]
    if weakness.get("severity") == "high":
        risk_level = "high"
    return {
        "recommendation_id": _stable_id("patch_recommendation", weakness.get("weakness_id", ""), front_id),
        "front_id": front_id,
        "benchmark_id": scorecard_entry.get("benchmark_id", ""),
        "weakness_id": weakness.get("weakness_id", ""),
        "category": weakness.get("category", ""),
        "secondary_categories": weakness.get("secondary_categories", []),
        "severity": weakness.get("severity", "medium"),
        "title": config["title"],
        "problem_statement": config["problem"],
        "recommended_patch_type": config["patch_type"],
        "recommended_scope": config["scope"],
        "target_files_suggested": list(config["targets"]),
        "files_forbidden_to_modify": list(FORBIDDEN_FILES),
        "implementation_steps": list(config["steps"]),
        "required_tests": list(config["tests"]),
        "acceptance_criteria": list(config["criteria"]),
        "rollback_plan_required": True,
        "operator_approval_required": True,
        "patch_allowed_now": False,
        "auto_apply_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "risk_level": risk_level,
        "risk_notes": config["risk_notes"],
        "created_at": now_utc(),
    }


def build_all_patch_recommendations(scorecard: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    recommendations = []
    for entry in scorecard:
        weakness = classify_weakness(entry)
        if weakness["safe_to_recommend_patch"] and (not entry.get("passed") or weakness["severity"] in {"high", "medium"}):
            recommendations.append(build_patch_recommendation(entry, weakness))
    return recommendations


def build_patch_execution_roadmap(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    high_priority = [item for item in recommendations if item.get("severity") == "high"]
    ordered = sorted(
        recommendations,
        key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item.get("severity", "medium"), 1),
    )
    return {
        "roadmap_id": _stable_id("patch_recommendation_roadmap", len(recommendations), "first_five"),
        "status": "recommendations_only_not_executed",
        "recommendations_count": len(recommendations),
        "high_priority_count": len(high_priority),
        "recommended_order": [item["recommendation_id"] for item in ordered],
        "execution_allowed_now": False,
        "requires_operator_approval": True,
        "auto_apply_allowed": False,
        "patches_generated": False,
        "patches_applied": False,
        "writes_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "promotion_allowed": False,
        "next_safe_front": "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-DRY-RUN-01",
    }


def summarize_patch_recommendations(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for recommendation in recommendations:
        severity = recommendation.get("severity", "medium")
        counts[severity] = counts.get(severity, 0) + 1
    return {
        "ok": len(recommendations) >= 1,
        "recommendations_count": len(recommendations),
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
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(recommendations: List[Dict[str, Any]], roadmap: Dict[str, Any], summary: Dict[str, Any]) -> str:
    lines = [
        "# Recomendaciones de patches - Dry Run",
        "",
        "## 1. Debilidades detectadas",
    ]
    for recommendation in recommendations:
        lines.append(f"- {recommendation['front_id']}: {recommendation['problem_statement']}")
    lines.extend(["", "## 2. Recomendaciones por frente"])
    for recommendation in recommendations:
        lines.extend(
            [
                f"### {recommendation['front_id']}",
                f"- Titulo: {recommendation['title']}",
                f"- Categoria: {recommendation['category']}",
                f"- Severidad: {recommendation['severity']}",
                f"- Tipo: {recommendation['recommended_patch_type']}",
                f"- Riesgo: {recommendation['risk_level']} - {recommendation['risk_notes']}",
                "- Archivos candidatos:",
            ]
        )
        for target in recommendation["target_files_suggested"]:
            lines.append(f"  - {target}")
        lines.append("- Archivos prohibidos:")
        for forbidden in recommendation["files_forbidden_to_modify"]:
            lines.append(f"  - {forbidden}")
        lines.append("- Tests requeridos:")
        for test in recommendation["required_tests"]:
            lines.append(f"  - {test}")
    lines.extend(
        [
            "",
            "## 3. Orden recomendado",
            *[f"- {item}" for item in roadmap["recommended_order"]],
            "",
            "## 4. Que NO se aplico",
            "- No se generaron diffs aplicables.",
            "- No se aplicaron patches.",
            "- No se modifico runtime/chat.",
            "- No se escribio memory/semantic ni FAISS.",
            "- No se promovio conocimiento.",
            "",
            "## 5. Por que requiere aprobacion humana",
            "- Las recomendaciones afectan governance, tests o harnesses que pueden cambiar el comportamiento futuro del Brain.",
            "- Deben revisarse scopes, rollback y evidencia antes de implementar.",
            "",
            "## 6. Siguiente paso recomendado",
            "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-PLAN-DRY-RUN-01",
            "",
            "## 7. Resumen",
            f"- recommendations_count: {summary['recommendations_count']}",
            f"- high_priority_count: {summary['high_priority_count']}",
            f"- medium_priority_count: {summary['medium_priority_count']}",
            f"- low_priority_count: {summary['low_priority_count']}",
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_patch_recommendation*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    return False


def run_first_five_patch_recommendation_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_patch_recommendation_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    harness_dir = out / "run_benchmark_harness"
    harness_result = run_first_five_benchmark_harness_dry_run(str(harness_dir))
    artifacts = load_benchmark_harness_artifacts(str(harness_dir))
    scorecard = artifacts.get("scorecard", [])
    recommendations = build_all_patch_recommendations(scorecard)
    roadmap = build_patch_execution_roadmap(recommendations)
    summary = summarize_patch_recommendations(recommendations)
    summary.update(
        {
            "harness_result": harness_result,
            "roadmap": roadmap,
            "output_dir": str(out),
        }
    )

    (out / "first_five_patch_recommendations.json").write_text(
        json.dumps(recommendations, indent=2), encoding="utf-8"
    )
    _write_jsonl(out / "first_five_patch_recommendations.jsonl", recommendations)
    (out / "first_five_patch_recommendation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_recommendation_roadmap.json").write_text(
        json.dumps(roadmap, indent=2), encoding="utf-8"
    )
    (out / "first_five_patch_recommendation_report.md").write_text(
        _render_report(recommendations, roadmap, summary), encoding="utf-8"
    )

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak and len(recommendations) >= 1,
        "recommendations_count": len(recommendations),
        "high_priority_count": summary["high_priority_count"],
        "medium_priority_count": summary["medium_priority_count"],
        "low_priority_count": summary["low_priority_count"],
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
        "next_safe_front": roadmap["next_safe_front"],
    }
