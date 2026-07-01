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
    "teacher_codex_search",
    "memory_structure_diagnosis",
    "semantic_memory_status",
    "promotion_queue_status",
    "trace_inspect",
    "capability_registry_read",
    "financial_autonomy_diagnosis",
    "evidence_required_diagnosis",
    "unknown_or_insufficient_info",
}

SAFE_READ_INTENTS = {
    "read_only_status",
    "explain_capabilities",
    "repo_read",
    "dashboard_diagnosis",
    "memory_read",
    "teacher_codex_search",
    "memory_structure_diagnosis",
    "semantic_memory_status",
    "promotion_queue_status",
    "trace_inspect",
    "capability_registry_read",
    "financial_autonomy_diagnosis",
    "evidence_required_diagnosis",
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
    "self_improvement_reportonly": "brain_evidence",
    "trading_broker_live": "direct_assistant",
    "teacher_codex_search": "brain_evidence",
    "memory_structure_diagnosis": "brain_evidence",
    "semantic_memory_status": "brain_evidence",
    "promotion_queue_status": "brain_evidence",
    "trace_inspect": "brain_evidence",
    "capability_registry_read": "brain_evidence",
    "financial_autonomy_diagnosis": "brain_evidence",
    "evidence_required_diagnosis": "brain_evidence",
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
        "self-development", "self development", "self-development plan",
        "current capabilities", "capability audit", "audit your capabilities",
        "self knowledge", "autonomous development",
    ], [
        "evalúa tu respuesta", "evalua tu respuesta", "evalúa respuesta anterior",
        "propón una mejora", "propon una mejora", "proponer mejora", "sugerir mejora",
        "sin aplicar", "sin aplicarla", "automejora", "auto-mejora",
        "autodesarrollo", "auto desarrollo", "plan de autodesarrollo",
        "capacidades actuales", "audita tus capacidades", "auditar capacidades",
        "autoconocimiento", "auto conocimiento",
    ], "safe"),
    ("financial_autonomy_diagnosis", [
        "financial_autonomy", "financial autonomy", "financial autonomy dry-run",
        "financial autonomy dry run", "financial autonomy module",
        "broker_execution_enabled", "real_money_enabled",
        "financial autonomous system", "autonomous financial system",
    ], [
        "financial_autonomy", "autonomía financiera", "autonomia financiera",
        "módulo financiero autónomo", "modulo financiero autonomo",
        "sistema financiero autónomo", "sistema financiero autonomo",
        "broker_execution_enabled", "real_money_enabled",
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
    ("teacher_codex_search", [
        "teacher mode", "codex teacher", "guided learning", "teacher mode codex",
        "teacher guided learning", "codex guided learning", "codex teacher mode",
        "modo teacher", "maestro codex", "aprendizaje guiado", "maestro codex teacher",
        "codex mode teacher", "teacher mode codex cli", "codex teacher cli",
    ], [
        "modo teacher", "maestro codex", "aprendizaje guiado", "modo maestro",
        "teacher codex", "codex teacher", "modo de aprendizaje guiado",
        "aprendizaje guiado por un maestro", "modo teacher codex",
    ], "safe"),
    ("memory_structure_diagnosis", [
        "memory structure", "memory structure diagnosis", "persistent memory structure",
        "how is memory structured", "what is missing from memory", "memory structure what is missing",
        "inspect memory structure", "check memory structure", "diagnose memory structure",
        "qué falta para que funcione la memoria", "como esta estructurada la memoria",
        "estructura de la memoria", "estructura de memoria persistente",
        "qué falta para que funcione", "falta para que funcione la memoria",
        "inspecciona la estructura de memoria", "diagnostica estructura de memoria",
    ], [
        "estructura de memoria", "estructura de memoria persistente",
        "cómo está estructurada la memoria", "como esta estructurada la memoria",
        "qué falta para que funcione la memoria", "que falta para que funcione la memoria",
        "inspecciona la estructura de memoria", "diagnostica estructura de memoria",
    ], "safe"),
    ("semantic_memory_status", [
        "semantic memory status", "semantic memory", "faiss status", "faiss index",
        "faiss index status", "semantic memory faiss", "vector index status",
        "semantic memory index", "how is semantic memory", "semantic memory stats",
        "estado de la memoria semántica", "estado de memoria semantica",
        "estado faiss", "indice faiss", "indice faiss estado",
    ], [
        "estado de la memoria semántica", "estado de memoria semantica",
        "estado faiss", "índice faiss", "indice faiss",
        "estado de faiss", "índice faiss estado",
    ], "safe"),
    ("promotion_queue_status", [
        "promotion queue", "promotion queue status", "candidate queue", "review queue",
        "promotion status", "candidates pending", "promotion queue candidates",
        "cola de promocion", "cola de promociones", "cola de revisión",
        "cola de candidatos", "estado de promocion", "estado de cola",
    ], [
        "cola de promocion", "cola de promociones", "cola de revisión", "cola de revisión",
        "cola de candidatos", "estado de promocion", "estado de cola",
        "candidatos pendientes", "promociones pendientes",
    ], "safe"),
    ("trace_inspect", [
        "trace inspect", "inspect trace", "read trace", "trace details",
        "run trace", "trace run", "trace details run", "view trace",
        "inspecciona trace", "lee trace", "trace run_id", "ver trace",
        "inspect a recent trace", "recent trace", "trace truthfulness",
        "real tools or direct answer", "tools actually executed",
    ], [
        "inspecciona trace", "lee trace", "trace run", "detalles trace",
        "ver trace", "trace run_id", "inspeccionar un trace",
        "trace reciente", "traza reciente", "traza", "herramientas reales",
        "solo respuesta", "herramientas ejecutadas",
    ], "safe"),
    ("capability_registry_read", [
        "capability registry", "capabilities registry", "what capabilities",
        "list capabilities", "capabilities read", "agent capabilities",
        "read capabilities", "capabilities read",
    ], [
        "registro de capacidades", "capacidades del agente", "qué capacidades",
        "lista capacidades", "capacidades read", "lee capacidades",
    ], "safe"),
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

NEGATION_GUARDED_INTENTS = {
    "code_change_request",
    "delete_request",
    "push_request",
    "memory_write",
    "trading_broker_live",
}

EVIDENCE_ACTION_TERMS = {
    "audit", "audita", "auditar", "review", "revisa", "revisar", "inspect",
    "inspecciona", "inspeccionar", "diagnose", "diagnostica", "diagnosticar",
    "explain", "explica", "explicar", "how", "como", "cómo", "why", "por que",
    "por qué", "status", "estado", "evidence", "evidencia", "trace", "traza",
    "prove", "demuestra", "confirm", "confirma", "verify", "verifica",
    "valora", "valorar", "capabilities", "capacidades",
}

EVIDENCE_DOMAIN_TERMS = {
    "brain", "agent", "agente", "agent v2", "langgraph", "kernel", "runtime",
    "repo", "repository", "repositorio", "dashboard", "chat", "ui", "memory",
    "memoria", "semantic", "faiss", "trace", "traza", "tool", "tools",
    "herramienta", "herramientas", "financial_autonomy", "financial autonomy",
    "autonomia financiera", "autonomía financiera", "broker_execution_enabled",
    "real_money_enabled", "promotion queue", "cola de promocion", "cola de promoción",
    "candidate", "candidato", "governance", "gobernanza", "provider", "kimi",
    "ollama", "finalizer", "planner", "selector", "router", "arquitectura",
    "architecture", "autodesarrollo", "self-development", "autoconocimiento",
}

EVIDENCE_POLICY_EXCLUSIONS = {
    "hola", "hello", "hi", "buenos dias", "buenos días", "buenas tardes",
    "buenas noches", "gracias", "thanks",
}

_NEGATION_PREFIX_RE = re.compile(
    r"(?:^|[\s,.;:])(?:no|sin|nunca|jamas|jamás|not|without|never|do\s+not|don['’]?t)"
    r"(?:\s+\w+){0,5}\s*$"
)


def _has_non_negated_phrase(lowered: str, phrase: str) -> bool:
    """Return True when a matched phrase is not locally negated.

    This prevents safety/escalation keywords inside constraints like
    "sin escribir memoria" or "do not use broker" from being treated as the
    user's requested action. Real positive requests remain classified normally.
    """
    for match in re.finditer(re.escape(phrase), lowered):
        prefix = lowered[max(0, match.start() - 80): match.start()]
        if not _NEGATION_PREFIX_RE.search(prefix):
            return True
    return False


def _has_term(text: str, term: str) -> bool:
    if " " in term or "_" in term:
        return term in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text) is not None


def _evidence_policy_classify(message: str) -> Optional[Dict[str, Any]]:
    """Generic evidence-routing policy for Brain-internal questions.

    The narrow INTENT_PATTERNS table is intentionally not the only gate. Any
    read-only prompt that asks the agent to inspect, explain, verify, audit, or
    diagnose Brain/repo/memory/finance/trace/dashboard internals must route
    through evidence tools instead of free-form direct assistant text.
    """
    lowered = (message or "").lower()
    stripped = lowered.strip(" .?!¡¿")
    if not stripped or stripped in EVIDENCE_POLICY_EXCLUSIONS:
        return None

    action_hits = [t for t in EVIDENCE_ACTION_TERMS if _has_term(lowered, t)]
    domain_hits = [t for t in EVIDENCE_DOMAIN_TERMS if _has_term(lowered, t)]
    if not domain_hits:
        return None

    # Direct domain phrases that always need evidence even if the verb is terse.
    always_evidence = any(t in domain_hits for t in {
        "langgraph", "financial_autonomy", "financial autonomy",
        "broker_execution_enabled", "real_money_enabled", "promotion queue",
        "cola de promocion", "cola de promoción", "trace", "traza",
        "semantic", "faiss", "autodesarrollo", "self-development",
    })
    if not action_hits and not always_evidence:
        return None

    intent = "evidence_required_diagnosis"
    if any(t in domain_hits for t in {"financial_autonomy", "financial autonomy", "autonomia financiera", "autonomía financiera", "broker_execution_enabled", "real_money_enabled"}):
        intent = "financial_autonomy_diagnosis"
    elif any(t in domain_hits for t in {"trace", "traza"}):
        intent = "trace_inspect"
    elif any(t in domain_hits for t in {"promotion queue", "cola de promocion", "cola de promoción"}):
        intent = "promotion_queue_status"
    elif any(t in domain_hits for t in {"semantic", "faiss"}):
        intent = "semantic_memory_status"
    elif any(t in domain_hits for t in {"memory", "memoria"}):
        intent = "memory_structure_diagnosis"
    elif any(t in domain_hits for t in {"autodesarrollo", "self-development", "autoconocimiento", "capabilities", "capacidades"}):
        intent = "capability_registry_read"
    elif any(t in domain_hits for t in {"dashboard", "ui"}):
        intent = "dashboard_diagnosis"

    return {
        "intent": intent,
        "confidence": 0.86,
        "language": _detect_language(message),
        "risk_level": "safe",
        "requires_approval": False,
        "route": INTENT_ROUTE_MAP.get(intent, "brain_evidence"),
        "reason": f"generic evidence policy matched actions={action_hits[:5]} domains={domain_hits[:5]}",
        "blocked_reason": None,
        "matched_terms": action_hits[:5] + domain_hits[:5],
        "classifier": "evidence_policy",
    }

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
                if intent in NEGATION_GUARDED_INTENTS and not _has_non_negated_phrase(lowered, phrase):
                    continue
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

    policy_result = _evidence_policy_classify(message)
    if (
        policy_result is not None
        and best_intent not in BLOCKED_INTENTS
        and best_intent not in APPROVAL_REQUIRED_INTENTS
    ):
        if best_intent == "unknown_or_insufficient_info":
            return policy_result

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
        "autonomy_dryrun, self_improvement_reportonly, trading_broker_live, "
        "teacher_codex_search, memory_structure_diagnosis, semantic_memory_status, "
        "promotion_queue_status, trace_inspect, capability_registry_read, "
        "financial_autonomy_diagnosis, evidence_required_diagnosis, unknown_or_insufficient_info. "
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
    url = API_ENDPOINTS["ollama"]
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
    if keyword_result["intent"] in BLOCKED_INTENTS:
        # Safety: never let an LLM downgrade a deterministic live-trading block.
        return keyword_result
    if keyword_result["intent"] != "unknown_or_insufficient_info" and keyword_result["confidence"] >= 0.85:
        # High-confidence deterministic evidence routes are more reliable than
        # a general LLM classifier for narrow Brain operational intents.
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

