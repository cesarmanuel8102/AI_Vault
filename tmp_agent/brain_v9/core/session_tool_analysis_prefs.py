"""B7-STRANGLER-09: Tool-analysis preference predicates.

Pure, side-effect-free helpers extracted from
``brain_v9.core.session.BrainSession`` to keep ``session.py`` lean.

Two predicates participate in agent-vs-LLM routing:

* :func:`prefers_no_tool_analysis` — detects explicit user preference for a
  pure analysis/chat reply without invoking tools (e.g. ``"no uses tools"``,
  ``"sin herramientas"``, ``"solo analiza"``).
* :func:`has_explicit_tool_target` — detects when the user names a concrete
  file/service/command target (path, port, IP, run/execute verb, ``log``,
  ``archivo``, ``ollama``...). When this is true, the agent route is kept
  even if :func:`prefers_no_tool_analysis` also matches.

Both functions preserve the exact semantics of the original
``BrainSession._prefers_no_tool_analysis`` / ``BrainSession._has_explicit_tool_target``
``@staticmethod`` implementations. ``BrainSession`` keeps two ``@staticmethod``
shim methods that delegate here, so external callers (including
``tests/unit/test_brain_chat_hygiene.py`` which exercises both class- and
instance-level access) continue to work without modification.

Notes
-----
* This module is pure: no I/O, no logging, no global state, no dependency on
  ``BrainSession`` or ``brain_v9.core.session``.
* The shared ``_CODE_ANALYSIS_PATH_RE`` regex is imported from
  ``brain_v9.core.session_routing_constants`` (B7-STRANGLER-04) — the single
  source of truth.
* ``brain_v9.core.routing.guards`` exports parallel ``prefers_no_tool_analysis``
  / ``has_explicit_tool_target`` helpers. Consolidating those duplicates is
  intentionally **out of scope** for B7-09 (would touch routing core).
"""

from __future__ import annotations

import re

from brain_v9.core.session_routing_constants import _CODE_ANALYSIS_PATH_RE

__all__ = [
    "prefers_no_tool_analysis",
    "has_explicit_tool_target",
]


def prefers_no_tool_analysis(message: str) -> bool:
    """Detect explicit user preference for pure analysis/chat without tools."""
    msg = (message or "").lower()
    return any(
        marker in msg
        for marker in (
            "no uses tools",
            "no use tools",
            "no herramientas",
            "sin herramientas",
            "sin tools",
            "no ejecutes herramientas",
            "no ejecutar herramientas",
            "no modifiques",
            "no modificar",
            "no cambies",
            "no cambiar",
            "no edites",
            "no editar",
            "no toques",
            "sin cambios",
            "sin modificar",
            "no hagas cambios",
            "solo analiza",
            "solo analizar",
            "solo razona",
            "solo explica",
        )
    )


def has_explicit_tool_target(message: str) -> bool:
    """Keep agent routing when the user names a concrete file/service/command target."""
    msg = (message or "").lower()
    return bool(
        _CODE_ANALYSIS_PATH_RE.search(message or "")
        or re.search(r"\b(?:[a-z]:[\\/]|/[\w.-]+/)", message or "", re.IGNORECASE)
        or re.search(r"\b(?:puerto|port)\s*\d{2,5}\b", msg)
        or re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b", msg)
        or re.search(r"\b(?:ejecuta|ejecutar|corre|run|execute)\s+[\w./:-]+", msg)
        or any(
            token in msg
            for token in (
                "servicio brain", "servicios brain", "ollama", "dashboard",
                "log", "logs", "archivo", "carpeta", "directorio",
                "file", "folder", "directory",
            )
        )
    )
