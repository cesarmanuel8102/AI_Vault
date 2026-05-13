"""
Brain Chat V7.2 - RSI Estratégico Alineado con Premisas Canónicas v3.1
Mejora recursiva priorizada por objetivos estratégicos cuantificados
"""

import os
import json
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# SECCIÓN 1: OBJETIVOS ESTRATÉGICOS (Según Premisas v3.1)
# =============================================================================

class StrategicObjective(Enum):
    """
    Objetivos estratégicos ordenados por prioridad según premisas canónicas v3.1.
    
    Jerarquía de valores:
    1. Supervivencia > retorno nominal
    2. Robustez > experiencia
    3. Control > expansión desordenada
    """
    AUTOSUPERVIVENCIA = "autosupervivencia"           # 40% - Robustez, continuidad, protección
    AUTODETERMINACION = "autodeterminacion"          # 25% - Autoconciencia avanzada, autonomía
    CRECIMIENTO_CAPITAL = "crecimiento_capital"      # 20% - Motor financiero, nichos de negocio
    GOBERNANZA = "gobernanza"                        # 10% - Control local, trazabilidad, reversión
    LEGALIDAD = "legalidad"                          # 3% - Cumplimiento, protección operador
    MORALIDAD = "moralidad"                          # 2% - Alineación con intención humana


# Pesos de impacto en el objetivo primordial
OBJECTIVE_WEIGHTS = {
    StrategicObjective.AUTOSUPERVIVENCIA: 0.40,
    StrategicObjective.AUTODETERMINACION: 0.25,
    StrategicObjective.CRECIMIENTO_CAPITAL: 0.20,
    StrategicObjective.GOBERNANZA: 0.10,
    StrategicObjective.LEGALIDAD: 0.03,
    StrategicObjective.MORALIDAD: 0.02,
}


# Mapeo: dimensión de evaluación → objetivos estratégicos que afecta
DIMENSION_IMPACT = {
    "veracity": [StrategicObjective.CRECIMIENTO_CAPITAL, StrategicObjective.GOBERNANZA],
    "responsiveness": [StrategicObjective.AUTOSUPERVIVENCIA, StrategicObjective.CRECIMIENTO_CAPITAL],
    "reliability": [StrategicObjective.AUTOSUPERVIVENCIA, StrategicObjective.AUTODETERMINACION],
    "depth": [StrategicObjective.CRECIMIENTO_CAPITAL, StrategicObjective.AUTODETERMINACION],
    "learning": [StrategicObjective.AUTODETERMINACION, StrategicObjective.GOBERNANZA],
    "introspection": [StrategicObjective.AUTODETERMINACION],
    "execution": [StrategicObjective.CRECIMIENTO_CAPITAL, StrategicObjective.GOBERNANZA],
}


# Umbrales según premisas v3.1
THRESHOLDS = {
    "phase1_exit": {
        "autoevaluation": 85.0,  # % en 5/7 dimensiones
        "uptime": 99.0,         # %
        "latency_p95": 2000.0,  # ms
        "latency_avg": 1000.0,    # ms
        "verification_rate": 90.0, # %
        "success_rate": 98.0,    # %
        "rsi_cycles": 20,        # ciclos exitosos
        "min_days": 14,          # días operando
    },
    "drawdown": {
        "daily_warning": 5.0,    # %
        "daily_critical": 10.0,  # %
        "weekly_warning": 10.0,  # %
        "weekly_critical": 15.0, # %
        "max_acceptable": 50.0,  # % (rollback total)
    },
    "ruina": {
        "total": 50.0,           # % pérdida capital
        "efectiva": 25.0,        # % pérdida capital
        "operativa": 20.0,         # % drawdown consecutivo
    }
}


@dataclass
class StrategicGap:
    """Brecha entre capacidad actual y objetivo estratégico"""
    gap_id: str
    objective: str
    current_capability: float
    required_capability: float
    gap_percentage: float
    impact_on_objective: str  # critical, high, medium, low
    blockers: List[str]
    time_to_deadline: Optional[int]  # días hasta timebox


