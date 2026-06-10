"""tests/smoke/smoke_front_chat_retrieval_injection_repair_01.py
FRONT-CHAT-RETRIEVAL-INJECTION-REPAIR-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.chat_retrieval_injection_patch_validation import (
    front_id,
    REPAIR_FRONT,
    opt_in_triggers,
    should_inject_retrieval,
    expected_marker_probes,
    evaluate_marker_match,
    run_live_chat_retrieval_probe,
    summarize_patch_validation,
)


def test_01_module_imports():
    import brain.chat_retrieval_injection_patch_validation as mod
    assert hasattr(mod, "REPAIR_FRONT")


def test_02_front_id_exact():
    assert front_id() == "FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01"


def test_03_repair_front_id_present():
    assert REPAIR_FRONT == "FRONT-CHAT-RETRIEVAL-INJECTION-REPAIR-01"


def test_04_opt_in_triggers_include_project_memory():
    triggers = opt_in_triggers()
    assert any("project memory" in t for t in triggers)


def test_05_should_inject_true_for_available_project_memory():
    assert should_inject_retrieval("Tell me using available project memory") is True


def test_06_should_inject_true_for_memoria_del_proyecto():
    assert should_inject_retrieval("usa la memoria del proyecto") is True


def test_07_should_inject_false_for_unrelated():
    assert should_inject_retrieval("Hello how are you today") is False


def test_08_expected_marker_probes_has_three():
    probes = expected_marker_probes()
    assert len(probes) == 3
    assert all("expected_markers" in p for p in probes)


def test_09_marker_evaluator_case_insensitive():
    result = evaluate_marker_match(
        "The REAL EXECUTION POLICY defines limits on Brain memory and FAISS.",
        ["real execution policy", "memory", "FAISS"],
    )
    assert result["match_count"] >= 2
    assert result["marker_pass"] is True


def test_10_marker_evaluator_requires_at_least_two():
    result = evaluate_marker_match("policy only", ["real execution policy", "memory", "FAISS"])
    assert result["match_count"] < 2
    assert result["marker_pass"] is False


def test_11_live_probe_handles_unavailable():
    result = run_live_chat_retrieval_probe(timeout_s=5)
    assert "chat_route_ok" in result
    assert "timeout_detected" in result
    assert isinstance(result.get("probes"), list)


def test_12_no_raw_chain_of_thought_in_prompts():
    for p in expected_marker_probes():
        text = p["prompt"].lower()
        assert "chain of thought" not in text
        assert "<think>" not in text


def test_13_no_semantic_memory_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_14_no_faiss_index_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss.index"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_15_no_unauthorized_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_16_session_py_staged_if_repair_applied():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/core/session.py"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() != ""


def test_17_main_py_not_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/main.py"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


def test_18_llm_py_not_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "tmp_agent/brain_v9/core/llm.py"],
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


def test_21_summary_status_is_allowed():
    result = run_live_chat_retrieval_probe(timeout_s=20)
    summary = summarize_patch_validation(result)
    assert summary["status"] in (
        "CHAT_RETRIEVAL_INJECTION_CONFIRMED",
        "CHAT_RETRIEVAL_INJECTION_PARTIAL",
        "CHAT_RETRIEVAL_INJECTION_NOT_CONFIRMED",
        "CHAT_ROUTE_TIMEOUT",
        "CHAT_SERVICE_NOT_RUNNING",
    )


def test_22_memory_not_mutated():
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
    result = run_live_chat_retrieval_probe(timeout_s=20)
    after = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    mutated = any(before[k] != after[k] for k in before)
    assert mutated is False


def test_23_faiss_not_mutated():
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
    result = run_live_chat_retrieval_probe(timeout_s=20)
    after = {
        "semantic_memory.jsonl": sha(mem_path),
        "semantic_memory_faiss.index": sha(idx_path),
        "semantic_memory_faiss_ids.json": sha(ids_path),
    }
    mutated = any(before[k] != after[k] for k in before)
    assert mutated is False


def test_24_no_connector_or_trading_or_b8():
    result = run_live_chat_retrieval_probe(timeout_s=20)
    summary = summarize_patch_validation(result)
    assert summary["connector_called"] is False
    assert summary["trading_executed"] is False
    assert summary["b8_touched"] is False
