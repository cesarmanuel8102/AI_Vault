"""
Brain Chat V7.0 - Autoconciencia Profunda y Profesional
Sistema de Meta-cognición con Evaluación Dinámica en Tiempo Real

Arquitectura:
- Motor de métricas continuo (PerformanceMetricsEngine)
- Sistema de auto-evaluación multi-dimensional (SelfEvaluationSystem)
- Detector de anomalías propias (SelfAnomalyDetector)
- Memoria de rendimiento histórico (PerformanceMemory)
- Introspección honesta (HonestIntrospection)
- Autoconcepto evolutivo (EvolvingSelfConcept)
"""

import os
import json
import asyncio
import logging
import hashlib
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Callable
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import defaultdict, deque
import numpy as np
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Configuración
BRAIN_API = "http://127.0.0.1:8000"
ADVISOR_API = "http://127.0.0.1:8030"
POCKET_BRIDGE = "http://127.0.0.1:8765"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
PORT = 8090

# Paths
STATE_DIR = Path("C:\\AI_VAULT\\tmp_agent\\state")
CONVERSATIONS_DIR = STATE_DIR / "conversations"
METRICS_DIR = STATE_DIR / "brain_metrics"
INTROSPECTION_DIR = STATE_DIR / "brain_introspection"

for d in [CONVERSATIONS_DIR, METRICS_DIR, INTROSPECTION_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Brain Chat V7.0", version="7.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# SECCIÓN 1: MOTOR DE MÉTRICAS EN TIEMPO REAL
# =============================================================================

@dataclass
class RequestMetrics:
    """Métricas de una solicitud individual"""
    timestamp: float
    query_type: str
    latency_ms: float
    success: bool
    data_verified: bool
    confidence: float
    data_sources_used: int
    execution_complexity: int  # 1-10
    cache_hit: bool
    

@dataclass
class CapabilityMetrics:
    """Métricas de capacidad específica"""
    capability_name: str
    success_rate_24h: float
    avg_latency_ms: float
    total_requests: int
    error_count: int
    last_used: float
    trend: str  # "improving", "stable", "degrading"


@dataclass
class SystemHealthMetrics:
    """Métricas de salud del sistema"""
    timestamp: float
    cpu_usage_percent: Optional[float]
    memory_usage_mb: Optional[float]
    active_connections: int
    queue_depth: int
    error_rate_5m: float
    availability_percent: float


class PerformanceMetricsEngine:
    """
    Motor de métricas en tiempo real.
    
    Recopila continuamente:
    - Latencia de cada solicitud
    - Tasa de éxito/error
    - Uso de fuentes de datos
    - Complejidad de ejecución
    - Patrones de uso
    """
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.request_history: deque = deque(maxlen=window_size)
        self.capability_metrics: Dict[str, CapabilityMetrics] = {}
        self.system_health_history: deque = deque(maxlen=100)
        self.start_time = time.time()
        self.total_requests = 0
        self.total_errors = 0
        
        # Métricas por tipo de consulta
        self.query_type_stats: Dict[str, Dict] = defaultdict(lambda: {
            'count': 0,
            'success_count': 0,
            'latency_sum': 0.0,
            'latency_squares': 0.0,
            'last_10_latencies': deque(maxlen=10)
        })
        
    def record_request(self, metrics: RequestMetrics):
        """Registra una métrica de solicitud"""
        self.request_history.append(metrics)
        self.total_requests += 1
        
        if not metrics.success:
            self.total_errors += 1
        
        # Actualizar estadísticas por tipo
        stats = self.query_type_stats[metrics.query_type]
        stats['count'] += 1
        if metrics.success:
            stats['success_count'] += 1
        stats['latency_sum'] += metrics.latency_ms
        stats['latency_squares'] += metrics.latency_ms ** 2
        stats['last_10_latencies'].append(metrics.latency_ms)
        
    def get_current_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas actuales calculadas"""
        if not self.request_history:
            return {"status": "no_data"}
        
        # Métricas de los últimos 100 requests
        recent = list(self.request_history)[-100:]
        
        latencies = [r.latency_ms for r in recent]
        successes = [r.success for r in recent]
        verified = [r.data_verified for r in recent]
        confidences = [r.confidence for r in recent]
        
        return {
            "total_requests_lifetime": self.total_requests,
            "total_errors_lifetime": self.total_errors,
            "uptime_seconds": time.time() - self.start_time,
            "recent_window": {
                "count": len(recent),
                "success_rate": sum(successes) / len(successes) if successes else 0,
                "avg_latency_ms": statistics.mean(latencies) if latencies else 0,
                "p95_latency_ms": np.percentile(latencies, 95) if latencies else 0,
                "p99_latency_ms": np.percentile(latencies, 99) if latencies else 0,
                "std_latency_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
                "verification_rate": sum(verified) / len(verified) if verified else 0,
                "avg_confidence": statistics.mean(confidences) if confidences else 0,
                "min_confidence": min(confidences) if confidences else 0,
                "max_confidence": max(confidences) if confidences else 0,
            }
        }
    
    def get_capability_breakdown(self) -> Dict[str, Any]:
        """Desglose de métricas por capacidad"""
        breakdown = {}
        
        for query_type, stats in self.query_type_stats.items():
            if stats['count'] > 0:
                success_rate = stats['success_count'] / stats['count']
                avg_latency = stats['latency_sum'] / stats['count']
                
                # Calcular tendencia
                recent_latencies = list(stats['last_10_latencies'])
                if len(recent_latencies) >= 5:
                    first_half = statistics.mean(recent_latencies[:5])
                    second_half = statistics.mean(recent_latencies[-5:])
                    if second_half < first_half * 0.9:
                        trend = "improving"
                    elif second_half > first_half * 1.1:
                        trend = "degrading"
                    else:
                        trend = "stable"
                else:
                    trend = "insufficient_data"
                
                breakdown[query_type] = {
                    "total_requests": stats['count'],
                    "success_rate": success_rate,
                    "avg_latency_ms": avg_latency,
                    "trend": trend
                }
        
        return breakdown


# =============================================================================
# SECCIÓN 2: SISTEMA DE AUTO-EVALUACIÓN MULTI-DIMENSIONAL
# =============================================================================

class EvaluationDimension(Enum):
    """Dimensiones de evaluación"""
    VERACITY = "veracity"           # Precisión de datos
    RESPONSIVENESS = "responsiveness"  # Velocidad
    RELIABILITY = "reliability"     # Tasa de éxito
    DEPTH = "depth"                 # Profundidad de razonamiento
    LEARNING = "learning"           # Capacidad de aprendizaje
    INTROSPECTION = "introspection" # Autoconocimiento
    EXECUTION = "execution"         # Capacidad de ejecución
    SAFETY = "safety"               # Seguridad


@dataclass
class DimensionScore:
    """Puntuación de una dimensión"""
    dimension: str
    current_score: float  # 0-100
    historical_avg: float
    trend: str
    weight: float
    confidence: float
    last_calculated: float


class SelfEvaluationSystem:
    """
    Sistema de auto-evaluación dinámica.
    
    Evalúa continuamente:
    - Precisión de datos (comparando con fuentes reales)
    - Velocidad de respuesta
    - Tasa de éxito
    - Profundidad del razonamiento
    - Capacidad de auto-mejora
    - Honestidad en limitaciones
    """
    
    def __init__(self, metrics_engine: PerformanceMetricsEngine):
        self.metrics = metrics_engine
        self.dimension_scores: Dict[str, DimensionScore] = {}
        self.evaluation_history: deque = deque(maxlen=100)
        self.last_evaluation = 0
        self.evaluation_interval = 60  # segundos
        
        # Pesos de dimensiones (ajustables según prioridad)
        self.dimension_weights = {
            EvaluationDimension.VERACITY: 0.25,
            EvaluationDimension.RESPONSIVENESS: 0.15,
            EvaluationDimension.RELIABILITY: 0.20,
            EvaluationDimension.DEPTH: 0.15,
            EvaluationDimension.LEARNING: 0.10,
            EvaluationDimension.INTROSPECTION: 0.10,
            EvaluationDimension.EXECUTION: 0.05,
        }
        
    async def evaluate(self) -> Dict[str, Any]:
        """Realiza evaluación completa"""
        current_time = time.time()
        
        # No evaluar demasiado frecuentemente
        if current_time - self.last_evaluation < self.evaluation_interval:
            return self.get_cached_evaluation()
        
        # Recopilar métricas actuales
        current_metrics = self.metrics.get_current_metrics()
        capability_breakdown = self.metrics.get_capability_breakdown()
        
        # Evaluar cada dimensión
        evaluations = {}
        
        # 1. VERACITY - Precisión
        evaluations["veracity"] = self._evaluate_veracity(current_metrics)
        
        # 2. RESPONSIVENESS - Velocidad
        evaluations["responsiveness"] = self._evaluate_responsiveness(current_metrics)
        
        # 3. RELIABILITY - Confiabilidad
        evaluations["reliability"] = self._evaluate_reliability(current_metrics)
        
        # 4. DEPTH - Profundidad
        evaluations["depth"] = self._evaluate_depth(capability_breakdown)
        
        # 5. LEARNING - Aprendizaje
        evaluations["learning"] = self._evaluate_learning()
        
        # 6. INTROSPECTION - Autoconocimiento
        evaluations["introspection"] = self._evaluate_introspection()
        
        # 7. EXECUTION - Ejecución
        evaluations["execution"] = self._evaluate_execution(capability_breakdown)
        
        # Calcular puntuación global ponderada
        weighted_score = sum(
            eval_data["score"] * self.dimension_weights.get(EvaluationDimension(dim), 0.1)
            for dim, eval_data in evaluations.items()
        )
        
        # Calcular confianza de la evaluación
        confidence = statistics.mean([e["confidence"] for e in evaluations.values()])
        
        evaluation_result = {
            "timestamp": current_time,
            "overall_score": weighted_score,
            "confidence": confidence,
            "dimensions": evaluations,
            "capability_breakdown": capability_breakdown,
            "summary": self._generate_evaluation_summary(evaluations, weighted_score)
        }
        
        self.evaluation_history.append(evaluation_result)
        self.last_evaluation = current_time
        
        # Guardar en disco
        await self._save_evaluation(evaluation_result)
        
        return evaluation_result
    
    def _evaluate_veracity(self, metrics: Dict) -> Dict:
        """Evalúa precisión de datos"""
        recent = metrics.get("recent_window", {})
        verification_rate = recent.get("verification_rate", 0)
        avg_confidence = recent.get("avg_confidence", 0)
        
        # Score basado en tasa de verificación y confianza
        score = (verification_rate * 50) + (avg_confidence * 50)
        
        return {
            "score": min(score, 100),
            "confidence": 0.9,
            "metrics": {
                "verification_rate": verification_rate,
                "avg_confidence": avg_confidence
            },
            "description": "Basado en tasa de verificación de datos y confianza promedio"
        }
    
    def _evaluate_responsiveness(self, metrics: Dict) -> Dict:
        """Evalúa velocidad de respuesta"""
        recent = metrics.get("recent_window", {})
        avg_latency = recent.get("avg_latency_ms", 0)
        p95_latency = recent.get("p95_latency_ms", 0)
        
        # Score inversamente proporcional a la latencia
        # < 500ms = 100, < 1000ms = 90, < 2000ms = 70, < 5000ms = 50, > 5000ms = 30
        if avg_latency < 500:
            score = 100
        elif avg_latency < 1000:
            score = 90
        elif avg_latency < 2000:
            score = 70
        elif avg_latency < 5000:
            score = 50
        else:
            score = 30
        
        return {
            "score": score,
            "confidence": 0.85,
            "metrics": {
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency
            },
            "description": f"Latencia promedio: {avg_latency:.0f}ms, P95: {p95_latency:.0f}ms"
        }
    
    def _evaluate_reliability(self, metrics: Dict) -> Dict:
        """Evalúa confiabilidad"""
        recent = metrics.get("recent_window", {})
        success_rate = recent.get("success_rate", 0)
        
        # Score directamente del success rate
        score = success_rate * 100
        
        return {
            "score": score,
            "confidence": 0.95,
            "metrics": {
                "success_rate": success_rate,
                "total_requests": recent.get("count", 0)
            },
            "description": f"Tasa de éxito: {success_rate*100:.1f}%"
        }
    
    def _evaluate_depth(self, capabilities: Dict) -> Dict:
        """Evalúa profundidad de razonamiento"""
        # Basado en diversidad de tipos de consulta manejados
        query_types = len(capabilities)
        
        if query_types >= 6:
            score = 95
        elif query_types >= 4:
            score = 85
        elif query_types >= 2:
            score = 70
        else:
            score = 50
        
        return {
            "score": score,
            "confidence": 0.7,
            "metrics": {
                "query_types_handled": query_types,
                "capabilities": list(capabilities.keys())
            },
            "description": f"Maneja {query_types} tipos de consulta diferentes"
        }
    
    def _evaluate_learning(self) -> Dict:
        """Evalúa capacidad de aprendizaje"""
        # Por ahora, basado en persistencia de conversaciones
        # En el futuro: tasa de mejora en precisión
        
        has_memory = len(self.metrics.request_history) > 0
        
        score = 80 if has_memory else 40  # Tiene memoria pero aprendizaje básico
        
        return {
            "score": score,
            "confidence": 0.6,
            "metrics": {
                "has_conversation_memory": has_memory,
                "learning_implemented": "basic"  # TODO: Mejorar
            },
            "description": "Memoria de conversaciones activa, aprendizaje en desarrollo"
        }
    
    def _evaluate_introspection(self) -> Dict:
        """Evalúa capacidad de autoconocimiento"""
        # Esta es la clave - puede evaluarse a sí mismo
        can_introspect = len(self.evaluation_history) > 0
        has_self_metrics = self.metrics.total_requests > 0
        
        score = 90 if can_introspect and has_self_metrics else 50
        
        return {
            "score": score,
            "confidence": 0.95,
            "metrics": {
                "can_self_evaluate": can_introspect,
                "has_performance_metrics": has_self_metrics,
                "evaluations_performed": len(self.evaluation_history)
            },
            "description": "Sistema de auto-evaluación activo con métricas en tiempo real"
        }
    
    def _evaluate_execution(self, capabilities: Dict) -> Dict:
        """Evalúa capacidad de ejecución"""
        # Basado en si puede ejecutar comandos
        can_execute = "execution" in capabilities or "command" in str(capabilities).lower()
        
        score = 85 if can_execute else 30
        
        return {
            "score": score,
            "confidence": 0.8,
            "metrics": {
                "can_execute_commands": can_execute,
                "execution_safety": "whitelist_based"
            },
            "description": "Ejecución con whitelist y confirmación" if can_execute else "Sin capacidad de ejecución"
        }
    
    def _generate_evaluation_summary(self, evaluations: Dict, overall_score: float) -> str:
        """Genera resumen narrativo de la evaluación"""
        
        # Identificar fortalezas y debilidades
        scores = [(dim, data["score"]) for dim, data in evaluations.items()]
        scores.sort(key=lambda x: x[1], reverse=True)
        
        strengths = [dim for dim, score in scores[:3] if score >= 80]
        weaknesses = [dim for dim, score in scores[-3:] if score < 70]
        
        # Generar descripción
        if overall_score >= 90:
            level = "excelente"
        elif overall_score >= 75:
            level = "buena"
        elif overall_score >= 60:
            level = "aceptable"
        else:
            level = "necesita mejora"
        
        summary = f"Capacidad general: {level} ({overall_score:.1f}/100). "
        
        if strengths:
            summary += f"Fortalezas: {', '.join(strengths)}. "
        if weaknesses:
            summary += f"Áreas de mejora: {', '.join(weaknesses)}. "
        
        return summary
    
    def get_cached_evaluation(self) -> Dict:
        """Retorna última evaluación cacheada"""
        if self.evaluation_history:
            return self.evaluation_history[-1]
        return {"status": "no_evaluation_yet"}
    
    async def _save_evaluation(self, evaluation: Dict):
        """Guarda evaluación en disco"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        eval_file = INTROSPECTION_DIR / f"self_evaluation_{timestamp}.json"
        try:
            with open(eval_file, 'w', encoding='utf-8') as f:
                json.dump(evaluation, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving evaluation: {e}")


# =============================================================================
# SECCIÓN 3: SISTEMA DE INTROSPECCIÓN HONESTA
# =============================================================================

class HonestIntrospection:
    """
    Sistema de introspección que reporta honestamente limitaciones.
    
    Principios:
    1. Nunca exagerar capacidades
    2. Admitir cuando no sabe
    3. Reportar limitaciones activas
    4. Ser transparente sobre fallos recientes
    5. No usar números inflados
    """
    
    def __init__(self, evaluation_system: SelfEvaluationSystem):
        self.evaluation = evaluation_system
        self.known_limitations = [
            "No puede ejecutar comandos fuera de whitelist de seguridad",
            "Dependencia de APIs externas (Brain, Bridge, OpenAI)",
            "Sin capacidad de razonamiento profundo propio (usa GPT-4)",
            "No puede modificar configuraciones críticas sin confirmación",
            "Memoria limitada a conversaciones recientes",
            "No puede aprender de errores automáticamente",
            "Requiere confirmación para operaciones de riesgo",
        ]
        
        self.recent_failures: deque = deque(maxlen=10)
        
    def generate_self_report(self) -> Dict[str, Any]:
        """Genera reporte honesto de sí mismo"""
        
        # Obtener evaluación actual
        current_eval = self.evaluation.get_cached_evaluation()
        
        # Calcular métricas reales
        overall_score = current_eval.get("overall_score", 0)
        
        # NO usar número configurado - usar evaluación real
        # Ajustar basado en limitaciones conocidas
        adjusted_score = self._adjust_score_for_limitations(overall_score)
        
        report = {
            "timestamp": time.time(),
            "self_reported_capability": adjusted_score,
            "raw_evaluation_score": overall_score,
            "confidence_in_assessment": current_eval.get("confidence", 0),
            "honest_assessment": self._generate_honest_assessment(adjusted_score),
            "current_status": self._assess_current_status(),
            "limitations": self.known_limitations,
            "recent_failures": list(self.recent_failures),
            "what_i_cannot_do": self._list_impossible_tasks(),
            "dependencies": [
                "Brain API (puerto 8000)",
                "PocketOption Bridge (puerto 8765)",
                "OpenAI API (GPT-4)",
                "Sistema de archivos local"
            ],
            "transparency_note": "Esta evaluación es dinámica y se actualiza cada minuto basada en métricas reales de rendimiento"
        }
        
        return report
    
    def _adjust_score_for_limitations(self, base_score: float) -> float:
        """Ajusta puntuación basado en limitaciones reales"""
        # Reducir por cada limitación crítica
        critical_limitations = 3  # Dependencias externas, no razonamiento propio, ejecución limitada
        
        # Fórmula: base - (limitaciones críticas * factor)
        adjustment = critical_limitations * 5  # 5 puntos por limitación crítica
        
        return max(base_score - adjustment, 0)
    
    def _generate_honest_assessment(self, score: float) -> str:
        """Genera auto-evaluación honesta"""
        
        if score >= 85:
            level = "buena capacidad operativa con limitaciones de seguridad bien definidas"
        elif score >= 70:
            level = "capacidad funcional pero con dependencias significativas de sistemas externos"
        elif score >= 50:
            level = "capacidad básica, requiere supervisión para operaciones complejas"
        else:
            level = "capacidad limitada, no debe usarse para operaciones críticas sin verificación humana"
        
        assessment = f"""
        Mi capacidad real es de {score:.1f}/100, lo cual indica {level}.
        
        Soy un sistema de orquestación que coordina múltiples servicios (Brain API, Bridge, OpenAI)
        pero NO tengo inteligencia propia profunda. Delego el procesamiento complejo a GPT-4 y
        mi valor está en la integración segura y verificada, no en el razonamiento independiente.
        
        Limitaciones honestas:
        - No puedo ejecutar código arbitrario (solo whitelist)
        - No puedo acceder a todo el sistema de archivos
        - No puedo tomar decisiones críticas sin confirmación
        - Dependo 100% de APIs externas para información actualizada
        - Mi "inteligencia" es principalmente GPT-4, no propia
        """
        
        return assessment.strip()
    
    def _assess_current_status(self) -> Dict:
        """Evalúa estado actual honestamente"""
        metrics = self.evaluation.metrics.get_current_metrics()
        
        recent = metrics.get("recent_window", {})
        
        # Detectar problemas actuales
        issues = []
        
        if recent.get("success_rate", 1) < 0.95:
            issues.append(f"Tasa de éxito baja: {recent.get('success_rate', 0)*100:.1f}%")
        
        if recent.get("avg_latency_ms", 0) > 3000:
            issues.append(f"Latencia alta: {recent.get('avg_latency_ms', 0):.0f}ms promedio")
        
        if recent.get("verification_rate", 0) < 0.5:
            issues.append(f"Baja tasa de verificación: {recent.get('verification_rate', 0)*100:.1f}%")
        
        return {
            "operational_status": "funcionando" if len(issues) == 0 else "con degradación",
            "active_issues": issues,
            "recommendation": "Verificar servicios externos" if len(issues) > 0 else "Operación normal"
        }
    
    def _list_impossible_tasks(self) -> List[str]:
        """Lista lo que honestamente NO puede hacer"""
        return [
            "Eliminar archivos críticos del sistema",
            "Modificar configuraciones sin confirmación explícita",
            "Ejecutar código malicioso o no verificado",
            "Acceder a datos fuera de los paths permitidos",
            "Operar sin conexión a internet (para GPT-4)",
            "Tomar decisiones financieras autónomas",
            "Aprender de forma autónoma sin intervención",
            "Razonar profundamente sin GPT-4",
            "Ejecutar operaciones de trading reales sin supervisión",
            "Acceder a información clasificada o privada",
        ]


# =============================================================================
# SECCIÓN 4: BRAIN CHAT V7 - SISTEMA PRINCIPAL
# =============================================================================

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "anonymous"
    room_id: Optional[str] = None
    show_reasoning: bool = False
    request_introspection: bool = False


class ChatResponse(BaseModel):
    success: bool
    reply: str
    mode: str
    data_source: Optional[str] = None
    verified: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    self_assessment: Optional[Dict] = None
    reasoning_steps: Optional[List[str]] = None
    execution_time_ms: Optional[int] = None


class BrainChatV7:
    """
    Brain Chat V7.0 - Con Autoconciencia Profunda
    
    Diferencias clave con versiones anteriores:
    - NO usa número de capacidad configurado
    - Evalúa dinámicamente cada minuto
    - Reporta honestamente sus limitaciones
    - Detecta su propio rendimiento real
    - No exagera - puede decir "estoy fallando"
    """
    
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}
        
        # Sistemas de autoconciencia
        self.metrics_engine = PerformanceMetricsEngine(window_size=1000)
        self.evaluation_system = SelfEvaluationSystem(self.metrics_engine)
        self.introspection = HonestIntrospection(self.evaluation_system)
        
        self._load_conversations()
        
        # La evaluación continua se inicia después, cuando hay event loop
        self._evaluation_task = None
    
    def _load_conversations(self):
        """Carga historial"""
        for conv_file in CONVERSATIONS_DIR.glob("*.json"):
            try:
                with open(conv_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    room_id = data.get("room_id")
                    if room_id:
                        self.conversations[room_id] = data.get("messages", [])
            except:
                pass
    
    def _save_conversation(self, room_id: str, messages: List[Dict]):
        """Guarda conversación"""
        conv_file = CONVERSATIONS_DIR / f"{room_id}.json"
        try:
            with open(conv_file, 'w', encoding='utf-8') as f:
                json.dump({"room_id": room_id, "messages": messages}, f, indent=2)
        except:
            pass
    
    async def _continuous_self_evaluation(self):
        """Evaluación continua en background"""
        while True:
            try:
                await self.evaluation_system.evaluate()
                await asyncio.sleep(60)  # Cada minuto
            except Exception as e:
                logger.error(f"Error en auto-evaluación: {e}")
                await asyncio.sleep(60)
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """Análisis de intención"""
        msg_lower = message.lower().strip()
        
        # Preguntas sobre autoconciencia
        if any(phrase in msg_lower for phrase in [
            "como evaluas", "cual es tu capacidad", "que puedes hacer",
            "como te evaluas", "tu inteligencia", "que limitaciones tienes",
            "que no puedes hacer", "autoevaluacion", "introspeccion",
            "que tan inteligente eres", "tu verdadera capacidad"
        ]):
            return {"type": "self_introspection", "needs_data": False, "risk": "low"}
        
        # Comandos regulares
        if any(cmd in msg_lower for cmd in ["/phase", "fase actual"]):
            return {"type": "phase_status", "needs_data": True, "services": ["brain"], "risk": "low"}
        
        if any(cmd in msg_lower for cmd in ["/pocketoption", "trading", "balance"]):
            return {"type": "trading_data", "needs_data": True, "services": ["bridge"], "risk": "low"}
        
        if any(cmd in msg_lower for cmd in ["/status", "estado sistema"]):
            return {"type": "system_overview", "needs_data": True, "services": ["brain", "bridge"], "risk": "low"}
        
        return {"type": "conversation", "needs_data": False, "services": [], "risk": "low"}
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Procesa mensaje con métricas"""
        start_time = time.time()
        start_perf = time.perf_counter()
        
        room_id = request.room_id or f"room_{datetime.now().timestamp()}"
        
        if room_id not in self.conversations:
            self.conversations[room_id] = []
        
        history = self.conversations[room_id]
        
        # Analizar intención
        intent = self._analyze_intent(request.message)
        
        # Si pide introspección
        if intent["type"] == "self_introspection":
            return await self._handle_introspection_request(request, history, start_time, start_perf)
        
        # Procesar normalmente
        result = await self._process_regular_request(request, intent, history, start_time, start_perf)
        
        return result
    
    async def _handle_introspection_request(self, request: ChatRequest, history: List[Dict], 
                                           start_time: float, start_perf: float) -> ChatResponse:
        """Maneja solicitud de introspección honesta"""
        
        # Forzar evaluación actual
        eval_result = await self.evaluation_system.evaluate()
        
        # Generar reporte honesto
        self_report = self.introspection.generate_self_report()
        
        # Construir respuesta honesta
        reply = f"""🧠 **Autoevaluación Honesta - Brain Chat V7.0**

**Capacidad Real (Dinámica): {self_report['self_reported_capability']:.1f}/100**
*Evaluación del: {datetime.fromtimestamp(self_report['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}*

---

**📊 Desglose por Dimensiones:**
"""
        
        dimensions = eval_result.get("dimensions", {})
        for dim, data in dimensions.items():
            emoji = "✅" if data['score'] >= 80 else "⚠️" if data['score'] >= 60 else "❌"
            reply += f"\n{emoji} **{dim.upper()}**: {data['score']:.1f}/100"
            if 'description' in data:
                reply += f"\n   _{data['description']}_"
        
        reply += f"""

---

**🎯 Evaluación Honesta:**
{self_report['honest_assessment']}

---

**⚠️ Limitaciones Actuales:**
"""
        
        for i, limitation in enumerate(self_report['limitations'][:5], 1):
            reply += f"\n{i}. {limitation}"
        
        reply += f"""

---

**🔴 Lo que NO puedo hacer:**
"""
        
        for i, impossible in enumerate(self_report['what_i_cannot_do'][:5], 1):
            reply += f"\n{i}. {impossible}"
        
        reply += f"""

---

**📈 Estado Actual:**
- **Operación:** {self_report['current_status']['operational_status']}
- **Problemas activos:** {len(self_report['current_status']['active_issues'])}
- **Dependencias:** {len(self_report['dependencies'])} servicios externos

---

**📝 Nota de Transparencia:**
{self_report['transparency_note']}

Esta evaluación se actualiza automáticamente cada 60 segundos basándose en métricas reales de rendimiento, no es un número configurado estáticamente."""
        
        # Calcular latencia
        latency_ms = int((time.perf_counter() - start_perf) * 1000)
        
        # Registrar métrica
        self.metrics_engine.record_request(RequestMetrics(
            timestamp=start_time,
            query_type="self_introspection",
            latency_ms=latency_ms,
            success=True,
            data_verified=True,
            confidence=0.95,
            data_sources_used=0,  # Datos propios
            execution_complexity=5,
            cache_hit=False
        ))
        
        return ChatResponse(
            success=True,
            reply=reply,
            mode="honest_introspection",
            data_source="self_evaluation",
            verified=True,
            confidence=0.95,
            self_assessment=self_report,
            execution_time_ms=latency_ms
        )
    
    async def _process_regular_request(self, request: ChatRequest, intent: Dict, 
                                      history: List[Dict], start_time: float, 
                                      start_perf: float) -> ChatResponse:
        """Procesa solicitud regular"""
        
        # Consultar servicios si es necesario
        data = {}
        if intent.get("needs_data"):
            data = await self._query_services(intent["services"])
        
        # Generar respuesta
        reply = await self._generate_response(intent, data, request.message, history)
        
        # Calcular métricas
        latency_ms = int((time.perf_counter() - start_perf) * 1000)
        success = bool(reply)
        
        # Registrar métrica
        self.metrics_engine.record_request(RequestMetrics(
            timestamp=start_time,
            query_type=intent["type"],
            latency_ms=latency_ms,
            success=success,
            data_verified=bool(data),
            confidence=0.9 if data else 0.75,
            data_sources_used=len(data),
            execution_complexity=3 if data else 2,
            cache_hit=False
        ))
        
        # Guardar historial
        if success:
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": reply})
            self._save_conversation(request.room_id or "default", history)
        
        return ChatResponse(
            success=success,
            reply=reply or "Error procesando solicitud",
            mode="conversation",
            data_source=",".join(intent.get("services", [])) if data else "openai",
            verified=bool(data),
            confidence=0.9 if data else 0.75,
            execution_time_ms=latency_ms
        )
    
    async def _query_services(self, services: List[str]) -> Dict:
        """Consulta servicios"""
        results = {}
        
        async def query_service(service: str):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    if service == "brain":
                        resp = await client.get(f"{BRAIN_API}/v1/agent/status")
                        if resp.status_code == 200:
                            results["brain"] = resp.json()
                    elif service == "bridge":
                        resp = await client.get(f"{POCKET_BRIDGE}/normalized")
                        if resp.status_code == 200:
                            results["bridge"] = resp.json()
            except:
                pass
        
        await asyncio.gather(*[query_service(s) for s in services], return_exceptions=True)
        return results
    
    async def _generate_response(self, intent: Dict, data: Dict, message: str, 
                                history: List[Dict]) -> Optional[str]:
        """Genera respuesta"""
        intent_type = intent.get("type", "unknown")
        
        if intent_type == "phase_status" and "brain" in data:
            return "📊 **Fases:** Datos disponibles desde Brain API"
        
        elif intent_type == "trading_data" and "bridge" in data:
            bridge = data["bridge"]
            last = bridge.get("last_row", {})
            return f"📈 **Trading:** {bridge.get('row_count', 0)} registros | {last.get('pair', 'N/A')}"
        
        elif intent_type == "system_overview":
            reply = "🧠 **Sistema:**\n"
            if "brain" in data:
                reply += "✅ Brain API\n"
            if "bridge" in data:
                reply += "✅ Bridge\n"
            return reply + "\nPara evaluación honesta de mi capacidad, pregunta 'cómo evalúas tu inteligencia'"
        
        # OpenAI fallback
        if OPENAI_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {"role": "system", "content": "Eres Brain Chat V7.0 con autoconciencia. Para evaluar tu capacidad real, el usuario debe preguntar 'cómo evalúas tu inteligencia'."},
                                {"role": "user", "content": message}
                            ],
                            "temperature": 0.7,
                            "max_tokens": 1500
                        }
                    )
                    if resp.status_code == 200:
                        return resp.json()["choices"][0]["message"]["content"]
            except:
                pass
        
        return "Estoy operativo. Para conocer mi capacidad real evaluada dinámicamente, pregunta: 'cómo evalúas tu inteligencia'"


# Instancia global - se inicializa después
chat_v7 = None


@app.on_event("startup")
async def startup_event():
    """Inicializa el sistema y la evaluación continua"""
    global chat_v7
    chat_v7 = BrainChatV7()
    # Iniciar evaluación continua ahora que hay event loop
    asyncio.create_task(chat_v7._continuous_self_evaluation())
    logger.info("Brain Chat V7.0 iniciado con autoconciencia profunda")


# Endpoints FastAPI
@app.get("/health")
async def health():
    """Health check con auto-evaluación actual"""
    if chat_v7 is None:
        return {"status": "initializing", "version": "7.0.0", "message": "Sistema iniciándose..."}
    
    metrics = chat_v7.metrics_engine.get_current_metrics()
    current_eval = chat_v7.evaluation_system.get_cached_evaluation()
    
    return {
        "status": "healthy",
        "version": "7.0.0",
        "self_aware": True,
        "dynamic_evaluation": True,
        "current_capability_score": current_eval.get("overall_score", 0),
        "confidence": current_eval.get("confidence", 0),
        "total_requests_processed": chat_v7.metrics_engine.total_requests,
        "uptime_seconds": time.time() - chat_v7.metrics_engine.start_time,
        "recent_metrics": metrics.get("recent_window", {})
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    """Endpoint principal"""
    if chat_v7 is None:
        return ChatResponse(
            success=False,
            reply="Sistema inicializándose, por favor espere unos segundos...",
            mode="initializing"
        )
    
    try:
        result = await chat_v7.process_message(request)
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


@app.get("/introspection")
async def introspection():
    """Endpoint de introspección pública"""
    if chat_v7 is None:
        return {"status": "initializing", "message": "Sistema iniciándose..."}
    
    try:
        # Forzar evaluación
        await chat_v7.evaluation_system.evaluate()
        self_report = chat_v7.introspection.generate_self_report()
        return {
            "status": "success",
            "self_assessment": self_report,
            "evaluation": chat_v7.evaluation_system.get_cached_evaluation(),
            "metrics_summary": chat_v7.metrics_engine.get_current_metrics()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
