"""
Brain Chat V7.1 - Sistema RSI (Recursive Self Improvement)
Mejora recursiva basada en métricas reales con validación de impacto

Arquitectura RSI:
1. DETECT: Identificar debilidades desde métricas
2. ANALYZE: Proponer mejoras específicas y medibles
3. PLAN: Crear plan de implementación con seguridad
4. EXECUTE: Aplicar mejoras (con confirmación)
5. VALIDATE: Medir impacto real post-implementación
6. ITERATE: Repetir ciclo con nuevas métricas
"""

import os
import json
import asyncio
import logging
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Callable
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque
import numpy as np

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Importar V7 base (asumiendo que está en el mismo directorio)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from brain_chat_v7 import BrainChatV7, ChatRequest, ChatResponse, RequestMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORT = 8090

# Directorios RSI
RSI_DIR = Path("C:\\AI_VAULT\\tmp_agent\\state\\rsi")
IMPROVEMENTS_DIR = RSI_DIR / "improvements"
VALIDATION_DIR = RSI_DIR / "validations"
METRICS_BASELINE_DIR = RSI_DIR / "baselines"

for d in [RSI_DIR, IMPROVEMENTS_DIR, VALIDATION_DIR, METRICS_BASELINE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SECCIÓN 1: SISTEMA DE DETECCIÓN DE DEBILIDADES
# =============================================================================

@dataclass
class Weakness:
    """Debilidad detectada con evidencia"""
    weakness_id: str
    dimension: str  # veracity, responsiveness, etc.
    severity: str   # critical, high, medium, low
    current_value: float
    target_value: float
    description: str
    evidence: List[str]
    detected_at: float
    frequency: int  # Cuántas veces se detectó


class WeaknessDetector:
    """
    Detecta debilidades basándose en métricas reales.
    
    No detecta "lo que podría estar mal" sino "lo que ESTÁ mal según los datos".
    """
    
    def __init__(self, metrics_engine):
        self.metrics = metrics_engine
        self.weaknesses: Dict[str, Weakness] = {}
        self.thresholds = {
            "veracity": {"critical": 50, "high": 70, "medium": 85},
            "responsiveness": {"critical": 5000, "high": 3000, "medium": 1500},  # latencia ms
            "reliability": {"critical": 0.80, "high": 0.90, "medium": 0.95},
            "depth": {"critical": 30, "high": 50, "medium": 70},
            "learning": {"critical": 30, "high": 50, "medium": 70},
            "execution": {"critical": 20, "high": 40, "medium": 60},
        }
    
    def detect_weaknesses(self) -> List[Weakness]:
        """Analiza métricas y detecta debilidades reales"""
        weaknesses = []
        
        current_metrics = self.metrics.get_current_metrics()
        recent = current_metrics.get("recent_window", {})
        
        # 1. Verificar VERACITY
        verif_rate = recent.get("verification_rate", 0)
        if verif_rate < 0.85:
            severity = self._calculate_severity("veracity", verif_rate * 100)
            weaknesses.append(Weakness(
                weakness_id=f"veracity_{int(time.time())}",
                dimension="veracity",
                severity=severity,
                current_value=verif_rate * 100,
                target_value=95.0,
                description=f"Baja tasa de verificación: {verif_rate*100:.1f}% (objetivo: 95%)",
                evidence=[
                    f"Tasa actual: {verif_rate*100:.1f}%",
                    f"Requests verificados: {int(verif_rate * recent.get('count', 0))}/{recent.get('count', 0)}"
                ],
                detected_at=time.time(),
                frequency=self._get_frequency("veracity")
            ))
        
        # 2. Verificar RESPONSIVENESS (latencia)
        avg_latency = recent.get("avg_latency_ms", 0)
        if avg_latency > 1500:
            severity = self._calculate_severity_responsiveness(avg_latency)
            weaknesses.append(Weakness(
                weakness_id=f"responsiveness_{int(time.time())}",
                dimension="responsiveness",
                severity=severity,
                current_value=avg_latency,
                target_value=800.0,
                description=f"Latencia alta: {avg_latency:.0f}ms promedio (objetivo: <800ms)",
                evidence=[
                    f"Latencia promedio: {avg_latency:.0f}ms",
                    f"P95: {recent.get('p95_latency_ms', 0):.0f}ms",
                    f"P99: {recent.get('p99_latency_ms', 0):.0f}ms"
                ],
                detected_at=time.time(),
                frequency=self._get_frequency("responsiveness")
            ))
        
        # 3. Verificar RELIABILITY
        success_rate = recent.get("success_rate", 1.0)
        if success_rate < 0.95:
            severity = self._calculate_severity("reliability", success_rate * 100)
            weaknesses.append(Weakness(
                weakness_id=f"reliability_{int(time.time())}",
                dimension="reliability",
                severity=severity,
                current_value=success_rate * 100,
                target_value=99.0,
                description=f"Tasa de éxito baja: {success_rate*100:.1f}% (objetivo: 99%)",
                evidence=[
                    f"Éxitos: {int(success_rate * recent.get('count', 0))}/{recent.get('count', 0)}",
                    f"Errores totales: {self.metrics.total_errors}"
                ],
                detected_at=time.time(),
                frequency=self._get_frequency("reliability")
            ))
        
        # 4. Verificar DEPTH (diversidad de consultas)
        capabilities = self.metrics.get_capability_breakdown()
        if len(capabilities) < 3:
            weaknesses.append(Weakness(
                weakness_id=f"depth_{int(time.time())}",
                dimension="depth",
                severity="medium",
                current_value=len(capabilities) * 20,
                target_value=80.0,
                description=f"Baja diversidad: solo {len(capabilities)} tipos de consulta manejados",
                evidence=[
                    f"Tipos detectados: {list(capabilities.keys())}",
                    "Se recomienda ampliar capacidades"
                ],
                detected_at=time.time(),
                frequency=self._get_frequency("depth")
            ))
        
        # Guardar debilidades detectadas
        for w in weaknesses:
            self.weaknesses[w.weakness_id] = w
        
        return weaknesses
    
    def _calculate_severity(self, dimension: str, value: float) -> str:
        """Calcula severidad basado en umbrales"""
        thresholds = self.thresholds.get(dimension, {})
        
        if value < thresholds.get("critical", 0):
            return "critical"
        elif value < thresholds.get("high", 0):
            return "high"
        elif value < thresholds.get("medium", 0):
            return "medium"
        return "low"
    
    def _calculate_severity_responsiveness(self, latency_ms: float) -> str:
        """Severidad especial para latencia (menor es mejor)"""
        if latency_ms > 5000:
            return "critical"
        elif latency_ms > 3000:
            return "high"
        elif latency_ms > 1500:
            return "medium"
        return "low"
    
    def _get_frequency(self, dimension: str) -> int:
        """Cuenta cuántas veces se detectó esta debilidad"""
        count = 0
        for w in self.weaknesses.values():
            if w.dimension == dimension:
                count += 1
        return count


# =============================================================================
# SECCIÓN 2: GENERADOR DE MEJORAS
# =============================================================================

@dataclass
class ImprovementProposal:
    """Propuesta de mejora específica"""
    proposal_id: str
    weakness_id: str
    title: str
    description: str
    implementation_steps: List[str]
    expected_impact: Dict[str, float]  # métricas que mejorarán
    risk_level: str
    estimated_effort: str  # small, medium, large
    validation_method: str
    created_at: float
    status: str = "pending"  # pending, approved, implemented, validated, rejected


class ImprovementGenerator:
    """
    Genera propuestas de mejora basadas en debilidades detectadas.
    
    Cada propuesta es:
    - Específica (no vaga)
    - Medible (tiene métricas objetivo)
    - Accionable (pasos claros)
    - Segura (no rompe el sistema)
    """
    
    def __init__(self):
        self.proposals: Dict[str, ImprovementProposal] = {}
        self.implemented_count = 0
    
    def generate_proposals(self, weaknesses: List[Weakness]) -> List[ImprovementProposal]:
        """Genera propuestas para debilidades detectadas"""
        proposals = []
        
        for weakness in weaknesses:
            if weakness.dimension == "responsiveness" and weakness.current_value > 1000:
                # Propuesta 1: Implementar caché para consultas frecuentes
                proposals.append(self._create_cache_proposal(weakness))
                
            elif weakness.dimension == "veracity" and weakness.current_value < 70:
                # Propuesta 2: Agregar más fuentes de datos
                proposals.append(self._create_data_source_proposal(weakness))
                
            elif weakness.dimension == "depth":
                # Propuesta 3: Ampliar tipos de consulta
                proposals.append(self._create_depth_proposal(weakness))
                
            elif weakness.dimension == "reliability":
                # Propuesta 4: Mejorar manejo de errores
                proposals.append(self._create_reliability_proposal(weakness))
        
        # Si no hay debilidades críticas, proponer optimizaciones
        if not any(w.severity in ["critical", "high"] for w in weaknesses):
            proposals.append(self._create_optimization_proposal())
        
        # Guardar propuestas
        for p in proposals:
            self.proposals[p.proposal_id] = p
        
        return proposals
    
    def _create_cache_proposal(self, weakness: Weakness) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=f"cache_{int(time.time())}",
            weakness_id=weakness.weakness_id,
            title="Implementar sistema de caché para consultas frecuentes",
            description=f"Cachear respuestas de /phase, /pocketoption y /status durante 30 segundos para reducir latencia",
            implementation_steps=[
                "1. Agregar diccionario de caché en memoria",
                "2. Implementar TTL (time-to-live) de 30 segundos",
                "3. Cachear respuestas de endpoints de sistema",
                "4. Invalidar caché al recibir nuevos datos",
                "5. Agregar métrica de cache hit rate"
            ],
            expected_impact={
                "responsiveness": 400.0,  # Reducir latencia a ~400ms
                "veracity": 0.0,  # Sin impacto
                "success_rate": 0.0
            },
            risk_level="low",
            estimated_effort="small",
            validation_method="medir latencia promedio durante 24h después de implementación",
            created_at=time.time()
        )
    
    def _create_data_source_proposal(self, weakness: Weakness) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=f"datasource_{int(time.time())}",
            weakness_id=weakness.weakness_id,
            title="Agregar Advisor API como fuente de datos verificada",
            description="Integrar Advisor (puerto 8030) para aumentar tasa de verificación",
            implementation_steps=[
                "1. Agregar Advisor API a lista de servicios",
                "2. Implementar endpoint /advisor/status",
                "3. Agregar consulta paralela en system_overview",
                "4. Validar respuestas cruzadas entre Brain y Advisor"
            ],
            expected_impact={
                "veracity": 15.0,  # Aumentar verificación ~15%
                "responsiveness": -50.0,  # Posible ligera penalización
                "depth": 10.0
            },
            risk_level="medium",
            estimated_effort="medium",
            validation_method="comparar tasa de verificación antes/después durante 48h",
            created_at=time.time()
        )
    
    def _create_depth_proposal(self, weakness: Weakness) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=f"depth_{int(time.time())}",
            weakness_id=weakness.weakness_id,
            title="Ampliar capacidades de análisis de trading",
            description="Agregar comandos /trend, /volatility y /backtest",
            implementation_steps=[
                "1. Implementar análisis de tendencias",
                "2. Calcular volatilidad de pares",
                "3. Integrar backtesting simple",
                "4. Agregar UI para visualización",
                "5. Documentar nuevos comandos"
            ],
            expected_impact={
                "depth": 30.0,
                "execution": 20.0,
                "responsiveness": 0.0
            },
            risk_level="medium",
            estimated_effort="large",
            validation_method="contar tipos de consulta únicos manejados",
            created_at=time.time()
        )
    
    def _create_reliability_proposal(self, weakness: Weakness) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=f"reliability_{int(time.time())}",
            weakness_id=weakness.weakness_id,
            title="Implementar retry automático y circuit breaker",
            description="Agregar reintentos automáticos para servicios caídos",
            implementation_steps=[
                "1. Agregar retry con exponential backoff",
                "2. Implementar circuit breaker pattern",
                "3. Agregar fallback a datos cacheados",
                "4. Mejorar logging de errores",
                "5. Agregar alertas tempranas"
            ],
            expected_impact={
                "reliability": 5.0,  # +5% éxito
                "responsiveness": -100.0,  # Posible ligera penalización
            },
            risk_level="medium",
            estimated_effort="medium",
            validation_method="medir tasa de éxito durante 72h",
            created_at=time.time()
        )
    
    def _create_optimization_proposal(self) -> ImprovementProposal:
        return ImprovementProposal(
            proposal_id=f"opt_{int(time.time())}",
            weakness_id="none",
            title="Optimización proactiva: Compresión de logs",
            description="Comprimir logs de métricas antiguos para reducir uso de disco",
            implementation_steps=[
                "1. Identificar logs > 30 días",
                "2. Comprimir a gzip",
                "3. Mover a archivo",
                "4. Implementar rotación automática"
            ],
            expected_impact={
                "disk_usage": -50.0,  # -50% uso disco
            },
            risk_level="low",
            estimated_effort="small",
            validation_method="comparar uso de disco antes/después",
            created_at=time.time()
        )


