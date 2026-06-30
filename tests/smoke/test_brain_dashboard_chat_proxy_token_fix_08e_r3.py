"""
Smoke test for FRONT-BRAIN-DASHBOARD-CHAT-PROXY-TOKEN-FIX-08E-R3.

Validates that tmp_agent.brain_v9.dashboard.dashboard_routes proxies
canonical Agent V2 chat and trace endpoints with the X-Brain-Token header
when BRAIN_ADMIN_TOKEN is configured, without leaking the token.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "R3_UNIT_TEST_ADMIN_TOKEN")

from tmp_agent.brain_v9.dashboard.dashboard_app import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_context_manager(payload: dict) -> MagicMock:
    """Return a MagicMock that behaves as a context manager yielding payload bytes."""
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _mock_urlopen_chat(ok: bool = True):
    def _inner(request, *args, **kwargs):
        # urllib normalizes header names to Title-Case (e.g., X-brain-token)
        assert request.get_header("X-brain-token") == "R3_UNIT_TEST_ADMIN_TOKEN"
        return _make_context_manager({
            "ok": ok,
            "final_answer": "hello",
            "run_id": "agv2_r3_test_run",
            "trace_url": "/v2/agent/runs/agv2_r3_test_run/trace",
            "provider_metadata": {},
        })

    return _inner


def _mock_urlopen_trace():
    def _inner(request, *args, **kwargs):
        # urllib normalizes header names to Title-Case (e.g., X-brain-token)
        assert request.get_header("X-brain-token") == "R3_UNIT_TEST_ADMIN_TOKEN"
        return _make_context_manager({
            "ok": True,
            "run_id": "agv2_r3_test_run",
            "trace": [],
        })

    return _inner


def test_dashboard_chat_proxy_forwards_token(client, monkeypatch):
    monkeypatch.setenv("BRAIN_ADMIN_TOKEN", "R3_UNIT_TEST_ADMIN_TOKEN")
    with patch("tmp_agent.brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _mock_urlopen_chat()):
        resp = client.post("/brain-dashboard/chat", json={
            "message": "r3 token forwarding check",
            "mode": "read_only",
            "user_id": "r3_smoke",
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["content"] == "hello"
    assert body["run_id"] == "agv2_r3_test_run"
    # Token must never appear in the response payload.
    assert "R3_UNIT_TEST_ADMIN_TOKEN" not in resp.text


def test_dashboard_trace_proxy_forwards_token(client, monkeypatch):
    monkeypatch.setenv("BRAIN_ADMIN_TOKEN", "R3_UNIT_TEST_ADMIN_TOKEN")
    with patch("tmp_agent.brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _mock_urlopen_trace()):
        resp = client.get("/brain-dashboard/agent-v2/runs/agv2_r3_test_run/trace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "R3_UNIT_TEST_ADMIN_TOKEN" not in resp.text


def test_dashboard_chat_proxy_no_token_when_unconfigured(client, monkeypatch):
    monkeypatch.delenv("BRAIN_ADMIN_TOKEN", raising=False)
    captured: list = []

    def _capture(request, *args, **kwargs):
        captured.append(request.get_header("X-Brain-Token"))
        return _make_context_manager({
            "ok": True,
            "final_answer": "hello",
            "run_id": "agv2_no_token_run",
            "trace_url": "/v2/agent/runs/agv2_no_token_run/trace",
            "provider_metadata": {},
        })

    with patch("tmp_agent.brain_v9.dashboard.dashboard_routes.urllib.request.urlopen", _capture):
        resp = client.post("/brain-dashboard/chat", json={
            "message": "r3 no token check",
            "mode": "read_only",
            "user_id": "r3_smoke",
        })
    assert resp.status_code == 200
    # When no token is configured, X-Brain-Token header must not be added.
    assert captured[0] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
