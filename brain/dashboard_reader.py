"""
DASHBOARD_READER.PY — Lectura y análisis profundo del dashboard

Permite al agente "ver" su propio dashboard, analizar métricas, detectar
problemas y generar recomendaciones accionables. Convierte los 6 endpoints
del dashboard en un análisis consolidado que el chat puede usar como contexto.

Endpoints leídos:
  /health, /brain/health, /brain/metrics, /brain/rsi,
  /autonomy/status, /upgrade/status
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

log = logging.getLogger("dashboard_reader")


@dataclass
class ServiceIssue:
    """Problema detectado en un servicio."""
    service: str
    severity: str  # "critical", "warning", "info"
    description: str
    recommendation: str


@dataclass
class DashboardAnalysis:
    """Análisis consolidado del dashboard."""
    overall_health: str  # "healthy", "degraded", "critical"
    health_score: float  # 0.0 - 1.0
    active_issues: List[ServiceIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    needs_attention: List[str] = field(default_factory=list)
    improvement_opportunities: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    analyzed_at: float = 0.0

    def to_text(self) -> str:
        """Convierte el análisis en texto legible para inyección en prompt."""
        parts = [f"### ANÁLISIS DE DASHBOARD (salud: {self.overall_health}, score: {self.health_score:.1%})"]

        if self.active_issues:
            parts.append("\n**Problemas activos:**")
            for issue in self.active_issues:
                parts.append(f"  [{issue.severity.upper()}] {issue.service}: {issue.description}")
                parts.append(f"    → {issue.recommendation}")

        if self.needs_attention:
            parts.append("\n**Requiere atención:**")
            for item in self.needs_attention:
                parts.append(f"  - {item}")

        if self.improvement_opportunities:
            parts.append("\n**Oportunidades de mejora:**")
            for opp in self.improvement_opportunities:
                parts.append(f"  - {opp}")

        if self.recommendations:
            parts.append("\n**Recomendaciones:**")
            for rec in self.recommendations:
                parts.append(f"  → {rec}")

        return "\n".join(parts)


class DashboardReader:
    """
    Lee los endpoints del dashboard y genera un análisis consolidado.
    Diseñado para ser invocado desde el chat como contexto, o como tool del agente.
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8090"):
        self.base_url = base_url.rstrip("/")
        self._cache: Optional[DashboardAnalysis] = None
        self._cache_time: float = 0.0
        self.CACHE_TTL = 15.0  # segundos

    async def analyze(self, force_refresh: bool = False) -> DashboardAnalysis:
        """
        Ejecuta análisis completo del dashboard.
        Usa cache si es reciente y no se fuerza refresh.
        """
        now = time.time()
        if not force_refresh and self._cache and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        # Recolectar datos de todos los endpoints
        raw_data = await self._collect_all_endpoints()

        # Analizar
        analysis = self._analyze_data(raw_data)
        analysis.analyzed_at = now

        self._cache = analysis
        self._cache_time = now
        return analysis

    def analyze_from_data(self, data: Dict[str, Any]) -> DashboardAnalysis:
        """
        Analiza datos del dashboard sin hacer HTTP calls.
        Útil para tests o cuando los datos ya están disponibles.
        """
        return self._analyze_data(data)

    async def _collect_all_endpoints(self) -> Dict[str, Any]:
        """Recolecta datos de todos los endpoints del dashboard."""
        results = {}
        endpoints = [
            ("health", "/health"),
            ("brain_health", "/brain/health"),
            ("brain_metrics", "/brain/metrics"),
            ("brain_rsi", "/brain/rsi"),
            ("autonomy_status", "/autonomy/status"),
            ("upgrade_status", "/upgrade/status"),
        ]

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                for name, path in endpoints:
                    try:
                        resp = await client.get(f"{self.base_url}{path}")
                        if resp.status_code == 200:
                            results[name] = resp.json()
                        else:
                            results[name] = {"error": f"HTTP {resp.status_code}", "_available": False}
                    except Exception as e:
                        results[name] = {"error": str(e), "_available": False}
        except ImportError:
            # httpx no disponible — usar fallback
            results["_fallback"] = True
            log.warning("httpx no disponible, usando análisis sin datos en vivo")

        return results

    def _analyze_data(self, raw_data: Dict[str, Any]) -> DashboardAnalysis:
        """Analiza los datos recolectados y genera insights."""
        issues: List[ServiceIssue] = []
        recommendations: List[str] = []
        needs_attention: List[str] = []
        opportunities: List[str] = []
        health_scores: List[float] = []

        # 1. Health check general
        health = raw_data.get("health") or {}
        if health.get("status") == "healthy":
            health_scores.append(1.0)
        elif health.get("status") == "initializing":
            health_scores.append(0.5)
            issues.append(ServiceIssue(
                service="brain_server",
                severity="warning",
                description="Servidor en inicialización",
                recommendation="Esperar a que complete el startup",
            ))
        elif health.get("status") in ("startup_failed", "unhealthy"):
            health_scores.append(0.0)
            issues.append(ServiceIssue(
                service="brain_server",
                severity="critical",
                description=f"Servidor con problemas: {health.get('error', 'unknown')}",
                recommendation="Verificar logs y reiniciar si es necesario",
            ))

        # 2. Brain health
        brain_health = raw_data.get("brain_health") or {}
        if isinstance(brain_health, dict):
            services = brain_health.get("services", {})
            if isinstance(services, dict):
                for svc_name, svc_data in services.items():
                    if isinstance(svc_data, dict):
                        if not svc_data.get("healthy", True):
                            health_scores.append(0.3)
                            issues.append(ServiceIssue(
                                service=f"brain.{svc_name}",
                                severity="critical",
                                description=f"Servicio {svc_name} no saludable",
                                recommendation=f"Reiniciar servicio {svc_name} o verificar configuración",
                            ))
                        else:
                            health_scores.append(1.0)

        # 3. Brain metrics
        metrics = raw_data.get("brain_metrics") or {}
        if isinstance(metrics, dict):
            errors = metrics.get("errors", {})
            if isinstance(errors, dict):
                error_rate = errors.get("rate_24h", 0)
                if error_rate > 0.1:
                    health_scores.append(0.4)
                    issues.append(ServiceIssue(
                        service="brain.errors",
                        severity="warning",
                        description=f"Tasa de errores alta: {error_rate:.1%}",
                        recommendation="Investigar causas de errores y aplicar correcciones",
                    ))

        # 4. RSI (Resilience and Strategic Insights)
        rsi = raw_data.get("brain_rsi") or {}
        if isinstance(rsi, dict):
            gaps = rsi.get("gaps", [])
            if isinstance(gaps, list) and len(gaps) > 3:
                opportunities.append(
                    f"RSI detecta {len(gaps)} gaps estratégicos — priorizar los de mayor impacto"
                )

        # 5. Autonomy status
        autonomy = raw_data.get("autonomy_status") or {}
        if isinstance(autonomy, dict):
            phase = autonomy.get("phase", "unknown")
            if phase in ("init", "monitor"):
                opportunities.append(
                    f"Fase de autonomía actual: {phase} — hay margen significativo de avance"
                )

        # 6. Upgrade status
        upgrade = raw_data.get("upgrade_status") or {}
        if isinstance(upgrade, dict):
            if upgrade.get("sandbox_pending"):
                needs_attention.append(
                    "Hay cambios en sandbox pendientes de aprobación"
                )

        # 7. Errores de endpoints
        unavailable = [k for k, v in raw_data.items()
                       if isinstance(v, dict) and v.get("_available") is False]
        if unavailable:
            for ep in unavailable:
                health_scores.append(0.5)
                needs_attention.append(f"Endpoint {ep} no disponible")

        # Calcular score general
        avg_health = sum(health_scores) / max(1, len(health_scores)) if health_scores else 0.5

        # Determinar estado general
        if avg_health >= 0.8:
            overall = "healthy"
        elif avg_health >= 0.5:
            overall = "degraded"
        else:
            overall = "critical"

        # Generar recomendaciones adicionales
        if not recommendations:
            if overall == "healthy":
                recommendations.append("Sistema saludable — enfocarse en crecimiento y aprendizaje")
            elif overall == "degraded":
                recommendations.append("Atender warnings antes de que escalen a critical")

        return DashboardAnalysis(
            overall_health=overall,
            health_score=avg_health,
            active_issues=issues,
            recommendations=recommendations,
            needs_attention=needs_attention,
            improvement_opportunities=opportunities,
            raw_data=raw_data,
        )


# ─── Singleton ─────────────────────────────────────────────────────────────────

_reader: Optional[DashboardReader] = None

def get_dashboard_reader(base_url: str = "http://127.0.0.1:8090") -> DashboardReader:
    global _reader
    if _reader is None:
        _reader = DashboardReader(base_url)
    return _reader
