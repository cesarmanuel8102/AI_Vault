"""Smoke tests for first-five self-improvement fronts dry-run ingestion."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.self_improvement_first_five_ingestion_dry_run as module
from brain.external_sources.self_improvement_first_five_ingestion_dry_run import (
    build_front_learning_candidate,
    build_source_search_plan,
    evaluate_front_candidate,
    get_first_five_learning_fronts,
    run_first_five_learning_fronts_dry_run,
)


CANONICAL_FRONT_IDS = {
    "MULTI_AGENT_SYSTEMS_ORCHESTRATION",
    "EVALUATION_BENCHMARKS_QUALITY_GATES",
    "MEMORY_RAG_KNOWLEDGE_STRUCTURE",
    "SECURITY_SANDBOXING_SUPPLY_CHAIN",
    "AUTO_CODING_AGENTS_PATCH_GENERATION",
}


def sample_front():
    return get_first_five_learning_fronts()[0]


def sample_source(**overrides):
    data = {
        "provider": "local_reference_catalog",
        "source_id": "sample_source",
        "source_type": "paper",
        "title": "Sample source",
        "url_redacted": "https://example.com/sample",
        "summary": "Useful self-improvement guidance for Brain.",
        "validation_score": 0.85,
        "trust_score": 0.80,
        "front_fit_score": 0.86,
    }
    data.update(overrides)
    return data


def test_import_module():
    assert module is not None


def test_get_first_five_learning_fronts_returns_5():
    assert len(get_first_five_learning_fronts()) == 5


def test_all_canonical_front_ids_present():
    ids = {front["front_id"] for front in get_first_five_learning_fronts()}
    assert CANONICAL_FRONT_IDS == ids


def test_each_front_has_purpose_for_brain():
    assert all(front.get("purpose_for_brain") for front in get_first_five_learning_fronts())


def test_each_front_has_search_queries():
    assert all(len(front.get("search_queries", [])) >= 3 for front in get_first_five_learning_fronts())


def test_build_source_search_plan_returns_5_fronts():
    plan = build_source_search_plan()
    assert plan["attempted_fronts"] == 5
    assert len(plan["fronts"]) == 5


def test_candidate_format_has_front_id():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    assert candidate["front_id"] == "MULTI_AGENT_SYSTEMS_ORCHESTRATION"


def test_candidate_format_has_what_brain_should_learn():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    assert candidate["what_brain_should_learn"]


def test_candidate_format_has_how_brain_could_apply_it():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    assert candidate["how_brain_could_apply_it"]


def test_candidate_write_flags_are_false():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    assert candidate["memory_write_allowed"] is False
    assert candidate["faiss_write_allowed"] is False
    assert candidate["real_write_allowed"] is False


def test_promotion_allowed_false():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    assert candidate["promotion_allowed"] is False


def test_evaluate_useful_candidate_works():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    review = evaluate_front_candidate(candidate)
    assert review["decision"] == "useful_for_brain_self_improvement"


def test_missing_provenance_rejected():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    candidate["provenance_bundle"] = {}
    review = evaluate_front_candidate(candidate)
    assert review["decision"] == "reject_missing_provenance"


def test_low_score_rejected():
    candidate = build_front_learning_candidate(sample_front(), sample_source(validation_score=0.5))
    review = evaluate_front_candidate(candidate)
    assert review["decision"] == "reject_low_quality"


def test_policy_safety_write_flag_rejected():
    candidate = build_front_learning_candidate(sample_front(), sample_source())
    candidate["memory_write_allowed"] = True
    review = evaluate_front_candidate(candidate)
    assert review["decision"] == "reject_policy_or_safety"


def test_run_writes_first_five_learning_fronts_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "first_five_learning_fronts.json").exists()


def test_run_writes_source_search_plan_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "source_search_plan.json").exists()


def test_run_writes_first_five_candidates_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "first_five_candidates.json").exists()


def test_run_writes_first_five_candidate_reviews_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "first_five_candidate_reviews.json").exists()


def test_run_writes_first_five_summary_json():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "first_five_summary.json").exists()


def test_run_writes_first_five_learning_report_md():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        assert Path(td, "first_five_learning_report.md").exists()


def test_no_token_leak_in_outputs():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("first_five*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "FRED_API_KEY" not in combined
        assert "api_key=" not in combined


def test_no_memory_semantic_write():
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["faiss_write_performed"] is False


def test_no_real_write():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["real_write_performed"] is False


def test_no_promotion():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["promotion_performed"] is False


def test_works_without_external_credentials():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["ok"] is True
    assert len(result["deferred_sources"]) == 5


def test_report_is_spanish_readable():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        report = Path(td, "first_five_learning_report.md").read_text(encoding="utf-8")
        assert "Frentes enumerados" in report
        assert "Que NO se escribio" in report


def test_output_includes_recommended_next_step():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        report = Path(td, "first_five_learning_report.md").read_text(encoding="utf-8")
        assert "SELF-IMPROVEMENT-FIRST-FIVE-UTILITY-EVALUATION-DRY-RUN-01" in report


def test_attempted_fronts_equals_5():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["attempted_fronts"] == 5


def test_fronts_enumerated_equals_5():
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_learning_fronts_dry_run(td)
    assert result["fronts_enumerated"] == 5


def test_all_candidates_have_dry_run_warning():
    with tempfile.TemporaryDirectory() as td:
        run_first_five_learning_fronts_dry_run(td)
        candidates = json.loads(Path(td, "first_five_candidates.json").read_text(encoding="utf-8"))
    assert all("dry_run_only" in candidate["warnings"] for candidate in candidates)


def test_source_search_plan_has_deferred_sources():
    plan = build_source_search_plan()
    assert len(plan["deferred_sources"]) == 5


def test_canonical_queries_present():
    fronts = {front["front_id"]: front for front in get_first_five_learning_fronts()}
    assert "multi agent orchestration planner executor evaluator agent framework" in fronts["MULTI_AGENT_SYSTEMS_ORCHESTRATION"]["search_queries"]
    assert "autonomous coding agent patch generation test driven repair" in fronts["AUTO_CODING_AGENTS_PATCH_GENERATION"]["search_queries"]
