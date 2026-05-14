"""
UNIFIED_CHAT_ROUTER.PY — Router inteligente unificado para el Brain V9.1

Convierte /chat en la ENTRADA UNICA al brain. Clasifica la intención del usuario
y la dirige automáticamente al subsistema correcto, sin que el usuario tenga que
saber si usar /chat, /agent, /chat/introspectivo, etc.

Rutas:
  GENERAL_CONVERSATION → LLM directo (rápido)
  SELF_AWARENESS       → Introspectivo + MetaCognitionCore
  DASHBOARD_ANALYSIS   → DashboardReader + recomendaciones
  LEARNING_REQUEST     → EvolucionContinua + LearningValidator
  GOAL_MANAGEMENT      → AOS (Sistema de Objetivos Autónomos)
  AGENT_TASK           → Agente ORAV con tools
"""

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

log = logging.getLogger("unified_chat_router")


# ─── Clasificación de Intención ────────────────────────────────────────────────

class IntentCategory(str, Enum):
    GENERAL_CONVERSATION = "general_conversation"
    SELF_AWARENESS = "self_awareness"
    DASHBOARD_ANALYSIS = "dashboard_analysis"
    LEARNING_REQUEST = "learning_request"
    GOAL_MANAGEMENT = "goal_management"
    AGENT_TASK = "agent_task"


@dataclass
class RoutingDecision:
    """Resultado de la clasificación de intención."""
    category: IntentCategory
    confidence: float
    matched_patterns: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Patrones de Detección ─────────────────────────────────────────────────────

SELF_AWARENESS_PATTERNS = [
    r"(?i)(qué\s+puedes?\s+hacer|what\s+can\s+you\s+do)",
    r"(?i)(qué\s+no\s+puedes|what\s+can'?t\s+you)",
    r"(?i)(cuáles?\s+son\s+tus\s+(?:capacidades|limitaciones|carencias))",
    r"(?i)(conoces?\s+tus\s+(?:gaps|brechas|limitaciones))",
    r"(?i)(autoconciencia|self.?awareness|introspección|introspect)",
    r"(?i)(qué\s+sabes\s+de\s+ti\s+mismo|dime\s+de\s+ti)",
    r"(?i)(cómo\s+estás?\s+internamente|estado\s+interno)",
    r"(?i)(qué\s+te\s+falta|what\s+are\s+you\s+missing)",
    r"(?i)(conoce\s+tus\s+limites|know\s+your\s+limits)",
    r"(?i)(qué\s+necesitas?\s+mejorar|what\s+needs\s+improvement)",
    r"(?i)(stress\s+level|nivel\s+de\s+estrés)",
    r"(?i)(fase\s+de\s+autonomía|autonomy\s+phase)",
    r"(?i)(capacidades?\s+confiable|reliable\s+capabilities?)",
]

DASHBOARD_PATTERNS = [
    r"(?i)(analiza\s+el\s+dashboard|analyze\s+the\s+dashboard)",
    r"(?i)(dashboard|panel\s+de\s+control)",
    r"(?i)(estado\s+del\s+sistema|system\s+status)",
    r"(?i)(health\s+check|chequeo\s+de\s+salud)",
    r"(?i)(métricas?\s+del\s+(?:brain|sistema)|brain\s+metrics?)",
    r"(?i)(rsi|resilience|resiliencia)",
    r"(?i)(servicios?\s+caídos?|services?\s+down)",
    r"(?i)(qué\s+muestra\s+el\s+dashboard|what\s+does\s+the\s+dashboard\s+show)",
    r"(?i)(necesita\s+atención|needs\s+attention)",
    r"(?i)(oportunidades?\s+de\s+mejora|improvement\s+opportunit)",
]

LEARNING_PATTERNS = [
    r"(?i)(aprende|r?learn|estudia|study)",
    r"(?i)(ingesta|ingest|curar?\s+información|curate)",
    r"(?i)(nuevo\s+conocimiento|new\s+knowledge)",
    r"(?i)(investiga|research|explora|explore)",
    r"(?i)(enseña|teach|entrena|train)",
    r"(?i)(valida\s+(?:lo\s+)?aprendido|validate\s+learning)",
    r"(?i)(ciclo\s+de\s+aprendizaje|learning\s+cycle)",
    r"(?i)(brecha\s+de\s+conocimiento|knowledge\s+gap)",
    r"(?i)(actualiza\s+base\s+de\s+conocimiento|update\s+knowledge\s+base)",
]

GOAL_PATTERNS = [
    r"(?i)(crea\s+(?:un\s+)?objetivo|create\s+(?:a\s+)?goal)",
    r"(?i)(objetivos?\s+activos?|active\s+goals?)",
    r"(?i)(aos|sistema\s+de\s+objetivos|goal\s+system)",
    r"(?i)(prioriza|prioritize|planifica|plan)",
    r"(?i)(qué\s+estás?\s+haciendo|what\s+are\s+you\s+doing)",
    r"(?i)(progreso\s+de\s+objetivos|goal\s+progress)",
    r"(?i)(ejecuta\s+objetivo|execute\s+goal)",
    r"(?i)(lista\s+de\s+tareas|task\s+list)",
]