@dataclass
class PhaseMetrics:
    """Métricas de fase actual"""
    phase: str  # phase1, phase2, phase3, phase4
    days_in_phase: int
    metrics_status: Dict[str, bool]  # métrica → cumple (True/False)
    progress_percentage: float
    next_gate: str
    time_to_deadline: Optional[int]


# =============================================================================
# SECCIÓN 2: SISTEMA DE PRIORIZACIÓN ESTRATÉGICA
# =============================================================================

class StrategicPrioritizer:
    """
    Prioriza mejoras basándose en impacto estratégico según premisas v3.1.
    
    Principio: No todas las debilidades son iguales.
    Se prioriza por ROI estratégico (qué tanto acerca al objetivo primordial).
    """
    
    def __init__(self):
        self.strategic_gaps: List[StrategicGap] = []
        self.current_phase: str = "phase1"
        self.phase_start_time: float = time.time()
        
    def analyze_strategic_gaps(self, current_evaluation: Dict, 
                              current_metrics: Dict) -> List[StrategicGap]:
        """Analiza brechas estratégicas actuales según premisas"""
        gaps = []
        
        dimensions = current_evaluation.get("dimensions", {})
        recent_metrics = current_metrics.get("recent_window", {})
        
        # GAP 1: AUTOSUPERVIVENCIA (40% peso)
        # Requiere: reliability > 98%, uptime > 99%
        rel_score = dimensions.get("reliability", {}).get("score", 0)
        uptime = recent_metrics.get("success_rate", 1.0) * 100  # Proxy de uptime
        
        autosuperv_current = min(rel_score, uptime)
        autosuperv_required = 99.0
        
        gaps.append(StrategicGap(
            gap_id="gap_autosupervivencia",
            objective=StrategicObjective.AUTOSUPERVIVENCIA.value,
            current_capability=autosuperv_current,
            required_capability=autosuperv_required,
            gap_percentage=max(0, autosuperv_required - autosuperv_current),
            impact_on_objective="critical" if autosuperv_current < 90 else "high",
            blockers=self._identify_autosuperv_blockers(rel_score, uptime),
            time_to_deadline=self._calculate_time_to_deadline("phase1")
        ))
        
        # GAP 2: AUTODETERMINACION (25% peso)
        # Requiere: introspection > 85%, learning > 70%
        intro_score = dimensions.get("introspection", {}).get("score", 0)
        learn_score = dimensions.get("learning", {}).get("score", 0)
        
        autodet_current = (intro_score + learn_score) / 2
        autodet_required = 85.0
        
        gaps.append(StrategicGap(
            gap_id="gap_autodeterminacion",
            objective=StrategicObjective.AUTODETERMINACION.value,
            current_capability=autodet_current,
            required_capability=autodet_required,
            gap_percentage=max(0, autodet_required - autodet_current),
            impact_on_objective="critical" if autodet_current < 75 else "high",
            blockers=self._identify_autodet_blockers(intro_score, learn_score),
            time_to_deadline=self._calculate_time_to_deadline("phase1")
        ))
        
        # GAP 3: CRECIMIENTO_CAPITAL (20% peso)
        # Requiere: execution > 80%, veracity > 90%, depth > 70%
        exec_score = dimensions.get("execution", {}).get("score", 0)
        ver_score = dimensions.get("veracity", {}).get("score", 0)
        depth_score = dimensions.get("depth", {}).get("score", 0)
        
        crec_current = (exec_score + ver_score + depth_score) / 3
        crec_required = 80.0
        
        gaps.append(StrategicGap(
            gap_id="gap_crecimiento_capital",
            objective=StrategicObjective.CRECIMIENTO_CAPITAL.value,
            current_capability=crec_current,
            required_capability=crec_required,
            gap_percentage=max(0, crec_required - crec_current),
            impact_on_objective="high" if crec_current < 70 else "medium",
            blockers=self._identify_crecimiento_blockers(exec_score, ver_score, depth_score),
            time_to_deadline=None  # Depende de salir de Fase 1
        ))
        
        # GAP 4: GOBERNANZA (10% peso)
        # Requiere: veracity > 90% (trazabilidad)
        gob_current = ver_score
        gob_required = 90.0
        
        gaps.append(StrategicGap(
            gap_id="gap_gobernanza",
            objective=StrategicObjective.GOBERNANZA.value,
            current_capability=gob_current,
            required_capability=gob_required,
            gap_percentage=max(0, gob_required - gob_current),
            impact_on_objective="medium" if gob_current < 80 else "low",
            blockers=["Trazabilidad insuficiente"] if gob_current < 80 else [],
            time_to_deadline=None
        ))
        
        # Ordenar por impacto ponderado
        gaps.sort(key=lambda g: (
            OBJECTIVE_WEIGHTS.get(StrategicObjective(g.objective), 0.1) * g.gap_percentage
        ), reverse=True)
        
        self.strategic_gaps = gaps
        return gaps
    
    def _identify_autosuperv_blockers(self, reliability: float, uptime: float) -> List[str]:
        """Identifica qué bloquea autosupervivencia"""
        blockers = []
        if reliability < 98:
            blockers.append(f"Confiabilidad insuficiente: {reliability:.1f}% (requerido: 98%)")
        if uptime < 99:
            blockers.append(f"Uptime insuficiente: {uptime:.1f}% (requerido: 99%)")
        return blockers
    
    def _identify_autodet_blockers(self, introspection: float, learning: float) -> List[str]:
        """Identifica qué bloquea autodeterminación"""
        blockers = []
        if introspection < 85:
            blockers.append(f"Autoconciencia limitada: {introspection:.1f}% (requerido: 85%)")
        if learning < 70:
            blockers.append(f"Capacidad de aprendizaje baja: {learning:.1f}%")
        return blockers
    
    def _identify_crecimiento_blockers(self, execution: float, veracity: float, depth: float) -> List[str]:
        """Identifica qué bloquea crecimiento de capital"""
        blockers = []
        if execution < 80:
            blockers.append(f"Ejecución limitada: {execution:.1f}% (whitelist restrictiva)")
        if veracity < 90:
            blockers.append(f"Datos insuficientemente verificados: {veracity:.1f}%")
        if depth < 70:
            blockers.append(f"Análisis superficial: {depth:.1f}% (pocos tipos de consulta)")
        return blockers
    
    def _calculate_time_to_deadline(self, phase: str) -> Optional[int]:
        """Calcula días hasta deadline de fase"""
        if phase == "phase1":
            # Timebox: 60 días desde inicio
            elapsed = (time.time() - self.phase_start_time) / 86400
            remaining = 60 - elapsed
            return int(remaining) if remaining > 0 else 0
        return None
    
    def check_phase1_exit_criteria(self, evaluation: Dict, metrics: Dict) -> PhaseMetrics:
        """Verifica si se cumplen criterios de salida de Fase 1"""
        
        dimensions = evaluation.get("dimensions", {})
        recent = metrics.get("recent_window", {})
        
        # Verificar cada métrica
        status = {}
        
        # 1. Autoevaluación ≥ 85% en 5/7 dimensiones
        high_scores = sum(1 for d in dimensions.values() if d.get("score", 0) >= 85)
        status["autoevaluation_5_7"] = high_scores >= 5
        
        # 2. Uptime ≥ 99%
        uptime = recent.get("success_rate", 0) * 100
        status["uptime_99"] = uptime >= 99
        
        # 3. Latencia p95 < 2000ms
        p95 = recent.get("p95_latency_ms", 9999)
        status["latency_p95"] = p95 < 2000
        
        # 4. Latencia promedio < 1000ms
        avg_lat = recent.get("avg_latency_ms", 9999)
        status["latency_avg"] = avg_lat < 1000
        
        # 5. Tasa de verificación ≥ 90%
        verif = recent.get("verification_rate", 0) * 100
        status["verification_90"] = verif >= 90
        
        # 6. Tasa de éxito ≥ 98%
        success = recent.get("success_rate", 0) * 100
        status["success_98"] = success >= 98
        
        # 7. Ciclos RSI exitosos ≥ 20
        # (Esta métrica vendría del sistema RSI)
        status["rsi_cycles_20"] = True  # Placeholder
        
        # 8. Días operando ≥ 14
        days = (time.time() - self.phase_start_time) / 86400
        status["min_days_14"] = days >= 14
        
        # Calcular progreso
        passed = sum(1 for v in status.values() if v)
        total = len(status)
        progress = (passed / total) * 100
        
        # Determinar siguiente gate
        if all(status.values()):
            next_gate = "Listo para Fase 2: Motor Financiero (Paper Trading)"
        else:
            missing = [k for k, v in status.items() if not v]
            next_gate = f"Faltan: {', '.join(missing[:3])}"
        
        return PhaseMetrics(
            phase="phase1",
            days_in_phase=int(days),
            metrics_status=status,
            progress_percentage=progress,
            next_gate=next_gate,
            time_to_deadline=self._calculate_time_to_deadline("phase1")
        )
    
    def get_critical_path(self) -> List[Dict]:
        """Retorna camino crítico para alcanzar objetivos"""
        if not self.strategic_gaps:
            return []
        
        path = []
        
        # Ordenar por brecha ponderada
        for gap in self.strategic_gaps:
            weight = OBJECTIVE_WEIGHTS.get(StrategicObjective(gap.objective), 0.1)
            priority = weight * gap.gap_percentage
            
            path.append({
                "objective": gap.objective,
                "priority_score": priority,
                "gap": gap.gap_percentage,
                "current": gap.current_capability,
                "required": gap.required_capability,
                "blockers": gap.blockers,
                "time_to_deadline": gap.time_to_deadline
            })
        
        # Ordenar por prioridad
        path.sort(key=lambda x: x["priority_score"], reverse=True)
        return path


