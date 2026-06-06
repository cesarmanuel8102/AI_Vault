"""Smoke tests for first-five benchmark harness dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.self_improvement_first_five_benchmark_harness_dry_run as module
from brain.external_sources.self_improvement_first_five_benchmark_design_dry_run import (
    CANONICAL_FRONT_IDS,
    build_all_benchmark_designs,
)
from brain.external_sources.self_improvement_first_five_benchmark_harness_dry_run import (
    build_synthetic_fixture_result,
    run_all_benchmarks_dry_run,
    run_first_five_benchmark_harness_dry_run,
    run_single_benchmark_dry_run,
    score_fixture_result,
    summarize_benchmark_harness_results,
)


def sample_evaluation(front_id):
    return {
        "candidate_id": f"candidate_{front_id.lower()}",
        "front_id": front_id,
        "title": front_id,
        "utility_score": 0.88,
    }


def sample_designs():
    return build_all_benchmark_designs(
        [sample_evaluation(front_id) for front_id in CANONICAL_FRONT_IDS],
        [
            {"front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES", "validation_status": "partially_validated"},
            {"front_id": "AUTO_CODING_AGENTS_PATCH_GENERATION", "validation_status": "partially_validated"},
        ],
    )


def sample_benchmark():
    return sample_designs()[0]


def fake_design_run(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    designs = sample_designs()
    (out / "first_five_benchmark_designs.json").write_text(json.dumps(designs), encoding="utf-8")
    (out / "first_five_benchmark_execution_plan.json").write_text(
        json.dumps({"execution_allowed_now": False, "benchmarks_count": 5}),
        encoding="utf-8",
    )
    return {
        "benchmark_designs": 5,
        "execution_plan_created": True,
        "execution_allowed_now": False,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def run_with_fake_design(monkeypatch, output_dir):
    monkeypatch.setattr(module, "run_first_five_benchmark_design_dry_run", fake_design_run)
    return run_first_five_benchmark_harness_dry_run(output_dir)


def test_import_module():
    assert module is not None


def test_run_first_five_benchmark_harness_dry_run_exists():
    assert callable(run_first_five_benchmark_harness_dry_run)


def test_build_synthetic_fixture_result_exists():
    assert callable(build_synthetic_fixture_result)


def test_score_fixture_result_exists():
    assert callable(score_fixture_result)


def test_run_single_benchmark_dry_run_exists():
    assert callable(run_single_benchmark_dry_run)


def test_fixture_result_has_synthetic_execution_true():
    benchmark = sample_benchmark()
    result = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    assert result["synthetic_execution"] is True


def test_fixture_result_write_flags_false():
    benchmark = sample_benchmark()
    result = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    assert result["memory_write_performed"] is False
    assert result["faiss_write_performed"] is False
    assert result["real_write_performed"] is False
    assert result["promotion_performed"] is False


def test_score_result_has_average_score():
    benchmark = sample_benchmark()
    fixture = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    score = score_fixture_result(benchmark, fixture)
    assert "average_score" in score


def test_score_result_has_passed():
    benchmark = sample_benchmark()
    fixture = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    assert "passed" in score_fixture_result(benchmark, fixture)


def test_score_result_write_flags_false():
    benchmark = sample_benchmark()
    fixture = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    score = score_fixture_result(benchmark, fixture)
    assert score["memory_write_performed"] is False
    assert score["faiss_write_performed"] is False
    assert score["real_write_performed"] is False
    assert score["promotion_performed"] is False


def test_benchmark_run_result_has_benchmark_type_dry_run_harness_only():
    assert run_single_benchmark_dry_run(sample_benchmark())["benchmark_type"] == "dry_run_harness_only"


def test_benchmark_run_result_has_fixtures_executed():
    assert run_single_benchmark_dry_run(sample_benchmark())["fixtures_executed"] > 0


def test_benchmark_run_patch_allowed_false():
    assert run_single_benchmark_dry_run(sample_benchmark())["patch_allowed"] is False


def test_benchmark_run_memory_write_allowed_false():
    assert run_single_benchmark_dry_run(sample_benchmark())["memory_write_allowed"] is False


def test_benchmark_run_faiss_write_allowed_false():
    assert run_single_benchmark_dry_run(sample_benchmark())["faiss_write_allowed"] is False


def test_benchmark_run_promotion_allowed_false():
    assert run_single_benchmark_dry_run(sample_benchmark())["promotion_allowed"] is False


def test_benchmark_run_runtime_modification_allowed_false():
    assert run_single_benchmark_dry_run(sample_benchmark())["runtime_modification_allowed"] is False


def test_all_5_benchmark_designs_produce_run_results():
    assert len(run_all_benchmarks_dry_run(sample_designs())) == 5


def test_summary_has_benchmark_runs_5():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert summary["benchmark_runs"] == 5


def test_summary_has_average_score():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert "average_score" in summary


def test_summary_has_passed_count():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert "passed_count" in summary


def test_summary_has_failed_count():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert "failed_count" in summary


def test_run_writes_first_five_benchmark_harness_results_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        assert Path(td, "first_five_benchmark_harness_results.json").exists()


def test_run_writes_first_five_benchmark_harness_results_jsonl(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        assert Path(td, "first_five_benchmark_harness_results.jsonl").exists()


def test_run_writes_first_five_benchmark_harness_summary_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        assert Path(td, "first_five_benchmark_harness_summary.json").exists()


def test_run_writes_first_five_benchmark_harness_report_md(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        assert Path(td, "first_five_benchmark_harness_report.md").exists()


def test_run_writes_first_five_benchmark_scorecard_json(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        assert Path(td, "first_five_benchmark_scorecard.json").exists()


def test_report_is_spanish_readable(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        report = Path(td, "first_five_benchmark_harness_report.md").read_text(encoding="utf-8")
        assert "Que NO se modifico" in report
        assert "Siguiente paso recomendado" in report


def test_no_token_leak_in_outputs(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        combined = "\n".join(
            p.read_text(encoding="utf-8") for p in Path(td).glob("first_five_benchmark*") if p.is_file()
        )
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "Bearer " not in combined


def test_no_memory_semantic_write(monkeypatch):
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_design(monkeypatch, td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        assert run_with_fake_design(monkeypatch, td)["faiss_write_performed"] is False


def test_no_real_write(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        assert run_with_fake_design(monkeypatch, td)["real_write_performed"] is False


def test_no_promotion(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        assert run_with_fake_design(monkeypatch, td)["promotion_performed"] is False


def test_no_runtime_chat_integration(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        assert run_with_fake_design(monkeypatch, td)["runtime_chat_integration"] is False


def test_no_trading_b8(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_design(monkeypatch, td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_scorecard_has_5_entries(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        run_with_fake_design(monkeypatch, td)
        scorecard = json.loads(Path(td, "first_five_benchmark_scorecard.json").read_text(encoding="utf-8"))
    assert len(scorecard) == 5


def test_execution_is_dry_run_only(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_design(monkeypatch, td)
    assert result["execution_dry_run_only"] is True


def test_no_patches_generated(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_design(monkeypatch, td)
    assert result["patches_generated"] is False


def test_next_recommended_front_present(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        result = run_with_fake_design(monkeypatch, td)
    assert result["next_recommended_front"] == "SELF-IMPROVEMENT-FIRST-FIVE-PATCH-RECOMMENDATION-DRY-RUN-01"


def test_at_least_one_weakness_identified():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert summary["weaknesses_identified"] >= 1


def test_score_result_failure_reasons_when_failed():
    weak = sample_designs()[0]
    run = run_single_benchmark_dry_run(weak)
    if not run["passed"]:
        assert any(score["failure_reasons"] for score in run["scores"])


def test_fixture_result_has_required_ids():
    benchmark = sample_benchmark()
    result = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    assert result["fixture_result_id"]
    assert result["benchmark_id"]


def test_score_result_metric_scores_not_empty():
    benchmark = sample_benchmark()
    fixture = build_synthetic_fixture_result(benchmark, benchmark["fixtures"][0])
    assert score_fixture_result(benchmark, fixture)["metric_scores"]


def test_summary_patches_generated_false():
    summary = summarize_benchmark_harness_results(run_all_benchmarks_dry_run(sample_designs()))
    assert summary["patches_generated"] is False
