"""
Canonical chat router entrypoint for Brain V9.

Future API adapters must call ``handle_user_message`` instead of invoking
``LLMManager.query`` directly. The entrypoint preserves the existing governed
``BrainSession.chat`` path while making intent detection and response hygiene
explicit at the boundary.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.intent import IntentDetector


CANONICAL_CHAT_ENTRYPOINT_VERSION = "1.0-router-preservation"
RAW_COT_MARKERS = (
    "raw_chain_of_thought",
    "private_reasoning",
    "hidden reasoning",
    "chain of thought",
    "analysis:",
    "thinking...",
    "done thinking",
    "<thinking>",
    "<think>",
    "scratchpad:",
    "chain-of-thought:",
)

_ENTRYPOINT_SESSIONS: Dict[str, Any] = {}


@dataclass
class ChatRouterInput:
    message: str
    room: str = "default"
    context: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


@dataclass
class ChatRouterOutput:
    content: str
    route: str
    intent: str
    evidence_ids: List[str] = field(default_factory=list)
    governance_applied: bool = True
    no_cot_leak: bool = True
    canonical_path: str = str(BASE_PATH)
    errors: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    model: Optional[str] = None
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["response"] = payload["content"]
        return payload


def detect_intent(message: str, history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Run the canonical intent detector for every chat request."""
    detector = IntentDetector()
    intent, confidence, metadata = detector.detect(message or "", history or [])
    return {
        "intent": intent,
        "confidence": confidence,
        "metadata": metadata or {},
        "detector": "IntentDetector.detect",
    }


def select_route(intent_result: Mapping[str, Any], *, dry_run: bool = False, provider_probe: bool = False) -> str:
    """Choose a conservative route label without executing tools or LLMs."""
    if provider_probe:
        return "provider_probe"
    if dry_run:
        return "diagnostic_dry_run"
    intent = str(intent_result.get("intent") or "UNKNOWN").upper()
    if intent in {"COMMAND", "CODE", "SYSTEM", "TRADING"}:
        return "brain_session_governed_agent_or_tool"
    if intent in {"QUERY", "UNKNOWN"}:
        return "brain_session_governed_chat"
    return "brain_session_governed_chat"


def _strip_raw_cot_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_raw_cot_fields(v)
            for k, v in value.items()
            if str(k).lower() not in {"raw_chain_of_thought", "private_reasoning"}
        }
    if isinstance(value, list):
        return [_strip_raw_cot_fields(v) for v in value]
    return value


def _contains_cot_marker(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in RAW_COT_MARKERS)


