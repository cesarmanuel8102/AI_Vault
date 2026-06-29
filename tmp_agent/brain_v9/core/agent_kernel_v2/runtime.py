"""Runtime selector guard for Agent V2 backends.

Keeps NativeAgentRuntimeV2 as the default. Only selects LangGraphParityRuntimeV2
when the AGENT_V2_BACKEND environment variable explicitly requests it and the
LangGraph package is available and initializes successfully.

Invalid values, missing packages, or init failures all fall back to Native.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .native_runtime import NativeAgentRuntimeV2

logger = logging.getLogger(__name__)


NATIVE_BACKEND_VALUES = {"", "native", "native_runtime"}
LANGGRAPH_BACKEND_VALUES = {"langgraph", "langgraph_parity", "langgraph_parity_runtime"}


def resolve_agent_v2_backend_choice(raw_value: Optional[str]) -> str:
    """Resolve raw env value into the canonical backend choice."""
    if raw_value is None:
        return "native_runtime"
    normalized = str(raw_value).strip().lower()
    if normalized in NATIVE_BACKEND_VALUES:
        return "native_runtime"
    if normalized in LANGGRAPH_BACKEND_VALUES:
        return "langgraph_parity"
    # Unknown values are treated as native (safe fallback)
    return "native_runtime"


def is_langgraph_backend_requested(raw_value: Optional[str]) -> bool:
    """Return True iff the raw env value requests a LangGraph backend."""
    if raw_value is None:
        return False
    return str(raw_value).strip().lower() in LANGGRAPH_BACKEND_VALUES


def is_any_non_native_backend_requested(raw_value: Optional[str]) -> bool:
    """Return True for any non-empty, non-native value (including invalid)."""
    if raw_value is None:
        return False
    normalized = str(raw_value).strip().lower()
    return normalized != "" and normalized not in NATIVE_BACKEND_VALUES


def _build_native_runtime_with_metadata(
    fallback_used: bool = False,
    fallback_reason: Optional[str] = None,
) -> NativeAgentRuntimeV2:
    """Create a Native runtime and attach backend metadata safely."""
    rt = NativeAgentRuntimeV2()
    rt.backend_selected = "native_runtime"
    rt.backend_fallback_used = fallback_used
    rt.backend_fallback_reason = fallback_reason
    # Expose backend metadata on the class so all instances report consistently.
    if not hasattr(NativeAgentRuntimeV2, "backend_selected"):
        NativeAgentRuntimeV2.backend_selected = rt.backend_selected
    if not hasattr(NativeAgentRuntimeV2, "backend_fallback_used"):
        NativeAgentRuntimeV2.backend_fallback_used = rt.backend_fallback_used
    if not hasattr(NativeAgentRuntimeV2, "backend_fallback_reason"):
        NativeAgentRuntimeV2.backend_fallback_reason = rt.backend_fallback_reason
    return rt


def _try_build_langgraph_runtime(
    requested_value: Optional[str],
) -> Optional[Any]:
    """Attempt to build LangGraphParityRuntimeV2; return None on failure."""
    try:
        from .langgraph_parity_runtime import LangGraphParityRuntimeV2
        rt = LangGraphParityRuntimeV2()
        if not rt.graph_available:
            logger.warning(
                "AGENT_V2_BACKEND=%r requested but LangGraph graph not available: %s",
                requested_value,
                rt.graph_error,
            )
            return None
        rt.backend_selected = "langgraph_parity"
        rt.backend_fallback_used = False
        rt.backend_fallback_reason = None
        return rt
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.warning(
            "AGENT_V2_BACKEND=%r requested but LangGraph import/init failed: %s",
            requested_value,
            exc,
        )
        return None


def get_agent_runtime_backend_name() -> str:
    """Return the currently selected backend name without instantiating runtime."""
    return resolve_agent_v2_backend_choice(os.environ.get("AGENT_V2_BACKEND"))


def get_agent_runtime_v2():
    """Return the Agent V2 runtime selected by AGENT_V2_BACKEND env var.

    Defaults to NativeAgentRuntimeV2. Falls back to Native on invalid values,
    missing packages, or init failures.
    """
    raw_value = os.environ.get("AGENT_V2_BACKEND")
    if not is_any_non_native_backend_requested(raw_value):
        return _build_native_runtime_with_metadata()

    if not is_langgraph_backend_requested(raw_value):
        # A non-native, non-LangGraph value was provided -> invalid -> safe native fallback
        return _build_native_runtime_with_metadata(
            fallback_used=True,
            fallback_reason=f"AGENT_V2_BACKEND={raw_value!r} is not a recognized backend; falling back to native_runtime",
        )

    lang_rt = _try_build_langgraph_runtime(raw_value)
    if lang_rt is not None:
        return lang_rt

    # Safe fallback to native with metadata explaining why
    return _build_native_runtime_with_metadata(
        fallback_used=True,
        fallback_reason=f"AGENT_V2_BACKEND={raw_value!r} requested but LangGraph is unavailable or failed to initialize; falling back to native_runtime",
    )
