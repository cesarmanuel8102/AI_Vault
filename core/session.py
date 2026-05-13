"""
Brain Chat V9 — BrainSession v3 FIXED
Enrutamiento inteligente LLM vs AgentLoop.
Fix: response y content siempre presentes en el resultado.
"""
import logging
from typing import Dict, List, Optional

from brain_v9.config import SYSTEM_IDENTITY
from brain_v9.core.llm import LLMManager
from brain_v9.core.memory import MemoryManager
from brain_v9.core.intent import IntentDetector
from brain_v9.core.nlp import ContextManager, ResponseFormatter

AGENT_INTENTS = {"ANALYSIS", "SYSTEM", "CODE", "COMMAND"}

AGENT_KEYWORDS = [
    "revisa", "verifica", "analiza", "diagnostica", "chequea",
    "que pasa", "qué pasa", "por que", "por qué", "caido", "caída",
    "no funciona", "busca", "encuentra", "lista", "muestra los",
    "ejecuta", "corre", "inspecciona", "estado de", "estado del",
    "puerto", "proceso", "log", "logs", "archivo", "carpeta",
    "directorio", "memoria", "cpu", "disco", "dashboard",
    "servicio", "servicios", "arregla", "dime que", "dime qué",
    "que hay en", "qué hay en", "que esta", "qué está",
    "que estan", "qué están", "corriendo en", "inicia", "arranca",
    "detén", "reinicia", "capital", "trading", "pocketoption",
    "rooms", "autonomia", "autonomía", "fase", "diagnóstico",
]


def _normalize(result: Dict, fallback_content: str = "") -> Dict:
    """
    Garantiza que el resultado siempre tenga AMBOS campos:
    - content  (usado internamente por session y memory)
    - response (usado por main.py y la UI)
    Si alguno falta, se copia del otro.
    """
    content  = result.get("content")  or result.get("response")  or fallback_content
    response = result.get("response") or result.get("content")   or fallback_content
    result["content"]  = content
    result["response"] = response
    return result


