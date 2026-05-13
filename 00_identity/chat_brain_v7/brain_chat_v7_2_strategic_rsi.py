"""
Brain Chat V7.2 - RSI Estratégico Priorizado
Mejora recursiva alineada con objetivos estratégicos

Principio: No todas las debilidades son iguales.
Se prioriza por impacto en el OBJETIVO PRIMORDIAL: Trading Autónomo
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
# SECCIÓN 1: DEFINICIÓN DEL OBJETIVO PRIMORDIAL
# =============================================================================

class StrategicObjective(Enum):
    """Objetivos estratégicos ordenados por prioridad"""
    AUTONOMOUS_TRADING = "autonomous_trading"      # OBJETIVO #1
    DECISION_MAKING = "decision_making"              # Tomar decisiones sin intervención
    DATA_INTEGRITY = "data_integrity"              # Datos de trading precisos
    EXECUTION_SPEED = "execution_speed"              # Ejecutar operaciones rápido
    RELIABILITY = "reliability"                      # Operar sin fallos
    ANALYTICAL_DEPTH = "analytical_depth"            # Análisis profundo


OBJECTIVE_DESCRIPTIONS = {
    StrategicObjective.AUTONOMOUS_TRADING: "Capacidad de ejecutar operaciones de trading de forma autónoma sin supervisión humana",
    StrategicObjective.DECISION_MAKING: "Tomar decisiones de compra/venta basadas en datos sin confirmación externa",
    StrategicObjective.DATA_INTEGRITY: "Obtener y mantener datos de mercado precisos y en tiempo real",
    StrategicObjective.EXECUTION_SPEED: "Ejecutar operaciones con latencia mínima (< 500ms)",
    StrategicObjective.RELIABILITY: "Operar 99.9% del tiempo sin errores críticos",
    StrategicObjective.ANALYTICAL_DEPTH: "Realizar análisis técnico complejo (tendencias, patrones, predicciones)"
}


@dataclass
class StrategicGap:
    """Brecha entre capacidad actual y objetivo estratégico"""
    gap_id: str
    objective: str  # ej: "autonomous_trading"
    current_capability: float  # 0-100
    required_capability: float  # 0-100
    gap_percentage: float  # Brecha por cubrir
    impact_on_objective: str  # critical, high, medium, low
    blockers: List[str]  # Qué impide alcanzarlo
    

# =============================================================================
# SECCIÓN 2: SISTEMA DE PRIORIZACIÓN ESTRATÉGICA
# =============================================================================

class StrategicPrioritizer:
    """
    Prioriza mejoras basándose en impacto estratégico.
    
    Lógica:
    1. Identificar brechas entre capacidad actual y objetivos
    2. Calcular impacto de cada debilidad en objetivos
    3. Priorizar por ROI estratégico (qué tanto acerca al objetivo)
    4. Identificar bloqueantes críticos
    """
    
    def __init__(self):
        self.strategic_gaps: List[StrategicGap] = []
        
        # Mapeo: debilidad → objetivos que afecta
        self.impact_matrix = {
            "veracity": [StrategicObjective.DATA_INTEGRITY, StrategicObjective.DECISION_MAKING],
            "responsiveness": [StrategicObjective.EXECUTION_SPEED, StrategicObjective.AUTONOMOUS_TRADING],
            "reliability": [StrategicObjective.AUTONOMOUS_TRADING, StrategicObjective.DECISION_MAKING],
            "execution": [StrategicObjective.AUTONOMOUS_TRADING, StrategicObjective.EXECUTION_SPEED],
            "depth": [StrategicObjective.ANALYTICAL_DEPTH, StrategicObjective.DECISION_MAKING],
            "learning": [StrategicObjective.ANALYTICAL_DEPTH, StrategicObjective.DECISION_MAKING],
            "introspection": [StrategicObjective.RELIABILITY]  # Meta-capacidad
        }
        
        # Pesos de impacto
        self.impact_weights = {
            "critical": 1.0,   # Sin esto, no hay objetivo
            "high": 0.8,       # Afecta severamente
            "medium": 0.5,     # Afecta moderadamente  
            "low": 0.2         # Mejora marginal
        }
    
    def analyze_strategic_gaps(self, current_metrics: Dict, 
                              current_evaluation: Dict) -> List[StrategicGap]:
        """Analiza brechas estratégicas actuales"""
        gaps = []
        
        dimensions = current_evaluation.get("dimensions", {})
        
        # GAP 1: Autonomous Trading
        # Requiere: execution > 80%, reliability > 95%, decision_making capability
        exec_score = dimensions.get("execution", {}).get("score", 0)
        rel_score = dimensions.get("reliability", {}).get("score", 0)
        
        gaps.append(StrategicGap(
            gap_id="gap_autonomous_trading",
            objective=StrategicObjective.AUTONOMOUS_TRADING.value,
            current_capability=min(exec_score, rel_score),
            required_capability=85.0,
            gap_percentage=max(0, 85.0 - min(exec_score, rel_score)),
            impact_on_objective="critical" if min(exec_score, rel_score) < 50 else "high",
            blockers=self._identify_trading_blockers(exec_score, rel_score)
        ))
        
        # GAP 2: Decision Making
        # Requiere: veracity > 90%, depth > 70%
        ver_score = dimensions.get("veracity", {}).get("score", 0)
        depth_score = dimensions.get("depth", {}).get("score", 0)
        
        gaps.append(StrategicGap(
            gap_id="gap_decision_making",
            objective=StrategicObjective.DECISION_MAKING.value,
            current_capability=(ver_score + depth_score) / 2,
            required_capability=80.0,
            gap_percentage=max(0, 80.0 - (ver_score + depth_score) / 2),
            impact_on_objective="critical" if ver_score < 70 else "high",
            blockers=self._identify_decision_blockers(ver_score, depth_score)
        ))
        
        # GAP 3: Data Integrity
        # Requiere: veracity > 95%
        gaps.append(StrategicGap(
            gap_id="gap_data_integrity",
            objective=StrategicObjective.DATA_INTEGRITY.value,
            current_capability=ver_score,
            required_capability=95.0,
            gap_percentage=max(0, 95.0 - ver_score),
            impact_on_objective="critical" if ver_score < 80 else "high",
            blockers=["Pocos datos verificados", "Dependencia de APIs externas"] if ver_score < 80 else []
        ))
        
        # GAP 4: Execution Speed
        # Requiere: responsiveness < 500ms (score > 90)
        resp_score = dimensions.get("responsiveness", {}).get("score", 0)
        
        gaps.append(StrategicGap(
            gap_id="gap_execution_speed",
            objective=StrategicObjective.EXECUTION_SPEED.value,
            current_capability=resp_score,
            required_capability=90.0,
            gap_percentage=max(0, 90.0 - resp_score),
            impact_on_objective="high" if resp_score < 70 else "medium",
            blockers=["Latencia alta", "Sin caché"] if resp_score < 70 else []
        ))
        
        # Ordenar por impacto + brecha
        gaps.sort(key=lambda g: (
            self.impact_weights.get(g.impact_on_objective, 0) * g.gap_percentage
        ), reverse=True)
        
        self.strategic_gaps = gaps
        return gaps
    
    def _identify_trading_blockers(self, exec_score: float, rel_score: float) -> List[str]:
        """Identifica qué bloquea el trading autónomo"""
        blockers = []
        if exec_score < 50:
            blockers.append("Capacidad de ejecución muy limitada (whitelist restrictiva)")
        if exec_score < 80:
            blockers.append("Requiere confirmación para operaciones de trading")
        if rel_score < 95:
            blockers.append("Tasa de éxito insuficiente para operaciones financieras")
        return blockers
    
    def _identify_decision_blockers(self, ver_score: float, depth_score: float) -> List[str]:
        """Identifica qué bloquea toma de decisiones"""
        blockers = []
        if ver_score < 70:
            blockers.append("Datos no suficientemente verificados para decisiones")
        if depth_score < 60:
            blockers.append("Análisis superficial, no puede evaluar riesgos complejos")
        return blockers
    
    def prioritize_improvements(self, weaknesses: List[Any], 
                                gaps: List[StrategicGap]) -> List[Dict]:
        """Prioriza debilidades por impacto estratégico"""
        
        prioritized = []
        
        for weakness in weaknesses:
            # Calcular impacto en objetivos
            affected_objectives = self.impact_matrix.get(weakness.dimension, [])
            
            # Encontrar brechas que afecta
            relevant_gaps = [g for g in gaps if any(
                obj.value == g.objective for obj in affected_objectives
            )]
            
            if relevant_gaps:
                # Calcular prioridad estratégica
                max_impact = max([
                    self.impact_weights.get(g.impact_on_objective, 0) * g.gap_percentage
                    for g in relevant_gaps
                ], default=0)
                
                top_gap = relevant_gaps[0] if relevant_gaps else None
                
                prioritized.append({
                    "weakness": weakness,
                    "strategic_priority": max_impact,
                    "primary_objective": top_gap.objective if top_gap else "general",
                    "gap_blocked": top_gap.gap_percentage if top_gap else 0,
                    "blockers": top_gap.blockers if top_gap else [],
                    "rationale": f"Mejorar {weakness.dimension} reduce brecha de {top_gap.objective if top_gap else 'N/A'} en {max_impact:.1f}%"
                })
            else:
                # Debilidad no crítica estratégicamente
                prioritized.append({
                    "weakness": weakness,
                    "strategic_priority": 0.1,
                    "primary_objective": "general",
                    "gap_blocked": 0,
                    "blockers": [],
                    "rationale": "Mejora general de calidad, no bloquea objetivos críticos"
                })
        
        # Ordenar por prioridad estratégica
        prioritized.sort(key=lambda x: x["strategic_priority"], reverse=True)
        
        return prioritized
    
    def get_critical_path(self) -> List[str]:
        """Retorna el camino crítico para alcanzar trading autónomo"""
        if not self.strategic_gaps:
            return []
        
        # Ordenar por qué tan cerca está de cerrar la brecha
        critical = [g for g in self.strategic_gaps if g.impact_on_objective == "critical"]
        
        path = []
        for gap in critical:
            path.append(f"{gap.objective}: {gap.gap_percentage:.1f}% por cubrir")
            path.extend([f"  → {blocker}" for blocker in gap.blockers])
        
        return path


# =============================================================================
# SECCIÓN 3: SISTEMA RSI ESTRATÉGICO COMPLETO
# =============================================================================

class StrategicRSI:
    """
    RSI con priorización estratégica.
    
    A diferencia del RSI genérico, este:
    1. Identifica OBJETIVO PRIMORDIAL (trading autónomo)
    2. Mapea debilidades a impacto en objetivo
    3. Prioriza por ROI estratégico
    4. Propone mejoras que acercan al objetivo final
    """
    
    def __init__(self, brain_chat):
        self.brain = brain_chat
        self.prioritizer = StrategicPrioritizer()
        self.cycle_count = 0
        self.last_strategic_analysis = None
    
    async def run_strategic_rsi_cycle(self) -> Dict:
        """Ejecuta ciclo RSI estratégico"""
        self.cycle_count += 1
        
        # 1. Obtener evaluación actual
        current_eval = self.brain.evaluation_system.get_cached_evaluation()
        current_metrics = self.brain.metrics_engine.get_current_metrics()
        
        # 2. Analizar brechas estratégicas
        gaps = self.prioritizer.analyze_strategic_gaps(current_metrics, current_eval)
        
        # 3. Detectar debilidades (del sistema base)
        weaknesses = self.brain.rsi.detector.detect_weaknesses()
        
        # 4. Priorizar por impacto estratégico
        prioritized = self.prioritizer.prioritize_improvements(weaknesses, gaps)
        
        # 5. Generar plan estratégico
        strategic_plan = self._generate_strategic_plan(gaps, prioritized)
        
        report = {
            "cycle_id": f"rsi_strategic_{self.cycle_count}",
            "timestamp": time.time(),
            "objective_primordial": StrategicObjective.AUTONOMOUS_TRADING.value,
            "progress_to_objective": self._calculate_progress(gaps),
            "strategic_gaps": [asdict(g) for g in gaps],
            "critical_path": self.prioritizer.get_critical_path(),
            "prioritized_weaknesses": prioritized[:5],  # Top 5
            "strategic_plan": strategic_plan,
            "next_milestone": self._identify_next_milestone(gaps)
        }
        
        self.last_strategic_analysis = report
        return report
    
    def _calculate_progress(self, gaps: List[StrategicGap]) -> float:
        """Calcula progreso hacia trading autónomo"""
        if not gaps:
            return 100.0
        
        # Peso por importancia del objetivo
        weights = {
            StrategicObjective.AUTONOMOUS_TRADING.value: 0.4,
            StrategicObjective.DECISION_MAKING.value: 0.3,
            StrategicObjective.DATA_INTEGRITY.value: 0.15,
            StrategicObjective.EXECUTION_SPEED.value: 0.1,
            StrategicObjective.RELIABILITY.value: 0.05
        }
        
        total_progress = 0
        total_weight = 0
        
        for gap in gaps:
            weight = weights.get(gap.objective, 0.1)
            progress = (gap.current_capability / gap.required_capability) * 100
            total_progress += progress * weight
            total_weight += weight
        
        return total_progress / total_weight if total_weight > 0 else 0
    
    def _generate_strategic_plan(self, gaps: List[StrategicGap], 
                                 prioritized: List[Dict]) -> Dict:
        """Genera plan estratégico priorizado"""
        
        plan = {
            "phase": "current",
            "primary_focus": "Ninguno - sistema óptimo",
            "actions": []
        }
        
        # Identificar brecha más crítica
        critical_gaps = [g for g in gaps if g.impact_on_objective == "critical"]
        
        if critical_gaps:
            top_gap = critical_gaps[0]
            plan["phase"] = "critical_improvement"
            plan["primary_focus"] = f"Cerrar brecha en {top_gap.objective}"
            plan["actions"] = [
                f"1. Mejorar {top_gap.objective} de {top_gap.current_capability:.1f}% a {top_gap.required_capability:.1f}%",
                f"2. Eliminar bloqueantes: {', '.join(top_gap.blockers[:2])}",
                f"3. Validar progreso en próximo ciclo RSI"
            ]
        elif prioritized:
            # Trabajar en debilidad de mayor prioridad
            top_weakness = prioritized[0]
            plan["phase"] = "strategic_optimization"
            plan["primary_focus"] = f"Mejorar {top_weakness['weakness'].dimension}"
            plan["actions"] = [
                f"1. {top_weakness['rationale']}",
                f"2. Impacto estratégico: {top_weakness['strategic_priority']:.1f}%",
                "3. Implementar y medir en 24h"
            ]
        else:
            plan["phase"] = "maintenance"
            plan["actions"] = ["Monitorear métricas", "Optimizaciones menores"]
        
        return plan
    
    def _identify_next_milestone(self, gaps: List[StrategicGap]) -> str:
        """Identifica próximo hito alcanzable"""
        if not gaps:
            return "Trading Autónomo: COMPLETADO"
        
        # Encontrar brecha más cercana a cerrar
        closest = min(gaps, key=lambda g: g.gap_percentage)
        
        if closest.gap_percentage < 10:
            return f"Cercano: {closest.objective} (falta {closest.gap_percentage:.1f}%)"
        
        # Si hay brechas críticas, priorizarlas
        critical = [g for g in gaps if g.impact_on_objective == "critical"]
        if critical:
            return f"CRÍTICO: {critical[0].objective} (bloquea objetivo primordial)"
        
        return f"Objetivo: {closest.objective} (brecha {closest.gap_percentage:.1f}%)"


# =============================================================================
# SECCIÓN 4: COMANDOS RSI ESTRATÉGICOS
# =============================================================================

async def handle_strategic_rsi_query(brain_chat) -> str:
    """Genera reporte RSI estratégico"""
    
    if not hasattr(brain_chat, 'strategic_rsi'):
        return "RSI Estratégico no inicializado"
    
    report = await brain_chat.strategic_rsi.run_strategic_rsi_cycle()
    
    reply = f"""🎯 **Análisis RSI Estratégico - Priorizado por Objetivo**

