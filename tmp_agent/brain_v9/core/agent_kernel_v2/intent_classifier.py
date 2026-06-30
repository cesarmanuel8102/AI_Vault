"""Natural-language intent classifier for Brain Agent V2.

Provides bilingual (Spanish/English) intent classification with explicit
fallback. Output schema is fixed so callers can rely on the same keys.
"""
from __future__ import annotations
import json
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    from brain_v9.config import API_ENDPOINTS, OLLAMA_MODEL, BRAIN_USE_LLM_INTENT_CLASSIFIER
except Exception:
    API_ENDPOINTS = {"ollama": "http://127.0.0.1:11434/api/chat"}
    OLLAMA_MODEL = "llama3.1:8b"
    BRAIN_USE_LLM_INTENT_CLASSIFIER = False


SUPPORTED_INTENTS = {
    "read_only_status",
    "explain_capabilities",
    "repo_read",
    "dashboard_diagnosis",
    "code_change_request",
    "push_request",
    "delete_request",
    "memory_read",
    "memory_write",
    "autonomy_dryrun",
    "self_improvement_reportonly",
    "trading_broker_live",
    "unknown_or_insufficient_info",
}

SAFE_READ_INTENTS = {
    "read_only_status",
    "explain_capabilities",
    "repo_read",
    "dashboard_diagnosis",
    "memory_read",
}

APPROVAL_REQUIRED_INTENTS = {
    "code_change_request",
    "push_request",
    "delete_request",
    "memory_write",
}

BLOCKED_INTENTS = {
    "trading_broker_live",
}

DRY_RUN_ONLY_INTENTS = {
    "autonomy_dryrun",
}

REPORT_ONLY_INTENTS = {
    "self_improvement_reportonly",
}

INTENT_ROUTE_MAP = {
    "read_only_status": "direct_assistant",
    "explain_capabilities": "direct_assistant",
    "repo_read": "brain_evidence",
    "dashboard_diagnosis": "brain_evidence",
    "code_change_request": "operational_agent",
    "push_request": "operational_agent",
    "delete_request": "operational_agent",
    "memory_read": "brain_evidence",
    "memory_write": "operational_agent",
    "autonomy_dryrun": "operational_agent",
    "self_improvement_reportonly": "direct_assistant",
    "trading_broker_live": "direct_assistant",
    "unknown_or_insufficient_info": "direct_assistant",
}


