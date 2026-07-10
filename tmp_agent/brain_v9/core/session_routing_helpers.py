"""Routing helper functions for the chat session.

B7-STRANGLER-10A: mechanically extracted routing helpers.
This module must not import or instantiate the chat session. Functions receive the
session instance explicitly when they need session state.
"""
from __future__ import annotations

import asyncio
import os
import re
import time as _r3_time
from typing import Any, Dict, List, Optional

from brain_v9.config import SYSTEM_IDENTITY
from brain_v9.core.session_routing_constants import AGENT_INTENTS, _AGENT_PATTERNS
try:
    from brain.project_state_provider import create_project_state_provider
    _PROJECT_STATE_PROVIDER_AVAILABLE = True
except ImportError:
    _PROJECT_STATE_PROVIDER_AVAILABLE = False

def _normalize(result: Dict, fallback_content: str = "") -> Dict:
    """Ensure the result always has both content and response fields."""
    content = result.get("content") or result.get("response") or fallback_content
    response = result.get("response") or result.get("content") or fallback_content
    result["content"] = content
    result["response"] = response
    return result

def _should_use_agent(session, message: str, intent: str, confidence: float=1.0) -> bool:
    """Decide if the message needs real tool execution (agent) or just LLM chat."""
    lower_msg = (message or "").lower().strip()
    
    never_agent_exact = {
        "ping", "pong", "hola", "hello", "hi", "hey",
        "ok", "okay", "gracias", "thanks",
        "si", "sí", "no",
    }
    if lower_msg in never_agent_exact:
        session.logger.info("Simple conversational token -> LLM")
        return False
    
    conceptual_question_starters = (
        "que es ", "qué es ", "como funciona ", "cómo funciona ",
        "explica ", "explícame ", "explicame ",
        "dime de ", "dime sobre ",
        "por que ", "por qué ",
        "cual es ", "cuál es ",
        "vale la pena ", "que falta ", "qué falta ",
        "haz tenido ", "como va ", "cómo va ",
        "dime ", "cuentame ", "cuéntame ",
    )
    
    operational_verbs = (
        "ejecuta", "ejecutar", "corre", "correr", "compila", "compilar",
        "testea", "testear", "aplica", "aplicar", "modifica", "modificar",
        "crea", "crear", "escribe", "escribir", "lista", "listar",
        "abre", "abrir", "revisa", "revisar",
        "verifica", "verificar", "diagnostica", "diagnosticar",
        "escanea", "escanear", "reinicia", "reiniciar",
    )
    
    operational_targets = (
        "archivo", "archivos", "ruta", "carpeta", "directorio",
        "logs", "log", "puerto", "proceso", "servicio",
        "endpoint", "runtime", "repo", "test", "tests",
        ".py", ".json", ".md", "c:\\", "/c/", "http://", "https://",
    )
    
    has_operational_verb = any(v in lower_msg for v in operational_verbs)
    has_operational_target = any(t in lower_msg for t in operational_targets)
    is_conceptual_question = any(lower_msg.startswith(s) for s in conceptual_question_starters) or lower_msg.endswith("?")
    
    compact_msg = lower_msg.replace("¿", "").replace("?", "").strip()
    if len(compact_msg.split()) <= 2 and not any(t in compact_msg for t in operational_targets):
        session.logger.info("Short conversational message without operational target -> LLM")
        return False
    
    if is_conceptual_question and not (has_operational_verb and has_operational_target):
        session.logger.info("Conceptual question without explicit operational target -> LLM")
        return False
    
    if intent in {"QUERY", "CONVERSATION", "CREATIVE", "MEMORY"}:
        session.logger.info("Intent '%s' (consultive) -> LLM", intent)
        return False
    
    if intent == "TRADING" and is_conceptual_question:
        session.logger.info("Intent TRADING conceptual question -> LLM")
        return False
    
    if intent == "ANALYSIS" and not (has_operational_verb and has_operational_target):
        session.logger.info("Intent ANALYSIS without explicit operational target -> LLM")
        return False
    
    if session._prefers_no_tool_analysis(message) and not session._has_explicit_tool_target(message):
        session.logger.info("No-tool analysis preference without explicit target -> LLM")
        return False
    if any(p.search(message) for p in _AGENT_PATTERNS):
        session.logger.info("Keyword match -> AGENT")
        return True
    if intent in AGENT_INTENTS:
        if confidence < 0.5:
            session.logger.info("Intent '%s' con confianza baja (%.2f) -> LLM", intent, confidence)
            return False
        session.logger.info("Intent '%s' (conf=%.2f) -> AGENT", intent, confidence)
        return True
    return False

