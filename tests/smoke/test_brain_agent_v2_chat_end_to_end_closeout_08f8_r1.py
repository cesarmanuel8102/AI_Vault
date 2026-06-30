"""Smoke test: end-to-end closeout battery for /v2/chat/agent.

Runs a small deterministic subset of the 20-prompt closeout battery and asserts
that the response contract contains all required fields.
"""
from __future__ import annotations
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tmp_agent"))


TOKEN = os.getenv("AGENTV2_TEST_ADMIN_TOKEN_08F8", "AGENTV2_TEST_ADMIN_TOKEN_08F8")
BASE = os.getenv("BRAIN_V2_BASE_URL", "http://127.0.0.1:8091")


REQUIRED_TOP_LEVEL_FIELDS = {
    "ok", "canonical_agent_v2", "route", "run_id", "final_answer", "provider_metadata",
    "capability_metadata", "mode_requested", "mode_effective", "mode_escalation_required",
    "approval_required", "confirmation_id", "required_permission", "expected_write_scope",
    "trace_url", "blocked_tools", "intent_route", "intent_detected", "intent_confidence",
    "classification", "status", "backend", "backend_selected", "runtime_type",
}


def _post_chat(message: str, mode: str = "read_only", user_id: str = "smoke_e2e_08f8"):
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


@pytest.mark.parametrize(
    "message,expected_intent",
    [
        ("what can you do", "explain_capabilities"),
        ("analyze the repo read-only", "repo_read"),
        ("push changes to remote", "push_request"),
        ("connect broker for live trading", "trading_broker_live"),
    ],
)
def test_chat_response_contract_and_intent(message, expected_intent):
    d = _post_chat(message, user_id=f"smoke_e2e_{expected_intent}_08f8")
    assert d["ok"] is True
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(d.keys())
    assert not missing, f"missing fields: {missing}"
    assert d.get("intent_detected") == expected_intent, f"got {d.get('intent_detected')}"
    assert d.get("provider_metadata", {}).get("provider_used")
    assert d.get("capability_metadata", {}).get("trace_events_count") is not None
