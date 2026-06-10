"""tests/smoke/smoke_front_chat_retrieval_evidence_trace_01.py
FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.chat_retrieval_evidence_trace import (
    front_id,
    safe_trace_fields,
    forbidden_trace_fields,
    expected_probe_messages,
    assert_no_forbidden_fields,
    run_trace_probe,
    summarize_trace,
)


def test_01_module_imports():
    import brain.chat_retrieval_evidence_trace as mod
    assert hasattr(mod, "front_id")
    assert hasattr(mod, "summarize_trace")


def test_02_front_id_exact():
    assert front_id() == "FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01"


def test_03_safe_trace_fields_contains_hit_ids():
    assert "hit_ids" in safe_trace_fields()


def test_04_safe_trace_fields_contains_context_injected():
    assert "context_injected" in safe_trace_fields()


def test_05_forbidden_trace_fields_contains_chain_of_thought():
    ff = forbidden_trace_fields()
    assert any("chain" in f for f in ff)
    assert any("system" in f for f in ff)
    assert any("secret" in f for f in ff)


def test_06_expected_probe_messages_has_three():
    probes = expected_probe_messages()
    assert len(probes) >= 3


def test_07_assert_no_forbidden_fields_passes_safe():
    safe = {"trace_id": "abc", "opt_in_detected": True}
    res = assert_no_forbidden_fields(safe)
    assert res["ok"] is True


def test_08_assert_no_forbidden_fields_fails_forbidden():
    bad = {"trace_id": "abc", "chain_of_thought": "secret"}
    res = assert_no_forbidden_fields(bad)
    assert res["ok"] is False
    assert len(res["found_forbidden"]) > 0


def test_09_run_trace_probe_handles_unavailable():
    result = run_trace_probe(timeout_s=5)
    assert "chat_route_ok" in result
    assert "timeout_detected" in result
    assert "trace_accessible" in result


def test_10_summarize_trace_status_allowed():
    result = run_trace_probe(timeout_s=20)
    summary = summarize_trace(result)
    assert summary["status"] in (
        "TRACE_CONFIRMS_CONTEXT_INJECTION",
        "TRACE_PARTIAL_CONTEXT_INJECTION",
        "TRACE_NOT_ACCESSIBLE",
        "TRACE_SHOWS_NO_CONTEXT_INJECTION",
        "CHAT_ROUTE_TIMEOUT",
        "CHAT_SERVICE_NOT_RUNNING",
    )


def test_11_no_raw_chain_of_thought_in_prompts():
    for p in expected_probe_messages():
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


def test_14_no_unauthorized_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_15_session_py_staged_if_trace_applied():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/core/session.py"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() != ""


def test_16_main_py_not_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/main.py"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_17_llm_py_not_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/core/llm.py"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_18_roadmap_valid():
    roadmap = Path("ROADMAP_STATUS.json")
    assert roadmap.exists()
    obj = json.loads(roadmap.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)


def test_19_ledger_exists():
    assert Path("docs/MIGRATION_CONTROL_LEDGER.md").exists()


def test_20_memory_not_mutated():
    import hashlib
    mem_path = Path("memory/semantic/semantic_memory.jsonl")
    idx_path = Path("memory/semantic/semantic_memory_faiss.index")
    ids_path = Path("memory/semantic/semantic_memory_faiss_ids.json")
    def sha(p):
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()
    before = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    result = run_trace_probe(timeout_s=20)
    after = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    mutated = any(before[k] != after[k] for k in before)
    assert mutated is False


def test_21_faiss_not_mutated():
    import hashlib
    mem_path = Path("memory/semantic/semantic_memory.jsonl")
    idx_path = Path("memory/semantic/semantic_memory_faiss.index")
    ids_path = Path("memory/semantic/semantic_memory_faiss_ids.json")
    def sha(p):
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()
    before = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    result = run_trace_probe(timeout_s=20)
    after = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    mutated = any(before[k] != after[k] for k in before)
    assert mutated is False


def test_22_no_connector_or_trading_or_b8():
    result = run_trace_probe(timeout_s=20)
    summary = summarize_trace(result)
    assert summary["connector_called"] is False
    assert summary["trading_executed"] is False
    assert summary["b8_touched"] is False
