"""Chat/dashboard recovery validation for 08F8.

Verifies that the Brain V9 safe server starts on 8091, that the chat UI
static route returns HTML, that Agent V2 status exposes LangGraph default,
and that Native rollback can be selected without code changes.
"""
from __future__ import annotations

import os

import pytest
import requests

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN_08F8")
VALID_TOKEN = os.environ["BRAIN_ADMIN_TOKEN"]
BASE_URL = os.getenv("BRAIN_PILOT_BASE_URL", "http://127.0.0.1:8091")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"X-Brain-Token": VALID_TOKEN})
    return s


def test_health(session):
    r = session.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_ui_route_redirects_and_serves_html(session):
    r = session.get(f"{BASE_URL}/ui", timeout=15, allow_redirects=False)
    assert r.status_code in (200, 307)
    r2 = session.get(f"{BASE_URL}/ui/", timeout=15)
    assert r2.status_code == 200
    assert "<html" in r2.text.lower()


def test_agent_v2_status_langgraph_default(session):
    r = session.get(f"{BASE_URL}/v2/agent/status", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["backend_selected"] == "langgraph_parity"
    assert data["backend_default"] == "langgraph_parity"
    assert data["langgraph_default_active"] is True
    assert data["rollback_backend"] == "native_runtime"


def test_chat_agent_endpoint_returns_canonical_response(session):
    r = session.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": "hola", "mode": "agent", "user_id": "local"},
        timeout=120,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["canonical_agent_v2"] is True
    assert "trace_url" in data


def test_native_rollback_runtime_selector():
    from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import resolve_agent_v2_backend_choice
    original = os.environ.get("AGENT_V2_BACKEND")
    try:
        os.environ["AGENT_V2_BACKEND"] = "native"
        backend = resolve_agent_v2_backend_choice("native")
        assert backend == "native_runtime"
    finally:
        if original is None:
            os.environ.pop("AGENT_V2_BACKEND", None)
        else:
            os.environ["AGENT_V2_BACKEND"] = original
