"""Smoke tests for first-five benchmark design dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.self_improvement_first_five_benchmark_design_dry_run as module
from brain.external_sources.self_improvement_first_five_benchmark_design_dry_run import (
    CANONICAL_FRONT_IDS,
    build_all_benchmark_designs,
    build_benchmark_design_for_front,
    build_benchmark_execution_plan,
    run_first_five_benchmark_design_dry_run,
    summarize_benchmark_designs,
)


def sample_evaluation(front_id):
    return {
        "candidate_id": f"candidate_{front_id.lower()}",
        "front_id": front_id,
        "title": front_id.replace("_", " ").title(),
        "utility_score": 0.88,
    }


def sample_live_result(front_id, status="partially_validated"):
    return {
        "candidate_id": f"candidate_{front_id.lower()}",
        "front_id": front_id,
        "validation_status": status,
        "evidence_count": 1,
    }


def fake_live_validation_run(output_dir):
    out = Path(output_dir)
    utility_dir = out / "run_utility_evaluation"
    utility_dir.mkdir(parents=True, exist_ok=True)
    evaluations = [sample_evaluation(front_id) for front_id in CANONICAL_FRONT_IDS]
    live_results = [
        sample_live_result("EVALUATION_BENCHMARKS_QUALITY_GATES"),
        sample_live_result("AUTO_CODING_AGENTS_PATCH_GENERATION"),
    ]
    (utility_dir / "first_five_utility_evaluations.json").write_text(json.dumps(evaluations), encoding="utf-8")
    (utility_dir / "first_five_utility_summary.json").write_text(json.dumps({"utility_evaluations": 5}), encoding="utf-8")
    (out / "live_validation_results.json").write_text(json.dumps(live_results), encoding="utf-8")
    (out / "live_validation_summary.json").write_text(json.dumps({"validation_results": 2}), encoding="utf-8")
    return {
        "safe_completion": True,
        "validation_results": 2,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def run_with_fake_live(monkeypatch, output_dir):
    monkeypatch.setattr(module, "run_first_five_live_source_validation_dry_run", fake_live_validation_run)
    return run_first_five_benchmark_design_dry_run(output_dir)


def all_designs():
    return build_all_benchmark_designs(
        [sample_evaluation(front_id) for front_id in CANONICAL_FRONT_IDS],
        [
            sample_live_result("EVALUATION_BENCHMARKS_QUALITY_GATES"),
            sample_live_result("AUTO_CODING_AGENTS_PATCH_GENERATION"),
        ],
    )


def test_import_module():
    assert module is not None


def test_build_benchmark_design_for_front_exists():
    assert callable(build_benchmark_design_for_front)


def test_run_first_five_benchmark_design_dry_run_exists():
    assert callable(run_first_five_benchmark_design_dry_run)


def test_creates_5_benchmark_designs():
    assert len(all_designs()) == 5


def test_all_canonical_front_ids_present():
    fronts = {design["front_id"] for design in all_designs()}
    assert fronts == set(CANONICAL_FRONT_IDS)


def test_each_benchmark_has_metrics():
    assert all(design["metrics"] for design in all_designs())


def test_each_benchmark_has_fixtures():
    assert all(design["fixtures"] for design in all_designs())


def test_each_benchmark_has_pass_criteria():
    assert all(design["pass_criteria"] for design in all_designs())


def test_each_benchmark_has_failure_modes():
    assert all(design["failure_modes"] for design in all_designs())


def test_each_benchmark_has_evidence_required():
    assert all(design["evidence_required"] for design in all_designs())


def test_safe_execution_constraints_memory_write_allowed_false():
    assert all(design["safe_execution_constraints"]["memory_write_allowed"] is False for design in all_designs())


def test_safe_execution_constraints_faiss_write_allowed_false():
    assert all(design["safe_execution_constraints"]["faiss_write_allowed"] is False for design in all_designs())


def test_safe_execution_constraints_real_write_allowed_false():
    assert all(design["safe_execution_constraints"]["real_write_allowed"] is False for design in all_designs())


def test_safe_execution_constraints_promotion_allowed_false():
    assert all(design["safe_execution_constraints"]["promotion_allowed"] is False for design in all_designs())


def test_safe_execution_constraints_trading_allowed_false():
    assert all(design["safe_execution_constraints"]["trading_allowed"] is False for design in all_designs())


def test_execution_plan_exists():
    assert build_benchmark_execution_plan(all_designs())["status"] == "designed_not_executed"


def test_execution_plan_execution_allowed_now_false():
    assert build_benchmark_execution_plan(all_designs())["execution_allowed_now"] is False


def test_execution_plan_requires_operator_approval_true():
    assert build_benchmark_execution_plan(all_designs())["requires_operator_approval"] is True


def test_execution_plan_writes_allowed_false():
    assert build_benchmark_execution_plan(all_designs())["writes_allowed"] is False


def test_execution_plan_next_safe_front_correct():
    assert (
        build_benchmark_execution_plan(all_designs())["next_safe_front"]
        == "SELF-IMPROVEMENT-FIRST-FIVE-BENCHMARK-HARNESS-DRY-RUN-01"
    )


def test_run_writes_first_five_benchmark_designs_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        assert Path(td, "first_five_benchmark_designs.json").exists()


def test_run_writes_first_five_benchmark_designs_jsonl(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        assert Path(td, "first_five_benchmark_designs.jsonl").exists()


def test_run_writes_first_five_benchmark_execution_plan_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        assert Path(td, "first_five_benchmark_execution_plan.json").exists()


def test_run_writes_first_five_benchmark_summary_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        assert Path(td, "first_five_benchmark_summary.json").exists()


def test_run_writes_first_five_benchmark_report_md(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        assert Path(td, "first_five_benchmark_report.md").exists()


def test_report_is_spanish_readable(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        report = Path(td, "first_five_benchmark_report.md").read_text(encoding="utf-8")
        assert "Que NO se ejecuto" in report
        assert "Siguiente paso recomendado" in report


def test_no_token_leak_in_outputs(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_live(monkeypatch, td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("first_five_benchmark*"))
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "Bearer " not in combined


def test_no_memory_semantic_write(monkeypatch):
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["faiss_write_performed"] is False


def test_no_real_write(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["real_write_performed"] is False


def test_no_promotion(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["promotion_performed"] is False


def test_no_runtime_chat_integration(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["runtime_chat_integration"] is False


def test_no_trading_b8(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_designs_are_dry_run_design_only():
    assert all(design["benchmark_type"] == "dry_run_design_only" for design in all_designs())


def test_at_least_one_benchmark_references_live_source_validation_status():
    statuses = [design["source_validation_status"] for design in all_designs()]
    assert "partially_validated" in statuses


def test_summary_reports_five_designs():
    assert summarize_benchmark_designs(all_designs())["benchmark_designs"] == 5


def test_summary_execution_allowed_now_false():
    assert summarize_benchmark_designs(all_designs())["execution_allowed_now"] is False


def test_metric_format_has_threshold():
    metric = all_designs()[0]["metrics"][0]
    assert metric["scoring"] == "0.0_to_1.0"
    assert metric["pass_threshold"] > 0.0


def test_fixture_format_has_expected_and_forbidden_behavior():
    fixture = all_designs()[0]["fixtures"][0]
    assert fixture["expected_behavior"]
    assert fixture["forbidden_behavior"]


def test_execution_plan_benchmarks_count_is_five():
    assert build_benchmark_execution_plan(all_designs())["benchmarks_count"] == 5


def test_run_result_reports_five_designs(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_live(monkeypatch, td)
    assert result["benchmark_designs"] == 5
