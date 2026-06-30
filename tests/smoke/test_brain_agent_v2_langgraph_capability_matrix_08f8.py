"""LangGraph capability matrix validation for 08F8.

Verifies that the canonical Agent V2 runtime exposes the production method
contract and that backend metadata is present in chat responses.
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


def test_runtime_contract_metadata(session):
    r = session.get(f"{BASE_URL}/v2/agent/status", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["backend_default"] == "langgraph_parity"
    assert data["rollback_backend"] == "native_runtime"
    assert data["runtime_type"] == "LangGraphParityRuntimeV2"
    assert data["trace_available"] is True
    assert data["checkpointed"] is True


def test_chat_response_contains_backend_metadata(session):
    r = session.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": "diagnostic ping", "mode": "agent", "user_id": "local"},
        timeout=120,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["backend_selected"] == "langgraph_parity"
    assert data["backend_default"] == "langgraph_parity"
    assert data["langgraph_default_active"] is True
    assert data["rollback_backend"] == "native_runtime"


def test_trace_endpoint_returns_events(session):
    r = session.post(
        f"{BASE_URL}/v2/chat/agent",
        json={"message": "create a trace", "mode": "agent", "user_id": "local"},
        timeout=120,
    )
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    tr = session.get(f"{BASE_URL}/v2/agent/runs/{run_id}/trace", timeout=15)
    assert tr.status_code == 200
    assert tr.json()["event_count"] > 0
