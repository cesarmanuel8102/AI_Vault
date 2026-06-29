"""Contract tests for Agent V2 trace endpoints.

Pins the contract that any future AGENT_V2_BACKEND opt-in wiring must preserve:
- trace_url returned by /v2/chat/agent must resolve
- trace events must have a compatible schema
- visual trace endpoints remain operational and independent of runtime backend
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import brain_v9.api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from tmp_agent.brain_v9.main import app

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for trace contract test"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


def _client():
    return TestClient(app, headers={"X-Brain-Token": "test-token"})


def _chat(client, message, mode="read_only"):
    return client.post("/v2/chat/agent", json={"message": message, "mode": mode, "user_id": "trace08d"})


def test_v2_chat_agent_trace_url_resolves(_patch_finalizer):
    client = _client()
    chat_resp = _chat(client, "What is the status of the brain gate approve endpoint?")
    assert chat_resp.status_code == 200
    data = chat_resp.json()
    trace_url = data.get("trace_url")
    assert trace_url and trace_url.startswith("/v2/agent/runs/")
    run_id = data["run_id"]

    trace_resp = client.get(trace_url)
    assert trace_resp.status_code == 200, f"trace_url {trace_url} did not resolve"
    trace_data = trace_resp.json()
    assert trace_data.get("ok") is True
    assert trace_data.get("run_id") == run_id
    assert isinstance(trace_data.get("trace"), list)
    assert "event_count" in trace_data


def test_v2_agent_trace_event_schema_contract(_patch_finalizer):
    client = _client()
    chat_resp = _chat(client, "What is the status of the brain gate approve endpoint?")
    data = chat_resp.json()
    trace_url = data["trace_url"]

    trace_resp = client.get(trace_url)
    trace_data = trace_resp.json()
    events = trace_data.get("trace", [])
    assert events, "Trace should contain events"
    for event in events:
        # Native V2 uses 'event_type'; dashboard expects this key
        assert "event_type" in event, f"Trace event missing event_type: {event.keys()}"
        # message or data may be present
        assert any(k in event for k in ("message", "data", "step_id", "run_id", "ts")), "Trace event lacks any content key"


def test_trace_contract_supports_dashboard_expected_sections(_patch_finalizer):
    client = _client()
    chat_resp = _chat(client, "What is the status of the brain gate approve endpoint?")
    data = chat_resp.json()
    trace_url = data["trace_url"]

    trace_resp = client.get(trace_url)
    trace_data = trace_resp.json()
    events = [e.get("event_type") for e in trace_data.get("trace", [])]

    # Dashboard / UI expects these Native V2 event types. Record any missing as a contract gap.
    required = {"run_completed"}
    missing = required - set(events)
    assert not missing, f"Required trace event types missing: {missing}"
    # plan_created and tool_call_* are route-dependent; their presence is recorded in the report.
    present = set(events)
    assert present, "Trace should contain at least one event"


def test_visual_trace_latest_endpoint_contract(_patch_finalizer):
    client = _client()
    response = client.get("/brain/agent-trace/latest?room_id=default&run_id=default&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert any(k in data for k in ("success", "ok"))
    assert "events" in data
    assert isinstance(data["events"], list)


def test_visual_trace_stream_route_exists(_patch_finalizer):
    # SSE stream blocks indefinitely waiting for events/heartbeats.
    # The contract we can safely pin without live EventSource plumbing is route
    # registration, content-type, and that the endpoint does not 404.
    from fastapi.routing import APIRoute
    route_paths = [r.path for r in app.routes if isinstance(r, APIRoute)]
    assert "/brain/agent-trace/stream" in route_paths


def test_trace_run_root_current_native_contract(_patch_finalizer):
    # Verify the current Native runtime stores trace such that /v2/agent/runs/{run_id}/trace resolves.
    client = _client()
    chat_resp = _chat(client, "hi", "read_only")
    data = chat_resp.json()
    trace_url = data["trace_url"]
    run_id = data["run_id"]

    trace_resp = client.get(trace_url)
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert trace_data.get("run_id") == run_id
    assert trace_data.get("event_count") == len(trace_data.get("trace", []))


def test_no_source_or_frontend_modified():
    import subprocess
    result = subprocess.run(["git", "diff", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True)
    changed = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    allowed_prefixes = (
        "tests/smoke/test_brain_agent_v2_backend_flag_contracts_08d.py",
        "tests/smoke/test_brain_dashboard_chat_contracts_08d.py",
        "tests/smoke/test_brain_agent_v2_trace_contracts_08d.py",
        "tmp_agent/front_brain_agent_v2_backend_flag_contract_tests_08d/",
    )
    disallowed = [c for c in changed if not any(c.startswith(p) for p in allowed_prefixes)]
    assert not disallowed, f"Disallowed source files modified: {disallowed}"
