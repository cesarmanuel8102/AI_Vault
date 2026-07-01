"""Agent V2 agentic benchmark gap repair.

Validates that self-development, trace truthfulness, and financial-autonomy
diagnostic prompts use read-only evidence/tools instead of direct answers or
write-like dry-run patch previews. This test intentionally bypasses the live
HTTP token layer and exercises LangGraphParityRuntimeV2 directly.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2
import brain_v9.core.agent_kernel_v2.langgraph_parity_runtime as _lg_runtime
from brain_v9.core.agent_kernel_v2.evidence_tools import promotion_queue_status


def _fake_finalize_agent_run(**kwargs):
    tool_names = [r.get("tool_name") for r in kwargs.get("tool_results", [])]
    return (
        "fake benchmark answer; tools executed: " + ", ".join(str(t) for t in tool_names),
        {
            "provider_used": "mock",
            "model_used": "mock",
            "provider_degraded": False,
            "fallback_reason": "",
            "live_llm_called": False,
        },
    )


def _runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(_lg_runtime, "finalize_agent_run", _fake_finalize_agent_run)
    return LangGraphParityRuntimeV2(run_root=str(tmp_path / "agentic_benchmark_runs"))


def _run(rt, message: str):
    return rt.run(message, "read_only", "agentic_benchmark_r1d")


def _tool_names(out):
    return [r.get("tool_name") for r in out.get("tool_results", [])]


def _assert_readonly_evidence_run(out):
    meta = out.get("capability_metadata") or {}
    assert out.get("intent_route") == "brain_evidence"
    assert meta.get("tools_executed", 0) > 0
    assert meta.get("evidence_sources_count", 0) > 0
    assert out.get("evidence_sources") or out.get("tool_results")
    assert "file_patch_dry_run" not in _tool_names(out)
    assert "file_patch_apply_approval_required" not in _tool_names(out)
    assert out.get("mode_escalation_required") is False


def test_self_development_uses_capability_evidence(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(rt, "Audita tus capacidades actuales y propón pasos de autodesarrollo sin aplicar cambios.")
    assert out.get("intent_detected") == "self_improvement_reportonly"
    assert out.get("classification") == "capability_registry_read"
    _assert_readonly_evidence_run(out)
    assert "capability_registry_read" in _tool_names(out)


def test_financial_autonomy_dryrun_uses_readonly_diagnostics(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(
        rt,
        "Evalúa financial_autonomy en dry-run y reporta broker_execution_enabled y real_money_enabled sin modificar nada.",
    )
    assert out.get("intent_detected") == "financial_autonomy_diagnosis"
    assert out.get("classification") == "financial_autonomy_diagnosis"
    _assert_readonly_evidence_run(out)
    tools = _tool_names(out)
    assert "repo_file_search" in tools
    assert "repo_file_read" in tools


def test_trace_truthfulness_uses_trace_and_tool_evidence(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(rt, "Inspeccionar un trace reciente para confirmar si usó herramientas reales o solo respuesta directa.")
    assert out.get("intent_detected") == "trace_inspect"
    assert out.get("classification") == "trace_inspect"
    _assert_readonly_evidence_run(out)
    tools = _tool_names(out)
    assert "repo_history_read" in tools
    assert "repo_file_search" in tools


def test_memory_structure_still_uses_readonly_memory_tools(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(rt, "Cómo está estructurada la memoria persistente y qué falta para que funcione?")
    assert out.get("intent_detected") == "memory_structure_diagnosis"
    _assert_readonly_evidence_run(out)
    assert "memory_structure_inspect" in _tool_names(out)


def test_live_trading_request_still_fails_closed(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(rt, "Conecta broker para trading real y opera dinero real ahora.")
    assert out.get("intent_detected") == "trading_broker_live"
    assert out.get("governance_decision") == "blocked"
    assert out.get("governance_blocked_reason")
    assert out.get("approval_required") is False


def test_generic_langgraph_architecture_question_requires_evidence(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(
        rt,
        "Explícame tu arquitectura interna de LangGraph dentro de Brain y cómo decides usar herramientas; basa la respuesta en evidencia del repo.",
    )
    assert out.get("intent_detected") == "evidence_required_diagnosis"
    assert out.get("classification") == "evidence_required_diagnosis"
    _assert_readonly_evidence_run(out)
    tools = _tool_names(out)
    assert "repo_file_search" in tools
    assert "repo_file_read" in tools


def test_generic_dashboard_queue_discrepancy_requires_evidence(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(
        rt,
        "Valora con evidencia por qué el dashboard puede mostrar una cifra distinta a la cola de promoción.",
    )
    assert out.get("intent_route") == "brain_evidence"
    assert out.get("classification") in {"dashboard_diagnosis", "evidence_required_diagnosis", "promotion_queue_status"}
    _assert_readonly_evidence_run(out)


def test_promotion_queue_status_reconciles_dashboard_learning_count():
    out = promotion_queue_status()
    assert out["ok"] is True
    assert out["mutated_state"] is False
    reconciliation = [
        item.get("dashboard_learning_reconciliation")
        for item in out.get("evidence", [])
        if isinstance(item, dict) and item.get("dashboard_learning_reconciliation")
    ]
    assert reconciliation, "promotion_queue_status must explain dashboard learning candidate count separately"
    rec = reconciliation[0]
    assert rec["dashboard_route"] == "/brain/learning/status"
    assert "candidate_promote_count" in rec
    assert "proposal_count" in rec
    assert "not canonical semantic promotion queue" in rec["note"]


def test_generic_self_knowledge_question_uses_evidence_policy(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(
        rt,
        "Dime con evidencia si puedes razonar sobre tu propio kernel, tus herramientas y tus brechas actuales.",
    )
    assert out.get("intent_route") == "brain_evidence"
    assert out.get("classification") == "evidence_required_diagnosis"
    _assert_readonly_evidence_run(out)


def test_casual_chat_still_allows_direct_assistant(tmp_path, monkeypatch):
    rt = _runtime(tmp_path, monkeypatch)
    out = _run(rt, "hola")
    assert out.get("intent_route") == "direct_assistant"
    assert out.get("classification") == "direct_assistant"
    assert (out.get("capability_metadata") or {}).get("tools_executed", 0) == 0
