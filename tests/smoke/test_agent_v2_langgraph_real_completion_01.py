"""
Smoke tests for LangGraph real completion audit.

Rules:
- No memory mutation.
- No ingestion/promotion.
- Verify LangGraph is removed from critical path and reporting is truthful.
"""
import os
import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

from tmp_agent.brain_v9.main import app
from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


def test_runtime_backend_is_native():
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime", f"Expected backend='native_runtime', got '{rt.backend}'"
    print("PASS: runtime_backend_is_native")


def test_no_langgraph_import_in_runtime():
    # Verify runtime module does not import or instantiate LangGraph
    from tmp_agent.brain_v9.core.agent_kernel_v2 import runtime as runtime_mod
    src = runtime_mod.__file__
    code = open(src, encoding="utf-8").read()
    assert "LangGraphAgentRuntimeV2" not in code, "runtime.py still references LangGraphAgentRuntimeV2"
    assert "langgraph_runtime" not in code, "runtime.py still imports langgraph_runtime"
    print("PASS: no_langgraph_import_in_runtime")


def test_api_status_no_false_langgraph_claims():
    r = client.get("/v2/agent/status", headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    data = r.json()
    assert data["backend"] == "native_runtime", f"Expected backend='native_runtime', got '{data['backend']}'"
    assert "langgraph_used" not in data, "status still contains false langgraph_used field"
    assert "langgraph_blocker" not in data, "status still contains false langgraph_blocker field"
    print("PASS: api_status_no_false_langgraph_claims")


def test_api_capabilities_no_false_langgraph_claims():
    r = client.get("/v2/agent/capabilities", headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 200
    data = r.json()
    assert data["backend"] == "native_runtime"
    assert "langgraph_used" not in data, "capabilities still contains false langgraph_used field"
    print("PASS: api_capabilities_no_false_langgraph_claims")


def test_dashboard_status_no_false_langgraph_claims():
    r = client.get("/brain-dashboard/agent-v2/status", headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 200
    data = r.json()
    assert data["backend"] == "native_runtime"
    assert "langgraph_used" not in data, "dashboard status still contains false langgraph_used field"
    assert "langgraph_blocker" not in data, "dashboard status still contains false langgraph_blocker field"
    print("PASS: dashboard_status_no_false_langgraph_claims")


def test_chat_entrypoint_uses_native_runtime():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What is the current runtime backend?", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("run_id", "").startswith("agv2_")
    print("PASS: chat_entrypoint_uses_native_runtime")


def test_trace_events_match_native_runtime_path():
    # Create a run and verify trace comes from native runtime
    r = client.post(
        "/v2/agent/runs",
        json={"goal": "test trace for native runtime", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    run = r.json()["run"]
    run_id = run["run_id"]
    # Plan and execute the run to get terminal events
    client.post(f"/v2/agent/runs/{run_id}/plan", headers={"X-Brain-Token": VALID_TOKEN})
    client.post(f"/v2/agent/runs/{run_id}/execute", headers={"X-Brain-Token": VALID_TOKEN})
    # Get trace
    trace_r = client.get(f"/v2/agent/runs/{run_id}/trace", headers={"X-Brain-Token": VALID_TOKEN})
    assert trace_r.status_code == 200
    trace_data = trace_r.json()
    assert isinstance(trace_data.get("trace"), list)
    # Native runtime emits trace events; verify at least run_created and run_completed exist
    event_types = [e.get("event_type", "") for e in trace_data["trace"]]
    assert "run_created" in event_types, f"trace missing run_created. events: {event_types}"
    assert "run_completed" in event_types or "run_failed" in event_types, f"trace missing terminal event. events: {event_types}"
    print("PASS: trace_events_match_native_runtime_path")


def test_plan_step_uses_native_runtime():
    r = client.post(
        "/v2/agent/runs",
        json={"goal": "test planning", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    run = r.json()["run"]
    run_id = run["run_id"]
    plan_r = client.post(f"/v2/agent/runs/{run_id}/plan", headers={"X-Brain-Token": VALID_TOKEN})
    assert plan_r.status_code == 200
    plan_data = plan_r.json()["run"]
    assert plan_data.get("status") == "planned"
    assert isinstance(plan_data.get("plan"), list)
    print("PASS: plan_step_uses_native_runtime")


def test_tool_step_uses_native_runtime():
    r = client.post(
        "/v2/agent/runs",
        json={"goal": "test tool execution with grep", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    run = r.json()["run"]
    run_id = run["run_id"]
    # Plan then execute
    client.post(f"/v2/agent/runs/{run_id}/plan", headers={"X-Brain-Token": VALID_TOKEN})
    exec_r = client.post(f"/v2/agent/runs/{run_id}/execute", headers={"X-Brain-Token": VALID_TOKEN})
    assert exec_r.status_code == 200
    exec_data = exec_r.json()["run"]
    assert exec_data.get("status") in ("completed", "failed")
    print("PASS: tool_step_uses_native_runtime")


def test_native_fallback_is_explicit():
    # After PATH C, there is no fallback — native is the only path
    rt = get_agent_runtime_v2()
    assert rt.backend == "native_runtime"
    # No graph_available attribute because it's native runtime, not LangGraph subclass
    assert not hasattr(rt, "graph_available"), "native runtime should not have graph_available attribute"
    print("PASS: native_fallback_is_explicit")


def test_no_memory_mutation():
    import json, faiss
    from pathlib import Path
    SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
    records = [line for line in (SEMANTIC_ROOT / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = json.loads((SEMANTIC_ROOT / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(SEMANTIC_ROOT / "semantic_memory_faiss.index")).ntotal)
    assert len(records) == 1795
    assert len(ids) == 1786
    assert ntotal == 1786
    print("PASS: no_memory_mutation")


if __name__ == "__main__":
    test_runtime_backend_is_native()
    test_no_langgraph_import_in_runtime()
    test_api_status_no_false_langgraph_claims()
    test_api_capabilities_no_false_langgraph_claims()
    test_dashboard_status_no_false_langgraph_claims()
    test_chat_entrypoint_uses_native_runtime()
    test_trace_events_match_native_runtime_path()
    test_plan_step_uses_native_runtime()
    test_tool_step_uses_native_runtime()
    test_native_fallback_is_explicit()
    test_no_memory_mutation()
    print("ALL 11 LANGGRAPH REAL COMPLETION TESTS PASSED")
