"""
Brain Chat V9 — agent/loop.py
Ciclo agente ORAV: Observe → Reason → Act → Verify
Basado en el diseño de V8.1 (OpenCode 2026-03-21).
Diferencia clave vs V8.0: este ES un agente, no un chatbot con tools.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from brain_v9.core.llm import LLMManager


# ─── Estructuras ──────────────────────────────────────────────────────────────
@dataclass
class Observation:
    timestamp: str
    source: str
    data: Any
    metadata: Dict = field(default_factory=dict)


@dataclass
class ReasoningResult:
    thought: str
    plan: List[str]
    tool_calls: List[Dict]
    confidence: float
    needs_clarification: bool = False


@dataclass
class ActionResult:
    tool: str
    success: bool
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class VerificationResult:
    verified: bool
    score: float           # 0.0 – 1.0
    issues: List[str]
    next_action: str       # "done" | "retry" | "escalate"


@dataclass
class AgentStep:
    step_id: int
    observation: Observation
    reasoning:   ReasoningResult
    actions:     List[ActionResult]
    verification: VerificationResult
    timestamp:   str = field(default_factory=lambda: datetime.now().isoformat())


# ─── AgentLoop ────────────────────────────────────────────────────────────────
class AgentLoop:
    """
    Ciclo agente autónomo ORAV.
    Diseñado para tareas multi-paso que requieren planificación,
    ejecución de tools y verificación de resultados.
    """

    MAX_STEPS    = 50
    MAX_RETRIES  = 5

    def __init__(self, llm: LLMManager, tools: Optional["ToolExecutor"] = None):
        self.llm    = llm
        self.tools  = tools or ToolExecutor()
        self.logger = logging.getLogger("AgentLoop")
        self.history: List[AgentStep] = []

    # ── Entry point ───────────────────────────────────────────────────────────
    async def run(self, task: str, context: Optional[Dict] = None) -> Dict:
        """
        Ejecuta una tarea completa usando el ciclo ORAV.

        Returns:
            {success, result, steps, summary}
        """
        self.logger.info("AgentLoop iniciado para tarea: %s", task[:80])
        self.history.clear()
        context = context or {}
        step_id  = 0
        result   = None

        for step_id in range(self.MAX_STEPS):
            self.logger.debug("ORAV paso %d/%d", step_id + 1, self.MAX_STEPS)

            # 1. OBSERVE
            obs = await self._observe(task, context, step_id)

            # 2. REASON
            reasoning = await self._reason(task, obs, context)

            if reasoning.needs_clarification:
                return {
                    "success": False,
                    "result":  reasoning.thought,
                    "steps":   step_id + 1,
                    "status":  "needs_clarification",
                }

            # 3. ACT
            actions = await self._act(reasoning.tool_calls)

            # 4. VERIFY
            verification = await self._verify(task, actions, reasoning)

            step = AgentStep(step_id, obs, reasoning, actions, verification)
            self.history.append(step)

            # Actualizar contexto con resultados
            context["last_actions"]    = [a.__dict__ for a in actions]
            context["last_verification"] = verification.__dict__

            if verification.next_action == "done":
                result = self._extract_result(actions)
                break
            elif verification.next_action == "escalate":
                return {
                    "success": False,
                    "result":  "La tarea requiere intervención humana.",
                    "steps":   step_id + 1,
                    "status":  "escalated",
                    "issues":  verification.issues,
                }
            # "retry" → siguiente iteración

        summary = await self._summarize(task, self.history)
        return {
            "success": bool(result is not None),
            "result":  result,
            "steps":   step_id + 1,
            "summary": summary,
            "status":  "completed" if result else "max_steps_reached",
        }

    # ── Fases ORAV ────────────────────────────────────────────────────────────
    async def _observe(self, task: str, context: Dict, step: int) -> Observation:
        """Reúne toda la información disponible relevante para la tarea."""
        data = {
            "task":          task,
            "step":          step,
            "previous_actions": context.get("last_actions", []),
            "environment":   {
                "timestamp":    datetime.now().isoformat(),
                "tools_available": self.tools.list_tools(),
            },
        }
        return Observation(
            timestamp = datetime.now().isoformat(),
            source    = "environment",
            data      = data,
        )

    async def _reason(self, task: str, obs: Observation, context: Dict) -> ReasoningResult:
        """Usa el LLM para planificar los próximos pasos."""

        # Listar tools con ejemplos de uso
        tool_examples = {
            "check_port":           '{"tool": "check_port", "args": {"port": 8070}}',
            "list_processes":       '{"tool": "list_processes", "args": {"filter_name": "python.exe"}}',
            "check_url":            '{"tool": "check_url", "args": {"url": "http://localhost:8070/health"}}',
            "run_command":          '{"tool": "run_command", "args": {"cmd": "netstat -ano | findstr 8070"}}',
            "list_directory":       '{"tool": "list_directory", "args": {"path": "C:\\\\AI_VAULT\\\\tmp_agent"}}',
            "search_files":         '{"tool": "search_files", "args": {"directory": "C:\\\\AI_VAULT", "pattern": "*.py", "content_search": "dashboard"}}',
            "read_file":            '{"tool": "read_file", "args": {"path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\brain_v9\\\\main.py"}}',
            "get_system_info":      '{"tool": "get_system_info", "args": {}}',
            "find_dashboard_files": '{"tool": "find_dashboard_files", "args": {}}',
            "analyze_python":       '{"tool": "analyze_python", "args": {"path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\brain_v9\\\\main.py"}}',
            "find_in_code":         '{"tool": "find_in_code", "args": {"path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\brain_v9\\\\main.py", "query": "dashboard"}}',
            "check_syntax":         '{"tool": "check_syntax", "args": {"path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\brain_v9\\\\main.py"}}',
            "start_dashboard":      '{"tool": "start_dashboard", "args": {}}',
            "start_brain_server":   '{"tool": "start_brain_server", "args": {}}',
            "get_dashboard_data":   '{"tool": "get_dashboard_data", "args": {"endpoint": "status"}}',
        }

        available = self.tools.list_tools()
        tools_lines = []
        for name in available:
            if name in self.tools._tools:
                desc = self.tools._tools[name]['description']
                example = tool_examples.get(name, f'{{"tool": "{name}", "args": {{}} }}')
                tools_lines.append(f"- {name}: {desc}\n  Ejemplo: {example}")
        tools_with_examples = "\n".join(tools_lines)

        prev = ""
        if context.get("last_actions"):
            prev = "\n\nACCIONES ANTERIORES:\n" + "\n".join(
                f"  [{a['tool']}] {'OK' if a['success'] else 'FALLO'}: {str(a.get('output',''))[:120]}"
                for a in context["last_actions"]
            )

        prompt = f"""Eres Brain V9, agente autónomo del ecosistema AI_VAULT en Windows.
