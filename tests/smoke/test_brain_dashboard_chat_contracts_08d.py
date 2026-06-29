"""Contract tests for dashboard chat proxy and agent-v2 trace proxy.

Pins the contract between the 8092 dashboard and the 8091 Agent V2 backend that
any future AGENT_V2_BACKEND opt-in wiring must preserve. Tests use the dashboard
app mounted as a TestClient and mock the upstream 8091 calls so no service is
required and no live LLM is called.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.dashboard.dashboard_app import app as dashboard_app

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")


def _dashboard_client():
    return TestClient(dashboard_app)


@pytest.fixture
def mock_upstream():
    """Patch urllib.request.urlopen so dashboard routes never hit a real service."""
    sample_trace = {
        "ok": True,
        "run_id": "agv2_test_run_08d",
        "trace": [
            {"event_type": "run_created", "message": "run created", "data": {"run_id": "agv2_test_run_08d"}},
            {"event_type": "plan_created", "message": "plan created", "data": {}},
            {"event_type": "tool_call_started", "data": {"tool": "semantic_retrieve"}},
            {"event_type": "tool_call_completed", "data": {"tool": "semantic_retrieve", "ok": True}},
            {"event_type": "final_answer_created", "message": "final answer"},
            {"event_type": "run_completed", "message": "run completed"},
        ],
        "event_count": 6,
    }

    def _urlopen(url_or_request, timeout=None):
        if isinstance(url_or_request, str):
            url = url_or_request
        else:
            url = url_or_request.get_full_url()

        if url == "http://127.0.0.1:8091/v2/chat/agent":
            body = json.loads(url_or_request.data.decode("utf-8")) if getattr(url_or_request, "data", None) else {}
            mode = body.get("mode", "read_only")
            response = {
                "ok": True,
                "canonical_agent_v2": True,
                "route": "/v2/chat/agent",
                "run_id": "agv2_test_run_08d",
                "final_answer": f"fake final answer for mode={mode}",
                "trace_url": "/v2/agent/runs/agv2_test_run_08d/trace",
                "classification": "brain_evidence",
                "status": "completed",
                "mode_requested": mode,
                "mode_effective": mode,
                "auto_decision": "n/a",
                "mode_escalation_required": mode == "build",
                "mode_escalation_reason": None,
                "required_permission": "build" if mode == "build" else None,
                "expected_write_scope": [] if mode != "build" else ["file_patch_tool"],
                "confirmation_id": "conf_08d" if mode == "build" else None,
                "blocked_tools": [],
                "provider_metadata": {
                    "provider_used": "fake_provider",
                    "model_used": "fake_model",
                    "provider_degraded": False,
                    "fallback_reason": "",
                },
                "capability_metadata": {
                    "memory_used": True,
                    "retrieval_attempted": True,
                    "planner_used": True,
                    "evidence_routed": True,
                    "tools_considered": 1,
                    "tools_executed": 1,
                    "tools_blocked": 0,
                    "governance_checked": mode == "build",
                    "trace_events_count": 6,
                    "intent_route": "brain_evidence",
                    "classification": "brain_evidence",
                },
                "intent_route": "brain_evidence",
                "intent_detected": "brain_evidence",
                "intent_confidence": 0.95,
            }
            return _MockResponse(response)

        if url == "http://127.0.0.1:8091/v2/agent/runs/agv2_test_run_08d/trace":
            return _MockResponse(sample_trace)

        raise RuntimeError(f"Unexpected URL in mock: {url}")

    class _MockResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    with patch("tmp_agent.brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _urlopen):
        yield


def test_dashboard_chat_proxy_contract(mock_upstream):
    client = _dashboard_client()
    response = client.post(
        "/brain-dashboard/chat",
        json={"message": "What is the status of the brain gate approve endpoint?", "mode": "read_only", "user_id": "dashboard_operator"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["canonical_agent_v2"] is True
    assert data["content"]
    assert data["run_id"].startswith("agv2_")
    assert data["trace_url"] == "/v2/agent/runs/agv2_test_run_08d/trace"
    required = {
        "content", "canonical_agent_v2", "run_id", "trace_url", "classification",
        "status", "model_used", "provider_used", "provider_degraded", "fallback_reason",
        "raw_cot_exposed", "mode_requested", "mode_effective", "auto_decision",
        "mode_escalation_required", "mode_escalation_reason", "required_permission",
        "expected_write_scope", "confirmation_id", "blocked_tools",
    }
    missing = required - set(data.keys())
    assert not missing, f"Missing dashboard chat response fields: {missing}"


def test_dashboard_chat_proxy_error_shape(mock_upstream):
    client = _dashboard_client()

    class _FailingResponse:
        def __enter__(self):
            raise RuntimeError("connection refused")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def _urlopen_failing(url_or_request, timeout=None):
        return _FailingResponse()

    with patch("tmp_agent.brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _urlopen_failing):
        response = client.post("/brain-dashboard/chat", json={"message": "hi", "mode": "read_only", "user_id": "dashboard_operator"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "error" in data
    assert "content" in data


def test_dashboard_agent_v2_trace_proxy_contract(mock_upstream):
    client = _dashboard_client()
    response = client.get("/brain-dashboard/agent-v2/runs/agv2_test_run_08d/trace")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["run_id"] == "agv2_test_run_08d"
    assert isinstance(data["trace"], list)
    assert data["event_count"] == len(data["trace"])
    events = [e.get("event_type") for e in data["trace"]]
    assert "plan_created" in events
    assert "run_completed" in events


def test_dashboard_agent_v2_status_contract(mock_upstream):
    client = _dashboard_client()
    response = client.get("/brain-dashboard/agent-v2/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    agent_v2 = data.get("agent_v2", {})
    assert agent_v2.get("ok") is True
    assert "backend" in agent_v2
    assert "chat_agent_route" in agent_v2
    assert agent_v2["chat_agent_route"] == "/v2/chat/agent"


def test_dashboard_status_includes_agent_v2_panel(mock_upstream):
    client = _dashboard_client()
    response = client.get("/brain-dashboard/status")
    assert response.status_code == 200
    data = response.json()
    assert "agent_v2" in data
    agent_v2 = data["agent_v2"]
    assert agent_v2.get("ok") is True
    assert "backend" in agent_v2
    assert "runs" in agent_v2
    assert "trace_available" in agent_v2


def test_dashboard_chat_build_mode_escalation_contract(mock_upstream):
    client = _dashboard_client()
    response = client.post(
        "/brain-dashboard/chat",
        json={"message": "Apply a patch to README.md", "mode": "build", "user_id": "dashboard_operator"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["mode_effective"] == "build"
    assert data["mode_escalation_required"] is True
    assert data["required_permission"] == "build"
    assert data["confirmation_id"] == "conf_08d"
    assert data["expected_write_scope"] == ["file_patch_tool"]


def test_dashboard_chat_auto_mode_exposes_auto_decision(mock_upstream):
    client = _dashboard_client()
    response = client.post(
        "/brain-dashboard/chat",
        json={"message": "Inspect repo status without modifying anything.", "mode": "auto", "user_id": "dashboard_operator"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "auto_decision" in data


def test_dashboard_chat_message_required_validation(mock_upstream):
    client = _dashboard_client()
    response = client.post("/brain-dashboard/chat", json={"message": "   ", "mode": "read_only", "user_id": "dashboard_operator"})
    assert response.status_code == 400


def test_no_dashboard_source_files_modified():
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
