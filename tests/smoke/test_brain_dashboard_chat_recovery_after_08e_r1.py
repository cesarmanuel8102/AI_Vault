"""Recovery tests for dashboard chat after 08E backend selector guard.

Validates that dashboard proxy endpoints still work and that the Agent V2 backend
falls back to Native when the requested backend is not production compatible.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9 import api_security as _api_security
from brain_v9.core.agent_kernel_v2 import finalizer as _finalizer
from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
from brain_v9.dashboard.dashboard_app import app as dashboard_app
from tmp_agent.brain_v9.main import app as brain_app

REPO_ROOT = Path("C:/AI_VAULT_CANONICAL")

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "RECOVERY_R1_TEST_ADMIN_TOKEN")


async def _strict_op_passthrough(request, x_brain_token=None):
    return None


_api_security.require_strict_operator_access.__code__ = _strict_op_passthrough.__code__

_ORIGINAL_OLLAMA_CHAT = _finalizer._ollama_chat


def _fake_ollama_chat(model, prompt, timeout=45, system_content=None):
    return "fake final answer for recovery r1"


@pytest.fixture(autouse=True)
def _patch_finalizer():
    _finalizer._ollama_chat = _fake_ollama_chat
    try:
        yield
    finally:
        _finalizer._ollama_chat = _ORIGINAL_OLLAMA_CHAT


@pytest.fixture
def _bridge_dashboard_to_brain():
    """Bridge dashboard urllib urlopen to brain TestClient so no real 8091 is needed."""
    brain = TestClient(brain_app)
    import brain_v9.dashboard.dashboard_routes as dashboard_module

    original_urlopen = dashboard_module.urllib.request.urlopen

    class _BrainClientBridge:
        def __init__(self, client):
            self._client = client

        def open(self, request, timeout=None):
            if isinstance(request, str):
                url = request
                data = None
                headers = {}
            else:
                url = request.get_full_url()
                data = getattr(request, "data", None)
                headers = {k: v for k, v in request.header_items()}
            if not url.startswith("http://127.0.0.1:8091"):
                return original_urlopen(request, timeout=timeout)
            path = url[len("http://127.0.0.1:8091"):]
            if data:
                response = self._client.request("POST", path, content=data, headers=headers)
            else:
                response = self._client.request("GET", path, headers=headers)

            class _Response:
                def __init__(self, payload):
                    self._payload = payload

                def read(self):
                    return self._payload

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_val, exc_tb):
                    return False

            return _Response(response.content)

    dashboard_module.urllib.request.urlopen = _BrainClientBridge(brain).open
    try:
        yield
    finally:
        dashboard_module.urllib.request.urlopen = original_urlopen


def _dashboard_client():
    return TestClient(dashboard_app)


def _native_default_env(monkeypatch):
    monkeypatch.delenv("AGENT_V2_BACKEND", raising=False)


def test_dashboard_health_after_08e_r1():
    client = _dashboard_client()
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert data.get("dashboard") == "brain_persistent_autonomy"


def test_dashboard_status_no_crash_after_08e_r1():
    client = _dashboard_client()
    response = client.get("/brain-dashboard/status")
    assert response.status_code == 200
    data = response.json()
    assert "ok" in data
    assert "agent_v2" in data


def test_dashboard_chat_proxy_success_with_mocked_8091_after_08e_r1():
    client = _dashboard_client()
    sample_response = {
        "ok": True,
        "canonical_agent_v2": True,
        "route": "/v2/chat/agent",
        "run_id": "agv2_test_run_r1",
        "final_answer": "fake answer",
        "trace_url": "/v2/agent/runs/agv2_test_run_r1/trace",
        "classification": "direct_assistant",
        "status": "completed",
        "mode_requested": "read_only",
        "mode_effective": "read_only",
        "auto_decision": "n/a",
        "mode_escalation_required": False,
        "mode_escalation_reason": None,
        "required_permission": None,
        "expected_write_scope": [],
        "confirmation_id": None,
        "blocked_tools": [],
        "provider_metadata": {
            "provider_used": "fake_provider",
            "model_used": "fake_model",
            "provider_degraded": False,
            "fallback_reason": "",
        },
        "capability_metadata": {
            "memory_used": False,
            "retrieval_attempted": False,
            "retrieval_no_results": False,
            "retrieval_skipped": False,
            "planner_used": False,
            "evidence_routed": False,
            "evidence_sources_count": 0,
            "tools_considered": 0,
            "tools_executed": 0,
            "tools_blocked": 0,
            "governance_checked": False,
            "trace_events_count": 4,
            "intent_route": "direct_assistant",
            "classification": "direct_assistant",
        },
    }

    class _MockResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def _urlopen(url_or_request, timeout=None):
        return _MockResponse(sample_response)

    with patch("brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _urlopen):
        response = client.post(
            "/brain-dashboard/chat",
            json={"message": "hi", "mode": "read_only", "user_id": "dashboard_operator"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["content"] == "fake answer"
    assert data["run_id"] == "agv2_test_run_r1"
    assert "blocked_tools" in data


def test_dashboard_chat_proxy_unreachable_safe_error_after_08e_r1():
    client = _dashboard_client()

    class _FailingResponse:
        def __enter__(self):
            raise RuntimeError("connection refused")

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def _urlopen_failing(url_or_request, timeout=None):
        return _FailingResponse()

    with patch("brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _urlopen_failing):
        response = client.post(
            "/brain-dashboard/chat",
            json={"message": "hi", "mode": "read_only", "user_id": "dashboard_operator"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert "error" in data
    assert "content" in data


def test_dashboard_trace_proxy_success_with_mocked_8091_after_08e_r1():
    client = _dashboard_client()
    sample_trace = {
        "ok": True,
        "run_id": "agv2_test_run_r1",
        "trace": [
            {"event_type": "run_created", "message": "run created"},
            {"event_type": "final_answer_created", "message": "final answer"},
        ],
        "event_count": 2,
    }

    class _MockResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    def _urlopen(url_or_request, timeout=None):
        return _MockResponse(sample_trace)

    with patch("brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _urlopen):
        response = client.get("/brain-dashboard/agent-v2/runs/agv2_test_run_r1/trace")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert isinstance(data.get("trace"), list)
    assert data["event_count"] == len(data["trace"])


def test_dashboard_chat_proxy_to_real_testclient_native_backend_after_08e_r1(_bridge_dashboard_to_brain, monkeypatch):
    _native_default_env(monkeypatch)
    client = _dashboard_client()
    response = client.post(
        "/brain-dashboard/chat",
        json={"message": "hi", "mode": "read_only", "user_id": "dashboard_operator"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["content"]


def test_dashboard_chat_proxy_to_real_testclient_langgraph_env_fallback_after_08e_r1(_bridge_dashboard_to_brain, monkeypatch):
    monkeypatch.setenv("AGENT_V2_BACKEND", "langgraph")
    client = _dashboard_client()
    response = client.post(
        "/brain-dashboard/chat",
        json={"message": "hi", "mode": "read_only", "user_id": "dashboard_operator"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["content"]


def test_dashboard_static_files_unchanged_after_08e_r1():
    result = os.popen("git diff --name-only").read()
    changed = [l.strip() for l in result.splitlines() if l.strip()]
    forbidden = [c for c in changed if c.startswith("tmp_agent/brain_v9/dashboard/static/")]
    assert not forbidden, f"Dashboard static files unexpectedly modified: {forbidden}"


def test_frontend_files_unchanged_after_08e_r1():
    result = os.popen("git diff --name-only").read()
    changed = [l.strip() for l in result.splitlines() if l.strip()]
    forbidden = [c for c in changed if c.startswith("tmp_agent/brain_v9/ui/")]
    assert not forbidden, f"Frontend UI files unexpectedly modified: {forbidden}"
