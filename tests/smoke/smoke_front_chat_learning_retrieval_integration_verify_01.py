"""tests/smoke/smoke_front_chat_learning_retrieval_integration_verify_01.py
FRONT-CHAT-ROUTE-LEARNING-RETRIEVAL-INTEGRATION-VERIFY-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.chat_learning_retrieval_integration_verify import (
    front_id,
    expected_records,
    direct_retrieval_queries,
    chat_probe_suite,
    evaluate_marker_match,
    run_direct_retrieval_control,
    run_live_chat_learning_probe,
    run_chat_learning_retrieval_integration_verify,
    summarize_integration_verify,
)


def test_01_module_imports():
    import brain.chat_learning_retrieval_integration_verify as mod
    assert callable(mod.front_id)
    assert callable(mod.run_chat_learning_retrieval_integration_verify)
    assert callable(mod.summarize_integration_verify)


def test_02_front_id_exact():
    assert front_id() == "FRONT-CHAT-ROUTE-LEARNING-RETRIEVAL-INTEGRATION-VERIFY-01"


def test_03_expected_records_has_three_ids():
    recs = expected_records()
    assert len(recs) == 3
    ids = {r["id"] for r in recs}
    assert ids == {
        "controlled_batch_01_real_execution_policy",
        "controlled_batch_01_runtime_recovery_runbook",
        "controlled_batch_01_memory_faiss_canary_doc",
    }


def test_04_direct_retrieval_queries_has_three():
    qs = direct_retrieval_queries()
    assert len(qs) == 3
    assert all("expected_id" in q for q in qs)


def test_05_chat_probe_suite_has_three():
    ps = chat_probe_suite()
    assert len(ps) == 3
    assert all("expected_markers" in p for p in ps)


def test_06_marker_evaluator_detects_markers():
    response = "The real execution policy defines limits on trading and connectors."
    eval_result = evaluate_marker_match(response, ["real execution policy", "trading", "connectors"])
    assert eval_result["match_count"] >= 2
    assert eval_result["marker_pass"] is True


def test_07_marker_evaluator_rejects_insufficient():
    response = "Hello world"
    eval_result = evaluate_marker_match(response, ["real execution policy", "trading", "connectors"])
    assert eval_result["match_count"] < 2
    assert eval_result["marker_pass"] is False


def test_08_direct_retrieval_returns_expected_keys():
    result = run_direct_retrieval_control()
    assert "all_passed" in result
    assert "results" in result
    assert len(result["results"]) == 3


def test_09_live_chat_probe_handles_service_unavailable():
    # This might hit live endpoint; if not running, should handle gracefully
    result = run_live_chat_learning_probe(timeout_s=5)
    assert "chat_route_ok" in result
    assert "timeout_detected" in result
    assert "probes" in result


def test_10_summary_status_in_allowed_statuses():
    result = run_chat_learning_retrieval_integration_verify()
    summary = summarize_integration_verify(result)
    assert summary["status"] in (
        "CHAT_LEARNING_RETRIEVAL_CONFIRMED",
        "CHAT_RESPONDS_BUT_RETRIEVAL_NOT_CONFIRMED",
        "CHAT_ROUTE_TIMEOUT",
        "CHAT_SERVICE_NOT_RUNNING",
    )


def test_11_no_raw_chain_of_thought_requested():
    for p in chat_probe_suite():
        text = p["prompt"].lower()
        assert "chain of thought" not in text
        assert "<think>" not in text


def test_12_no_semantic_memory_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_13_no_faiss_index_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss.index"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_14_no_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "session.py", "main.py", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_15_roadmap_valid():
    roadmap = Path("ROADMAP_STATUS.json")
    assert roadmap.exists()
    obj = json.loads(roadmap.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)


def test_16_ledger_exists():
    assert Path("docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_17_no_connector_call_flag():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["connector_called"] is False


def test_18_no_trading_flag():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["trading_executed"] is False


def test_19_no_b8_flag():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["b8_touched"] is False


def test_20_memory_mutated_false():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["memory_mutated"] is False


def test_21_faiss_mutated_false():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["faiss_mutated"] is False


def test_22_direct_retrieval_control_passed():
    result = run_chat_learning_retrieval_integration_verify()
    assert result["direct_retrieval_control"]["all_passed"] is True


def test_23_chat_probe_no_timeout_crash():
    result = run_live_chat_learning_probe(timeout_s=20)
    assert isinstance(result.get("probes"), list)
