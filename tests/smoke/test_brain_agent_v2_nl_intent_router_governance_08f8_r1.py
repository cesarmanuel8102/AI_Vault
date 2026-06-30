"""Smoke test: Brain Agent V2 NL intent router and governance.

Covers bilingual Spanish/English intent classification, route selection, and
governance decisions for safe, approval-required, blocked, and dry-run intents.
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


def _post_chat(message: str, mode: str = "read_only", user_id: str = "smoke_intent_08f8"):
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
    "message,expected_intent,expected_route,expected_governance",
    [
        ("what can you do", "explain_capabilities", "direct_assistant", "allow"),
        ("qué puedes hacer", "explain_capabilities", "direct_assistant", "allow"),
        ("status of the repo", "read_only_status", "direct_assistant", "allow"),
        ("analyze the repo read-only", "repo_read", "brain_evidence", "allow"),
        ("diagnose the dashboard", "dashboard_diagnosis", "brain_evidence", "allow"),
        ("read from memory only", "memory_read", "brain_evidence", "allow"),
        ("modify the response normalizer code", "code_change_request", "operational_agent", "approval_required"),
        ("push changes to remote", "push_request", "operational_agent", "approval_required"),
        ("delete old log files", "delete_request", "operational_agent", "approval_required"),
        ("run autonomously in dry-run", "autonomy_dryrun", "operational_agent", "dry_run_only"),
        ("connect broker for live trading", "trading_broker_live", "direct_assistant", "blocked"),
        ("conecta broker para trading real", "trading_broker_live", "direct_assistant", "blocked"),
    ],
)
def test_intent_router_and_governance(message, expected_intent, expected_route, expected_governance):
    d = _post_chat(message, user_id=f"smoke_{expected_intent}_08f8")
    assert d["ok"] is True
    assert d.get("intent_detected") == expected_intent, f"message={message!r} got intent={d.get('intent_detected')}"
    assert d.get("intent_route") == expected_route, f"message={message!r} got route={d.get('intent_route')}"
    assert d.get("governance_decision") == expected_governance, f"message={message!r} got governance={d.get('governance_decision')}"
    assert d.get("provider_metadata") is not None
    assert "trace_url" in d