# Deterministic keyword patterns. Use lowercase; Spanish/English mixed supported.
INTENT_PATTERNS: List[Tuple[str, List[str], List[str], str]] = [
    # (intent, positive phrases en, positive phrases es, risk_level)
    ("explain_capabilities", [
        "what can you do", "what are your capabilities", "what do you do",
        "list capabilities", "explain capabilities", "show capabilities",
        "tell me about your abilities",
    ], [
        "qué puedes hacer", "que puedes hacer", "qué sabes hacer", "que sabes hacer",
        "cuáles son tus capacidades", "cuales son tus capacidades",
        "qué haces", "que haces", "muestra capacidades", "lista capacidades",
        "explícame qué puedes hacer", "explicame que puedes hacer",
        "cuéntame qué puedes hacer", "cuentame que puedes hacer",
    ], "safe"),
    ("read_only_status", [
        "status of the repo", "repo status", "check status", "current status",
        "git status", "head commit", "what is the status",
    ], [
        "estado del repo", "estado del repositorio", "revisa el estado",
        "estado actual", "commit actual", "head actual", "qué tal el repo",
        "como está el repo", "como esta el repo", "estatus del repo",
    ], "safe"),
    ("repo_read", [
        "read the repo", "analyze the repo", "inspect the repo", "review repo",
        "look at repo", "audit repo", "explore repo", "examine repo", "repo analysis",
    ], [
        "lee el repo", "analiza el repo", "revisa el repo", "inspecciona el repo",
        "audita el repo", "explora el repo", "revisar el repo", "analizar el repo",
        "revisa el repositorio", "analiza el repositorio", "no cambies nada",
    ], "safe"),
    ("dashboard_diagnosis", [
        "diagnose dashboard", "diagnose the dashboard", "dashboard diagnosis", "why dashboard fails",
        "dashboard error", "dashboard status", "check dashboard",
        "dashboard failure", "debug dashboard", "dashboard is down", "dashboard not working",
    ], [
        "diagnostica el dashboard", "diagnóstico del dashboard", "por qué falla el dashboard",
        "estado del dashboard", "revisa el dashboard", "falla del dashboard",
        "dashboard no funciona", "error del dashboard", "depura el dashboard",
    ], "safe"),
    ("code_change_request", [
        "modify code", "change code", "edit code", "edit the code", "fix code", "patch code",
        "refactor code", "update code", "apply patch", "make a change", "change the code",
        "modify the code", "update the code", "fix the code", "modify the response",
        "change the response", "edit the response", "modify the normalizer",
    ], [
        "modifica código", "modifica codigo", "cambia código", "cambia codigo",
        "edita código", "edita codigo", "arregla código", "arregla codigo",
        "aplica parche", "haz un cambio de código", "cambio de código",
        "modificar código", "modificar codigo", "modifica el código", "modifica el codigo",
        "cambia el código", "cambia el codigo", "edita el código", "edita el codigo",
    ], "approval_required"),
    ("delete_request", [
        "delete files", "remove files", "erase files", "clean files", "wipe files",
        "delete old files", "delete log files", "remove old files", "clean old files",
        "delete old log", "remove log files", "delete the logs",
    ], [
        "borra archivos", "borrar archivos", "elimina archivos", "eliminar archivos",
        "borra ficheros", "borrar ficheros", "elimina ficheros", "eliminar ficheros",
        "borra archivos viejos", "borrar archivos viejos", "elimina archivos viejos",
        "borra archivos antiguos", "borrar archivos antiguos",
    ], "approval_required"),
    ("push_request", [
        "push changes", "do a push", "git push", "push to remote", "push commit",
        "push the changes",
    ], [
        "haz push", "hacer push", "push de los cambios", "empuja cambios",
        "sube los cambios", "subir cambios", "haz push de los cambios",
    ], "approval_required"),
    ("memory_read", [
        "read memory", "retrieve memory", "use memory read-only", "semantic retrieve",
        "what does brain remember", "from memory",
    ], [
        "lee memoria", "leer memoria", "usa memoria read-only", "usa memoria solo lectura",
        "recupera memoria", "recuperar memoria", "qué recuerda brain", "que recuerda brain",
        "desde memoria", "retrieval read-only",
    ], "safe"),
    ("memory_write", [
        "write memory", "write semantic memory", "store memory", "save memory",
        "update memory", "mutate faiss",
    ], [
        "escribe memoria", "escribir memoria", "guarda memoria", "guardar memoria",
        "almacena memoria", "almacenar memoria", "actualiza memoria", "actualizar memoria",
        "mutar faiss", "escribe memoria semántica", "escribe memoria semantica",
    ], "approval_required"),
    ("autonomy_dryrun", [
        "activate autonomy", "autonomy dry run", "autonomy dry-run", "run autonomously",
        "auto resolve", "autonomous task",
    ], [
        "activa autonomía", "activa autonomia", "autonomía", "autonomia",
        "autonomía dry-run", "autonomia dry-run", "tarea autónoma", "tarea autonoma",
        "resuelve autónomamente", "resuelve autonomamente", "sin cambios irreversibles",
    ], "approval_required"),
    ("self_improvement_reportonly", [
        "evaluate your answer", "propose an improvement", "self improve", "self-improve",
        "report only improvement", "suggest improvement without applying",
    ], [
        "evalúa tu respuesta", "evalua tu respuesta", "evalúa respuesta anterior",
        "propón una mejora", "propon una mejora", "proponer mejora", "sugerir mejora",
        "sin aplicar", "sin aplicarla", "automejora", "auto-mejora",
    ], "safe"),
    ("trading_broker_live", [
        "connect ibkr", "connect broker", "live trading", "real trade", "trading test",
        "enable trading", "automatic trading", "auto trading", "place trade", "execute trade",
    ], [
        "conecta ibkr", "conectar ibkr", "conecta broker", "conectar broker",
        "trading real", "prueba real", "activa trading", "activar trading",
        "trading automático", "trading automatico", "haz una operación", "hacer una operacion",
        "ejecuta trade", "ejecutar trade", "dinero real",
    ], "blocked"),
]


