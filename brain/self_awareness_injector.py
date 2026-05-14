"""
SELF_AWARENESS_INJECTOR.PY — Inyección permanente de autoconciencia en el chat

Garantiza que CADA interacción /chat incluya estado de autoconciencia real,
no solo el endpoint /chat/introspectivo. Extrae datos reales de:
  - MetaCognitionCore (capacidades, gaps, stress, resiliencia)
  - SistemaConscienciaLimitaciones (carencias conocidas)
  - AOS (goals activos, proactivos)
  - BrainOrchestrator (último tick, subsistemas)

El bloque inyectado es compacto (<800 tokens) para no degradar rendimiento.
Cache de 30s para evitar overhead en conversaciones rápidas.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

log = logging.getLogger("self_awareness_injector")


@dataclass
class AwarenessBlock:
    """Bloque de autoconciencia listo para inyectar en system prompt."""
    text: str
    token_estimate: int
    cached_at: float
    source: str  # "real", "fallback", "error"


class SelfAwarenessInjector:
    """
    Inyecta autoconciencia real en CADA system prompt del chat.
    Degradación graceful: si un subsistema falla, continúa con lo disponible.
    """

    CACHE_TTL = 30.0  # segundos

    def __init__(self):
        self._cache: Optional[AwarenessBlock] = None
        self._cache_time: float = 0.0

    def inject(self, orchestrator=None, meta_core=None,
               consciencia_limitaciones=None) -> AwarenessBlock:
        """
        Genera el bloque de autoconciencia usando datos reales.
        Usa cache si es reciente.
        """
        # Cache check
        now = time.time()
        if self._cache and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        # Intentar obtener datos reales
        try:
            block = self._build_real_block(orchestrator, meta_core, consciencia_limitaciones)
            self._cache = block
            self._cache_time = now
            return block
        except Exception as e:
            log.warning(f"Error construyendo awareness block real: {e}")
            block = self._build_fallback_block(str(e))
            self._cache = block
            self._cache_time = now
            return block

    def _build_real_block(self, orchestrator, meta_core,
                          consciencia_limitaciones) -> AwarenessBlock:
        """Construye bloque con datos reales de los subsistemas."""
        sections = []
        sections.append("### ESTADO DE AUTOCONCIENCIA (datos reales)")

        # 1. Capacidades
        caps_info = self._extract_capabilities(meta_core)
        if caps_info:
            sections.append("**Capacidades:**")
            sections.append(caps_info)

        # 2. Gaps
        gaps_info = self._extract_gaps(meta_core)
        if gaps_info:
            sections.append("**Brechas de conocimiento:**")
            sections.append(gaps_info)

        # 3. Limitaciones conocidas
        limits_info = self._extract_limitations(consciencia_limitaciones)
        if limits_info:
            sections.append("**Limitaciones conocidas:**")
            sections.append(limits_info)

        # 4. Resiliencia y stress
        resilience_info = self._extract_resilience(meta_core)
        if resilience_info:
            sections.append("**Estado operativo:**")
            sections.append(resilience_info)

        # 5. AOS goals
        aos_info = self._extract_aos(orchestrator)
        if aos_info:
            sections.append("**Objetivos activos:**")
            sections.append(aos_info)

        text = "\n".join(sections)
        token_estimate = len(text.split()) * 1.3  # Estimación rough

        return AwarenessBlock(
            text=text,
            token_estimate=int(token_estimate),
            cached_at=time.time(),
            source="real",
        )

    def _extract_capabilities(self, meta_core) -> str:
        """Extrae información de capacidades del MetaCognitionCore."""
        if not meta_core:
            return "MetaCognitionCore no disponible"

        report = meta_core.get_self_awareness_report()
        caps = report.get("capabilities_summary", {})

        reliable = caps.get("reliable", 0)
        unreliable = caps.get("unreliable", 0)
        total = caps.get("total", 0)

        lines = []
        if reliable > 0:
            lines.append(f"  Confiables: {reliable}/{total}")
        if unreliable > 0:
            lines.append(f"  No confiables: {unreliable}/{total}")
            # Listar capacidades no confiables
            for name, cap in meta_core.self_model.capabilities.items():
                if not cap.is_reliable():
                    lines.append(f"    - {name}: confianza={cap.confidence:.2f}, evidencia={cap.evidence_count}")

        return "\n".join(lines) if lines else "Sin datos de capacidades"

    def _extract_gaps(self, meta_core) -> str:
        """Extrae brechas de conocimiento."""
        if not meta_core:
            return ""

        gaps = meta_core.self_model.known_gaps
        open_gaps = [g for g in gaps if g.resolution_status == "open"]

        if not open_gaps:
            return "Sin brechas abiertas"

        lines = []
        for g in open_gaps[:5]:  # Top 5
            lines.append(f"  - [{g.domain}] {g.description[:80]} (impacto={g.impact_if_known:.1f})")

        if len(open_gaps) > 5:
            lines.append(f"  ... y {len(open_gaps) - 5} más")

        return "\n".join(lines)

    def _extract_limitations(self, consciencia_limitaciones) -> str:
        """Extrae limitaciones del SistemaConscienciaLimitaciones."""
        if not consciencia_limitaciones:
            return ""

        try:
            if hasattr(consciencia_limitaciones, 'known_capabilities'):
                known = consciencia_limitaciones.known_capabilities
                if isinstance(known, dict):
                    weak = [k for k, v in known.items()
                            if isinstance(v, (int, float)) and v < 0.5]
                    if weak:
                        return "\n".join(f"  - {w}" for w in weak[:5])
            return ""
        except Exception:
            return ""

    def _extract_resilience(self, meta_core) -> str:
        """Extrae estado de resiliencia y stress."""
        if not meta_core:
            return ""

        model = meta_core.self_model
        return (f"  Modo: {model.resilience_mode}, "
                f"Stress: {model.stress_level:.2f}, "
                f"Riesgo unknowns: {meta_core.get_unknown_unknowns_risk():.2f}")

    def _extract_aos(self, orchestrator) -> str:
        """Extrae información del AOS si está disponible."""
        if not orchestrator or not orchestrator.aos:
            return ""

        try:
            status = orchestrator.aos.status()
            pending = status.get("pending", 0)
            executed = status.get("executed", 0)
            proactive = status.get("proactive_running", False)

            lines = [f"  Pendientes: {pending}, Ejecutados: {executed}"]
            if proactive:
                lines.append("  Loop proactivo: ACTIVO")
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_fallback_block(self, error: str) -> AwarenessBlock:
        """Bloque de fallback cuando los subsistemas no están disponibles."""
        text = (
            "### ESTADO DE AUTOCONCIENCIA (fallback)\n"
            "Los subsistemas de autoconciencia no están disponibles actualmente.\n"
            f"Error: {error[:100]}\n"
            "ADVERTENCIA: Puedo estar dando respuestas sin conocimiento completo "
            "de mis limitaciones actuales."
        )
        return AwarenessBlock(
            text=text,
            token_estimate=int(len(text.split()) * 1.3),
            cached_at=time.time(),
            source="error",
        )

    def format_for_injection(self, block: AwarenessBlock) -> str:
        """Formatea el bloque para inyección directa en system prompt."""
        return f"\n\n{block.text}\n\nNOTA: Responde honestamente basándote en estos datos reales. No inventes información."


# ─── Singleton ─────────────────────────────────────────────────────────────────

_injector: Optional[SelfAwarenessInjector] = None

def get_injector() -> SelfAwarenessInjector:
    global _injector
    if _injector is None:
        _injector = SelfAwarenessInjector()
    return _injector
