"""Response normalization adapter for Agent V2 chat responses.

Guarantees that /v2/chat/agent returns a stable schema regardless of backend
(Native or LangGraph parity). The normalizer fills missing optional fields
with safe defaults and preserves fields already consumed by frontend/dashboard.
It never mutates the input dict.
"""
from __future__ import annotations

import copy
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
        "evidence_routed": bool(src.get("evidence_routed")) if "evidence_routed" in src else bool(raw.get("evidence_sources")),
        "evidence_sources_count": src.get("evidence_sources_count") if "evidence_sources_count" in src else len(raw.get("evidence_sources") or []),
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
    out.setdefault("final_answer", _extract_final_answer(raw))

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

    # Error / detail
    out.setdefault("error", raw.get("error"))
    out.setdefault("detail", raw.get("detail"))

    return out