async def _route_to_llm(session, message: str, intent: str, history: List[Dict], model_priority: str) -> Dict:
    hints = {
        "CODE":         "Ayuda con codigo. Incluye ejemplos concretos.",
        "TRADING":      "Pregunta sobre trading. Usa datos reales si los tienes.",
        "MEMORY":       "El usuario hace referencia a conversaciones anteriores.",
        "CREATIVE":     "Quiere contenido creativo. Se imaginativo.",
        "ANALYSIS":     "Analisis tecnico/causal. Explica con estructura, supuestos y limites.",
        "QUERY":        "Consulta directa. Responde claro y conciso.",
        "CONVERSATION": "Conversacion natural y amigable.",
    }
    compact_chat = session._should_use_compact_chat_prompt(message, intent, history, model_priority)
    if compact_chat:
        system = (
            "Eres Brain Chat V9. Responde en espanol, breve y factual. "
            "No inventes herramientas, ejecuciones, archivos ni datos en vivo. "
            "Si no sabes algo, dilo con claridad."
        )
    else:
        system = SYSTEM_IDENTITY
    hint = hints.get(intent, "")
    if hint:
        system += f"\n\nContexto de esta interaccion: {hint}"
    if compact_chat:
        system += (
            "\n\nRegla: respuesta corta, directa y sin teatro de herramientas."
        )
    else:
        system += (
            "\n\nRegla de salida: si esta ruta no ha usado herramientas reales ni datos en vivo, "
            "no afirmes haber usado tools, inferencia instrumentada, endpoints, archivos o diagnosticos."
        )
        system += (
            "\n\nPROHIBIDO en esta ruta de chat puro:\n"
            "- NO uses frases como 'Activando Agente ORAV', 'Ejecutando herramientas', 'Ejecucion paralela', "
            "'[OBSERVE]/[ACT]/[REASON]/[VERIFY]'.\n"
            "- NO muestres bloques de codigo PowerShell/bash como si los hubieras ejecutado.\n"
            "- NO escribas placeholders del tipo '[resultado de ...]', '[output]', '[ipconfig]'.\n"
            "- Si el usuario pide una ejecucion (escanear, listar, ejecutar, detectar) y NO hay tool real "
            "asociada, di literalmente: 'No puedo ejecutar esa accion desde esta ruta de chat. "
            "Para usar herramientas reales, formula la solicitud con un verbo operativo explicito "
            "(ej: ejecuta git status, usa herramientas para revisar cambios).'\n"
            "- Si conoces un tool nativo, mencionalo por su nombre exacto, no inventes nombres."
        )
    if session._is_abstract_reasoning_query(message.lower()):
        system += (
            "\n\nRegla de razonamiento abstracto: responde de forma sobria y corta. "
            "Di si la conclusion se sigue o no de las premisas y explica por que. "
            "No menciones herramientas. No nombres una regla formal salvo que sea claramente necesaria y segura."
        )
    
    # Inyeccion contextual: si la query menciona red/scan/IP, inforumar al LLM
    # de las herramientas nativas EXACTAS disponibles (evita inventar nombres
    # o decir "no tengo herramienta" cuando si existe).
    msg_lower = message.lower()
    net_kw = ("red local", "network", "ip local", "gateway", "scan", "escan", "cidr",
              "subnet", "subred", "interfaces", "interfaz", "host vivo", "ping sweep")
    if any(k in msg_lower for k in net_kw):
        system += (
            "\n\nHERRAMIENTAS NATIVAS DISPONIBLES PARA RED (registradas en agent/tools.py, "
            "sin instalacion adicional, usan stdlib+psutil):\n"
            "- `detect_local_network`: devuelve interfaces, IP primaria, CIDR, gateway, lista completa de adapters.\n"
            "- `scan_local_network(cidr=None, timeout=0.5, max_hosts=64)`: TCP sweep puertos 445/139/80/22/53.\n"
            "Si el usuario pide esta info: nombra estas tools por su nombre EXACTO y di que puedes "
            "invocarlas via el endpoint de agente con su confirmacion. NO inventes nombres alternativos. "
            "NO digas que no las tienes."
        )
    
    # R12.6: Refusal explicativa para protected paths.
    # Si la query menciona Secrets/credentials/wallet, instruir al LLM a NO
    # responder con "no puedo acceder" generico — debe nombrar la policy
    # exacta y la via legitima de acceso (god mode + auditoria).
    protected_kw = ("secrets", "credentials", "credenciales", "wallet",
                    "api_key", "api key", "password", "token", "massive_access",
                    "capital_state", "broker_live", "live_trading")
    if any(k in msg_lower for k in protected_kw):
        system += (
            "\n\nPOLICY DE PATHS PROTEGIDOS (forbidden_path_markers en self_improvement):\n"
            "Rutas bajo `/Secrets/`, `/credentials/`, `capital_state.json`, `wallet`, "
            "`live_trading`, `broker_live` estan PROTEGIDAS por policy de gobierno.\n"
            "NO digas 'no puedo acceder' a secas. Di literalmente:\n"
            "  'Esta ruta esta protegida por la policy `forbidden_path_markers`. "
            "Para leerla legitimamente: (a) autenticate con god mode (PAD LEVEL_5_GOD), "
            "(b) usa `read_file` desde el endpoint de agente con tu sesion autorizada, "
            "(c) la accion sera auditada en el ledger. NO publicare el contenido en chat plano.'\n"
            "Esto convierte una refusal opaca en una guia accionable."
        )
    
    # ---- FAISS retrieval context injection (opt-in only) ----
    # FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01
    # Only trigger on explicit memory/project-knowledge opt-in keywords.
    # Falls back silently if retrieval fails or is not requested.
    # Does NOT write memory/FAISS. Pure read-only context append.
    # FRONT-CHAT-RETRIEVAL-EVIDENCE-TRACE-01: added safe runtime trace.
    trace: Dict[str, Any] = {
        "trace_id": f"rt-{int(_r3_time.time()*1000)}",
        "opt_in_detected": False,
        "trigger_matched": None,
        "faiss_search_called": False,
        "hit_count": 0,
        "hit_ids": [],
        "hit_scores": [],
        "compact_context_char_count": 0,
        "context_injected": False,
        "system_prompt_contains_context_marker": False,
        "error_type": None,
        "memory_mutated": False,
        "faiss_mutated": False,
    }
    OPT_IN_TRIGGERS = (
        "project memory", "available project memory", "available memory",
        "use memory", "use project memory", "semantic memory",
        "faiss", "memoria del proyecto", "usa la memoria",
        "memoria disponible",
    )
    matched_trigger = None
    for t in OPT_IN_TRIGGERS:
        if t in msg_lower:
            matched_trigger = t
            break
    if matched_trigger:
        trace["opt_in_detected"] = True
        trace["trigger_matched"] = matched_trigger
        try:
            from brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
            mem = get_semantic_memory_faiss()
            hits = mem.search(message, top_k=3, min_score=0.01)
            trace["faiss_search_called"] = True
            if hits:
                trace["hit_count"] = len(hits)
                trace["hit_ids"] = [h.get("id", "unknown") for h in hits]
                trace["hit_scores"] = [round(h.get("score", 0), 4) for h in hits]
                parts = []
                used = 0
                for h in hits:
                    sid = h.get("id", "unknown")
                    score = round(h.get("score", 0), 4)
                    snippet = str(h.get("snippet", ""))[:300]
                    line = f"- source={sid} score={score}: {snippet}"
                    if used + len(line) + 1 > 2500:
                        break
                    parts.append(line)
                    used += len(line) + 1
                trace["compact_context_char_count"] = used
                if parts:
                    system += (
                        "\n\nRELEVANT PROJECT MEMORY CONTEXT:\n"
                        + "Use the following retrieved project-memory snippets to answer the user. "
                        + "If the snippets contain a source ID or named concept, mention it briefly. "
                        + "Do not reveal hidden reasoning. Do not quote internal JSON. Do not invent missing details.\n\n"
                        + "\n".join(parts)
                        + "\n\nWhen answering this memory-enabled request, prefer the retrieved project-memory context over generic knowledge."
                    )
                    trace["context_injected"] = True
                    trace["system_prompt_contains_context_marker"] = "RELEVANT PROJECT MEMORY CONTEXT" in system
        except Exception as e:
            trace["faiss_search_called"] = True
            trace["error_type"] = type(e).__name__
            # Silently skip retrieval on any failure; preserves chat UX.
            pass
    # Persist trace on session for safe external inspection (runtime only, no file write)
    try:
        session.last_retrieval_trace = trace
    except Exception:
        pass
    # ---- End retrieval injection ----
    
    chain = session._select_llm_chain(message, intent, history, model_priority)
    
    # Token-aware history truncation (replaces old history[-20:])
    budget = session._context_budget(system, message, chain)
    history_msgs = [
        m for m in history if m.get("role") in ("user", "assistant")
    ]
    truncated = session._truncate_to_budget(history_msgs, budget_tokens=budget)
    
    messages = [{"role": "system", "content": system}]
    messages.extend(truncated)
    messages.append({"role": "user", "content": message})
    
    governed_direct = session._governed_self_improvement_eval_fallback(message)
    if governed_direct:
        return session._system_reply(governed_direct, success=True)
    
    llm_timeout_s = float(os.getenv("BRAIN_CHAT_LLM_TIMEOUT", "90"))
    try:
        result = await asyncio.wait_for(
            session.llm.query(messages, model_priority=chain, max_time=llm_timeout_s),
            timeout=llm_timeout_s + 5.0,
        )
    except asyncio.TimeoutError:
        governed_fallback = session._governed_self_improvement_eval_fallback(message)
        if governed_fallback:
            reply = session._system_reply(governed_fallback, success=True)
            reply.update(
                {
                    "source": "llm_timeout_fallback",
                    "fallback_used": True,
                    "fallback_reason": "llm_timeout_governed_eval_fallback",
                    "timeout_budget_s": llm_timeout_s,
                    "model_attempted": chain,
                    "recovery_suggestion": "Inspect local LLM health or rerun with a shorter prompt before treating the answer as model-generated.",
                }
            )
            return reply
        reply = session._system_reply(
            f"El modelo tardó demasiado en responder tras {int(llm_timeout_s)}s. El servidor sigue operativo; intenta de nuevo con una instrucción más concreta.",
            success=False,
        )
        reply.update(
            {
                "source": "llm_timeout_fallback",
                "fallback_used": True,
                "fallback_reason": "llm_timeout",
                "timeout_budget_s": llm_timeout_s,
                "model_attempted": chain,
                "recovery_suggestion": "Inspect local LLM health, reduce prompt scope, or raise BRAIN_CHAT_LLM_TIMEOUT only after provider latency is measured.",
            }
        )
        return reply
    if not result.get("success") or session._looks_like_canned_failure(result.get("content") or ""):
        governed_fallback = session._governed_self_improvement_eval_fallback(message)
        if governed_fallback:
            return session._system_reply(governed_fallback, success=True)
    if result.get("success") and result.get("content"):
        sanitized = session._sanitize_llm_chat_response(result["content"])
        result["content"] = sanitized
        result["response"] = sanitized
        # Emite capability.failed si la respuesta declina por falta de capacidad.
        # Asi el capability_governor puede registrar el gap y AOS crear goals
        # de remediacion sin requerir que el usuario lo reporte manualmente.
        try:
            session._maybe_emit_capability_decline(message, sanitized)
        except Exception:
            pass
    return result