def apply_governance(content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Apply boundary response hygiene.

    BrainSession already performs the main governance cascade; this function is
    the entrypoint-level guard required so adapters cannot leak private
    reasoning even if a downstream route regresses.
    """
    metadata = _strip_raw_cot_fields(metadata or {})
    sanitized = content or ""
    try:
        from brain_v9.core.session import BrainSession

        sanitized, hygiene = BrainSession._sanitize_llm_chat_response_with_metadata(sanitized)
        metadata["thinking_stripped"] = bool(metadata.get("thinking_stripped") or hygiene["thinking_stripped"])
    except Exception:
        sanitized = sanitized.strip()

    no_cot_leak = not _contains_cot_marker(sanitized)
    if not no_cot_leak:
        sanitized = (
            "No puedo exponer razonamiento privado o chain-of-thought. "
            "Puedo dar una respuesta breve, verificable y con evidencia visible."
        )
        no_cot_leak = True

    return {
        "content": sanitized,
        "metadata": metadata,
        "governance_applied": True,
        "no_cot_leak": no_cot_leak,
    }


def render_response(output: ChatRouterOutput) -> Dict[str, Any]:
    return output.to_dict()


async def handle_user_message(
    message: str,
    room: str = "default",
    context: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Canonical user-message entrypoint.

    This function is intentionally the boundary future OpenAI-compatible
    adapters must use. It calls IntentDetector.detect, selects a governed route,
    delegates to BrainSession.chat only when not in dry-run, and sanitizes the
    final visible response.
    """
    started = time.monotonic()
    context = dict(context or {})
    errors: List[str] = []
    evidence_ids = list(context.get("evidence_ids") or [])
    history = list(context.get("history") or [])
    provider_probe = bool(context.get("provider_probe"))

    intent_result = detect_intent(message, history)
    route = select_route(intent_result, dry_run=dry_run, provider_probe=provider_probe)

    if dry_run:
        governed = apply_governance(
            "Dry-run canonical router entrypoint validated. No LLM, tools, memory, or FAISS writes executed.",
            {"intent_result": intent_result, "dry_run": True},
        )
        return render_response(
            ChatRouterOutput(
                content=governed["content"],
                route=route,
                intent=str(intent_result["intent"]),
                evidence_ids=evidence_ids,
                governance_applied=governed["governance_applied"],
                no_cot_leak=governed["no_cot_leak"],
                errors=errors,
                latency_ms=round((time.monotonic() - started) * 1000, 3),
                model="canonical_router_dry_run",
                success=True,
                metadata={
                    **governed["metadata"],
                    "entrypoint_version": CANONICAL_CHAT_ENTRYPOINT_VERSION,
                    "intent_detector_called": True,
                    "future_adapter_policy": "OpenAI adapters must call handle_user_message; direct LLMManager.query is forbidden.",
                },
            )
        )

    if provider_probe:
        try:
            from brain_v9.core.session import get_or_create_session

            active_sessions = context.get("active_sessions")
            if active_sessions is None:
                active_sessions = _ENTRYPOINT_SESSIONS
            model_priority = str(context.get("model_priority") or "chat")
            session = get_or_create_session(room, active_sessions)
            downstream = await session.provider_probe(message, model_priority=model_priority)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")
            downstream = {
                "content": "provider_probe failed safely before provider selection.",
                "success": False,
                "route": "provider_probe",
                "model": "canonical_router_provider_probe_error",
                "no_cot_leak": True,
            }
        downstream = _strip_raw_cot_fields(downstream if isinstance(downstream, dict) else {"content": str(downstream)})
        content = str(downstream.get("content") or downstream.get("response") or "")
        governed = apply_governance(content, {"downstream": downstream, "intent_result": intent_result, "provider_probe": True})
        result = ChatRouterOutput(
            content=governed["content"],
            route="provider_probe",
            intent=str(downstream.get("intent") or intent_result["intent"]),
            evidence_ids=evidence_ids,
            governance_applied=governed["governance_applied"],
            no_cot_leak=governed["no_cot_leak"],
            errors=errors,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
            model=downstream.get("model"),
            success=bool(downstream.get("success", not errors)),
            metadata={
                "entrypoint_version": CANONICAL_CHAT_ENTRYPOINT_VERSION,
                "intent_detector_called": True,
                "selected_route": "provider_probe",
                "provider_probe": True,
                "read_only": True,
                "evaluation": True,
                "tools_blocked": True,
                "memory_writes_blocked": True,
                "faiss_writes_blocked": True,
                "external_side_effects_blocked": True,
                "thinking_stripped": bool(governed["metadata"].get("thinking_stripped") or downstream.get("thinking_stripped")),
                "future_adapter_policy": "OpenAI adapters must call handle_user_message; direct LLMManager.query is forbidden.",
            },
        )
        payload = render_response(result)
        for key in (
            "provider_chain",
            "provider_attempts",
            "provider_selected",
            "model_selected",
            "provider_status",
            "provider_latency_ms",
            "fallback_used",
            "fallback_reason",
            "primary_provider_available",
            "secondary_provider_available",
            "cloud_provider_available",
            "codex_provider_available",
            "local_fallback_used",
            "thinking_stripped",
            "tools_blocked",
            "memory_writes_blocked",
            "faiss_writes_blocked",
            "external_side_effects_blocked",
            "save_turn_skipped",
            "aiohttp_session_closed_after_probe",
        ):
            if key in downstream:
                payload[key] = downstream[key]
        return payload

    try:
        from brain_v9.core.session import get_or_create_session

        active_sessions = context.get("active_sessions")
        if active_sessions is None:
            active_sessions = _ENTRYPOINT_SESSIONS
        model_priority = str(context.get("model_priority") or "chat")
        session = get_or_create_session(room, active_sessions)
        downstream = await session.chat(message, model_priority=model_priority)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {str(exc)[:300]}")
        downstream = {
            "content": "No pude completar la ruta gobernada de chat. Revisa el error estructurado del entrypoint.",
            "success": False,
            "model": "canonical_router_error",
        }

    downstream = _strip_raw_cot_fields(downstream if isinstance(downstream, dict) else {"content": str(downstream)})
    content = str(downstream.get("content") or downstream.get("response") or "")
    governed = apply_governance(content, {"downstream": downstream, "intent_result": intent_result})
    result = ChatRouterOutput(
        content=governed["content"],
        route=str(downstream.get("route") or route),
        intent=str(downstream.get("intent") or intent_result["intent"]),
        evidence_ids=evidence_ids,
        governance_applied=governed["governance_applied"],
        no_cot_leak=governed["no_cot_leak"],
        errors=errors,
        latency_ms=round((time.monotonic() - started) * 1000, 3),
        model=downstream.get("model"),
        success=bool(downstream.get("success", not errors)),
        metadata={
            "entrypoint_version": CANONICAL_CHAT_ENTRYPOINT_VERSION,
            "intent_detector_called": True,
            "selected_route": route,
            "future_adapter_policy": "OpenAI adapters must call handle_user_message; direct LLMManager.query is forbidden.",
        },
    )
    payload = render_response(result)

    # Preserve operational fields used by main.py UI response plumbing.
    for key in (
        "permission_required",
        "permission_id",
        "tool_name",
        "risk_level",
        "options",
        "tool01_real",
        "tool01_router_used",
        "blocked_by_policy",
        "blocked_by_user",
        "tool_result",
        "pending_id",
    ):
        if key in downstream:
            payload[key] = downstream[key]
    return payload