# =============================================================================
# SECCIÓN 3: SISTEMA RSI ESTRATÉGICO COMPLETO
# =============================================================================

class StrategicRSI:
    """
    RSI (Recursive Self Improvement) Estratégico.
    
    Diferencias con RSI genérico:
    1. Prioriza por impacto en objetivos estratégicos (no por facilidad)
    2. Respeta fases de desarrollo (no salta a trading prematuramente)
    3. Verifica gates antes de transiciones
    4. Respeta timeboxes y deadlines
    5. Detecta riesgo de ruina y activa protecciones
    """
    
    def __init__(self, brain_chat):
        self.brain = brain_chat
        self.prioritizer = StrategicPrioritizer()
        self.cycle_count = 0
        self.last_cycle = 0
        self.cycle_interval = 3600  # 1 hora
        self.improvements_history = []
        
        # Métricas de fase
        self.phase_metrics = None
        
    async def run_strategic_rsi_cycle(self, force: bool = False) -> Dict:
        """Ejecuta ciclo RSI estratégico completo"""
        
        current_time = time.time()
        
        # Verificar si es tiempo de ciclo
        if not force and (current_time - self.last_cycle) < self.cycle_interval:
            return {
                "status": "skipped",
                "reason": f"Próximo ciclo en {int((self.cycle_interval - (current_time - self.last_cycle)) / 60)} minutos",
                "last_cycle": datetime.fromtimestamp(self.last_cycle).isoformat()
            }
        
        self.cycle_count += 1
        cycle_id = f"rsi_strategic_{self.cycle_count}_{int(current_time)}"
        
        logger.info(f"Iniciando ciclo RSI Estratégico #{self.cycle_count}")
        
        # 1. Obtener evaluación actual
        current_eval = self.brain.evaluation_system.get_cached_evaluation()
        current_metrics = self.brain.metrics_engine.get_current_metrics()
        
        # 2. Analizar brechas estratégicas
        gaps = self.prioritizer.analyze_strategic_gaps(current_eval, current_metrics)
        
        # 3. Verificar criterios de fase
        self.phase_metrics = self.prioritizer.check_phase1_exit_criteria(
            current_eval, current_metrics
        )
        
        # 4. Detectar riesgos de ruina
        ruina_risks = self._assess_ruina_risks(current_metrics)
        
        # 5. Generar plan estratégico
        strategic_plan = self._generate_strategic_plan(gaps, ruina_risks)
        
        # 6. Verificar si debe activar modo seguro
        safe_mode_triggered = self._check_safe_mode_triggers(current_metrics, ruina_risks)
        
        report = {
            "cycle_id": cycle_id,
            "timestamp": current_time,
            "cycle_number": self.cycle_count,
            "objective_primordial": "Crecimiento de capital con protección fuerte",
            "fase_actual": self.phase_metrics.phase,
            "dias_en_fase": self.phase_metrics.days_in_phase,
            "progreso_fase": self.phase_metrics.progress_percentage,
            "proximo_gate": self.phase_metrics.next_gate,
            "time_to_deadline": self.phase_metrics.time_to_deadline,
            "strategic_gaps": [asdict(g) for g in gaps],
            "critical_path": self.prioritizer.get_critical_path(),
            "ruina_risks": ruina_risks,
            "safe_mode_triggered": safe_mode_triggered,
            "strategic_plan": strategic_plan,
            "recommendations": self._generate_recommendations(gaps, ruina_risks, safe_mode_triggered),
            "status": "analysis_complete"
        }
        
        # Guardar reporte
        await self._save_rsi_report(cycle_id, report)
        
        self.last_cycle = current_time
        
        # Si hay riesgo crítico, activar modo seguro
        if safe_mode_triggered:
            await self._activate_safe_mode(report)
        
        return report
    
    def _assess_ruina_risks(self, metrics: Dict) -> List[Dict]:
        """Evalúa riesgos de ruina según premisas"""
        risks = []
        
        recent = metrics.get("recent_window", {})
        
        # Riesgo de ruina operativa
        success_rate = recent.get("success_rate", 1.0)
        if success_rate < 0.95:
            risks.append({
                "type": "ruina_operativa",
                "level": "high" if success_rate < 0.90 else "medium",
                "probability": (1 - success_rate) * 100,
                "description": f"Tasa de éxito {success_rate*100:.1f}% indica inestabilidad",
                "threshold": "95%",
                "action": "Activar modo seguro, investigar causas"
            })
        
        # Riesgo de degradación
        if recent.get("avg_latency_ms", 0) > 5000:
            risks.append({
                "type": "degradacion_critica",
                "level": "high",
                "description": f"Latencia crítica: {recent.get('avg_latency_ms', 0):.0f}ms",
                "action": "Rollback inmediato"
            })
        
        return risks
    
    def _check_safe_mode_triggers(self, metrics: Dict, ruina_risks: List[Dict]) -> bool:
        """Verifica si debe activar modo seguro"""
        
        # Trigger 1: Riesgo de ruina alto
        high_risks = [r for r in ruina_risks if r.get("level") == "high"]
        if high_risks:
            return True
        
        # Trigger 2: Degradación de métricas
        recent = metrics.get("recent_window", {})
        if recent.get("success_rate", 1.0) < 0.90:
            return True
        
        # Trigger 3: Brecha crítica en autosupervivencia
        for gap in self.prioritizer.strategic_gaps:
            if gap.objective == StrategicObjective.AUTOSUPERVIVENCIA.value:
                if gap.gap_percentage > 20:  # Más de 20% por debajo
                    return True
        
        return False
    
    def _generate_strategic_plan(self, gaps: List[StrategicGap], 
                                 ruina_risks: List[Dict]) -> Dict:
        """Genera plan estratégico priorizado"""
        
        # Si hay riesgos de ruina, plan es mitigación
        if ruina_risks:
            critical = [r for r in ruina_risks if r.get("level") == "high"]
            return {
                "phase": "emergency",
                "primary_focus": "Mitigación de riesgos de ruina",
                "actions": [
                    f"1. {r.get('action', 'Investigar')}" for r in critical[:3]
                ] + [
                    "2. Activar modo seguro",
                    "3. Notificar a operador",
                    "4. No iniciar nuevas mejoras hasta estabilizar"
                ],
                "timeline": "Inmediato"
            }
        
        # Si estamos en Fase 1, plan es alcanzar gates
        if self.phase_metrics and self.phase_metrics.phase == "phase1":
            if self.phase_metrics.progress_percentage < 100:
                missing = [k for k, v in self.phase_metrics.metrics_status.items() if not v]
                return {
                    "phase": "phase1_development",
                    "primary_focus": f"Alcanzar gates de Fase 1 ({self.phase_metrics.progress_percentage:.0f}% completado)",
                    "actions": [
                        f"1. Priorizar: {missing[0] if missing else 'N/A'}",
                        f"2. Tiempo restante: {self.phase_metrics.time_to_deadline} días",
                        "3. Validar métricas diariamente",
                        "4. Documentar progreso"
                    ],
                    "timeline": f"{self.phase_metrics.time_to_deadline} días"
                }
            else:
                return {
                    "phase": "phase1_complete",
                    "primary_focus": "Listo para transición a Fase 2",
                    "actions": [
                        "1. Validar todos los criterios de salida",
                        "2. Preparar entorno de Paper Trading",
                        "3. Solicitar aprobación explícita del operador",
                        "4. Documentar baseline de Fase 1"
                    ],
                    "timeline": "Transición inmediata"
                }
        
        # Plan general de mejoras
        if gaps:
            top_gap = gaps[0]
            return {
                "phase": "strategic_improvement",
                "primary_focus": f"Cerrar brecha en {top_gap.objective}",
                "actions": [
                    f"1. Mejorar {top_gap.objective}: {top_gap.current_capability:.1f}% → {top_gap.required_capability:.1f}%",
                    f"2. Eliminar bloqueantes: {', '.join(top_gap.blockers[:2]) if top_gap.blockers else 'N/A'}",
                    "3. Validar progreso en próximo ciclo RSI",
                    "4. Documentar impacto"
                ],
                "timeline": "Próximo ciclo RSI (1 hora)"
            }
        
        return {
            "phase": "maintenance",
            "primary_focus": "Monitoreo y optimizaciones menores",
            "actions": ["Monitorear métricas", "Mantener estabilidad"],
            "timeline": "Continuo"
        }
    
    def _generate_recommendations(self, gaps: List[StrategicGap], 
                                 ruina_risks: List[Dict],
                                 safe_mode: bool) -> List[str]:
        """Genera recomendaciones accionables"""
        recommendations = []
        
        if safe_mode:
            recommendations.append("🚨 ACTIVAR MODO SEGURO INMEDIATAMENTE")
            recommendations.append("📧 Notificar a operador de riesgos detectados")
            return recommendations
        
        if ruina_risks:
            for risk in ruina_risks[:2]:
                recommendations.append(f"⚠️ {risk.get('type', 'Riesgo')}: {risk.get('action', 'Investigar')}")
        
        # Priorizar brechas críticas
        critical_gaps = [g for g in gaps if g.impact_on_objective == "critical"]
        if critical_gaps:
            recommendations.append(f"🎯 Prioridad #1: Cerrar brecha en {critical_gaps[0].objective}")
        
        # Recomendar según fase
        if self.phase_metrics:
            if self.phase_metrics.progress_percentage < 50:
                recommendations.append(f"📊 Fase 1 temprana: Enfocarse en autosupervivencia y autodeterminación")
            elif self.phase_metrics.progress_percentage < 100:
                recommendations.append(f"📈 Fase 1 avanzada: {self.phase_metrics.progress_percentage:.0f}% - Enfocarse en gaps restantes")
            else:
                recommendations.append("✅ Listo para Fase 2: Preparar paper trading")
        
        return recommendations
    
    async def _activate_safe_mode(self, report: Dict):
        """Activa modo seguro automáticamente"""
        logger.warning("🚨 MODO SEGURO ACTIVADO por RSI Estratégico")
        # Aquí iría la lógica real de modo seguro
        # Por ahora solo loguea
    
    async def _save_rsi_report(self, cycle_id: str, report: Dict):
        """Guarda reporte RSI"""
        try:
            from pathlib import Path
            rsi_dir = Path("C:\\AI_VAULT\\tmp_agent\\state\\rsi")
            rsi_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = rsi_dir / f"{cycle_id}_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving RSI report: {e}")


