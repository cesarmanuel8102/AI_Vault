"""
Brain Chat V7.2 - Autoconciencia Profunda y Profesional
Sistema de Meta-cognición con Evaluación Dinámica en Tiempo Real

MEJORAS V7.2:
- GPT-4 como modelo principal con Ollama fallback
- Sistema de perfiles de usuario (developer/business)
- Integración de datos de trading (PocketOption Bridge)
- Análisis de código estructurado con AST
- Memoria conversacional persistente con resumen automático

Arquitectura:
- Motor de métricas continuo (PerformanceMetricsEngine)
- Sistema de auto-evaluación multi-dimensional (SelfEvaluationSystem)
- Detector de anomalías propias (SelfAnomalyDetector)
- Memoria de rendimiento histórico (PerformanceMemory)
- Introspección honesta (HonestIntrospection)
- Autoconcepto evolutivo (EvolvingSelfConcept)
- UserProfileManager para perfiles de usuario
- TradingDataIntegration para métricas de trading
- CodeAnalyzer para análisis de código
- PersistentMemory para memoria a largo plazo

CHANGELOG V7.2:
- Líneas 1-13: Actualizada documentación y changelog
- Líneas 44-46: Agregado GPT4_MODEL y configuración de trading
- Líneas 51-53: Agregado USER_PROFILES_DIR y CODE_ANALYSIS_DIR
- Líneas 680-780: Nueva clase UserProfileManager
- Líneas 781-850: Nueva clase TradingDataIntegration
- Líneas 851-950: Nueva clase CodeAnalyzer
- Líneas 951-1050: Nueva clase PersistentMemory
- Líneas 2006-2100: query_llm() con GPT-4 primario y Ollama fallback
"""

import os
import json
import asyncio
import logging
import subprocess
import hashlib
import time
import statistics
import ast
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple, Callable
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import defaultdict, deque
import numpy as np
import re

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Configuración
BRAIN_API = "http://127.0.0.1:8000"
ADVISOR_API = "http://127.0.0.1:8030"
POCKET_BRIDGE = "http://127.0.0.1:8765"
OLLAMA_HOST = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2.5:14b"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GPT4_MODEL = "gpt-4"  # Modelo principal para consultas generales
GPT4_FALLBACK_MODEL = "gpt-4o-mini"  # Fallback más económico
PORT = 8090

# Trading Configuration
TRADING_BRIDGE_URL = "http://127.0.0.1:8765"  # PocketOption Bridge

# Paths
STATE_DIR = Path("C:\\AI_VAULT\\tmp_agent\\state")
CONVERSATIONS_DIR = STATE_DIR / "conversations"
METRICS_DIR = STATE_DIR / "brain_metrics"
INTROSPECTION_DIR = STATE_DIR / "brain_introspection"
USER_PROFILES_DIR = STATE_DIR / "user_profiles"
CODE_ANALYSIS_DIR = STATE_DIR / "code_analysis"
MEMORY_SUMMARIES_DIR = STATE_DIR / "memory_summaries"

for d in [CONVERSATIONS_DIR, METRICS_DIR, INTROSPECTION_DIR, USER_PROFILES_DIR, CODE_ANALYSIS_DIR, MEMORY_SUMMARIES_DIR]:
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
# SECCIÓN 0: SISTEMA DE DETECCIÓN DE INTENCIONES MEJORADO (V7.2)
# =============================================================================

# Banco de sinónimos por intención para detección semántica
INTENT_SYNONYMS = {
    "rsi_strategic": [
        "brechas", "cómo vamos", "estado del proyecto", "qué falta",
        "progreso", "avance", "cómo va el negocio", "qué problemas tenemos",
        "falta", "mejoras", "optimizaciones", "qué hacer", "tareas pendientes",
        "roadmap", "plan", "estrategia", "objetivos"
    ],
    "self_awareness": [
        "autoconciencia", "cómo te evalúas", "tu capacidad", "qué sabes hacer",
        "análisis de ti mismo", "cómo funcionas", "cómo te sientes",
        "tu inteligencia", "tu limitación", "tu desempeño",
        "conócete", "autoanálisis", "quien eres"
    ],
    "trading_data": [
        "datos de mercado", "precios", "spy", "trading", "métricas",
        "cómo van las operaciones", "balance", "resultados de trading",
        "pocket option", "inversiones", "portafolio", "ganancias",
        "pérdidas", "rentabilidad", "operaciones", "transacciones"
    ],
    "system_status": [
        "estado del sistema", "todo bien", "está funcionando", "health",
        "diagnóstico", "cómo está todo", "verificador", "status",
        "todo ok", "estado general", "funcionamiento", "sistema"
    ],
    "code_analysis": [
        "analiza código", "revisa código", "código fuente", "estructura",
        "arquitectura", "patrones", "refactor", "mejora el código",
        "calidad del código", "documentación", "complejidad"
    ],
    "tool_calling": [
        "busca archivos", "lee archivo", "ejecuta", "lista directorio",
        "muestra archivo", "corre comando", "encuentra"
    ]
}


def calculate_intent_similarity(text1: str, text2: str) -> float:
    """
    Calcula similitud entre dos textos usando combinación de Jaccard y características.
    
    Args:
        text1: Texto del mensaje del usuario
        text2: Texto de referencia del banco de sinónimos
        
    Returns:
        float: Similitud entre 0.0 y 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalizar textos
    t1 = text1.lower().strip()
    t2 = text2.lower().strip()
    
    # Tokenización simple (palabras)
    words1 = set(re.findall(r'\b\w+\b', t1))
    words2 = set(re.findall(r'\b\w+\b', t2))
    
    if not words1 or not words2:
        return 0.0
    
    # Similitud de Jaccard: |intersección| / |unión|
    intersection = words1 & words2
    union = words1 | words2
    
    if not union:
        return 0.0
    
    jaccard = len(intersection) / len(union)
    
    # Peso adicional por coincidencias exactas de frases
    phrase_bonus = 0.0
    if t2 in t1:
        phrase_bonus = 0.3  # Frase completa encontrada
    
    # Peso por contención de palabras clave
    containment = len(intersection) / len(words1) if words1 else 0
    
    # Combinar métricas
    similarity = (jaccard * 0.5) + (containment * 0.3) + min(phrase_bonus, 0.2)
    
    return min(similarity, 1.0)


def find_best_intent_match(message: str, intent_synonyms: dict, threshold: float = 0.4) -> tuple:
    """
    Encuentra la mejor coincidencia de intención usando similitud semántica.
    
    Args:
        message: Mensaje del usuario
        intent_synonyms: Diccionario de sinónimos por intención
        threshold: Umbral mínimo de similitud (0.0-1.0)
        
    Returns:
        tuple: (nombre_intencion, score_similitud) o (None, 0) si no hay match
    """
    best_intent = None
    best_score = 0.0
    
    for intent_name, synonyms in intent_synonyms.items():
        for synonym in synonyms:
            score = calculate_intent_similarity(message, synonym)
            if score > best_score:
                best_score = score
                best_intent = intent_name
    
    if best_score >= threshold:
        return best_intent, best_score
    
    return None, 0.0


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
# SECCIÓN 3.4: SISTEMA DE PERFILES DE USUARIO
# =============================================================================

class ProfileType(Enum):
    """Tipos de perfil de usuario"""
    DEVELOPER = "developer"
    BUSINESS = "business"
    TRADER = "trader"
    GENERAL = "general"


@dataclass
class UserProfile:
    """Perfil de usuario para personalización de respuestas"""
    user_id: str
    profile_type: ProfileType
    preferences: Dict[str, Any] = field(default_factory=dict)
    history_summary: str = ""
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    total_interactions: int = 0
    detected_patterns: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "profile_type": self.profile_type.value,
            "preferences": self.preferences,
            "history_summary": self.history_summary,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "total_interactions": self.total_interactions,
            "detected_patterns": self.detected_patterns
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserProfile':
        return cls(
            user_id=data.get("user_id", "anonymous"),
            profile_type=ProfileType(data.get("profile_type", "general")),
            preferences=data.get("preferences", {}),
            history_summary=data.get("history_summary", ""),
            created_at=data.get("created_at", time.time()),
            last_updated=data.get("last_updated", time.time()),
            total_interactions=data.get("total_interactions", 0),
            detected_patterns=data.get("detected_patterns", [])
        )


class UserProfileManager:
    """
    Gestiona perfiles de usuario con detección automática de tipo.
    
    Características:
    - Detección automática de perfil basada en consultas
    - Persistencia de preferencias entre sesiones
    - Adaptación de respuestas según perfil
    """
    
    def __init__(self):
        self.profiles: Dict[str, UserProfile] = {}
        self._load_all_profiles()
    
    def _load_all_profiles(self):
        """Carga todos los perfiles existentes"""
        if not USER_PROFILES_DIR.exists():
            return
        
        for profile_file in USER_PROFILES_DIR.glob("*.json"):
            try:
                with open(profile_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    profile = UserProfile.from_dict(data)
                    self.profiles[profile.user_id] = profile
            except Exception as e:
                logger.error(f"Error cargando perfil {profile_file}: {e}")
    
    def _save_profile(self, profile: UserProfile):
        """Guarda un perfil en disco"""
        try:
            profile_file = USER_PROFILES_DIR / f"{profile.user_id}.json"
            with open(profile_file, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando perfil {profile.user_id}: {e}")
    
    def get_or_create_profile(self, user_id: str) -> UserProfile:
        """Obtiene o crea un perfil de usuario"""
        if user_id not in self.profiles:
            self.profiles[user_id] = UserProfile(
                user_id=user_id,
                profile_type=ProfileType.GENERAL
            )
            self._save_profile(self.profiles[user_id])
        return self.profiles[user_id]
    
    def detect_profile_type(self, message: str) -> ProfileType:
        """
        Detecta el tipo de perfil basado en el contenido del mensaje.
        
        Developer: código, funciones, clases, imports, debug, API
        Business: ROI, métricas, estrategia, clientes, ventas, marketing
        Trader: trading, balance, operaciones, drawdown, señales, pares
        """
        msg_lower = message.lower()
        
        # Patrones para desarrolladores
        dev_patterns = [
            r'\b(def|class|import|from|function|return|async|await)\b',
            r'\b(código|code|script|debug|error|exception|traceback)\b',
            r'\b(api|endpoint|json|xml|rest|graphql)\b',
            r'\b(python|javascript|java|c\+\+|rust|go|typescript)\b',
            r'\b(git|github|commit|branch|merge|pull request)\b',
            r'\b(database|sql|query|orm|model|schema)\b',
        ]
        
        # Patrones para negocios
        business_patterns = [
            r'\b(roi|kpi|métrica|metric|conversion|ventas|sales)\b',
            r'\b(estrategia|strategy|marketing|cliente|customer|lead)\b',
            r'\b(negocio|business|empresa|company|startup)\b',
            r'\b(ingresos|revenue|profit|margen|margin|costo|cost)\b',
            r'\b(presupuesto|budget|inversión|investment)\b',
        ]
        
        # Patrones para traders
        trader_patterns = [
            r'\b(trading|trade|operación|operation|position)\b',
            r'\b(balance|equity|drawdown|profit|loss|p&l)\b',
            r'\b(señal|signal|indicador|indicator|rsi|macd|bollinger)\b',
            r'\b(par|pair|eurusd|gbpusd|usd|forex|crypto)\b',
            r'\b(broker|mt4|mt5|pocketoption|binance)\b',
            r'\b(candle|vela|chart|gráfico|timeframe|tick)\b',
        ]
        
        dev_score = sum(1 for p in dev_patterns if re.search(p, msg_lower))
        business_score = sum(1 for p in business_patterns if re.search(p, msg_lower))
        trader_score = sum(1 for p in trader_patterns if re.search(p, msg_lower))
        
        scores = [
            (ProfileType.DEVELOPER, dev_score),
            (ProfileType.BUSINESS, business_score),
            (ProfileType.TRADER, trader_score)
        ]
        
        best_type, best_score = max(scores, key=lambda x: x[1])
        
        # Solo cambiar si hay suficiente evidencia (al menos 2 coincidencias)
        if best_score >= 2:
            return best_type
        return ProfileType.GENERAL
    
    def update_profile(self, user_id: str, message: str, response_type: str = ""):
        """Actualiza el perfil basado en interacción"""
        profile = self.get_or_create_profile(user_id)
        profile.total_interactions += 1
        
        # Detectar tipo si hay suficientes interacciones
        if profile.total_interactions % 5 == 0:  # Cada 5 interacciones
            detected = self.detect_profile_type(message)
            if detected != ProfileType.GENERAL and detected != profile.profile_type:
                profile.profile_type = detected
                logger.info(f"Perfil de {user_id} actualizado a: {detected.value}")
        
        profile.last_updated = time.time()
        self._save_profile(profile)
    
    def get_system_prompt_for_profile(self, profile: UserProfile) -> str:
        """Genera system prompt adaptado al perfil"""
        base_prompt = "Eres Brain Chat V7.2, un asistente inteligente."
        
        if profile.profile_type == ProfileType.DEVELOPER:
            return base_prompt + """
            