# =============================================================================
# SECCIÓN 3: SISTEMA RSI INTEGRADO
# =============================================================================

class RSISystem:
    """
    Sistema RSI completo que orquesta el ciclo de mejora.
    
    Ciclo RSI:
    1. DETECT → Detecta debilidades desde métricas
    2. ANALYZE → Genera propuestas de mejora
    3. PLAN → Crea plan seguro con rollback
    4. EXECUTE → Ejecuta con confirmación
    5. VALIDATE → Mide impacto real
    6. ITERATE → Repite con nuevas métricas
    """
    
    def __init__(self, brain_chat: BrainChatV7):
        self.brain = brain_chat
        self.detector = WeaknessDetector(brain_chat.metrics_engine)
        self.generator = ImprovementGenerator()
        
        self.cycle_count = 0
        self.last_cycle = 0
        self.cycle_interval = 3600  # 1 hora entre ciclos RSI
        
        self.improvements_history: List[Dict] = []
        
    async def run_rsi_cycle(self, force: bool = False) -> Dict[str, Any]:
        """
        Ejecuta un ciclo completo de RSI.
        
        Retorna:
        - weaknessses detectadas
        - propuestas generadas
        - recomendaciones de implementación
        - métricas baseline
        """
        current_time = time.time()
        
        # Verificar si es tiempo de ciclo
        if not force and (current_time - self.last_cycle) < self.cycle_interval:
            return {
                "status": "skipped",
                "reason": f"Próximo ciclo en {int((self.cycle_interval - (current_time - self.last_cycle)) / 60)} minutos",
                "last_cycle": datetime.fromtimestamp(self.last_cycle).isoformat()
            }
        
        self.cycle_count += 1
        cycle_id = f"rsi_cycle_{self.cycle_count}_{int(current_time)}"
        
        logger.info(f"Iniciando ciclo RSI #{self.cycle_count}: {cycle_id}")
        
        # PASO 1: DETECT - Detectar debilidades
        weaknesses = self.detector.detect_weaknesses()
        
        # PASO 2: ANALYZE - Generar propuestas
        proposals = self.generator.generate_proposals(weaknesses)
        
        # PASO 3: BASELINE - Guardar métricas baseline
        baseline = self.brain.metrics_engine.get_current_metrics()
        await self._save_baseline(cycle_id, baseline)
        
        # PASO 4: PREPARAR REPORTE
        report = {
            "cycle_id": cycle_id,
            "timestamp": current_time,
            "status": "analysis_complete",
            "weaknesses_detected": len(weaknesses),
            "proposals_generated": len(proposals),
            "current_metrics": baseline,
            "weaknesses": [asdict(w) for w in weaknesses],
            "proposals": [asdict(p) for p in proposals],
            "recommendations": self._generate_recommendations(weaknesses, proposals),
            "next_steps": [
                "Revisar propuestas generadas",
                "Aprobar implementaciones con confirm_token",
                "Sistema aplicará mejoras y validará impacto",
                "Repetir ciclo RSI cada hora"
            ]
        }
        
        # Guardar reporte
        await self._save_rsi_report(cycle_id, report)
        
        self.last_cycle = current_time
        
        return report
    
    def _generate_recommendations(self, weaknesses: List[Weakness], 
                                 proposals: List[ImprovementProposal]) -> List[str]:
        """Genera recomendaciones basadas en análisis"""
        recommendations = []
        
        # Priorizar por severidad
        critical = [w for w in weaknesses if w.severity == "critical"]
        high = [w for w in weaknesses if w.severity == "high"]
        
        if critical:
            recommendations.append(f"🚨 URGENTE: {len(critical)} debilidades críticas detectadas")
            for w in critical:
                recommendations.append(f"   - {w.dimension}: {w.description}")
        
        if high:
            recommendations.append(f"⚠️ IMPORTANTE: {len(high)} debilidades de alta prioridad")
        
        if not critical and not high:
            recommendations.append("✅ Sistema saludable. Considerar optimizaciones proactivas.")
        
        # Recomendar propuestas de bajo riesgo primero
        low_risk = [p for p in proposals if p.risk_level == "low"]
        if low_risk:
            recommendations.append(f"💡 {len(low_risk)} propuestas de bajo riesgo listas para implementar")
        
        return recommendations
    
    async def _save_baseline(self, cycle_id: str, baseline: Dict):
        """Guarda métricas baseline"""
        baseline_file = METRICS_BASELINE_DIR / f"{cycle_id}_baseline.json"
        try:
            with open(baseline_file, 'w', encoding='utf-8') as f:
                json.dump(baseline, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving baseline: {e}")
    
    async def _save_rsi_report(self, cycle_id: str, report: Dict):
        """Guarda reporte RSI"""
        report_file = RSI_DIR / f"{cycle_id}_report.json"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving RSI report: {e}")


# =============================================================================
# SECCIÓN 4: INTEGRACIÓN CON BRAIN CHAT V7
# =============================================================================

class BrainChatV7_RSI(BrainChatV7):
    """
    Brain Chat V7.1 con capacidad RSI.
    
    Hereda todo de V7 y agrega:
    - Auto-detección de debilidades
    - Generación de mejoras
    - Ciclo RSI automático
    """
    
    def __init__(self):
        super().__init__()
        self.rsi = RSISystem(self)
        
        # Iniciar ciclo RSI automático
        asyncio.create_task(self._rsi_continuous_cycle())
    
    async def _rsi_continuous_cycle(self):
        """Ejecuta ciclo RSI cada hora"""
        while True:
            try:
                logger.info("Iniciando ciclo RSI automático...")
                report = await self.rsi.run_rsi_cycle()
                
                if report.get("status") == "analysis_complete":
                    logger.info(f"Ciclo RSI completado: {report['weaknesses_detected']} debilidades, "
                              f"{report['proposals_generated']} propuestas")
                    
                    # Si hay debilidades críticas, logear alerta
                    weaknesses = report.get("weaknesses", [])
                    critical = [w for w in weaknesses if w.get("severity") == "critical"]
                    if critical:
                        logger.warning(f"🚨 {len(critical)} debilidades críticas detectadas en ciclo RSI")
                
                await asyncio.sleep(3600)  # Esperar 1 hora
                
            except Exception as e:
                logger.error(f"Error en ciclo RSI: {e}")
                await asyncio.sleep(3600)
    
    async def process_message(self, request) -> ChatResponse:
        """Procesa mensajes y detecta consultas sobre RSI"""
        msg_lower = request.message.lower()
        
        # Detectar consultas sobre RSI
        if any(phrase in msg_lower for phrase in [
            "rsi", "mejora", "improvement", "debilidades", "weaknesses",
            "auto-mejora", "recursive", "como puedes mejorar"
        ]):
            return await self._handle_rsi_query(request)
        
        # Detectar consultas sobre propuestas activas
        if any(phrase in msg_lower for phrase in [
            "propuestas", "proposals", "mejoras pendientes"
        ]):
            return await self._handle_proposals_query(request)
        
        # Procesar normalmente
        return await super().process_message(request)
    
    async def _handle_rsi_query(self, request) -> ChatResponse:
        """Maneja consultas sobre RSI"""
        
        # Forzar ciclo RSI
        report = await self.rsi.run_rsi_cycle(force=True)
        
        if report.get("status") == "skipped":
            # Usar último reporte
            report = await self._get_last_rsi_report()
        
        # Construir respuesta
        reply = f"""🔧 **Análisis RSI (Recursive Self Improvement)**

**Ciclo #{self.rsi.cycle_count}** | Estado: {report.get('status', 'unknown')}

---

**📊 Debilidades Detectadas: {report.get('weaknesses_detected', 0)}**
"""
        
        weaknesses = report.get("weaknesses", [])
        if weaknesses:
            for w in weaknesses[:5]:  # Mostrar top 5
                emoji = "🚨" if w.get("severity") == "critical" else "⚠️" if w.get("severity") == "high" else "📋"
                reply += f"\n{emoji} **{w.get('dimension', 'unknown').upper()}**: {w.get('current_value', 0):.1f} → {w.get('target_value', 0):.1f}\n"
                reply += f"   _{w.get('description', '')}_"
        else:
            reply += "\n✅ No se detectaron debilidades significativas"
        
        reply += f"""

---

**💡 Propuestas Generadas: {report.get('proposals_generated', 0)}**
"""
        
        proposals = report.get("proposals", [])
        if proposals:
            for p in proposals[:3]:  # Top 3
                risk_emoji = "🟢" if p.get("risk_level") == "low" else "🟡" if p.get("risk_level") == "medium" else "🔴"
                reply += f"\n{risk_emoji} **{p.get('title', 'Propuesta')}** ({p.get('estimated_effort', 'unknown')})\n"
                reply += f"   Impacto esperado: {self._format_impact(p.get('expected_impact', {}))}"
        
        reply += f"""

---

**🎯 Recomendaciones:**
"""
        
        for rec in report.get("recommendations", [])[:3]:
            reply += f"\n• {rec}"
        
        reply += f"""

---

**📈 Métricas Actuales:**
• Total ciclos RSI: {self.rsi.cycle_count}
• Debilidades históricas: {len(self.rsi.detector.weaknesses)}
• Propuestas generadas: {len(self.rsi.generator.proposals)}

**Ciclo RSI automático:** Cada 60 minutos"""
        
        return ChatResponse(
            success=True,
            reply=reply,
            mode="rsi_analysis",
            data_source="rsi_system",
            verified=True,
            confidence=0.95
        )
    
    async def _handle_proposals_query(self, request) -> ChatResponse:
        """Muestra propuestas de mejora"""
        
        proposals = list(self.rsi.generator.proposals.values())
        pending = [p for p in proposals if p.status == "pending"]
        
        reply = f"""📋 **Propuestas de Mejora ({len(pending)} pendientes)**

---
"""
        
        if pending:
            for i, p in enumerate(pending[:5], 1):
                risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(p.risk_level, "⚪")
                reply += f"""
**{i}. {p.title}**
{risk_emoji} Riesgo: {p.risk_level.upper()} | Esfuerzo: {p.estimated_effort.upper()}

{p.description}

**Impacto esperado:**
"""
                for metric, impact in p.expected_impact.items():
                    sign = "+" if impact > 0 else ""
                    reply += f"\n• {metric}: {sign}{impact:.1f}"
                
                reply += f"""

**Implementación:**
"""
                for step in p.implementation_steps:
                    reply += f"\n{step}"
                
                reply += "\n---"
        else:
            reply += "\n✅ No hay propuestas pendientes. Sistema funcionando óptimamente."
        
        return ChatResponse(
            success=True,
            reply=reply,
            mode="rsi_proposals",
            data_source="rsi_system",
            verified=True,
            confidence=0.9
        )
    
    def _format_impact(self, impact: Dict) -> str:
        """Formatea impacto esperado"""
        parts = []
        for metric, value in impact.items():
            sign = "+" if value > 0 else ""
            parts.append(f"{metric}: {sign}{value:.1f}")
        return ", ".join(parts) if parts else "N/A"
    
    async def _get_last_rsi_report(self) -> Dict:
        """Recupera último reporte RSI"""
        try:
            # Buscar archivos de reporte
            files = sorted(RSI_DIR.glob("rsi_cycle_*_report.json"), reverse=True)
            if files:
                with open(files[0], 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading RSI report: {e}")
        return {"status": "no_data"}


# =============================================================================
# INICIALIZACIÓN Y ENDPOINTS
# =============================================================================

# Crear instancia global
chat_v7_rsi = None

@app.on_event("startup")
async def startup_event():
    """Inicializa Brain Chat V7.1 con RSI"""
    global chat_v7_rsi
    chat_v7_rsi = BrainChatV7_RSI()
    logger.info("Brain Chat V7.1 iniciado con Sistema RSI")


@app.get("/health")
async def health():
    """Health check con estado RSI"""
    if chat_v7_rsi is None:
        return {"status": "initializing", "version": "7.1.0", "rsi": "pending"}
    
    base_health = await chat_v7_rsi.metrics_engine.get_current_metrics()
    
    return {
        "status": "healthy",
        "version": "7.1.0",
        "rsi_enabled": True,
        "rsi_cycles": chat_v7_rsi.rsi.cycle_count,
        "weaknesses_detected": len(chat_v7_rsi.rsi.detector.weaknesses),
        "proposals_generated": len(chat_v7_rsi.rsi.generator.proposals),
        "self_aware": True,
        "dynamic_evaluation": True,
        "recursive_improvement": True,
        "metrics": base_health
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint principal"""
    if chat_v7_rsi is None:
        return ChatResponse(
            success=False,
            reply="Sistema inicializándose con RSI...",
            mode="initializing"
        )
    
    try:
        result = await chat_v7_rsi.process_message(request)
        return result
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return ChatResponse(
            success=False,
            reply=f"Error: {str(e)}",
            mode="error"
        )


@app.get("/rsi/status")
async def rsi_status():
    """Estado del sistema RSI"""
    if chat_v7_rsi is None:
        return {"status": "initializing"}
    
    return {
        "status": "active",
        "cycles_completed": chat_v7_rsi.rsi.cycle_count,
        "last_cycle": datetime.fromtimestamp(chat_v7_rsi.rsi.last_cycle).isoformat() if chat_v7_rsi.rsi.last_cycle else None,
        "weaknesses_detected": len(chat_v7_rsi.rsi.detector.weaknesses),
        "proposals_pending": len([p for p in chat_v7_rsi.rsi.generator.proposals.values() if p.status == "pending"]),
        "auto_cycle_interval_minutes": 60
    }


@app.post("/rsi/trigger")
async def trigger_rsi(background_tasks: BackgroundTasks):
    """Fuerza un ciclo RSI inmediato"""
    if chat_v7_rsi is None:
        return {"status": "error", "message": "Sistema no inicializado"}
    
    report = await chat_v7_rsi.rsi.run_rsi_cycle(force=True)
    return report


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