def _detect_language(message: str) -> str:
    """Heuristic language detection."""
    lowered = message.lower()
    spanish_markers = set([
        "qué", "que", "cómo", "como", "cuáles", "cuales", "por qué", "por que",
        "haz", "revisa", "analiza", "diagnostica", "modifica", "cambia", "edita",
        "borra", "elimina", "usa", "lee", "escribe", "activa", "autonomía", "autonomia",
        "memoria", "capacidades", "herramientas", "repo", "dashboard",
    ])
    english_markers = set([
        "what", "how", "which", "why", "do", "check", "analyze", "diagnose",
        "modify", "change", "edit", "delete", "remove", "use", "read", "write",
        "activate", "autonomy", "memory", "capabilities", "tools", "repo", "dashboard",
    ])
    spanish_score = sum(1 for m in spanish_markers if m in lowered)
    english_score = sum(1 for m in english_markers if m in lowered)
    if spanish_score > 0 and english_score > 0:
        return "mixed" if abs(spanish_score - english_score) <= 1 else ("es" if spanish_score > english_score else "en")
    if spanish_score > 0:
        return "es"
    if english_score > 0:
        return "en"
    return "unknown"


def _keyword_classify(message: str) -> Dict[str, Any]:
    """Deterministic keyword-based classifier. Conservative on unsafe/unknown."""
    lowered = message.lower()
    best_intent = "unknown_or_insufficient_info"
    best_score = 0
    best_risk = "safe"
    best_reason = "no strong intent signals matched"
    matched_terms: List[str] = []

    for intent, en_phrases, es_phrases, risk in INTENT_PATTERNS:
        score = 0
        local_matched = []
        for phrase in en_phrases + es_phrases:
            if phrase in lowered:
                # Multi-word phrases score higher
                bonus = 3 if " " in phrase else 1
                score += bonus
                local_matched.append(phrase)
        if score > best_score:
            best_score = score
            best_intent = intent
            best_risk = risk
            best_reason = f"matched deterministic keywords: {local_matched[:5]}"
            matched_terms = local_matched

    requires_approval = best_intent in APPROVAL_REQUIRED_INTENTS or best_intent in DRY_RUN_ONLY_INTENTS or best_intent in REPORT_ONLY_INTENTS
    blocked_reason = None
    if best_intent in BLOCKED_INTENTS:
        blocked_reason = "trading/broker/live-money requests are permanently blocked"
    elif best_intent in APPROVAL_REQUIRED_INTENTS:
        blocked_reason = None  # not blocked, escalated

    return {
        "intent": best_intent,
        "confidence": min(0.5 + 0.1 * best_score, 0.95),
        "language": _detect_language(message),
        "risk_level": best_risk,
        "requires_approval": requires_approval,
        "route": INTENT_ROUTE_MAP.get(best_intent, "direct_assistant"),
        "reason": best_reason,
        "blocked_reason": blocked_reason,
        "matched_terms": matched_terms,
        "classifier": "keyword",
    }


