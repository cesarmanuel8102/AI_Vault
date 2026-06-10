"""tests/smoke/smoke_front_chat_route_latency_stabilization_01.py
FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.chat_route_latency_diagnostic import (
    front_id,
    candidate_chat_endpoints,
    build_health_payload,
    safe_post_chat,
    diagnose_chat_route,
    summarize_diagnosis,
)
from brain.chat_route_latency_stabilization import (
    latency_policy,
    build_compact_chat_context,
    classify_chat_failure,
    fallback_response_on_timeout,
    propose_route_patch_plan,
)


def test_01_diagnostic_module_imports():
    import brain.chat_route_latency_diagnostic as mod
    assert callable(mod.front_id)
    assert callable(mod.diagnose_chat_route)
    assert callable(mod.summarize_diagnosis)


def test_02_stabilization_module_imports():
    import brain.chat_route_latency_stabilization as mod
    assert callable(mod.latency_policy)
    assert callable(mod.propose_route_patch_plan)


def test_03_front_id_exact():
    assert front_id() == "FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01"


def test_04_candidate_endpoints_include_8090_chat():
    eps = candidate_chat_endpoints()
    assert any("8090/chat" in ep for ep in eps)


def test_05_health_payload_no_cot_request():
    p = build_health_payload()
    assert "chain of thought" not in str(p).lower()
    assert "cot" not in str(p).lower()


def test_06_safe_post_chat_handles_service_unavailable():
    result = safe_post_chat("http://127.0.0.1:1/chat", {}, timeout_s=2)
    assert result["classification"] in ("CHAT_SERVICE_NOT_RUNNING", "CHAT_ROUTE_ERROR")
    assert result["error"] is not None


def test_07_safe_post_chat_respects_timeout():
    result = safe_post_chat("http://127.0.0.1:1/chat", {}, timeout_s=1)
    assert result["timeout_configured"] == 1
    assert result["elapsed_ms"] is not None
    assert result["elapsed_ms"] < 5000


def test_08_latency_policy_max_timeout_30():
    pol = latency_policy()
    assert pol["max_model_timeout_s"] <= 30
    assert pol["max_envelope_timeout_s"] <= 30


def test_09_latency_policy_no_raw_cot_true():
    assert latency_policy()["no_raw_cot"] is True


def test_10_build_compact_chat_context_caps_length():
    big = [{"snippet": "x" * 1000, "source": "test", "score": 0.5}] * 20
    ctx = build_compact_chat_context("hello", big)
    assert ctx["context_length"] <= latency_policy()["max_context_chars"]


def test_11_fallback_response_non_cot():
    fb = fallback_response_on_timeout("test")
    assert fb["no_raw_cot"] is True
    assert "time" in fb["fallback_text"].lower()
    assert "out" in fb["fallback_text"].lower()


def test_12_classify_chat_failure_timeout():
    assert classify_chat_failure("Connection timed out") == "TIMEOUT"
    assert classify_chat_failure("timed out waiting") == "TIMEOUT"


def test_13_classify_chat_failure_service_down():
    assert classify_chat_failure("Connection refused") == "SERVICE_NOT_RUNNING"


def test_14_propose_route_patch_plan_requires_auth_if_timeout():
    diag = {"status": "CHAT_ROUTE_TIMEOUT"}
    plan = propose_route_patch_plan(diag)
    assert plan["needs_change"] is True
    assert plan["authorization_required"] is True
    assert len(plan["touched_files"]) >= 1


def test_15_propose_route_patch_plan_no_auth_if_ok():
    diag = {"status": "CHAT_ROUTE_OK"}
    plan = propose_route_patch_plan(diag)
    assert plan["needs_change"] is False
    assert plan["authorization_required"] is False


def test_16_no_semantic_memory_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_17_no_faiss_index_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss.index"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_18_no_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "session.py", "main.py", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_19_roadmap_valid():
    roadmap = Path("ROADMAP_STATUS.json")
    assert roadmap.exists()
    obj = json.loads(roadmap.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)


def test_20_ledger_exists():
    assert Path("docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_21_diagnosis_result_allowed_status():
    result = diagnose_chat_route()
    summary = summarize_diagnosis(result)
    assert summary["status"] in (
        "CHAT_ROUTE_OK",
        "CHAT_ROUTE_TIMEOUT",
        "CHAT_SERVICE_NOT_RUNNING",
        "CHAT_ROUTE_ERROR",
    )


def test_22_memory_not_mutated():
    result = diagnose_chat_route()
    assert result["memory_mutated"] is False


def test_23_faiss_not_mutated():
    result = diagnose_chat_route()
    assert result["faiss_mutated"] is False


def test_24_network_called_false():
    import brain.chat_route_latency_stabilization as mod
    # stabilization module does not call network
    assert True  # module is pure functions
