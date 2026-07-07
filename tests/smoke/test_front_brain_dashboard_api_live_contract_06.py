"""Live dashboard/API contract checks for local Brain 8091 + dashboard 8092.

These tests are intentionally skip-safe when the local services are not running,
so they can live in the repo without making CI depend on a developer runtime.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BRAIN = "http://127.0.0.1:8091"
DASH = "http://127.0.0.1:8092"
TOKEN_LITERAL = "REDACTED_TEST_TOKEN_SHOULD_NOT_APPEAR"


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def _json_request(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None, timeout: int = 30) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


@pytest.fixture(scope="module")
def live_services_available():
    if not (_port_open(8091) and _port_open(8092)):
        pytest.skip("local Brain 8091 and dashboard 8092 are not running")
    return True


def test_dashboard_static_contract_does_not_expose_operator_token():
    html = (ROOT / "tmp_agent/brain_v9/dashboard/static/index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "tmp_agent/brain_v9/dashboard/static/app.js").read_text(encoding="utf-8")

    assert TOKEN_LITERAL not in html
    assert TOKEN_LITERAL not in app_js
    assert "/brain-dashboard/chat" in app_js
    assert "X-Brain-Token" not in app_js
    assert "raw_cot_exposed" in app_js
    assert "trace_url" in app_js


def test_dashboard_health_and_agent_status_proxy_live(live_services_available):
    health = _json_request(f"{DASH}/health")
    assert health["ok"] is True
    assert health["port"] == 8092

    status = _json_request(f"{DASH}/brain-dashboard/agent-v2/status")
    assert status["ok"] is True
    agent = status["agent_v2"]
    assert agent["canonical_for_new_agent_runs"] is True
    assert agent["backend_selected"] == "langgraph_parity"
    assert agent["langgraph_default_active"] is True
    assert agent["primary_finalizer_model"] == "kimi-k2.6:cloud"


def test_dashboard_chat_proxy_live_returns_canonical_agent_and_trace(live_services_available):
    payload = {
        "message": "Responde una linea: estado operativo read-only, sin escribir memoria y sin broker.",
        "mode": "read_only",
        "user_id": "dashboard_live_contract_06",
    }
    try:
        chat = _json_request(f"{DASH}/brain-dashboard/chat", method="POST", body=payload, timeout=120)
    except urllib.error.HTTPError as exc:
        pytest.fail(f"dashboard chat proxy returned HTTP {exc.code}")

    assert chat["ok"] is True
    assert chat["canonical_agent_v2"] is True
    assert chat["run_id"]
    assert chat["trace_url"]
    assert chat["provider_used"] == "ollama_cloud"
    assert chat["model_used"] == "kimi-k2.6:cloud"
    assert chat["raw_cot_exposed"] is False
    assert chat["mode_effective"] == "read_only"
    assert chat["blocked_tools"] == []

    trace = _json_request(f"{DASH}/brain-dashboard/agent-v2/runs/{chat['run_id']}/trace", timeout=30)
    assert trace["ok"] is True
    assert trace["run_id"] == chat["run_id"]
    assert trace["event_count"] >= 1
    assert any(event.get("event_type") == "run_completed" for event in trace["trace"])


def test_direct_agent_rejects_missing_token_when_live(live_services_available):
    payload = {"message": "hola", "mode": "read_only", "user_id": "missing_token_contract_06"}
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _json_request(f"{BRAIN}/v2/chat/agent", method="POST", body=payload, timeout=30)
    assert excinfo.value.code == 403
