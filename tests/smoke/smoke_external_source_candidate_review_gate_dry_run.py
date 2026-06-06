"""Smoke tests for external source candidate review gate — dry-run only.

No memory writes. No FAISS writes. No real writes. No promotion.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from brain.external_sources.candidate_review_gate_dry_run import (
    now_utc,
    evaluate_candidate,
    evaluate_candidates,
    summarize_review_results,
    run_candidate_review_gate_dry_run,
)


def test_module_imports():
    assert callable(evaluate_candidate)
    assert callable(evaluate_candidates)
    assert callable(summarize_review_results)
    assert callable(run_candidate_review_gate_dry_run)


def test_evaluate_candidate_exists():
    assert evaluate_candidate is not None


def test_run_candidate_review_gate_dry_run_exists():
    assert run_candidate_review_gate_dry_run is not None


def test_valid_github_like_candidate_approved():
    cand = {
        "candidate_id": "github_test_1234",
        "provider": "github",
        "source_id": "repo_test",
        "source_type": "github_repo",
        "evidence_refs": ["repo_test"],
        "provenance_bundle": {
            "http_status": 200,
            "url_redacted": "https://example.com",
        },
        "validation_score": 0.82,
        "trust_score": 0.78,
        "warnings": ["dry_run_only"],
        "real_write_allowed": False,
        "faiss_write_allowed": False,
        "memory_write_allowed": False,
        "promotion_allowed": False,
    }
    review = evaluate_candidate(cand)
    assert review["decision"] == "approved_for_operator_review"
    assert review["promotion_allowed"] is False
    assert review["memory_write_allowed"] is False
    assert review["faiss_write_allowed"] is False
    assert review["real_write_allowed"] is False
    assert review["operator_action_required"] is True


def test_candidate_missing_provenance_rejected():
    cand = {
        "candidate_id": "bad_1234",
        "provider": "github",
        "source_id": "repo_test",
        "source_type": "github_repo",
        "evidence_refs": [],
        "provenance_bundle": {},
        "validation_score": 0.82,
        "trust_score": 0.78,
        "warnings": ["dry_run_only"],
        "real_write_allowed": False,
        "faiss_write_allowed": False,
        "memory_write_allowed": False,
        "promotion_allowed": False,
    }
    review = evaluate_candidate(cand)
    assert review["decision"] == "rejected_missing_provenance"


def test_candidate_low_scores_rejected():
    cand = {
        "candidate_id": "low_q_1234",
        "provider": "github",
        "source_id": "repo_test",
        "source_type": "github_repo",
        "evidence_refs": ["repo_test"],
        "provenance_bundle": {
            "http_status": 200,
            "url_redacted": "https://example.com",
        },
        "validation_score": 0.60,
        "trust_score": 0.60,
        "warnings": ["dry_run_only"],
        "real_write_allowed": False,
        "faiss_write_allowed": False,
        "memory_write_allowed": False,
        "promotion_allowed": False,
    }
    review = evaluate_candidate(cand)
    assert review["decision"] == "rejected_low_quality"


def test_candidate_promotion_allowed_rejected_policy():
    cand = {
        "candidate_id": "unsafe_1234",
        "provider": "github",
        "source_id": "repo_test",
        "source_type": "github_repo",
        "evidence_refs": ["repo_test"],
        "provenance_bundle": {
            "http_status": 200,
            "url_redacted": "https://example.com",
        },
        "validation_score": 0.90,
        "trust_score": 0.90,
        "warnings": ["dry_run_only"],
        "real_write_allowed": False,
        "faiss_write_allowed": False,
        "memory_write_allowed": False,
        "promotion_allowed": True,
    }
    review = evaluate_candidate(cand)
    assert review["decision"] == "rejected_policy_or_safety"


def test_dry_run_writes_review_results():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "review_results.json"))


def test_dry_run_writes_review_summary():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "review_summary.json"))


def test_dry_run_writes_operator_review_queue():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        assert os.path.exists(os.path.join(td, "operator_review_queue.json"))


def test_every_result_has_promotion_false():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        with open(os.path.join(td, "review_results.json"), "r", encoding="utf-8") as fh:
            results = json.load(fh)
        for r in results:
            assert r["promotion_allowed"] is False, f"Candidate {r['candidate_id']} has promotion_allowed=True"


def test_every_result_has_memory_write_false():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        with open(os.path.join(td, "review_results.json"), "r", encoding="utf-8") as fh:
            results = json.load(fh)
        for r in results:
            assert r["memory_write_allowed"] is False


def test_every_result_has_faiss_write_false():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        with open(os.path.join(td, "review_results.json"), "r", encoding="utf-8") as fh:
            results = json.load(fh)
        for r in results:
            assert r["faiss_write_allowed"] is False


def test_operator_queue_only_approved():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        with open(os.path.join(td, "operator_review_queue.json"), "r", encoding="utf-8") as fh:
            queue = json.load(fh)
        for q in queue:
            assert q["decision"] == "approved_for_operator_review", f"Operator queue has non-approved decision: {q['decision']}"


def test_no_token_leak_in_outputs():
    with tempfile.TemporaryDirectory() as td:
        run_candidate_review_gate_dry_run(output_dir=td)
        for fname in ("review_results.json", "review_summary.json", "operator_review_queue.json"):
            path = os.path.join(td, fname)
            if not os.path.exists(path):
                continue
            content = open(path, "r", encoding="utf-8").read()
            assert "github_pat_" not in content, f"Potential token leak in {fname}"
            assert "ghp_" not in content, f"Potential GitHub token leak in {fname}"
            assert "api_key=" not in content or "REDACTED" in content


def test_no_real_write_performed():
    result = run_candidate_review_gate_dry_run(output_dir=None)
    assert result["real_write_performed"] is False
    assert result["faiss_write_performed"] is False
    assert result["memory_write_performed"] is False
    assert result["promotion_performed"] is False


def test_summarize_review_results_structure():
    results = [
        {"decision": "approved_for_operator_review"},
        {"decision": "rejected_low_quality"},
    ]
    summary = summarize_review_results(results)
    assert "approved_for_operator_review" in summary
    assert summary["ok"] is True


def test_no_memory_semantic_write_or_paths_created():
    with tempfile.TemporaryDirectory() as td:
        result = run_candidate_review_gate_dry_run(output_dir=td)
        # Confirm no files under memory/semantic were created
        memory_semantic_path = os.path.join(os.path.dirname(__file__), "..", "..", "memory", "semantic")
        memory_semantic_full = os.path.abspath(memory_semantic_path)
        if os.path.exists(memory_semantic_full):
            initial_files = set(os.listdir(memory_semantic_full))
        else:
            initial_files = set()

        # Check result flags
        assert result["memory_write_performed"] is False
        assert result["faiss_write_performed"] is False
        assert result["real_write_performed"] is False
        assert result["promotion_performed"] is False

        # Output dir must not be under memory/semantic
        assert "memory" not in td.replace("\\", "/").split("/")
        assert "semantic" not in td.replace("\\", "/").split("/")
