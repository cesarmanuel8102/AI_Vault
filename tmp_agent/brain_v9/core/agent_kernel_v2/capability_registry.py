"""Truthful capability registry for Brain Agent V2.

Reports current runtime state without faking capabilities. Real LLM availability
is probed by trying to reach the configured Ollama endpoint.
"""
from __future__ import annotations
import json
import urllib.request
from typing import Any, Dict, List

from brain_v9.config import API_ENDPOINTS, OLLAMA_MODEL, PRIMARY_KIMI_MODEL
from .intent_classifier import list_supported_intents, INTENT_ROUTE_MAP
from .tool_gateway import ToolGatewayV2
from .governance_policy import summarize_governance_modes


PRIMARY_MODEL = PRIMARY_KIMI_MODEL
FALLBACK_MODELS = ["deepseek-v4-pro:cloud", "gpt-oss:120b-cloud", "kimi-k2.5:cloud"]


def _probe_ollama_reachable() -> bool:
    """Lightweight probe: list local models on Ollama."""
    url = API_ENDPOINTS["ollama"].replace("/api/chat", "/api/tags")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET", headers={"Accept": "application/json"}), timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _available_models() -> List[str]:
    models = []
    if _probe_ollama_reachable():
        models = [PRIMARY_MODEL] + FALLBACK_MODELS + [OLLAMA_MODEL]
    return models


def build_capability_report(runtime: Any) -> Dict[str, Any]:
    """Build a truthful capability report for the current runtime."""
    tg = ToolGatewayV2()
    caps = tg.list_capabilities()
    available_models = _available_models()
    real_llm_available = bool(available_models)
    provider_candidates = available_models if available_models else ["ollama_cloud (unreachable)", "deterministic_parity_finalizer"]
    active_provider = "ollama_cloud" if real_llm_available else "deterministic_parity_finalizer"

    backend_default = getattr(runtime, "backend_default", "langgraph_parity")
    backend_selected = getattr(runtime, "backend_selected", getattr(runtime, "backend", "langgraph_parity"))
    runtime_type = getattr(runtime, "runtime_type", type(runtime).__name__)
    rollback_backend = getattr(runtime, "rollback_backend", "native_runtime")

    tool_categories: Dict[str, List[str]] = {}
    for c in caps:
        risk = c.get("risk_level", "unknown")
        tool_name = c.get("name")
        if not tool_name:
            continue
        tool_categories.setdefault(risk, []).append(tool_name)

    return {
        "ok": True,
        "canonical": True,
        "capabilities_version": "08F8-R1",
        "backend_default": backend_default,
        "backend_selected": backend_selected,
        "runtime_type": runtime_type,
        "langgraph_default_active": backend_default == "langgraph_parity",
        "rollback_backend": rollback_backend,
        "real_llm_available": real_llm_available,
        "provider_candidates": provider_candidates,
        "active_provider": active_provider,
        "deterministic_fallback_available": True,
        "supported_intents": list_supported_intents(),
        "available_routes": sorted(set(INTENT_ROUTE_MAP.values())),
        "available_tools_count": len(caps),
        "tool_categories": tool_categories,
        "tools_available": [c.get("name") for c in caps if c.get("name")],
        "memory_read_available": True,
        "memory_write_allowed": False,
        "faiss_mutation_allowed": False,
        "trading_broker_allowed": False,
        "autonomy_modes": ["dry_run_only_by_default", "approval_required_for_unsupervised"],
        "self_improvement_modes": ["report_only_by_default", "approval_required_to_apply"],
        "governance_summary": summarize_governance_modes(),
        "known_gaps": [
            "Streaming responses not implemented for /v2/chat/agent",
            "LLM provider requires reachable Ollama/cloud endpoint; otherwise falls back to deterministic finalizer",
        ],
    }


def list_tool_capabilities() -> List[Dict[str, Any]]:
    return ToolGatewayV2().list_capabilities()
