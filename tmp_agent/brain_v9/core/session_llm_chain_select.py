"""LLM chain selection heuristics + model priority normalization.

Extracted from BrainSession (B7-STRANGLER-10).

Design rules (do not break):
- No I/O, no network, no globals/state.
- Does NOT import brain_v9.core.session (avoids circular import).
"""
from __future__ import annotations

import re
from typing import Dict, List

from brain_v9.core import session_query_predicates as _qp
from brain_v9.core.llm import LLMManager

__all__ = [
    "MODEL_PRIORITY_ALIASES",
    "normalize_model_priority",
    "should_use_compact_chat_prompt",
    "should_use_analysis_frontier",
    "select_llm_chain",
]

MODEL_PRIORITY_ALIASES = {
    "deepseek-r1:14b": "deepseek14b",
    "deepseek-r1:32b": "deepseek14b",
    "qwen2.5:14b": "coder14b",
    "qwen2.5-coder:14b": "coder14b",
    "llama3.1:8b": "llama8b",
    "gemini": "chat",
    "auto": "chat",
    "default": "chat",
    "sonnet": "claude",
    "sonnet4": "claude",
    "frontier": "agent_frontier",
    "analysis_frontier": "analysis_frontier",
    "analysis": "analysis_frontier",
    "analysis_frontier_legacy": "analysis_frontier_legacy",
    "analysis_legacy": "analysis_frontier_legacy",
    "codex": "codex",
    "openai": "codex",
    "agent_legacy": "agent_legacy",
    "frontier_legacy": "agent_frontier_legacy",
    "agent_frontier_legacy": "agent_frontier_legacy",
    "code_legacy": "code_legacy",
    "chat_legacy": "chat_legacy",
}


def normalize_model_priority(model_priority: str, aliases=None) -> str:
    """Normalize a raw model-priority string via alias map."""
    if aliases is None:
        aliases = MODEL_PRIORITY_ALIASES
    normalized = (model_priority or "chat").strip().lower()
    return aliases.get(normalized, normalized)


def should_use_compact_chat_prompt(
    message: str,
    intent: str,
    history: List[Dict],
    model_priority: str,
    *,
    normalize_model_priority_func=normalize_model_priority,
) -> bool:
    """Return True if the message qualifies for the compact chat prompt."""
    if intent not in {"QUERY", "CONVERSATION"}:
        return False
    msg_l = (message or "").lower()
    if _qp.is_operational_agent_query(msg_l):
        return False
    if _qp.is_grounded_code_analysis_query(message):
        return False
    if _qp.is_llm_status_query(msg_l):
        return False
    if re.search(r"\b[a-z]:\\|\.py\b|\.json\b|/chat\b|/agent\b", message, re.IGNORECASE):
        return False
    compact_history = [m for m in history if m.get("role") in ("user", "assistant")]
    if len(compact_history) > 2:
        return False
    if LLMManager.estimate_tokens(message) > 48:
        return False
    requested = normalize_model_priority_func(model_priority or "chat")
    return requested in {"chat", "llama8b", "deepseek14b", "coder14b", "ollama"}


def should_use_analysis_frontier(
    message: str,
    intent: str,
    history: List[Dict],
    model_priority: str,
    *,
    normalize_model_priority_func=normalize_model_priority,
) -> bool:
    """Return True if the message should route through the analysis frontier chain."""
    requested = normalize_model_priority_func(model_priority or "chat")
    if requested in {"analysis_frontier", "analysis_frontier_legacy"}:
        return True
    if requested not in {"chat", "ollama", "agent_frontier", "agent_frontier_legacy"}:
        return False
    msg_l = (message or "").lower()
    if _qp.is_benign_security_audit_query(message):
        return True
    if intent not in {"ANALYSIS", "MEMORY", "QUERY", "CREATIVE"}:
        return False
    if _qp.is_brain_diagnostic_analysis_query(message):
        return True
    if _qp.is_grounded_code_analysis_query(message):
        return False
    if _qp.is_llm_status_query(msg_l):
        return False
    if _qp.is_recent_activity_query(msg_l) or _qp.is_chat_interaction_review_query(msg_l):
        return False
    hard_operational_markers = (
        "ejecuta", "corre", "run ", "scan ", "escanea", "escanear",
        "revisa ", "verifica", "diagnostica", "lista ", "lee ",
        "abre ", "busca ", "check ", "servicio", "servicios",
        "proceso", "procesos", "puerto", "puertos", "red local",
        "network", "log ", "logs", "archivo", "archivos",
    )
    if any(marker in msg_l for marker in hard_operational_markers):
        return False
    analysis_markers = (
        "explica", "explain", "que significa", "qué significa",
        "por que", "por qué", "why", "cause", "causa", "implica",
        "implicacion", "implicación", "evalua", "evalúa", "interpreta",
        "significa", "analiza", "analysis", "audita", "auditor",
    )
    technical_scope = (
        "codex", "llm", "modelo", "model", "brain", "agente", "agent",
        "chat", "prompt", "route", "routing", "latencia", "timeout",
        "sintesis", "síntesis", "fallback", "fastpath", "governance",
        "dashboard",
    )
    return any(marker in msg_l for marker in analysis_markers) and any(scope in msg_l for scope in technical_scope)


def select_llm_chain(
    message: str,
    intent: str,
    history: List[Dict],
    model_priority: str,
    *,
    normalize_model_priority_func=normalize_model_priority,
    should_use_analysis_frontier_func=should_use_analysis_frontier,
) -> str:
    """Select the LLM chain key for this message/intent/history."""
    requested = normalize_model_priority_func(model_priority or "chat")
    if intent == "CODE":
        return "code"
    if should_use_analysis_frontier_func(message, intent, history, requested):
        return "analysis_frontier" if requested != "analysis_frontier_legacy" else "analysis_frontier_legacy"
    return requested
