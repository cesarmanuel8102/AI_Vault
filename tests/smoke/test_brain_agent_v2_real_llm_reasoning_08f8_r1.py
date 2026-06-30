"""Smoke test: Brain Agent V2 real LLM reasoning with explicit deterministic fallback.

Scope: verify that /v2/chat/agent uses Ollama-cloud LLM when reachable and reports
provider metadata; when unreachable, it falls back to deterministic parity finalizer.
"""
from __future__ import annotations
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tmp_agent"))


TOKEN = os.getenv("AGENTV2_TEST_ADMIN_TOKEN_08F8", "AGENTV2_TEST_ADMIN_TOKEN_08F8")
BASE = os.getenv("BRAIN_V2_BASE_URL", "http://127.0.0.1:8091")


def _post_chat(message: str, mode: str = "read_only", user_id: str = "smoke_llm_08f8"):
    try:
        import requests
    except Exception as exc:
        pytest.skip(f"requests not available: {exc}")
    r = requests.post(
        f"{BASE}/v2/chat/agent",
        headers={"Content-Type": "application/json", "X-Brain-Token": TOKEN},
        json={"message": message, "mode": mode, "user_id": user_id},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def test_capabilities_reports_real_llm_availability():
    import requests
    r = requests.get(
        f"{BASE}/v2/agent/capabilities",
        headers={"X-Brain-Token": TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    assert d["ok"] is True
    assert "real_llm_available" in d
    assert "active_provider" in d
    assert "supported_intents" in d
    assert "available_routes" in d
    assert d["memory_write_allowed"] is False
    assert d["trading_broker_allowed"] is False


def test_chat_uses_real_llm_when_available():
    d = _post_chat("what can you do")
    assert d["ok"] is True
    assert d["canonical_agent_v2"] is True
    provider = d.get("provider_metadata") or {}
    # If Ollama is reachable, expect ollama_cloud; otherwise deterministic fallback.
    assert provider.get("provider_used") in {"ollama_cloud", "deterministic_parity_finalizer"}
    assert d.get("final_answer")
    assert d.get("run_id")
    assert d.get("trace_url")


def test_chat_reports_fallback_when_provider_degraded(monkeypatch):
    import requests
    # Probe current provider state via chat response metadata.
    d = _post_chat("what can you do", user_id="smoke_fallback_probe")
    provider = d.get("provider_metadata") or {}
    if provider.get("provider_used") == "ollama_cloud":
        # Provider is healthy; we cannot force a fallback in this integration test.
        assert provider.get("provider_degraded") is False
        assert provider.get("fallback_reason") in {"none", ""}
    else:
        # Provider unavailable or fallback path used.
        assert provider.get("provider_degraded") is True
        assert provider.get("fallback_reason")