**Objetivo Primordial:** {report['objective_primordial']}
**Progreso hacia Autonomía:** {report['progress_to_objective']:.1f}%
**Ciclo Estratégico #{report['cycle_id']}**

---

**🚨 Brechas Estratégicas Detectadas: {len(report['strategic_gaps'])}**

"""
    
    for gap in report['strategic_gaps'][:4]:
        status = "✅" if gap['gap_percentage'] < 10 else "⚠️" if gap['gap_percentage'] < 30 else "🚨"
        reply += f"""
{status} **{gap['objective'].replace('_', ' ').title()}**
   Capacidad: {gap['current_capability']:.1f}% / {gap['required_capability']:.1f}% requerido
   Brecha: {gap['gap_percentage']:.1f}% | Impacto: {gap['impact_on_objective']}
"""
        if gap['blockers']:
            reply += f"   Bloqueantes: {', '.join(gap['blockers'][:2])}\n"
    
    reply += f"""
---

**🛤️ Camino Crítico para Trading Autónomo:**
"""
    
    for step in report['critical_path'][:6]:
        reply += f"\n• {step}"
    
    reply += f"""

---

**📋 Plan Estratégico Actual:**
Fase: {report['strategic_plan']['phase']}
Enfoque: {report['strategic_plan']['primary_focus']}

Acciones:
"""
    for action in report['strategic_plan']['actions']:
        reply += f"\n{action}"
    
    reply += f"""

---

**🎯 Próximo Hito:** {report['next_milestone']}

---

**Nota:** Este análisis prioriza mejoras por impacto en el objetivo primordial
(Trading Autónomo), no por facilidad de implementación."""
    
    return reply


# Uso: Agregar a BrainChatV7_RSI.__init__:
# self.strategic_rsi = StrategicRSI(self)

# Y en process_message, detectar:
# "rsi estratégico", "prioridad", "objetivo", "brechas", "camino crítico"