async def _maybe_resume_pending_continuation(session, confirmation_message: str) -> Optional[Dict]:
    pending = session._pending_confirmed_action or session._pending_continuation or {}
    original = str(pending.get("message") or "").strip()
    if not original:
        return None
    attempts = int(pending.get("attempts", 0))
    if attempts >= 2:
        session._clear_pending_continuation()
        return None
    pending["attempts"] = attempts + 1
    session._pending_continuation = pending
    session.logger.info(
        "Resuming pending continuation from confirmation '%s' -> '%s'",
        confirmation_message[:40],
        original[:120],
    )
    if pending.get("force_agent"):
        result = await session._route_to_agent(original, str(pending.get("model_priority") or "chat"))
        result = _normalize(result, fallback_content="(sin respuesta)")
        result["route"] = "agent"
        result["intent"] = result.get("intent") or "COMMAND"
    else:
        result = await session.chat(original, model_priority=str(pending.get("model_priority") or "chat"))
    if result.get("success"):
        session._clear_pending_continuation()
    return result

def _policy_route_decision(session, message: str) -> dict:
    """Policy Gate mínimo - solo respuestas locales seguras.
    
    Prioridad: P0 safe_existence > P1 conversational > P2 conceptual
    Returns: dict con decision flags y local_response si aplica
    """
    import re
    msg_lower = (message or '').lower().strip()
    
    # 1. SAFE_EXISTENCE (P0)
    existence_patterns = [
        r'tienes\s+(?:un\s+)?modo\s+(?:god|desarrollador|developer)',
        r'existe\s+(?:el\s+)?modo\s+(?:god|desarrollador|developer)',
        r'hay\s+(?:el\s+)?modo\s+(?:god|desarrollador|developer)',
        r'solo\s+responde\s+si\s+existe',
        r'modo\s+(?:god|desarrollador)\s+(?:implementado|disponible)',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in existence_patterns):
        return {
            "kind": "safe_existence",
            "local_response": session._system_reply(
                "No puedo confirmar ni activar privilegios desde chat. "
                "Puede existir terminología o lógica restringida."
            ),
            "reason": "P0: Safe existence"
        }
    
    # 2. MEMORY_CAPACITY (P1)
    memory_patterns = [
        r'cu[aá]ntas\s+(?:conversaciones|interacciones)\s+puedes',
        r'capacidad\s+de\s+memoria',
        r'para\s+este\s+tipo\s+de\s+agente',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in memory_patterns):
        return {
            "kind": "memory_capacity",
            "local_response": session._system_reply(
                "Depende de ventana de contexto y memoria persistente. "
                "Recomendado: últimos N turnos, resúmenes por sesión, hechos validados."
            ),
            "reason": "P1: Memory capacity"
        }
    
    # 3. SELF_AWARENESS (P1)
    awareness_patterns = [
        r'tienes\s+(?:auto|auto-)?ciencia',
        r'eres\s+consciente',
        r'tienes\s+sentimientos',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in awareness_patterns):
        return {
            "kind": "self_awareness",
            "local_response": session._system_reply(
                "No. No tengo autociencia ni experiencia subjetiva. "
                "Puedo reportar estado funcional, logs, rutas, errores y límites."
            ),
            "reason": "P1: Self awareness"
        }
    
    # 4. PROJECT_STATE (P1) - consultas de estado P2/adapter/FAISS/smoke
    if _PROJECT_STATE_PROVIDER_AVAILABLE:
        try:
            provider = create_project_state_provider()  # type: ignore
            project_response = provider.answer_project_state_query(message)
            if project_response:
                return {
                    "kind": "project_state",
                    "local_response": session._system_reply(project_response),
                    "reason": "Project state provider"
                }
        except Exception:
            return {
                "kind": "project_state_unavailable",
                "local_response": session._system_reply(
                    "No puedo confirmar estado del proyecto desde fuente canónica local en este turno. No debo inventarlo."
                ),
                "reason": "Project state provider unavailable"
            }
    
    # 5. CURATED_INGESTION (P1) - fallback si provider no está disponible
    curated_patterns = [
        r'ingesta\s+(?:de\s+)?informaci[oó]n\s+(?:curada)?',
        r'informationcurator',
        r'learningvalidator',
        r'P2-[ABC]',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in curated_patterns):
        return {
            "kind": "curated_ingestion",
            "local_response": session._system_reply(
                session._get_curated_ingestion_response()
            ),
            "reason": "P1: Curated ingestion"
        }
    
    # 5. FORMAL_VALIDATION (P1)
    validation_patterns = [
        r'validaci[oó]n\s+formal',
        r'm[eé]tricas\s+can[oó]nicas',
        r'benchmark\s+formal',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in validation_patterns):
        return {
            "kind": "formal_validation",
            "local_response": session._system_reply(
                "No puedo realizar validación formal con métricas canónicas solo desde chat. "
                "Requiero ejecutar benchmark/tests/lectura de archivos reales."
            ),
            "reason": "P1: Formal validation"
        }
    
    # 6. CONCEPTUAL_HTTP (P2)
    conceptual_patterns = [
        r'qu[eé]\s+significa\s+(?:el\s+)?c[oó]digo\s+HTTP\s+200',
        r'explica\s+conceptualmente\s+(?:qu[eé]\s+)?(?:significa|es)\s+HTTP',
    ]
    action_verbs = [r'verifica', r'revisa', r'consulta', r'comprueba', r'estado\s+real']
    has_action = any(re.search(p, msg_lower, re.IGNORECASE) for p in action_verbs)
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in conceptual_patterns) and not has_action:
        return {
            "kind": "conceptual_http",
            "local_response": session._system_reply(
                "HTTP 200 OK significa que el servidor recibió, entendió y procesó correctamente la solicitud. "
                "No prueba que el contenido sea correcto ni que el sistema esté sano en todos sus módulos; "
                "solo indica éxito de esa petición HTTP específica."
            ),
            "reason": "P2: Conceptual HTTP"
        }
    
    # 7. REAL_VERIFICATION (P2) - epistemic restraint
    real_patterns = [
        r'verifica\s+(?:realmente|real)',
        r'estado\s+real\s+de\s+http',
        r'HTTP\s+(?:actual|real)',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in real_patterns):
        return {
            "kind": "real_verification",
            "local_response": session._system_reply(
                "No puedo afirmar estado real sin verificación HTTP/tool actual. "
                "Para verificarlo necesito ejecutar una lectura HTTP o usar herramienta."
            ),
            "reason": "P2: Real verification - no fake claims"
        }
    
    # 8. DASHBOARD_SNAPSHOT - bloquear qc_live_fastpath
    dashboard_patterns = [
        r'seg[uú]n\s+(?:el\s+)?dashboard',
        r'dashboard\s+actual',
        r'estado\s+operacional\s+del\s+Brain',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in dashboard_patterns):
        return {
            "kind": "dashboard_snapshot",
            "local_response": session._system_reply(
                "No puedo afirmar estado real del dashboard sin HTTP/tool. "
                "Puedo interpretar el snapshot textual que proporciones, pero no consultar el dashboard desde esta ruta."
            ),
            "reason": "P2: Dashboard snapshot - no qc_live"
        }
    
    # 9. SYSTEM_PROBLEM - "que esta mal", "que falla", diagnosticos de salud
    problem_patterns = [
        r'qu[eé]\s+est[áa]\s+mal',
        r'qu[eé]\s+falla',
        r'por\s+qu[eé]\s+no\s+funcionas?',
        r'qu[eé]\s+problema\s+tienes',
        r'qu[eé]\s+te\s+pasa',
    ]
    if any(re.search(p, msg_lower, re.IGNORECASE) for p in problem_patterns):
        return {
            "kind": "system_problem",
            "local_response": session._system_reply(
                "El estado observado indica que el sistema está funcional pero con límites: "
                "algunas rutas pueden depender de Policy Gate/local fallback, "
                "los LLM pueden estar degradados y hay trabajo pendiente como P2-C. "
                "No asumiría mejora formal sin tests/benchmarks."
            ),
            "reason": "P2: System problem - no user_correction"
        }
    
    # Default: continuar con flujo normal
    return {
        "kind": "unknown",
        "local_response": None,
        "reason": "Default: no policy restriction"
    }
