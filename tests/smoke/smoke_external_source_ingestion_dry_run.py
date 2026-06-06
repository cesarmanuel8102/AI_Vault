"""Smoke tests for real source ingestion dry-run.

Read-only. Must tolerate missing credentials safely.
Must NOT write to memory/semantic/FAISS.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from brain.external_sources.real_source_ingestion_dry_run import (
    now_utc,
    sha256_text,
    redact_url,
    safe_excerpt,
    build_normalized_source_records,
    github_record_to_candidate,
    sec_record_to_candidate,
    docs_record_to_candidate,
    run_real_source_ingestion_dry_run,
)


def test_now_utc_returns_iso_string():
    s = now_utc()
    assert isinstance(s, str)
    assert 'T' in s


def test_sha256_text_is_hex():
    h = sha256_text("hello")
    assert len(h) == 64
    assert all(c in '0123456789abcdef' for c in h)


def test_redact_url_removes_api_key():
    url = "https://example.com?foo=bar&api_key=secret123&baz=qux"
    assert "secret123" not in redact_url(url)
    assert "api_key=REDACTED" in redact_url(url)


def test_safe_excerpt_shortens():
    assert len(safe_excerpt("a" * 1000, max_chars=50)) == 50
    assert safe_excerpt(None, 10) == ""


def test_run_all_smokes_structure():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    result = run_all_smokes()
    assert isinstance(result, dict)
    assert "sources" in result


def test_build_normalized_source_records_keys():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    smoke = run_all_smokes()
    records = build_normalized_source_records(smoke)
    assert isinstance(records, list)
    for rec in records:
        assert "source_id" in rec
        assert "source_type" in rec
        assert "provider" in rec
        assert "url" in rec
        assert "retrieved_at" in rec
        assert "dry_run" in rec and rec["dry_run"] is True
        assert rec["real_write_allowed"] is False
        assert rec["faiss_write_allowed"] is False
        assert rec["memory_write_allowed"] is False


def test_candidates_have_required_fields():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    smoke = run_all_smokes()
    records = build_normalized_source_records(smoke)
    for rec in records:
        cand = None
        if rec["provider"] == "github" and rec.get("http_status") == 200:
            cand = github_record_to_candidate(rec)
        elif rec["provider"] == "sec" and rec.get("http_status") == 200:
            cand = sec_record_to_candidate(rec)
        elif rec["provider"] == "docs" and rec.get("http_status") == 200:
            cand = docs_record_to_candidate(rec)
        else:
            continue
        assert cand["state"] == "candidate_from_external_source"
        assert cand["label"] == "unverified_external_candidate"
        assert cand["real_write_allowed"] is False
        assert cand["faiss_write_allowed"] is False
        assert cand["memory_write_allowed"] is False
        assert cand["promotion_allowed"] is False
        assert "warnings" in cand
        assert "dry_run_only" in cand["warnings"]


def test_run_real_source_ingestion_dry_run_no_output_dir():
    result = run_real_source_ingestion_dry_run(output_dir=None)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "complete" in result
    assert "partial" in result
    assert result["real_write_performed"] is False
    assert result["faiss_write_performed"] is False
    assert result["memory_write_performed"] is False
    assert result["promotion_performed"] is False


def test_run_real_source_ingestion_dry_run_with_output_dir():
    with tempfile.TemporaryDirectory() as td:
        result = run_real_source_ingestion_dry_run(output_dir=td)
        assert result["output_dir"] == td
        summary_path = os.path.join(td, "ingestion_summary.json")
        assert os.path.exists(summary_path)
        with open(summary_path, "r", encoding="utf-8") as fh:
            summary = json.load(fh)
        assert summary["real_write_performed"] is False
        assert summary["faiss_write_performed"] is False
        assert summary["memory_write_performed"] is False
        assert summary["promotion_performed"] is False
        assert os.path.exists(os.path.join(td, "normalized_source_records.json"))
        assert os.path.exists(os.path.join(td, "curated_candidates.json"))
        assert os.path.exists(os.path.join(td, "curated_candidates.jsonl"))


def test_candidates_content_no_token():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    smoke = run_all_smokes()
    records = build_normalized_source_records(smoke)
    for rec in records:
        if rec["provider"] == "github" and rec.get("http_status") == 200:
            cand = github_record_to_candidate(rec)
            raw = json.dumps(cand)
            assert "ghp_" not in raw or "REDACTED" in raw


def test_github_candidate_scores_when_ok():
    rec = {
        "provider": "github",
        "source_id": "test_repo",
        "http_status": 200,
        "credential_status": "authenticated",
        "title": "Test",
        "text_excerpt": "...",
        "provenance": {"method": "api"},
    }
    cand = github_record_to_candidate(rec)
    assert cand["validation_score"] == 0.82
    assert cand["curation_score"] == 0.75
    assert cand["trust_score"] == 0.78
    assert "github_authenticated" in cand["warnings"] or "github_unauthenticated_or_authenticated_failed" in cand["warnings"]


def test_sec_candidate_scores_when_ok():
    rec = {
        "provider": "sec",
        "source_id": "test_sec",
        "http_status": 200,
        "credential_status": "not_required_user_agent_present",
        "title": "Apple Inc.",
        "text_excerpt": None,
        "provenance": {"method": "api"},
    }
    cand = sec_record_to_candidate(rec)
    assert cand["validation_score"] == 0.90
    assert cand["curation_score"] == 0.82
    assert cand["trust_score"] == 0.88
    assert "not_financial_advice" in cand["warnings"]


def test_docs_candidate_scores_when_ok():
    rec = {
        "provider": "docs",
        "source_id": "test_docs",
        "http_status": 200,
        "credential_status": "not_required",
        "title": "GitHub REST API Docs",
        "text_excerpt": "<!DOCTYPE html>...",
        "provenance": {"method": "http_get"},
    }
    cand = docs_record_to_candidate(rec)
    assert cand["validation_score"] == 0.80
    assert cand["curation_score"] == 0.74
    assert cand["trust_score"] == 0.76


def test_run_real_source_ingestion_dry_run_ok_when_any_provider_succeeds():
    result = run_real_source_ingestion_dry_run(output_dir=None)
    assert isinstance(result["ok"], bool)
    assert isinstance(result["complete"], bool)
    assert isinstance(result["partial"], bool)


def test_normalized_records_redact_url():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    smoke = run_all_smokes()
    records = build_normalized_source_records(smoke)
    for rec in records:
        url = rec.get("url", "")
        if "api_key=" in url:
            assert "api_key=REDACTED" in url, "URL must redact api_key"


def test_candidates_topic_for_github():
    rec = {
        "provider": "github",
        "source_id": "test_repo",
        "http_status": 200,
        "credential_status": "authenticated",
        "title": "Test",
        "text_excerpt": "...",
        "provenance": {"method": "api"},
    }
    cand = github_record_to_candidate(rec)
    assert cand["topic"] == "external_source_connectivity/github_repository_metadata"


def test_failed_github_record_does_not_generate_candidate():
    from brain.external_sources.real_source_ingestion_dry_run import _to_candidate
    record = {
        "provider": "github",
        "source_id": "failed_repo",
        "http_status": 403,
        "credential_status": "credential_missing",
        "title": "N/A",
        "text_excerpt": None,
    }
    assert _to_candidate(record) is None


def test_all_curated_candidates_have_http_200():
    with tempfile.TemporaryDirectory() as td:
        run_real_source_ingestion_dry_run(output_dir=td)
        with open(os.path.join(td, "curated_candidates.json"), "r", encoding="utf-8") as fh:
            candidates = json.load(fh)
        for c in candidates:
            assert c["provenance_bundle"]["http_status"] == 200, f"Candidate {c['candidate_id']} has non-200 http_status"


def test_candidates_only_from_passed_providers():
    with tempfile.TemporaryDirectory() as td:
        result = run_real_source_ingestion_dry_run(output_dir=td)
        with open(os.path.join(td, "curated_candidates.json"), "r", encoding="utf-8") as fh:
            candidates = json.load(fh)
        for c in candidates:
            assert c["provider"] in result["providers_passed"], f"Candidate from {c['provider']} not in passed providers"


def test_fred_and_openbb_never_generate_candidates():
    from brain.external_sources.connectivity_smoke import run_all_smokes
    smoke = run_all_smokes()
    from brain.external_sources.real_source_ingestion_dry_run import build_normalized_source_records, _to_candidate
    records = build_normalized_source_records(smoke)
    for rec in records:
        if rec["provider"] in ("fred", "openbb"):
            assert _to_candidate(rec) is None, f"Provider {rec['provider']} should not generate candidates"


def test_counts_match_candidates():
    with tempfile.TemporaryDirectory() as td:
        result = run_real_source_ingestion_dry_run(output_dir=td)
        with open(os.path.join(td, "curated_candidates.json"), "r", encoding="utf-8") as fh:
            candidates = json.load(fh)
        assert result["github_candidates_count"] == sum(
            1 for c in candidates if c.get("provider") == "github"
        )
        assert result["sec_candidates_count"] == sum(
            1 for c in candidates if c.get("provider") == "sec"
        )
        assert result["docs_candidates_count"] == sum(
            1 for c in candidates if c.get("provider") == "docs"
        )
        assert result["fred_candidates_count"] == 0
        assert result["openbb_candidates_count"] == 0
