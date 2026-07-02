"""Smoke tests for Brain Agent V2 canonical self-knowledge index v1."""
from __future__ import annotations

import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9.core.agent_kernel_v2.evidence_tools import dispatch_evidence_tool
from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent
from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2
import brain_v9.core.agent_kernel_v2.langgraph_parity_runtime as _lg_runtime
from brain_v9.core.agent_kernel_v2.planner import build_plan, classify_goal
from brain_v9.core.agent_kernel_v2.self_knowledge_index import (
    brain_self_knowledge_lookup,
    list_self_knowledge_domains,
)
from brain_v9.core.agent_kernel_v2.tool_gateway import ToolCallRequest, ToolGatewayV2


REQUIRED_DOMAINS = {
    "agent_v2_runtime",
    "langgraph_parity",
    "dashboard",
    "memory_semantic_faiss",
    "promotion_queue",
    "curated_knowledge",
    "financial_autonomy",
    "trading_qc_ibkr",
    "governance_approval",
    "capabilities_tools",
    "ci_tests",
    "known_gaps",
}


def _fake_finalize_agent_run(**kwargs):
    names = [item.get("tool_name") for item in kwargs.get("tool_results", [])]
    return "tools executed: " + ", ".join(str(name) for name in names), {
        "provider_used": "mock",
        "model_used": "mock",
        "provider_degraded": False,
        "fallback_reason": "",
        "live_llm_called": False,
    }


def test_self_knowledge_index_contains_required_domains():
    domains = set(list_self_knowledge_domains())
    assert REQUIRED_DOMAINS.issubset(domains)


def test_lookup_routes_dashboard_queue_question_to_authoritative_domains():
    out = brain_self_knowledge_lookup("por que dashboard cuenta 57 en promotion queue", top_k=3)
    assert out["ok"] is True
    assert out["mutated_state"] is False
    matched = [item["canonical_domain"] for item in out["evidence"]["matched_domains"]]
    assert "promotion_queue" in matched
    assert "dashboard" in matched
    assert "promotion_queue_status" in out["evidence"]["required_tools_union"]
    assert "/brain-dashboard/status" in out["evidence"]["authoritative_endpoints_union"]


def test_lookup_financial_autonomy_distinguishes_research_from_real_money():
    out = brain_self_knowledge_lookup("estado del sistema financiero autonomo y trading real", top_k=4)
    matched = [item["canonical_domain"] for item in out["evidence"]["matched_domains"]]
    assert "financial_autonomy" in matched
    assert "trading_qc_ibkr" in matched
    flat_rules = "\n".join(rule for item in out["evidence"]["matched_domains"] for rule in item["do_not_infer"])
    assert "real-money" in flat_rules or "real money" in flat_rules


def test_dispatch_and_tool_gateway_expose_self_knowledge_readonly():
    dispatched = dispatch_evidence_tool("brain_self_knowledge_lookup", {"query": "autoconocimiento del brain"})
    assert dispatched["ok"] is True
    assert dispatched["mutated_state"] is False

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest(tool_name="brain_self_knowledge_lookup", args={"query": "dashboard"}, mode="read_only"))
    assert result.ok is True
    assert result.blocked is False
    assert result.result["matched_domains"]


def test_planner_schedules_self_knowledge_before_specific_evidence_tools():
    classification, plan, metadata = build_plan(
        "Dime con evidencia donde buscar el autoconocimiento del Brain, sus capacidades, dashboard, memoria y brechas.",
        "read_only",
    )
    tools = [step.get("tool_name") for step in plan if step.get("tool_name")]
    assert classification == "brain_self_knowledge_lookup"
    assert tools[0] == "brain_self_knowledge_lookup"
    assert "capability_registry_read" in tools
    assert "brain_self_knowledge_lookup" in metadata["scheduled_tools"]


def test_intent_classifier_routes_self_knowledge_to_brain_evidence():
    out = classify_intent("Analiza el autoconocimiento del Brain y dime dónde debes buscar para responder sobre ti mismo")
    assert out["intent"] == "brain_self_knowledge_lookup"
    assert out["route"] == "brain_evidence"
    assert out["requires_approval"] is False


def test_langgraph_runtime_executes_self_knowledge_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(_lg_runtime, "finalize_agent_run", _fake_finalize_agent_run)
    rt = LangGraphParityRuntimeV2(run_root=str(tmp_path / "self_knowledge_runs"))
    out = rt.run(
        "Dime con evidencia dónde buscar tu autoconocimiento del sistema Brain completo.",
        "read_only",
        "self_knowledge_smoke",
    )
    tools = [item.get("tool_name") for item in out.get("tool_results", [])]
    assert out.get("intent_route") == "brain_evidence"
    assert out.get("classification") == "brain_self_knowledge_lookup"
    assert "brain_self_knowledge_lookup" in tools
    assert "file_patch_dry_run" not in tools
    assert "file_patch_apply_approval_required" not in tools
