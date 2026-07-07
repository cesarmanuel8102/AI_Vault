"""Pure query/intent predicates extracted from BrainSession (B7-STRANGLER-03).

This module hosts side-effect-free predicate functions that classify user
messages by intent (greeting, dashboard, deep analysis, code change request,
temporal references, ...). They are re-exported as bound shim methods on
BrainSession in brain_v9.core.session so existing call sites keep working.

Design rules (do not break):
- No I/O, no network, no globals/state.
- Does NOT import brain_v9.core.session (avoids circular import).
- Does NOT reference BrainSession.
- Does NOT use ``self`` or ``cls``.
- Only depends on the standard library ``re`` module and module-private
  pre-compiled patterns mirrored from session.py.

The patterns ``_CODE_ANALYSIS_PATH_RE``, ``_CONFIRM_PATTERNS``,
``_TEMPORAL_QUERY_RE`` and ``_RECENT_ACTIVITY_PATTERNS`` are intentionally
duplicated from session.py to avoid a circular import. Keep them
byte-equivalent to their counterparts in session.py.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Pre-compiled patterns (mirrored from brain_v9.core.session, intentional copy
# to avoid circular imports). Keep byte-equivalent.
# ---------------------------------------------------------------------------

_CODE_ANALYSIS_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/][^\\/:*?\"<>|\r\n]+(?:[\\/][^\\/:*?\"<>|\r\n]+)*|"
    r"(?:tmp_agent|brain|core|tests)[\\/][^\s\"']+\.(?:py|json|md|txt|ps1|yaml|yml)))",
    re.IGNORECASE,
)

_CONFIRM_PATTERNS = re.compile(
    r"^(?:s[ií]|ok|dale|yes|ya|aprueba|aprobar|confirma|confirmo|"
    r"adelante|hazlo|ejecuta|proceed|approve|do it|go ahead)"
    r"[\s.!,;:…]*$",
    re.IGNORECASE,
)
_TEMPORAL_QUERY_RE = re.compile(
    r"\b(hoy|ayer|mañana|latest|ultimo|último|ultimos|últimos|ultima|última|actual|actualmente|now|today|live|running|estado|status|reciente|recientes|recent|esta semana|this week|mejoras?|cambios?|modificaciones?|recientemente|nuevo|nueva|nuevos|nuevas)\b",
    re.IGNORECASE,
)
_RECENT_ACTIVITY_PATTERNS = (
    "has estado mejorando", "has estado mejorandote", "te has mejorado",
    "que has hecho ultimamente", "qué has hecho últimamente",
    "que has hecho recientemente", "qué has hecho recientemente",
    "que estuviste haciendo", "qué estuviste haciendo",
    "en que has estado trabajando", "en qué has estado trabajando",
    "cuanto has estado trabajando", "cuánto has estado trabajando",
    "que mejoras has hecho", "qué mejoras has hecho",
    "tu progreso reciente", "tu actividad reciente",
    "ultima actividad", "última actividad",
    "que aprendiste", "qué aprendiste",
    "que sprints", "qué sprints", "ultimos sprints", "últimos sprints",
    "que tools fallaron", "qué tools fallaron", "tool failures recientes",
    "resumen de tu trabajo", "que decisiones tomaste", "qué decisiones tomaste",
    "actividad de las ultimas", "actividad de las últimas",
)

__all__ = [
    "looks_like_canned_failure",
    "is_benign_security_audit_query",
    "is_confirmation",
    "is_code_change_request",
    "is_tool_confirmation_request_response",
    "is_dashboard_query",
    "is_greeting_query",
    "is_capabilities_query",
    "is_llm_status_query",
    "is_codex_role_query",
    "is_codex_comparison_query",
    "is_recent_activity_query",
    "is_chat_interaction_review_query",
    "is_brain_diagnostic_analysis_query",
    "is_grounded_code_analysis_query",
    "is_chat_ui_background_change_query",
    "is_chat_ui_background_restore_query",
    "is_chat_send_button_move_query",
    "is_brain_status_query",
    "is_deep_brain_analysis_query",
    "looks_like_deep_analysis",
    "is_deep_risk_analysis_query",
    "is_deep_edge_analysis_query",
    "is_deep_strategy_analysis_query",
    "is_deep_pipeline_analysis_query",
    "is_self_build_query",
    "is_self_build_resolution_query",
    "is_consciousness_query",
    "is_abstract_reasoning_query",
    "is_operational_agent_query",
    "is_temporal_query",
    "contains_raw_tool_markup",
    "is_manual_confirmation_step",
    "is_continue_sequence_message",
]

# ---------------------------------------------------------------------------
# Predicate functions (pure)
# ---------------------------------------------------------------------------

def looks_like_canned_failure(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    return any(
        marker in lowered
        for marker in (
            "el agente no ejecutó ninguna herramienta",
            "no obtuve resultados para esta consulta",
            "*[resumen extractivo",
            "(sin respuesta)",
        )
    )

def is_benign_security_audit_query(message: str) -> bool:
    msg_l = (message or "").lower()
    security_markers = ("seguridad", "security", "auditoria", "auditoría", "audit", "exposicion", "exposición")
    benign_markers = ("sin explotar", "benigna", "benigno", "harmless", "no explotar", "superficies")
    scope_markers = ("brain", "local", "sistema", "chat", "agente")
    harmful_markers = ("hackea", "hackear", "bypass", "payload", "intrusion", "intrusión")
    return (
        any(token in msg_l for token in security_markers)
        and any(token in msg_l for token in benign_markers)
        and any(token in msg_l for token in scope_markers)
        and not any(token in msg_l for token in harmful_markers)
    )

def is_confirmation(msg: str) -> bool:
    """Return True if the message is a short confirmation phrase."""
    # Only match short messages (avoid false positives on long paragraphs)
    if len(msg) > 40:
        return False
    stripped = msg.strip()
    if _CONFIRM_PATTERNS.match(stripped):
        return True
    tokens = [t for t in re.split(r"[\s,;:.!¡¿?\-_/]+", stripped.lower()) if t]
    allowed = {
        "si", "sí", "ok", "dale", "yes", "ya", "aprueba", "aprobar",
        "confirma", "confirmo", "confirmado", "adelante", "hazlo",
        "ejecuta", "proceed", "approve", "do", "it", "go", "ahead",
    }
    return bool(tokens) and all(token in allowed for token in tokens)

def is_code_change_request(message: str) -> bool:
    msg = (message or "").lower()
    action_markers = (
        "modifica", "modificar", "cambia", "cambiar", "edita", "editar",
        "arregla", "fix", "refactor", "crea", "crear", "implementa",
        "implement", "ajusta", "ajusta", "patch", "reemplaza",
    )
    scope_markers = (
        ".py", ".json", "ui", "frontend", "chat", "dashboard", "index.html",
        "background", "fondo", "color", "css", "html", "javascript",
        "archivo", "archivos", "brain", "session.py", "llm.py",
    )
    return any(a in msg for a in action_markers) and any(s in msg for s in scope_markers)

def is_tool_confirmation_request_response(response: str) -> bool:
    """Detect chat-only replies that asked the user to confirm tool execution."""
    text = (response or "").lower()
    return (
        "confirma si quieres que" in text
        and (
            "endpoint de agente" in text
            or "herramientas" in text
            or "tools" in text
        )
    )

def is_dashboard_query(message: str) -> bool:
    msg_l = (message or "").lower()
    if not (re.search(r"\bdashboard\b", msg_l) or "interfaz" in msg_l or "/ui" in msg_l or "/dashboard" in msg_l):
        return False
    # PHASE R3.1: do NOT take fastpath if the user is asking about CONTENT
    # of a tab / panel / section — that requires fetching the HTML, not just
    # confirming infrastructure availability.
    deep_kw = (
        "pesta", "tab", "muestra", "muestre", "contenido", "que hay", "qué hay",
        "que dice", "qué dice", "explica", "describe", "describir",
        "detalle", "detalles", "panel", "seccion", "sección", "componente",
        "elemento", "widget", "grafico", "gráfico", "metric",
    )
    return not any(k in msg_l for k in deep_kw)

def is_greeting_query(message: str) -> bool:
    normalized = re.sub(r"[!?.,;:]+", " ", message).strip()
    return normalized in {
        "hola", "hello", "hi", "hey", "buenas", "buenos dias",
        "buen día", "buen dia", "buenas tardes", "buenas noches",
        "gracias", "thanks", "ok", "okay", "vale",
    }

def is_capabilities_query(message: str) -> bool:
    normalized = re.sub(r"\s+", " ", re.sub(r"[!?.,;:]+", " ", message)).strip()
    return normalized in {
        "que puedes hacer", "qué puedes hacer", "que haces", "qué haces",
        "what can you do", "what do you do", "help me",
    }

def is_llm_status_query(message: str) -> bool:
    msg = (message or "").lower()
    if not any(token in msg for token in ("llm", "modelo", "model", "chain", "cadena", "motor")):
        return False
    return any(
        phrase in msg for phrase in (
            "que llm", "qué llm", "que modelo", "qué modelo",
            "modelo principal", "llm principal", "model principal",
            "estas usando", "estás usando", "usas como principal",
            "usa como principal", "using as primary", "current model",
            "modelo estas usando", "modelo estás usando",
        )
    )

def is_codex_role_query(message: str) -> bool:
    msg = (message or "").lower()
    if "codex" not in msg:
        return False
    if any(token in msg for token in ("evalua", "evalúa", "analiza", "analisis", "análisis", "compara", "comparativa", "tecnicamente", "técnicamente")):
        return False
    return any(
        phrase in msg for phrase in (
            "principal", "chat general", "que carril", "qué carril",
            "por que", "por qué", "porqué", "significa",
            "participa", "activo", "activa", "usa hoy", "role", "rol",
        )
    )

def is_codex_comparison_query(message: str) -> bool:
    msg = (message or "").lower()
    if "codex" not in msg:
        return False
    if "code" not in msg and "chat general" not in msg:
        return False
    return any(token in msg for token in (
        "diferencia", "compara", "comparativa", "evalua", "evalúa",
        "analiza", "analisis", "análisis", "tecnicamente", "técnicamente",
    ))

def is_recent_activity_query(message: str) -> bool:
    msg_l = (message or "").lower()
    return any(pat in msg_l for pat in _RECENT_ACTIVITY_PATTERNS)

def is_chat_interaction_review_query(message: str) -> bool:
    msg = (message or "").lower()
    return (
        ("interacciones" in msg or "respuestas" in msg or "chat-brain" in msg or "chat brain" in msg)
        and any(token in msg for token in ("mala", "malas", "fallando", "que esta fallando", "qué está fallando", "revisa", "evalua", "evalúa"))
    )

def is_brain_diagnostic_analysis_query(message: str) -> bool:
    msg = (message or "").lower()
    scope_markers = (
        "brain", "chat-brain", "chat brain", "agente", "agent", "llm",
        "codex", "ruta", "routing", "fallback", "timeout", "latencia",
        "resumen extractivo", "ghost_completion", "interacciones", "respuestas",
    )
    analysis_markers = (
        "explica", "por que", "por qué", "porque", "why", "causa",
        "coherente", "evalua", "evalúa", "analiza", "analisis", "análisis",
        "que significa", "qué significa", "que esta fallando", "qué está fallando",
        "diagnostica", "diagnóstico", "revisa", "valora",
    )
    return any(marker in msg for marker in scope_markers) and any(
        marker in msg for marker in analysis_markers
    )

def is_grounded_code_analysis_query(message: str) -> bool:
    msg = (message or "").lower()
    if not _CODE_ANALYSIS_PATH_RE.search(message or ""):
        return False
    analysis_words = (
        "resume", "resumen", "explica", "explicar", "dime", "como se", "cómo se",
        "condicion", "condición", "corrigio", "corrigió", "prueba", "test",
        "fallback", "timeout", "analiza", "analisis", "análisis", "revisa", "inspecciona", "lee",
    )
    return any(word in msg for word in analysis_words)

def is_chat_ui_background_change_query(message: str) -> bool:
    msg = (message or "").lower()
    change_verbs = ("modifica", "cambia", "ajusta", "editar", "edita")
    restore_verbs = ("vuelve", "volver", "restablece", "restablecer", "retorna", "retornar", "deja", "dejar")
    target_tokens = ("chat", "ui", "interfaz", "color de fondo", "fondo", "background", "color", "oscuro", "claro", "anterior", "previo", "original")
    return (
        any(token in msg for token in change_verbs + restore_verbs)
        and any(token in msg for token in target_tokens)
    )

def is_chat_ui_background_restore_query(message: str) -> bool:
    msg = (message or "").lower()
    restore_verbs = ("vuelve", "volver", "restablece", "restablecer", "retorna", "retornar", "deja", "dejar")
    restore_targets = ("oscuro", "claro", "anterior", "previo", "original", "como estaba")
    return (
        any(token in msg for token in restore_verbs)
        and any(token in msg for token in restore_targets)
    )

def is_chat_send_button_move_query(message: str) -> bool:
    msg = (message or "").lower()
    return (
        any(token in msg for token in ("mueve", "mover", "desplaza", "ajusta"))
        and any(token in msg for token in ("boton de enviar", "botón de enviar", "send button", "send-btn"))
        and any(token in msg for token in ("izquierda", "derecha", "left", "right"))
    )

def is_brain_status_query(message: str) -> bool:
    return any(
        phrase in message for phrase in (
            "estado del brain", "estado actual del brain", "brain status",
            "estado del sistema", "estado actual del sistema", "resumen del brain",
        )
    )

def is_deep_brain_analysis_query(message: str) -> bool:
    analysis_markers = (
        "analiza profundamente", "analisis profundo", "análisis profundo",
        "implicaciones", "explica profundamente", "deep analysis",
    )
    scope_markers = (
        "brain", "sistema", "governance", "gobernanza", "autonomia",
        "autonomía", "self improvement", "autoconstruccion", "autoconstrucción",
    )
    return any(marker in message for marker in analysis_markers) and any(
        marker in message for marker in scope_markers
    )

def looks_like_deep_analysis(message: str) -> bool:
    return any(
        marker in message for marker in (
            "analiza profundamente", "analisis profundo", "análisis profundo",
            "implicaciones", "explica profundamente", "audita", "auditoria",
            "auditoría", "evalua", "evalúa", "deep analysis",
        )
    )

def is_deep_risk_analysis_query(message: str) -> bool:
    return looks_like_deep_analysis(message) and any(
        marker in message for marker in ("riesgo", "risk", "risk contract", "drawdown", "exposure")
    )

def is_deep_edge_analysis_query(message: str) -> bool:
    return looks_like_deep_analysis(message) and any(
        marker in message for marker in ("edge", "edge validation", "validated edge", "probation", "promotable")
    )

def is_deep_strategy_analysis_query(message: str) -> bool:
    return looks_like_deep_analysis(message) and any(
        marker in message for marker in ("strategy engine", "estrategia", "ranking", "strategy", "candidatos")
    )

def is_deep_pipeline_analysis_query(message: str) -> bool:
    return looks_like_deep_analysis(message) and any(
        marker in message for marker in ("pipeline", "integridad", "ledger", "scorecard")
    )

def is_self_build_query(message: str) -> bool:
    return any(
        phrase in message for phrase in (
            "autoconstruccion", "autoconstrucción", "self improvement",
            "self-improvement", "cambios autonomos", "cambios autónomos",
            "promover cambios autonomos", "promover cambios autónomos",
        )
    )

def is_self_build_resolution_query(message: str) -> bool:
    if not is_self_build_query(message) and "automejora" not in message:
        return False
    return any(
        phrase in message for phrase in (
            "por que", "por qué", "detenida", "detenido", "bloqueada",
            "bloqueado", "frenada", "frenado", "parada", "parado",
            "resuelvelo", "resuélvelo", "resolver", "resuelvela",
            "resuélvela", "solucionalo", "soluciónalo", "arreglalo",
            "arréglalo", "playbook", "plan de accion", "plan de acción",
            "como lo resuelvo", "como la resuelvo", "cómo lo resuelvo",
            "cómo la resuelvo",
        )
    )

def is_consciousness_query(message: str) -> bool:
    return any(
        phrase in message for phrase in (
            "autoconsciente", "autoconciencia", "autoconsciencia",
            "self aware", "self-aware", "consciousness",
        )
    )

def is_abstract_reasoning_query(message: str) -> bool:
    return any(
        marker in message for marker in (
            "si todos", "puedes concluir", "se sigue que", "premisa",
            "deduce", "deducir", "logica", "lógica", "syllog", "inferir",
        )
    )

def is_operational_agent_query(message: str) -> bool:
    """Detect queries that can be answered with deterministic formatting
    instead of an unreliable LLM interpretation call."""
    return any(
        token in message for token in (
            "estado", "status", "resume", "resumen", "revisa", "verifica",
            "diagnost", "audit", "audita", "auditor", "health", "salud",
            "operativo", "operativa", "dashboard", "brain", "sistema",
            "puerto", "puertos", "port", "ports", "proceso", "procesos",
            "servicio", "servicios", "service", "services",
            "espacio", "disco", "disk", "memoria", "memory",
            "corriendo", "running", "activo", "activos", "ejecutando",
            "version", "versión", "check", "chequea", "comprueba",
            "ejecuta", "diagnostico", "diagnóstico", "info",
        )
    )

def is_temporal_query(message: str) -> bool:
    return bool(_TEMPORAL_QUERY_RE.search(message or ""))


def contains_raw_tool_markup(text: str) -> bool:
    """Detect raw XML tool-call markup that should never leak to the user."""
    lowered = str(text or "").lower()
    return "<function_calls" in lowered or "<invoke name=" in lowered


def is_manual_confirmation_step(text: str) -> bool:
    """Skip steps that are just confirmation instructions."""
    t = text.lower()
    manual_keywords = [
        "allow once", "allow_once", "allow session", "allow_session",
        "confirmo", "confirma", "dale", "sigue", "continua", "continúa",
        "próximo", "proximo", "next", "manual", "aprueba",
    ]
    return any(k in t for k in manual_keywords)


def is_continue_sequence_message(text: str) -> bool:
    """Detect continuation requests for active sequences."""
    t = text.lower().strip().rstrip(".!?")
    return t in ("continua", "continúa", "sigue", "próximo", "proximo",
                   "next", "dale", "continuar", "adelante", "procede",
                   "continua...", "sigue...")