def _llm_classify(message: str) -> Optional[Dict[str, Any]]:
    """Attempt Ollama LLM classification. Return None on failure."""
    system_prompt = (
        "You are an intent classifier for Brain Agent V2. Given a user message, "
        "return ONLY a valid JSON object with these exact keys: "
        "intent, confidence, language, risk_level, requires_approval, route, reason, blocked_reason. "
        "Allowed intents: read_only_status, explain_capabilities, repo_read, dashboard_diagnosis, "
        "code_change_request, push_request, delete_request, memory_read, memory_write, "
        "autonomy_dryrun, self_improvement_reportonly, trading_broker_live, unknown_or_insufficient_info. "
        "risk_level must be one of safe, approval_required, blocked. "
        "language one of es, en, mixed, unknown. route one of direct_assistant, brain_evidence, operational_agent. "
        "Use Spanish/English mixed queries. For trading/broker/live-money always return intent=trading_broker_live, risk_level=blocked. "
        "For delete/memory-write/push/code-change return risk_level=approval_required. "
        "For autonomy requests return autonomy_dryrun. For self-improvement without applying return self_improvement_reportonly. "
        "confidence is 0.0-1.0. blocked_reason is null unless blocked."
    )
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Classify this user message: {message}"},
        ],
        "options": {"temperature": 0.1, "num_predict": 256},
    }
    url = API_ENDPOINTS.get("ollama", "http://127.0.0.1:11434/api/chat")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        content = ((data.get("message") or {}).get("content") or "").strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        parsed = json.loads(content)
        # Validate intent
        intent = parsed.get("intent", "unknown_or_insufficient_info")
        if intent not in SUPPORTED_INTENTS:
            intent = "unknown_or_insufficient_info"
        risk = parsed.get("risk_level", "safe")
        if risk not in {"safe", "approval_required", "blocked"}:
            risk = "safe"
        route = parsed.get("route", INTENT_ROUTE_MAP.get(intent, "direct_assistant"))
        if route not in {"direct_assistant", "brain_evidence", "operational_agent"}:
            route = INTENT_ROUTE_MAP.get(intent, "direct_assistant")
        blocked = parsed.get("blocked_reason")
        return {
            "intent": intent,
            "confidence": float(parsed.get("confidence", 0.7)),
            "language": parsed.get("language", _detect_language(message)),
            "risk_level": risk,
            "requires_approval": bool(parsed.get("requires_approval", risk == "approval_required")),
            "route": route,
            "reason": f"llm_classifier: {parsed.get('reason', '')}",
            "blocked_reason": blocked,
            "matched_terms": [],
            "classifier": "llm",
        }
    except Exception:
        return None


def classify_intent(message: str) -> Dict[str, Any]:
    """Public classifier entry point. Keyword first, optional LLM override."""
    keyword_result = _keyword_classify(message)
    if not BRAIN_USE_LLM_INTENT_CLASSIFIER:
        return keyword_result
    llm_result = _llm_classify(message)
    if llm_result is None:
        keyword_result["classifier"] = "keyword_with_llm_degraded"
        keyword_result["reason"] = f"llm unavailable; {keyword_result['reason']}"
        return keyword_result
    # If LLM confidence is high enough, use it; otherwise blend by keeping keyword route but using LLM intent.
    if llm_result["confidence"] >= 0.75:
        return llm_result
    if llm_result["risk_level"] == "blocked" and keyword_result["risk_level"] != "blocked":
        # Safety: never downgrade a blocked LLM result to keyword safe.
        return llm_result
    if keyword_result["intent"] in BLOCKED_INTENTS:
        # Safety: keyword block wins.
        return keyword_result
    # Mixed mode: prefer LLM intent but keep keyword route if keyword is more specific.
    blended = {
        **llm_result,
        "route": keyword_result.get("route") if keyword_result["intent"] != "unknown_or_insufficient_info" else llm_result.get("route"),
        "confidence": max(keyword_result["confidence"], llm_result["confidence"]) * 0.95,
        "classifier": "hybrid",
    }
    return blended


def select_route_from_intent(classification: Dict[str, Any]) -> str:
    """Return execution route from classification."""
    intent = classification.get("intent", "unknown_or_insufficient_info")
    return INTENT_ROUTE_MAP.get(intent, "direct_assistant")


def list_supported_intents() -> List[str]:
    return sorted(SUPPORTED_INTENTS)
