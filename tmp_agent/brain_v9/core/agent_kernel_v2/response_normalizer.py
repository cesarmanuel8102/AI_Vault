"""Response normalization adapter for Agent V2 chat responses.

Guarantees that /v2/chat/agent returns a stable schema regardless of backend
(Native or LangGraph parity). The normalizer fills missing optional fields
with safe defaults and preserves fields already consumed by frontend/dashboard.
It never mutates the input dict.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional


REQUIRED_TOP_LEVEL_FIELDS = (
    "ok",
    "canonical_agent_v2",
    "route",
    "run_id",
    "final_answer",
    "provider_metadata",
    "capability_metadata",
    "mode_requested",
    "mode_effective",
    "mode_escalation_required",
    "approval_required",
    "confirmation_id",
    "required_permission",
    "expected_write_scope",
    "trace_url",
    "blocked_tools",
    "intent_route",
    "intent_detected",
    "intent_confidence",
    "classification",
    "status",
    "auto_decision",
    "backend",
    "backend_selected",
    "backend_default",
    "backend_fallback_used",
    "backend_fallback_reason",
    "runtime_type",
    "langgraph_default_active",
    "rollback_backend",
    "error",
    "detail",
)

REQUIRED_PROVIDER_METADATA_FIELDS = (
    "provider_used",
    "model_used",
    "provider_degraded",
    "fallback_reason",
)

REQUIRED_CAPABILITY_METADATA_FIELDS = (
    "memory_used",
    "retrieval_attempted",
    "retrieval_no_results",
    "retrieval_skipped",
    "planner_used",
    "evidence_routed",
    "evidence_sources_count",
    "tools_considered",
    "tools_executed",
    "tools_blocked",
    "governance_checked",
    "trace_events_count",
    "intent_route",
    "classification",
)


def normalize_provider_metadata(
    raw_provider_metadata: Optional[Dict[str, Any]],
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a normalized provider_metadata dict with all required keys."""
    raw = raw or {}
    src = raw_provider_metadata or {}
    degraded = src.get("provider_degraded") if "provider_degraded" in src else raw.get("provider_degraded")
    fallback = src.get("fallback_reason") if "fallback_reason" in src else raw.get("fallback_reason")
    provider = src.get("provider_used") or raw.get("provider") or src.get("provider")
    return {
        "provider_used": src.get("provider_used") or provider or "unknown",
        "model_used": src.get("model_used") or raw.get("model_used") or "unknown",
        "provider_degraded": bool(degraded) if degraded is not None else False,
        "fallback_reason": fallback if fallback is not None else "",
    }