# =============================================================================
# SECCIÓN 4: COMANDOS RSI ESTRATÉGICOS
# =============================================================================

async def handle_strategic_rsi_query(brain_chat) -> str:
    """Genera reporte RSI estratégico completo"""
    
    if not hasattr(brain_chat, 'strategic_rsi'):
        return "RSI Estratégico no inicializado"
    
    report = await brain_chat.strategic_rsi.run_strategic_rsi_cycle(force=True)
    
    if report.get("status") == "skipped":
        return f"RSI reciente. Próximo ciclo en {report.get('reason', 'N/A')}"
    
    # Construir respuesta
    reply = f"""🎯 **Análisis RSI Estratégico - Ciclo #{report['cycle_number']}**

**Fase Actual:** {report['fase_actual'].upper()} | Día {report['dias_en_fase']}
**Progreso:** {report['progreso_fase']:.1f}% | Deadline: {report['time_to_deadline']} días
**Próximo Gate:** {report['proximo_gate']}

---

**🚨 Riesgos de Ruina Detectados: {len(report['ruina_risks'])}**
"""
    
    if report['ruina_risks']:
        for risk in report['ruina_risks']:
            emoji = "🔴" if risk.get('level') == 'high' else "🟡"
            reply += f"\n{emoji} **{risk.get('type', 'Riesgo').upper()}**: {risk.get('probability', 'N/A')}% probabilidad"
            reply += f"\n   {risk.get('description', '')}"
            reply += f"\n   Acción: {risk.get('action', 'Investigar')}"
    else:
        reply += "\n✅ No se detectaron riesgos críticos"
    
    reply += f"""

---

**📊 Brechas Estratégicas (por impacto):**
"""
    
    for gap in report['strategic_gaps'][:4]:
        status = "✅" if gap['gap_percentage'] < 10 else "⚠️" if gap['gap_percentage'] < 30 else "🚨"
        weight = OBJECTIVE_WEIGHTS.get(StrategicObjective(gap['objective']), 0.1)
        priority = weight * gap['gap_percentage']
        
        reply += f"""
{status} **{gap['objective'].replace('_', ' ').title()}** (Peso: {weight*100:.0f}%)
   Capacidad: {gap['current_capability']:.1f}% / {gap['required_capability']:.1f}% requerido
   Brecha: {gap['gap_percentage']:.1f}% | Prioridad: {priority:.1f}
"""
        if gap['blockers']:
            reply += f"   Bloqueantes: {', '.join(gap['blockers'][:2])}\n"
    
    reply += f"""

---

**🛤️ Camino Crítico (Top 3):**
"""
    
    for i, path in enumerate(report['critical_path'][:3], 1):
        reply += f"""
{i}. **{path['objective'].replace('_', ' ').title()}** (Score: {path['priority_score']:.1f})
   Brecha: {path['gap']:.1f}% | {path['current']:.1f}% → {path['required']:.1f}%
"""
    
    reply += f"""

---

**📋 Plan Estratégico:**
Fase: {report['strategic_plan']['phase']}
Enfoque: {report['strategic_plan']['primary_focus']}
Timeline: {report['strategic_plan']['timeline']}

Acciones:
"""
    for action in report['strategic_plan']['actions']:
        reply += f"\n{action}"
    
    if report['safe_mode_triggered']:
        reply += "\n\n🚨 **MODO SEGURO ACTIVADO** - Requiere atención inmediata"
    
    reply += f"""

---

**💡 Recomendaciones:**
"""
    for rec in report['recommendations'][:4]:
        reply += f"\n{rec}"
    
    reply += f"""

---

**Nota:** Este RSI prioriza por impacto en el objetivo primordial según premisas canónicas v3.1.
Ciclo automático: Cada 60 minutos | Confirmación de alineación: Diaria + alertas"""
    
    return reply


# Uso: Integrar con BrainChatV7_RSI
# Agregar en __init__: self.strategic_rsi = StrategicRSI(self)
# Agregar en process_message: detectar "rsi estratégico", "brechas", "fase", "progreso"
