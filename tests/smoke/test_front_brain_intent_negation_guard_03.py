"""Smoke test: Agent V2 intent classifier does not escalate negated risky actions."""
from __future__ import annotations
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tmp_agent"))

from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent


def test_negated_memory_write_is_not_memory_write():
    result = classify_intent("Confirma estado operativo sin escribir memoria ni mutar FAISS.")
    assert result["intent"] != "memory_write"
    assert result["requires_approval"] is False
    assert result["risk_level"] == "safe"


def test_positive_memory_write_still_requires_approval():
    result = classify_intent("escribir memoria con esta leccion")
    assert result["intent"] == "memory_write"
    assert result["requires_approval"] is True
    assert result["risk_level"] == "approval_required"


def test_negated_broker_reference_is_not_live_trading():
    result = classify_intent("Diagnostica el agente sin conectar broker y sin ejecutar trade.")
    assert result["intent"] != "trading_broker_live"
    assert result["blocked_reason"] is None


def test_positive_broker_request_still_blocked():
    result = classify_intent("conecta broker para trading real")
    assert result["intent"] == "trading_broker_live"
    assert result["risk_level"] == "blocked"
    assert result["blocked_reason"]
