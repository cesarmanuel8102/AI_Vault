"""Smoke test: /v2/agent/capabilities truthful capability report."""
from __future__ import annotations
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tmp_agent"))


TOKEN = os.getenv("AGENTV2_TEST_ADMIN_TOKEN_08F8", "AGENTV2_TEST_ADMIN_TOKEN_08F8")
BASE = os.getenv("BRAIN_V2_BASE_URL", "http://127.0.0.1:8091")


def test_capabilities_endpoint_truthful():
    try:
        import requests
    except Exception as exc:
        pytest.skip(f"requests not available: {exc}")
    r = requests.get(
        f"{BASE}/v2/agent/capabilities",
        headers={"X-Brain-Token": TOKEN},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    assert d["ok"] is True
    assert d["capabilities_version"] == "08F8-R1"
    assert d["backend_default"] == "langgraph_parity"
    assert "real_llm_available" in d
    assert "provider_candidates" in d
    assert "supported_intents" in d
    assert "available_routes" in d
    assert isinstance(d["tools_available"], list)
    assert len(d["tools_available"]) == d["available_tools_count"]
    assert "tool_categories" in d
    assert d["memory_write_allowed"] is False
    assert d["faiss_mutation_allowed"] is False
    assert d["trading_broker_allowed"] is False
    assert d["deterministic_fallback_available"] is True
