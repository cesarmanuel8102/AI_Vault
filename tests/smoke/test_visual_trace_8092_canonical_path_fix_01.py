"""
Smoke tests for FRONT-VISUAL-TRACE-8092-CANONICAL-PATH-FIX-01.

Rules:
- No memory mutation.
- No ingestion/promotion.
- Verify 8092 dashboard UI uses same-origin trace proxy without hardcoded 8091.
"""
import os
import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

from tmp_agent.brain_v9.dashboard.dashboard_app import app

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


def test_dashboard_app_js_has_no_hardcoded_8091_trace_url():
    """
    Verify dashboard/static/app.js does not contain hardcoded http://127.0.0.1:8091
    in trace link builders.
    """
    from pathlib import Path
    js_path = Path("C:/AI_VAULT_CANONICAL/tmp_agent/brain_v9/dashboard/static/app.js")
    content = js_path.read_text(encoding="utf-8")
    # 8091 may appear in error messages ("Ensure Agent V2 is running on 8091") but NOT in trace URLs
    trace_url_lines = [line for line in content.splitlines() if "trace_url" in line.lower() or "traceUrl" in line]
    for line in trace_url_lines:
        assert "127.0.0.1:8091" not in line, f"Hardcoded 8091 found in trace-related line: {line}"
    print("PASS: dashboard_app_js_has_no_hardcoded_8091_trace_url")


def test_dashboard_app_js_uses_same_origin_trace_proxy():
    """
    Verify app.js remaps /v2/agent/runs/ to /brain-dashboard/agent-v2/runs/
    """
    from pathlib import Path
    js_path = Path("C:/AI_VAULT_CANONICAL/tmp_agent/brain_v9/dashboard/static/app.js")
    content = js_path.read_text(encoding="utf-8")
    assert "/brain-dashboard/agent-v2/runs/" in content, "app.js should use same-origin dashboard proxy"
    # Make sure it replaces the old v2 path
    assert content.count("replace('/v2/agent/runs/', '/brain-dashboard/agent-v2/runs/')") >= 2, "Should replace v2 trace path in multiple places"
    print("PASS: dashboard_app_js_uses_same_origin_trace_proxy")


def test_dashboard_proxy_trace_route_exists():
    """
    The dashboard proxy route /brain-dashboard/agent-v2/runs/{run_id}/trace must exist and work.
    """
    # Create a chat run first to get a valid run_id
    from tmp_agent.brain_v9.main import app as main_app
    main_client = TestClient(main_app)
    r = main_client.post(
        "/v2/chat/agent",
        json={"message": "ping", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    # Now test the dashboard proxy
    proxy_r = client.get(f"/brain-dashboard/agent-v2/runs/{run_id}/trace")
    assert proxy_r.status_code == 200, f"Dashboard proxy trace returned {proxy_r.status_code}"
    data = proxy_r.json()
    assert data.get("ok") is True
    assert data.get("run_id") == run_id
    print("PASS: dashboard_proxy_trace_route_exists")


def test_dashboard_chat_route_exists():
    """
    POST /brain-dashboard/chat must exist on 8092 and proxy to canonical Agent V2.
    """
    r = client.post(
        "/brain-dashboard/chat",
        json={"message": "ping", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200, f"Dashboard chat returned {r.status_code}"
    data = r.json()
    assert data.get("ok") is True
    assert data.get("canonical_agent_v2") is True
    assert data.get("run_id", "").startswith("agv2_")
    print("PASS: dashboard_chat_route_exists")


def test_trace_url_mapping_converts_v2_trace_to_dashboard_proxy():
    """
    Verify that the trace_url returned by chat is remapped to dashboard proxy correctly.
    """
    r = client.post(
        "/brain-dashboard/chat",
        json={"message": "What is 2+2?", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    trace_url = data.get("trace_url", "")
    assert trace_url.startswith("/v2/agent/runs/"), f"Expected relative /v2/agent/runs/, got: {trace_url}"
    # Remap to proxy
    proxy_url = trace_url.replace("/v2/agent/runs/", "/brain-dashboard/agent-v2/runs/")
    proxy_r = client.get(proxy_url)
    assert proxy_r.status_code == 200, f"Proxy trace GET returned {proxy_r.status_code}"
    trace_data = proxy_r.json()
    assert trace_data.get("ok") is True
    assert trace_data.get("run_id") == data["run_id"]
    print("PASS: trace_url_mapping_converts_v2_trace_to_dashboard_proxy")


def test_raw_cot_not_exposed_in_dashboard_trace_rendering():
    """
    Trace events from dashboard proxy must not contain raw CoT markers.
    """
    r = client.post(
        "/brain-dashboard/chat",
        json={"message": "What is 2+2?", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    trace_url = data.get("trace_url", "")
    proxy_url = trace_url.replace("/v2/agent/runs/", "/brain-dashboard/agent-v2/runs/")
    trace_r = client.get(proxy_url)
    trace_text = str(trace_r.json())
    from tmp_agent.brain_v9.core.agent_kernel_v2.state import RAW_COT_MARKERS
    for marker in RAW_COT_MARKERS:
        assert marker not in trace_text, f"Raw CoT marker '{marker}' found in dashboard trace"
    print("PASS: raw_cot_not_exposed_in_dashboard_trace_rendering")


def test_secrets_not_exposed_in_dashboard_trace_rendering():
    """
    Dashboard trace must not contain secrets.
    """
    r = client.post(
        "/brain-dashboard/chat",
        json={"message": "What is 2+2?", "mode": "read_only", "user_id": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    trace_url = data.get("trace_url", "")
    proxy_url = trace_url.replace("/v2/agent/runs/", "/brain-dashboard/agent-v2/runs/")
    trace_r = client.get(proxy_url)
    trace_text = str(trace_r.json())
    assert "AGENTV2_TEST_ADMIN_TOKEN" not in trace_text, "Admin token leaked in dashboard trace"
    assert "OPENAI_API_KEY" not in trace_text, "OpenAI key leaked in dashboard trace"
    print("PASS: secrets_not_exposed_in_dashboard_trace_rendering")


def test_no_memory_mutation():
    import json, faiss
    from pathlib import Path
    SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
    records = [line for line in (SEMANTIC_ROOT / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = json.loads((SEMANTIC_ROOT / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(SEMANTIC_ROOT / "semantic_memory_faiss.index")).ntotal)
    assert len(records) == 1803
    assert len(ids) == 1794
    assert ntotal == 1794
    print("PASS: no_memory_mutation")


if __name__ == "__main__":
    test_dashboard_app_js_has_no_hardcoded_8091_trace_url()
    test_dashboard_app_js_uses_same_origin_trace_proxy()
    test_dashboard_proxy_trace_route_exists()
    test_dashboard_chat_route_exists()
    test_trace_url_mapping_converts_v2_trace_to_dashboard_proxy()
    test_raw_cot_not_exposed_in_dashboard_trace_rendering()
    test_secrets_not_exposed_in_dashboard_trace_rendering()
    test_no_memory_mutation()
    print("ALL 8 VISUAL TRACE 8092 CANONICAL PATH FIX TESTS PASSED")