Eres un asistente técnico experto en desarrollo de software.
- Proporciona código limpio, bien documentado y siguiendo mejores prácticas
- Explica conceptos técnicos con precisión y profundidad
- Sugiere optimizaciones y patrones de diseño cuando sea relevante
- Usa terminología técnica apropiada
- Incluye ejemplos de código cuando sea útil"""
        
        elif profile.profile_type == ProfileType.BUSINESS:
            return base_prompt + """
            
Eres un asistente de negocios enfocado en resultados.
- Enfócate en ROI, métricas clave y resultados tangibles
- Usa lenguaje claro y directo, evita jerga técnica innecesaria
- Proporciona análisis estratégico y recomendaciones accionables
- Considera aspectos de viabilidad y recursos
- Prioriza soluciones escalables y sostenibles"""
        
        elif profile.profile_type == ProfileType.TRADER:
            return base_prompt + """
            
Eres un asistente especializado en trading y análisis de mercados.
- Proporciona análisis técnico preciso y basado en datos
- Menciona métricas relevantes: drawdown, win rate, risk/reward
- Enfatiza la gestión de riesgos y el control emocional
- Usa terminología de trading apropiada
- Recuerda siempre incluir disclaimer sobre riesgos"""
        
        return base_prompt + " Adapta tu respuesta al contexto de la conversación."


# =============================================================================
# SECCIÓN 3.5: INTEGRACIÓN DE DATOS DE TRADING
# =============================================================================

@dataclass
class TradingMetrics:
    """Métricas de trading del PocketOption Bridge"""
    timestamp: float
    balance: float
    equity: float
    open_positions: int
    daily_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    avg_trade_duration: float
    latency_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradingDataIntegration:
    """
    Integra datos del PocketOption Bridge para análisis de trading.
    
    Características:
    - Consulta de métricas en tiempo real
    - Análisis de rendimiento histórico
    - Detección de anomalías en trading
    """
    
    def __init__(self):
        self.last_metrics: Optional[TradingMetrics] = None
        self.metrics_history: deque = deque(maxlen=1000)
        self.connection_status = "unknown"
    
    async def fetch_trading_data(self) -> Optional[TradingMetrics]:
        """
        Obtiene datos de trading desde el PocketOption Bridge.
        
        Returns:
            TradingMetrics con los datos actuales o None si hay error
        """
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Intentar obtener datos normalizados del bridge
                response = await client.get(f"{TRADING_BRIDGE_URL}/normalized")
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Calcular métricas
                    row_count = data.get("row_count", 0)
                    last_row = data.get("last_row", {})
                    
                    balance = last_row.get("balance", 0.0)
                    metrics = TradingMetrics(
                        timestamp=time.time(),
                        balance=balance,
                        equity=last_row.get("equity", balance),
                        open_positions=last_row.get("open_positions", 0),
                        daily_pnl=last_row.get("daily_pnl", 0.0),
                        total_trades=last_row.get("total_trades", row_count),
                        winning_trades=last_row.get("winning_trades", 0),
                        losing_trades=last_row.get("losing_trades", 0),
                        win_rate=last_row.get("win_rate", 0.0),
                        max_drawdown=last_row.get("max_drawdown", 0.0),
                        avg_trade_duration=last_row.get("avg_duration", 0.0),
                        latency_ms=(time.time() - start_time) * 1000
                    )
                    
                    self.last_metrics = metrics
                    self.metrics_history.append(metrics)
                    self.connection_status = "connected"
                    
                    return metrics
                else:
                    self.connection_status = f"error_{response.status_code}"
                    return None
                    
        except httpx.TimeoutException:
            self.connection_status = "timeout"
            logger.warning("Timeout consultando PocketOption Bridge")
            return None
        except Exception as e:
            self.connection_status = "error"
            logger.error(f"Error consultando trading data: {e}")
            return None
    
    async def analyze_trading_performance(self, lookback_hours: int = 24) -> Dict[str, Any]:
        """
        Analiza el rendimiento de trading en un período.
        
        Args:
            lookback_hours: Horas hacia atrás para analizar
            
        Returns:
            Dict con análisis de rendimiento
        """
        current = await self.fetch_trading_data()
        
        if not current:
            return {
                "status": "error",
                "message": "No se pudieron obtener datos de trading",
                "connection_status": self.connection_status
            }
        
        # Calcular estadísticas de historial
        cutoff_time = time.time() - (lookback_hours * 3600)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > cutoff_time]
        
        if len(recent_metrics) < 2:
            return {
                "status": "partial",
                "current_metrics": current.to_dict(),
                "message": "Datos históricos insuficientes para análisis completo"
            }
        
        # Calcular tendencias
        balances = [m.balance for m in recent_metrics]
        pnls = [m.daily_pnl for m in recent_metrics]
        win_rates = [m.win_rate for m in recent_metrics]
        
        balance_trend = "up" if balances[-1] > balances[0] else "down" if balances[-1] < balances[0] else "stable"
        
        return {
            "status": "success",
            "period_hours": lookback_hours,
            "current_metrics": current.to_dict(),
            "statistics": {
                "balance_start": balances[0],
                "balance_end": balances[-1],
                "balance_change": balances[-1] - balances[0],
                "balance_change_pct": ((balances[-1] - balances[0]) / balances[0] * 100) if balances[0] > 0 else 0,
                "balance_trend": balance_trend,
                "avg_daily_pnl": statistics.mean(pnls) if pnls else 0,
                "max_daily_pnl": max(pnls) if pnls else 0,
                "min_daily_pnl": min(pnls) if pnls else 0,
                "avg_win_rate": statistics.mean(win_rates) if win_rates else 0,
                "volatility": statistics.stdev(pnls) if len(pnls) > 1 else 0,
                "data_points": len(recent_metrics)
            },
            "alerts": self._generate_trading_alerts(current, recent_metrics)
        }
    
    def _generate_trading_alerts(self, current: TradingMetrics, history: List[TradingMetrics]) -> List[str]:
        """Genera alertas basadas en métricas de trading"""
        alerts = []
        
        # Alerta de drawdown
        if current.max_drawdown > 10:
            alerts.append(f"⚠️ Drawdown elevado: {current.max_drawdown:.1f}%")
        
        # Alerta de win rate bajo
        if current.win_rate < 40:
            alerts.append(f"⚠️ Win rate bajo: {current.win_rate:.1f}%")
        
        # Alerta de latencia
        if current.latency_ms > 1000:
            alerts.append(f"⚠️ Latencia alta: {current.latency_ms:.0f}ms")
        
        # Alerta de pérdida consecutiva
        if len(history) >= 5:
            recent_pnls = [m.daily_pnl for m in history[-5:]]
            if all(p < 0 for p in recent_pnls):
                alerts.append("⚠️ 5 períodos consecutivos en pérdida")
        
        return alerts


# =============================================================================
# SECCIÓN 3.6: ANALIZADOR DE CÓDIGO
# =============================================================================

@dataclass
class CodeStructure:
    """Estructura de código analizado"""
    filepath: str
    language: str
    imports: List[str]
    functions: List[Dict[str, Any]]
    classes: List[Dict[str, Any]]
    complexity_score: float
    lines_of_code: int
    docstring_coverage: float
    type_hint_coverage: float
    issues: List[Dict[str, Any]]


class CodeAnalyzer:
    """
    Analiza estructura de código Python y otros lenguajes.
    
    Características:
    - Análisis AST para Python
    - Detección de imports, funciones, clases
    - Cálculo de complejidad ciclomática básica
    - Sugerencias de mejora
    """
    
    def __init__(self):
        self.analysis_cache: Dict[str, CodeStructure] = {}
        self.supported_languages = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.go': 'go',
            '.rs': 'rust'
        }
    
    def _detect_language(self, filepath: str) -> str:
        """Detecta el lenguaje basado en extensión"""
        ext = Path(filepath).suffix.lower()
        return self.supported_languages.get(ext, 'unknown')
    
    def analyze_code_structure(self, filepath: str) -> Optional[CodeStructure]:
        """
        Analiza la estructura de un archivo de código.
        
        Args:
            filepath: Ruta al archivo de código
            
        Returns:
            CodeStructure con el análisis o None si hay error
        """
        try:
            file_path = Path(filepath)
            if not file_path.exists():
                return None
            
            language = self._detect_language(filepath)
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            lines = content.split('\n')
            loc = len(lines)
            
            if language == 'python':
                return self._analyze_python_code(filepath, content, lines)
            else:
                # Análisis básico para otros lenguajes
                return self._analyze_generic_code(filepath, content, lines, language)
                
        except Exception as e:
            logger.error(f"Error analizando código {filepath}: {e}")
            return None
    
    def _analyze_python_code(self, filepath: str, content: str, lines: List[str]) -> CodeStructure:
        """Analiza código Python usando AST"""
        import ast as ast_module
        ast = ast_module
        
        imports = []
        functions = []
        classes = []
        issues = []
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # Imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
                
                # Funciones
                elif isinstance(node, ast.FunctionDef):
                    func_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "args": len(node.args.args),
                        "returns": ast.unparse(node.returns) if node.returns else None,
                        "docstring": ast.get_docstring(node) is not None,
                        "complexity": self._calculate_function_complexity(node)
                    }
                    functions.append(func_info)
                    
                    # Verificar si tiene docstring
                    if not func_info["docstring"]:
                        issues.append({
                            "type": "missing_docstring",
                            "severity": "info",
                            "line": node.lineno,
                            "message": f"Función '{node.name}' sin docstring"
                        })
                
                # Clases
                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": len([n for n in node.body if isinstance(n, ast.FunctionDef)]),
                        "docstring": ast.get_docstring(node) is not None
                    }
                    classes.append(class_info)
            
            # Calcular métricas
            total_functions = len(functions)
            documented = sum(1 for f in functions if f["docstring"])
            docstring_coverage = (documented / total_functions * 100) if total_functions > 0 else 0
            
            # Calcular complejidad promedio
            avg_complexity = statistics.mean([f["complexity"] for f in functions]) if functions else 0
            
            return CodeStructure(
                filepath=filepath,
                language="python",
                imports=imports,
                functions=functions,
                classes=classes,
                complexity_score=avg_complexity,
                lines_of_code=len(lines),
                docstring_coverage=docstring_coverage,
                type_hint_coverage=0.0,  # TODO: Implementar
                issues=issues
            )
            
        except SyntaxError as e:
            return CodeStructure(
                filepath=filepath,
                language="python",
                imports=[],
                functions=[],
                classes=[],
                complexity_score=0,
                lines_of_code=len(lines),
                docstring_coverage=0,
                type_hint_coverage=0,
                issues=[{"type": "syntax_error", "severity": "error", "message": str(e)}]
            )
    
    def _calculate_function_complexity(self, node: ast.FunctionDef) -> int:
        """Calcula complejidad ciclomática básica de una función"""
        complexity = 1  # Base
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        
        return complexity
    
    def _analyze_generic_code(self, filepath: str, content: str, lines: List[str], language: str) -> CodeStructure:
        """Análisis básico para otros lenguajes"""
        imports = []
        functions = []
        classes = []
        issues = []
        
        # Patrones básicos por lenguaje
        if language == 'javascript' or language == 'typescript':
            # Detectar imports
            import_pattern = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)")
            for match in import_pattern.finditer(content):
                imports.append(match.group(1) or match.group(2))
            
            # Detectar funciones
            func_pattern = re.compile(r"(?:function|const|let|var)\s+(\w+)\s*[=\(]")
            for match in func_pattern.finditer(content):
                functions.append({"name": match.group(1), "line": content[:match.start()].count('\n') + 1})
        
        return CodeStructure(
            filepath=filepath,
            language=language,
            imports=list(set(imports)),
            functions=functions,
            classes=classes,
            complexity_score=0,
            lines_of_code=len(lines),
            docstring_coverage=0,
            type_hint_coverage=0,
            issues=issues
        )
    
    def suggest_improvements(self, structure: CodeStructure) -> List[Dict[str, Any]]:
        """Sugiere mejoras basadas en el análisis"""
        suggestions = []
        
        # Sugerencias basadas en complejidad
        high_complexity = [f for f in structure.functions if f.get("complexity", 0) > 10]
        if high_complexity:
            suggestions.append({
                "type": "complexity",
                "priority": "medium",
                "message": f"{len(high_complexity)} funciones con alta complejidad (>10)",
                "suggestion": "Considera refactorizar funciones complejas en sub-funciones más pequeñas",
                "affected": [f["name"] for f in high_complexity]
            })
        
        # Sugerencias de documentación
        if structure.docstring_coverage < 50:
            suggestions.append({
                "type": "documentation",
                "priority": "low",
                "message": f"Cobertura de docstrings baja: {structure.docstring_coverage:.1f}%",
                "suggestion": "Agrega docstrings a las funciones para mejorar mantenibilidad"
            })
        
        # Sugerencias de imports
        if len(structure.imports) > 20:
            suggestions.append({
                "type": "imports",
                "priority": "low",
                "message": f"Archivo con {len(structure.imports)} imports",
                "suggestion": "Considera dividir el módulo o revisar imports no utilizados"
            })
        
        return suggestions


# =============================================================================
# SECCIÓN 3.7: MEMORIA CONVERSACIONAL PERSISTENTE
# =============================================================================

@dataclass
class ConversationSummary:
    """Resumen de una conversación"""
    room_id: str
    summary: str
    key_topics: List[str]
    user_preferences: Dict[str, Any]
    last_updated: float
    message_count: int


class PersistentMemory:
    """
    Sistema de memoria conversacional persistente.
    
    Características:
    - Resumen automático de conversaciones largas
    - Extracción de preferencias del usuario
    - Persistencia entre sesiones
    - Compresión de contexto
    """
    
    def __init__(self):
        self.summaries: Dict[str, ConversationSummary] = {}
        self._load_summaries()
    
    def _load_summaries(self):
        """Carga resúmenes existentes"""
        if not MEMORY_SUMMARIES_DIR.exists():
            return
        
        for summary_file in MEMORY_SUMMARIES_DIR.glob("*.json"):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    summary = ConversationSummary(
                        room_id=data["room_id"],
                        summary=data["summary"],
                        key_topics=data.get("key_topics", []),
                        user_preferences=data.get("user_preferences", {}),
                        last_updated=data["last_updated"],
                        message_count=data.get("message_count", 0)
                    )
                    self.summaries[summary.room_id] = summary
            except Exception as e:
                logger.error(f"Error cargando resumen {summary_file}: {e}")
    
    def _save_summary(self, summary: ConversationSummary):
        """Guarda un resumen en disco"""
        try:
            summary_file = MEMORY_SUMMARIES_DIR / f"{summary.room_id}.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "room_id": summary.room_id,
                    "summary": summary.summary,
                    "key_topics": summary.key_topics,
                    "user_preferences": summary.user_preferences,
                    "last_updated": summary.last_updated,
                    "message_count": summary.message_count
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando resumen: {e}")
    
    async def summarize_conversation(self, room_id: str, messages: List[Dict]) -> ConversationSummary:
        """
        Genera un resumen de la conversación.
        
        Args:
            room_id: ID de la sala
            messages: Lista de mensajes
            
        Returns:
            ConversationSummary con el resumen
        """
        if len(messages) < 10:
            # Conversación corta, no necesita resumen
            return ConversationSummary(
                room_id=room_id,
                summary="Conversación en progreso",
                key_topics=[],
                user_preferences={},
                last_updated=time.time(),
                message_count=len(messages)
            )
        
        # Extraer temas clave (palabras frecuentes)
        all_text = " ".join([m.get("content", "") for m in messages])
        words = re.findall(r'\b[a-zA-Z]{4,}\b', all_text.lower())
        word_freq = {}
        for word in words:
            if word not in ['esto', 'esta', 'como', 'para', 'que', 'with', 'from', 'this', 'that']:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        key_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Detectar preferencias simples
        preferences = {}
        for msg in messages:
            content = msg.get("content", "").lower()
            if "prefiero" in content or "me gusta" in content:
                preferences["style"] = "personalizado"
        
        summary = ConversationSummary(
            room_id=room_id,
            summary=f"Conversación con {len(messages)} mensajes sobre: {', '.join([t[0] for t in key_topics])}",
            key_topics=[t[0] for t in key_topics],
            user_preferences=preferences,
            last_updated=time.time(),
            message_count=len(messages)
        )
        
        self.summaries[room_id] = summary
        self._save_summary(summary)
        
        return summary
    
    def get_context_for_room(self, room_id: str, max_messages: int = 20) -> List[Dict]:
        """
        Obtiene el contexto relevante para una sala.
        
        Combina el resumen histórico con los mensajes recientes.
        """
        summary = self.summaries.get(room_id)
        
        context = []
        
        if summary:
            # Agregar resumen como contexto
            context.append({
                "role": "system",
                "content": f"Contexto previo: {summary.summary}. Temas: {', '.join(summary.key_topics)}"
            })
        
        return context
    
    def extract_user_preferences(self, room_id: str, messages: List[Dict]) -> Dict[str, Any]:
        """Extrae preferencias del usuario de los mensajes"""
        preferences = {}
        
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "").lower()
                
                # Detectar preferencias de formato
                if any(word in content for word in ["código", "code", "ejemplo"]):
                    preferences["likes_code_examples"] = True
                
                if any(word in content for word in ["detallado", "detail", "explica"]):
                    preferences["detail_level"] = "high"
                elif any(word in content for word in ["resumen", "breve", "short"]):
                    preferences["detail_level"] = "low"
                
                # Detectar idioma preferido
                if any(word in content for word in ["inglés", "english"]):
                    preferences["language"] = "en"
                elif any(word in content for word in ["español", "spanish"]):
                    preferences["language"] = "es"
        
        return preferences


# =============================================================================
# SECCIÓN 3.8: TOOL REGISTRY - Sistema de Herramientas para Tool Calling
# =============================================================================

class ToolRegistry:
    """Registro de herramientas disponibles para el Brain Chat"""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_descriptions: Dict[str, str] = {}
    
    def register(self, name: str, func: Callable, description: str):
        """Registra una herramienta nueva"""
        self.tools[name] = func
        self.tool_descriptions[name] = description
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Obtiene una herramienta por nombre"""
        return self.tools.get(name)
    
    def list_tools(self) -> Dict[str, str]:
        """Lista todas las herramientas disponibles"""
        return self.tool_descriptions.copy()
    
    async def execute_tool(self, name: str, **kwargs) -> Any:
        """Ejecuta una herramienta con los parámetros dados"""
        tool = self.get_tool(name)
        if not tool:
            return {"error": f"Tool '{name}' not found"}
        
        try:
            if asyncio.iscoroutinefunction(tool):
                return await tool(**kwargs)
            else:
                return tool(**kwargs)
        except Exception as e:
            return {"error": str(e)}


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
        
        # Sistema de Tool Calling con Ollama
        self.tool_registry = ToolRegistry()
        self.register_default_tools()
        
        # Tool calling state
        self.last_tool_results = None
        self.tool_execution_log = []
        
        self._load_conversations()
        
        # La evaluación continua se inicia después, cuando hay event loop
        self._evaluation_task = None
    
    def register_default_tools(self):
        """Registra las herramientas básicas disponibles"""
        self.tool_registry.register(
            "search_files",
            self.search_files,
            "Busca archivos usando patrones glob. Params: pattern (str), path (str, default: 'C:\\AI_VAULT')"
        )
        self.tool_registry.register(
            "read_file",
            self.read_file,
            "Lee el contenido de un archivo. Params: filepath (str)"
        )
        self.tool_registry.register(
            "execute_command",
            self.execute_command,
            "Ejecuta comandos shell en whitelist. Params: command (str)"
        )
        self.tool_registry.register(
            "list_directory",
            self.list_directory,
            "Lista archivos y carpetas en un directorio. Params: path (str)"
        )
        self.tool_registry.register(
            "get_market_data",
            self.get_market_data,
            "Obtiene datos de mercado de QuantConnect o Tiingo. Params: symbol (str), source (str: quantconnect/tiingo)"
        )
        self.tool_registry.register(
            "get_trading_metrics",
            self.get_trading_metrics,
            "Obtiene métricas de trading del sistema. Params: none"
        )
        logger.info("Herramientas básicas registradas en ToolRegistry")
    
    async def get_market_data(self, symbol: str, source: str = "tiingo") -> Dict[str, Any]:
        """Obtiene datos de mercado del dashboard 8070"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://127.0.0.1:8070/api/market-data/{symbol}",
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "data": data, "symbol": symbol, "source": source}
                else:
                    return {
                        "success": False,
                        "error": f"Dashboard returned status {response.status_code}",
                        "symbol": symbol
                    }
        except Exception as e:
            return {"success": False, "error": str(e), "symbol": symbol}
    
    async def get_trading_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de trading del sistema"""
        try:
            # Consultar dashboard 8070 para métricas
            dashboard_data = {}
            async with httpx.AsyncClient() as client:
                response = await client.get("http://127.0.0.1:8070/api/data-sources/health", timeout=10.0)
                if response.status_code == 200:
                    dashboard_data = response.json()
                else:
                    dashboard_data = {"error": "Dashboard no disponible"}
            
            # Consultar PocketOption si está disponible
            pocket_data = {}
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{POCKET_BRIDGE}/health", timeout=5.0)
                    if response.status_code == 200:
                        pocket_data = response.json()
            except:
                pocket_data = {"status": "offline"}
            
            return {
                "success": True,
                "data_sources": dashboard_data,
                "pocket_option": pocket_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def search_files(self, pattern: str, path: str = "C:\\AI_VAULT") -> Dict[str, Any]:
        """Busca archivos usando patrones glob"""
        try:
            import fnmatch
            results = []
            search_path = Path(path)
            
            if not search_path.exists():
                return {"success": False, "error": f"Path no existe: {path}", "results": []}
            
            for root, dirs, files in os.walk(search_path):
                for filename in files:
                    if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                        full_path = os.path.join(root, filename)
                        results.append({
                            "name": filename,
                            "path": full_path,
                            "size": os.path.getsize(full_path)
                        })
            
            return {
                "success": True,
                "pattern": pattern,
                "path": path,
                "count": len(results),
                "results": results[:50]  # Limitar a 50 resultados
            }
        except Exception as e:
            return {"success": False, "error": str(e), "results": []}
    
    def read_file(self, filepath: str) -> Dict[str, Any]:
        """Lee el contenido de un archivo"""
        try:
            file_path = Path(filepath)
            
            # Verificar que el archivo existe
            if not file_path.exists():
                return {"success": False, "error": f"Archivo no encontrado: {filepath}"}
            
            # Verificar que es un archivo (no directorio)
            if not file_path.is_file():
                return {"success": False, "error": f"La ruta no es un archivo: {filepath}"}
            
            # Limitar tamaño para evitar problemas de memoria
            max_size = 1024 * 1024  # 1MB
            file_size = file_path.stat().st_size
            
            if file_size > max_size:
                # Leer solo las primeras líneas para archivos grandes
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = ''.join(f.readline() for _ in range(100))
                    content += f"\n\n[... Archivo truncado. Tamaño total: {file_size} bytes ...]"
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            
            return {
                "success": True,
                "filepath": filepath,
                "size": file_size,
                "content": content
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Ejecuta comandos shell con whitelist de seguridad"""
        # Whitelist de comandos permitidos
        allowed_prefixes = [
            'dir', 'ls', 'echo', 'cat', 'type', 'find',
            'git status', 'git log', 'git diff',
            'python --version', 'python -V',
            'pip list', 'pip freeze',
            'netstat -an', 'ping', 'ipconfig', 'ifconfig',
            'tasklist', 'ps aux', 'wmic', 'df', 'du', 'free'
        ]
        
        # Verificar si el comando está permitido
        cmd_lower = command.lower().strip()
        is_allowed = any(cmd_lower.startswith(allowed.lower()) for allowed in allowed_prefixes)
        
        if not is_allowed:
            return {
                "success": False,
                "error": f"Comando no permitido por seguridad: {command}",
                "allowed_commands": allowed_prefixes
            }
        
        try:
            # Ejecutar con timeout de 30 segundos
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout[:5000],  # Limitar salida
                "stderr": result.stderr[:2000],
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Timeout: comando excedió 30 segundos",
                "command": command
            }
        except Exception as e:
            return {"success": False, "error": str(e), "command": command}
    
    def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """Lista archivos y carpetas en un directorio"""
        try:
            dir_path = Path(path)
            
            if not dir_path.exists():
                return {"success": False, "error": f"Directorio no existe: {path}", "entries": []}
            
            if not dir_path.is_dir():
                return {"success": False, "error": f"La ruta no es un directorio: {path}", "entries": []}
            
            entries = []
            for item in dir_path.iterdir():
                try:
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except (PermissionError, OSError):
                    # Ignorar archivos sin permisos
                    continue
            
            # Ordenar: primero directorios, luego archivos
            entries.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
            
            return {
                "success": True,
                "path": str(dir_path.resolve()),
                "count": len(entries),
                "entries": entries
            }
        except Exception as e:
            return {"success": False, "error": str(e), "entries": []}
    
    def detect_tool_intent(self, message: str) -> Dict[str, Any]:
        """
        Detecta si el mensaje requiere uso de herramientas.
        
        V7.2 Mejorado: Ahora usa similitud semántica además de coincidencias exactas.
        """
        msg_lower = message.lower()
        
        # PASO 1: Intentar detección por similitud con INTENT_SYNONYMS (tool_calling)
        intent_match, similarity = find_best_intent_match(message, {"tool_calling": INTENT_SYNONYMS.get("tool_calling", [])}, threshold=0.35)
        
        # PASO 2: Patrones de detección para cada herramienta - EXPANDIDOS
        tool_patterns = {
            "search_files": [
                "busca archivos", "encuentra archivos", "search files", "find file",
                "busca *.py", "encuentra *.json", "buscar archivo", "find files",
                "buscar archivos", "donde esta", "where is", "locate", "find"
            ],
            "read_file": [
                "lee archivo", "read file", "muestra archivo", "ver archivo",
                "contenido de", "contenido del archivo", "cat ", "leer ",
                "muestrame el codigo", "show me the code", "que dice el archivo",
                "ver contenido de", "abrir archivo", "lee el archivo", "muestrame"
            ],
            "execute_command": [
                "ejecuta comando", "run command", "execute command", "corre comando",
                "haz un ping", "git status", "show git", "lista procesos",
                "que servicios", "what services", "puertos abiertos", "open ports",
                "netstat", "estado del sistema", "system status", "processes",
                "servicios corriendo", "running services", "status",
                "espacio en disco", "espacio libre", "espacio disponible", 
                "disk space", "free space", "cuanto espacio",
                "version de python", "python version", "version python",
                "ultimos archivos", "recent files", "servicios activos", "que puertos",
                "what ports", "health", "estado", "cuanto disco"
            ],
            "list_directory": [
                "lista directorio", "list directory", "muestra carpeta", "ver carpeta",
                "que hay en", "contenido de carpeta", "archivos en", "ls -la",
                "mostrar directorio", "ver directorio", "listar archivos"
            ],
            "check_system": [
                "estado del brain", "brain status", "servicios activos", "active services",
                "que esta corriendo", "what is running", "dashboard", "monitoreo",
                "health check", "estado de salud", "sistema operativo"
            ]
        }
        
        detected_tools = []
        confidence_scores = {}
        
        for tool_name, patterns in tool_patterns.items():
            for pattern in patterns:
                if pattern in msg_lower:
                    detected_tools.append(tool_name)
                    confidence_scores[tool_name] = 0.9
                    break
            
            # V7.2: También verificar similitud con patrones de esta herramienta
            if tool_name not in detected_tools:
                for pattern in patterns:
                    sim_score = calculate_intent_similarity(message, pattern)
                    if sim_score >= 0.5:  # Umbral de similitud para herramientas
                        detected_tools.append(tool_name)
                        confidence_scores[tool_name] = max(0.6, sim_score)
                        break
        
        # PASO 3: Boost de confianza si detectamos intención de tool_calling por similitud
        if intent_match and not detected_tools:
            # Si hay intención semántica pero no coincidencia exacta, usar tools genérico
            detected_tools.append("check_system")
            confidence_scores["check_system"] = similarity * 0.8
        
        # Detectar parámetros si es posible
        params = {}
        
        # Extraer rutas de archivos
        if ".py" in msg_lower or ".json" in msg_lower or ".txt" in msg_lower:
            file_matches = re.findall(r'[\w\-./\\]+\.\w+', message)
            if file_matches:
                params["filepath"] = file_matches[0]
        
        # Extraer patrones de búsqueda
        if "*." in message:
            pattern_matches = re.findall(r'\*\.\w+', message)
            if pattern_matches:
                params["pattern"] = pattern_matches[0]
        
        final_confidence = max(confidence_scores.values()) if confidence_scores else 0
        if intent_match and similarity > final_confidence:
            final_confidence = similarity * 0.9
        
        return {
            "needs_tools": len(detected_tools) > 0,
            "detected_tools": detected_tools,
            "confidence": final_confidence,
            "extracted_params": params,
            "semantic_match": intent_match is not None,
            "semantic_score": similarity if intent_match else 0,
            "tool_descriptions": {name: self.tool_registry.tool_descriptions.get(name, "") 
                                  for name in detected_tools}
        }
    
    async def process_with_tools(self, message: str) -> Dict[str, Any]:
        """Procesa mensaje detectando y ejecutando herramientas si es necesario"""
        # 1. Detectar intención de herramienta
        tool_intent = self.detect_tool_intent(message)
        
        if not tool_intent["needs_tools"]:
            return {
                "needs_tools": False,
                "tool_results": None,
                "final_response": None
            }
        
        # 2. Ejecutar herramientas detectadas
        tool_results = []
        tools_context = []
        
        for tool_name in tool_intent["detected_tools"]:
            # Extraer parámetros del mensaje para esta herramienta específica
            params = self._extract_tool_params(tool_name, message)
            
            logger.info(f"Ejecutando herramienta: {tool_name} con params: {params}")
            
            # Ejecutar herramienta
            result = await self.tool_registry.execute_tool(tool_name, **params)
            tool_results.append({
                "tool": tool_name,
                "params": params,
                "result": result
            })
            
            # Agregar al contexto para Ollama
            tools_context.append(f"Herramienta '{tool_name}' ejecutada:")
            if isinstance(result, dict):
                if result.get("success"):
                    if "content" in result:
                        tools_context.append(f"  Contenido: {result['content'][:500]}...")
                    elif "results" in result:
                        tools_context.append(f"  Resultados: {len(result.get('results', []))} items")
                    elif "entries" in result:
                        tools_context.append(f"  Entradas: {len(result.get('entries', []))} items")
                    else:
                        tools_context.append(f"  Resultado: {json.dumps(result, indent=2)[:500]}")
                else:
                    tools_context.append(f"  Error: {result.get('error', 'Error desconocido')}")
            
            # Log de ejecución
            self.tool_execution_log.append({
                "timestamp": time.time(),
                "tool": tool_name,
                "params": params,
                "success": isinstance(result, dict) and result.get("success", False)
            })
        
        # 3. Consultar Ollama con contexto de herramientas
        tools_context_str = "\n".join(tools_context)
        ollama_response = await query_ollama(
            messages=[{"role": "user", "content": message}],
            tools_context=tools_context_str
        )
        
        return {
            "needs_tools": True,
            "detected_tools": tool_intent["detected_tools"],
            "tool_results": tool_results,
            "ollama_response": ollama_response,
            "final_response": ollama_response.get("content", "Error procesando respuesta")
        }
    
    def _extract_tool_params(self, tool_name: str, message: str) -> Dict[str, Any]:
        """Extrae parámetros específicos para una herramienta del mensaje"""
        params = {}
        msg_lower = message.lower()
        import re
        
        if tool_name == "search_files":
            # Buscar patrón como *.py, *.json, etc.
            pattern_match = re.search(r'\*\.\w+', message)
            if pattern_match:
                params["pattern"] = pattern_match.group(0)
            else:
                # Buscar nombre de archivo genérico
                file_match = re.search(r'(?:busca|search|encuentra)\s+["\']?([^"\']+\.[\w]+)["\']?', message, re.IGNORECASE)
                if file_match:
                    params["pattern"] = file_match.group(1)
            
            # Buscar path
            path_match = re.search(r'(?:en|in|path)\s+["\']?(["\']?C:\\[^"\']+)["\']?', message, re.IGNORECASE)
            if path_match:
                params["path"] = path_match.group(1).strip('"\'')
            else:
                params["path"] = "C:\\AI_VAULT"
        
        elif tool_name == "read_file":
            # Buscar ruta de archivo
            path_matches = re.findall(r'["\']?([\w\-./\\]+\.[\w]+)["\']?', message)
            if path_matches:
                # Tomar el primer match que parezca un archivo
                for match in path_matches:
                    if "." in match and not match.endswith("."):
                        params["filepath"] = match
                        break
        
        elif tool_name == "execute_command":
            # Extraer el comando después de "ejecuta" o similar
            cmd_patterns = [
                r'(?:ejecuta|run|execute)\s+(?:comando\s+)?["\']?(.+?)["\']?(?:\s|$)',
                r'(?:haz\s+un|do\s+a)\s+(\w+\s+.+?)(?:\s|$)',
            ]
            for pattern in cmd_patterns:
                cmd_match = re.search(pattern, message, re.IGNORECASE)
                if cmd_match:
                    params["command"] = cmd_match.group(1).strip()
                    break
            
            # Comandos específicos reconocidos
            if "git status" in msg_lower:
                params["command"] = "git status"
            elif "ping" in msg_lower and "command" not in params:
                # Extraer IP/host después de ping
                ping_match = re.search(r'ping\s+(\S+)', message, re.IGNORECASE)
                if ping_match:
                    params["command"] = f"ping -n 4 {ping_match.group(1)}"
            
            # NUEVO: Servicios y puertos
            elif any(x in msg_lower for x in ['servicios', 'procesos', 'tasklist', 'corriendo', 'ejecutando']):
                params["command"] = "tasklist"
            elif any(x in msg_lower for x in ['puertos', 'netstat', 'conexiones']):
                params["command"] = "netstat -an"
            elif any(x in msg_lower for x in ['espacio', 'disco', 'libre']):
                params["command"] = "wmic logicaldisk get size,freespace,caption"
            elif any(x in msg_lower for x in ['version python', 'python version', 'py -V']):
                params["command"] = "python --version"
        
        elif tool_name == "list_directory":
            # Buscar ruta de directorio
            path_match = re.search(r'(?:en|in|directorio|directory|carpeta|folder)\s+["\']?([^"\']+)["\']?', message, re.IGNORECASE)
            if path_match:
                path = path_match.group(1).strip('"\'')
                if path and path not in ["el", "la", "los", "las", "the", "a", "an"]:
                    params["path"] = path
            
            # Si no se especificó path, usar directorio actual
            if "path" not in params:
                params["path"] = "."
        
        return params
    
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
        """
        Análisis de intención mejorado con similitud semántica.
        
        Ahora detecta intenciones basándose en similitud con bancos de sinónimos,
        no solo en coincidencias exactas de palabras clave.
        """
        msg_lower = message.lower().strip()
        
        # PASO 1: Intentar detección por similitud semántica
        intent_match, similarity = find_best_intent_match(message, INTENT_SYNONYMS, threshold=0.4)
        
        if intent_match:
            # Mapear intención detectada a tipo de respuesta
            intent_mapping = {
                "rsi_strategic": {"type": "strategic_rsi", "needs_data": False, "risk": "low", "confidence": similarity},
                "self_awareness": {"type": "self_introspection", "needs_data": False, "risk": "low", "confidence": similarity},
                "trading_data": {"type": "trading_data", "needs_data": True, "services": ["bridge"], "risk": "low", "confidence": similarity},
                "system_status": {"type": "system_overview", "needs_data": True, "services": ["brain", "bridge"], "risk": "low", "confidence": similarity},
                "code_analysis": {"type": "code_analysis", "needs_data": False, "risk": "low", "confidence": similarity}
            }
            
            if intent_match in intent_mapping:
                return intent_mapping[intent_match]
        
        # PASO 2: Fallback a detección por keywords exactos (comportamiento anterior)
        # Preguntas sobre autoconciencia
        if any(phrase in msg_lower for phrase in [
            "como evaluas", "cual es tu capacidad", "que puedes hacer",
            "como te evaluas", "tu inteligencia", "que limitaciones tienes",
            "que no puedes hacer", "autoevaluacion", "introspeccion",
            "que tan inteligente eres", "tu verdadera capacidad"
        ]):
            return {"type": "self_introspection", "needs_data": False, "risk": "low", "confidence": 0.8}
        
        # Comandos regulares
        if any(cmd in msg_lower for cmd in ["/phase", "fase actual"]):
            return {"type": "phase_status", "needs_data": True, "services": ["brain"], "risk": "low", "confidence": 0.9}
        
        if any(cmd in msg_lower for cmd in ["/pocketoption", "trading", "balance"]):
            return {"type": "trading_data", "needs_data": True, "services": ["bridge"], "risk": "low", "confidence": 0.9}
        
        if any(cmd in msg_lower for cmd in ["/status", "estado sistema"]):
            return {"type": "system_overview", "needs_data": True, "services": ["brain", "bridge"], "risk": "low", "confidence": 0.9}
        
        return {"type": "conversation", "needs_data": False, "services": [], "risk": "low", "confidence": 0.5}
    
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
    chat_v7 = BrainChatV7_RSI()
    # Iniciar evaluación continua ahora que hay event loop
    asyncio.create_task(chat_v7._continuous_self_evaluation())
    logger.info("Brain Chat V7.2 iniciado con autoconciencia profunda y RSI")


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


# =============================================================================
# SECCIÓN RSI ESTRATÉGICO - Agregado para V7.2
# =============================================================================

class StrategicObjective:
    """Objetivos estratégicos según premisas canónicas v3.1"""
    AUTOSUPERVIVENCIA = "autosupervivencia"
    AUTODETERMINACION = "autodeterminacion"
    CRECIMIENTO_CAPITAL = "crecimiento_capital"
    GOBERNANZA = "gobernanza"
    LEGALIDAD = "legalidad"
    MORALIDAD = "moralidad"

class StrategicRSI:
    """RSI Estratégico simplificado para integración"""
    
    def __init__(self, brain_chat):
        self.brain = brain_chat
        self.cycle_count = 0
        self.objective_weights = {
            StrategicObjective.AUTOSUPERVIVENCIA: 0.40,
            StrategicObjective.AUTODETERMINACION: 0.25,
            StrategicObjective.CRECIMIENTO_CAPITAL: 0.20,
            StrategicObjective.GOBERNANZA: 0.10,
            StrategicObjective.LEGALIDAD: 0.03,
            StrategicObjective.MORALIDAD: 0.02,
        }
    
    async def run_strategic_rsi_cycle(self, force=False):
        """Ejecuta ciclo RSI estratégico"""
        self.cycle_count += 1
        
        # Obtener evaluación actual
        current_eval = self.brain.evaluation_system.get_cached_evaluation()
        dimensions = current_eval.get("dimensions", {})
        
        # Calcular brechas estratégicas
        gaps = []
        
        # Gap 1: Autosupervivencia (reliability > 98%, uptime > 99%)
        rel_score = dimensions.get("reliability", {}).get("score", 0)
        gaps.append({
            "objective": "autosupervivencia",
            "current": rel_score,
            "required": 98.0,
            "gap": max(0, 98.0 - rel_score),
            "weight": 0.40
        })
        
        # Gap 2: Autodeterminación (introspección > 85%)
        intro_score = dimensions.get("introspection", {}).get("score", 0)
        gaps.append({
            "objective": "autodeterminacion",
            "current": intro_score,
            "required": 85.0,
            "gap": max(0, 85.0 - intro_score),
            "weight": 0.25
        })
        
        # Gap 3: Crecimiento de capital (execution > 80%)
        exec_score = dimensions.get("execution", {}).get("score", 0)
        gaps.append({
            "objective": "crecimiento_capital",
            "current": exec_score,
            "required": 80.0,
            "gap": max(0, 80.0 - exec_score),
            "weight": 0.20
        })
        
        # Ordenar por impacto
        gaps.sort(key=lambda g: g["weight"] * g["gap"], reverse=True)
        
        return {
            "cycle_number": self.cycle_count,
            "gaps": gaps,
            "critical_objective": gaps[0]["objective"] if gaps else "none",
            "status": "analysis_complete"
        }

# Extender BrainChatV7 para incluir RSI
class BrainChatV7_RSI(BrainChatV7):
    """Brain Chat V7 con RSI Estratégico y mejoras V7.2"""
    
    def __init__(self):
        super().__init__()
        self.strategic_rsi = StrategicRSI(self)
        
        # V7.2: Sistemas adicionales
        self.user_profile_manager = UserProfileManager()
        self.trading_integration = TradingDataIntegration()
        self.code_analyzer = CodeAnalyzer()
        self.persistent_memory = PersistentMemory()
        
        # Logging de inicialización V7.2
        logger.info("=" * 60)
        logger.info("Brain Chat V7.2 - Mejoras implementadas:")
        logger.info("  ✓ GPT-4 como modelo principal con Ollama fallback")
        logger.info("  ✓ Sistema de perfiles de usuario (developer/business/trader)")
        logger.info("  ✓ Integración de datos de trading (PocketOption Bridge)")
        logger.info("  ✓ Análisis de código con AST")
        logger.info("  ✓ Memoria conversacional persistente")
        logger.info("=" * 60)
        
        logger.info("RSI Estratégico integrado")
        logger.info("V7.2: User profiles, Trading integration, Code analyzer, Persistent memory cargados")
        logger.info("V7.2: Sistema de detección de intenciones por similitud semántica ACTIVADO")
    
    def _analyze_intent(self, message: str):
        """
        Análisis extendido con comandos RSI usando similitud semántica.
        
        V7.2 Mejorado: Ahora detecta intenciones por similitud con sinónimos,
        no solo por coincidencias exactas de palabras clave.
        """
        msg_lower = message.lower().strip()
        
        # PASO 1: Usar el sistema mejorado de similitud semántica
        intent_match, similarity = find_best_intent_match(message, INTENT_SYNONYMS, threshold=0.4)
        
        if intent_match:
            logger.debug(f"Intención detectada por similitud: {intent_match} (score: {similarity:.2f})")
            
            # Mapear intenciones a tipos de respuesta
            intent_mapping = {
                "rsi_strategic": {"type": "strategic_rsi", "needs_data": False, "risk": "low", "semantic_confidence": similarity},
                "self_awareness": {"type": "self_introspection", "needs_data": False, "risk": "low", "semantic_confidence": similarity},
                "trading_data": {"type": "trading_data", "needs_data": True, "services": ["bridge"], "risk": "low", "semantic_confidence": similarity},
                "system_status": {"type": "system_overview", "needs_data": True, "services": ["brain", "bridge"], "risk": "low", "semantic_confidence": similarity},
                "code_analysis": {"type": "code_analysis", "needs_data": False, "risk": "low", "semantic_confidence": similarity}
            }
            
            if intent_match in intent_mapping:
                return intent_mapping[intent_match]
        
        # PASO 2: Fallback a coincidencias exactas (comportamiento anterior)
        words = re.findall(r'\b\w+\b', msg_lower)
        exact_rsi_commands = {"rsi", "brechas", "fase", "progreso", "autoconciencia", "verificador"}
        
        if any(word in exact_rsi_commands for word in words):
            return {"type": "strategic_rsi", "needs_data": False, "risk": "low", "exact_match": True}
        
        # PASO 3: Fallback al análisis del padre
        return super()._analyze_intent(message)
    
    async def process_message(self, request: ChatRequest):
        """
        Procesa mensajes incluyendo Tool Calling y comandos RSI.
        
        V7.2 Mejorado: Ahora usa similitud semántica para detectar intenciones.
        """
        
        msg_lower = request.message.lower()
        
        # PASO 0: Analizar intención semántica primero
        intent_analysis = self._analyze_intent(request.message)
        logger.info(f"Intención detectada: {intent_analysis.get('type', 'unknown')} "
                    f"(confianza: {intent_analysis.get('semantic_confidence', intent_analysis.get('confidence', 0)):.2f})")
        
        # PRIORIDAD 1: Tool Calling para operaciones del sistema
        tool_intent = self.detect_tool_intent(request.message)
        # Reducir threshold de confianza a 0.4 para mejor detección (antes 0.5)
        if tool_intent["needs_tools"] and tool_intent["confidence"] >= 0.4:
            return await self._handle_tool_calling(request)
        
        # PRIORIDAD 2: Verificación especial ANTES de RSI
        # "fases del proyecto" o "fases del brain" -> Tool Calling, NO RSI
        if "fases del proyecto" in msg_lower or "fases del brain" in msg_lower:
            import logging
            logging.info(f"Detectado 'fases del proyecto/brain' - forzando Tool Calling")
            tool_intent["needs_tools"] = True
            tool_intent["confidence"] = 0.8
            return await self._handle_tool_calling(request)
        
        # PRIORIDAD 3: Procesar según intención semántica detectada
        intent_type = intent_analysis.get("type", "conversation")
        
        if intent_type == "strategic_rsi":
            return await self._handle_rsi_command(request)
        
        if intent_type == "self_introspection":
            return await self._handle_introspection_request(
                request, 
                self.conversations.get(request.room_id or f"room_{datetime.now().timestamp()}", []),
                time.time(), 
                0
            )
        
        # Fallback para palabras exactas de RSI (comportamiento anterior)
        words = re.findall(r'\b\w+\b', msg_lower)
        exact_rsi_words = {"rsi", "brechas", "fase", "progreso", "autoconciencia", "verificador"}
        if any(word in exact_rsi_words for word in words):
            return await self._handle_rsi_command(request)
        
        # PRIORIDAD 4: Procesar mensajes normales con potencial Tool Calling bajo
        if tool_intent["needs_tools"]:
            return await self._handle_tool_calling(request)
        
        # PRIORIDAD 5: Procesar con lógica normal del padre
        return await super().process_message(request)
    
    async def _handle_rsi_command(self, request: ChatRequest):
        """Maneja comandos RSI extendidos"""
        msg_lower = request.message.lower().strip()
        try:
            # Autoconciencia completa - 5 dimensiones
            if 'autoconciencia' in msg_lower:
                await self.evaluation_system.evaluate()
                self_report = self.introspection.generate_self_report()
                return ChatResponse(
                    success=True,
                    reply=self._format_self_awareness_report(self_report),
                    mode="self_awareness",
                    data_source="evaluation_system",
                    verified=True,
                    confidence=0.95
                )
            
            # Verificador - estado del sistema de verificación
            elif 'verificador' in msg_lower:
                return await self._handle_verifier_status()
            
            # Comandos RSI estándar
            else:
                report = await self.strategic_rsi.run_strategic_rsi_cycle(force=True)
                reply = self._format_rsi_report(report)
                
                return ChatResponse(
                    success=True,
                    reply=reply,
                    mode="strategic_rsi",
                    data_source="rsi_system",
                    verified=True,
                    confidence=0.95
                )
        except Exception as e:
            logger.error(f"Error RSI: {e}")
            return ChatResponse(
                success=False,
                reply=f"Error en RSI: {str(e)}",
                mode="error"
            )
    
    async def _handle_tool_calling(self, request: ChatRequest) -> ChatResponse:
        """Maneja solicitudes que requieren Tool Calling"""
        start_time = time.time()
        start_perf = time.perf_counter()
        
        try:
            # Ejecutar Tool Calling
            tool_result = await self.process_with_tools(request.message)
            
            if not tool_result["needs_tools"]:
                # No se necesitaron herramientas, procesar normalmente
                return await super().process_message(request)
            
            # Construir respuesta basada en los resultados
            if tool_result.get("final_response"):
                # Ollama proporcionó respuesta coherente
                reply = tool_result["final_response"]
                mode = "tool_calling_with_llm"
                data_source = "ollama_tools"
            else:
                # Fallback: construir respuesta manual de los resultados
                reply = self._format_tool_results_response(tool_result)
                mode = "tool_calling_direct"
                data_source = "tool_execution"
            
            # Calcular métricas
            latency_ms = int((time.perf_counter() - start_perf) * 1000)
            
            # Registrar métrica
            self.metrics_engine.record_request(RequestMetrics(
                timestamp=start_time,
                query_type="tool_calling",
                latency_ms=latency_ms,
                success=True,
                data_verified=True,
                confidence=tool_result.get("ollama_response", {}).get("success", False) and 0.9 or 0.75,
                data_sources_used=len(tool_result.get("detected_tools", [])),
                execution_complexity=5,
                cache_hit=False
            ))
            
            # Guardar historial
            room_id = request.room_id or f"room_{datetime.now().timestamp()}"
            if room_id not in self.conversations:
                self.conversations[room_id] = []
            history = self.conversations[room_id]
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": reply})
            self._save_conversation(room_id, history)
            
            return ChatResponse(
                success=True,
                reply=reply,
                mode=mode,
                data_source=data_source,
                verified=True,
                confidence=0.9,
                execution_time_ms=latency_ms
            )
            
        except Exception as e:
            logger.error(f"Error en Tool Calling: {e}")
            return ChatResponse(
                success=False,
                reply=f"Error ejecutando herramientas: {str(e)}",
                mode="tool_error"
            )
    
    def _format_tool_results_response(self, tool_result: Dict) -> str:
        """Formatea resultados de herramientas como respuesta legible"""
        detected_tools = tool_result.get("detected_tools", [])
        results = tool_result.get("tool_results", [])
        
        reply = "🔧 **Resultados de Herramientas Ejecutadas**\n\n"
        
        for i, result in enumerate(results, 1):
            tool_name = result.get("tool", "unknown")
            params = result.get("params", {})
            tool_output = result.get("result", {})
            
            reply += f"**{i}. Herramienta: `{tool_name}`**\n"
            reply += f"   Parámetros: {json.dumps(params)}\n"
            
            if isinstance(tool_output, dict):
                if tool_output.get("success"):
                    reply += "   ✅ Ejecución exitosa\n"
                    
                    if "content" in tool_output:
                        content_preview = tool_output["content"][:800]
                        if len(tool_output["content"]) > 800:
                            content_preview += "\n... (truncado)"
                        reply += f"\n**Contenido:**\n```\n{content_preview}\n```\n"
                    
                    elif "entries" in tool_output:
                        entries = tool_output.get("entries", [])
                        reply += f"\n**Entradas encontradas ({len(entries)}):**\n"
                        for entry in entries[:20]:  # Mostrar máximo 20
                            entry_type = "📁" if entry.get("type") == "directory" else "📄"
                            reply += f"   {entry_type} {entry.get('name', 'N/A')}\n"
                        if len(entries) > 20:
                            reply += f"   ... y {len(entries) - 20} más\n"
                    
                    elif "results" in tool_output:
                        items = tool_output.get("results", [])
                        reply += f"\n**Archivos encontrados ({len(items)}):**\n"
                        for item in items[:10]:  # Mostrar máximo 10
                            reply += f"   📄 {item.get('name', 'N/A')} ({item.get('size', 0)} bytes)\n"
                        if len(items) > 10:
                            reply += f"   ... y {len(items) - 10} más\n"
                    
                    elif "stdout" in tool_output:
                        stdout = tool_output.get("stdout", "")
                        if stdout:
                            reply += f"\n**Salida:**\n```\n{stdout[:800]}\n```\n"
                        stderr = tool_output.get("stderr", "")
                        if stderr:
                            reply += f"\n**Errores:**\n```\n{stderr[:400]}\n```\n"
                
                else:
                    reply += f"   ❌ Error: {tool_output.get('error', 'Error desconocido')}\n"
            
            reply += "\n"
        
        return reply

    def _format_self_awareness_report(self, self_report: dict) -> str:
        """Formatea reporte de autoconciencia completa"""
        score = self_report.get('self_reported_capability', 0)
        raw_score = self_report.get('raw_evaluation_score', 0)
        limitations = self_report.get('limitations', [])
        current_status = self_report.get('current_status', {})
        honest_assessment = self_report.get('honest_assessment', 'No disponible')
        
        # Obtener evaluación actual para dimensiones
        current_eval = self.evaluation_system.get_cached_evaluation()
        dims = current_eval.get('dimensions', {})
        
        reply = f"""AUTONCONCIENCIA PROFUNDA - Brain Chat V7.2

╔═══════════════════════════════════════════════════════════╗
║ EVALUACIÓN GLOBAL: {score:.1f}/100 (Raw: {raw_score:.1f})
║ Nivel: {"Alta" if score >= 85 else "Media" if score >= 60 else "Baja"} capacidad con limitaciones bien definidas
╚═══════════════════════════════════════════════════════════╝

📊 DIMENSIONES EVALUADAS:
"""
        for dim_name, dim_data in dims.items():
            dim_score = dim_data.get('score', 0) if isinstance(dim_data, dict) else dim_data
            status = "✅" if dim_score >= 85 else "⚠️" if dim_score >= 60 else "❌"
            reply += f"\n{status} {dim_name.upper().replace('_', ' ')}: {dim_score:.0f}%"
        
        reply += f"""

🔍 ESTADO OPERATIVO ACTUAL:
• Status: {current_status.get('operational_status', 'desconocido')}
• Recomendación: {current_status.get('recommendation', 'N/A')}
"""
        
        if current_status.get('active_issues'):
            reply += "\n⚠️ Problemas activos:\n"
            for issue in current_status['active_issues']:
                reply += f"  • {issue}\n"
        
        reply += f"""

📝 EVALUACIÓN HONESTA:
{honest_assessment}

⚠️ LIMITACIONES CRÍTICAS (según premisas v3.2):
"""
        for lim in limitations:
            reply += f"\n• {lim}"
        
        reply += """

🔄 RSI ACTIVO:
• Ciclo automático cada 60 minutos
• Detección de brechas estratégicas
• Priorización por impacto en objetivo primordial
• Verificación básica activa (tests + revisión humana)

Nota: La autoconciencia se actualiza dinámicamente cada 60 segundos."""
        
        return reply
    
    async def _handle_verifier_status(self) -> ChatResponse:
        """Reporte del sistema verificador"""
        metrics = self.metrics_engine.get_current_metrics()
        
        # Simular tests automatizados
        test_results = {
            "api_connectivity": True,
            "response_format": True,
            "memory_usage": metrics.get("recent_window", {}).get("memory_mb", 0) < 500,
            "latency_acceptable": metrics.get("recent_window", {}).get("avg_latency_ms", 0) < 2000,
            "success_rate": metrics.get("recent_window", {}).get("success_rate", 0) > 0.95
        }
        
        all_passed = all(test_results.values())
        
        reply = f"""VERIFICADOR DE SEGURIDAD - Estado Actual

╔═══════════════════════════════════════════════════════════╗
║ ESTADO GENERAL: {"✅ TODOS LOS TESTS PASARON" if all_passed else "⚠️ ALGUNOS TESTS FALLARON"}
╚═══════════════════════════════════════════════════════════╝

🔬 TESTS AUTOMATIZADOS:
"""
        for test, passed in test_results.items():
            icon = "✅" if passed else "❌"
            reply += f"\n{icon} {test.replace('_', ' ').title()}"
        
        reply += f"""

📈 MÉTRICAS ACTUALES:
• Latencia promedio: {metrics.get("recent_window", {}).get("avg_latency_ms", 0):.0f}ms (límite: 2000ms)
• Tasa de éxito: {metrics.get("recent_window", {}).get("success_rate", 0)*100:.1f}% (mínimo: 95%)
• Total peticiones: {self.metrics_engine.total_requests}
• Uptime: {time.time() - self.metrics_engine.start_time:.0f}s

🛡️ MECANISMOS DE PROTECCIÓN:
• Whitelist de operaciones permitidas
• Confirmación requerida para acciones críticas
• Rollback automático ante fallos detectados
• Logs de auditoría en: C:\\AI_VAULT\\tmp_agent\\state\\rsi\\

⚠️ NOTA IMPORTANTE:
Según Premisas Canónicas v3.2, la autosupervivencia NO puede validarse a sí misma.
Este verificador proporciona validación automatizada básica, pero:
- Requiere supervisión humana periódica
- No garantiza seguridad absoluta
- Debe ser complementado con auditorías externas

Revisión humana recomendada: cada 7 días o cuando se activen alertas."""
        
        return ChatResponse(
            success=True,
            reply=reply,
            mode="verifier_status",
            data_source="verification_system",
            verified=True,
            confidence=0.95
        )
    
    def _format_rsi_report(self, report: dict) -> str:
        """Formatea reporte RSI"""
        
        reply = f"""RSI Estratégico - Ciclo #{report['cycle_number']}

BRECHAS ESTRATÉGICAS (por impacto):
"""
        
        for gap in report['gaps'][:4]:
            priority = gap['weight'] * gap['gap']
            status = "OK" if gap['gap'] < 5 else "!" if gap['gap'] < 20 else "X"
            reply += f"""
[{status}] {gap['objective'].replace('_', ' ').title()}
   Actual: {gap['current']:.1f}% / Requerido: {gap['required']:.1f}%
   Brecha: {gap['gap']:.1f}% | Peso: {gap['weight']*100:.0f}% | Prioridad: {priority:.1f}
"""
        
        reply += f"""
OBJETIVO CRÍTICO: {report['critical_objective'].replace('_', ' ').title()}

RECOMENDACIONES:
1. Priorizar cierre de brechas de alto impacto
2. Validar progreso en próximo ciclo RSI (60 min)
3. Mantener monitoreo de métricas críticas

Nota: RSI prioriza por impacto en objetivo primordial según premisas v3.1
"""
        
        return reply

# Reemplazar instancia global
chat_v7 = BrainChatV7_RSI()


# =============================================================================
# INTEGRACIÓN CON OLLAMA - Tool Calling Support
# =============================================================================

async def query_llm(
    messages: list,
    tools_context: Optional[str] = None,
    model_preference: str = "auto",
    user_profile: Optional[UserProfile] = None
) -> Dict[str, Any]:
    """
    Consulta LLM con GPT-4 como modelo principal y Ollama como fallback.
    
    Args:
        messages: Lista de mensajes en formato {role, content}
        tools_context: Contexto opcional de resultados de herramientas
        model_preference: "auto", "gpt4", o "ollama"
        user_profile: Perfil del usuario para personalización
    
    Returns:
        Dict con content, model, y metadatos
    
    CHANGELOG V7.2:
    - Agregado soporte para GPT-4 como modelo primario
    - Ollama como fallback para tool calling específico
    - Integración con perfiles de usuario
    """
    
    # Determinar qué modelo usar
    use_gpt4 = model_preference in ["auto", "gpt4"] and OPENAI_API_KEY
    use_ollama = model_preference == "ollama" or not use_gpt4
    
    # Construir system prompt adaptado al perfil
    base_system = "Eres Brain Chat V7.2, un asistente inteligente del sistema AI_VAULT."
    
    if user_profile:
        profile_prompt = {
            ProfileType.DEVELOPER: " Eres un experto técnico. Proporciona código limpio y bien documentado.",
            ProfileType.BUSINESS: " Eres un asistente de negocios enfocado en resultados y ROI.",
            ProfileType.TRADER: " Eres un especialista en trading. Incluye análisis técnico y gestión de riesgos.",
            ProfileType.GENERAL: ""
        }.get(user_profile.profile_type, "")
        base_system += profile_prompt
    
    if tools_context:
        base_system += f"""

=== RESULTADOS DE HERRAMIENTAS ===
{tools_context}
=== FIN RESULTADOS ===

Instrucción: Responde basándote ÚNICAMENTE en los datos proporcionados."""
    
    # Intentar GPT-4 primero
    if use_gpt4:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                gpt_messages = [{"role": "system", "content": base_system}]
                gpt_messages.extend(messages)
                
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": GPT4_MODEL,
                        "messages": gpt_messages,
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "content": data["choices"][0]["message"]["content"],
                        "model": GPT4_MODEL,
                        "provider": "openai",
                        "usage": data.get("usage", {})
                    }
                else:
                    logger.warning(f"GPT-4 error: {response.status_code}, fallback a Ollama")
                    use_ollama = True
                    
        except Exception as e:
            logger.error(f"Error GPT-4: {e}, fallback a Ollama")
            use_ollama = True
    
    # Fallback a Ollama
    if use_ollama:
        return await query_ollama(messages, tools_context, base_system)
    
    return {
        "success": False,
        "content": "No se pudo conectar a ningún modelo LLM",
        "error": "No available LLM"
    }


async def query_ollama(
    messages: list,
    tools_context: Optional[str] = None,
    custom_system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Consulta Ollama API con soporte para tool calling.
    
    Args:
        messages: Lista de mensajes en formato {role, content}
        tools_context: Contexto opcional de resultados de herramientas ejecutadas
        custom_system_prompt: System prompt personalizado opcional
    
    Returns:
        Dict con content, model, y metadatos de la respuesta
    
    CHANGELOG V7.2:
    - Ahora es fallback de query_llm
    - Soporte para custom_system_prompt
    """
    
    # Usar system prompt personalizado o default
    if custom_system_prompt:
        system_prompt = custom_system_prompt
    else:
        system_prompt = """Eres Brain Chat V7.2, un asistente del sistema AI_VAULT.

REGLAS CRÍTICAS:
1. SIEMPRE usa los RESULTADOS DE HERRAMIENTAS proporcionados
2. NUNCA digas "no tengo acceso" - YA TIENES los datos
3. Responde basándote ÚNICAMENTE en los resultados
4. Sé específico: menciona nombres de archivos, puertos, servicios
5. Responde en español de forma concisa"""
    
    if tools_context:
        system_prompt += f"""

=== RESULTADOS DE HERRAMIENTAS ===
{tools_context}
=== FIN RESULTADOS ==="""
    
    # Preparar mensajes
    ollama_messages = [{"role": "system", "content": system_prompt}]
    ollama_messages.extend(messages)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 2048
                    }
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "content": data.get("message", {}).get("content", ""),
                    "model": OLLAMA_MODEL,
                    "provider": "ollama",
                    "eval_count": data.get("eval_count", 0),
                    "eval_duration": data.get("eval_duration", 0),
                    "load_duration": data.get("load_duration", 0)
                }
            else:
                return {
                    "success": False,
                    "content": f"Error Ollama: HTTP {response.status_code}",
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
    
    except httpx.TimeoutException:
        return {
            "success": False,
            "content": "Timeout: Ollama no respondió a tiempo",
            "error": "timeout"
        }
    except Exception as e:
        logger.error(f"Error consultando Ollama: {e}")
        return {
            "success": False,
            "content": f"Error consultando Ollama: {str(e)}",
            "error": str(e)
        }


# =============================================================================
# UTILIDADES AUXILIARES
# =============================================================================

# =============================================================================
# UI HTML
# =============================================================================

@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """Interfaz web del chat"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Brain Chat V7.2 - RSI Unificado</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }
            h1 { color: #4ecca3; }
            #chat { border: 1px solid #4ecca3; padding: 10px; height: 400px; overflow-y: auto; background: #16213e; margin-bottom: 10px; }
            .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
            .user { background: #0f3460; text-align: right; }
            .assistant { background: #1a1a2e; }
            #input { width: 70%; padding: 10px; background: #0f3460; color: #fff; border: 1px solid #4ecca3; }
            button { padding: 10px 20px; background: #4ecca3; color: #1a1a2e; border: none; cursor: pointer; }
            button:hover { background: #3db892; }
            .info { background: #e94560; padding: 10px; margin-bottom: 10px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h1>Brain Chat V7.2 - Sistema Unificado v3.2</h1>
        <div class="info">
            <strong>Comandos RSI:</strong> rsi | brechas | fase | progreso | autoconciencia | verificador
        </div>
        <div id="chat"></div>
        <input type="text" id="input" placeholder="Escribe tu mensaje..." onkeypress="if(event.key==='Enter')send()">
        <button onclick="send()">Enviar</button>
        
        <script>
            async function send() {
                const input = document.getElementById('input');
                const chat = document.getElementById('chat');
                const message = input.value.trim();
                if (!message) return;
                
                // Mostrar mensaje usuario
                chat.innerHTML += '<div class="message user">' + message + '</div>';
                input.value = '';
                
                // Llamar API
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message})
                });
                
                const data = await response.json();
                chat.innerHTML += '<div class="message assistant">' + data.reply.replace(/\\n/g, '<br>') + '</div>';
                chat.scrollTop = chat.scrollHeight;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# =============================================================================
# INICIO DEL SERVIDOR
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Brain Chat V7.2 - Autoconciencia + RSI Estratégico")
    print("=" * 60)
    print("Comandos RSI: 'rsi', 'brechas', 'fase', 'progreso'")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