class BrainSession:
    """Sesión con enrutamiento inteligente LLM ↔ AgentLoop."""

    def __init__(self, session_id: str = "default"):
        self.session_id  = session_id
        self.logger      = logging.getLogger(f"BrainSession.{session_id}")
        self.llm         = LLMManager()
        self.memory      = MemoryManager(session_id)
        self.intent      = IntentDetector()
        self.context_mgr = ContextManager()
        self.formatter   = ResponseFormatter()
        self._executor   = None
        self.is_running  = True
        self.logger.info("BrainSession '%s' v3-fixed lista", session_id)

    async def chat(self, message: str, model_priority: str = "ollama") -> Dict:
        history = self.memory.get_context()
        intent, confidence, _ = self.intent.detect(message, history)
        use_agent = self._should_use_agent(message, intent)

        self.logger.info(
            "MSG='%s...' | INTENT=%s (%.2f) | RUTA=%s",
            message[:50], intent, confidence,
            "AGENTE" if use_agent else "LLM"
        )

        if use_agent:
            result = await self._route_to_agent(message, model_priority)
        else:
            result = await self._route_to_llm(message, intent, history, model_priority)

        # Normalizar siempre antes de guardar y retornar
        result = _normalize(result, fallback_content="(sin respuesta)")

        # Guardar en memoria
        self.memory.save({"role": "user", "content": message})
        if result.get("success") and result.get("content"):
            self.memory.save({"role": "assistant", "content": result["content"]})

        result["intent"] = intent
        result["route"]  = "agent" if use_agent else "llm"
        return result

    def _should_use_agent(self, message: str, intent: str) -> bool:
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in AGENT_KEYWORDS):
            self.logger.info("Keyword match -> AGENTE")
            return True
        if intent in AGENT_INTENTS:
            self.logger.info("Intent '%s' -> AGENTE", intent)
            return True
        return False

    async def _route_to_llm(
        self, message: str, intent: str,
        history: List[Dict], model_priority: str
    ) -> Dict:
        self.context_mgr.add_message(self.session_id, "user", message, intent)

        hints = {
            "CODE":         "Ayuda con código. Incluye ejemplos concretos.",
            "TRADING":      "Pregunta sobre trading. Usa datos reales si los tienes.",
            "MEMORY":       "El usuario hace referencia a conversaciones anteriores.",
            "CREATIVE":     "Quiere contenido creativo. Sé imaginativo.",
            "QUERY":        "Consulta directa. Responde claro y conciso.",
            "CONVERSATION": "Conversación natural y amigable.",
        }
        system = SYSTEM_IDENTITY
        hint   = hints.get(intent, "")
        if hint:
            system += f"\n\nContexto de esta interacción: {hint}"

        messages = [{"role": "system", "content": system}]
        for msg in history[-20:]:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        # Usar cadena "code" para intenciones de código
        chain = "code" if intent == "CODE" else model_priority
        result = await self.llm.query(messages, model_priority=chain)
        # llm.query() devuelve {"success":..., "content":..., "model":...}
        # _normalize() copiará content → response
        return result

    async def _route_to_agent(self, message: str, model_priority: str) -> Dict:
        from brain_v9.agent.loop import AgentLoop
        from brain_v9.agent.tools import build_standard_executor

        if self._executor is None:
            self._executor = build_standard_executor()
            self.logger.info(
                "ToolExecutor inicializado: %d tools",
                len(self._executor.list_tools())
            )

        loop = AgentLoop(self.llm, self._executor)
        loop.MAX_STEPS = 6

        agent_result = await loop.run(
            task    = message,
            context = {
                "session_id":     self.session_id,
                "history":        self.memory.get_context()[-4:],
                "model_priority": model_priority,
            }
        )

        steps   = agent_result.get("steps",  0)
        status  = agent_result.get("status", "?")
        history = loop.get_history()

        # Recopilar todos los outputs de tools
        tool_outputs = []
        for step in history:
            for action in step.get("actions", []):
                out  = action.get("output")
                tool = action.get("tool", "tool")
                ok   = action.get("success", False)
                if out is not None:
                    icon = "✓" if ok else "✗"
                    tool_outputs.append(f"{icon} [{tool}]: {str(out)[:600]}")

        # ── INTERPRETACIÓN: pedir al LLM que explique los resultados ──────────
        if tool_outputs:
            tool_data = "\n\n".join(tool_outputs)
            interp_prompt = f"""El agente ejecutó herramientas reales del sistema AI_VAULT.

TAREA ORIGINAL: {message}

RESULTADOS OBTENIDOS:
{tool_data}

Basándote ÚNICAMENTE en estos resultados reales, explica de forma clara y estructurada:
1. Qué encontraste exactamente
2. El estado actual (corriendo/caído/configurado/etc.)
3. Si hay problemas, cuáles son y qué los causa
4. Qué acciones recomiendas o ya tomaste

Responde en español, sin mostrar código Python ni dicts crudos.
Sé específico con los datos: puertos, archivos, estados, errores."""

            interp_result = await self.llm.query(
                [{"role": "user", "content": interp_prompt}],
                model_priority = model_priority,
            )

            if interp_result.get("success") and interp_result.get("content"):
                full = interp_result["content"]
                full += f"\n\n*[Agente ORAV: {steps} paso(s) — {status}]*"
            else:
                # Si falla la interpretación, mostrar raw con formato mínimo
                full = f"Resultados del agente ({steps} paso(s)):\n\n{tool_data}"

        elif agent_result.get("success") and agent_result.get("result"):
            raw  = agent_result["result"]
            full = raw if isinstance(raw, str) else str(raw)
            full += f"\n\n*[Agente ORAV: {steps} paso(s) — {status}]*"
        else:
            full = (
                f"El agente ejecutó {steps} paso(s) pero no obtuvo resultados.\n"
                f"Estado: {status}\n"
                f"Intenta reformular o usar un modelo más potente."
            )

        return {
            "success":      True,        # siempre True para mostrar lo que se encontró
            "content":      full,
            "response":     full,        # duplicado explícito — la UI usa este campo
            "model":        "agent_orav",
            "model_used":   "agent_orav",
            "agent_steps":  steps,
            "agent_status": status,
        }

    async def close(self):
        await self.llm.close()
        self.is_running = False
        self.logger.info("BrainSession '%s' cerrada", self.session_id)


def get_or_create_session(session_id: str, sessions: Dict) -> "BrainSession":
    if session_id not in sessions:
        sessions[session_id] = BrainSession(session_id)
    return sessions[session_id]
