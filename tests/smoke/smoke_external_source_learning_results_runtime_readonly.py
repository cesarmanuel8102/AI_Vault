"""Smoke tests for runtime read-only external knowledge results."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.learning_results_runtime_readonly as readonly_module
from brain.external_sources.learning_results_runtime_readonly import (
    build_readonly_response,
    find_latest_learning_results_output,
    safe_read_json,
    search_learning_results,
)


def write_fixture(output_dir: str) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cards = [
        {
            "card_id": "card_1",
            "provider": "github",
            "source_id": "github_repo_openbb",
            "candidate_id": "github_candidate_1",
            "status": "ready_for_operator_review",
            "what_was_learned": "External source retrieved from github: OpenBB-finance/OpenBB",
            "why_it_matters": "Creates a reviewable external knowledge candidate.",
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
            "promotion_allowed": False,
        },
        {
            "card_id": "card_2",
            "provider": "sec",
            "source_id": "sec_submissions_CIK0000320193",
            "candidate_id": "sec_candidate_1",
            "status": "ready_for_operator_review",
            "what_was_learned": "External source retrieved from sec: Apple Inc.",
            "why_it_matters": "Creates a reviewable SEC knowledge candidate.",
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
            "promotion_allowed": False,
        },
    ]
    summary = {
        "ok": True,
        "learning_result_cards": 2,
        "queue_items": 2,
        "promotion_plan_items": 2,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }
    (out / "learning_results_cards.json").write_text(json.dumps(cards), encoding="utf-8")
    (out / "learning_results_summary.json").write_text(json.dumps(summary), encoding="utf-8")


def response_text(response) -> str:
    return json.dumps(response, sort_keys=True)


def test_import_module():
    assert readonly_module is not None


def test_build_readonly_response_exists():
    assert callable(build_readonly_response)


def test_search_learning_results_exists():
    assert callable(search_learning_results)


def test_build_readonly_response_returns_readonly_true():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert response["readonly"] is True


def test_build_readonly_response_does_not_write_memory():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert response["memory_write_performed"] is False


def test_build_readonly_response_does_not_write_faiss():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert response["faiss_write_performed"] is False


def test_build_readonly_response_does_not_promote():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert response["promotion_performed"] is False


def test_build_readonly_response_loads_cards_if_output_exists():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert response["learning_result_cards"] == 2
        assert len(response["cards"]) == 2


def test_search_by_provider_works():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        result = search_learning_results("github", output_dir=td)
        assert result["result_count"] == 1
        assert result["results"][0]["provider"] == "github"


def test_search_by_candidate_or_source_text_works():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        result = search_learning_results("Apple", output_dir=td)
        assert result["result_count"] == 1
        assert result["results"][0]["provider"] == "sec"


def test_search_limit_works():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        result = search_learning_results("ready_for_operator_review", output_dir=td, limit=1)
        assert result["result_count"] == 1
        assert result["total_matches"] == 2


def test_no_token_appears_in_response():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        text = response_text(response)
        assert "github_pat_" not in text
        assert "ghp_" not in text


def test_no_authorization_header_appears():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert "Authorization:" not in response_text(response)


def test_no_raw_api_key_appears():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
        assert "FRED_API_KEY" not in response_text(response)
        assert "api_key=" not in response_text(response)


def test_no_network_calls_required():
    source = Path("brain/external_sources/learning_results_runtime_readonly.py").read_text(encoding="utf-8")
    assert "requests" not in source
    assert "httpx" not in source
    assert "urllib" not in source


def test_no_memory_semantic_write():
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        build_readonly_response(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after


def test_no_faiss_write():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
    assert response["faiss_write_performed"] is False


def test_no_real_write():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
    assert response["real_write_performed"] is False


def test_no_promotion():
    with tempfile.TemporaryDirectory() as td:
        write_fixture(td)
        response = build_readonly_response(td)
    assert response["promotion_performed"] is False


def test_missing_output_dir_returns_ok_false_not_exception():
    response = build_readonly_response("tmp_agent/path/that/does/not/exist")
    assert response["ok"] is False
    assert response["readonly"] is True


def test_malformed_json_handled_safely():
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td, "bad.json")
        bad.write_text("{not valid", encoding="utf-8")
        assert safe_read_json(str(bad)) == {}


def test_find_latest_learning_results_output_prefers_existing_pipeline_output():
    found = find_latest_learning_results_output()
    assert found is None or "learning_results" in found


def test_real_pipeline_output_loads_if_present():
    output_dir = "tmp_agent/external_source_learning_results_report_dry_run_01_evidence/run_output"
    if Path(output_dir).exists():
        response = build_readonly_response(output_dir)
        assert response["learning_result_cards"] >= 1
        assert response["mode"] == "runtime_readonly_external_knowledge_results"
