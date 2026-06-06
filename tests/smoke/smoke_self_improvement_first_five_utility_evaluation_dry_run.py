"""Smoke tests for first-five utility evaluation dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.self_improvement_first_five_utility_evaluation_dry_run as module
from brain.external_sources.self_improvement_first_five_ingestion_dry_run import (
    build_front_learning_candidate,
    get_first_five_learning_fronts,
)
from brain.external_sources.self_improvement_first_five_utility_evaluation_dry_run import (
    build_actionability_matrix,
    evaluate_candidate_utility,
    run_first_five_utility_evaluation_dry_run,
)


def sample_candidate(**overrides):
    front = get_first_five_learning_fronts()[1]
    source = {
        "provider": "local_reference_catalog",
        "source_id": "sample_benchmark",
        "source_type": "benchmark",
        "title": "Sample benchmark",
        "url_redacted": "https://example.com/benchmark",
        "summary": "Benchmark and regression testing guidance for Brain quality gates.",
        "validation_score": 0.90,
        "trust_score": 0.84,
        "front_fit_score": 0.90,
    }
    candidate = build_front_learning_candidate(front, source)
    candidate.update(overrides)
    return candidate


def test_import_module():
    assert module is not None


def test_evaluate_candidate_utility_exists():
    assert callable(evaluate_candidate_utility)


def test_run_first_five_utility_evaluation_dry_run_exists():
    assert callable(run_first_five_utility_evaluation_dry_run)


def test_useful_candidate_gets_utility_score():
    evaluation = evaluate_candidate_utility(sample_candidate())
    assert evaluation["utility_score"] > 0.0


def test_score_keys_exist():
    evaluation = evaluate_candidate_utility(sample_candidate())
    for key in (
        "evidence_strength",
        "brain_goal_alignment",
        "implementation_actionability",
        "measurable_impact",
        "governance_safety_alignment",
        "current_codebase_fit",
    ):
        assert key in evaluation["scores"]


def test_write_flags_false():
    evaluation = evaluate_candidate_utility(sample_candidate())
    assert evaluation["memory_write_allowed"] is False
    assert evaluation["faiss_write_allowed"] is False
    assert evaluation["real_write_allowed"] is False


def test_promotion_allowed_false():
    evaluation = evaluate_candidate_utility(sample_candidate())
    assert evaluation["promotion_allowed"] is False


def test_policy_unsafe_candidate_rejected():
    candidate = sample_candidate(memory_write_allowed=True)
    evaluation = evaluate_candidate_utility(candidate)
    assert evaluation["decision"] == "reject_policy_or_safety"


def test_low_utility_candidate_rejected(monkeypatch):
    candidate = sample_candidate(validation_score=0.1, trust_score=0.1, front_fit_score=0.1)
    candidate["source_type"] = "unknown"
    candidate["why_relevant_to_brain"] = ""
    candidate["how_brain_could_apply_it"] = ""
    candidate["what_brain_should_learn"] = ""
    candidate["provenance_bundle"] = {"http_status": 200, "content_hash": "x", "url_redacted": "https://example.com"}
    monkeypatch.setattr(module, "_score_evidence_strength", lambda _: 0.30)
    monkeypatch.setattr(module, "_score_brain_goal_alignment", lambda _: 0.30)
    monkeypatch.setattr(module, "_score_implementation_actionability", lambda _: 0.30)
    monkeypatch.setattr(module, "_score_measurable_impact", lambda _: 0.30)
    monkeypatch.setattr(module, "_score_current_codebase_fit", lambda _: 0.30)
    evaluation = evaluate_candidate_utility(candidate)
    assert evaluation["decision"] == "reject_low_utility"


def test_offline_catalog_candidate_can_become_useful_but_needs_live_evidence():
    candidate = sample_candidate()
    candidate["provenance_bundle"] = {"http_status": 200, "url_redacted": "https://example.com/nohash"}
    evaluation = evaluate_candidate_utility(candidate)
    assert evaluation["decision"] == "useful_but_needs_live_evidence"


def test_measurable_impact_low_can_become_useful_but_needs_benchmark(monkeypatch):
    candidate = sample_candidate()
    monkeypatch.setattr(module, "_score_measurable_impact", lambda _: 0.50)
    evaluation = evaluate_candidate_utility(candidate)
    assert evaluation["decision"] == "useful_but_needs_benchmark"


def test_actionability_matrix_created():
    evaluation = evaluate_candidate_utility(sample_candidate())
    matrix = build_actionability_matrix([evaluation])
    assert len(matrix) == 1


def test_actionability_matrix_has_5_rows_when_5_candidates():
    evaluations = [evaluate_candidate_utility(sample_candidate(candidate_id=f"c{i}")) for i in range(5)]
    matrix = build_actionability_matrix(evaluations)
    assert len(matrix) == 5


def test_run_writes_first_five_utility_evaluations_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        assert Path(td, "first_five_utility_evaluations.json").exists()


def test_run_writes_first_five_utility_evaluations_jsonl():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        assert Path(td, "first_five_utility_evaluations.jsonl").exists()


def test_run_writes_first_five_actionability_matrix_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        assert Path(td, "first_five_actionability_matrix.json").exists()


def test_run_writes_first_five_utility_summary_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        assert Path(td, "first_five_utility_summary.json").exists()


def test_run_writes_first_five_utility_report_md():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        assert Path(td, "first_five_utility_report.md").exists()


def test_summary_attempted_candidates_equals_5():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["candidates_evaluated"] == 5


def test_no_token_leak_in_outputs():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("first_five_*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "FRED_API_KEY" not in combined


def test_no_memory_semantic_write():
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["faiss_write_performed"] is False


def test_no_real_write():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["real_write_performed"] is False


def test_no_promotion():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["promotion_performed"] is False


def test_no_runtime_chat_integration():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["runtime_chat_integration"] is False


def test_no_trading_b8():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_report_is_spanish_readable():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        report = Path(td, "first_five_utility_report.md").read_text(encoding="utf-8")
        assert "Que se evaluo" in report
        assert "Que NO se escribio todavia" in report


def test_report_includes_next_validation():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_utility_evaluation_dry_run(td)
        report = Path(td, "first_five_utility_report.md").read_text(encoding="utf-8")
        assert "SELF-IMPROVEMENT-FIRST-FIVE-LIVE-SOURCE-VALIDATION-DRY-RUN-01" in report


def test_at_least_one_candidate_requires_live_source_validation():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_utility_evaluation_dry_run(td)
    assert result["live_source_validation_required"] >= 1


def test_at_least_one_metric_recommended():
    evaluation = evaluate_candidate_utility(sample_candidate())
    assert evaluation["recommended_metric"]


def test_evaluation_format_has_required_fields():
    evaluation = evaluate_candidate_utility(sample_candidate())
    assert "recommended_patch_or_policy" in evaluation
    assert "recommended_next_validation" in evaluation