Tu tarea es: {task}
Paso actual: {obs.data['step'] + 1}

HERRAMIENTAS DISPONIBLES (usa EXACTAMENTE estos nombres):
{tools_with_examples}

RUTA BASE DEL SISTEMA: C:\\AI_VAULT
SISTEMA OPERATIVO: Windows
{prev}

INSTRUCCIONES:
- Usa SOLO los nombres de tools listados arriba (exacto, sin cambios)
- Para verificar puertos: usa "check_port" con el número de puerto
- Para verificar si un servicio web responde: usa "check_url"
- Para buscar dashboards: usa "find_dashboard_files"
- Para iniciar el dashboard en puerto 8070: usa "start_dashboard" (sin argumentos)
- Para iniciar Brain Chat V9: usa "start_brain_server" (sin argumentos)
- Para CONSULTAR datos del dashboard: usa "get_dashboard_data" con endpoint="status", "roadmap/v2", etc.
- Para comandos Windows: usa "run_command"
- Si el usuario pide iniciar/levantar/arrancar un servicio, USA la tool específica de inicio
- Si ya tienes suficiente información para responder, devuelve tool_calls vacío

Responde SOLO con este JSON (sin markdown, sin texto adicional):
{{
  "thought": "qué voy a hacer y por qué",
  "plan": ["paso 1", "paso 2"],
  "tool_calls": [
    {{"tool": "nombre_exacto_tool", "args": {{"parametro": "valor"}}}}
  ],
  "confidence": 0.85,
  "needs_clarification": false
}}"""

        result = await self.llm.query(
            [{"role": "user", "content": prompt}],
            model_priority=context.get("model_priority", "ollama"),
        )

        if not result.get("success"):
            self.logger.warning("LLM no disponible para razonamiento")
            return ReasoningResult(
                thought="LLM no disponible",
                plan=[], tool_calls=[], confidence=0.0,
            )

        try:
            import json
            content = result["content"].strip()
            # Limpiar markdown si el LLM lo incluyó
            if "```" in content:
                parts = content.split("```")
                for p in parts:
                    p = p.strip()
                    if p.startswith("json"):
                        p = p[4:]
                    p = p.strip()
                    if p.startswith("{"):
                        content = p
                        break
            # Encontrar el JSON aunque haya texto alrededor
            start = content.find("{")
            end   = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]

            data = json.loads(content)
            return ReasoningResult(
                thought             = data.get("thought", ""),
                plan                = data.get("plan", []),
                tool_calls          = data.get("tool_calls", []),
                confidence          = float(data.get("confidence", 0.7)),
                needs_clarification = data.get("needs_clarification", False),
            )
        except Exception as e:
            self.logger.warning("Error parseando JSON del LLM: %s | contenido: %s", e, result["content"][:200])
            return ReasoningResult(
                thought   = result["content"][:300],
                plan      = [],
                tool_calls = [],
                confidence = 0.3,
            )

    async def _act(self, tool_calls: List[Dict]) -> List[ActionResult]:
        """
        Ejecuta tools en PARALELO aprovechando los 12 CPUs disponibles.
        Antes: herramientas en secuencia (lento).
        Ahora: todas las herramientas simultáneamente (rápido).
        """
        if not tool_calls:
            return []

        async def _execute_one(call: Dict) -> ActionResult:
            tool = call.get("tool", "")
            args = call.get("args", {})
            t0   = asyncio.get_event_loop().time()
            try:
                output = await self.tools.execute(tool, **args)
                ms     = (asyncio.get_event_loop().time() - t0) * 1000
                self.logger.debug("Tool %s OK (%.0fms)", tool, ms)
                return ActionResult(tool=tool, success=True,
                                    output=output, duration_ms=ms)
            except Exception as e:
                ms = (asyncio.get_event_loop().time() - t0) * 1000
                self.logger.warning("Tool %s FAIL: %s", tool, e)
                return ActionResult(tool=tool, success=False,
                                    output=None, error=str(e), duration_ms=ms)

        # Ejecutar todas las tools en paralelo (asyncio.gather)
        results = await asyncio.gather(
            *[_execute_one(call) for call in tool_calls],
            return_exceptions=False
        )
        return list(results)

    async def _verify(self, task: str, actions: List[ActionResult], reasoning: ReasoningResult) -> VerificationResult:
        """Verifica si los resultados satisfacen la tarea."""
        if not actions:
            # Sin acciones = tarea completada o sin herramientas
            return VerificationResult(verified=True, score=1.0, issues=[], next_action="done")

        failed  = [a for a in actions if not a.success]
        ok      = [a for a in actions if a.success]
        score   = len(ok) / len(actions) if actions else 0.0
        issues  = [f"{a.tool}: {a.error}" for a in failed]

        if score >= 0.6:
            return VerificationResult(verified=True, score=score, issues=issues, next_action="done")
        elif score >= 0.2:
            return VerificationResult(verified=False, score=score, issues=issues, next_action="retry")
        else:
            # Solo escalar si hay 0 tools disponibles o error crítico
            if not actions:
                return VerificationResult(verified=True, score=1.0, issues=[], next_action="done")
            return VerificationResult(verified=False, score=score, issues=issues, next_action="escalate")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _extract_result(self, actions: List[ActionResult]) -> Any:
        successful = [a.output for a in actions if a.success and a.output is not None]
        if not successful:
            return None
        return successful[-1] if len(successful) == 1 else successful

    async def _summarize(self, task: str, history: List[AgentStep]) -> str:
        if not history:
            return "Sin pasos ejecutados."
        ok    = sum(1 for s in history for a in s.actions if a.success)
        fail  = sum(1 for s in history for a in s.actions if not a.success)
        tools = list({a.tool for s in history for a in s.actions})
        return (
            f"Tarea completada en {len(history)} paso(s). "
            f"Acciones: {ok} exitosas, {fail} fallidas. "
            f"Tools usadas: {', '.join(tools) or 'ninguna'}."
        )

    def get_history(self) -> List[Dict]:
        return [
            {
                "step":        s.step_id,
                "thought":     s.reasoning.thought[:100],
                "actions":     [{"tool": a.tool, "success": a.success, "output": a.output} for a in s.actions],
                "verified":    s.verification.verified,
                "next_action": s.verification.next_action,
            }
            for s in self.history
        ]


# ─── ToolExecutor ─────────────────────────────────────────────────────────────
class ToolExecutor:
    """Registro y ejecutor de herramientas para el agente."""

    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self.logger = logging.getLogger("ToolExecutor")

    def register(self, name: str, func: Callable, description: str, category: str = "general"):
        self._tools[name] = {"func": func, "description": description, "category": category}
        self.logger.debug("Tool registrada: %s", name)

    async def execute(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool desconocida: {name}")
        fn = self._tools[name]["func"]
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        return fn(**kwargs)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def descriptions(self) -> Dict[str, str]:
        return {n: d["description"] for n, d in self._tools.items()}

    def get_for_llm(self) -> str:
        cats: Dict[str, List[str]] = {}
        for n, d in self._tools.items():
            cats.setdefault(d["category"], []).append(f"  - {n}: {d['description']}")
        return "\n".join(
            f"[{cat.upper()}]\n" + "\n".join(tools)
            for cat, tools in sorted(cats.items())
        )
