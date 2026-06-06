"""Smoke tests for first-five live-source validation dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.self_improvement_first_five_live_source_validation_dry_run as module
from brain.external_sources.self_improvement_first_five_live_source_validation_dry_run import (
    build_live_validation_query,
    load_utility_evaluation_artifacts,
    run_first_five_live_source_validation_dry_run,
    select_candidates_for_live_validation,
    summarize_live_source_validation,
    validate_all_live_sources_dry_run,
    validate_candidate_source_live_dry_run,
)


def sample_evaluation(**overrides):
    evaluation = {
        "evaluation_id": "utility_eval_sample",
        "candidate_id": "candidate_swe_bench",
        "front_id": "EVALUATION_BENCHMARKS_QUALITY_GATES",
        "title": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
        "utility_score": 0.91,
        "decision": "ready_for_live_source_validation",
        "requires_live_source_validation": True,
        "promotion_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
    }
    evaluation.update(overrides)
    return evaluation


def fake_evidence(provider="official_docs"):
    return {
        "provider": provider,
        "source_id": f"{provider}_source",
        "source_type": "official_doc" if provider != "github" else "github_repo",
        "url_redacted": f"https://example.com/{provider}",
        "http_status": 200,
        "content_hash": "abc123",
        "retrieved_at": "2026-06-06T00:00:00+00:00",
    }


def patch_safe_providers(monkeypatch, evidence_count=1, deferred=None):
    deferred = deferred or []

    def fake_check(query, provider):
        if provider in deferred:
            return [], [provider], []
        if evidence_count <= 0:
            return [], [], ["not_found"]
        if provider == "github" and evidence_count >= 2:
            return [fake_evidence("github")], [], []
        if provider == "official_docs":
            return [fake_evidence("official_docs")], [], []
        return [], [], []

    monkeypatch.setattr(module, "_check_provider", fake_check)


def test_import_module():
    assert module is not None


def test_select_candidates_for_live_validation_exists():
    assert callable(select_candidates_for_live_validation)


def test_run_first_five_live_source_validation_dry_run_exists():
    assert callable(run_first_five_live_source_validation_dry_run)


def test_selects_ready_for_live_source_validation_candidates():
    selected = select_candidates_for_live_validation([sample_evaluation()])
    assert len(selected) == 1


def test_does_not_select_rejected_candidates():
    selected = select_candidates_for_live_validation([sample_evaluation(decision="reject_low_utility")])
    assert selected == []


def test_fallback_selects_useful_but_needs_live_evidence():
    selected = select_candidates_for_live_validation(
        [
            sample_evaluation(
                decision="useful_but_needs_live_evidence",
                utility_score=0.75,
                requires_live_source_validation=True,
            )
        ]
    )
    assert len(selected) == 1


def test_query_has_candidate_id():
    query = build_live_validation_query(sample_evaluation())
    assert query["candidate_id"] == "candidate_swe_bench"


def test_query_has_provider_targets():
    query = build_live_validation_query(sample_evaluation())
    assert query["provider_targets"] == ["github", "official_docs", "paper_index"]


def test_query_has_raw_body_storage_allowed_false():
    assert build_live_validation_query(sample_evaluation())["raw_body_storage_allowed"] is False


def test_query_has_memory_write_allowed_false():
    assert build_live_validation_query(sample_evaluation())["memory_write_allowed"] is False


def test_query_has_faiss_write_allowed_false():
    assert build_live_validation_query(sample_evaluation())["faiss_write_allowed"] is False


def test_query_has_promotion_allowed_false():
    assert build_live_validation_query(sample_evaluation())["promotion_allowed"] is False


def test_query_has_expected_evidence_types():
    query = build_live_validation_query(sample_evaluation())
    assert "github_repo" in query["expected_evidence_types"]
    assert "official_doc" in query["expected_evidence_types"]


def test_live_validation_result_format_has_validation_status(monkeypatch):
    patch_safe_providers(monkeypatch)
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert "validation_status" in result


def test_missing_credentials_deferred_safely(monkeypatch):
    patch_safe_providers(monkeypatch, evidence_count=0, deferred=["github"])
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert result["validation_status"] in {"deferred_missing_credentials", "deferred_no_network"}
    assert "github" in result["providers_deferred"]


def test_network_failure_handled_safely(monkeypatch):
    def fake_check(query, provider):
        return [], [provider], []

    monkeypatch.setattr(module, "_check_provider", fake_check)
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert result["validation_status"] == "deferred_no_network"


def test_no_raw_body_saved(monkeypatch):
    patch_safe_providers(monkeypatch)
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert result["raw_body_saved"] is False


def test_evidence_refs_do_not_contain_authorization(monkeypatch):
    patch_safe_providers(monkeypatch)
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert "Authorization" not in json.dumps(result["evidence_refs"])


def test_run_writes_live_validation_queries_json(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        assert Path(td, "live_validation_queries.json").exists()


def test_run_writes_live_validation_results_json(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        assert Path(td, "live_validation_results.json").exists()


def test_run_writes_live_validation_results_jsonl(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        assert Path(td, "live_validation_results.jsonl").exists()


def test_run_writes_live_validation_summary_json(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        assert Path(td, "live_validation_summary.json").exists()


def test_run_writes_live_validation_report_md(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        assert Path(td, "live_validation_report.md").exists()


def test_no_token_leak_in_outputs(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("live_validation*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "Bearer " not in combined
        assert "GITHUB_TOKEN" not in combined


def test_no_memory_semantic_write(monkeypatch):
    patch_safe_providers(monkeypatch)
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["faiss_write_performed"] is False


def test_no_real_write(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["real_write_performed"] is False


def test_no_promotion(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["promotion_performed"] is False


def test_no_runtime_chat_integration(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["runtime_chat_integration"] is False


def test_no_trading_b8(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_report_is_spanish_readable(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        report = Path(td, "live_validation_report.md").read_text(encoding="utf-8")
        assert "Que NO se escribio todavia" in report
        assert "Siguiente paso recomendado" in report


def test_summary_has_candidates_selected():
    summary = summarize_live_source_validation([{"validation_status": "partially_validated", "providers_deferred": []}])
    assert summary["candidates_selected"] == 1


def test_summary_has_providers_deferred():
    summary = summarize_live_source_validation([{"validation_status": "deferred_no_network", "providers_deferred": ["github"]}])
    assert summary["providers_deferred"]["github"] == 1


def test_at_least_one_result_exists_or_safe_empty_result(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        result = run_first_five_live_source_validation_dry_run(td)
    assert result["validation_results"] >= 0
    assert result["safe_completion"] is True


def test_validate_all_live_sources_uses_selection(monkeypatch):
    patch_safe_providers(monkeypatch)
    results = validate_all_live_sources_dry_run([sample_evaluation(), sample_evaluation(decision="reject_low_utility")])
    assert len(results) == 1


def test_load_utility_evaluation_artifacts_handles_missing_dir():
    with tempfile.TemporaryDirectory() as td:
        artifacts = load_utility_evaluation_artifacts(td)
    assert artifacts["evaluations"] == []


def test_content_hash_present_in_evidence(monkeypatch):
    patch_safe_providers(monkeypatch)
    result = validate_candidate_source_live_dry_run(sample_evaluation())
    assert result["evidence_refs"][0]["content_hash"]


def test_output_summary_has_safe_completion(monkeypatch):
    patch_safe_providers(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        run_first_five_live_source_validation_dry_run(td)
        summary = json.loads(Path(td, "live_validation_summary.json").read_text(encoding="utf-8"))
    assert summary["safe_completion"] is True