AGENT_PATTERNS = [
    r"(?i)(ejecuta|execute|corre|run\s+)",
    r"(?i)(revisa?\s+(?:el\s+)?(?:archivo|file|código|code|log))",
    r"(?i)(diagnostica|diagnose|debug|depura)",
    r"(?i)(modifica|modify|edita|edit|cambia|change)",
    r"(?i)(instala|install|actualiza|update)",
    r"(?i)(escanea|scan|busca|search|encuentra|find)",
    r"(?i)(verifica|verify|chequea|check)",
    r"(?i)(backtest|trading|estrategia|strategy)",
    r"(?i)(\.py|\.json|\.md|\.csv)",
    r"(?i)(puerto|port|servicio|service|proceso|process)",
    r"(?i)(lee\s+(?:el\s+)?archivo|read\s+(?:the\s+)?file)",
    r"(?i)(lista\s+(?:el\s+)?(?:directorio|directory|dir))",
    r"(?i)(grep|rglob|find\s+in\s+code)",
]


class UnifiedChatRouter:
    """
    Router inteligente que clasifica la intención del usuario y dirige
    al subsistema correcto del brain.
    """

    def __init__(self):
        self._compiled = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compila todos los patrones regex para rendimiento."""
        groups = {
            IntentCategory.SELF_AWARENESS: SELF_AWARENESS_PATTERNS,
            IntentCategory.DASHBOARD_ANALYSIS: DASHBOARD_PATTERNS,
            IntentCategory.LEARNING_REQUEST: LEARNING_PATTERNS,
            IntentCategory.GOAL_MANAGEMENT: GOAL_PATTERNS,
            IntentCategory.AGENT_TASK: AGENT_PATTERNS,
        }
        for category, patterns in groups.items():
            self._compiled[category] = [re.compile(p) for p in patterns]

    def classify(self, message: str) -> RoutingDecision:
        """
        Clasifica el mensaje del usuario en una categoría de intención.

        Estrategia: cada categoría produce un score basado en matches.
        La categoría con mayor score gana. Si no hay matches, es conversación general.
        """
        scores: Dict[IntentCategory, float] = {}
        matched_by_category: Dict[IntentCategory, List[str]] = {}

        for category, compiled_patterns in self._compiled.items():
            matches = []
            for pattern in compiled_patterns:
                if pattern.search(message):
                    matches.append(pattern.pattern)
            if matches:
                # Score ponderado: más matches = más confianza,
                # pero con diminishing returns para evitar sesgo hacia categorías con más patrones
                scores[category] = len(matches) / (1.0 + 0.1 * len(compiled_patterns))
                matched_by_category[category] = matches

        if not scores:
            return RoutingDecision(
                category=IntentCategory.GENERAL_CONVERSATION,
                confidence=0.9,
                matched_patterns=[],
                metadata={"reason": "no_pattern_matched"},
            )

        # Seleccionar la categoría con mayor score
        best_category = max(scores, key=scores.get)
        total_score = sum(scores.values())
        confidence = scores[best_category] / total_score if total_score > 0 else 0.5

        return RoutingDecision(
            category=best_category,
            confidence=min(0.95, confidence + 0.3),  # Boost base confidence
            matched_patterns=matched_by_category.get(best_category, []),
            metadata={
                "all_scores": {k.value: v for k, v in scores.items()},
            },
        )

    def enrich_system_prompt(self, base_prompt: str, decision: RoutingDecision,
                              self_awareness_block: str = "",
                              dashboard_block: str = "") -> str:
        """
        Enriquece el system prompt según la categoría detectada.

        Cada categoría añade contexto específico que mejora la calidad
        de la respuesta del LLM.
        """
        parts = [base_prompt]

        if decision.category == IntentCategory.SELF_AWARENESS:
            if self_awareness_block:
                parts.append("\n\n### AUTOCONCIENCIA ACTIVADA\n" + self_awareness_block)
            parts.append(
                "\n\nINSTRUCCIONES: El usuario pregunta sobre ti mismo. "
                "Responde HONESTAMENTE usando los datos reales de tu estado interno. "
                "NO inventes capacidades que no tienes. Si un dato muestra 0 o null, admítelo."
            )

        elif decision.category == IntentCategory.DASHBOARD_ANALYSIS:
            if dashboard_block:
                parts.append("\n\n### ANÁLISIS DE DASHBOARD\n" + dashboard_block)
            parts.append(
                "\n\nINSTRUCCIONES: Analiza el dashboard con profundidad. "
                "Identifica problemas, oportunidades de mejora, y acciones concretas. "
                "Prioriza por impacto."
            )

        elif decision.category == IntentCategory.LEARNING_REQUEST:
            parts.append(
                "\n\nINSTRUCCIONES: El usuario quiere aprender o ingerir conocimiento. "
                "Propón un plan de aprendizaje concreto con pasos verificables. "
                "Si hay gaps abiertos, priorízalos."
            )

        elif decision.category == IntentCategory.GOAL_MANAGEMENT:
            parts.append(
                "\n\nINSTRUCCIONES: El usuario habla de objetivos y planificación. "
                "Reporta el estado actual de tus goals, sugiere nuevos si es relevante, "
                "y propone priorización basada en utilidad."
            )

        elif decision.category == IntentCategory.AGENT_TASK:
            parts.append(
                "\n\nINSTRUCCIONES: El usuario pide una acción concreta. "
                "Ejecuta con el ciclo ORAV si es complejo, o responde directamente si es simple. "
                "Verifica resultados antes de confirmar."
            )

        return "\n".join(parts)

    def should_use_agent(self, decision: RoutingDecision) -> bool:
        """Determina si la decisión requiere el agente ORAV."""
        return decision.category in (
            IntentCategory.AGENT_TASK,
            IntentCategory.DASHBOARD_ANALYSIS,
        ) and decision.confidence > 0.5


# ─── Singleton ─────────────────────────────────────────────────────────────────

_router: Optional[UnifiedChatRouter] = None

def get_router() -> UnifiedChatRouter:
    global _router
    if _router is None:
        _router = UnifiedChatRouter()
    return _router
