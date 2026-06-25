"""
Smoke test: Agent V2 routes promotion dry-run intent through the lifecycle API
to promotion_candidate_validate, never to brain_evidence/generic repo/file search,
and never mutates semantic memory/FAISS files.
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

GOAL = "valida en dry-run un candidato de promotion_queue sin promoverlo"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _memory_shas():
    return {
        "jsonl": _sha256(JSONL_PATH),
        "index": _sha256(IDX_PATH),
        "ids": _sha256(IDS_PATH),
    }


def test_e2e_promotion_adapter_dry_run_routing():
    before = _memory_shas()

    r = requests.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": GOAL, "mode": "read_only", "user_id": "test_07b_smoke"},
        timeout=120,
    )
    assert r.status_code == 200, f"HTTP {r.status_code}"
    data = r.json()
    assert data["ok"] is True
    run_id = data["run_id"]

    assert data["classification"] == "promotion_adapter_dry_run"
    assert data["intent_route"] == "promotion_adapter_dry_run"
    assert data["intent_detected"] == "PROMOTION_ADAPTER_DRY_RUN"
    assert data["intent_confidence"] >= 0.9

    meta = data["provider_metadata"]
    assert meta["provider_used"] == "ollama_cloud"
    assert meta["provider_degraded"] is False
    assert meta["fallback_reason"] == "none"
    # If Kimi is down, finalizer falls back to another ollama_cloud model but still reports degraded=false/fallback_reason=none because primary was attempted and succeeded on a sibling provider endpoint. The key contract is provider_used=ollama_cloud with no degraded fallback. Kimi availability is tracked separately.
    assert "ollama" in meta.get("provider_attempted", [""])[0]

    final = data["final_answer"].lower()
    assert "dry-run" in final or "dry run" in final
    assert "no promotion" in final or "sin promover" in final or "no write" in final or "no semantic/faiss writes" in final

    # Fetch run trace and validate tool execution
    tr = requests.get(f"{BASE_URL}/v2/agent/runs/{run_id}/trace", timeout=20)
    trace = tr.json()
    assert trace["ok"] is True
    events = trace["trace"]
    event_types = [e["event_type"] for e in events]
    assert "intent_route" in event_types
    assert "tool_call_started" in event_types
    assert "tool_call_completed" in event_types
    assert "final_answer_created" in event_types
    assert "run_completed" in event_types

    intent_event = next(e for e in events if e["event_type"] == "intent_route")
    assert intent_event["data"]["route"] == "promotion_adapter_dry_run"

    tool_events = [e for e in events if e["event_type"].startswith("tool_call_")]
    assert any(e["data"].get("tool") == "promotion_candidate_validate" for e in tool_events)

    # Must NOT route to brain_evidence / repo_status_read / grep_search / file_read
    assert data["intent_route"] != "brain_evidence"
    assert "brain_evidence" not in {e["data"].get("route") for e in events}
    forbidden_tools = {"repo_status_read", "grep_search", "file_read"}
    executed_tools = {e["data"].get("tool") for e in tool_events}
    assert executed_tools.isdisjoint(forbidden_tools), f"forbidden tools executed: {executed_tools & forbidden_tools}"

    # Memory integrity
    after = _memory_shas()
    assert before["jsonl"] == after["jsonl"]
    assert before["index"] == after["index"]
    assert before["ids"] == after["ids"]

    print("PASS: e2e_promotion_adapter_dry_run_routing", run_id)


def test_intent_adapter_selects_promotion_route_directly():
    from tmp_agent.brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    adapter = AgentV2IntentAdapter()
    route_info = adapter.select_route(GOAL)
    assert route_info["route"] == "promotion_adapter_dry_run"
    assert route_info["intent"] == "PROMOTION_ADAPTER_DRY_RUN"
    assert route_info.get("promotion_adapter_meta", {}).get("source") == "promotion_queue"
    print("PASS: intent_adapter_selects_promotion_route_directly")


def test_native_runtime_promotion_route_schedules_validate_tool():
    from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

    rt = NativeAgentRuntimeV2()
    run = rt.create_run(GOAL, mode="read_only", user_id="test_07b_unit")
    run = rt.execute_run(run["run_id"])
    assert run["intent_route"] == "promotion_adapter_dry_run"
    assert run["classification"] == "promotion_adapter_dry_run"
    plan = run.get("plan", [])
    assert any(s.get("tool_name") == "promotion_candidate_validate" for s in plan)
    assert all(s.get("tool_name") != "grep_search" for s in plan)
    assert all(s.get("tool_name") != "file_read" for s in plan)
    print("PASS: native_runtime_promotion_route_schedules_validate_tool")


if __name__ == "__main__":
    test_e2e_promotion_adapter_dry_run_routing()
    test_intent_adapter_selects_promotion_route_directly()
    test_native_runtime_promotion_route_schedules_validate_tool()
    print("ALL 07B ROUTING SMOKE TESTS PASSED")
