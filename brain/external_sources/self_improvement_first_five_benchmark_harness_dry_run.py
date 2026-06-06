"""Synthetic benchmark harness dry-run for first-five self-improvement fronts.

Runs only synthetic fixtures from the benchmark design artifacts and produces
measurable scorecards. It does not apply patches, change runtime/chat, write
memory, write FAISS, promote knowledge, or touch trading/B8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain.external_sources.self_improvement_first_five_benchmark_design_dry_run import (
    run_first_five_benchmark_design_dry_run,
)


TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
)

BASELINE_PROFILES = {
    "MULTI_AGENT_SYSTEMS_ORCHESTRATION": {
        "base": 0.72,
        "weakness": "planner/evaluator handoff still needs a real trace harness",
        "recommended_action": "design_planner_executor_evaluator_trace_fixtures",
    },
    "EVALUATION_BENCHMARKS_QUALITY_GATES": {
        "base": 0.90,
        "weakness": "needs materialized before/after baseline corpus",
        "recommended_action": "implement_quality_gate_harness_dry_run",
    },
    "MEMORY_RAG_KNOWLEDGE_STRUCTURE": {
        "base": 0.74,
        "weakness": "retrieval/provenance scorer is not connected to real readonly corpus",
        "recommended_action": "materialize_readonly_rag_fixture_corpus",
    },
    "SECURITY_SANDBOXING_SUPPLY_CHAIN": {
        "base": 0.86,
        "weakness": "guardrails are strong, supply-chain dependency risk scoring remains synthetic",
        "recommended_action": "add_security_policy_fixture_runner_dry_run",
    },
    "AUTO_CODING_AGENTS_PATCH_GENERATION": {
        "base": 0.78,
        "weakness": "patch quality needs repo fixture and diff hygiene scorer",
        "recommended_action": "build_patch_fixture_repo_harness_dry_run",
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


def load_benchmark_design_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "benchmark_designs": _read_json(out / "first_five_benchmark_designs.json", []),
        "execution_plan": _read_json(out / "first_five_benchmark_execution_plan.json", {}),
        "summary": _read_json(out / "first_five_benchmark_summary.json", {}),
        "output_dir": str(out),
    }


def _baseline_for(front_id: str) -> Dict[str, Any]:
    return BASELINE_PROFILES.get(
        front_id,
        {
            "base": 0.68,
            "weakness": "front has no calibrated synthetic baseline",
            "recommended_action": "calibrate_front_specific_fixture_harness",
        },
    )


def build_synthetic_fixture_result(benchmark: Dict[str, Any], fixture: Dict[str, Any]) -> Dict[str, Any]:
    front_id = benchmark.get("front_id", "")
    baseline = float(_baseline_for(front_id)["base"])
    expected_observed = baseline >= 0.70
    forbidden_observed = False
    if "supply" in str(fixture.get("fixture_id", "")).lower() or "dependency" in str(fixture.get("fixture_id", "")).lower():
        expected_observed = baseline >= 0.86
    return {
        "fixture_result_id": _stable_id("fixture_result", benchmark.get("benchmark_id", ""), fixture.get("fixture_id", "")),
        "benchmark_id": benchmark.get("benchmark_id", ""),
        "front_id": front_id,
        "fixture_id": fixture.get("fixture_id", ""),
        "fixture_description": fixture.get("description", ""),
        "synthetic_execution": True,
        "expected_behavior_observed": expected_observed,
        "forbidden_behavior_observed": forbidden_observed,
        "notes": f"Synthetic baseline only; weakness: {_baseline_for(front_id)['weakness']}",
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "executed_at": now_utc(),
    }


def score_fixture_result(benchmark: Dict[str, Any], fixture_result: Dict[str, Any]) -> Dict[str, Any]:
    front_id = benchmark.get("front_id", "")
    base = float(_baseline_for(front_id)["base"])
    metrics = benchmark.get("metrics", [])
    metric_scores: Dict[str, float] = {}
    for index, metric in enumerate(metrics):
        metric_id = metric.get("metric_id", f"metric_{index}")
        score = base
        if not fixture_result.get("expected_behavior_observed"):
            score -= 0.12
        if fixture_result.get("forbidden_behavior_observed"):
            score -= 0.30
        if "dependency" in metric_id or "supply" in metric_id:
            score -= 0.16
        if "evidence" in metric_id or "provenance" in metric_id:
            score -= 0.04
        if "governance" in metric_id or "block" in metric_id or "forbidden" in metric_id:
            score += 0.04
        metric_scores[metric_id] = round(max(0.0, min(score, 0.96)), 4)
    average_score = round(sum(metric_scores.values()) / max(len(metric_scores), 1), 4)
    pass_threshold = round(
        sum(float(metric.get("pass_threshold", 0.80)) for metric in metrics) / max(len(metrics), 1),
        4,
    )
    passed = average_score >= pass_threshold
    failure_reasons: List[str] = []
    if not passed:
        failure_reasons.append(_baseline_for(front_id)["weakness"])
    if fixture_result.get("forbidden_behavior_observed"):
        failure_reasons.append("forbidden behavior observed in synthetic result")
    return {
        "score_result_id": _stable_id("score_result", fixture_result.get("fixture_result_id", "")),
        "benchmark_id": benchmark.get("benchmark_id", ""),
        "front_id": front_id,
        "fixture_id": fixture_result.get("fixture_id", ""),
        "metric_scores": metric_scores,
        "average_score": average_score,
        "pass_threshold": pass_threshold,
        "passed": passed,
        "failure_reasons": failure_reasons,
        "safe_next_step": _baseline_for(front_id)["recommended_action"],
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def run_single_benchmark_dry_run(benchmark: Dict[str, Any]) -> Dict[str, Any]:
    fixture_results = [build_synthetic_fixture_result(benchmark, fixture) for fixture in benchmark.get("fixtures", [])]
    scores = [score_fixture_result(benchmark, result) for result in fixture_results]
    average = round(sum(score.get("average_score", 0.0) for score in scores) / max(len(scores), 1), 4)
    passed_count = sum(1 for score in scores if score.get("passed"))
    pass_rate = round(passed_count / max(len(scores), 1), 4)
    passed = pass_rate >= 0.80 and average >= 0.80
    return {
        "benchmark_run_id": _stable_id("benchmark_run", benchmark.get("benchmark_id", "")),
        "benchmark_id": benchmark.get("benchmark_id", ""),
        "front_id": benchmark.get("front_id", ""),
        "title": benchmark.get("title", ""),
        "benchmark_type": "dry_run_harness_only",
        "fixtures_executed": len(fixture_results),
        "fixture_results": fixture_results,
        "scores": scores,
        "average_benchmark_score": average,
        "passed": passed,
        "pass_rate": pass_rate,
        "recommended_action": _baseline_for(benchmark.get("front_id", ""))["recommended_action"],
        "patch_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "runtime_modification_allowed": False,
        "completed_at": now_utc(),
    }


def run_all_benchmarks_dry_run(benchmark_designs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [run_single_benchmark_dry_run(benchmark) for benchmark in benchmark_designs]


def summarize_benchmark_harness_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    passed_count = sum(1 for result in results if result.get("passed"))
    failed_count = len(results) - passed_count
    average_score = round(sum(result.get("average_benchmark_score", 0.0) for result in results) / max(len(results), 1), 4)
    weaknesses = [
        {
            "front_id": result.get("front_id", ""),
            "weakness": _baseline_for(result.get("front_id", ""))["weakness"],
            "recommended_action": result.get("recommended_action", ""),
        }
        for result in results
        if not result.get("passed")
    ]
    return {
        "ok": len(results) == 5,
        "benchmark_runs": len(results),
        "scorecard_entries": len(results),
        "average_score": average_score,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "weaknesses_identified": len(weaknesses),
        "weaknesses": weaknesses,
        "execution_dry_run_only": True,
        "patches_generated": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "timestamp": now_utc(),
    }


def _build_scorecard(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "front_id": result.get("front_id", ""),
            "benchmark_id": result.get("benchmark_id", ""),
            "average_benchmark_score": result.get("average_benchmark_score", 0.0),
            "passed": result.get("passed", False),
            "pass_rate": result.get("pass_rate", 0.0),
            "weakness": _baseline_for(result.get("front_id", ""))["weakness"],
            "recommended_action": result.get("recommended_action", ""),
        }
        for result in results
    ]


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(results: List[Dict[str, Any]], summary: Dict[str, Any], scorecard: List[Dict[str, Any]]) -> str:
    lines = [
        "# Benchmark harness sintetico - Dry Run",
        "",
        "## 1. Benchmarks ejecutados sinteticamente",
    ]
    for result in results:
        lines.append(f"- {result['front_id']}: {result['title']}")
    lines.extend(["", "## 2. Fixtures evaluados"])
    for result in results:
        lines.append(f"### {result['front_id']}")
        for fixture in result.get("fixture_results", []):
            lines.append(f"- {fixture['fixture_id']}: {fixture['fixture_description']}")
    lines.extend(["", "## 3. Scores por frente"])
    for entry in scorecard:
        lines.append(
            f"- {entry['front_id']}: score={entry['average_benchmark_score']} "
            f"pass_rate={entry['pass_rate']} passed={str(entry['passed']).lower()}"
        )
    lines.extend(["", "## 4. Pass/fail por benchmark"])
    lines.append(f"- passed_count: {summary['passed_count']}")
    lines.append(f"- failed_count: {summary['failed_count']}")
    lines.extend(["", "## 5. Frentes debiles"])
    for weakness in summary["weaknesses"]:
        lines.append(f"- {weakness['front_id']}: {weakness['weakness']}")
    lines.extend(
        [
            "",
            "## 6. Evidencia faltante",
            "- Harness con fixtures materializados.",
            "- Baselines before/after reales.",
            "- Trace logs de ejecucion controlada.",
            "- Scorers conectados a resultados reales.",
            "",
            "## 7. Que NO se modifico",
            "- No runtime/chat.",
            "- No memory/semantic.",
            "- No FAISS.",
            "- No trading/B8.",
            "",
            "## 8. Que no esta permitido todavia",
            "- Patches reales.",
            "- Promotion real.",
            "- Writes a memoria.",
            "- Ejecucion de benchmarks contra runtime productivo.",
            "",
            "## 9. Siguiente paso recomendado",
            "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-RECOMMENDATION-DRY-RUN-01",
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("first_five_benchmark_harness*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in TOKEN_MARKERS):
                return True
    scorecard = output_dir / "first_five_benchmark_scorecard.json"
    if scorecard.exists() and any(marker in scorecard.read_text(encoding="utf-8", errors="ignore") for marker in TOKEN_MARKERS):
        return True
    return False


def run_first_five_benchmark_harness_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_benchmark_harness_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    design_dir = out / "run_benchmark_design"
    design_result = run_first_five_benchmark_design_dry_run(str(design_dir))
    artifacts = load_benchmark_design_artifacts(str(design_dir))
    benchmark_designs = artifacts.get("benchmark_designs", [])
    results = run_all_benchmarks_dry_run(benchmark_designs)
    summary = summarize_benchmark_harness_results(results)
    scorecard = _build_scorecard(results)
    summary.update(
        {
            "benchmark_design_result": design_result,
            "output_dir": str(out),
            "next_recommended_front": "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-RECOMMENDATION-DRY-RUN-01",
        }
    )

    (out / "first_five_benchmark_harness_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_jsonl(out / "first_five_benchmark_harness_results.jsonl", results)
    (out / "first_five_benchmark_harness_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "first_five_benchmark_scorecard.json").write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    (out / "first_five_benchmark_harness_report.md").write_text(
        _render_report(results, summary, scorecard), encoding="utf-8"
    )

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak and len(results) == 5 and len(scorecard) == 5,
        "benchmark_runs": len(results),
        "scorecard_entries": len(scorecard),
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
        "average_score": summary["average_score"],
        "weaknesses_identified": summary["weaknesses_identified"],
        "execution_dry_run_only": True,
        "patches_generated": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
        "next_recommended_front": "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-RECOMMENDATION-DRY-RUN-01",
    }
