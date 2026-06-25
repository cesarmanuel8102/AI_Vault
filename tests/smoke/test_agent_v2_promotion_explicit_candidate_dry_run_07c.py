"""
Smoke test: Agent V2 passes an explicit promotion candidate_id from a natural request
to promotion_candidate_validate via the lifecycle API, executes dry-run validation,
returns duplicate detection, and never mutates semantic memory/FAISS.
"""
import sys
import hashlib
import json
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")

import requests

SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
BASE_URL = "http://127.0.0.1:8091"

CANDIDATE_ID = "codex_pure_brain_training_autonomy_dashboard_visual_trace_self_improvement_governance_training_1"
GOAL = f"valida en dry-run el candidato {CANDIDATE_ID} de promotion_queue sin promoverlo"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _memory_shas():
    return {
        "jsonl": _sha256(JSONL_PATH),
        "index": _sha256(IDX_PATH),
        "ids": _sha256(IDS_PATH),
    }


def test_direct_intent_extracts_candidate_id():
    from tmp_agent.brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    route_info = AgentV2IntentAdapter().select_route(GOAL)
    assert route_info["intent"] == "PROMOTION_ADAPTER_DRY_RUN"
    assert route_info["route"] == "promotion_adapter_dry_run"
    meta = route_info.get("promotion_adapter_meta", {})
    assert meta["source"] == "promotion_queue"
    assert meta["candidate_id"] == CANDIDATE_ID
    print("PASS: direct_intent_extracts_candidate_id")


def test_native_runtime_passes_candidate_id_to_tool():
    from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

    rt = NativeAgentRuntimeV2()
    run = rt.create_run(GOAL, mode="read_only", user_id="test_07c_unit")
    run = rt.execute_run(run["run_id"])
    assert run["intent_route"] == "promotion_adapter_dry_run"
    plan = run.get("plan", [])
    step = next((s for s in plan if s.get("tool_name") == "promotion_candidate_validate"), None)
    assert step is not None
    assert step["input"].get("candidate_id") == CANDIDATE_ID
    assert step["input"].get("source") == "promotion_queue"
    assert step["input"].get("dry_run") is True
    print("PASS: native_runtime_passes_candidate_id_to_tool")


def test_direct_tool_reports_duplicate_no_write():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    before = _memory_shas()
    res = ToolGatewayV2().call(
        ToolCallRequest(
            tool_name="promotion_candidate_validate",
            args={"candidate_id": CANDIDATE_ID, "source": "promotion_queue", "dry_run": True},
            mode="read_only",
        )
    )
    after = _memory_shas()
    assert res.ok is True
    assert res.result["write_performed"] is False
    assert res.result["would_write_jsonl"] is False
    assert res.result["would_write_faiss"] is False
    assert res.result["candidate_valid"] is False
    assert "duplicate_exact_text_in_canonical_memory" in res.result.get("validation_errors", [])
    assert before == after
    print("PASS: direct_tool_reports_duplicate_no_write")


def test_e2e_explicit_candidate_routes_to_promotion_candidate_validate():
    before = _memory_shas()
    r = requests.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": GOAL, "mode": "read_only", "user_id": "test_07c_e2e"},
        timeout=120,
    )
    data = r.json()
    run_id = data["run_id"]
    trace = requests.get(f"{BASE_URL}/v2/agent/runs/{run_id}/trace", timeout=30).json()

    assert data["ok"] is True
    assert data["classification"] == "promotion_adapter_dry_run"
    assert data["intent_route"] == "promotion_adapter_dry_run"
    assert data["intent_detected"] == "PROMOTION_ADAPTER_DRY_RUN"

    events = trace.get("trace", [])
    tool_events = [e for e in events if e.get("event_type", "").startswith("tool_call_")]
    executed_tools = [e.get("data", {}).get("tool") for e in tool_events]
    assert "promotion_candidate_validate" in executed_tools

    # Verify candidate_id made it into the plan input
    run_data = requests.get(f"{BASE_URL}/v2/agent/runs/{run_id}", timeout=30).json()
    plan = run_data["run"].get("plan", [])
    step = next((s for s in plan if s.get("tool_name") == "promotion_candidate_validate"), {})
    assert step.get("input", {}).get("candidate_id") == CANDIDATE_ID

    meta = data["provider_metadata"]
    assert meta["model_used"] == "kimi-k2.6:cloud"
    assert meta["provider_used"] == "ollama_cloud"
    assert meta["provider_degraded"] is False
    assert meta["fallback_reason"] == "none"

    after = _memory_shas()
    assert before == after
    print("PASS: e2e_explicit_candidate_routes_to_promotion_candidate_validate", run_id)


def test_e2e_does_not_mutate_semantic_or_faiss():
    before = _memory_shas()
    r = requests.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": GOAL, "mode": "read_only", "user_id": "test_07c_safety"},
        timeout=120,
    )
    data = r.json()
    assert data["ok"] is True
    after = _memory_shas()
    assert before == after
    print("PASS: e2e_does_not_mutate_semantic_or_faiss")


def test_repo_file_fallback_absent():
    r = requests.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": GOAL, "mode": "read_only", "user_id": "test_07c_fallback"},
        timeout=120,
    )
    data = r.json()
    run_id = data["run_id"]
    trace = requests.get(f"{BASE_URL}/v2/agent/runs/{run_id}/trace", timeout=30).json()
    events = trace.get("trace", [])
    tool_events = [e for e in events if e.get("event_type", "").startswith("tool_call_")]
    executed_tools = {e.get("data", {}).get("tool") for e in tool_events}
    forbidden = {"repo_status_read", "grep_search", "file_read"}
    assert executed_tools.isdisjoint(forbidden), f"forbidden tools executed: {executed_tools & forbidden}"
    print("PASS: repo_file_fallback_absent")


if __name__ == "__main__":
    test_direct_intent_extracts_candidate_id()
    test_native_runtime_passes_candidate_id_to_tool()
    test_direct_tool_reports_duplicate_no_write()
    test_e2e_explicit_candidate_routes_to_promotion_candidate_validate()
    test_e2e_does_not_mutate_semantic_or_faiss()
    test_repo_file_fallback_absent()
    print("ALL 07C EXPLICIT CANDIDATE SMOKE TESTS PASSED")
