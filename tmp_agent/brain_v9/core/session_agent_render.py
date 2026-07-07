"""Agent output rendering helpers extracted from BrainSession (B7-STRANGLER-11).

Design rules (do not break):
- No I/O, no network, no globals/state.
- Does NOT import brain_v9.core.session (avoids circular import).
- Dependencies on BrainSession symbols are injected as callables.
"""
from __future__ import annotations

from typing import Dict, List, Optional

__all__ = [
    "render_agent_failure_reply",
    "summarize_action_output",
    "render_operational_agent_summary",
    "is_agent_execution_failure",
]


def render_agent_failure_reply(
    status: str,
    raw_text: str = "",
    *,
    sanitize_user_visible_response_func,
    contains_raw_tool_markup_func,
    looks_like_canned_failure_func,
) -> str:
    """Return a human-readable failure reply for the given agent status."""
    status_map = {
        "ghost_completion": (
            "No pude completar esta peticion con herramientas en este turno. "
            "El agente no llego a ejecutar ninguna herramienta."
        ),
        "max_steps_reached": (
            "Agente agoto pasos sin cerrar la tarea. "
            "Suele ocurrir cuando el modelo LLM no responde. "
            "Verifica que Ollama este activo (ollama serve) o reformula en partes concretas."
        ),
        "llm_pool_unavailable": (
            "LLM pool no disponible: todos los modelos del chain estan con circuit breaker abierto. "
            "Inicia Ollama (ollama serve) para restaurar modelos locales."
        ),
        "retry_exhausted": (
            "No pude completar esta peticion con herramientas en este turno. "
            "El agente agoto sus reintentos antes de cerrarla."
        ),
        "timeout": (
            "No pude completar esta peticion con herramientas en este turno. "
            "La ejecucion del agente expiro por tiempo."
        ),
    }
    prefix = status_map.get(
        status,
        "No pude completar esta peticion con herramientas en este turno.",
    )
    cleaned = sanitize_user_visible_response_func(raw_text or "")
    if cleaned and not contains_raw_tool_markup_func(cleaned) and not looks_like_canned_failure_func(cleaned):
        return f"{cleaned}\n\n{prefix}"
    return (
        f"{prefix} Reformula la peticion o pideme que verifique una fuente, archivo "
        f"o servicio concreto."
    )


def summarize_action_output(
    action: Dict,
    *,
    format_tool_result_func,
) -> str:
    """Format a single agent action for display."""
    tool = action.get("tool", "tool")
    ok = action.get("success", False)
    out = action.get("output")
    err = action.get("error")
    return format_tool_result_func(tool, ok, out, err)


def render_operational_agent_summary(
    message: str,
    actions: List[Dict],
    *,
    steps: int,
    status: str,
    summarize_action_output_func,
    format_tool_result_func=None,
    format_action_value_func=None,
) -> str:
    """Render agent results as a clean, conversational response.

    P-OP59: No debug metadata, no task echo, no action counts.
    Just the information the user asked for, clearly formatted.

    R7.1: Structured extractive fallback. Groups actions by tool,
    counts success/failure, applies known formatters per tool, and
    keeps the rendered output bounded so the user never sees a
    raw source-code dump even when LLM synthesis collapses.
    """
    if not actions:
        return (
            "*[Resumen extractivo — sintesis LLM no disponible]*\n"
            "No se ejecutaron herramientas. Reformula la pregunta o "
            "intenta de nuevo en unos segundos."
        )

    successful = [a for a in actions if a.get("success")]
    failed = [a for a in actions if not a.get("success")]

    # Group successful actions by tool name for compact rendering
    by_tool: Dict[str, List[Dict]] = {}
    for a in successful:
        by_tool.setdefault(a.get("tool", "tool"), []).append(a)

    # R7.1: Header with high-signal counts (replaces R6.2 banner)
    header = (
        f"*[Resumen extractivo — sintesis LLM no disponible]* "
        f"({len(successful)} ok, {len(failed)} fallos, {steps} pasos)"
    )
    lines = [header]

    # One block per tool, one rendered output per tool (the first/best)
    # to avoid repetition. Cap total tools shown at 6.
    for tool_name, tool_actions in list(by_tool.items())[:6]:
        count = len(tool_actions)
        tag = f"{tool_name} (x{count})" if count > 1 else tool_name
        # Use the formatter on the first successful action of the group
        rendered = summarize_action_output_func(tool_actions[0])
        # Defensive cap: never let a single tool block exceed 400 chars
        if len(rendered) > 400:
            rendered = rendered[:380] + " [...truncado]"
        lines.append(f"- {tag}: {rendered}")

    if len(by_tool) > 6:
        lines.append(f"- (+{len(by_tool) - 6} herramientas adicionales)")

    # Failures grouped by tool with their error reason (truncated)
    if failed:
        fail_groups: Dict[str, str] = {}
        for a in failed:
            t = a.get("tool", "?")
            err = str(a.get("error") or "sin detalle")[:120]
            fail_groups.setdefault(t, err)
        fail_summary = "; ".join(
            f"{t} ({err})" for t, err in list(fail_groups.items())[:5]
        )
        lines.append(f"\nFallos: {fail_summary}")

    # Footer: status + suggested next action
    if status == "timeout":
        lines.append("*(resultados parciales — timeout del agente)*")
    elif status not in ("success", "completed", "ok"):
        lines.append(f"*(estado: {status})*")

    # R7.1: Suggest a retry path so the user has agency
    lines.append(
        "\n_Sugerencia: si necesitas un analisis sintetizado, reintenta "
        "en unos segundos o reformula mas corto (los modelos LLM no "
        "respondieron a tiempo)."
    )

    return "\n".join(lines)


# Status values that indicate the agent failed to execute tools properly.
_AGENT_FAILURE_STATUSES = frozenset({
    "ghost_completion",
    "max_steps_reached",
    "llm_pool_unavailable",
    "retry_exhausted",
    "timeout",
})


def is_agent_execution_failure(agent_result: Dict) -> bool:
    """Return True if the agent result indicates a tool execution failure.

    Pure function extracted from BrainSession._is_agent_execution_failure.
    A failure is when success is False/absent AND the status matches one of
    the known agent failure modes.
    """
    if not isinstance(agent_result, dict):
        return False
    status = str(agent_result.get("status") or "").lower()
    success = bool(agent_result.get("success", True))
    return (not success) and status in _AGENT_FAILURE_STATUSES