def normalize_capability_metadata(
    raw_capability_metadata: Optional[Dict[str, Any]],
    raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a normalized capability_metadata dict with all required keys."""
    raw = raw or {}
    src = raw_capability_metadata or {}
    plan = raw.get("plan") or []
    evidence_sources = raw.get("evidence_sources") or []
    tool_results = raw.get("tool_results") or []
    intent_route = src.get("intent_route") or raw.get("intent_route")
    semantic_steps = [s for s in plan if s.get("tool_name") == "semantic_retrieve"]
    retrieval_attempted = src.get("retrieval_attempted") if "retrieval_attempted" in src else bool(semantic_steps)
    retrieval_no_results = src.get("retrieval_no_results") if "retrieval_no_results" in src else any(
        not (s.get("output", {}).get("result", {}).get("hits", []))
        for s in semantic_steps
    )
    retrieval_skipped = src.get("retrieval_skipped") if "retrieval_skipped" in src else (
        not retrieval_attempted and intent_route not in {"direct_assistant", "promotion_adapter_dry_run"}
    )
    tools_considered = src.get("tools_considered") if "tools_considered" in src else len(
        [s for s in plan if s.get("tool_name")]
    )
    tools_executed = src.get("tools_executed") if "tools_executed" in src else len(
        [s for s in plan if s.get("status") in ("completed", "failed", "blocked")]
    )
    return {
        "memory_used": bool(src.get("memory_used")) if "memory_used" in src else retrieval_attempted,
        "retrieval_attempted": retrieval_attempted,
        "retrieval_no_results": bool(retrieval_no_results),
        "retrieval_skipped": bool(retrieval_skipped),
        "planner_used": bool(src.get("planner_used")) if "planner_used" in src else bool(plan and any(s.get("tool_name") for s in plan)),
        "evidence_routed": bool(src.get("evidence_routed")) if "evidence_routed" in src else bool(evidence_sources or tool_results),
        "evidence_sources_count": src.get("evidence_sources_count") if "evidence_sources_count" in src else (len(evidence_sources) if evidence_sources else len(tool_results)),
        "tools_considered": tools_considered,
        "tools_executed": tools_executed,
        "tools_blocked": src.get("tools_blocked") if "tools_blocked" in src else len(raw.get("blocked_tools") or []),
        "governance_checked": bool(src.get("governance_checked")) if "governance_checked" in src else bool(
            raw.get("mode_escalation_required") or raw.get("blocked_tools")
        ),
        "trace_events_count": src.get("trace_events_count") if "trace_events_count" in src else len(raw.get("trace_events") or []),
        "intent_route": intent_route or raw.get("classification") or "unknown",
        "classification": src.get("classification") or raw.get("classification") or intent_route or "unknown",
    }


def normalize_trace_url(raw: Dict[str, Any]) -> Optional[str]:
    """Return a normalized trace_url or None if run_id is missing."""
    if raw.get("trace_url"):
        return str(raw["trace_url"])
    run_id = raw.get("run_id")
    if run_id:
        return f"/v2/agent/runs/{run_id}/trace"
    return None


def normalize_blocked_tools(raw: Dict[str, Any]) -> List[str]:
    """Return blocked_tools as a list of strings."""
    bt = raw.get("blocked_tools")
    if bt is None:
        return []
    if isinstance(bt, list):
        return [str(x) for x in bt]
    if isinstance(bt, (set, tuple)):
        return [str(x) for x in bt]
    if isinstance(bt, (int, float, bool)):
        return [str(bt)]
    if isinstance(bt, str):
        return [bt] if bt else []
    return [str(bt)]


def _extract_final_answer(raw: Dict[str, Any]) -> Optional[str]:
    """Extract the best final_answer string from common keys."""
    for key in ("final_answer", "content", "response", "message", "answer"):
        val = raw.get(key)
        if val is not None and str(val):
            return str(val)
    return ""


# Repair FIX_A (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02):
# Post-response identity guard. Detects Claude-style disclaimers that the cloud
# LLM produces despite the AGENT_V2_IDENTITY_PREAMBLE in finalizer.system_content,
# and rewrites the answer to state the truthful Agent V2 identity + capability
# distinction (system has tools; this run may or may not have used them).
# Runs unconditionally on every /v2/chat/agent response regardless of backend.
_CLAUDE_DISCLAIMER_PATTERNS = [
    # English identity denials (sentence-bounded)
    re.compile(r"(?i)\bas an? (ai|language model|artificial intelligence)\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi am (an? |just |only )?(ai|language model|large language model|assistant (made|created|built) by (anthropic|openai|meta))[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi am claude\b[^.!?\n]*[.!?]"),
    # English capability denials
    re.compile(r"(?i)\bi (do not|don['\u2019]?t|cannot|can['\u2019]?t) have (access to|the ability|any) (tools|internet|memory|persistent memory|real-time|external)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi cannot (execute code|access tools|remember prior sessions|browse the internet)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi (do not|don['\u2019]?t) (have|possess) tools\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi have no (tools|memory|persistent memory|access to)[^.!?\n]*[.!?]"),
    # Spanish identity denials
    re.compile(r"(?i)\bsoy (una?|un) (ia|modelo de lenguaje|asistente (creado|hecho) por (anthropic|openai))[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bsoy solo un modelo de lenguaje\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bsoy (una?|un) modelo de lenguaje\b[^.!?\n]*[.!?]"),
    # Spanish capability denials
    re.compile(r"(?i)\bno (tengo|puedo|dispongo) (acceso a|la capacidad|herramientas|memoria persistente|internet|ejecutar c\u00f3digo|ejecutar codigo|usar herramientas)[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno puedo (ejecutar|acceder|usar|recordar) [^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno tengo (herramientas|memoria|acceso)[^.!?\n]*[.!?]"),
    # Repair FIX_B (front-brain-agent-v2-session-memory-truth-and-continuity-01):
    # Memory/session persistence denials that slipped past the FIX_A pattern set.
    # Triggered by observed run agv2_0ea89c34bea6a903 (2026-07-02T05:22:46Z) which
    # denied Brain's persistent-memory capability while runs_parity/ ARE persisting
    # every turn and semantic_memory + FAISS index (1794 entries) exist read-only.
    # Additive only; existing patterns above are untouched.
    # Spanish
    re.compile(r"(?i)\bcada interacci[oó]n( que tenemos)? es independiente\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno queda escrito en ning[uú]n lugar persistente\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno hay una?[^.!?\n]*?sesi[oó]n anterior[^.!?\n]*?guard[aá]ndo(se)?\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno existe una? memoria de chat que persista\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bno tengo memoria de conversaciones (pasadas|anteriores)\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bpara m[ií] es como empezar de nuevo\b[^.!?\n]*[.!?]"),
    # English
    re.compile(r"(?i)\beach (interaction|conversation)( we have)? is independent\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bnothing is (written|saved|stored)[^.!?\n]*persistent[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bthere is no (chat|conversation) memory that persists\b[^.!?\n]*[.!?]"),
    re.compile(r"(?i)\bi don['\u2019]?t (have|retain) (any )?memory (of|between|across) (past|prior|previous) (conversations|sessions|interactions)\b[^.!?\n]*[.!?]"),
]

_IDENTITY_REPLACEMENT_ES = (
    "Soy Canonical Agent V2 dentro de Brain Chat V9 "
    "(backend runtime: langgraph_parity, LangGraphParityRuntimeV2). "
    "El sistema tiene tools disponibles (file_read, grep_search, "
    "brain_self_knowledge_lookup, capability_registry_read, semantic_retrieve, "
    "memory_structure_inspect, promotion_queue_status, semantic_memory_status, "
    "trace_inspect, repo_status_read, repo_history_read, route_probe, "
    "smoke_test_readonly, repo_file_search, repo_file_read), pero en esta "
    "ejecuci\u00f3n pueden o no haberse usado. En modo read_only no ejecuto "
    "writes ni toco broker/memoria/FAISS. "
    "Brain S\u00cd tiene memoria persistente como sistema: el \u00edndice FAISS y "
    "la semantic memory conservan entradas indexadas, y cada turno de chat se "
    "escribe en runs_parity/ (run.json + trace.jsonl) para poder ser recuperado "
    "posteriormente. En este modo read_only la escritura autom\u00e1tica en "
    "FAISS/semantic est\u00e1 gobernada (requiere approval); eso no equivale a "
    "'no existe memoria'. Si en este run no se ejecutaron tools de memoria, "
    "dilo as\u00ed, pero no niegues la capacidad del sistema."
)

_IDENTITY_REPLACEMENT_EN = (
    "I am Canonical Agent V2 inside Brain Chat V9 "
    "(backend runtime: langgraph_parity, LangGraphParityRuntimeV2). "
    "The system has tools available (file_read, grep_search, "
    "brain_self_knowledge_lookup, capability_registry_read, semantic_retrieve, "
    "memory_structure_inspect, promotion_queue_status, semantic_memory_status, "
    "trace_inspect, repo_status_read, repo_history_read, route_probe, "
    "smoke_test_readonly, repo_file_search, repo_file_read), but in this "
    "execution they may or may not have been used. In read_only mode I do not "
    "execute writes and do not touch broker/memory/FAISS. "
    "Brain DOES have persistent memory as a system: the FAISS index and semantic "
    "memory retain indexed entries, and every chat turn is written to "
    "runs_parity/ (run.json + trace.jsonl) so it can be retrieved later. In "
    "this read_only mode automatic writes to FAISS/semantic memory are "
    "governed (require approval); that is not equivalent to 'no memory exists'. "
    "If no memory tools were executed in this run, say so, but do not deny the "
    "capability of the system."
)

_SPANISH_HINT_RE = re.compile(
    r"\b(soy|no tengo|no puedo|memoria|herramientas|est\u00e1|est\u00e1s|c\u00f3mo|"
    r"qu\u00e9|d\u00f3nde|pruebas|reconc\u00edlialo|autonom\u00eda)\b",
    re.IGNORECASE,
)


def _identity_guard_rewrite(text: Optional[str], intent_route: Optional[str] = None) -> tuple:
    """Detect Claude-style disclaimers in the final answer and rewrite with the
    truthful Agent V2 identity + capability disclosure. Returns
    (rewritten_text, metadata_dict). Safe on empty / None input."""
    if not text:
        return (text or ""), {
            "triggered": False,
            "matched_patterns": [],
            "original_length": 0,
            "rewritten_length": 0,
            "language": "unknown",
        }
    original_length = len(text)
    matched = []
    result = text
    for i, pattern in enumerate(_CLAUDE_DISCLAIMER_PATTERNS):
        for m in pattern.finditer(result):
            matched.append({
                "pattern_index": i,
                "matched_text": m.group(0)[:200],
                "start": m.start(),
                "end": m.end(),
            })
        result = pattern.sub("", result)
    triggered = bool(matched)
    if triggered:
        # Choose replacement language based on original text hints.
        is_spanish = bool(_SPANISH_HINT_RE.search(text))
        replacement = _IDENTITY_REPLACEMENT_ES if is_spanish else _IDENTITY_REPLACEMENT_EN
        result = replacement + "\n\n" + result.strip()
    return result, {
        "triggered": triggered,
        "matched_patterns": matched,
        "original_length": original_length,
        "rewritten_length": len(result),
        "language": ("es" if triggered and _SPANISH_HINT_RE.search(text) else ("en" if triggered else "unknown")),
    }


_FINALIZER_BOILERPLATE_PATTERNS = [
    re.compile(r"(?im)^#{1,3}\s*Finalizaci[oó]n de Ejecuci[oó]n Agent V2[^\n]*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Summary\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Evidence used\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Actions performed\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Risks?/?\s*gates?\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Next safe action\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Brain evidence\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Reasoning\s*\n*"),
    re.compile(r"(?im)^#{1,3}\s*Conclusion\s*\n*"),
    re.compile(r"(?im)^I(?:'| a)m?\s*(?:will|going to|about to)\s+finalize this Agent V2 run[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^I'll finalize this Agent V2 run[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^This is an? (?:evidence[- ]required|read[- ]only evidence)\s*(?:diagnosis\s*)?run[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^The user (?:requested|asked)[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^Requested vs\.?\s*(?:Scheduled(?:\s*vs\.?\s*Executed)?)?[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*LIVE TOOL EVIDENCE\*\*[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*MEMORY EVIDENCE\*\*[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^Goal:[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*Goal:\*\*[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*Resultado actual:\*\*[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*Classification:\*\*[^\n]*\n+", re.IGNORECASE),
    re.compile(r"(?im)^\*\*Mode:\*\*[^\n]*\n+", re.IGNORECASE),
]

_FINALIZER_SENTENCE_PREFIXES = [
    re.compile(r"(?im)^I'll finalize this Agent V2 run using only the provided evidence[,.]?\s+Distinguish requested vs scheduled vs executed tools clearly\.?\s+Do not claim tools are unavailable when they were simply not scheduled\.?\s*", re.IGNORECASE),
    re.compile(r"(?im)^I(?:'| a)m?\s*(?:will|going to)\s+finalize this Agent V2 run[^.]*\.\s*", re.IGNORECASE),
    re.compile(r"(?im)^This is an? evidence[- ]required diagnosis run in read[- ]only mode\.?\s*The user asked:?\s*", re.IGNORECASE),
    re.compile(r"(?im)^The user (?:requested|asked):\s*\*?[^\n]*\*?\.?\s*(?:This run executed in read[- ]only mode\.?)?\s*", re.IGNORECASE),
    re.compile(r"(?im)^This run executed in read[- ]only mode\.?\s*", re.IGNORECASE),
    re.compile(r"(?im)^Finalizaci[oó]n de Ejecuci[oó]n Agent V2\s*[—\-:•]?\s*Diagn[oó]stico:?\s*[^\n]*\n+", re.IGNORECASE),
]


def sanitize_user_facing_content(content: Optional[str], classification: Optional[str] = None) -> str:
    """Strip finalizer boilerplate/preamble from user-facing content.

    Conservative: only removes known finalizer scaffolding patterns. Preserves
    actual answer paragraphs, code blocks, safety refusals, and legitimate
    markdown headings that are NOT finalizer section markers.

    Called on final_answer after identity_guard_rewrite, before it reaches the
    chat UI. Never mutates structured metadata (run_id, trace_url, etc.).
    """
    if not content:
        return content or ""
    original = content
    result = content

    for pattern in _FINALIZER_SENTENCE_PREFIXES:
        result = pattern.sub("", result)

    for pattern in _FINALIZER_BOILERPLATE_PATTERNS:
        result = pattern.sub("", result)

    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip()

    if not result and original.strip():
        return original.strip()

    return result


def normalize_agent_v2_chat_response(
    raw: Dict[str, Any],
    *,
    backend: str = "native_runtime",
    mode_requested: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize a raw Agent V2 run dict into the stable /v2/chat/agent contract."""
    if not isinstance(raw, dict):
        raw = {"ok": False, "error": "non-dict response from backend", "detail": str(raw)}

    out = copy.deepcopy(raw)
    out.setdefault("ok", True)
    out.setdefault("canonical_agent_v2", True)
    out.setdefault("route", "/v2/chat/agent")
    out.setdefault("run_id", raw.get("run_id"))
    # Fix A (front-brain-agent-v2-identity-guard-and-intent-floor-widen-02):
    # Active identity guard rewrite. This is the sole chokepoint for ALL response
    # paths (Native, LangGraph, injected, timeout, structured fallback, deterministic
    # finalizer). LLM-stage AGENT_V2_IDENTITY_PREAMBLE is unreliable because Kimi's
    # alignment overrides the system prompt. This post-response guard is
    # deterministic and cannot be overridden by the LLM.
    _raw_final_pre_guard = _extract_final_answer(raw) if raw.get("final_answer") is None else str(raw.get("final_answer") or "")
    _intent_route_for_guard = raw.get("intent_route") or raw.get("classification")
    _rewritten_final, _identity_guard_metadata = _identity_guard_rewrite(_raw_final_pre_guard, _intent_route_for_guard)
    _sanitized_final = sanitize_user_facing_content(_rewritten_final, _intent_route_for_guard)
    out["final_answer"] = _sanitized_final
    out["identity_guard_metadata"] = _identity_guard_metadata
    out["sanitizer_applied"] = _sanitized_final != _rewritten_final

    # Provider metadata must always be a complete dict
    provider_metadata = normalize_provider_metadata(raw.get("provider_metadata"), raw)
    out["provider_metadata"] = provider_metadata

    # Capability metadata must always be a complete dict
    capability_metadata = normalize_capability_metadata(raw.get("capability_metadata"), raw)
    out["capability_metadata"] = capability_metadata

    # Mode fields
    out.setdefault("mode_requested", mode_requested or raw.get("mode_requested") or raw.get("mode") or "read_only")
    out.setdefault("mode_effective", raw.get("mode_effective") or raw.get("mode") or "read_only")
    out.setdefault("mode_escalation_required", bool(raw.get("mode_escalation_required")))
    out.setdefault("approval_required", bool(raw.get("approval_required") or raw.get("mode_escalation_required")))

    # Approval / escalation fields
    out.setdefault("required_permission", raw.get("required_permission"))
    out.setdefault("expected_write_scope", raw.get("expected_write_scope") if raw.get("expected_write_scope") is not None else [])
    out.setdefault("confirmation_id", raw.get("confirmation_id"))

    # Trace and tools
    out.setdefault("trace_url", normalize_trace_url(raw))
    out.setdefault("blocked_tools", normalize_blocked_tools(raw))

    # Intent fields
    intent_route = raw.get("intent_route") or raw.get("classification") or "unknown"
    out.setdefault("intent_route", intent_route)
    out.setdefault("intent_detected", raw.get("intent_detected") or intent_route)
    out.setdefault("intent_confidence", raw.get("intent_confidence") if raw.get("intent_confidence") is not None else 0.0)
    out.setdefault("classification", raw.get("classification") or intent_route)
    out.setdefault("status", raw.get("status") or "completed")

    # Auto decision
    auto = raw.get("auto_decision")
    out.setdefault("auto_decision", auto if auto is not None else "n/a")

    # Backend metadata
    backend_selected = raw.get("backend_selected") or backend
    out.setdefault("backend", backend_selected)
    out.setdefault("backend_selected", backend_selected)
    out.setdefault("backend_default", raw.get("backend_default"))
    out.setdefault("backend_fallback_used", bool(raw.get("backend_fallback_used")))
    out.setdefault("backend_fallback_reason", raw.get("backend_fallback_reason"))
    out.setdefault("runtime_type", raw.get("runtime_type") or backend_selected)
    out.setdefault("langgraph_default_active", bool(raw.get("langgraph_default_active")))
    out.setdefault("rollback_backend", raw.get("rollback_backend") or "native_runtime")

    # Tool distinction fields
    out.setdefault("tools_considered", raw.get("tools_considered") if raw.get("tools_considered") is not None else [])
    out.setdefault("tools_executed", raw.get("tools_executed") if raw.get("tools_executed") is not None else [])
    out.setdefault("tools_blocked", raw.get("tools_blocked") if raw.get("tools_blocked") is not None else [])
    out.setdefault("evidence_sources", raw.get("evidence_sources") if raw.get("evidence_sources") is not None else [])
    out.setdefault("tool_results", raw.get("tool_results") if raw.get("tool_results") is not None else [])

    # Governance/intent enrichment fields
    out.setdefault("governance_decision", raw.get("governance_decision") if raw.get("governance_decision") is not None else "allow")
    out.setdefault("governance_required_permission", raw.get("governance_required_permission"))
    out.setdefault("governance_blocked_reason", raw.get("governance_blocked_reason"))
    out.setdefault("intent_language", raw.get("intent_language") if raw.get("intent_language") is not None else "unknown")
    out.setdefault("intent_risk_level", raw.get("intent_risk_level") if raw.get("intent_risk_level") is not None else "safe")
    out.setdefault("intent_requires_approval", bool(raw.get("intent_requires_approval")))
    out.setdefault("intent_blocked_reason", raw.get("intent_blocked_reason"))
    out.setdefault("route_raw", raw.get("route_raw"))

    # Error / detail (08e contract requires these keys to be present and string-typed)
    out.setdefault("error", raw.get("error") if raw.get("error") is not None else "")
    out.setdefault("detail", raw.get("detail") if raw.get("detail") is not None else "")

    return out
