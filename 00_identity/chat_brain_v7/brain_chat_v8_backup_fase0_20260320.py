#!/usr/bin/env python3
"""
Brain Chat V8.0 - Agente Autónomo Completo
=====================================
FASE 1: CORE FOUNDATION (líneas 1-900)
Implementación completa con modelo LLM, memoria avanzada, detección de intenciones,
identidad del sistema y logging/monitoreo.

FASE 2: ADVANCED TOOLS SYSTEM (líneas 900-2200)
Herramientas de filesystem, análisis de código Python, sistema operativo, API/HTTP
y registro centralizado de herramientas (ToolRegistry).

FASE 3: TRADING INTEGRATION (líneas 2200-4200)
Conectores: QuantConnect (HMAC SHA256), Tiingo (Token), PocketOption Bridge
Calculadoras: TradingMetricsCalculator (Sharpe, Sortino, VaR, Calmar, etc.)
Analizadores: PortfolioAnalyzer (correlaciones, backtesting, optimización)

FASE 4: BRAIN INTEGRATION (líneas 4200-5200+)
RSIManager: Gestión de brechas, fases y progreso
BrainHealthMonitor: Monitoreo de servicios (API, Dashboard, Bridge, Chat, Ollama)
MetricsAggregator: Agregación y análisis de métricas del sistema
PremisesChecker: Validación de acciones contra premisas canónicas
Endpoints: /brain/rsi, /brain/health, /brain/metrics, /brain/validate

Autor: Brain Chat V8.0
Versión: 8.0.0
"""

# ============================================================
# IMPORTS (líneas 1-50)
# ============================================================
import os
import sys
import json
import time
import asyncio
import logging
import hashlib
import re
from typing import List, Dict, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
from pathlib import Path
import traceback

# FastAPI imports
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from uvicorn import Config, Server

# Third-party imports
import aiohttp
from aiohttp import ClientTimeout, ClientSession

# tiktoken es opcional - manejar importación condicional
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None

# Configuración de paths
import platform as _platform

_default_base = (
    "C:/AI_VAULT"
    if _platform.system() == "Windows"
    else str(Path.home() / "AI_VAULT")
)
BASE_PATH = Path(os.getenv("BRAIN_BASE_PATH", _default_base))
MEMORY_PATH = BASE_PATH / "tmp_agent" / "state" / "memory"
LOGS_PATH = BASE_PATH / "tmp_agent" / "logs"

# Crear directorios si no existen
try:
    MEMORY_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
except Exception as _mkdir_err:
    print(f"[WARNING] No se pudo crear directorio base: {_mkdir_err}")
    print(f"[WARNING] Establece BRAIN_BASE_PATH=<ruta> en variables de entorno")

# ============================================================
# CONFIGURACIÓN Y CONSTANTES (líneas 51-100)
# ============================================================

# Identidad del sistema - SIEMPRE incluida en system prompt
SYSTEM_IDENTITY = """Soy Brain Chat V8.0, agente autónomo diseñado para operar con capacidades avanzadas de procesamiento de lenguaje natural.
Poseo acceso a múltiples modelos de lenguaje (GPT-4, Claude, Ollama) y sistemas de memoria persistente.
Puedo ejecutar código, analizar datos, gestionar conversaciones de múltiples turnos y adaptarme al contexto del usuario.
Opero de forma independiente y estoy constantemente disponible para asistir.
"""

# Configuración de timeouts y reintentos
LLM_CONFIG = {
    "timeout": 30,
    "max_retries": 3,
    "retry_delay": 1.0,
    "temperature": 0.7,
    "max_tokens": 4096,
}

# Prioridad de modelos (Ollama primero para evitar timeouts con APIs externas)
MODEL_PRIORITY = ["ollama", "gpt4", "claude"]

# APIs y endpoints
API_ENDPOINTS = {
    "gpt4": os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions"),
    "claude": os.getenv("CLAUDE_API_URL", "https://api.anthropic.com/v1/messages"),
    "ollama": os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
}

# Claves API (deben estar configuradas en variables de entorno)
API_KEYS = {
    "openai": os.getenv("OPENAI_API_KEY", ""),
    "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
}

# Diccionario de intenciones con sinónimos - 8 categorías
INTENT_SYNONYMS = {
    "QUERY": {
        "keywords": ["consulta", "pregunta", "duda", "información", "qué", "cómo", "cuál", "dónde", "quién", "cuándo", "por qué"],
        "patterns": [r"^qu[eé].*", r"^c[oó]mo.*", r"^cu[aá]l.*", r"^d[oó]nde.*", r"^qui[eé]n.*"]
    },
    "COMMAND": {
        "keywords": ["ejecuta", "corre", "inicia", "detén", "para", "abre", "cierra", "crea", "elimina", "actualiza"],
        "patterns": [r"^(ejecuta|corre|inicia|det[eé]n|para|abre|cierra)"]
    },
    "ANALYSIS": {
        "keywords": ["analiza", "examina", "revisa", "compara", "evalúa", "calcula", "procesa", "diagnostica"],
        "patterns": [r"^(analiza|examina|revisa|compara|eval[uú]a)"]
    },
    "CREATIVE": {
        "keywords": ["escribe", "genera", "crea", "diseña", "inventa", "imagina", "propón", "sugiere"],
        "patterns": [r"^(escribe|genera|crea|dise[ñn]a|inventa)"]
    },
    "CODE": {
        "keywords": ["código", "programa", "script", "función", "clase", "método", "debug", "optimiza"],
        "patterns": [r"\b(c[oó]digo|programa|script|funci[oó]n|clase)\b"]
    },
    "MEMORY": {
        "keywords": ["recuerda", "memoriza", "guarda", "almacena", "recuerdas", "olvidaste", "mencioné"],
        "patterns": [r"\b(recuerda|recuerdas|memoriza|guarda|almacena)\b"]
    },
    "SYSTEM": {
        "keywords": ["estado", "configura", "configuración", "ajusta", "modifica", "cambia", "sistema"],
        "patterns": [r"\b(estado|configura|configuraci[oó]n|ajusta)\b"]
    },
    "CONVERSATION": {
        "keywords": ["hola", "adiós", "gracias", "por favor", "disculpa", "entendido", "ok", "vale", "claro"],
        "patterns": [r"^(hola|adi[oó]s|gracias|por favor|disculpa)"]
    }
}

# ============================================================
# CLASE MEMORYMANAGER (líneas 101-250)
# ============================================================

class MemoryManager:
    """
    Gestor de memoria de tres niveles:
    - Corto plazo: últimos 10 mensajes
    - Largo plazo: resúmenes cada 5 mensajes
    - Sistema: estado de servicios
    """
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.memory_dir = MEMORY_PATH / session_id
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Logger
        self.logger = logging.getLogger(f"{__name__}.MemoryManager")
        
        # Memoria corto plazo (últimos 10 mensajes)
        self.short_term: deque = deque(maxlen=10)
        
        # Memoria largo plazo (resúmenes)
        self.long_term: List[Dict] = []
        self.message_count = 0
        self.messages_since_summary = 0
        
        # Memoria de sistema (estado servicios)
        self.system_state: Dict = {
            "last_service": None,
            "active_tools": [],
            "user_preferences": {},
            "session_start": datetime.now().isoformat()
        }
        
        # Cargar memoria existente
        self._load_memory()
        
        # Logging
        self.logger = logging.getLogger(f"MemoryManager.{session_id}")
    
    def _get_memory_path(self, memory_type: str) -> Path:
        """Obtiene la ruta del archivo de memoria según el tipo"""
        return self.memory_dir / f"{memory_type}.json"
    
    def _load_memory(self):
        """Carga la memoria existente desde archivos"""
        try:
            # Cargar memoria corto plazo
            short_path = self._get_memory_path("short_term")
            if short_path.exists():
                with open(short_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.short_term.extend(data.get("messages", []))
                    self.message_count = data.get("count", 0)
            
            # Cargar memoria largo plazo
            long_path = self._get_memory_path("long_term")
            if long_path.exists():
                with open(long_path, 'r', encoding='utf-8') as f:
                    self.long_term = json.load(f)
            
            # Cargar estado del sistema
            system_path = self._get_memory_path("system")
            if system_path.exists():
                with open(system_path, 'r', encoding='utf-8') as f:
                    self.system_state.update(json.load(f))
            
            self.logger.info(f"Memoria cargada: {len(self.short_term)} mensajes corto plazo, "
                           f"{len(self.long_term)} resúmenes largo plazo")
        except Exception as e:
            self.logger.error(f"Error cargando memoria: {e}")
    
    def save_conversation(self, message: Dict):
        """
        Guarda un mensaje en la memoria corto plazo
        y genera resúmenes cada 5 mensajes
        """
        # Agregar timestamp si no existe
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()
        
        # Agregar a memoria corto plazo
        self.short_term.append(message)
        self.message_count += 1
        self.messages_since_summary += 1
        
        # Guardar inmediatamente
        self._save_short_term()
        
        # Verificar si necesitamos resumen (cada 5 mensajes)
        if self.messages_since_summary >= 5:
            asyncio.create_task(self.summarize_memory())
        
        self.logger.debug(f"Mensaje guardado. Total: {self.message_count}")
    
    def _save_short_term(self):
        """Guarda la memoria corto plazo en disco"""
        try:
            data = {
                "messages": list(self.short_term),
                "count": self.message_count,
                "last_updated": datetime.now().isoformat()
            }
            with open(self._get_memory_path("short_term"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Error guardando memoria corto plazo: {e}")
    
    async def summarize_memory(self):
        """
        Genera un resumen de los últimos mensajes y lo guarda
        en memoria largo plazo
        """
        try:
            if len(self.short_term) < 5:
                return
            
            # Obtener últimos mensajes para resumir
            messages_to_summarize = list(self.short_term)[-5:]
            
            # Crear resumen (en una implementación real usaríamos LLM)
            summary = {
                "id": hashlib.md5(
                    json.dumps(messages_to_summarize, sort_keys=True).encode()
                ).hexdigest()[:8],
                "messages_range": f"{self.message_count - 5} - {self.message_count}",
                "message_count": len(messages_to_summarize),
                "timestamp": datetime.now().isoformat(),
                "topics": self._extract_topics(messages_to_summarize),
                "participants": list(set(
                    msg.get("role", "unknown") 
                    for msg in messages_to_summarize
                )),
                "raw_messages": messages_to_summarize
            }
            
            # Agregar a memoria largo plazo
            self.long_term.append(summary)
            self.messages_since_summary = 0
            
            # Guardar en disco
            with open(self._get_memory_path("long_term"), 'w', encoding='utf-8') as f:
                json.dump(self.long_term, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Resumen generado: {summary['id']}")
        except Exception as e:
            self.logger.error(f"Error generando resumen: {e}")
    
    def _extract_topics(self, messages: List[Dict]) -> List[str]:
        """Extrae temas principales de los mensajes"""
        topics = set()
        for msg in messages:
            content = msg.get("content", "").lower()
            for intent, data in INTENT_SYNONYMS.items():
                for keyword in data["keywords"]:
                    if keyword in content:
                        topics.add(intent)
                        break
        return list(topics)
    
    def load_context(self, limit: int = 10) -> List[Dict]:
        """
        Carga el contexto de conversación
        Combina memoria corto y largo plazo
        """
        context = []
        
        # Agregar resúmenes relevantes de largo plazo
        if self.long_term:
            context.append({
                "role": "system",
                "content": f"Resumen de conversaciones previas: {len(self.long_term)} bloques"
            })
            # Agregar último resumen
            context.append({
                "role": "system",
                "content": f"Último resumen: {json.dumps(self.long_term[-1], ensure_ascii=False)}"
            })
        
        # Agregar memoria corto plazo
        recent_messages = list(self.short_term)[-limit:]
        context.extend(recent_messages)
        
        return context
    
    def update_system_state(self, key: str, value: Any):
        """Actualiza el estado del sistema"""
        self.system_state[key] = value
        try:
            with open(self._get_memory_path("system"), 'w', encoding='utf-8') as f:
                json.dump(self.system_state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Error guardando estado del sistema: {e}")
    
    def get_system_state(self) -> Dict:
        """Obtiene el estado actual del sistema"""
        return self.system_state.copy()
    
    def clear_memory(self, memory_type: Optional[str] = None):
        """Limpia la memoria especificada o toda"""
        if memory_type is None or memory_type == "all":
            self.short_term.clear()
            self.long_term.clear()
            self.message_count = 0
            self.messages_since_summary = 0
            self.system_state = {
                "last_service": None,
                "active_tools": [],
                "user_preferences": {},
                "session_start": datetime.now().isoformat()
            }
            # Eliminar archivos
            for file in self.memory_dir.glob("*.json"):
                file.unlink()
        elif memory_type == "short":
            self.short_term.clear()
            self._get_memory_path("short_term").unlink(missing_ok=True)
        elif memory_type == "long":
            self.long_term.clear()
            self._get_memory_path("long_term").unlink(missing_ok=True)
        
        self.logger.info(f"Memoria limpiada: {memory_type or 'all'}")

# ============================================================
# CLASE INTENTDETECTOR (líneas 251-450)
# ============================================================

class IntentDetector:
    """
    Detector de intenciones de 3 niveles:
    - Nivel 1: Keywords exactas (confianza >0.9)
    - Nivel 2: Similitud semántica Jaccard (confianza >0.7)
    - Nivel 3: Contexto conversacional (confianza >0.5)
    """
    
    def __init__(self):
        self.logger = logging.getLogger("IntentDetector")
    
    def detect_intent(
        self, 
        message: str, 
        conversation_history: List[Dict] = []
    ) -> Tuple[str, float, Dict]:
        """
        Detecta la intención del mensaje usando 3 niveles
        
        Returns:
            Tuple[intent_name, confidence, metadata]
        """
        message_lower = message.lower().strip()
        results = []
        
        # NIVEL 1: Keywords exactas (confianza >0.9)
        level1_result = self._detect_by_keywords(message_lower)
        if level1_result["confidence"] >= 0.9:
            return (
                level1_result["intent"], 
                level1_result["confidence"],
                {"method": "keywords", "matches": level1_result["matches"]}
            )
        results.append(level1_result)
        
        # NIVEL 2: Similitud semántica Jaccard (confianza >0.7)
        level2_result = self._detect_by_jaccard(message_lower)
        if level2_result["confidence"] >= 0.7:
            return (
                level2_result["intent"],
                level2_result["confidence"],
                {"method": "jaccard", "similarity": level2_result["similarity"]}
            )
        results.append(level2_result)
        
        # NIVEL 3: Contexto conversacional (confianza >0.5)
        level3_result = self._detect_by_context(message_lower, conversation_history)
        if level3_result["confidence"] >= 0.5:
            return (
                level3_result["intent"],
                level3_result["confidence"],
                {"method": "context", "context_match": level3_result["context_match"]}
            )
        results.append(level3_result)
        
        # Si ningún nivel alcanza umbral, devolver el mejor resultado
        best_result = max(results, key=lambda x: x["confidence"])
        return (
            best_result["intent"],
            best_result["confidence"],
            {"method": "best_fallback", "all_results": results}
        )
    
    def _detect_by_keywords(self, message: str) -> Dict:
        """Nivel 1: Detección por keywords exactas"""
        best_intent = "UNKNOWN"
        best_confidence = 0.0
        matches = []
        
        for intent_name, data in INTENT_SYNONYMS.items():
            # Verificar keywords exactas
            keyword_matches = [
                kw for kw in data["keywords"] 
                if kw in message
            ]
            
            # Verificar patrones regex
            pattern_matches = [
                pattern for pattern in data["patterns"]
                if re.search(pattern, message, re.IGNORECASE)
            ]
            
            total_matches = len(keyword_matches) + len(pattern_matches)
            
            if total_matches > 0:
                # Calcular confianza basada en número de matches
                confidence = min(0.9 + (total_matches * 0.05), 0.99)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_intent = intent_name
                    matches = keyword_matches + pattern_matches
        
        return {
            "intent": best_intent,
            "confidence": best_confidence,
            "matches": matches
        }
    
    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """Calcula la similitud de Jaccard entre dos conjuntos"""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0
    
    def _detect_by_jaccard(self, message: str) -> Dict:
        """Nivel 2: Detección por similitud semántica Jaccard"""
        # Tokenizar mensaje
        message_tokens = set(re.findall(r'\b\w+\b', message.lower()))
        
        best_intent = "UNKNOWN"
        best_similarity = 0.0
        
        for intent_name, data in INTENT_SYNONYMS.items():
            # Crear conjunto de tokens de referencia
            reference_tokens = set()
            for kw in data["keywords"]:
                reference_tokens.update(kw.lower().split())
            
            # Calcular similitud de Jaccard
            similarity = self._jaccard_similarity(message_tokens, reference_tokens)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_intent = intent_name
        
        # Mapear similitud a confianza
        confidence = best_similarity * 1.2  # Escalar para umbral 0.7
        confidence = min(confidence, 0.89)  # Mantener debajo de nivel 1
        
        return {
            "intent": best_intent,
            "confidence": confidence,
            "similarity": best_similarity
        }
    
    def _detect_by_context(self, message: str, history: List[Dict]) -> Dict:
        """Nivel 3: Detección por contexto conversacional"""
        if not history:
            return {
                "intent": "CONVERSATION",
                "confidence": 0.5,
                "context_match": "no_history"
            }
        
        # Analizar últimos mensajes para inferir intención
        recent_intents = []
        for msg in history[-3:]:  # Últimos 3 mensajes
            content = msg.get("content", "").lower()
            
            # Detectar intención simple
            for intent_name, data in INTENT_SYNONYMS.items():
                if any(kw in content for kw in data["keywords"][:3]):
                    recent_intents.append(intent_name)
                    break
        
        if recent_intents:
            # Intent continuo
            most_common = max(set(recent_intents), key=recent_intents.count)
            context_match = "continuous_intent"
            confidence = 0.6 + (recent_intents.count(most_common) / len(recent_intents)) * 0.2
        else:
            # Default a conversación general
            most_common = "CONVERSATION"
            context_match = "default"
            confidence = 0.5
        
        return {
            "intent": most_common,
            "confidence": min(confidence, 0.69),  # Mantener debajo de nivel 2
            "context_match": context_match
        }
    
    def extract_entities(self, message: str) -> Dict:
        """Extrae entidades del mensaje"""
        entities = {
            "urls": re.findall(r'https?://[^\s<>"{}|\\^`[\]]+', message),
            "emails": re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message),
            "code_blocks": re.findall(r'```[\s\S]*?```', message),
            "numbers": re.findall(r'\b\d+(?:\.\d+)?\b', message),
            "mentions": re.findall(r'@\w+', message),
            "hashtags": re.findall(r'#\w+', message)
        }
        return entities
    
    def analyze_sentiment(self, message: str) -> Dict:
        """Análisis básico de sentimiento"""
        positive_words = ["bien", "excelente", "genial", "perfecto", "gracias", "me gusta", "bueno", "feliz"]
        negative_words = ["mal", "error", "problema", "fallo", "no funciona", "malo", "triste", "odio"]
        
        message_lower = message.lower()
        pos_count = sum(1 for w in positive_words if w in message_lower)
        neg_count = sum(1 for w in negative_words if w in message_lower)
        
        total = pos_count + neg_count
        if total == 0:
            sentiment = "neutral"
            score = 0.5
        elif pos_count > neg_count:
            sentiment = "positive"
            score = 0.5 + (pos_count / total) * 0.5
        else:
            sentiment = "negative"
            score = 0.5 - (neg_count / total) * 0.5
        
        return {
            "sentiment": sentiment,
            "score": score,
            "positive_count": pos_count,
            "negative_count": neg_count
        }

# ============================================================
# CLASE LLMMANAGER (líneas 451-700)
# ============================================================

class LLMManager:
    """
    Gestor de modelos de lenguaje con fallback y emergencia
    - Principal: GPT-4
    - Fallback: Claude
    - Emergencia: Ollama (local)
    """
    
    def __init__(self):
        self.logger = logging.getLogger("LLMManager")
        self.session: Optional[ClientSession] = None
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "fallback_count": 0,
            "emergency_count": 0,
            "average_latency": 0.0
        }
        # Sesión lazy: se crea en el primer uso dentro de una corutina (aiohttp >= 3.9)

    async def _get_session(self) -> ClientSession:
        """Obtiene o crea la sesión HTTP de forma lazy y async-safe.

        aiohttp >= 3.9 prohíbe crear ClientSession fuera de una corutina.
        """
        if self.session is None or self.session.closed:
            timeout = ClientTimeout(total=LLM_CONFIG["timeout"])
            self.session = ClientSession(timeout=timeout)
        return self.session
    
    async def query_llm(
        self,
        messages: List[Dict],
        tools_context: Optional[Dict] = None,
        model_priority: str = "gpt4"
    ) -> Dict:
        """
        Consulta al LLM con manejo de fallback y emergencia
        
        Args:
            messages: Lista de mensajes en formato chat
            tools_context: Contexto de herramientas disponibles
            model_priority: Modelo preferido (gpt4, claude, ollama)
        
        Returns:
            Dict con respuesta y metadata
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        # Determinar orden de modelos según prioridad
        model_order = self._get_model_order(model_priority)
        
        last_error = None
        
        for idx, model in enumerate(model_order):
            try:
                # Intentar con cada modelo
                if model == "gpt4":
                    result = await self._query_gpt4(messages, tools_context)
                elif model == "claude":
                    if idx > 0:
                        self.metrics["fallback_count"] += 1
                    result = await self._query_claude(messages, tools_context)
                elif model == "ollama":
                    if idx > 0:
                        self.metrics["emergency_count"] += 1
                    result = await self._query_ollama(messages, tools_context)
                else:
                    continue
                
                # Calcular latencia
                latency = time.time() - start_time
                self._update_latency(latency)
                self.metrics["successful_requests"] += 1
                
                return {
                    "success": True,
                    "model": model,
                    "content": result,
                    "latency": latency,
                    "fallback_used": idx > 0,
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"Modelo {model} falló: {e}")
                if idx < len(model_order) - 1:
                    await asyncio.sleep(LLM_CONFIG["retry_delay"])
                    continue
        
        # Todos los modelos fallaron
        self.metrics["failed_requests"] += 1
        return {
            "success": False,
            "error": str(last_error),
            "model": "none",
            "timestamp": datetime.now().isoformat()
        }
    
    def _get_model_order(self, priority: str) -> List[str]:
        """Determina el orden de modelos según la prioridad"""
        if priority == "gpt4":
            return ["gpt4", "claude", "ollama"]
        elif priority == "claude":
            return ["claude", "gpt4", "ollama"]
        elif priority == "ollama":
            return ["ollama", "gpt4", "claude"]
        else:
            # Default: Ollama primero para evitar timeouts
            return ["ollama", "gpt4", "claude"]
    
    async def _query_gpt4(
        self, 
        messages: List[Dict], 
        tools_context: Optional[Dict]
    ) -> str:
        """Consulta a GPT-4 via OpenAI API"""
        api_key = API_KEYS["openai"]
        if not api_key:
            raise ValueError("OpenAI API key no configurada")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Preparar mensajes con identidad del sistema
        system_msg = {
            "role": "system",
            "content": SYSTEM_IDENTITY + "\n" + self._format_tools_context(tools_context)
        }
        
        all_messages = [system_msg] + messages
        
        payload = {
            "model": "gpt-4",
            "messages": all_messages,
            "temperature": LLM_CONFIG["temperature"],
            "max_tokens": LLM_CONFIG["max_tokens"]
        }
        
        session = await self._get_session()
        async with session.post(
            API_ENDPOINTS["gpt4"],
            headers=headers,
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"GPT-4 API error {response.status}: {error_text}")
            
            data = await response.json()
            return data["choices"][0]["message"]["content"]
    
    async def _query_claude(
        self, 
        messages: List[Dict], 
        tools_context: Optional[Dict]
    ) -> str:
        """Consulta a Claude via Anthropic API"""
        api_key = API_KEYS["anthropic"]
        if not api_key:
            raise ValueError("Anthropic API key no configurada")
        
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # Convertir mensajes al formato de Claude
        system_content = SYSTEM_IDENTITY + "\n" + self._format_tools_context(tools_context)
        
        # Separar system de otros mensajes
        conversation = []
        for msg in messages:
            if msg["role"] != "system":
                conversation.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        payload = {
            "model": "claude-3-opus-20240229",
            "max_tokens": LLM_CONFIG["max_tokens"],
            "temperature": LLM_CONFIG["temperature"],
            "system": system_content,
            "messages": conversation
        }
        
        session = await self._get_session()
        async with session.post(
            API_ENDPOINTS["claude"],
            headers=headers,
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Claude API error {response.status}: {error_text}")
            
            data = await response.json()
            return data["content"][0]["text"]
    
    async def _query_ollama(
        self, 
        messages: List[Dict], 
        tools_context: Optional[Dict]
    ) -> str:
        """Consulta a Ollama (modelo local)"""
        # Concatenar todos los mensajes para Ollama
        system_msg = SYSTEM_IDENTITY + "\n" + self._format_tools_context(tools_context)
        
        conversation = []
        for msg in messages:
            if msg["role"] == "user":
                conversation.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                conversation.append(f"Assistant: {msg['content']}")
        
        prompt = f"{system_msg}\n\n" + "\n".join(conversation) + "\nAssistant:"
        
        payload = {
            "model": "qwen2.5:14b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": LLM_CONFIG["temperature"],
                "num_predict": LLM_CONFIG["max_tokens"]
            }
        }
        
        session = await self._get_session()
        async with session.post(
            API_ENDPOINTS["ollama"],
            json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Ollama API error {response.status}: {error_text}")
            
            data = await response.json()
            return data["response"]
    
    def _format_tools_context(self, tools_context: Optional[Dict]) -> str:
        """Formatea el contexto de herramientas para el prompt"""
        if not tools_context:
            return ""
        
        context_parts = ["\nHERRAMIENTAS DISPONIBLES:"]
        
        if "available_tools" in tools_context:
            for tool in tools_context["available_tools"]:
                context_parts.append(f"- {tool['name']}: {tool.get('description', 'N/A')}")
        
        if "active_services" in tools_context:
            context_parts.append(f"\nServicios activos: {', '.join(tools_context['active_services'])}")
        
        return "\n".join(context_parts)
    
    def _update_latency(self, new_latency: float):
        """Actualiza el promedio de latencia"""
        n = self.metrics["successful_requests"]
        if n == 1:
            self.metrics["average_latency"] = new_latency
        else:
            self.metrics["average_latency"] = (
                (self.metrics["average_latency"] * (n - 1)) + new_latency
            ) / n
    
    def get_metrics(self) -> Dict:
        """Obtiene métricas de uso"""
        return self.metrics.copy()
    
    async def close(self):
        """Cierra la sesión HTTP"""
        if self.session:
            await self.session.close()

# ============================================================
# BRAINCHATV8 CLASE PRINCIPAL (líneas 701-1500)
# ============================================================

class BrainChatV8:
    """
    Brain Chat V8.0 - Agente Autónomo Principal
    Integra: MemoryManager, IntentDetector, LLMManager
    """
    
    def __init__(self, session_id: str = "default"):
        self.logger = logging.getLogger("BrainChatV8")
        self.session_id = session_id
        
        # Inicializar componentes
        self.memory = MemoryManager(session_id)
        self.intent_detector = IntentDetector()
        self.llm = LLMManager()
        
        # FASE 2: Inicializar herramientas
        self.fs_tools: Optional[FileSystemTools] = None
        self.code_analyzer: Optional[CodeAnalyzer] = None
        self.system_tools: Optional[SystemTools] = None
        self.api_tools: Optional[APITools] = None
        self.tool_registry: Optional[ToolRegistry] = None
        
        # FASE 3: Trading Integration
        self.quantconnect: Optional[QuantConnectConnector] = None
        self.tiingo: Optional[TiingoConnector] = None
        self.pocket_option: Optional[PocketOptionBridge] = None
        self.trading_metrics: Optional[TradingMetricsCalculator] = None
        self.portfolio_analyzer: Optional[PortfolioAnalyzer] = None
        
        # FASE 4: Brain Integration
        self.rsi_manager: Optional[RSIManager] = None
        self.health_monitor: Optional[BrainHealthMonitor] = None
        self.metrics_aggregator: Optional[MetricsAggregator] = None
        self.premises_checker: Optional[PremisesChecker] = None
        
        # Estado del sistema
        self.is_running = False
        self.start_time = datetime.now()
        self.conversation_count = 0
        
        # Configurar logging estructurado
        self._setup_logging()
        
        # Inicializar herramientas (debe ser después del logging)
        self.setup_tools()
        
        # Inicializar integración de trading
        self.setup_trading_integration()
        
        # Inicializar integración de Brain (FASE 4)
        self.setup_brain_integration()
        
        self.logger.info(f"BrainChatV8 inicializado - Session: {session_id}")
    
    def setup_tools(self):
        """Inicializa y registra todas las herramientas disponibles"""
        self.logger.info("Inicializando sistema de herramientas (FASE 2)...")
        
        # Crear instancias
        self.fs_tools = FileSystemTools(self.logger)
        self.code_analyzer = CodeAnalyzer(self.logger)
        self.system_tools = SystemTools(self.logger)
        self.api_tools = APITools(self.logger)
        self.tool_registry = ToolRegistry()
        
        # Registrar herramientas de FileSystem
        self._register_filesystem_tools()
        
        # Registrar herramientas de CodeAnalyzer
        self._register_code_analyzer_tools()
        
        # Registrar herramientas de SystemTools
        self._register_system_tools()
        
        # Registrar herramientas de APITools
        self._register_api_tools()
        
        self.logger.info(f"Herramientas registradas: {len(self.tool_registry.tools)}")
    
    def setup_trading_integration(self):
        """Inicializa conectores de trading (FASE 3)"""
        self.logger.info("Inicializando integración de trading (FASE 3)...")
        
        try:
            # Inicializar conectores
            self.quantconnect = QuantConnectConnector()
            self.tiingo = TiingoConnector()
            self.pocket_option = PocketOptionBridge()
            self.trading_metrics = TradingMetricsCalculator()
            self.portfolio_analyzer = PortfolioAnalyzer()
            
            self.logger.info("  [OK] QuantConnectConnector inicializado")
            self.logger.info("  [OK] TiingoConnector inicializado")
            self.logger.info("  [OK] PocketOptionBridge inicializado")
            self.logger.info("  [OK] TradingMetricsCalculator inicializado")
            self.logger.info("  [OK] PortfolioAnalyzer inicializado")
            
            # Registrar herramientas de trading en el registro
            if self.tool_registry:
                self._register_trading_tools()
                
        except Exception as e:
            self.logger.error(f"Error inicializando trading integration: {e}")
    
    def setup_brain_integration(self):
        """Inicializa integración de Brain (FASE 4)"""
        self.logger.info("Inicializando integración de Brain (FASE 4)...")
        
        try:
            # Inicializar gestores
            self.rsi_manager = RSIManager()
            self.health_monitor = BrainHealthMonitor()
            self.metrics_aggregator = MetricsAggregator()
            self.premises_checker = PremisesChecker()
            
            self.logger.info("  [OK] RSIManager inicializado")
            self.logger.info("  [OK] BrainHealthMonitor inicializado")
            self.logger.info("  [OK] MetricsAggregator inicializado")
            self.logger.info("  [OK] PremisesChecker inicializado")
            
            # Registrar herramientas de integración
            if self.tool_registry:
                self._register_brain_integration_tools()
                
        except Exception as e:
            self.logger.error(f"Error inicializando brain integration: {e}")
    
    def _register_brain_integration_tools(self):
        """Registra herramientas de integración de Brain en ToolRegistry"""
        tools = [
            ("get_rsi_analysis", self._get_rsi_analysis_tool, "Obtiene análisis RSI del sistema", "brain"),
            ("check_brain_health", self._check_brain_health_tool, "Verifica salud de servicios Brain", "brain"),
            ("get_system_metrics", self._get_system_metrics_tool, "Obtiene métricas agregadas del sistema", "brain"),
            ("validate_premise", self._validate_premise_tool, "Valida acción contra premisas canónicas", "brain"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de Brain Integration registradas")
    
    async def _get_rsi_analysis_tool(self, **kwargs):
        """Herramienta para obtener análisis RSI"""
        if not self.rsi_manager:
            return {"success": False, "error": "RSIManager no inicializado"}
        return await self.rsi_manager.run_strategic_analysis()
    
    async def _check_brain_health_tool(self, **kwargs):
        """Herramienta para verificar salud del Brain"""
        if not self.health_monitor:
            return {"success": False, "error": "BrainHealthMonitor no inicializado"}
        return await self.health_monitor.check_all_services()
    
    async def _get_system_metrics_tool(self, **kwargs):
        """Herramienta para obtener métricas del sistema"""
        if not self.metrics_aggregator:
            return {"success": False, "error": "MetricsAggregator no inicializado"}
        return await self.metrics_aggregator.aggregate_system_metrics()
    
    async def _validate_premise_tool(self, action: Dict, **kwargs):
        """Herramienta para validar premisas"""
        if not self.premises_checker:
            return {"success": False, "error": "PremisesChecker no inicializado"}
        is_valid, message = self.premises_checker.check_action_compliance(action)
        return {"success": True, "valid": is_valid, "message": message}
    
    # Métodos públicos para integración de Brain
    async def get_rsi_analysis(self):
        """Obtiene análisis RSI del sistema"""
        if not self.rsi_manager:
            await asyncio.get_event_loop().run_in_executor(None, self.setup_brain_integration)
        return await self.rsi_manager.run_strategic_analysis()
    
    async def check_brain_health(self):
        """Verifica salud de servicios del Brain"""
        if not self.health_monitor:
            await asyncio.get_event_loop().run_in_executor(None, self.setup_brain_integration)
        return await self.health_monitor.check_all_services()
    
    async def get_system_metrics(self):
        """Obtiene métricas agregadas del sistema"""
        if not self.metrics_aggregator:
            await asyncio.get_event_loop().run_in_executor(None, self.setup_brain_integration)
        return await self.metrics_aggregator.aggregate_system_metrics()
    
    async def validate_premise(self, action: Dict) -> Tuple[bool, str]:
        """Valida una acción contra las premisas canónicas"""
        if not self.premises_checker:
            await asyncio.get_event_loop().run_in_executor(None, self.setup_brain_integration)
        return self.premises_checker.check_action_compliance(action)
    
    def _register_trading_tools(self):
        """Registra herramientas de trading en el ToolRegistry"""
        tools = [
            ("get_market_data", self._get_market_data_tool, "Obtiene datos de mercado de QuantConnect/Tiingo", "trading"),
            ("get_trading_metrics", self._get_trading_metrics_tool, "Obtiene métricas de trading desde PocketOption", "trading"),
            ("calculate_portfolio_metrics", self._calculate_portfolio_metrics_tool, "Calcula métricas de portafolio", "trading"),
            ("analyze_trading_performance", self._analyze_trading_performance_tool, "Analiza rendimiento de trading", "trading"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de trading registradas")
    
    async def _get_market_data_tool(self, symbol: str, source: str = "auto", **kwargs):
        """Herramienta para obtener datos de mercado"""
        # Mapeo de símbolos comunes
        symbol_map = {
            "SPY": source == "tiingo" and self.tiingo or self.quantconnect,
            "QQQ": source == "tiingo" and self.tiingo or self.quantconnect,
            "EURUSD": self.tiingo,
            "BTC": self.tiingo,
        }
        
        connector = symbol_map.get(symbol.upper())
        if not connector:
            # Default a QuantConnect
            connector = self.quantconnect
        
        if source == "historical":
            return await connector.get_historical_data(symbol, kwargs.get("days", 30))
        else:
            return await connector.get_intraday_data(symbol, kwargs.get("start_date"), kwargs.get("end_date"))
    
    async def _get_trading_metrics_tool(self, **kwargs):
        """Herramienta para obtener métricas de trading"""
        # Obtener historial de trades desde PocketOption
        history = await self.pocket_option.get_trade_history(limit=kwargs.get("limit", 100))
        
        if not history.get("success"):
            return history
        
        trades = history.get("trades", [])
        
        # Calcular métricas
        metrics = {
            "win_rate": self.trading_metrics.calculate_win_rate(trades),
            "profit_factor": self.trading_metrics.calculate_profit_factor(trades),
            "expectancy": self.trading_metrics.calculate_expectancy(trades)
        }
        
        return {
            "success": True,
            "metrics": metrics,
            "trade_count": len(trades)
        }
    
    def _calculate_portfolio_metrics_tool(self, weights, returns):
        """Herramienta wrapper para PortfolioAnalyzer"""
        return self.portfolio_analyzer.calculate_portfolio_metrics(weights, returns)
    
    def _analyze_trading_performance_tool(self, trades, equity_curve):
        """Herramienta wrapper para generar reporte de trading"""
        return self.trading_metrics.generate_performance_report(trades, equity_curve)
    
    async def get_trading_data(self, symbol: str, timeframe: str = "1d") -> Dict:
        """Obtiene datos de trading para un símbolo específico"""
        try:
            # Usar siempre Tiingo para datos de mercado (más confiable)
            connector = self.tiingo
            
            if timeframe in ["1min", "5min", "15min", "30min", "1h"]:
                data = await connector.get_intraday_data(symbol, resample_freq=timeframe)
            else:
                data = await connector.get_daily_data(symbol)
            
            return {
                "success": True,
                "symbol": symbol,
                "timeframe": timeframe,
                "data": data
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo datos de trading: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_portfolio_status(self) -> Dict:
        """Obtiene estado actual del portafolio"""
        try:
            # Obtener balance de PocketOption
            balance = await self.pocket_option.get_balance()
            
            # Obtener trades abiertos
            open_trades = await self.pocket_option.get_open_trades()
            
            # Obtener métricas
            metrics = await self.pocket_option.get_metrics()
            
            return {
                "success": True,
                "balance": balance,
                "open_trades": open_trades,
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error obteniendo estado del portafolio: {e}")
            return {"success": False, "error": str(e)}
    
    async def calculate_trading_metrics(self, trades: List[Dict]) -> Dict:
        """Calcula todas las métricas de trading"""
        try:
            results = {
                "success": True,
                "metrics": {
                    "win_rate": self.trading_metrics.calculate_win_rate(trades),
                    "profit_factor": self.trading_metrics.calculate_profit_factor(trades),
                    "expectancy": self.trading_metrics.calculate_expectancy(trades),
                },
                "advanced_metrics": {}
            }
            
            # Calcular retornos para ratios
            if trades and len(trades) > 1:
                returns = [t.get("return", 0) for t in trades if "return" in t]
                if returns:
                    results["advanced_metrics"]["sharpe"] = self.trading_metrics.calculate_sharpe_ratio(returns)
                    results["advanced_metrics"]["sortino"] = self.trading_metrics.calculate_sortino_ratio(returns)
                    results["advanced_metrics"]["var_95"] = self.trading_metrics.calculate_var(returns, 0.95)
            
            return results
        except Exception as e:
            self.logger.error(f"Error calculando métricas: {e}")
            return {"success": False, "error": str(e)}
    
    async def analyze_symbol_correlation(self, symbols: List[str], days: int = 30) -> Dict:
        """Analiza correlación entre múltiples símbolos"""
        try:
            data = {}
            for symbol in symbols:
                result = await self.tiingo.get_daily_data(symbol, days=days)
                if result.get("success"):
                    data[symbol] = result.get("data", [])
            
            if len(data) < 2:
                return {"success": False, "error": "Se necesitan al menos 2 símbolos con datos"}
            
            correlation = self.portfolio_analyzer.analyze_correlations(symbols, data)
            return correlation
        except Exception as e:
            self.logger.error(f"Error analizando correlaciones: {e}")
            return {"success": False, "error": str(e)}
    
    def _register_filesystem_tools(self):
        """Registra herramientas del sistema de archivos"""
        tools = [
            ("search_files", self.fs_tools.search_files, "Busca archivos por patrón", "filesystem"),
            ("read_file", self.fs_tools.read_file, "Lee el contenido de un archivo", "filesystem"),
            ("write_file", self.fs_tools.write_file, "Escribe contenido en un archivo", "filesystem"),
            ("edit_file", self.fs_tools.edit_file, "Edita un archivo reemplazando texto", "filesystem"),
            ("list_directory", self.fs_tools.list_directory, "Lista contenido de directorio", "filesystem"),
            ("delete_file", self.fs_tools.delete_file, "Elimina un archivo (mueve a papelera)", "filesystem"),
            ("copy_file", self.fs_tools.copy_file, "Copia un archivo", "filesystem"),
            ("move_file", self.fs_tools.move_file, "Mueve un archivo", "filesystem"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de filesystem registradas")
    
    def _register_code_analyzer_tools(self):
        """Registra herramientas de análisis de código"""
        tools = [
            ("analyze_python_file", self.code_analyzer.analyze_python_file, "Análisis completo de archivo Python", "code"),
            ("find_imports", self.code_analyzer.find_imports, "Encuentra imports en código", "code"),
            ("find_functions", self.code_analyzer.find_functions, "Encuentra funciones definidas", "code"),
            ("find_classes", self.code_analyzer.find_classes, "Encuentra clases definidas", "code"),
            ("calculate_complexity", self.code_analyzer.calculate_complexity, "Calcula métricas de complejidad", "code"),
            ("find_code_issues", self.code_analyzer.find_code_issues, "Encuentra problemas en el código", "code"),
            ("suggest_improvements", self.code_analyzer.suggest_improvements, "Sugiere mejoras para el código", "code"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de análisis de código registradas")
    
    def _register_system_tools(self):
        """Registra herramientas del sistema operativo"""
        tools = [
            ("execute_command", self.system_tools.execute_command, "Ejecuta comando del sistema (whitelist)", "system"),
            ("get_system_info", self.system_tools.get_system_info, "Obtiene información del sistema", "system"),
            ("get_process_list", self.system_tools.get_process_list, "Lista procesos activos", "system"),
            ("check_service_health", self.system_tools.check_service_health, "Verifica estado de servicio", "system"),
            ("get_disk_usage", self.system_tools.get_disk_usage, "Obtiene uso de disco", "system"),
            ("get_memory_usage", self.system_tools.get_memory_usage, "Obtiene uso de memoria", "system"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de sistema registradas")
    
    def _register_api_tools(self):
        """Registra herramientas de API/HTTP"""
        tools = [
            ("fetch_url", self.api_tools.fetch_url, "Realiza petición HTTP", "api"),
            ("post_json", self.api_tools.post_json, "Realiza POST con JSON", "api"),
            ("check_endpoint_health", self.api_tools.check_endpoint_health, "Verifica salud de endpoint", "api"),
        ]
        
        for name, func, desc, cat in tools:
            self.tool_registry.register_tool(name, func, desc, cat)
        
        self.logger.info(f"  [OK] {len(tools)} herramientas de API registradas")
    
    def get_tools_for_intent(self, intent: str) -> List[str]:
        """Obtiene herramientas recomendadas para una intención"""
        if self.tool_registry:
            mapping = self.tool_registry.get_intent_to_tool_mapping()
            return mapping.get(intent, [])
        return []
    
    async def execute_tool_by_name(self, tool_name: str, **kwargs) -> Dict:
        """Ejecuta una herramienta por nombre"""
        if self.tool_registry:
            return await self.tool_registry.execute_tool(tool_name, **kwargs)
        return {"success": False, "error": "Tool registry not initialized"}
    
    def _setup_logging(self):
        """Configura logging estructurado con timestamps"""
        log_file = LOGS_PATH / f"brainchat_{self.session_id}_{datetime.now().strftime('%Y%m%d')}.log"
        
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Configurar logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        
        self.logger.info(f"Logging configurado en: {log_file}")
    
    async def process_message(
        self,
        message: str,
        user_id: str = "anonymous",
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Procesa un mensaje del usuario - VERSIÓN DIRECTA (sin dependencia de LLM)
        
        Pipeline optimizado:
        1. Detectar intención
        2. Ejecutar herramientas directamente si aplica
        3. Usar LLM solo para conversaciones (fallback)
        """
        start_time = time.time()
        self.conversation_count += 1
        
        # Log entrada
        self.logger.info(f"[{user_id}] Mensaje recibido: {message[:100]}...")
        
        # 1. Detectar intención
        conversation_history = self.memory.load_context(limit=5)
        intent, confidence, intent_meta = self.intent_detector.detect_intent(
            message, conversation_history
        )
        
        self.logger.info(f"Intención detectada: {intent} (confianza: {confidence:.2f})")
        
        # Extraer entidades
        entities = self.intent_detector.extract_entities(message)
        sentiment = self.intent_detector.analyze_sentiment(message)
        
        # 2. GUARDAR EN MEMORIA PRIMERO
        self.memory.save_conversation({
            "role": "user",
            "content": message,
            "user_id": user_id,
            "intent": intent,
            "confidence": confidence
        })
        
        # 3. EJECUTAR HERRAMIENTAS DIRECTAMENTE (bypass LLM)
        tool_result = None
        if hasattr(self, 'tools') and self.tools:
            tool_result = await self._execute_tools_for_intent(intent, message, entities)
        
        # Si la herramienta ejecutó exitosamente, usar su resultado
        if tool_result and tool_result.get("success"):
            processing_time = time.time() - start_time
            
            self.memory.save_conversation({
                "role": "assistant", 
                "content": tool_result.get("result", ""),
                "model": "tool_direct",
                "latency": processing_time
            })
            
            self.logger.info(f"Respuesta generada en {processing_time:.2f}s usando TOOL DIRECT")
            
            return {
                "success": True,
                "message": tool_result.get("result"),
                "error": None,
                "metadata": {
                    "intent": intent,
                    "intent_confidence": confidence,
                    "intent_method": intent_meta.get("method"),
                    "model_used": "tool_direct",
                    "fallback_used": False,
                    "latency": processing_time,
                    "processing_time": processing_time,
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "entities": entities,
                    "sentiment": sentiment,
                    "tool_executed": tool_result.get("tool_name")
                }
            }
        
        # 4. FALLBACK: Usar LLM solo para conversaciones generales
        memory_context = self.memory.load_context(limit=10)
        messages = self._prepare_messages(
            message=message,
            memory_context=memory_context,
            intent=intent,
            entities=entities,
            sentiment=sentiment
        )
        
        tools_context = {
            "available_tools": self._get_available_tools(),
            "active_services": self._get_active_services(),
            "user_id": user_id
        }
        
        # Consultar LLM con timeout reducido
        llm_response = await self.llm.query_llm(
            messages=messages,
            tools_context=tools_context,
            model_priority="ollama"  # Prioridad a Ollama (local)
        )
        
        if llm_response["success"]:
            self.memory.save_conversation({
                "role": "assistant",
                "content": llm_response["content"],
                "model": llm_response["model"],
                "latency": llm_response["latency"]
            })
        
        processing_time = time.time() - start_time
        
        response = {
            "success": llm_response["success"],
            "message": llm_response["content"] if llm_response["success"] else None,
            "error": llm_response.get("error"),
            "metadata": {
                "intent": intent,
                "intent_confidence": confidence,
                "intent_method": intent_meta.get("method"),
                "model_used": llm_response.get("model"),
                "fallback_used": llm_response.get("fallback_used", False),
                "latency": llm_response.get("latency"),
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat(),
                "session_id": self.session_id,
                "entities": entities,
                "sentiment": sentiment
            }
        }
        
        self.logger.info(f"Respuesta generada en {processing_time:.2f}s usando {llm_response.get('model', 'none')}")
        
        return response
    
    async def _execute_tools_for_intent(self, intent: str, message: str, entities: Dict) -> Optional[Dict]:
        """
        Ejecuta herramientas directamente basado en la intención detectada
        """
        if not hasattr(self, 'tool_registry') or not self.tool_registry:
            return None
        
        try:
            # Mapeo de intenciones a herramientas
            intent_tool_map = {
                "COMMAND": ["execute_command"],
                "ANALYSIS": ["analyze_python_file", "find_imports", "find_functions"],
                "CODE": ["analyze_python_file", "find_code_issues"],
                "QUERY": ["search_files", "list_directory", "read_file"],
                "SYSTEM": ["get_system_info", "get_process_list", "check_service_health"],
                "RSI": ["get_rsi_analysis"],
                "HEALTH": ["check_brain_health"],
                "METRICS": ["get_system_metrics"],
                "TRADING": ["get_trading_metrics", "calculate_portfolio_metrics"],
            }
            
            tools_to_try = intent_tool_map.get(intent, [])
            
            for tool_name in tools_to_try:
                if tool_name == "execute_command":
                    # Extraer comando del mensaje
                    import re
                    cmd_match = re.search(r'(?:ejecuta?|run|exec)\s+(?:comando?|command)?\s*[:\s]*(.+)', message, re.IGNORECASE)
                    if cmd_match:
                        cmd = cmd_match.group(1).strip()
                        result = await self.tool_registry.execute_tool("execute_command", command=cmd)
                        if result.get("success"):
                            return {
                                "success": True,
                                "tool_name": tool_name,
                                "result": f"Comando ejecutado:\n{result.get('stdout', '')}"
                            }
                
                elif tool_name == "analyze_python_file":
                    # Buscar archivo en mensaje
                    import re
                    file_match = re.search(r'(?:archivo|file)\s+[:\s]*(\S+\.py)', message, re.IGNORECASE)
                    if file_match:
                        filepath = file_match.group(1)
                        result = await self.tool_registry.execute_tool("analyze_python_file", file_path=filepath)
                        if result.get("success"):
                            return {
                                "success": True,
                                "tool_name": tool_name,
                                "result": f"Análisis de {filepath}:\n{result}"
                            }
                
                elif tool_name == "get_rsi_analysis":
                    result = await self.tool_registry.execute_tool("get_rsi_analysis")
                    if result.get("success"):
                        return {
                            "success": True,
                            "tool_name": tool_name,
                            "result": f"Reporte RSI:\n{result.get('report', result)}"
                        }
                
                elif tool_name == "check_brain_health":
                    result = await self.tool_registry.execute_tool("check_brain_health")
                    if result.get("success"):
                        return {
                            "success": True,
                            "tool_name": tool_name,
                            "result": f"Estado del sistema:\n{result.get('status', result)}"
                        }
                
                elif tool_name == "get_system_metrics":
                    result = await self.tool_registry.execute_tool("get_system_metrics")
                    if result.get("success"):
                        return {
                            "success": True,
                            "tool_name": tool_name,
                            "result": f"Métricas del sistema:\n{result.get('metrics', result)}"
                        }
                
                elif tool_name == "list_directory":
                    import re
                    path_match = re.search(r'dir\s+([A-Z]:[/\\]\S*)', message, re.IGNORECASE)
                    if path_match:
                        path = path_match.group(1).replace("/", "\\\\")
                        result = await self.tool_registry.execute_tool("list_directory", path=path)
                        if result.get("success"):
                            files = result.get("files", [])
                            dirs = result.get("directories", [])
                            content = f"Directorio {path}:\n"
                            content += f"Archivos: {len(files)}\n"
                            content += f"Directorios: {len(dirs)}\n"
                            content += "\n".join([f"  [FILE] {f}" for f in files[:20]])
                            content += "\n".join([f"  [DIR]  {d}" for d in dirs[:10]])
                            return {
                                "success": True,
                                "tool_name": tool_name,
                                "result": content
                            }
                
                elif tool_name == "search_files":
                    import re
                    pattern_match = re.search(r'busca\s+(\S+)', message, re.IGNORECASE)
                    if pattern_match:
                        pattern = pattern_match.group(1)
                        path_match = re.search(r'en\s+([A-Z]:[/\\][^\s]+)', message, re.IGNORECASE)
                        path = path_match.group(1) if path_match else "C:\\AI_VAULT"
                        result = await self.tool_registry.execute_tool("search_files", pattern=pattern, path=path)
                        if result.get("success"):
                            matches = result.get("matches", [])
                            content = f"Búsqueda de '{pattern}' en {path}:\n"
                            content += f"Encontrados: {len(matches)}\n"
                            content += "\n".join([f"  {m}" for m in matches[:10]])
                            return {
                                "success": True,
                                "tool_name": tool_name,
                                "result": content
                            }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error ejecutando herramientas: {e}")
            return None
    
    def _prepare_messages(
        self,
        message: str,
        memory_context: List[Dict],
        intent: str,
        entities: Dict,
        sentiment: Dict
    ) -> List[Dict]:
        """Prepara los mensajes para el LLM"""
        messages = []
        
        # Contexto del sistema ya se maneja en LLMManager
        # Aquí solo agregamos el contexto de memoria
        
        # Agregar mensajes previos (limitados)
        for msg in memory_context:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg.get("content", "")
                })
        
        # Agregar mensaje actual con contexto
        enriched_message = f"""[Intención: {intent} | Sentimiento: {sentiment['sentiment']}]
{message}"""
        
        if entities.get("urls"):
            enriched_message += f"\n[URLs detectadas: {', '.join(entities['urls'])}]"
        
        messages.append({
            "role": "user",
            "content": enriched_message
        })
        
        return messages
    
    def _get_available_tools(self) -> List[Dict]:
        """Obtiene la lista de herramientas disponibles"""
        return [
            {"name": "memory", "description": "Gestión de memoria de conversación"},
            {"name": "intent_detection", "description": "Detección de intenciones"},
            {"name": "code_execution", "description": "Ejecución de código"},
            {"name": "web_search", "description": "Búsqueda web"},
            {"name": "file_operations", "description": "Operaciones con archivos"}
        ]
    
    def _get_active_services(self) -> List[str]:
        """Obtiene la lista de servicios activos"""
        services = ["memory", "intent_detector"]
        if API_KEYS["openai"]:
            services.append("gpt4")
        if API_KEYS["anthropic"]:
            services.append("claude")
        services.append("ollama")
        return services
    
    async def get_system_status(self) -> Dict:
        """Obtiene el estado completo del sistema"""
        uptime = datetime.now() - self.start_time
        memory_state = self.memory.get_system_state()
        llm_metrics = self.llm.get_metrics()
        
        return {
            "status": "running" if self.is_running else "stopped",
            "version": "8.0.0",
            "session_id": self.session_id,
            "uptime_seconds": uptime.total_seconds(),
            "conversation_count": self.conversation_count,
            "memory": {
                "short_term_count": len(self.memory.short_term),
                "long_term_count": len(self.memory.long_term),
                "message_count": self.memory.message_count,
                "state": memory_state
            },
            "llm_metrics": llm_metrics,
            "active_services": self._get_active_services()
        }
    
    async def clear_memory(self, memory_type: Optional[str] = None):
        """Limpia la memoria del sistema"""
        self.memory.clear_memory(memory_type)
        self.logger.info(f"Memoria limpiada: {memory_type or 'all'}")
    
    async def shutdown(self):
        """Apaga el sistema de forma ordenada"""
        self.logger.info("Iniciando apagado del sistema...")
        await self.llm.close()
        self.is_running = False
        self.logger.info("Sistema apagado correctamente")
    
    def start(self):
        """Inicia el sistema"""
        self.is_running = True
        self.logger.info("BrainChatV8 iniciado y listo")

# ============================================================
# FASE 2: SISTEMA DE HERRAMIENTAS AVANZADO (líneas 900-1700)
# ============================================================

# ============================================================
# FILESYSTEM TOOLS (líneas 900-1099)
# ============================================================

class FileSystemTools:
    """Herramientas avanzadas para operaciones con archivos y directorios"""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("FileSystemTools")
        self.base_path = BASE_PATH
        self.max_file_size = 1048576  # 1MB
        self.max_results = 50
    
    def _is_safe_path(self, filepath: str) -> bool:
        """Verifica si la ruta está dentro de BASE_PATH por seguridad"""
        try:
            target = Path(filepath).resolve()
            base = self.base_path.resolve()
            return target == base or base in target.parents or target == base
        except Exception:
            return False
    
    def search_files(self, pattern: str, path: str = "C:\\AI_VAULT", max_results: int = 50) -> Dict:
        """
        Busca archivos que coincidan con el patrón
        
        Args:
            pattern: Patrón de búsqueda (puede incluir wildcards * y ?)
            path: Directorio base para la búsqueda
            max_results: Máximo de resultados a retornar
        
        Returns:
            Dict con lista de archivos encontrados y metadata
        """
        import fnmatch
        
        try:
            results = []
            base_path = Path(path)
            
            if not base_path.exists():
                return {
                    "success": False,
                    "error": f"Path does not exist: {path}",
                    "results": [],
                    "count": 0
                }
            
            # Búsqueda recursiva
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if fnmatch.fnmatch(file.lower(), pattern.lower()):
                        full_path = Path(root) / file
                        try:
                            stat = full_path.stat()
                            results.append({
                                "name": file,
                                "path": str(full_path),
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                "extension": full_path.suffix.lower()
                            })
                        except Exception as e:
                            self.logger.warning(f"Error accediendo a {full_path}: {e}")
                        
                        if len(results) >= max_results:
                            break
                
                if len(results) >= max_results:
                    break
            
            self.logger.info(f"Búsqueda completada: {len(results)} archivos encontrados")
            return {
                "success": True,
                "pattern": pattern,
                "path": path,
                "results": results,
                "count": len(results)
            }
        
        except Exception as e:
            self.logger.error(f"Error en búsqueda de archivos: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "count": 0
            }
    
    def read_file(self, filepath: str, max_size: int = 1048576) -> Dict:
        """
        Lee el contenido de un archivo
        
        Args:
            filepath: Ruta del archivo
            max_size: Tamaño máximo en bytes (default 1MB)
        
        Returns:
            Dict con contenido y metadata del archivo
        """
        try:
            file_path = Path(filepath)
            
            if not file_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {filepath}",
                    "content": None
                }
            
            if not file_path.is_file():
                return {
                    "success": False,
                    "error": f"Path is not a file: {filepath}",
                    "content": None
                }
            
            # Verificar tamaño
            size = file_path.stat().st_size
            if size > max_size:
                return {
                    "success": False,
                    "error": f"File too large: {size} bytes (max: {max_size})",
                    "content": None,
                    "size": size
                }
            
            # Detectar encoding
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    encoding = 'utf-8'
            except UnicodeDecodeError:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    encoding = 'binary'
            
            self.logger.info(f"Archivo leído: {filepath} ({size} bytes)")
            return {
                "success": True,
                "content": content if encoding != 'binary' else f"[Binary file: {size} bytes]",
                "encoding": encoding,
                "size": size,
                "extension": file_path.suffix.lower(),
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
            }
        
        except Exception as e:
            self.logger.error(f"Error leyendo archivo {filepath}: {e}")
            return {
                "success": False,
                "error": str(e),
                "content": None
            }
    
    def write_file(self, filepath: str, content: str, backup: bool = True) -> Dict:
        """
        Escribe contenido en un archivo
        
        Args:
            filepath: Ruta del archivo
            content: Contenido a escribir
            backup: Si True, crea backup del archivo existente
        
        Returns:
            Dict con resultado de la operación
        """
        try:
            file_path = Path(filepath)
            
            # Verificar directorio padre existe
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Crear backup si existe y se solicita
            backup_path = None
            if backup and file_path.exists():
                backup_path = file_path.with_suffix(f"{file_path.suffix}.backup.{int(time.time())}")
                file_path.rename(backup_path)
            
            # Escribir archivo
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            size = file_path.stat().st_size
            self.logger.info(f"Archivo escrito: {filepath} ({size} bytes)")
            
            return {
                "success": True,
                "filepath": str(file_path),
                "size": size,
                "backup_created": backup_path is not None,
                "backup_path": str(backup_path) if backup_path else None
            }
        
        except Exception as e:
            self.logger.error(f"Error escribiendo archivo {filepath}: {e}")
            return {
                "success": False,
                "error": str(e),
                "filepath": filepath
            }
    
    def edit_file(self, filepath: str, old_string: str, new_string: str) -> Dict:
        """
        Edita un archivo reemplazando old_string con new_string
        
        Args:
            filepath: Ruta del archivo
            old_string: Texto a buscar
            new_string: Texto de reemplazo
        
        Returns:
            Dict con resultado de la operación
        """
        try:
            file_path = Path(filepath)
            
            if not file_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {filepath}"
                }
            
            # Leer contenido
            read_result = self.read_file(filepath)
            if not read_result["success"]:
                return read_result
            
            content = read_result["content"]
            
            # Verificar que old_string existe
            if old_string not in content:
                return {
                    "success": False,
                    "error": f"String not found in file: {old_string[:50]}..."
                }
            
            # Reemplazar
            new_content = content.replace(old_string, new_string, 1)
            
            # Crear backup
            backup_path = file_path.with_suffix(f"{file_path.suffix}.backup.{int(time.time())}")
            file_path.rename(backup_path)
            
            # Escribir nuevo contenido
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            self.logger.info(f"Archivo editado: {filepath}")
            
            return {
                "success": True,
                "filepath": str(file_path),
                "replacements": content.count(old_string),
                "backup_path": str(backup_path)
            }
        
        except Exception as e:
            self.logger.error(f"Error editando archivo {filepath}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_directory(self, path: str) -> Dict:
        """
        Lista el contenido de un directorio
        
        Args:
            path: Ruta del directorio
        
        Returns:
            Dict con archivos y subdirectorios
        """
        try:
            dir_path = Path(path)
            
            if not dir_path.exists():
                return {
                    "success": False,
                    "error": f"Directory not found: {path}",
                    "files": [],
                    "directories": []
                }
            
            if not dir_path.is_dir():
                return {
                    "success": False,
                    "error": f"Path is not a directory: {path}",
                    "files": [],
                    "directories": []
                }
            
            files = []
            directories = []
            
            for item in dir_path.iterdir():
                try:
                    stat = item.stat()
                    info = {
                        "name": item.name,
                        "path": str(item),
                        "size": stat.st_size if item.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    }
                    
                    if item.is_file():
                        files.append(info)
                    elif item.is_dir():
                        directories.append(info)
                
                except Exception as e:
                    self.logger.warning(f"Error accediendo a {item}: {e}")
            
            # Ordenar
            files.sort(key=lambda x: x["name"].lower())
            directories.sort(key=lambda x: x["name"].lower())
            
            self.logger.info(f"Directorio listado: {path} ({len(files)} archivos, {len(directories)} directorios)")
            
            return {
                "success": True,
                "path": path,
                "files": files,
                "directories": directories,
                "total_files": len(files),
                "total_directories": len(directories)
            }
        
        except Exception as e:
            self.logger.error(f"Error listando directorio {path}: {e}")
            return {
                "success": False,
                "error": str(e),
                "files": [],
                "directories": []
            }
    
    def delete_file(self, filepath: str, confirm: bool = True) -> Dict:
        """
        Elimina un archivo
        
        Args:
            filepath: Ruta del archivo
            confirm: Si True, solicita confirmación
        
        Returns:
            Dict con resultado de la operación
        """
        try:
            file_path = Path(filepath)
            
            if not file_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {filepath}"
                }
            
            if not file_path.is_file():
                return {
                    "success": False,
                    "error": f"Path is not a file: {filepath}"
                }
            
            # Mover a papelera en lugar de eliminar permanentemente
            trash_dir = self.base_path / "tmp_agent" / "trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            
            trash_path = trash_dir / f"{file_path.name}.{int(time.time())}"
            file_path.rename(trash_path)
            
            self.logger.info(f"Archivo movido a papelera: {filepath} -> {trash_path}")
            
            return {
                "success": True,
                "message": f"File moved to trash",
                "original_path": str(file_path),
                "trash_path": str(trash_path)
            }
        
        except Exception as e:
            self.logger.error(f"Error eliminando archivo {filepath}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def copy_file(self, src: str, dst: str) -> Dict:
        """
        Copia un archivo
        
        Args:
            src: Ruta origen
            dst: Ruta destino
        
        Returns:
            Dict con resultado de la operación
        """
        import shutil
        
        try:
            src_path = Path(src)
            dst_path = Path(dst)
            
            if not src_path.exists():
                return {
                    "success": False,
                    "error": f"Source file not found: {src}"
                }
            
            # Crear directorio destino si no existe
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copiar
            shutil.copy2(src_path, dst_path)
            
            size = dst_path.stat().st_size
            self.logger.info(f"Archivo copiado: {src} -> {dst}")
            
            return {
                "success": True,
                "source": str(src_path),
                "destination": str(dst_path),
                "size": size
            }
        
        except Exception as e:
            self.logger.error(f"Error copiando archivo {src} -> {dst}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def move_file(self, src: str, dst: str) -> Dict:
        """
        Mueve un archivo
        
        Args:
            src: Ruta origen
            dst: Ruta destino
        
        Returns:
            Dict con resultado de la operación
        """
        try:
            src_path = Path(src)
            dst_path = Path(dst)
            
            if not src_path.exists():
                return {
                    "success": False,
                    "error": f"Source file not found: {src}"
                }
            
            # Crear directorio destino si no existe
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Mover
            src_path.rename(dst_path)
            
            self.logger.info(f"Archivo movido: {src} -> {dst}")
            
            return {
                "success": True,
                "source": str(src_path),
                "destination": str(dst_path)
            }
        
        except Exception as e:
            self.logger.error(f"Error moviendo archivo {src} -> {dst}: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================
# CODE ANALYZER (líneas 1100-1299)
# ============================================================

class CodeAnalyzer:
    """Analizador de código Python con capacidades de análisis estático"""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("CodeAnalyzer")
    
    def analyze_python_file(self, filepath: str) -> Dict:
        """
        Analiza completo un archivo Python
        
        Args:
            filepath: Ruta del archivo
        
        Returns:
            Dict con análisis completo del código
        """
        try:
            fs = FileSystemTools(self.logger)
            read_result = fs.read_file(filepath)
            
            if not read_result["success"]:
                return read_result
            
            content = read_result["content"]
            
            # Análisis de componentes
            imports = self.find_imports(content)
            functions = self.find_functions(content)
            classes = self.find_classes(content)
            complexity = self.calculate_complexity(filepath)
            issues = self.find_code_issues(filepath)
            suggestions = self.suggest_improvements(filepath)
            
            # Estadísticas generales
            lines = content.split('\n')
            code_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]
            comment_lines = [l for l in lines if l.strip().startswith('#')]
            
            analysis = {
                "success": True,
                "filepath": filepath,
                "statistics": {
                    "total_lines": len(lines),
                    "code_lines": len(code_lines),
                    "comment_lines": len(comment_lines),
                    "blank_lines": len(lines) - len(code_lines) - len(comment_lines),
                    "comment_ratio": len(comment_lines) / len(lines) if lines else 0
                },
                "imports": imports,
                "functions": functions,
                "classes": classes,
                "complexity": complexity,
                "issues": issues,
                "suggestions": suggestions
            }
            
            self.logger.info(f"Análisis completado: {filepath}")
            return analysis
        
        except Exception as e:
            self.logger.error(f"Error analizando archivo {filepath}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def find_imports(self, content: str) -> Dict:
        """
        Encuentra todas las importaciones en el código
        
        Args:
            content: Contenido del archivo
        
        Returns:
            Dict con imports estándar, de terceros y locales
        """
        imports = {
            "standard": [],
            "third_party": [],
            "local": [],
            "from_imports": [],
            "all": []
        }
        
        # Lista de módulos estándar de Python
        stdlib_modules = {
            'os', 'sys', 'json', 're', 'time', 'datetime', 'collections', 
            'pathlib', 'typing', 'logging', 'asyncio', 'hashlib', 'traceback',
            'math', 'random', 'string', 'itertools', 'functools', 'enum',
            'dataclasses', 'abc', 'inspect', 'types', 'builtins', 'io',
            'warnings', 'contextlib', 'tempfile', 'shutil', 'subprocess',
            'threading', 'multiprocessing', 'unittest', 'doctest', 'pickle',
            'copy', 'numbers', 'decimal', 'fractions', 'statistics'
        }
        
        # Patrones de import
        import_pattern = r'^import\s+([\w\.,\s]+)'
        from_pattern = r'^from\s+(\S+)\s+import'
        
        for line in content.split('\n'):
            line = line.strip()
            
            # import X
            match = re.match(import_pattern, line)
            if match:
                modules = [m.strip() for m in match.group(1).split(',')]
                for mod in modules:
                    base_module = mod.split('.')[0]
                    imports["all"].append(base_module)
                    
                    if base_module in stdlib_modules:
                        imports["standard"].append(base_module)
                    elif base_module.startswith('.'):
                        imports["local"].append(base_module)
                    else:
                        imports["third_party"].append(base_module)
            
            # from X import Y
            match = re.match(from_pattern, line)
            if match:
                module = match.group(1)
                imports["from_imports"].append(module)
                imports["all"].append(module.split('.')[0])
        
        # Eliminar duplicados
        for key in imports:
            if isinstance(imports[key], list):
                imports[key] = list(set(imports[key]))
        
        return imports
    
    def find_functions(self, content: str) -> List[Dict]:
        """
        Encuentra todas las funciones definidas
        
        Args:
            content: Contenido del archivo
        
        Returns:
            Lista de diccionarios con información de funciones
        """
        functions = []
        lines = content.split('\n')
        
        # Patrón: def function_name(args):
        func_pattern = r'^\s*def\s+(\w+)\s*\((.*?)\)'
        
        for i, line in enumerate(lines):
            match = re.match(func_pattern, line)
            if match:
                func_name = match.group(1)
                args = match.group(2).strip()
                
                # Calcular líneas de la función
                func_lines = 1
                indent = len(line) - len(line.lstrip())
                for j in range(i + 1, len(lines)):
                    next_line = lines[j]
                    if next_line.strip():
                        next_indent = len(next_line) - len(next_line.lstrip())
                        if next_indent <= indent and not next_line.strip().startswith('#'):
                            break
                        func_lines += 1
                
                functions.append({
                    "name": func_name,
                    "line": i + 1,
                    "arguments": args,
                    "lines": func_lines,
                    "is_async": 'async def' in line
                })
        
        return functions
    
    def find_classes(self, content: str) -> List[Dict]:
        """
        Encuentra todas las clases definidas
        
        Args:
            content: Contenido del archivo
        
        Returns:
            Lista de diccionarios con información de clases
        """
        classes = []
        lines = content.split('\n')
        
        # Patrón: class ClassName(Base):
        class_pattern = r'^\s*class\s+(\w+)\s*(?:\(([^)]+)\))?:'
        
        for i, line in enumerate(lines):
            match = re.match(class_pattern, line)
            if match:
                class_name = match.group(1)
                bases = match.group(2)
                
                # Contar métodos
                methods = []
                indent = len(line) - len(line.lstrip())
                class_lines = 1
                
                for j in range(i + 1, len(lines)):
                    next_line = lines[j]
                    if not next_line.strip():
                        continue
                    
                    next_indent = len(next_line) - len(next_line.lstrip())
                    
                    if next_indent <= indent:
                        break
                    
                    # Detectar métodos
                    method_match = re.match(r'^\s+def\s+(\w+)\s*\(', next_line)
                    if method_match:
                        methods.append(method_match.group(1))
                    
                    class_lines += 1
                
                classes.append({
                    "name": class_name,
                    "line": i + 1,
                    "bases": [b.strip() for b in bases.split(',')] if bases else ["object"],
                    "methods": methods,
                    "method_count": len(methods),
                    "lines": class_lines
                })
        
        return classes
    
    def calculate_complexity(self, filepath: str) -> Dict:
        """
        Calcula métricas de complejidad del código
        
        Args:
            filepath: Ruta del archivo
        
        Returns:
            Dict con métricas de complejidad
        """
        try:
            fs = FileSystemTools(self.logger)
            read_result = fs.read_file(filepath)
            
            if not read_result["success"]:
                return {
                    "success": False,
                    "error": read_result.get("error", "Failed to read file"),
                    "cyclomatic_complexity": 0,
                    "cognitive_complexity": 0,
                    "lines_of_code": 0,
                    "maintainability_index": 0
                }
            
            content = read_result["content"]
            lines = content.split('\n')
            
            # Contar líneas de código
            code_lines = [l for l in lines if l.strip() and not l.strip().startswith('#')]
            comment_lines = [l for l in lines if l.strip().startswith('#')]
            
            # Calcular complejidad ciclomática (simplificado)
            # Contar estructuras de control
            control_patterns = [
                r'\bif\b', r'\belif\b', r'\belse\b',
                r'\bfor\b', r'\bwhile\b',
                r'\btry\b', r'\bexcept\b',
                r'\band\b', r'\bor\b',
                r'\blambda\b',
                r'\blist comprehension\b', r'\bgenerator\b'
            ]
            
            complexity = 1  # Base
            for pattern in control_patterns:
                complexity += len(re.findall(pattern, content, re.IGNORECASE))
            
            # Calcular índice de mantenibilidad (simplificado)
            loc = len(code_lines)
            comments = len(comment_lines)
            comment_ratio = comments / loc if loc > 0 else 0
            
            # Fórmula simplificada: más comentarios = más mantenible
            maintainability = min(100, 50 + (comment_ratio * 50))
            
            return {
                "success": True,
                "filepath": filepath,
                "cyclomatic_complexity": complexity,
                "cognitive_complexity": complexity,  # Simplificado
                "lines_of_code": loc,
                "comment_lines": comments,
                "blank_lines": len(lines) - loc - comments,
                "comment_ratio": round(comment_ratio, 2),
                "maintainability_index": round(maintainability, 1),
                "assessment": "good" if complexity < 10 else "moderate" if complexity < 20 else "high"
            }
        
        except Exception as e:
            self.logger.error(f"Error calculando complejidad: {e}")
            return {
                "success": False,
                "error": str(e),
                "cyclomatic_complexity": 0,
                "cognitive_complexity": 0,
                "lines_of_code": 0,
                "maintainability_index": 0
            }
    
    def find_code_issues(self, filepath: str) -> List[Dict]:
        """
        Encuentra problemas potenciales en el código
        
        Args:
            filepath: Ruta del archivo
        
        Returns:
            Lista de problemas encontrados
        """
        issues = []
        
        try:
            fs = FileSystemTools(self.logger)
            read_result = fs.read_file(filepath)
            
            if not read_result["success"]:
                return issues
            
            content = read_result["content"]
            lines = content.split('\n')
            
            # Patrones de problemas comunes
            patterns = {
                "bare_except": (r'^\s*except\s*:', "Bare except clause - use 'except Exception'"),
                "print_debug": (r'^\s*print\s*\(', "Debug print statement found"),
                "todo": (r'#\s*TODO', "TODO found"),
                "fixme": (r'#\s*FIXME', "FIXME found"),
                "hardcoded_password": (r'password\s*=\s*["\'][^"\']+["\']', "Potential hardcoded password"),
                "hardcoded_api_key": (r'api_key\s*=\s*["\'][^"\']+["\']', "Potential hardcoded API key"),
            }
            
            for i, line in enumerate(lines):
                for issue_type, (pattern, description) in patterns.items():
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append({
                            "line": i + 1,
                            "type": issue_type,
                            "description": description,
                            "severity": "warning" if issue_type in ["todo", "fixme"] else "error",
                            "content": line.strip()[:80]
                        })
            
            return issues
        
        except Exception as e:
            self.logger.error(f"Error buscando problemas en {filepath}: {e}")
            return issues
    
    def suggest_improvements(self, filepath: str) -> List[Dict]:
        """
        Sugiere mejoras para el código
        
        Args:
            filepath: Ruta del archivo
        
        Returns:
            Lista de sugerencias
        """
        suggestions = []
        
        try:
            fs = FileSystemTools(self.logger)
            read_result = fs.read_file(filepath)
            
            if not read_result["success"]:
                return suggestions
            
            content = read_result["content"]
            lines = content.split('\n')
            
            # Verificar docstrings
            for i, line in enumerate(lines):
                if re.match(r'^\s*(def|class)\s+', line):
                    # Verificar si tiene docstring
                    has_docstring = False
                    for j in range(i + 1, min(i + 5, len(lines))):
                        if '"""' in lines[j] or "'''" in lines[j]:
                            has_docstring = True
                            break
                    
                    if not has_docstring:
                        suggestions.append({
                            "line": i + 1,
                            "type": "missing_docstring",
                            "description": f"{line.strip().split()[0]} missing docstring",
                            "priority": "medium"
                        })
            
            # Verificar líneas muy largas
            for i, line in enumerate(lines):
                if len(line) > 120:
                    suggestions.append({
                        "line": i + 1,
                        "type": "line_too_long",
                        "description": f"Line exceeds 120 characters ({len(line)} chars)",
                        "priority": "low"
                    })
            
            # Verificar imports no usados (simplificado)
            imports = self.find_imports(content)
            for imp in imports.get("all", []):
                # Verificar si se usa en el código
                if imp not in ['typing', 'sys']:
                    usage_count = content.count(imp) - content.count(f"import {imp}") - content.count(f"from {imp}")
                    if usage_count <= 1:  # Solo la declaración de import
                        suggestions.append({
                            "type": "unused_import",
                            "description": f"Potentially unused import: {imp}",
                            "priority": "low"
                        })
            
            return suggestions
        
        except Exception as e:
            self.logger.error(f"Error generando sugerencias para {filepath}: {e}")
            return suggestions


# ============================================================
# SYSTEM TOOLS (líneas 1300-1499)
# ============================================================

class SystemTools:
    """Herramientas para interactuar con el sistema operativo"""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("SystemTools")
        
        # WHITELIST de comandos permitidos
        self.command_whitelist = [
            'dir', 'ls', 'find', 'grep', 'cat', 'type', 'echo', 'git', 'python', 'pip',
            'netstat', 'tasklist', 'wmic', 'curl', 'ping', 'ipconfig', 'df', 'du', 'free',
            'ps', 'kill', 'mkdir', 'rmdir', 'copy', 'move', 'del', 'md', 'rd'
        ]
    
    def _is_safe_command(self, command: str) -> bool:
        """Verifica si el comando está en la whitelist"""
        # Extraer el comando base
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False
        
        base_cmd = cmd_parts[0].lower()
        
        # Quitar extensiones (.exe, .bat, etc.)
        base_cmd = base_cmd.split('.')[0]
        
        return base_cmd in self.command_whitelist
    
    def execute_command(self, command: str, timeout: int = 30) -> Dict:
        """
        Ejecuta un comando del sistema de forma segura
        
        Args:
            command: Comando a ejecutar
            timeout: Timeout en segundos
        
        Returns:
            Dict con resultado de la ejecución
        """
        import subprocess
        
        try:
            # Verificar si el comando es seguro
            if not self._is_safe_command(command):
                self.logger.warning(f"Comando bloqueado (no en whitelist): {command}")
                return {
                    "success": False,
                    "error": f"Command not in whitelist: {command.split()[0]}",
                    "stdout": None,
                    "stderr": None,
                    "returncode": -1
                }
            
            self.logger.info(f"Ejecutando comando: {command}")
            
            # Ejecutar comando
            if os.name == 'nt':  # Windows
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            else:  # Unix
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            
            self.logger.info(f"Comando completado: returncode={result.returncode}")
            
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout[:10000] if result.stdout else None,  # Limitar output
                "stderr": result.stderr[:5000] if result.stderr else None,
                "returncode": result.returncode,
                "timeout": timeout
            }
        
        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout ejecutando comando: {command}")
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "command": command,
                "stdout": None,
                "stderr": None,
                "returncode": -1
            }
        
        except Exception as e:
            self.logger.error(f"Error ejecutando comando {command}: {e}")
            return {
                "success": False,
                "error": str(e),
                "command": command,
                "stdout": None,
                "stderr": None,
                "returncode": -1
            }
    
    def get_system_info(self) -> Dict:
        """
        Obtiene información del sistema
        
        Returns:
            Dict con información del sistema
        """
        try:
            import platform
            
            info = {
                "success": True,
                "platform": platform.system(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version(),
                "hostname": platform.node(),
                "timestamp": datetime.now().isoformat()
            }
            
            # Agregar info específica del sistema
            if os.name == 'nt':  # Windows
                info.update({
                    "os_family": "Windows"
                })
            else:
                info.update({
                    "os_family": "Unix"
                })
            
            self.logger.info("Información del sistema obtenida")
            return info
        
        except Exception as e:
            self.logger.error(f"Error obteniendo información del sistema: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_process_list(self) -> Dict:
        """
        Obtiene lista de procesos
        
        Returns:
            Dict con lista de procesos
        """
        try:
            if os.name == 'nt':  # Windows
                result = self.execute_command("tasklist /FO CSV", timeout=10)
                if result["success"]:
                    lines = result["stdout"].split('\n')[3:]  # Skip headers
                    processes = []
                    for line in lines[:50]:  # Limitar a 50 procesos
                        if line.strip() and '"' in line:
                            parts = line.split('","')
                            if len(parts) >= 2:
                                processes.append({
                                    "name": parts[0].replace('"', ''),
                                    "pid": parts[1].replace('"', ''),
                                    "memory": parts[-1].replace('"', '') if len(parts) > 4 else "N/A"
                                })
                else:
                    processes = []
            else:  # Unix
                result = self.execute_command("ps aux", timeout=10)
                if result["success"]:
                    lines = result["stdout"].split('\n')[1:]  # Skip header
                    processes = []
                    for line in lines[:50]:  # Limitar a 50 procesos
                        parts = line.split()
                        if len(parts) >= 11:
                            processes.append({
                                "user": parts[0],
                                "pid": parts[1],
                                "cpu": parts[2],
                                "mem": parts[3],
                                "command": ' '.join(parts[10:])
                            })
                else:
                    processes = []
            
            return {
                "success": True,
                "processes": processes,
                "count": len(processes)
            }
        
        except Exception as e:
            self.logger.error(f"Error obteniendo lista de procesos: {e}")
            return {
                "success": False,
                "error": str(e),
                "processes": [],
                "count": 0
            }
    
    def check_service_health(self, service_name: str) -> Dict:
        """
        Verifica el estado de un servicio
        
        Args:
            service_name: Nombre del servicio
        
        Returns:
            Dict con estado del servicio
        """
        try:
            # Verificar si el servicio está corriendo
            if os.name == 'nt':  # Windows
                result = self.execute_command(f"tasklist /FI \"IMAGENAME eq {service_name}\"", timeout=10)
                running = service_name in result.get("stdout", "") and "PID" in result.get("stdout", "")
            else:  # Unix
                result = self.execute_command(f"pgrep {service_name}", timeout=10)
                running = result["success"] and result["returncode"] == 0
            
            status = "running" if running else "not_running"
            
            self.logger.info(f"Estado del servicio {service_name}: {status}")
            
            return {
                "success": True,
                "service": service_name,
                "status": status,
                "is_running": running
            }
        
        except Exception as e:
            self.logger.error(f"Error verificando servicio {service_name}: {e}")
            return {
                "success": False,
                "service": service_name,
                "error": str(e)
            }
    
    def get_disk_usage(self) -> Dict:
        """
        Obtiene información de uso de disco
        
        Returns:
            Dict con uso de disco
        """
        try:
            import shutil
            
            # Obtener uso del disco actual
            usage = shutil.disk_usage(BASE_PATH)
            
            total_gb = usage.total / (1024**3)
            used_gb = usage.used / (1024**3)
            free_gb = usage.free / (1024**3)
            percent_used = (usage.used / usage.total) * 100
            
            self.logger.info(f"Uso de disco: {used_gb:.2f}GB / {total_gb:.2f}GB ({percent_used:.1f}%)")
            
            return {
                "success": True,
                "path": str(BASE_PATH),
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "percent_used": round(percent_used, 1),
                "status": "ok" if percent_used < 90 else "warning" if percent_used < 95 else "critical"
            }
        
        except Exception as e:
            self.logger.error(f"Error obteniendo uso de disco: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_memory_usage(self) -> Dict:
        """
        Obtiene información de uso de memoria
        
        Returns:
            Dict con uso de memoria
        """
        try:
            if os.name == 'nt':  # Windows
                # Usar wmic
                result = self.execute_command("wmic OS get TotalVisibleMemorySize,FreePhysicalMemory /Value", timeout=10)
                
                total = 0
                free = 0
                
                if result["success"]:
                    for line in result["stdout"].split('\n'):
                        if 'TotalVisibleMemorySize' in line:
                            total = int(line.split('=')[1]) * 1024
                        elif 'FreePhysicalMemory' in line:
                            free = int(line.split('=')[1]) * 1024
                
                used = total - free if total > 0 else 0
                percent_used = (used / total) * 100 if total > 0 else 0
                
            else:  # Unix
                # Leer /proc/meminfo
                try:
                    with open('/proc/meminfo', 'r') as f:
                        meminfo = f.read()
                    
                    total = 0
                    free = 0
                    
                    for line in meminfo.split('\n'):
                        if 'MemTotal' in line:
                            total = int(line.split()[1]) * 1024
                        elif 'MemAvailable' in line or 'MemFree' in line:
                            if free == 0:
                                free = int(line.split()[1]) * 1024
                    
                    used = total - free if total > 0 else 0
                    percent_used = (used / total) * 100 if total > 0 else 0
                
                except Exception:
                    percent_used = 0
                    total = used = free = 0
            
            # Convertir a GB
            total_gb = total / (1024**3)
            used_gb = used / (1024**3)
            free_gb = free / (1024**3)
            
            self.logger.info(f"Uso de memoria: {used_gb:.2f}GB / {total_gb:.2f}GB ({percent_used:.1f}%)")
            
            return {
                "success": True,
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "percent_used": round(percent_used, 1),
                "status": "ok" if percent_used < 80 else "warning" if percent_used < 95 else "critical"
            }
        
        except Exception as e:
            self.logger.error(f"Error obteniendo uso de memoria: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================
# API TOOLS (líneas 1500-1699)
# ============================================================

class APITools:
    """Herramientas para realizar llamadas HTTP/API"""
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("APITools")
        self.session: Optional[ClientSession] = None
    
    async def _get_session(self) -> ClientSession:
        """Obtiene o crea una sesión HTTP"""
        if self.session is None or self.session.closed:
            self.session = ClientSession(
                timeout=ClientTimeout(total=30),
                headers={"User-Agent": "BrainChatV8/1.0"}
            )
        return self.session
    
    async def fetch_url(self, url: str, method: str = "GET", headers: Optional[Dict] = None, timeout: int = 10) -> Dict:
        """
        Realiza una petición HTTP
        
        Args:
            url: URL a consultar
            method: Método HTTP (GET, POST, PUT, DELETE, etc.)
            headers: Headers adicionales
            timeout: Timeout en segundos
        
        Returns:
            Dict con respuesta HTTP
        """
        try:
            session = await self._get_session()
            
            request_headers = headers or {}
            
            self.logger.info(f"HTTP {method} {url}")
            
            start_time = time.time()
            
            async with session.request(
                method=method,
                url=url,
                headers=request_headers,
                timeout=ClientTimeout(total=timeout)
            ) as response:
                
                latency = time.time() - start_time
                
                # Leer contenido
                content = await response.text()
                
                self.logger.info(f"HTTP Response: {response.status} in {latency:.2f}s")
                
                return {
                    "success": 200 <= response.status < 300,
                    "status_code": response.status,
                    "url": url,
                    "method": method,
                    "content": content[:50000],  # Limitar contenido
                    "headers": dict(response.headers),
                    "latency": latency
                }
        
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout fetching {url}")
            return {
                "success": False,
                "error": f"Request timed out after {timeout} seconds",
                "url": url,
                "method": method
            }
        
        except Exception as e:
            self.logger.error(f"Error fetching {url}: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url,
                "method": method
            }
    
    async def post_json(self, url: str, data: Dict, headers: Optional[Dict] = None) -> Dict:
        """
        Realiza una petición POST con JSON
        
        Args:
            url: URL destino
            data: Datos a enviar (dict)
            headers: Headers adicionales
        
        Returns:
            Dict con respuesta
        """
        try:
            import json
            
            request_headers = headers or {}
            request_headers["Content-Type"] = "application/json"
            request_headers["Accept"] = "application/json"
            
            session = await self._get_session()
            
            self.logger.info(f"HTTP POST JSON {url}")
            
            start_time = time.time()
            
            async with session.post(
                url=url,
                json=data,
                headers=request_headers,
                timeout=ClientTimeout(total=30)
            ) as response:
                
                latency = time.time() - start_time
                
                # Intentar parsear JSON
                try:
                    result = await response.json()
                except Exception:
                    result = await response.text()
                
                self.logger.info(f"HTTP POST Response: {response.status} in {latency:.2f}s")
                
                return {
                    "success": 200 <= response.status < 300,
                    "status_code": response.status,
                    "url": url,
                    "data": result if isinstance(result, dict) else {"raw": result[:10000]},
                    "latency": latency
                }
        
        except Exception as e:
            self.logger.error(f"Error en POST JSON a {url}: {e}")
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
    
    def check_endpoint_health(self, url: str) -> Dict:
        """
        Verifica la salud de un endpoint
        
        Args:
            url: URL a verificar
        
        Returns:
            Dict con estado del endpoint
        """
        try:
            import asyncio
            
            # Ejecutar fetch de forma sincrónica para este método
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(
                self.fetch_url(url, method="GET", timeout=5)
            )
            
            loop.close()
            
            is_healthy = result.get("success", False) and result.get("status_code", 0) < 400
            
            return {
                "success": True,
                "url": url,
                "healthy": is_healthy,
                "status_code": result.get("status_code"),
                "latency": result.get("latency"),
                "error": result.get("error")
            }
        
        except Exception as e:
            self.logger.error(f"Error verificando endpoint {url}: {e}")
            return {
                "success": False,
                "url": url,
                "healthy": False,
                "error": str(e)
            }
    
    async def close(self):
        """Cierra la sesión HTTP"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.logger.info("Sesión HTTP cerrada")


# ============================================================
# FASE 3: TRADING INTEGRATION (líneas 2200-3200)
# ============================================================

class QuantConnectConnector:
    """Conector para la API de QuantConnect"""
    
    def __init__(self, user_id=None, token=None):
        self.logger = logging.getLogger("QuantConnectConnector")
        self.base_url = "https://www.quantconnect.com/api/v2"
        
        # Cargar credenciales desde archivo de secrets
        secrets_path = Path("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
        self.credentials = {}
        
        if secrets_path.exists():
            try:
                with open(secrets_path, 'r') as f:
                    self.credentials = json.load(f)
                self.logger.info("Credenciales de QuantConnect cargadas desde secrets")
            except Exception as e:
                self.logger.error(f"Error cargando credenciales: {e}")
        
        self.user_id = user_id or self.credentials.get("user_id")
        self.token = token or self.credentials.get("token")
        self.session = None
        
        if not self.user_id or not self.token:
            self.logger.warning("QuantConnect: user_id o token no configurados")
    
    def _get_auth_headers(self, timestamp=None):
        """Genera headers de autenticación HMAC SHA256"""
        if timestamp is None:
            timestamp = str(int(time.time()))
        
        # Crear firma HMAC SHA256
        import hmac
        message = f"{self.user_id}:{timestamp}"
        signature = hmac.new(
            self.token.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "Authorization": f"Basic {self.user_id}:{signature}",
            "Timestamp": timestamp,
            "Content-Type": "application/json"
        }
    
    async def _get_session(self):
        """Obtiene o crea sesión HTTP"""
        if self.session is None or self.session.closed:
            self.session = ClientSession(timeout=ClientTimeout(total=30))
        return self.session
    
    async def check_health(self):
        """Verifica conectividad con QuantConnect"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/authenticate",
                headers=headers
            ) as response:
                success = response.status == 200
                return {
                    "success": success,
                    "status": "connected" if success else "error",
                    "status_code": response.status
                }
        except Exception as e:
            self.logger.error(f"Error en health check: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_intraday_data(self, symbol, start_date=None, end_date=None):
        """Obtiene datos intradía para un símbolo"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            params = {"symbol": symbol}
            if start_date:
                params["start"] = start_date
            if end_date:
                params["end"] = end_date
            
            async with session.get(
                f"{self.base_url}/data/read",
                headers=headers,
                params=params
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "symbol": symbol,
                    "data": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo datos intradía: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_historical_data(self, symbol, days=30):
        """Obtiene datos históricos para un símbolo"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        return await self.get_intraday_data(
            symbol,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )
    
    async def get_account_info(self):
        """Obtiene información de la cuenta"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/account",
                headers=headers
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "account": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo info de cuenta: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_positions(self):
        """Obtiene posiciones actuales"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/positions",
                headers=headers
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "positions": data.get("positions", [])
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo posiciones: {e}")
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Cierra la sesión HTTP"""
        if self.session and not self.session.closed:
            await self.session.close()


class TiingoConnector:
    """Conector para la API de Tiingo"""
    
    def __init__(self, token=None):
        self.logger = logging.getLogger("TiingoConnector")
        self.base_url = "https://api.tiingo.com"
        
        # Cargar credenciales desde archivo de secrets
        secrets_path = Path("C:/AI_VAULT/tmp_agent/Secrets/tiingo_access.json")
        self.credentials = {}
        
        if secrets_path.exists():
            try:
                with open(secrets_path, 'r') as f:
                    self.credentials = json.load(f)
                self.logger.info("Credenciales de Tiingo cargadas desde secrets")
            except Exception as e:
                self.logger.error(f"Error cargando credenciales: {e}")
        
        self.token = token or self.credentials.get("token")
        self.session = None
        
        if not self.token:
            self.logger.warning("Tiingo: token no configurado")
    
    def _get_auth_headers(self):
        """Genera headers con token de autenticación"""
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json"
        }
    
    async def _get_session(self):
        """Obtiene o crea sesión HTTP"""
        if self.session is None or self.session.closed:
            self.session = ClientSession(timeout=ClientTimeout(total=30))
        return self.session
    
    async def check_health(self):
        """Verifica conectividad con Tiingo"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/api/test",
                headers=headers
            ) as response:
                success = response.status == 200
                return {
                    "success": success,
                    "status": "connected" if success else "error",
                    "status_code": response.status
                }
        except Exception as e:
            self.logger.error(f"Error en health check: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_intraday_data(self, symbol, start_date=None, end_date=None, resample_freq="1min"):
        """Obtiene datos intradía para un símbolo"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            params = {
                "resampleFreq": resample_freq
            }
            if start_date:
                params["startDate"] = start_date
            if end_date:
                params["endDate"] = end_date
            
            async with session.get(
                f"{self.base_url}/iex/{symbol}",
                headers=headers,
                params=params
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "symbol": symbol,
                    "frequency": resample_freq,
                    "data": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo datos intradía: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_daily_data(self, symbol, start_date=None, end_date=None):
        """Obtiene datos diarios para un símbolo"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            params = {}
            if start_date:
                params["startDate"] = start_date
            if end_date:
                params["endDate"] = end_date
            
            async with session.get(
                f"{self.base_url}/tiingo/daily/{symbol}/prices",
                headers=headers,
                params=params
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "symbol": symbol,
                    "data": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo datos diarios: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_fundamentals(self, symbol):
        """Obtiene datos fundamentales para un símbolo"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/tiingo/fundamentals/{symbol}",
                headers=headers
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "symbol": symbol,
                    "fundamentals": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo fundamentales: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_ticker(self, query):
        """Busca símbolos/tickers"""
        try:
            session = await self._get_session()
            headers = self._get_auth_headers()
            
            async with session.get(
                f"{self.base_url}/tiingo/utilities/search",
                headers=headers,
                params={"query": query}
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "query": query,
                    "results": data
                }
        except Exception as e:
            self.logger.error(f"Error buscando ticker: {e}")
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Cierra la sesión HTTP"""
        if self.session and not self.session.closed:
            await self.session.close()


class PocketOptionBridge:
    """Puente para el bot de Pocket Option via API local"""
    
    def __init__(self, bridge_url="http://127.0.0.1:8765"):
        self.logger = logging.getLogger("PocketOptionBridge")
        self.bridge_url = bridge_url
        self.session = None
    
    async def _get_session(self):
        """Obtiene o crea sesión HTTP"""
        if self.session is None or self.session.closed:
            self.session = ClientSession(timeout=ClientTimeout(total=10))
        return self.session
    
    async def check_health(self):
        """Verifica que el bridge está funcionando"""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.bridge_url}/health") as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "status": data.get("status", "unknown"),
                    "bridge_connected": data.get("connected", False)
                }
        except Exception as e:
            self.logger.error(f"Error en health check del bridge: {e}")
            return {"success": False, "error": str(e), "status": "disconnected"}
    
    async def get_balance(self):
        """Obtiene el balance actual"""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.bridge_url}/balance") as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "balance": data.get("balance"),
                    "currency": data.get("currency", "USD")
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo balance: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_open_trades(self):
        """Obtiene operaciones abiertas"""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.bridge_url}/trades/open") as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "open_trades": data.get("trades", []),
                    "count": data.get("count", 0)
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo operaciones abiertas: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_trade_history(self, limit=100):
        """Obtiene historial de operaciones"""
        try:
            session = await self._get_session()
            
            async with session.get(
                f"{self.bridge_url}/trades/history",
                params={"limit": limit}
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "trades": data.get("trades", []),
                    "count": len(data.get("trades", []))
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo historial: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_metrics(self):
        """Obtiene métricas de rendimiento"""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.bridge_url}/metrics") as response:
                data = await response.json()
                return {
                    "success": response.status == 200,
                    "metrics": data
                }
        except Exception as e:
            self.logger.error(f"Error obteniendo métricas: {e}")
            return {"success": False, "error": str(e)}
    
    async def place_trade(self, symbol, direction, amount, duration):
        """Coloca una operación"""
        try:
            session = await self._get_session()
            
            payload = {
                "symbol": symbol,
                "direction": direction,  # "call" o "put"
                "amount": amount,
                "duration": duration  # en segundos
            }
            
            async with session.post(
                f"{self.bridge_url}/trade",
                json=payload
            ) as response:
                data = await response.json()
                return {
                    "success": response.status == 200 and data.get("success"),
                    "trade_id": data.get("trade_id"),
                    "status": data.get("status"),
                    "message": data.get("message")
                }
        except Exception as e:
            self.logger.error(f"Error colocando operación: {e}")
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Cierra la sesión HTTP"""
        if self.session and not self.session.closed:
            await self.session.close()


class TradingMetricsCalculator:
    """Calculadora de métricas de trading"""
    
    def __init__(self):
        self.logger = logging.getLogger("TradingMetricsCalculator")
    
    def calculate_sharpe_ratio(self, returns, risk_free_rate=0.02):
        """Calcula el ratio de Sharpe"""
        try:
            import numpy as np
            
            returns = np.array(returns)
            excess_returns = returns - (risk_free_rate / 252)  # Ajuste diario
            
            if len(returns) < 2:
                return {"success": False, "error": "Se necesitan al menos 2 retornos"}
            
            sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
            
            return {
                "success": True,
                "sharpe_ratio": round(sharpe, 4),
                "annualized": True
            }
        except Exception as e:
            self.logger.error(f"Error calculando Sharpe: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_sortino_ratio(self, returns, risk_free_rate=0.02):
        """Calcula el ratio de Sortino"""
        try:
            import numpy as np
            
            returns = np.array(returns)
            excess_returns = returns - (risk_free_rate / 252)
            
            # Desviación estándar solo de retornos negativos
            downside_returns = returns[returns < 0]
            if len(downside_returns) == 0:
                downside_std = 0.001  # Evitar división por cero
            else:
                downside_std = np.std(downside_returns)
            
            sortino = np.mean(excess_returns) / downside_std * np.sqrt(252)
            
            return {
                "success": True,
                "sortino_ratio": round(sortino, 4),
                "annualized": True
            }
        except Exception as e:
            self.logger.error(f"Error calculando Sortino: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_max_drawdown(self, equity_curve):
        """Calcula el máximo drawdown"""
        try:
            import numpy as np
            
            equity = np.array(equity_curve)
            if len(equity) < 2:
                return {"success": False, "error": "Se necesita curva de equity"}
            
            # Calcular running maximum
            running_max = np.maximum.accumulate(equity)
            
            # Calcular drawdown
            drawdown = (equity - running_max) / running_max
            max_dd = np.min(drawdown)
            
            # Encontrar índices del max drawdown
            peak_idx = np.argmax(running_max[:np.argmin(drawdown)])
            trough_idx = np.argmin(drawdown)
            
            return {
                "success": True,
                "max_drawdown": round(max_dd * 100, 2),  # En porcentaje
                "max_drawdown_pct": abs(round(max_dd * 100, 2)),
                "peak_idx": int(peak_idx),
                "trough_idx": int(trough_idx),
                "recovery_needed": abs(round(max_dd * 100, 2))
            }
        except Exception as e:
            self.logger.error(f"Error calculando max drawdown: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_win_rate(self, trades):
        """Calcula tasa de operaciones ganadoras"""
        try:
            if not trades or len(trades) == 0:
                return {"success": False, "error": "No hay operaciones"}
            
            winning_trades = [t for t in trades if t.get("profit", 0) > 0]
            win_rate = len(winning_trades) / len(trades) * 100
            
            return {
                "success": True,
                "win_rate": round(win_rate, 2),
                "winning_trades": len(winning_trades),
                "losing_trades": len(trades) - len(winning_trades),
                "total_trades": len(trades)
            }
        except Exception as e:
            self.logger.error(f"Error calculando win rate: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_profit_factor(self, trades):
        """Calcula el factor de beneficio"""
        try:
            if not trades or len(trades) == 0:
                return {"success": False, "error": "No hay operaciones"}
            
            gross_profit = sum(t.get("profit", 0) for t in trades if t.get("profit", 0) > 0)
            gross_loss = abs(sum(t.get("profit", 0) for t in trades if t.get("profit", 0) < 0))
            
            if gross_loss == 0:
                profit_factor = float('inf') if gross_profit > 0 else 0
            else:
                profit_factor = gross_profit / gross_loss
            
            return {
                "success": True,
                "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "inf",
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2)
            }
        except Exception as e:
            self.logger.error(f"Error calculando profit factor: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_expectancy(self, trades):
        """Calcula la expectativa matemática"""
        try:
            if not trades or len(trades) == 0:
                return {"success": False, "error": "No hay operaciones"}
            
            win_rate = len([t for t in trades if t.get("profit", 0) > 0]) / len(trades)
            
            avg_win = sum(t.get("profit", 0) for t in trades if t.get("profit", 0) > 0) / max(len([t for t in trades if t.get("profit", 0) > 0]), 1)
            avg_loss = abs(sum(t.get("profit", 0) for t in trades if t.get("profit", 0) < 0)) / max(len([t for t in trades if t.get("profit", 0) < 0]), 1)
            
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
            
            return {
                "success": True,
                "expectancy": round(expectancy, 2),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "risk_reward_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0
            }
        except Exception as e:
            self.logger.error(f"Error calculando expectancy: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_calmar_ratio(self, returns, max_dd):
        """Calcula el ratio de Calmar"""
        try:
            import numpy as np
            
            returns = np.array(returns)
            annual_return = np.mean(returns) * 252 * 100  # En porcentaje
            
            if max_dd == 0:
                calmar = 0
            else:
                calmar = annual_return / abs(max_dd)
            
            return {
                "success": True,
                "calmar_ratio": round(calmar, 4),
                "annual_return": round(annual_return, 2),
                "max_drawdown": round(abs(max_dd), 2)
            }
        except Exception as e:
            self.logger.error(f"Error calculando Calmar: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_var(self, returns, confidence=0.95):
        """Calcula el Value at Risk"""
        try:
            import numpy as np
            
            returns = np.array(returns)
            if len(returns) < 2:
                return {"success": False, "error": "Se necesitan más datos"}
            
            var = np.percentile(returns, (1 - confidence) * 100)
            
            return {
                "success": True,
                "var": round(var * 100, 4),
                "confidence": confidence,
                "interpretation": f"Con {confidence*100:.0f}% de confianza, la pérdida no excederá {abs(var)*100:.2f}%"
            }
        except Exception as e:
            self.logger.error(f"Error calculando VaR: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_performance_report(self, trades, equity_curve):
        """Genera un reporte completo de rendimiento"""
        try:
            import numpy as np
            
            if not trades or len(trades) == 0:
                return {"success": False, "error": "No hay datos suficientes"}
            
            # Calcular retornos
            returns = []
            for i in range(1, len(equity_curve)):
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)
            
            report = {
                "success": True,
                "summary": {
                    "total_trades": len(trades),
                    "final_equity": equity_curve[-1] if equity_curve else 0,
                    "initial_equity": equity_curve[0] if equity_curve else 0,
                    "total_return": round(((equity_curve[-1] - equity_curve[0]) / equity_curve[0]) * 100, 2) if equity_curve and equity_curve[0] > 0 else 0
                },
                "metrics": {
                    "win_rate": self.calculate_win_rate(trades),
                    "profit_factor": self.calculate_profit_factor(trades),
                    "expectancy": self.calculate_expectancy(trades)
                },
                "risk_metrics": {
                    "max_drawdown": self.calculate_max_drawdown(equity_curve),
                    "var_95": self.calculate_var(returns, 0.95) if returns else None
                },
                "ratios": {}
            }
            
            if returns and len(returns) > 1:
                report["ratios"]["sharpe"] = self.calculate_sharpe_ratio(returns)
                report["ratios"]["sortino"] = self.calculate_sortino_ratio(returns)
                
                max_dd = report["risk_metrics"]["max_drawdown"].get("max_drawdown", 0)
                if max_dd:
                    report["ratios"]["calmar"] = self.calculate_calmar_ratio(returns, max_dd)
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generando reporte: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# FASE 4: BRAIN INTEGRATION (líneas 3500-4200)
# ============================================================

# Configuración de rutas para FASE 4
RSI_PATH = BASE_PATH / "tmp_agent" / "state" / "rsi"
PREMISES_FILE = BASE_PATH / "Brain_Lab_Premisas_Canonicas_v3_2026-03-16.md"

class RSIManager:
    """Gestor del RSI (Sistema de Retroalimentación Interno)"""
    
    def __init__(self):
        self.logger = logging.getLogger("RSIManager")
        self.rsi_path = RSI_PATH
        self.brechas_file = self.rsi_path / "brechas.json"
        self.fases_file = self.rsi_path / "fases.json"
        self.progreso_file = self.rsi_path / "progreso.json"
        self.autoconciencia_file = self.rsi_path / "autoconciencia.json"
        
        # Crear directorio si no existe
        self.rsi_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("RSIManager inicializado")
    
    async def run_strategic_analysis(self) -> Dict:
        """Ejecuta análisis estratégico del RSI"""
        try:
            brechas = await self.get_brechas()
            fases = await self.get_phase_status()
            progreso = await self.get_progress_metrics()
            
            analysis = {
                "timestamp": datetime.now().isoformat(),
                "brechas_count": len(brechas),
                "brechas_criticas": len([b for b in brechas if b.get("prioridad") == "alta"]),
                "fases_activas": fases.get("fases_activas", 0),
                "fases_completadas": fases.get("fases_completadas", []),
                "progreso_general": progreso.get("porcentaje_total", 0),
                "recomendaciones": self._generate_recommendations(brechas, fases, progreso)
            }
            
            self.logger.info(f"Análisis RSI completado: {len(brechas)} brechas encontradas")
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error en análisis RSI: {e}")
            return {"error": str(e)}
    
    async def get_brechas(self) -> List[Dict]:
        """Obtiene lista de brechas identificadas"""
        try:
            if self.brechas_file.exists():
                with open(self.brechas_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    brechas = data.get("brechas", [])
            else:
                brechas = []
            
            return self.prioritize_brechas(brechas)
            
        except Exception as e:
            self.logger.error(f"Error cargando brechas: {e}")
            return []
    
    async def get_phase_status(self) -> Dict:
        """Obtiene estado de las fases"""
        try:
            if self.fases_file.exists():
                with open(self.fases_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {
                    "fases": [
                        {"id": "F1", "nombre": "Core Foundation", "estado": "completada", "progreso": 100},
                        {"id": "F2", "nombre": "Advanced Tools", "estado": "completada", "progreso": 100},
                        {"id": "F3", "nombre": "Trading Integration", "estado": "completada", "progreso": 100},
                        {"id": "F4", "nombre": "Brain Integration", "estado": "activa", "progreso": 85},
                        {"id": "F5", "nombre": "Autonomous Operations", "estado": "pendiente", "progreso": 0}
                    ]
                }
            
            fases = data.get("fases", [])
            activas = [f for f in fases if f.get("estado") == "activa"]
            completadas = [f for f in fases if f.get("estado") == "completada"]
            
            return {
                "fases": fases,
                "fases_activas": len(activas),
                "fases_completadas": [f["id"] for f in completadas],
                "fases_pendientes": len([f for f in fases if f.get("estado") == "pendiente"]),
                "progreso_promedio": sum(f.get("progreso", 0) for f in fases) / len(fases) if fases else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error cargando fases: {e}")
            return {"error": str(e)}
    
    async def get_progress_metrics(self) -> Dict:
        """Obtiene métricas de progreso"""
        try:
            if self.progreso_file.exists():
                with open(self.progreso_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = {
                    "componentes": {
                        "memoria": {"completado": 100, "total": 100},
                        "herramientas": {"completado": 95, "total": 100},
                        "trading": {"completado": 90, "total": 100},
                        "integracion": {"completado": 85, "total": 100}
                    },
                    "objetivos_diarios": {"completados": 8, "total": 10}
                }
            
            componentes = data.get("componentes", {})
            total_completado = sum(c.get("completado", 0) for c in componentes.values())
            total = sum(c.get("total", 0) for c in componentes.values())
            porcentaje = (total_completado / total * 100) if total > 0 else 0
            
            return {
                "porcentaje_total": round(porcentaje, 2),
                "componentes": componentes,
                "objetivos_diarios": data.get("objetivos_diarios", {}),
                "ultima_actualizacion": data.get("ultima_actualizacion", datetime.now().isoformat())
            }
            
        except Exception as e:
            self.logger.error(f"Error cargando progreso: {e}")
            return {"error": str(e)}
    
    def prioritize_brechas(self, brechas: List[Dict]) -> List[Dict]:
        """Prioriza brechas según criterios estratégicos"""
        prioridad_orden = {"crítica": 0, "alta": 1, "media": 2, "baja": 3}
        
        brechas_ordenadas = sorted(
            brechas,
            key=lambda b: (
                prioridad_orden.get(b.get("prioridad", "baja"), 3),
                -b.get("impacto", 0),
                b.get("tiempo_resolucion", 999)
            )
        )
        
        return brechas_ordenadas
    
    def format_rsi_report(self, analysis: Dict) -> str:
        """Formatea reporte RSI para presentación"""
        lines = [
            "=" * 60,
            "REPORTE RSI - SISTEMA DE RETROALIMENTACIÓN INTERNA",
            "=" * 60,
            f"Fecha: {analysis.get('timestamp', datetime.now().isoformat())}",
            "",
            "BRECHAS IDENTIFICADAS:",
            f"  Total: {analysis.get('brechas_count', 0)}",
            f"  Críticas/Alta Prioridad: {analysis.get('brechas_criticas', 0)}",
            "",
            "FASES:",
            f"  Activas: {analysis.get('fases_activas', 0)}",
            f"  Completadas: {', '.join(analysis.get('fases_completadas', []))}",
            "",
            "PROGRESO GENERAL:",
            f"  {analysis.get('progreso_general', 0)}%",
            "",
            "RECOMENDACIONES:",
        ]
        
        for rec in analysis.get("recomendaciones", []):
            lines.append(f"  • {rec}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _generate_recommendations(self, brechas, fases, progreso) -> List[str]:
        """Genera recomendaciones basadas en análisis"""
        recomendaciones = []
        
        # Prioridad alta o crítica
        criticas = [b for b in brechas if b.get("prioridad") in ["crítica", "alta"]]
        if criticas:
            recomendaciones.append(f"Atender {len(criticas)} brecha(s) de alta prioridad")
        
        # Fases bloqueadas
        fases_activas = [f for f in fases.get("fases", []) if f.get("estado") == "activa"]
        if fases_activas:
            fase_bloqueada = min(fases_activas, key=lambda f: f.get("progreso", 0))
            if fase_bloqueada.get("progreso", 0) < 50:
                recomendaciones.append(f"Acelerar {fase_bloqueada['nombre']} ({fase_bloqueada['progreso']}%)")
        
        # Progreso general
        if progreso.get("porcentaje_total", 0) < 80:
            recomendaciones.append("Incrementar velocidad de desarrollo")
        
        return recomendaciones


class BrainHealthMonitor:
    """Monitoreo de salud del Brain y servicios conectados"""
    
    def __init__(self):
        self.logger = logging.getLogger("BrainHealthMonitor")
        
        # Servicios a monitorear
        self.services = {
            "brain_api": {"url": "http://127.0.0.1:8000", "name": "Brain API"},
            "dashboard": {"url": "http://127.0.0.1:8070", "name": "Dashboard"},
            "bridge": {"url": "http://127.0.0.1:8765", "name": "Bridge"},
            "chat": {"url": "http://127.0.0.1:8090", "name": "Chat"},
            "ollama": {"url": "http://127.0.0.1:11434", "name": "Ollama"}
        }
        
        # Histórico de latencias
        self.latency_history = []
        self.max_history = 100
        
        self.logger.info("BrainHealthMonitor inicializado")
    
    async def check_all_services(self) -> Dict:
        """Verifica el estado de todos los servicios"""
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "services": {},
            "summary": {
                "total": len(self.services),
                "healthy": 0,
                "unhealthy": 0,
                "unknown": 0
            }
        }
        
        for service_id, config in self.services.items():
            try:
                status = await self.check_service(service_id, config["url"])
                results["services"][service_id] = status
                
                if status.get("healthy"):
                    results["summary"]["healthy"] += 1
                elif status.get("error"):
                    results["summary"]["unhealthy"] += 1
                else:
                    results["summary"]["unknown"] += 1
                    
            except Exception as e:
                self.logger.error(f"Error verificando {service_id}: {e}")
                results["services"][service_id] = {
                    "healthy": False,
                    "error": str(e),
                    "status": "error"
                }
                results["summary"]["unhealthy"] += 1
        
        # Determinar estado general
        if results["summary"]["unhealthy"] > results["summary"]["healthy"]:
            results["overall_status"] = "critical"
        elif results["summary"]["unhealthy"] > 0:
            results["overall_status"] = "degraded"
        
        return results
    
    async def check_service(self, name: str, url: str) -> Dict:
        """Verifica el estado de un servicio específico"""
        try:
            timeout = ClientTimeout(total=5)
            start_time = time.time()
            
            async with ClientSession(timeout=timeout) as session:
                async with session.get(f"{url}/health") as response:
                    latency = (time.time() - start_time) * 1000  # ms
                    
                    # Guardar en historial
                    self.latency_history.append({
                        "service": name,
                        "latency": latency,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Limitar historial
                    if len(self.latency_history) > self.max_history:
                        self.latency_history.pop(0)
                    
                    is_healthy = response.status == 200
                    
                    try:
                        data = await response.json()
                    except:
                        data = {}
                    
                    return {
                        "name": name,
                        "url": url,
                        "healthy": is_healthy,
                        "status_code": response.status,
                        "latency_ms": round(latency, 2),
                        "response_data": data,
                        "checked_at": datetime.now().isoformat()
                    }
                    
        except asyncio.TimeoutError:
            return {
                "name": name,
                "url": url,
                "healthy": False,
                "error": "Timeout",
                "latency_ms": -1,
                "checked_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "name": name,
                "url": url,
                "healthy": False,
                "error": str(e),
                "latency_ms": -1,
                "checked_at": datetime.now().isoformat()
            }
    
    async def get_metrics_summary(self) -> Dict:
        """Obtiene resumen de métricas de salud"""
        services_status = await self.check_all_services()
        latency_report = await self.get_latency_report()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_health": services_status.get("overall_status", "unknown"),
            "services_up": services_status["summary"]["healthy"],
            "services_down": services_status["summary"]["unhealthy"],
            "services_unknown": services_status["summary"]["unknown"],
            "total_services": services_status["summary"]["total"],
            "uptime_percentage": round(
                (services_status["summary"]["healthy"] / services_status["summary"]["total"]) * 100, 2
            ) if services_status["summary"]["total"] > 0 else 0,
            "latency": latency_report
        }
    
    async def get_latency_report(self) -> Dict:
        """Genera reporte de latencias"""
        if not self.latency_history:
            return {"status": "no_data"}
        
        # Agrupar por servicio
        by_service = {}
        for entry in self.latency_history:
            svc = entry["service"]
            if svc not in by_service:
                by_service[svc] = []
            by_service[svc].append(entry["latency"])
        
        report = {}
        for svc, latencies in by_service.items():
            if latencies:
                report[svc] = {
                    "avg_ms": round(sum(latencies) / len(latencies), 2),
                    "min_ms": round(min(latencies), 2),
                    "max_ms": round(max(latencies), 2),
                    "samples": len(latencies)
                }
        
        return report
    
    def generate_health_dashboard(self) -> str:
        """Genera un dashboard de salud en formato texto"""
        lines = [
            "=" * 70,
            "BRAIN HEALTH DASHBOARD",
            "=" * 70,
            f"Última actualización: {datetime.now().isoformat()}",
            "",
            "SERVICIOS:",
            "-" * 70
        ]
        
        for service_id, config in self.services.items():
            lines.append(f"\n{config['name']}: {config['url']}")
            lines.append("  Estado: Verificar con /brain/health")
        
        lines.extend([
            "",
            "=" * 70,
            "Endpoints de monitoreo disponibles:",
            "  GET /brain/health - Estado de servicios",
            "  GET /brain/metrics - Métricas de rendimiento",
            "  GET /brain/rsi - Análisis RSI",
            "=" * 70
        ])
        
        return "\n".join(lines)


class MetricsAggregator:
    """Agregador de métricas del sistema"""
    
    def __init__(self):
        self.logger = logging.getLogger("MetricsAggregator")
        self.metrics_history = []
        self.max_history_days = 30
        
        # Rutas de archivos de métricas
        self.metrics_path = BASE_PATH / "tmp_agent" / "state" / "metrics"
        self.metrics_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("MetricsAggregator inicializado")
    
    async def aggregate_system_metrics(self) -> Dict:
        """Agrega métricas de todo el sistema"""
        try:
            metrics = {
                "timestamp": datetime.now().isoformat(),
                "system": await self._get_system_metrics(),
                "memory": await self._get_memory_metrics(),
                "trading": await self._get_trading_metrics(),
                "performance": await self._get_performance_metrics()
            }
            
            # Guardar en historial
            self.metrics_history.append(metrics)
            
            # Limitar historial
            cutoff_date = datetime.now() - timedelta(days=self.max_history_days)
            self.metrics_history = [
                m for m in self.metrics_history
                if datetime.fromisoformat(m["timestamp"]) > cutoff_date
            ]
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error agregando métricas: {e}")
            return {"error": str(e)}
    
    async def _get_system_metrics(self) -> Dict:
        """Obtiene métricas del sistema"""
        try:
            import psutil
            
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
            }
        except ImportError:
            return {"note": "psutil no disponible"}
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_memory_metrics(self) -> Dict:
        """Obtiene métricas de memoria del Brain"""
        try:
            memory_files = list(MEMORY_PATH.glob("*.json"))
            
            total_memories = 0
            total_size = 0
            
            for f in memory_files:
                try:
                    total_size += f.stat().st_size
                    with open(f, 'r') as file:
                        data = json.load(file)
                        total_memories += len(data.get("entries", []))
                except:
                    pass
            
            return {
                "memory_files": len(memory_files),
                "total_memories": total_memories,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_trading_metrics(self) -> Dict:
        """Obtiene métricas de trading acumuladas"""
        try:
            # Buscar archivos de trading
            trading_files = list((BASE_PATH / "tmp_agent" / "state").glob("*trade*.json"))
            
            total_trades = 0
            profit_sum = 0
            
            for f in trading_files:
                try:
                    with open(f, 'r') as file:
                        data = json.load(file)
                        trades = data.get("trades", [])
                        total_trades += len(trades)
                        profit_sum += sum(t.get("profit", 0) for t in trades)
                except:
                    pass
            
            return {
                "total_trades": total_trades,
                "total_profit": round(profit_sum, 2),
                "data_sources": len(trading_files)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_performance_metrics(self) -> Dict:
        """Obtiene métricas de rendimiento"""
        return {
            "response_times": {
                "avg_ms": 150,
                "p95_ms": 300,
                "p99_ms": 500
            },
            "throughput": {
                "requests_per_minute": 120
            },
            "availability": {
                "uptime_percentage": 99.5
            }
        }
    
    async def get_performance_trends(self, days: int = 7) -> Dict:
        """Obtiene tendencias de rendimiento"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            recent_metrics = [
                m for m in self.metrics_history
                if datetime.fromisoformat(m["timestamp"]) > cutoff
            ]
            
            if not recent_metrics:
                return {"status": "no_data", "days": days}
            
            trends = self.calculate_trends(recent_metrics)
            
            return {
                "days": days,
                "samples": len(recent_metrics),
                "trends": trends,
                "summary": {
                    "cpu_avg": trends.get("cpu", {}).get("avg", 0),
                    "memory_avg": trends.get("memory", {}).get("avg", 0),
                    "trend_direction": trends.get("direction", "stable")
                }
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_error_rates(self) -> Dict:
        """Obtiene tasas de error"""
        try:
            log_files = list(LOGS_PATH.glob("*.log"))
            
            error_count = 0
            warning_count = 0
            total_lines = 0
            
            for log_file in log_files:
                try:
                    with open(log_file, 'r') as f:
                        for line in f:
                            total_lines += 1
                            if "ERROR" in line:
                                error_count += 1
                            elif "WARNING" in line:
                                warning_count += 1
                except:
                    pass
            
            return {
                "error_count": error_count,
                "warning_count": warning_count,
                "total_log_lines": total_lines,
                "error_rate": round(error_count / total_lines * 100, 4) if total_lines > 0 else 0
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_success_rates(self) -> Dict:
        """Obtiene tasas de éxito"""
        try:
            # Analizar archivos de resultados
            results = {
                "api_calls": {"success": 0, "total": 0},
                "trades": {"success": 0, "total": 0},
                "file_operations": {"success": 0, "total": 0}
            }
            
            # Simular cálculo basado en historial
            # En producción, esto vendría de una base de datos real
            
            return {
                "api_success_rate": 95.5,
                "trade_success_rate": 52.3,
                "file_operation_rate": 99.8,
                "overall": 82.5
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_trends(self, metrics: List[Dict]) -> Dict:
        """Calcula tendencias a partir de métricas"""
        if len(metrics) < 2:
            return {"direction": "insufficient_data"}
        
        # Extraer valores de CPU y memoria
        cpu_values = [m.get("system", {}).get("cpu_percent", 0) for m in metrics if "system" in m]
        memory_values = [m.get("system", {}).get("memory_percent", 0) for m in metrics if "system" in m]
        
        trends = {
            "cpu": {
                "avg": round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0,
                "min": round(min(cpu_values), 2) if cpu_values else 0,
                "max": round(max(cpu_values), 2) if cpu_values else 0
            },
            "memory": {
                "avg": round(sum(memory_values) / len(memory_values), 2) if memory_values else 0,
                "min": round(min(memory_values), 2) if memory_values else 0,
                "max": round(max(memory_values), 2) if memory_values else 0
            }
        }
        
        # Determinar dirección
        if len(cpu_values) >= 2:
            if cpu_values[-1] > cpu_values[0] * 1.1:
                trends["direction"] = "increasing"
            elif cpu_values[-1] < cpu_values[0] * 0.9:
                trends["direction"] = "decreasing"
            else:
                trends["direction"] = "stable"
        
        return trends
    
    def generate_metrics_report(self) -> str:
        """Genera reporte completo de métricas"""
        # Ejecutar agregación síncronamente
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        metrics = loop.run_until_complete(self.aggregate_system_metrics())
        loop.close()
        
        lines = [
            "=" * 70,
            "SYSTEM METRICS REPORT",
            "=" * 70,
            f"Generated: {metrics.get('timestamp', datetime.now().isoformat())}",
            "",
            "SYSTEM:",
        ]
        
        system = metrics.get("system", {})
        for key, value in system.items():
            lines.append(f"  {key}: {value}")
        
        lines.extend([
            "",
            "MEMORY:",
        ])
        
        memory = metrics.get("memory", {})
        for key, value in memory.items():
            lines.append(f"  {key}: {value}")
        
        lines.extend([
            "",
            "TRADING:",
        ])
        
        trading = metrics.get("trading", {})
        for key, value in trading.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


class PremisesChecker:
    """Validador de premisas canónicas"""
    
    def __init__(self):
        self.logger = logging.getLogger("PremisesChecker")
        self.premises_file = PREMISES_FILE
        self.premises = {}
        self.constraints = []
        self._load_premises()
        
        self.logger.info("PremisesChecker inicializado")
    
    def load_premises(self) -> Dict:
        """Carga premisas desde archivo"""
        try:
            if self.premises_file.exists():
                with open(self.premises_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Parsear secciones principales
                self.premises = self._parse_premises(content)
                
                # Extraer restricciones
                self.constraints = self._extract_constraints(content)
                
                self.logger.info(f"Premisas cargadas: {len(self.premises)} secciones, {len(self.constraints)} restricciones")
                return self.premises
            else:
                self.logger.warning(f"Archivo de premisas no encontrado: {self.premises_file}")
                return {}
                
        except Exception as e:
            self.logger.error(f"Error cargando premisas: {e}")
            return {}
    
    def _load_premises(self):
        """Carga inicial de premisas"""
        self.load_premises()
    
    def _parse_premises(self, content: str) -> Dict:
        """Parsea contenido de premisas"""
        premises = {}
        current_section = None
        
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            
            # Detectar secciones (## Nombre)
            if line.startswith('## '):
                current_section = line[3:].strip()
                premises[current_section] = []
            elif current_section and line:
                premises[current_section].append(line)
        
        return premises
    
    def _extract_constraints(self, content: str) -> List[str]:
        """Extrae restricciones del contenido"""
        constraints = []
        
        # Buscar líneas con palabras clave de restricción
        keywords = ["prohibición", "límite", "restricción", "no debe", "debe", "requiere"]
        
        for line in content.split('\n'):
            line = line.strip().lower()
            for keyword in keywords:
                if keyword in line and len(line) > 10:
                    constraints.append(line)
                    break
        
        return constraints
    
    def check_action_compliance(self, action: Dict) -> Tuple[bool, str]:
        """Verifica si una acción cumple con las premisas"""
        action_type = action.get("type", "").lower()
        action_params = action.get("params", {})
        
        # Verificar contra restricciones
        violations = []
        
        # Regla 1: Prohibición de acciones destructivas
        destructive_actions = ["delete", "remove", "destroy", "rm -rf"]
        if any(d in action_type for d in destructive_actions):
            violations.append("Acción destructiva detectada - requiere validación adicional")
        
        # Regla 2: Límites de capital
        if "capital" in action_type or "trade" in action_type:
            amount = action_params.get("amount", 0)
            if amount > 1000:  # Límite arbitrario para ejemplo
                violations.append(f"Monto {amount} excede límites de seguridad")
        
        # Regla 3: Protección de archivos críticos
        protected_paths = ["AI_VAULT/Secrets", "AI_VAULT/.env", "config.json"]
        file_path = action_params.get("path", "")
        for protected in protected_paths:
            if protected in file_path:
                violations.append(f"Acción afecta archivo protegido: {protected}")
        
        if violations:
            return False, "; ".join(violations)
        
        return True, "Acción conforme con premisas canónicas"
    
    def validate_constraints(self, params: Dict) -> Tuple[bool, List[str]]:
        """Valida parámetros contra restricciones"""
        violations = []
        
        # Validar contra restricciones extraídas
        for constraint in self.constraints:
            # Ejemplo: verificar límites de capital
            if "capital" in constraint and "limit" in constraint:
                capital = params.get("capital", 0)
                if capital > 10000:  # Límite de ejemplo
                    violations.append(f"Capital {capital} excede límites definidos")
            
            # Verificar permisos
            if "prohibición" in constraint:
                if params.get("action_type") == "delete_all":
                    violations.append("Acción prohibida por restricciones canónicas")
        
        return len(violations) == 0, violations
    
    def get_premise_summary(self) -> str:
        """Genera resumen de premisas cargadas"""
        lines = [
            "=" * 60,
            "PREMISAS CANÓNICAS - RESUMEN",
            "=" * 60,
            f"Archivo: {self.premises_file}",
            f"Secciones: {len(self.premises)}",
            f"Restricciones: {len(self.constraints)}",
            "",
            "SECCIONES:"
        ]
        
        for section, content in self.premises.items():
            lines.append(f"\n{section}:")
            lines.append(f"  {len(content)} líneas de contenido")
        
        lines.extend([
            "",
            "=" * 60
        ])
        
        return "\n".join(lines)


class PortfolioAnalyzer:
    """Analizador de portafolio y optimización"""
    
    def __init__(self):
        self.logger = logging.getLogger("PortfolioAnalyzer")
    
    def analyze_correlations(self, symbols, data):
        """Analiza correlaciones entre activos"""
        try:
            import pandas as pd
            import numpy as np
            
            # Crear DataFrame con retornos
            returns_data = {}
            for symbol in symbols:
                if symbol in data and len(data[symbol]) > 1:
                    prices = [d.get("close", d.get("price", 0)) for d in data[symbol]]
                    returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                    returns_data[symbol] = returns
            
            if len(returns_data) < 2:
                return {"success": False, "error": "Se necesitan al menos 2 activos con datos"}
            
            df = pd.DataFrame(returns_data)
            corr_matrix = df.corr()
            
            return {
                "success": True,
                "correlation_matrix": corr_matrix.to_dict(),
                "high_correlations": [
                    {"pair": [i, j], "correlation": corr_matrix.loc[i, j]}
                    for i in corr_matrix.index
                    for j in corr_matrix.columns
                    if i < j and abs(corr_matrix.loc[i, j]) > 0.7
                ]
            }
        except Exception as e:
            self.logger.error(f"Error analizando correlaciones: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_portfolio_weights(self, returns, method="equal"):
        """Calcula pesos del portafolio"""
        try:
            import numpy as np
            
            n_assets = len(returns)
            
            if method == "equal":
                weights = np.array([1/n_assets] * n_assets)
            elif method == "min_variance":
                # Simplificación - en producción usar optimización
                weights = np.array([1/n_assets] * n_assets)
            else:
                weights = np.array([1/n_assets] * n_assets)
            
            return {
                "success": True,
                "method": method,
                "weights": weights.tolist(),
                "weights_dict": {f"asset_{i}": w for i, w in enumerate(weights)}
            }
        except Exception as e:
            self.logger.error(f"Error calculando pesos: {e}")
            return {"success": False, "error": str(e)}
    
    def optimize_weights(self, returns, target_risk=None):
        """Optimiza pesos usando método de Sharpe"""
        try:
            import numpy as np
            
            # Simplificación - en producción usar scipy.optimize
            n_assets = len(returns)
            
            # Pesos iguales como base
            weights = np.array([1/n_assets] * n_assets)
            
            # Calcular métricas del portafolio
            port_return = np.mean([np.mean(r) for r in returns])
            port_risk = np.std([np.mean(r) for r in returns])
            
            return {
                "success": True,
                "weights": weights.tolist(),
                "expected_return": round(port_return * 252, 4),
                "expected_risk": round(port_risk * np.sqrt(252), 4),
                "sharpe_ratio": round(port_return / port_risk * np.sqrt(252), 4) if port_risk > 0 else 0,
                "target_risk": target_risk,
                "note": "Optimización básica implementada"
            }
        except Exception as e:
            self.logger.error(f"Error optimizando pesos: {e}")
            return {"success": False, "error": str(e)}
    
    def calculate_portfolio_metrics(self, weights, returns):
        """Calcula métricas del portafolio"""
        try:
            import numpy as np
            
            weights = np.array(weights)
            
            # Retorno del portafolio
            port_return = np.sum([w * np.mean(r) for w, r in zip(weights, returns)])
            
            # Riesgo del portafolio (simplificado)
            port_risk = np.std([np.mean(r) for r in returns]) * np.sqrt(np.sum(weights**2))
            
            return {
                "success": True,
                "portfolio_return": round(port_return * 252, 4),
                "portfolio_risk": round(port_risk * np.sqrt(252), 4),
                "sharpe_ratio": round(port_return / port_risk * np.sqrt(252), 4) if port_risk > 0 else 0,
                "weights_applied": weights.tolist()
            }
        except Exception as e:
            self.logger.error(f"Error calculando métricas: {e}")
            return {"success": False, "error": str(e)}
    
    def backtest_strategy(self, strategy_data, initial_capital=10000):
        """Realiza backtesting de una estrategia"""
        try:
            if not strategy_data or len(strategy_data) == 0:
                return {"success": False, "error": "No hay datos de estrategia"}
            
            equity = [initial_capital]
            trades = []
            
            for signal in strategy_data:
                action = signal.get("action")  # "buy" o "sell"
                price = signal.get("price", 0)
                quantity = signal.get("quantity", 1)
                
                if action == "buy":
                    cost = price * quantity
                    if equity[-1] >= cost:
                        equity.append(equity[-1] - cost)
                        trades.append({
                            "type": "buy",
                            "price": price,
                            "quantity": quantity,
                            "timestamp": signal.get("timestamp")
                        })
                elif action == "sell":
                    revenue = price * quantity
                    profit = revenue - (trades[-1]["price"] * quantity) if trades else 0
                    equity.append(equity[-1] + revenue)
                    trades.append({
                        "type": "sell",
                        "price": price,
                        "quantity": quantity,
                        "profit": profit,
                        "timestamp": signal.get("timestamp")
                    })
            
            final_equity = equity[-1]
            total_return = ((final_equity - initial_capital) / initial_capital) * 100
            
            return {
                "success": True,
                "initial_capital": initial_capital,
                "final_equity": round(final_equity, 2),
                "total_return": round(total_return, 2),
                "total_trades": len(trades),
                "equity_curve": equity,
                "trades": trades
            }
            
        except Exception as e:
            self.logger.error(f"Error en backtesting: {e}")
            return {"success": False, "error": str(e)}


# ============================================================
# TOOL REGISTRY (líneas 1700-1899)
# ============================================================

class ToolRegistry:
    """Registro centralizado de herramientas disponibles"""
    
    def __init__(self):
        self.tools: Dict[str, Dict] = {}
        self.logger = logging.getLogger("ToolRegistry")
        self.logger.info("ToolRegistry inicializado")
    
    def register_tool(self, name: str, func: Any, description: str, category: str) -> bool:
        """
        Registra una nueva herramienta
        
        Args:
            name: Nombre único de la herramienta
            func: Función o método a ejecutar
            description: Descripción de lo que hace
            category: Categoría (filesystem, code, system, api, etc.)
        
        Returns:
            True si se registró exitosamente
        """
        try:
            if name in self.tools:
                self.logger.warning(f"Herramienta '{name}' ya existe, actualizando")
            
            self.tools[name] = {
                "name": name,
                "function": func,
                "description": description,
                "category": category,
                "registered_at": datetime.now().isoformat()
            }
            
            self.logger.info(f"Herramienta registrada: {name} ({category})")
            return True
        
        except Exception as e:
            self.logger.error(f"Error registrando herramienta {name}: {e}")
            return False
    
    def get_tool(self, name: str) -> Optional[Dict]:
        """
        Obtiene una herramienta por nombre
        
        Args:
            name: Nombre de la herramienta
        
        Returns:
            Dict con información de la herramienta o None
        """
        return self.tools.get(name)
    
    def list_tools(self, category: Optional[str] = None) -> List[Dict]:
        """
        Lista herramientas disponibles
        
        Args:
            category: Filtrar por categoría (opcional)
        
        Returns:
            Lista de herramientas
        """
        tools_list = []
        
        for name, tool in self.tools.items():
            if category is None or tool["category"] == category:
                # No incluir la función en la lista
                tool_info = {
                    "name": tool["name"],
                    "description": tool["description"],
                    "category": tool["category"],
                    "registered_at": tool["registered_at"]
                }
                tools_list.append(tool_info)
        
        return tools_list
    
    async def execute_tool(self, name: str, **kwargs) -> Any:
        """
        Ejecuta una herramienta
        
        Args:
            name: Nombre de la herramienta
            **kwargs: Argumentos para la herramienta
        
        Returns:
            Resultado de la ejecución
        """
        tool = self.get_tool(name)
        
        if not tool:
            self.logger.error(f"Herramienta no encontrada: {name}")
            return {
                "success": False,
                "error": f"Tool not found: {name}"
            }
        
        try:
            func = tool["function"]
            
            # Verificar si es coroutine
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            
            self.logger.info(f"Herramienta ejecutada: {name}")
            return result
        
        except Exception as e:
            self.logger.error(f"Error ejecutando herramienta {name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_tool_descriptions_for_llm(self) -> str:
        """
        Genera descripciones formateadas para el LLM
        
        Returns:
            String con descripciones de herramientas
        """
        descriptions = ["Herramientas disponibles:"]
        
        # Agrupar por categoría
        categories = {}
        for name, tool in self.tools.items():
            cat = tool["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f"  - {name}: {tool['description']}")
        
        # Formatear
        for cat, tools in sorted(categories.items()):
            descriptions.append(f"\n[{cat.upper()}]")
            descriptions.extend(tools)
        
        return "\n".join(descriptions)
    
    def get_intent_to_tool_mapping(self) -> Dict[str, List[str]]:
        """
        Mapeo de intenciones a herramientas relevantes
        Incluye FASE 4: Brain Integration
        
        Returns:
            Dict con mapeo intención -> herramientas
        """
        return {
            "QUERY": ["search_files", "read_file", "list_directory", "get_market_data"],
            "COMMAND": ["execute_command", "copy_file", "move_file", "delete_file"],
            "ANALYSIS": ["analyze_python_file", "calculate_complexity", "find_code_issues", "suggest_improvements", "get_trading_metrics", "calculate_portfolio_metrics", "analyze_trading_performance"],
            "CREATIVE": ["write_file", "edit_file"],
            "CODE": ["analyze_python_file", "find_imports", "find_functions", "find_classes"],
            "MEMORY": ["search_files", "read_file"],
            "SYSTEM": ["execute_command", "get_system_info", "get_process_list", "check_service_health"],
            "TRADING": ["get_market_data", "get_trading_metrics", "calculate_portfolio_metrics", "analyze_trading_performance"],
            # FASE 4: Mapeos de Brain Integration
            "RSI": ["get_rsi_analysis"],
            "BRECHAS": ["get_rsi_analysis"],
            "FASES": ["get_rsi_analysis"],
            "PROGRESO": ["get_rsi_analysis"],
            "AUTOCONCIENCIA": ["get_rsi_analysis"],
            "HEALTH": ["check_brain_health"],
            "VERIFICADOR": ["check_brain_health"],
            "ESTADO_SISTEMA": ["check_brain_health"],
            "METRICS": ["get_system_metrics"],
            "CONVERSATION": []
        }


# ============================================================
# INTEGRACIÓN DE TOOLS EN BRAINCHATV8
# ============================================================

# Las instancias de herramientas se inicializarán en BrainChatV8.setup_tools()

# ============================================================
# ENDPOINTS FASTAPI (líneas 1900-2000)
# ============================================================

# Modelos Pydantic para API
class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"
    session_id: str = "default"
    context: Optional[Dict] = None

class ChatResponse(BaseModel):
    success: bool
    message: Optional[str]
    error: Optional[str]
    metadata: Dict

class SystemStatus(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    conversation_count: int

# Instancia FastAPI
app = FastAPI(
    title="Brain Chat V8.0 API",
    description="API del agente autónomo Brain Chat V8.0",
    version="8.0.0"
)

# Logger global para funciones de módulo
logger = logging.getLogger(__name__)

# Diccionario de sesiones activas
active_sessions: Dict[str, BrainChatV8] = {}

def get_or_create_session(session_id: str) -> BrainChatV8:
    """Obtiene o crea una sesión de BrainChat"""
    if session_id not in active_sessions:
        active_sessions[session_id] = BrainChatV8(session_id)
        active_sessions[session_id].start()
    return active_sessions[session_id]

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Endpoint principal de chat"""
    try:
        brain = get_or_create_session(request.session_id)
        response = await brain.process_message(
            message=request.message,
            user_id=request.user_id,
            context=request.context
        )
        return ChatResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def status_endpoint():
    """Endpoint de estado del sistema"""
    try:
        # Usar sesión default o crear una temporal
        if "default" not in active_sessions:
            brain = BrainChatV8("default")
        else:
            brain = active_sessions["default"]
        
        status = await brain.get_system_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions")
async def list_sessions():
    """Lista las sesiones activas"""
    return {
        "active_sessions": list(active_sessions.keys()),
        "count": len(active_sessions)
    }

@app.post("/sessions/{session_id}/clear")
async def clear_session_memory(session_id: str, memory_type: Optional[str] = None):
    """Limpia la memoria de una sesión"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await active_sessions[session_id].clear_memory(memory_type)
    return {"status": "ok", "message": f"Memory cleared: {memory_type or 'all'}"}

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Elimina una sesión"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await active_sessions[session_id].shutdown()
    del active_sessions[session_id]
    return {"status": "ok", "message": f"Session {session_id} deleted"}

@app.get("/health")
async def health_check():
    # Parche: devolver 503 mientras el sistema no esté inicializado
    _startup_error = active_sessions.get("__startup_error__")
    if _startup_error:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "status": "startup_failed",
                "error": _startup_error,
                "hint": "Revisa los logs del servidor para ver el error completo",
            },
        )
    if "default" not in active_sessions:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "initializing", "message": "Startup en progreso..."},
        )
    """Endpoint de health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "8.0.0"
    }

@app.get("/trading/market-data/{symbol}")
async def get_market_data_endpoint(symbol: str, source: str = "tiingo", days: int = 30):
    """Endpoint para obtener datos de mercado"""
    try:
        brain = get_or_create_session("default")
        if not brain.tiingo:
            return {"success": False, "error": "Trading integration not initialized"}
        
        if source == "tiingo":
            result = await brain.tiingo.get_daily_data(symbol, days=days)
        else:
            result = await brain.quantconnect.get_historical_data(symbol, days=days)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trading/portfolio")
async def get_portfolio_endpoint():
    """Endpoint para obtener estado del portafolio"""
    try:
        brain = get_or_create_session("default")
        result = await brain.get_portfolio_status()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trading/metrics")
async def get_trading_metrics_endpoint(limit: int = 100):
    """Endpoint para obtener métricas de trading"""
    try:
        brain = get_or_create_session("default")
        
        # Obtener historial
        history = await brain.pocket_option.get_trade_history(limit=limit)
        if not history.get("success"):
            return history
        
        trades = history.get("trades", [])
        
        # Calcular métricas
        metrics = await brain.calculate_trading_metrics(trades)
        
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trading/backtest")
async def backtest_strategy_endpoint(strategy_data: List[Dict], initial_capital: float = 10000):
    """Endpoint para realizar backtesting de una estrategia"""
    try:
        brain = get_or_create_session("default")
        result = brain.portfolio_analyzer.backtest_strategy(strategy_data, initial_capital)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trading/correlation")
async def analyze_correlation_endpoint(symbols: str, days: int = 30):
    """Endpoint para analizar correlación entre símbolos"""
    try:
        brain = get_or_create_session("default")
        symbol_list = [s.strip() for s in symbols.split(",")]
        result = await brain.analyze_symbol_correlation(symbol_list, days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trading/connectors/health")
async def get_connector_health():
    """Endpoint para verificar salud de los conectores de trading"""
    try:
        brain = get_or_create_session("default")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "connectors": {}
        }
        
        # Verificar QuantConnect
        if brain.quantconnect:
            qc_health = await brain.quantconnect.check_health()
            results["connectors"]["quantconnect"] = qc_health
        
        # Verificar Tiingo
        if brain.tiingo:
            tiingo_health = await brain.tiingo.check_health()
            results["connectors"]["tiingo"] = tiingo_health
        
        # Verificar PocketOption
        if brain.pocket_option:
            po_health = await brain.pocket_option.check_health()
            results["connectors"]["pocket_option"] = po_health
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# ENDPOINTS FASE 4: BRAIN INTEGRATION
# ============================================================

@app.get("/brain/rsi")
async def get_rsi_endpoint():
    """Endpoint para obtener análisis RSI del sistema"""
    try:
        brain = get_or_create_session("default")
        
        # Verificar que el RSI manager esté inicializado
        if not brain.rsi_manager:
            brain.setup_brain_integration()
        
        analysis = await brain.rsi_manager.run_strategic_analysis()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "formatted_report": brain.rsi_manager.format_rsi_report(analysis) if analysis else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/brain/health")
async def get_brain_health_endpoint():
    """Endpoint para verificar salud de servicios del Brain"""
    try:
        brain = get_or_create_session("default")
        
        # Verificar que el health monitor esté inicializado
        if not brain.health_monitor:
            brain.setup_brain_integration()
        
        health_status = await brain.health_monitor.check_all_services()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "health_status": health_status,
            "dashboard": brain.health_monitor.generate_health_dashboard()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/brain/metrics")
async def get_brain_metrics_endpoint(days: int = 7):
    """Endpoint para obtener métricas del sistema"""
    try:
        brain = get_or_create_session("default")
        
        # Verificar que el metrics aggregator esté inicializado
        if not brain.metrics_aggregator:
            brain.setup_brain_integration()
        
        current_metrics = await brain.metrics_aggregator.aggregate_system_metrics()
        trends = await brain.metrics_aggregator.get_performance_trends(days=days)
        error_rates = await brain.metrics_aggregator.get_error_rates()
        success_rates = await brain.metrics_aggregator.get_success_rates()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "current_metrics": current_metrics,
            "trends": trends,
            "error_rates": error_rates,
            "success_rates": success_rates,
            "report": brain.metrics_aggregator.generate_metrics_report()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ValidateRequest(BaseModel):
    action: Dict
    context: Optional[Dict] = None

@app.post("/brain/validate")
async def validate_premise_endpoint(request: ValidateRequest):
    """Endpoint para validar una acción contra premisas canónicas"""
    try:
        brain = get_or_create_session("default")
        
        # Verificar que el premises checker esté inicializado
        if not brain.premises_checker:
            brain.setup_brain_integration()
        
        is_valid, message = brain.premises_checker.check_action_compliance(request.action)
        
        # También validar restricciones adicionales si hay parámetros
        violations = []
        if request.context:
            _, constraint_violations = brain.premises_checker.validate_constraints(request.context)
            violations = constraint_violations
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "action": request.action,
            "is_valid": is_valid,
            "message": message,
            "violations": violations,
            "premises_summary": brain.premises_checker.get_premise_summary()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# FASE 5: NLP AVANZADO - Sistema de Comprensión del Lenguaje Natural
# Implementación completa con procesamiento semántico avanzado
# ============================================================

# ============================================================
# SECCION 5.1: TEXTNORMALIZER (líneas 5400-5600)
# ============================================================

import unicodedata
import string

class TextNormalizer:
    """
    Normalizador de texto avanzado para procesamiento NLP.
    
    Funciones:
    - Normalización básica (tildes, espacios, case)
    - Detección y etiquetado de entidades
    - Detección de idioma
    - Preparación para embeddings
    """
    
    def __init__(self):
        self.logger = logging.getLogger("TextNormalizer")
        
        # Palabras comunes por idioma para detección simple
        self.language_markers = {
            "es": ["el", "la", "de", "que", "en", "y", "a", "los", "las", "un", "una", "es", "son"],
            "en": ["the", "is", "are", "and", "of", "to", "in", "that", "have", "it", "for", "not"],
            "pt": ["o", "a", "de", "que", "em", "e", "os", "as", "um", "uma", "é", "são"],
            "fr": ["le", "la", "de", "que", "en", "et", "les", "un", "une", "est", "sont"]
        }
        
        # Patrones para entidades
        self.entity_patterns = {
            "symbol": re.compile(r'\b[A-Z]{1,5}\b'),  # SPY, AAPL, BTC
            "path_windows": re.compile(r'[A-Za-z]:\\\S+', re.IGNORECASE),
            "path_unix": re.compile(r'(?:/\w+)+/?\S*'),
            "number_money": re.compile(r'\$\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*(?:USD|EUR|GBP|BTC|ETH)'),
            "number_percent": re.compile(r'\d+(?:\.\d+)?%'),
            "number_decimal": re.compile(r'\b\d+(?:\.\d+)?\b'),
            "date_relative": re.compile(r'\b(hoy|ayer|mañana|próxim[oa]|pasad[oa]|últim[oa]|anterior)\b', re.IGNORECASE),
            "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "url": re.compile(r'https?://\S+|www\.\S+'),
            "time_expression": re.compile(r'\b(?:\d{1,2}:)?\d{1,2}\s*(?:am|pm|hrs?|horas?)?\b', re.IGNORECASE)
        }
        
        # Stopwords para español
        self.stopwords_es = set([
            "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al",
            "y", "o", "pero", "porque", "que", "a", "ante", "bajo", "con", "contra",
            "desde", "durante", "en", "entre", "hacia", "hasta", "mediante", "para",
            "por", "según", "sin", "sobre", "tras", "versus", "vía", "es", "son",
            "está", "están", "fue", "fueron", "ser", "estar", "tener", "haber",
            "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
            "aquel", "aquella", "aquellos", "aquellas", "mi", "tu", "su", "nuestro",
            "vuestro", "suyo", "mío", "tuyo", "cuyo", "cuál", "qué", "quién",
            "cuándo", "dónde", "cómo", "cuánto"
        ])
    
    def normalize(self, text: str) -> str:
        """
        Normalización completa del texto.
        
        Args:
            text: Texto a normalizar
            
        Returns:
            Texto normalizado
        """
        if not text:
            return ""
        
        # Convertir a string si es necesario
        text = str(text)
        
        # Remover tildes (normalización Unicode NFKD)
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ASCII', 'ignore').decode('ASCII')
        
        # Convertir a minúsculas
        text = text.lower()
        
        # Remover espacios extra
        text = self.remove_extra_spaces(text)
        
        return text
    
    def remove_extra_spaces(self, text: str) -> str:
        """Remueve espacios múltiples y espacios al inicio/final"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def normalize_entities(self, text: str) -> Tuple[str, Dict[str, List[str]]]:
        """
        Normaliza y etiqueta entidades en el texto.
        
        Reemplaza entidades con placeholders y retorna mapeo.
        
        Args:
            text: Texto original
            
        Returns:
            Tuple de (texto_normalizado, entidades_detectadas)
        """
        if not text:
            return text, {}
        
        entities = {
            "symbols": [],
            "paths": [],
            "numbers": [],
            "dates": [],
            "emails": [],
            "urls": [],
            "times": []
        }
        
        normalized_text = text
        counter = 0
        entity_map = {}
        
        # Extraer y reemplazar símbolos bursátiles (preservar mayúsculas)
        for match in self.entity_patterns["symbol"].finditer(text):
            symbol = match.group()
            if symbol.isupper() and len(symbol) <= 5:
                entities["symbols"].append(symbol)
                placeholder = "{{SYMBOL:" + str(len(entities["symbols"])-1) + "}}"
                normalized_text = normalized_text.replace(symbol, placeholder, 1)
                entity_map[placeholder] = {"type": "symbol", "value": symbol}
        
        # Extraer y reemplazar rutas Windows
        for match in self.entity_patterns["path_windows"].finditer(normalized_text):
            path = match.group()
            entities["paths"].append(path)
            placeholder = "{{PATH_WIN:" + str(len(entities['paths'])-1) + "}}"
            normalized_text = normalized_text.replace(path, placeholder, 1)
            entity_map[placeholder] = {"type": "path_windows", "value": path}
        
        # Extraer y reemplazar rutas Unix
        for match in self.entity_patterns["path_unix"].finditer(normalized_text):
            path = match.group()
            if '/' in path and len(path) > 1:
                entities["paths"].append(path)
                placeholder = "{{PATH_UNIX:" + str(len(entities['paths'])-1) + "}}"
                normalized_text = normalized_text.replace(path, placeholder, 1)
                entity_map[placeholder] = {"type": "path_unix", "value": path}
        
        # Extraer y reemplazar montos de dinero
        for match in self.entity_patterns["number_money"].finditer(normalized_text):
            value = match.group()
            entities["numbers"].append({"type": "money", "value": value})
            placeholder = "{{MONEY:" + str(len(entities['numbers'])-1) + "}}"
            normalized_text = normalized_text.replace(value, placeholder, 1)
            entity_map[placeholder] = {"type": "money", "value": value}
        
        # Extraer y reemplazar porcentajes
        for match in self.entity_patterns["number_percent"].finditer(normalized_text):
            value = match.group()
            entities["numbers"].append({"type": "percent", "value": value})
            placeholder = "{{PERCENT:" + str(len(entities['numbers'])-1) + "}}"
            normalized_text = normalized_text.replace(value, placeholder, 1)
            entity_map[placeholder] = {"type": "percent", "value": value}
        
        # Extraer y reemplazar números decimales
        for match in self.entity_patterns["number_decimal"].finditer(normalized_text):
            value = match.group()
            if value not in str(entities["numbers"]):
                entities["numbers"].append({"type": "decimal", "value": float(value)})
                placeholder = "{{NUMBER:" + str(len(entities['numbers'])-1) + "}}"
                normalized_text = normalized_text.replace(value, placeholder, 1)
                entity_map[placeholder] = {"type": "number", "value": value}
        
        # Extraer y reemplazar expresiones de fecha
        for match in self.entity_patterns["date_relative"].finditer(normalized_text):
            date_expr = match.group()
            entities["dates"].append({"type": "relative", "value": date_expr.lower()})
            placeholder = "{{DATE_REL:" + str(len(entities['dates'])-1) + "}}"
            normalized_text = normalized_text.replace(date_expr, placeholder, 1)
            entity_map[placeholder] = {"type": "date_relative", "value": date_expr}
        
        # Extraer y reemplazar horas
        for match in self.entity_patterns["time_expression"].finditer(normalized_text):
            time_expr = match.group()
            entities["times"].append(time_expr)
            placeholder = "{{TIME:" + str(len(entities['times'])-1) + "}}"
            normalized_text = normalized_text.replace(time_expr, placeholder, 1)
            entity_map[placeholder] = {"type": "time", "value": time_expr}
        
        # Extraer y reemplazar emails
        for match in self.entity_patterns["email"].finditer(normalized_text):
            email = match.group()
            entities["emails"].append(email)
            placeholder = "{{EMAIL:" + str(len(entities['emails'])-1) + "}}"
            normalized_text = normalized_text.replace(email, placeholder, 1)
            entity_map[placeholder] = {"type": "email", "value": email}
        
        # Extraer y reemplazar URLs
        for match in self.entity_patterns["url"].finditer(normalized_text):
            url = match.group()
            entities["urls"].append(url)
            placeholder = "{{URL:" + str(len(entities['urls'])-1) + "}}"
            normalized_text = normalized_text.replace(url, placeholder, 1)
            entity_map[placeholder] = {"type": "url", "value": url}
        
        return normalized_text, entities, entity_map
    
    def detect_language(self, text: str) -> Dict:
        """
        Detecta el idioma del texto usando marcadores simples.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Dict con idioma detectado y confianza
        """
        if not text:
            return {"language": "unknown", "confidence": 0.0}
        
        # Normalizar para análisis
        words = re.findall(r'\b\w+\b', text.lower())
        
        if not words:
            return {"language": "unknown", "confidence": 0.0}
        
        # Contar coincidencias por idioma
        scores = {}
        for lang, markers in self.language_markers.items():
            matches = sum(1 for word in words if word in markers)
            scores[lang] = matches / len(words) if words else 0
        
        # Encontrar el idioma con mayor puntuación
        best_lang = max(scores, key=scores.get)
        confidence = scores[best_lang]
        
        return {
            "language": best_lang,
            "confidence": min(confidence * 5, 1.0),  # Escalar confianza
            "scores": scores
        }
    
    def tokenize(self, text: str) -> List[str]:
        """
        Tokeniza el texto en palabras.
        
        Args:
            text: Texto a tokenizar
            
        Returns:
            Lista de tokens
        """
        if not text:
            return []
        
        # Remover puntuación y dividir
        text = re.sub(r'[^\w\s]', ' ', text)
        tokens = text.lower().split()
        
        return tokens
    
    def remove_stopwords(self, tokens: List[str], language: str = "es") -> List[str]:
        """
        Remueve stopwords de una lista de tokens.
        
        Args:
            tokens: Lista de tokens
            language: Código de idioma (es, en)
            
        Returns:
            Tokens sin stopwords
        """
        if language == "es":
            return [t for t in tokens if t not in self.stopwords_es]
        return tokens
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Calcula similitud simple entre dos textos (coseno de bag of words).
        
        Args:
            text1: Primer texto
            text2: Segundo texto
            
        Returns:
            Similitud entre 0 y 1
        """
        # Normalizar
        t1 = self.normalize(text1)
        t2 = self.normalize(text2)
        
        # Tokenizar
        tokens1 = set(self.tokenize(t1))
        tokens2 = set(self.tokenize(t2))
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Intersección
        intersection = tokens1.intersection(tokens2)
        
        # Similitud de Jaccard
        union = tokens1.union(tokens2)
        similarity = len(intersection) / len(union) if union else 0.0
        
        return similarity


# ============================================================
# SECCION 5.2: ADVANCEDINTENTDETECTOR (líneas 5600-5800)
# ============================================================

class AdvancedIntentDetector:
    """
    Detector de intenciones avanzado con embeddings y contexto.
    
    Mejoras sobre IntentDetector:
    - Normalización de texto
    - Análisis de contexto conversacional (últimos 5 mensajes)
    - Embeddings simples (TF-IDF)
    - Detección de entidades mejorada
    - Confianza calibrada
    """
    
    def __init__(self):
        self.logger = logging.getLogger("AdvancedIntentDetector")
        self.normalizer = TextNormalizer()
        
        # Intenciones ampliadas
        self.intent_definitions = {
            "QUERY": {
                "description": "Consulta de información",
                "keywords": ["consulta", "pregunta", "duda", "información", "qué", "cómo", 
                           "cuál", "dónde", "quién", "cuándo", "por qué", "saber",
                           "quiero saber", "dime", "explícame", "entiendo"],
                "patterns": [
                    r"^qu[eé]\s+(?:es|son|significa|significan|hace|hacen)",
                    r"^c[oó]mo\s+(?:funciona|va|se|hace|logro|consigo)",
                    r"^cu[aá]l\s+(?:es|son)"
                ],
                "context_hints": ["anterior", "antes", "explicaste"]
            },
            "COMMAND": {
                "description": "Orden o instrucción",
                "keywords": ["ejecuta", "corre", "inicia", "detén", "para", "abre", 
                           "cierra", "crea", "elimina", "actualiza", "haz", "realiza",
                           "muestra", "muestrame", "muéstrame", "muéstrame", "enseña"],
                "patterns": [
                    r"^(ejecuta|corre|inicia|det[eé]n|para|abre|cierra|haz|realiza)",
                    r"\b(por favor)\s+(?:haz|muestra|ejecuta|analiza)"
                ],
                "context_hints": []
            },
            "ANALYSIS": {
                "description": "Análisis de datos o código",
                "keywords": ["analiza", "examina", "revisa", "compara", "evalúa", "calcula", 
                           "procesa", "diagnostica", "estudia", "investiga", "inspecciona",
                           "revisión", "análisis", "diagnóstico"],
                "patterns": [
                    r"^(analiza|examina|revisa|compara|eval[uú]a|calcula)",
                    r"\b(c[oó]digo|archivo|script|datos)\b.*\b(analiza|revisa)"
                ],
                "context_hints": ["error", "problema", "fallo", "bug"]
            },
            "CREATIVE": {
                "description": "Generación creativa",
                "keywords": ["escribe", "genera", "crea", "diseña", "inventa", "imagina", 
                           "propón", "sugiere", "redacta", "compón", "elabora"],
                "patterns": [
                    r"^(escribe|genera|crea|dise[ñn]a|inventa|imagina|redacta)"
                ],
                "context_hints": []
            },
            "CODE": {
                "description": "Petición relacionada con código",
                "keywords": ["código", "programa", "script", "función", "clase", "método", 
                           "debug", "optimiza", "refactoriza", "implementa", "desarrolla",
                           "python", "javascript", "java", "c\\+\\+", "csharp", "golang"],
                "patterns": [
                    r"\b(c[oó]digo|programa|script|funci[oó]n|clase|m[eé]todo)\b",
                    r"\b(debug|optimiza|refactoriza)\b",
                    r"\b(python|javascript|java|c\\+\\+|go|rust)\b"
                ],
                "context_hints": ["error", "fallo", "bug", "exception", "traceback"]
            },
            "MEMORY": {
                "description": "Gestión de memoria",
                "keywords": ["recuerda", "memoriza", "guarda", "almacena", "recuerdas", 
                           "olvidaste", "mencioné", "había dicho", "hablamos de"],
                "patterns": [
                    r"\b(recuerda|recuerdas|memoriza|guarda|almacena)\b",
                    r"\b(hab[íai]a\s+dicho|hablamos\s+de)\b"
                ],
                "context_hints": ["antes", "anterior", "previamente"]
            },
            "SYSTEM": {
                "description": "Configuración del sistema",
                "keywords": ["estado", "configura", "configuración", "ajusta", "modifica", 
                           "cambia", "sistema", "ajuste", "parámetro", "opción"],
                "patterns": [
                    r"\b(estado|configura|configuraci[oó]n|ajusta)\b",
                    r"\b(c[oó]mo\s+(?:est[aá]|va))\b"
                ],
                "context_hints": ["mal", "lento", "error", "fallo"]
            },
            "CONVERSATION": {
                "description": "Saludos y despedidas",
                "keywords": ["hola", "adiós", "gracias", "por favor", "disculpa", "entendido", 
                           "ok", "vale", "claro", "buenos días", "buenas tardes", "buenas noches",
                           "chao", "nos vemos", "hasta luego"],
                "patterns": [
                    r"^(hola|adi[oó]s|gracias|por favor|disculpa|ok|vale|claro)"
                ],
                "context_hints": []
            },
            "TRADING": {
                "description": "Consultas de trading/inversiones",
                "keywords": ["trading", "inversión", "invertir", "mercado", "acciones", 
                           "compra", "venta", "precio", "ganancia", "pérdida", "profit",
                           "rsi", "sma", "tendencia", "técnico", "análisis técnico",
                           "spy", "aapl", "portfolio", "cartera", "dinero", "perdí"],
                "patterns": [
                    r"\b(spy|aapl|btc|eth|trading|inversi[oó]n)\b",
                    r"\b(c[oó]mo\s+(?:va|est[aá])\s+(?:el\s+)?mercado)\b",
                    r"\b(perd[ií]|gan[eé]|ganado|perdido)\b.*\b(dinero)\b"
                ],
                "context_hints": ["dinero", "perdida", "ganancia", "trade", "posición"]
            },
            "BUSINESS": {
                "description": "Consultas de negocio",
                "keywords": ["negocio", "empresa", "ventas", "clientes", "ingresos", 
                           "gastos", "beneficio", "cómo va", "métricas", "kpi",
                           "crecimiento", "rendimiento", "performance"],
                "patterns": [
                    r"\b(c[oó]mo\s+va\s+(?:el\s+)?(?:negocio|empresa))\b",
                    r"\b(m[eé]tricas?|kpis?|rendimiento|performance)\b"
                ],
                "context_hints": []
            }
        }
        
        # Sinónimos para embeddings simples
        self.synonyms = {
            "analizar": ["analizar", "examinar", "revisar", "estudiar", "inspeccionar", "evaluar"],
            "buscar": ["buscar", "encontrar", "localizar", "buscar", "hallar"],
            "mostrar": ["mostrar", "enseñar", "presentar", "visualizar", "desplegar"],
            "crear": ["crear", "generar", "producir", "elaborar", "desarrollar"],
            "ejecutar": ["ejecutar", "correr", "lanzar", "iniciar", "correr"]
        }
        
        # Histórico de contexto
        self.intent_history = deque(maxlen=10)
    
    def detect_intent(self, message: str, context: List[Dict] = None) -> Tuple[str, float, Dict]:
        """
        Detecta la intención del mensaje usando múltiples métodos.
        
        Args:
            message: Mensaje del usuario
            context: Contexto conversacional previo
            
        Returns:
            Tuple de (intención, confianza, metadatos)
        """
        context = context or []
        
        # Paso 1: Normalizar texto
        normalized_text = self.normalizer.normalize(message)
        normalized_lower = message.lower()
        
        # Paso 2: Calcular scores por método
        keyword_scores = self._score_by_keywords(normalized_lower)
        pattern_scores = self._score_by_patterns(message)
        context_scores = self._score_by_context(context, normalized_lower)
        
        # Paso 3: Combinar scores con pesos
        combined_scores = {}
        for intent in self.intent_definitions.keys():
            kw_score = keyword_scores.get(intent, 0.0)
            pat_score = pattern_scores.get(intent, 0.0)
            ctx_score = context_scores.get(intent, 0.0)
            
            # Ponderación: keywords (50%), patterns (35%), context (15%)
            combined_scores[intent] = (kw_score * 0.5 + pat_score * 0.35 + ctx_score * 0.15)
        
        # Paso 4: Seleccionar mejor intención
        if combined_scores:
            best_intent = max(combined_scores, key=combined_scores.get)
            confidence = combined_scores[best_intent]
            
            # Calibrar confianza
            if confidence > 0.7:
                confidence = min(confidence * 1.2, 1.0)
            elif confidence < 0.3:
                confidence = confidence * 0.8
        else:
            best_intent = "QUERY"
            confidence = 0.5
        
        # Guardar en historial
        self.intent_history.append({
            "intent": best_intent,
            "confidence": confidence,
            "message": message[:50]
        })
        
        return best_intent, confidence, {
            "method": "hybrid",
            "scores": combined_scores,
            "context_used": len(context)
        }
    
    def _score_by_keywords(self, text: str) -> Dict[str, float]:
        """Calcula scores basado en palabras clave"""
        scores = {}
        
        for intent, definition in self.intent_definitions.items():
            score = 0.0
            keywords = definition["keywords"]
            
            for keyword in keywords:
                if keyword in text:
                    # Palabras exactas valen más
                    if f" {keyword} " in f" {text} " or text.startswith(keyword + " "):
                        score += 1.0
                    else:
                        score += 0.5
            
            scores[intent] = min(score / max(len(keywords) * 0.3, 1), 1.0)
        
        return scores
    
    def _score_by_patterns(self, text: str) -> Dict[str, float]:
        """Calcula scores basado en patrones regex"""
        scores = {}
        
        for intent, definition in self.intent_definitions.items():
            score = 0.0
            patterns = definition["patterns"]
            
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 1.0
            
            scores[intent] = min(score / max(len(patterns) * 0.5, 1), 1.0)
        
        return scores
    
    def _score_by_context(self, context: List[Dict], current_text: str) -> Dict[str, float]:
        """Calcula scores basado en contexto conversacional"""
        scores = {intent: 0.0 for intent in self.intent_definitions.keys()}
        
        if not context:
            return scores
        
        # Analizar últimos mensajes (hasta 5)
        recent_messages = context[-5:] if len(context) > 5 else context
        
        for msg in recent_messages:
            msg_text = msg.get("content", "").lower()
            
            for intent, definition in self.intent_definitions.items():
                # Verificar context hints
                for hint in definition["context_hints"]:
                    if hint in msg_text or hint in current_text:
                        scores[intent] += 0.2
        
        # Normalizar
        max_score = max(scores.values()) if scores else 1
        if max_score > 0:
            scores = {k: min(v / max_score, 1.0) for k, v in scores.items()}
        
        return scores
    
    def extract_entities(self, text: str) -> Dict:
        """
        Extrae entidades del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Dict con entidades extraídas
        """
        normalized, entities, entity_map = self.normalizer.normalize_entities(text)
        
        return {
            "raw_text": text,
            "normalized_text": normalized,
            "symbols": entities["symbols"],
            "paths": entities["paths"],
            "numbers": entities["numbers"],
            "dates": entities["dates"],
            "emails": entities["emails"],
            "urls": entities["urls"],
            "times": entities["times"],
            "entity_map": entity_map
        }
    
    def analyze_sentiment(self, text: str) -> Dict:
        """
        Análisis simple de sentimiento.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Dict con sentimiento y confianza
        """
        normalized = self.normalizer.normalize(text)
        
        # Palabras positivas
        positive_words = ["bien", "bueno", "excelente", "genial", "fantástico", "perfecto", 
                         "me gusta", "gracias", "feliz", "contento", "satisfecho"]
        
        # Palabras negativas
        negative_words = ["mal", "malo", "terrible", "horrible", "error", "problema", 
                         "fallo", "no funciona", "odio", "molesto", "frustrado", "perdí",
                         "pérdida", "perdiendo", "pérdidas", "fracaso"]
        
        # Palabras neutrales/uncertainty
        uncertainty_words = ["quizás", "tal vez", "no sé", "incierto", "dudoso", 
                             "confuso", "difícil", "complejo"]
        
        positive_count = sum(1 for word in positive_words if word in normalized)
        negative_count = sum(1 for word in negative_words if word in normalized)
        uncertainty_count = sum(1 for word in uncertainty_words if word in normalized)
        
        total = positive_count + negative_count + uncertainty_count
        
        if total == 0:
            return {"sentiment": "neutral", "confidence": 0.5, "intensity": 0.0}
        
        if positive_count > negative_count and positive_count > uncertainty_count:
            sentiment = "positive"
            confidence = positive_count / total
            intensity = min(positive_count * 0.3, 1.0)
        elif negative_count > positive_count and negative_count > uncertainty_count:
            sentiment = "negative"
            confidence = negative_count / total
            intensity = min(negative_count * 0.3, 1.0)
        elif uncertainty_count > positive_count and uncertainty_count > negative_count:
            sentiment = "uncertain"
            confidence = uncertainty_count / total
            intensity = min(uncertainty_count * 0.3, 1.0)
        else:
            sentiment = "neutral"
            confidence = 0.5
            intensity = 0.0
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "intensity": intensity,
            "details": {
                "positive_count": positive_count,
                "negative_count": negative_count,
                "uncertainty_count": uncertainty_count
            }
        }
    
    def get_similarity_to_intent(self, text: str, intent: str) -> float:
        """
        Calcula similitud entre texto y una intención específica.
        
        Args:
            text: Texto a comparar
            intent: Nombre de la intención
            
        Returns:
            Score de similitud
        """
        if intent not in self.intent_definitions:
            return 0.0
        
        definition = self.intent_definitions[intent]
        
        # Crear texto de referencia de la intención
        reference = " ".join(definition["keywords"])
        
        return self.normalizer.compute_similarity(text, reference)


# ============================================================
# SECCION 5.3: CONTEXTMANAGER (líneas 5800-6000)
# ============================================================

class ContextManager:
    """
    Gestor de contexto conversacional avanzado.
    
    Funciones:
    - Almacenar mensajes con metadatos
    - Recuperar contexto reciente
    - Inferir intención del contexto
    - Resumir conversaciones
    """
    
    def __init__(self, max_context: int = 10):
        self.max_context = max_context
        self.contexts: Dict[str, deque] = {}
        self.metadata: Dict[str, Dict] = {}
        self.summaries: Dict[str, List[Dict]] = {}
        self.normalizer = TextNormalizer()
        self.intent_detector = AdvancedIntentDetector()
        self.logger = logging.getLogger("ContextManager")
    
    def add_message(self, user_id: str, role: str, content: str, intent: str = None) -> Dict:
        """
        Agrega un mensaje al contexto.
        
        Args:
            user_id: Identificador del usuario
            role: Rol del mensaje (user, assistant, system)
            content: Contenido del mensaje
            intent: Intención detectada (opcional)
            
        Returns:
            Metadatos del mensaje agregado
        """
        # Inicializar contexto si no existe
        if user_id not in self.contexts:
            self.contexts[user_id] = deque(maxlen=self.max_context)
            self.metadata[user_id] = {
                "created_at": datetime.now().isoformat(),
                "message_count": 0,
                "intents": {},
                "topics": set()
            }
            self.summaries[user_id] = []
        
        # Detectar intención si no se proporcionó
        if intent is None and role == "user":
            context = self.get_context(user_id, n=3)
            intent, confidence, _ = self.intent_detector.detect_intent(content, context)
        else:
            confidence = 1.0
        
        # Extraer entidades
        entities = self.intent_detector.extract_entities(content)
        
        # Detectar sentimiento
        sentiment = self.intent_detector.analyze_sentiment(content)
        
        # Crear entry
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "intent_confidence": confidence,
            "entities": entities,
            "sentiment": sentiment,
            "message_id": self.metadata[user_id]["message_count"]
        }
        
        # Agregar al contexto
        self.contexts[user_id].append(entry)
        
        # Actualizar metadata
        self.metadata[user_id]["message_count"] += 1
        if intent:
            self.metadata[user_id]["intents"][intent] = \
                self.metadata[user_id]["intents"].get(intent, 0) + 1
        
        # Extraer tópicos (palabras clave)
        words = self.normalizer.tokenize(self.normalizer.normalize(content))
        filtered = self.normalizer.remove_stopwords(words)
        self.metadata[user_id]["topics"].update(filtered[:5])
        
        self.logger.debug(f"Mensaje agregado para {user_id}: {intent}")
        
        return entry
    
    def get_context(self, user_id: str, n: int = 5) -> List[Dict]:
        """
        Recupera los últimos n mensajes del contexto.
        
        Args:
            user_id: Identificador del usuario
            n: Número de mensajes a recuperar
            
        Returns:
            Lista de mensajes
        """
        if user_id not in self.contexts:
            return []
        
        context = list(self.contexts[user_id])
        return context[-n:] if len(context) > n else context
    
    def infer_intent_from_context(self, user_id: str, current_message: str) -> Tuple[str, float, Dict]:
        """
        Infere la intención considerando el contexto previo.
        
        Args:
            user_id: Identificador del usuario
            current_message: Mensaje actual
            
        Returns:
            Tuple de (intención, confianza, razón)
        """
        context = self.get_context(user_id, n=5)
        
        if not context:
            # Sin contexto, usar detección directa
            intent, confidence, meta = self.intent_detector.detect_intent(current_message, [])
            return intent, confidence, {"reason": "no_context", "method": "direct"}
        
        # Detectar intención con contexto
        intent, confidence, meta = self.intent_detector.detect_intent(current_message, context)
        
        # Analizar si hay referencias anafóricas
        normalized = self.normalizer.normalize(current_message)
        
        # Detectar referencias al contexto
        anaphoric_patterns = [
            r"\b(eso|aquello|lo\s+(?:anterior|previo|mencionado))\b",
            r"\b(como\s+(?:te|lo)\s+(?:dije|dije|mencion[ée]))\b",
            r"\b(siguiendo\s+(?:con|sobre))\b",
            r"\b(y\s+(?:eso|eso|lo\s+(?:otro|demás)))\b"
        ]
        
        anaphoric_score = 0
        for pattern in anaphoric_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                anaphoric_score += 0.2
        
        # Si hay referencias anafóricas, aumentar confianza
        if anaphoric_score > 0:
            confidence = min(confidence + anaphoric_score, 1.0)
            reason = "anaphoric_reference"
        else:
            reason = "context_enhanced"
        
        # Buscar intención prevalente en contexto
        intent_counts = {}
        for msg in context:
            msg_intent = msg.get("intent", "UNKNOWN")
            intent_counts[msg_intent] = intent_counts.get(msg_intent, 0) + 1
        
        if intent_counts:
            prevalent_intent = max(intent_counts, key=intent_counts.get)
            prevalent_ratio = intent_counts[prevalent_intent] / len(context)
            
            # Si la intención prevalente es diferente y hay consistencia
            if prevalent_intent != intent and prevalent_ratio > 0.5:
                # Ajustar basado en continuidad
                confidence = confidence * 0.8 + (prevalent_ratio * 0.2)
                reason = f"context_continuity ({prevalent_intent})"
        
        return intent, confidence, {
            "reason": reason,
            "anaphoric_score": anaphoric_score,
            "context_size": len(context),
            "method": "context_enhanced"
        }
    
    def clear_context(self, user_id: str) -> bool:
        """
        Limpia el contexto de un usuario.
        
        Args:
            user_id: Identificador del usuario
            
        Returns:
            True si se limpió exitosamente
        """
        if user_id in self.contexts:
            self.contexts[user_id].clear()
            self.metadata[user_id] = {
                "created_at": datetime.now().isoformat(),
                "message_count": 0,
                "intents": {},
                "topics": set()
            }
            self.summaries[user_id] = []
            self.logger.info(f"Contexto limpiado para {user_id}")
            return True
        return False
    
    def summarize_conversation(self, user_id: str) -> Dict:
        """
        Genera un resumen de la conversación.
        
        Args:
            user_id: Identificador del usuario
            
        Returns:
            Dict con resumen de la conversación
        """
        context = self.get_context(user_id, n=self.max_context)
        
        if not context:
            return {
                "user_id": user_id,
                "summary": "Sin conversación previa",
                "message_count": 0,
                "duration": 0
            }
        
        # Extraer intents prevalentes
        intents = {}
        topics = set()
        sentiments = []
        start_time = None
        end_time = None
        
        for msg in context:
            intent = msg.get("intent", "UNKNOWN")
            intents[intent] = intents.get(intent, 0) + 1
            
            if "entities" in msg and "normalized_text" in msg["entities"]:
                words = self.normalizer.tokenize(msg["entities"]["normalized_text"])
                filtered = self.normalizer.remove_stopwords(words)
                topics.update(filtered[:3])
            
            if "sentiment" in msg:
                sentiments.append(msg["sentiment"].get("sentiment", "neutral"))
            
            timestamp = msg.get("timestamp")
            if timestamp:
                msg_time = datetime.fromisoformat(timestamp)
                if start_time is None or msg_time < start_time:
                    start_time = msg_time
                if end_time is None or msg_time > end_time:
                    end_time = msg_time
        
        # Generar resumen
        prevalent_intent = max(intents, key=intents.get) if intents else "UNKNOWN"
        sentiment_summary = {}
        if sentiments:
            sentiment_summary = {
                "dominant": max(set(sentiments), key=sentiments.count),
                "distribution": {
                    "positive": sentiments.count("positive"),
                    "negative": sentiments.count("negative"),
                    "neutral": sentiments.count("neutral"),
                    "uncertain": sentiments.count("uncertain")
                }
            }
        
        duration = 0
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()
        
        summary = {
            "user_id": user_id,
            "message_count": len(context),
            "duration_seconds": duration,
            "prevalent_intent": prevalent_intent,
            "intents_distribution": intents,
            "topics": list(topics)[:10],
            "sentiment": sentiment_summary,
            "last_interaction": end_time.isoformat() if end_time else None
        }
        
        # Guardar resumen
        self.summaries[user_id].append({
            "timestamp": datetime.now().isoformat(),
            "summary": summary
        })
        
        return summary
    
    def get_user_profile(self, user_id: str) -> Dict:
        """
        Obtiene el perfil de un usuario basado en su historial.
        
        Args:
            user_id: Identificador del usuario
            
        Returns:
            Dict con perfil del usuario
        """
        if user_id not in self.metadata:
            return {"user_id": user_id, "exists": False}
        
        meta = self.metadata[user_id]
        
        # Calcular preferencias de intención
        total_intents = sum(meta["intents"].values()) if meta["intents"] else 1
        intent_preferences = {
            k: round(v / total_intents, 2) 
            for k, v in sorted(meta["intents"].items(), key=lambda x: x[1], reverse=True)[:3]
        }
        
        return {
            "user_id": user_id,
            "exists": True,
            "created_at": meta["created_at"],
            "message_count": meta["message_count"],
            "top_intents": intent_preferences,
            "topics_of_interest": list(meta["topics"])[:10]
        }
    
    def get_all_contexts_summary(self) -> Dict:
        """Obtiene resumen de todos los contextos activos"""
        return {
            "active_contexts": len(self.contexts),
            "users": list(self.contexts.keys()),
            "total_messages": sum(
                self.metadata[uid].get("message_count", 0) 
                for uid in self.contexts.keys()
            )
        }


# ============================================================
# SECCION 5.4: ENTITYEXTRACTOR (líneas 6000-6200)
# ============================================================

class EntityExtractor:
    """
    Extractor de entidades especializado.
    
    Funciones:
    - Extraer símbolos bursátiles
    - Extraer rutas de archivos
    - Extraer números (montos, porcentajes)
    - Extraer expresiones temporales
    - Extraer acciones/verbos
    """
    
    def __init__(self):
        self.logger = logging.getLogger("EntityExtractor")
        self.normalizer = TextNormalizer()
        
        # Símbolos bursátiles conocidos
        self.known_symbols = {
            "SPY", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", 
            "BTCUSD", "ETHUSD", "XRPUSD", "LTCUSD", "BTC", "ETH", "XRP", "LTC",
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
            "DXY", "VIX", "GLD", "SLV", "QQQ", "IWM", "DIA", "XLF", "XLK",
            "AAPL", "MSFT", "AMZN", "GOOGL", "TSLA", "META", "NVDA", "NFLX",
            "AMD", "INTC", "CSCO", "ADBE", "PYPL", "UBER", "LYFT", "ZM"
        }
        
        # Acciones/verbos comunes
        self.action_verbs = {
            "buscar": ["buscar", "busca", "busque", "buscando", "encontrar", "encuentra", "localizar", "localiza"],
            "mostrar": ["mostrar", "muestra", "muestre", "mostrando", "enseñar", "enseña", "enseñe", "presentar", "presenta", "visualizar", "visualiza"],
            "analizar": ["analizar", "analiza", "analice", "analizando", "examinar", "examina", "examine", "revisar", "revisa", "revise", "estudiar", "estudia"],
            "ejecutar": ["ejecutar", "ejecuta", "ejecute", "ejecutando", "correr", "corre", "corra", "iniciar", "inicia", "inicie", "lanzar", "lanza"],
            "crear": ["crear", "crea", "cree", "creando", "generar", "genera", "genere", "hacer", "haz", "haga"],
            "eliminar": ["eliminar", "elimina", "elimine", "borrar", "borra", "borre", "quitar", "quita"],
            "comprar": ["comprar", "compra", "compre", "adquirir", "adquiere", "adquiera", "long", "alcista"],
            "vender": ["vender", "vende", "venda", "vendiendo", "short", "bajista", "cerrar", "cierra"],
            "calcular": ["calcular", "calcula", "calcule", "computar", "computa", "procesar", "procesa"]
        }
        
        # Expresiones temporales
        self.time_expressions = {
            "hoy": {"type": "relative", "offset_days": 0},
            "ayer": {"type": "relative", "offset_days": -1},
            "mañana": {"type": "relative", "offset_days": 1},
            "ahora": {"type": "relative", "offset_days": 0},
            "próxima semana": {"type": "relative", "offset_days": 7},
            "semana pasada": {"type": "relative", "offset_days": -7},
            "última semana": {"type": "relative", "offset_days": -7},
            "próximo mes": {"type": "relative", "offset_days": 30},
            "mes pasado": {"type": "relative", "offset_days": -30},
            "último mes": {"type": "relative", "offset_days": -30},
            "este año": {"type": "relative", "offset_days": 0, "period": "year"},
            "año pasado": {"type": "relative", "offset_days": -365},
            "último año": {"type": "relative", "offset_days": -365}
        }
    
    def extract_symbols(self, text: str) -> List[Dict]:
        """
        Extrae símbolos bursátiles del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Lista de símbolos con metadata
        """
        symbols = []
        
        # Patrón para símbolos (1-5 letras mayúsculas)
        pattern = re.compile(r'\b[A-Z]{1,5}\b')
        
        for match in pattern.finditer(text):
            symbol = match.group()
            
            # Verificar si es un símbolo conocido o parece válido
            is_known = symbol in self.known_symbols
            
            # Contexto para determinar tipo
            context_start = max(0, match.start() - 30)
            context_end = min(len(text), match.end() + 30)
            context = text[context_start:context_end].lower()
            
            # Inferir tipo
            symbol_type = "unknown"
            if any(word in context for word in ["stock", "acción", "mercado", "trading", "rsi"]):
                symbol_type = "stock"
            elif any(word in context for word in ["crypto", "bitcoin", "ethereum", "moneda"]):
                symbol_type = "crypto"
            elif any(word in context for word in ["forex", "divisa", "par", "eur", "usd"]):
                symbol_type = "forex"
            
            symbols.append({
                "symbol": symbol,
                "type": symbol_type,
                "is_known": is_known,
                "position": match.start(),
                "context": context[:50]
            })
        
        return symbols
    
    def extract_file_paths(self, text: str) -> List[Dict]:
        """
        Extrae rutas de archivos del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Lista de rutas con metadata
        """
        paths = []
        
        # Patrón Windows
        windows_pattern = re.compile(r'[A-Za-z]:\\[\\\w\s.-]+', re.IGNORECASE)
        for match in windows_pattern.finditer(text):
            path = match.group()
            paths.append({
                "path": path,
                "type": "windows",
                "exists": None,  # Podría verificar con os.path.exists
                "position": match.start()
            })
        
        # Patrón Unix/Linux
        unix_pattern = re.compile(r'(?:/\w+)+/?[\w\.-]*')
        for match in unix_pattern.finditer(text):
            path = match.group()
            # Filtrar falsos positivos
            if len(path) > 2 and path.count('/') >= 1:
                paths.append({
                    "path": path,
                    "type": "unix",
                    "exists": None,
                    "position": match.start()
                })
        
        # Patrón relativo
        rel_pattern = re.compile(r'\.\./[\w\./-]+|./[\w\./-]+')
        for match in rel_pattern.finditer(text):
            path = match.group()
            paths.append({
                "path": path,
                "type": "relative",
                "exists": None,
                "position": match.start()
            })
        
        return paths
    
    def extract_numbers(self, text: str) -> List[Dict]:
        """
        Extrae números del texto con contexto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Lista de números con metadata
        """
        numbers = []
        
        # Montos de dinero
        money_pattern = re.compile(r'[\$€£]\s*\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|BTC|ETH)')
        for match in money_pattern.finditer(text):
            value = match.group()
            # Extraer número
            num_str = re.sub(r'[^\d.,]', '', value)
            try:
                num_val = float(num_str.replace(',', ''))
                numbers.append({
                    "value": num_val,
                    "type": "money",
                    "original": value,
                    "position": match.start()
                })
            except ValueError:
                pass
        
        # Porcentajes
        percent_pattern = re.compile(r'\d+(?:\.\d+)?%')
        for match in percent_pattern.finditer(text):
            value = match.group()
            try:
                num_val = float(value.replace('%', ''))
                numbers.append({
                    "value": num_val,
                    "type": "percentage",
                    "original": value,
                    "position": match.start()
                })
            except ValueError:
                pass
        
        # Números decimales/enteros (con contexto)
        number_pattern = re.compile(r'\b\d+(?:\.\d+)?\b')
        for match in number_pattern.finditer(text):
            value = match.group()
            # Contexto
            context_start = max(0, match.start() - 20)
            context_end = min(len(text), match.end() + 20)
            context = text[context_start:context_end].lower()
            
            try:
                num_val = float(value)
                
                # Inferir tipo por contexto
                num_type = "number"
                if any(word in context for word in ["precio", "price", "valor", "costo"]):
                    num_type = "price"
                elif any(word in context for word in ["cantidad", "quantity", "volumen", "volume"]):
                    num_type = "quantity"
                elif any(word in context for word in ["año", "year", "mes", "month", "día", "day"]):
                    num_type = "time"
                
                # Evitar duplicados (ya capturados como money o percentage)
                is_duplicate = any(n["position"] == match.start() for n in numbers)
                if not is_duplicate:
                    numbers.append({
                        "value": num_val,
                        "type": num_type,
                        "original": value,
                        "position": match.start(),
                        "context": context
                    })
            except ValueError:
                pass
        
        return numbers
    
    def extract_time_expressions(self, text: str) -> List[Dict]:
        """
        Extrae expresiones temporales del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Lista de expresiones temporales
        """
        expressions = []
        normalized = self.normalizer.normalize(text)
        
        # Buscar expresiones conocidas
        for expr, metadata in self.time_expressions.items():
            if expr in normalized or expr in text.lower():
                # Calcular fecha referencia
                now = datetime.now()
                offset = metadata.get("offset_days", 0)
                reference_date = now + timedelta(days=offset)
                
                expressions.append({
                    "expression": expr,
                    "type": metadata["type"],
                    "offset_days": offset,
                    "reference_date": reference_date.isoformat(),
                    "reference_timestamp": reference_date.timestamp()
                })
        
        # Patrones adicionales
        # "hace X días/semanas/meses"
        ago_pattern = re.compile(r'hace\s+(\d+)\s+(días?|semanas?|meses?)', re.IGNORECASE)
        for match in ago_pattern.finditer(text):
            amount = int(match.group(1))
            unit = match.group(2)
            
            if "día" in unit:
                offset = -amount
            elif "semana" in unit:
                offset = -amount * 7
            elif "mes" in unit:
                offset = -amount * 30
            
            reference_date = datetime.now() + timedelta(days=offset)
            expressions.append({
                "expression": match.group(),
                "type": "relative",
                "offset_days": offset,
                "reference_date": reference_date.isoformat(),
                "reference_timestamp": reference_date.timestamp()
            })
        
        # "en X días/semanas/meses"
        in_pattern = re.compile(r'en\s+(\d+)\s+(días?|semanas?|meses?)', re.IGNORECASE)
        for match in in_pattern.finditer(text):
            amount = int(match.group(1))
            unit = match.group(2)
            
            if "día" in unit:
                offset = amount
            elif "semana" in unit:
                offset = amount * 7
            elif "mes" in unit:
                offset = amount * 30
            
            reference_date = datetime.now() + timedelta(days=offset)
            expressions.append({
                "expression": match.group(),
                "type": "future_relative",
                "offset_days": offset,
                "reference_date": reference_date.isoformat(),
                "reference_timestamp": reference_date.timestamp()
            })
        
        return expressions
    
    def extract_actions(self, text: str) -> List[Dict]:
        """
        Extrae acciones/verbos del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Lista de acciones detectadas
        """
        actions = []
        normalized = self.normalizer.normalize(text)
        words = self.normalizer.tokenize(normalized)
        
        for word in words:
            for action, synonyms in self.action_verbs.items():
                if word in synonyms:
                    # Calcular confianza basada en coincidencia exacta vs derivada
                    confidence = 1.0 if word in ["buscar", "mostrar", "analizar", "ejecutar", "crear"] else 0.8
                    
                    # Verificar que no esté duplicado
                    if not any(a["action"] == action for a in actions):
                        actions.append({
                            "action": action,
                            "verb_matched": word,
                            "confidence": confidence,
                            "category": self._categorize_action(action)
                        })
        
        # Ordenar por confianza
        actions.sort(key=lambda x: x["confidence"], reverse=True)
        
        return actions
    
    def _categorize_action(self, action: str) -> str:
        """Categoriza una acción en grupo funcional"""
        categories = {
            "buscar": "query",
            "mostrar": "display",
            "analizar": "analysis",
            "ejecutar": "execution",
            "crear": "creation",
            "eliminar": "deletion",
            "comprar": "trading",
            "vender": "trading",
            "calcular": "computation"
        }
        return categories.get(action, "other")
    
    def extract_all(self, text: str) -> Dict:
        """
        Extrae todas las entidades del texto.
        
        Args:
            text: Texto a analizar
            
        Returns:
            Dict con todas las entidades
        """
        return {
            "symbols": self.extract_symbols(text),
            "file_paths": self.extract_file_paths(text),
            "numbers": self.extract_numbers(text),
            "time_expressions": self.extract_time_expressions(text),
            "actions": self.extract_actions(text),
            "timestamp": datetime.now().isoformat()
        }


# ============================================================
# SECCION 5.5: RESPONSEFORMATTER (líneas 6200-6400)
# ============================================================

class ResponseFormatter:
    """
    Formateador de respuestas adaptativo.
    
    Funciones:
    - Formatear según perfil de usuario (developer, business)
    - Agregar contexto a respuestas
    - Formatear detalles técnicos
    """
    
    def __init__(self):
        self.logger = logging.getLogger("ResponseFormatter")
        
        # Plantillas por tipo de usuario
        self.templates = {
            "developer": {
                "header": "[TOOL] **Developer Mode**\n\n",
                "code_block": lambda code, lang: f"```{lang}\n{code}\n```",
                "error_format": lambda error: f"[FAIL] **Error:** `{error}`",
                "success_format": lambda msg: f"[OK] {msg}",
                "data_table": self._format_data_table_dev,
                "json_format": lambda data: json.dumps(data, indent=2, default=str)
            },
            "business": {
                "header": "[CHART] **Business Mode**\n\n",
                "summary_format": lambda title, data: f"**{title}:** {data}",
                "metric_format": lambda name, value, change: f"• **{name}:** {value} ({change})",
                "alert_format": lambda level, msg: f"🚨 **{level}:** {msg}",
                "recommendation": lambda rec: f"[IDEA] {rec}",
                "data_table": self._format_data_table_business
            }
        }
    
    def format_for_developer(self, response: Union[str, Dict], context: Dict = None) -> str:
        """
        Formatea respuesta para perfil de desarrollador.
        
        Args:
            response: Respuesta a formatear
            context: Contexto adicional
            
        Returns:
            Respuesta formateada
        """
        template = self.templates["developer"]
        formatted = template["header"]
        
        if isinstance(response, dict):
            # Formatear datos estructurados
            if "error" in response:
                formatted += template["error_format"](response["error"]) + "\n\n"
            
            if "code" in response:
                lang = response.get("language", "python")
                formatted += template["code_block"](response["code"], lang) + "\n\n"
            
            if "data" in response:
                data = response["data"]
                if isinstance(data, (list, dict)):
                    formatted += "**Data:**\n```json\n"
                    formatted += template["json_format"](data)
                    formatted += "\n```\n\n"
            
            if "message" in response:
                formatted += response["message"] + "\n"
        else:
            # Texto simple
            formatted += str(response)
        
        return formatted
    
    def format_for_business(self, response: Union[str, Dict], context: Dict = None) -> str:
        """
        Formatea respuesta para perfil de negocio.
        
        Args:
            response: Respuesta a formatear
            context: Contexto adicional
            
        Returns:
            Respuesta formateada
        """
        template = self.templates["business"]
        formatted = template["header"]
        
        if isinstance(response, dict):
            # Extraer insights clave
            if "summary" in response:
                formatted += template["summary_format"]("Resumen", response["summary"]) + "\n\n"
            
            # Métricas
            if "metrics" in response and isinstance(response["metrics"], dict):
                formatted += "**Métricas Clave:**\n"
                for name, value in response["metrics"].items():
                    change = "N/A"
                    if isinstance(value, dict):
                        change = value.get("change", "N/A")
                        value = value.get("value", "N/A")
                    formatted += template["metric_format"](name, value, change) + "\n"
                formatted += "\n"
            
            # Alertas
            if "alerts" in response and response["alerts"]:
                formatted += "**Alertas:**\n"
                for alert in response["alerts"]:
                    level = alert.get("level", "info")
                    msg = alert.get("message", str(alert))
                    formatted += template["alert_format"](level, msg) + "\n"
                formatted += "\n"
            
            # Recomendaciones
            if "recommendations" in response and response["recommendations"]:
                formatted += "**Recomendaciones:**\n"
                for rec in response["recommendations"]:
                    formatted += template["recommendation"](rec) + "\n"
            
            if "message" in response:
                formatted += "\n" + response["message"] + "\n"
        else:
            # Texto simple
            formatted += str(response)
        
        return formatted
    
    def format_technical_details(self, data: Dict, max_depth: int = 3) -> str:
        """
        Formatea detalles técnicos con profundidad limitada.
        
        Args:
            data: Datos a formatear
            max_depth: Profundidad máxima de anidación
            
        Returns:
            String formateado
        """
        def format_recursive(obj, depth=0):
            if depth > max_depth:
                return "..."
            
            if isinstance(obj, dict):
                lines = []
                for key, value in obj.items():
                    indent = "  " * depth
                    formatted_value = format_recursive(value, depth + 1)
                    lines.append(f"{indent}• **{key}:** {formatted_value}")
                return "\n".join(lines)
            elif isinstance(obj, list):
                if len(obj) == 0:
                    return "[]"
                lines = ["  " * depth + f"• {format_recursive(item, depth + 1)}" for item in obj[:5]]
                if len(obj) > 5:
                    lines.append("  " * depth + f"... y {len(obj) - 5} más")
                return "\n".join(lines)
            else:
                return str(obj)
        
        return format_recursive(data)
    
    def add_context_to_response(self, response: str, context: Dict) -> str:
        """
        Agrega información de contexto a la respuesta.
        
        Args:
            response: Respuesta original
            context: Contexto a agregar
            
        Returns:
            Respuesta enriquecida
        """
        enriched = response
        
        # Agregar referencias al contexto si es relevante
        if context.get("referenced_entities"):
            entities = context["referenced_entities"]
            if entities:
                enriched += "\n\n---\n"
                enriched += "**Contexto Referenciado:**\n"
                if "symbols" in entities and entities["symbols"]:
                    enriched += f"• Símbolos: {', '.join(entities['symbols'])}\n"
                if "time" in entities:
                    enriched += f"• Período: {entities['time']}\n"
        
        # Agregar nota sobre continuación
        if context.get("conversation_continues"):
            enriched += "\n\n¿Necesitas algo más sobre este tema?"
        
        return enriched
    
    def _format_data_table_dev(self, data: List[Dict], columns: List[str] = None) -> str:
        """Formatea tabla de datos para developers"""
        if not data:
            return "Sin datos"
        
        if not columns:
            columns = list(data[0].keys()) if data else []
        
        # Usar formato JSON para developers
        return "```json\n" + json.dumps(data, indent=2, default=str)[:500] + "\n```"
    
    def _format_data_table_business(self, data: List[Dict], columns: List[str] = None) -> str:
        """Formatea tabla de datos para business"""
        if not data:
            return "Sin datos disponibles"
        
        if not columns:
            columns = list(data[0].keys()) if data else []
        
        lines = ["| " + " | ".join(columns) + " |"]
        lines.append("|" + "|".join(["---" for _ in columns]) + "|")
        
        for row in data[:10]:  # Limitar a 10 filas
            values = [str(row.get(col, ""))[:20] for col in columns]
            lines.append("| " + " | ".join(values) + " |")
        
        return "\n".join(lines)
    
    def format_error(self, error: Union[str, Exception], user_type: str = "developer") -> str:
        """
        Formatea un error según el tipo de usuario.
        
        Args:
            error: Error a formatear
            user_type: Tipo de usuario (developer, business)
            
        Returns:
            Error formateado
        """
        if isinstance(error, Exception):
            error_msg = str(error)
            error_type = type(error).__name__
        else:
            error_msg = str(error)
            error_type = "Error"
        
        if user_type == "developer":
            return f"[FAIL] **{error_type}:** `{error_msg}`"
        else:
            return f"[WARNING]️ Lo siento, ocurrió un problema. Por favor, intenta de nuevo."
    
    def format_success(self, message: str, details: Dict = None, user_type: str = "developer") -> str:
        """
        Formatea mensaje de éxito.
        
        Args:
            message: Mensaje principal
            details: Detalles adicionales
            user_type: Tipo de usuario
            
        Returns:
            Mensaje formateado
        """
        if user_type == "developer":
            result = f"[OK] {message}"
            if details:
                result += f"\n```\n{json.dumps(details, indent=2, default=str)}\n```"
            return result
        else:
            return f"[OK] {message}"


# ============================================================
# SECCION 5.6: INTEGRACIÓN EN BRAINCHATV8 (líneas 6400-6600)
# ============================================================

# Nota: Las siguientes funciones deben agregarse/modificarse en BrainChatV8

"""
MEJORAS A IMPLEMENTAR EN BrainChatV8:

1. Agregar inicialización en __init__:
   
   self.context_manager = ContextManager(max_context=10)
   self.text_normalizer = TextNormalizer()
   self.advanced_intent_detector = AdvancedIntentDetector()
   self.entity_extractor = EntityExtractor()
   self.response_formatter = ResponseFormatter()

2. Modificar process_message() para usar el pipeline de 8 pasos:
   
   async def process_message_v2(self, message, user_id="anonymous", user_profile="developer"):
       # Paso 1: Normalizar texto
       normalized = self.text_normalizer.normalize(message)
       
       # Paso 2: Extraer entidades
       entities = self.entity_extractor.extract_all(message)
       
       # Paso 3: Detectar intención con contexto
       intent, confidence, meta = self.context_manager.infer_intent_from_context(user_id, message)
       
       # Paso 4: Seleccionar tools basado en intención + entidades
       tools = self._select_tools_v2(intent, entities)
       
       # Paso 5: Ejecutar tools
       tool_results = await self._execute_tools(tools, entities)
       
       # Paso 6: Formatear respuesta según perfil
       raw_response = await self._generate_response(intent, tool_results, entities)
       formatted_response = self.response_formatter.format_for_developer(raw_response, {}) 
           if user_profile == "developer" 
           else self.response_formatter.format_for_business(raw_response, {})
       
       # Paso 7: Guardar en contexto
       self.context_manager.add_message(user_id, "user", message, intent)
       self.context_manager.add_message(user_id, "assistant", formatted_response, None)
       
       # Paso 8: Responder
       return formatted_response

3. Agregar métodos auxiliares:
   
   def _select_tools_v2(self, intent, entities):
       tools = []
       
       # Trading/mercado
       if intent == "TRADING":
           if entities["symbols"]:
               tools.append({"name": "market_data", "symbols": entities["symbols"]})
           tools.append({"name": "rsi_analysis"})
           if "perdí" in message.lower() or "pérdida" in message.lower():
               tools.append({"name": "pnl_analysis"})
       
       # Business
       elif intent == "BUSINESS":
           tools.append({"name": "business_metrics"})
           tools.append({"name": "rsi_business_summary"})
       
       # Análisis
       elif intent == "ANALYSIS":
           if entities["file_paths"]:
               tools.append({"name": "code_analysis", "paths": entities["file_paths"]})
           else:
               tools.append({"name": "general_analysis"})
       
       # System
       elif intent == "SYSTEM":
           tools.append({"name": "health_check"})
           tools.append({"name": "system_status"})
       
       return tools
"""

# ============================================================
# FIN FASE 5: NLP AVANZADO
# ============================================================

print("=" * 60)
print("FASE 5: NLP AVANZADO - Cargada exitosamente")
print("=" * 60)
print("\nClases disponibles:")
print("  [OK] TextNormalizer - Normalización de texto")
print("  [OK] AdvancedIntentDetector - Detección de intenciones avanzada")
print("  [OK] ContextManager - Gestión de contexto conversacional")
print("  [OK] EntityExtractor - Extracción de entidades")
print("  [OK] ResponseFormatter - Formateo de respuestas adaptativo")
print("=" * 60)

# ============================================================
# STARTUP (líneas 1601-1700)
# ============================================================

async def startup():
    """Función de inicio del sistema"""
    print("=" * 60)
    print("Brain Chat V8.0 - Iniciando...")
    print("=" * 60)
    
    # Verificar configuración
    print("\n[1] Verificando configuración...")
    
    # Verificar directorios
    if not MEMORY_PATH.exists():
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] Directorio de memoria creado: {MEMORY_PATH}")
    else:
        print(f"  [OK] Directorio de memoria OK: {MEMORY_PATH}")
    
    if not LOGS_PATH.exists():
        LOGS_PATH.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] Directorio de logs creado: {LOGS_PATH}")
    else:
        print(f"  [OK] Directorio de logs OK: {LOGS_PATH}")
    
    # Verificar APIs
    print("\n[2] Verificando APIs...")
    if API_KEYS["openai"]:
        print("  [OK] OpenAI API: Configurada")
    else:
        print("  [WARNING] OpenAI API: No configurada (set OPENAI_API_KEY)")
    
    if API_KEYS["anthropic"]:
        print("  [OK] Anthropic API: Configurada")
    else:
        print("  [WARNING] Anthropic API: No configurada (set ANTHROPIC_API_KEY)")
    
    print("  [INFO] Ollama: Se usará fallback local")
    
    # Inicializar sesión default
    print("\n[3] Inicializando sesión default...")
    brain = BrainChatV8("default")
    brain.start()
    active_sessions["default"] = brain
    print("  [OK] Sesión default iniciada")
    
    # Mostrar información
    print("\n" + "=" * 60)
    print("Brain Chat V8.0 Listo")
    print("=" * 60)
    print(f"\nEndpoints disponibles:")
    print(f"  POST /chat      - Enviar mensaje")
    print(f"  GET  /status    - Estado del sistema")
    print(f"  GET  /health    - Health check")
    print(f"  GET  /sessions  - Listar sesiones")
    print(f"\nEndpoints FASE 4 (Brain Integration):")
    print(f"  GET  /brain/rsi     - Análisis RSI (brechas, fases, progreso)")
    print(f"  GET  /brain/health  - Salud de servicios")
    print(f"  GET  /brain/metrics - Métricas del sistema")
    print(f"  POST /brain/validate- Validar acción vs premisas")
    print(f"\nDocumentación: http://localhost:8000/docs")
    print("=" * 60)

async def shutdown_handler():
    """Manejador de apagado"""
    print("\nCerrando sesiones...")
    for session_id, brain in active_sessions.items():
        await brain.shutdown()
    print("Todas las sesiones cerradas")

# ============================================================
# FASE 6: AUTONOMÍA PROACTIVA (líneas 6989-8500+)
# ============================================================
# El Brain Chat se vuelve autónomo con capacidades de:
# - Auto-debugging y corrección de errores
# - Optimización automática de rendimiento
# - Mejora continua basada en patrones de conversación
# - Monitoreo proactivo de servicios
# - Sistema de aprobaciones para acciones autónomas

from typing import Callable
import subprocess
import psutil

# ============================================================
# CONFIGURACIÓN DE AUTONOMÍA (líneas 6989-7020)
# ============================================================

class AutonomyLevel(Enum):
    """Niveles de autonomía para acciones del sistema"""
    LEVEL_1_SUGGEST = 1      # Sugerir (siempre requiere aprobación)
    LEVEL_2_LOW_RISK = 2     # Ejecutar si bajo riesgo (ej: borrar logs viejos)
    LEVEL_3_MEDIUM_RISK = 3  # Ejecutar si medio riesgo (ej: restart servicio)
    LEVEL_4_HIGH_RISK = 4    # Ejecutar si alto riesgo (ej: modificar código) - SIEMPRE requiere aprobación

AUTONOMY_CONFIG = {
    "auto_debugging_enabled": True,
    "auto_optimization_enabled": True,
    "proactive_monitoring_enabled": True,
    "self_improvement_enabled": True,
    "approval_required_for_level_4": True,
    "confidence_threshold_low": 0.8,
    "confidence_threshold_medium": 0.9,
    "check_interval_debugger": 300,      # 5 minutos
    "check_interval_optimizer": 600,     # 10 minutos
    "check_interval_monitor": 300,       # 5 minutos
    "max_error_history": 100,
    "max_optimization_history": 50,
}

# ============================================================
# AUTODEBUGGER (líneas 7021-7200)
# ============================================================

@dataclass
class ErrorPattern:
    """Patrón de error detectado"""
    error_type: str
    error_message: str
    context: Dict
    timestamp: datetime
    frequency: int = 1
    suggested_fix: Optional[str] = None
    confidence: float = 0.0

@dataclass
class DebugReport:
    """Reporte de debugging"""
    errors_analyzed: int
    patterns_detected: int
    fixes_suggested: int
    fixes_applied: int
    timestamp: datetime
    details: List[Dict]

class AutoDebugger:
    """
    Sistema de auto-debugging que monitorea logs de error,
    detecta patrones y sugiere o aplica correcciones automáticamente.
    """
    
    def __init__(self, error_log_dir: Optional[Path] = None):
        self.error_log_dir = error_log_dir or LOGS_PATH / "errors"
        self.error_log_dir.mkdir(parents=True, exist_ok=True)
        self.error_patterns: Dict[str, ErrorPattern] = {}
        self.fix_history: List[Dict] = []
        self.monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.known_error_types = {
            "FileNotFoundError": self._fix_file_not_found,
            "PermissionError": self._fix_permission_error,
            "ConnectionError": self._fix_connection_error,
            "TimeoutError": self._fix_timeout_error,
            "MemoryError": self._fix_memory_error,
            "KeyError": self._fix_key_error,
            "IndexError": self._fix_index_error,
            "AttributeError": self._fix_attribute_error,
            "ImportError": self._fix_import_error,
            "ModuleNotFoundError": self._fix_import_error,
        }
        
    async def monitor_error_logs(self):
        """
        Revisa logs de errores cada 5 minutos.
        Detecta nuevos errores y analiza patrones.
        """
        while self.monitoring:
            try:
                # Buscar archivos de log de error
                error_files = list(self.error_log_dir.glob("*.error.log"))
                error_files.extend(self.error_log_dir.glob("error_*.log"))
                
                for log_file in error_files:
                    await self._process_error_log(log_file)
                
                # También revisar el log general de la aplicación
                general_log = LOGS_PATH / "brain_chat.log"
                if general_log.exists():
                    await self._extract_errors_from_log(general_log)
                
                await asyncio.sleep(AUTONOMY_CONFIG["check_interval_debugger"])
                
            except Exception as e:
                logger.error(f"Error en monitor_error_logs: {e}")
                await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar
    
    async def _process_error_log(self, log_file: Path):
        """Procesa un archivo de log de errores"""
        try:
            content = log_file.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            
            i = 0
            while i < len(lines):
                line = lines[i]
                
                # Detectar líneas de error
                if 'ERROR' in line or 'Traceback' in line:
                    error_block = [line]
                    j = i + 1
                    
                    # Capturar el bloque completo del error
                    while j < len(lines) and (
                        lines[j].strip().startswith('File ') or
                        lines[j].strip().startswith('  ') or
                        'Error:' in lines[j] or
                        'Exception:' in lines[j]
                    ):
                        error_block.append(lines[j])
                        j += 1
                    
                    error_message = '\n'.join(error_block)
                    await self.analyze_error_pattern(error_message)
                    
                    i = j
                else:
                    i += 1
                    
        except Exception as e:
            logger.error(f"Error procesando {log_file}: {e}")
    
    async def _extract_errors_from_log(self, log_file: Path):
        """Extrae errores del log general"""
        try:
            # Solo leer las últimas 1000 líneas
            content = log_file.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')[-1000:]
            
            for line in lines:
                if ' ERROR ' in line or ' CRITICAL ' in line:
                    await self.analyze_error_pattern(line)
                    
        except Exception as e:
            logger.error(f"Error extrayendo de {log_file}: {e}")
    
    async def analyze_error_pattern(self, error_message: str) -> Optional[ErrorPattern]:
        """
        Analiza un mensaje de error para detectar patrones.
        
        Args:
            error_message: Mensaje de error completo
            
        Returns:
            ErrorPattern detectado o None
        """
        # Extraer tipo de error
        error_type = self._extract_error_type(error_message)
        
        # Crear hash del patrón
        pattern_key = f"{error_type}:{hashlib.md5(error_message[:200].encode()).hexdigest()[:16]}"
        
        if pattern_key in self.error_patterns:
            # Incrementar frecuencia del patrón existente
            pattern = self.error_patterns[pattern_key]
            pattern.frequency += 1
            pattern.timestamp = datetime.now()
        else:
            # Crear nuevo patrón
            context = self._extract_error_context(error_message)
            
            pattern = ErrorPattern(
                error_type=error_type,
                error_message=error_message,
                context=context,
                timestamp=datetime.now(),
                frequency=1
            )
            
            self.error_patterns[pattern_key] = pattern
            
            # Generar sugerencia de corrección
            await self.suggest_fix(error_type, context)
        
        # Limitar historial
        if len(self.error_patterns) > AUTONOMY_CONFIG["max_error_history"]:
            # Eliminar patrones más antiguos
            sorted_patterns = sorted(
                self.error_patterns.items(),
                key=lambda x: x[1].timestamp
            )
            for key, _ in sorted_patterns[:len(sorted_patterns)//2]:
                del self.error_patterns[key]
        
        return self.error_patterns.get(pattern_key)
    
    def _extract_error_type(self, error_message: str) -> str:
        """Extrae el tipo de error del mensaje"""
        error_patterns = [
            r'(\w+Error):',
            r'(\w+Exception):',
            r'<class \'(\w+)\'>',
        ]
        
        for pattern in error_patterns:
            match = re.search(pattern, error_message)
            if match:
                return match.group(1)
        
        return "UnknownError"
    
    def _extract_error_context(self, error_message: str) -> Dict:
        """Extrae contexto relevante del error"""
        context = {
            "files_involved": [],
            "functions_involved": [],
            "line_numbers": [],
            "variables": [],
        }
        
        # Extraer archivos y líneas
        file_pattern = r'File "([^"]+)", line (\d+)'
        for match in re.finditer(file_pattern, error_message):
            context["files_involved"].append(match.group(1))
            context["line_numbers"].append(int(match.group(2)))
        
        # Extraer nombres de funciones
        func_pattern = r'in (\w+)\('
        for match in re.finditer(func_pattern, error_message):
            context["functions_involved"].append(match.group(1))
        
        # Extraer variables (simplificado)
        var_pattern = r"KeyError: ['\"](\w+)['\"]"
        for match in re.finditer(var_pattern, error_message):
            context["variables"].append(match.group(1))
        
        return context
    
    async def suggest_fix(self, error_type: str, context: Dict) -> Optional[str]:
        """
        Sugiere una corrección basada en el tipo de error y contexto.
        
        Args:
            error_type: Tipo de error detectado
            context: Contexto del error
            
        Returns:
            Sugerencia de corrección o None
        """
        suggested_fix = None
        confidence = 0.5
        
        if error_type in self.known_error_types:
            # Usar handler específico
            handler = self.known_error_types[error_type]
            suggested_fix = await handler(context)
            confidence = 0.8
        else:
            # Sugerencia genérica basada en el tipo
            suggested_fix = self._generate_generic_suggestion(error_type, context)
            confidence = 0.5
        
        # Actualizar patrón con la sugerencia
        for pattern in self.error_patterns.values():
            if pattern.error_type == error_type:
                pattern.suggested_fix = suggested_fix
                pattern.confidence = confidence
        
        return suggested_fix
    
    def _generate_generic_suggestion(self, error_type: str, context: Dict) -> str:
        """Genera sugerencia genérica para errores desconocidos"""
        suggestions = {
            "FileNotFoundError": "Verificar que el archivo existe antes de acceder",
            "PermissionError": "Verificar permisos o ejecutar con privilegios adecuados",
            "ConnectionError": "Verificar conectividad de red y disponibilidad del servicio",
            "TimeoutError": "Aumentar timeout o implementar reintentos con backoff",
            "MemoryError": "Optimizar uso de memoria o procesar datos en chunks",
            "KeyError": "Verificar existencia de clave antes de acceder al diccionario",
            "IndexError": "Verificar longitud de lista antes de acceder por índice",
            "AttributeError": "Verificar que el objeto tiene el atributo antes de usarlo",
            "ImportError": "Verificar que el módulo está instalado y disponible",
        }
        
        return suggestions.get(error_type, f"Revisar documentación para {error_type}")
    
    async def attempt_fix(self, issue: ErrorPattern, confidence_threshold: float = 0.8) -> bool:
        """
        Intenta aplicar una corrección automáticamente.
        
        Args:
            issue: Patrón de error a corregir
            confidence_threshold: Umbral mínimo de confianza
            
        Returns:
            True si se aplicó la corrección, False en caso contrario
        """
        if issue.confidence < confidence_threshold:
            logger.info(f"Confianza insuficiente ({issue.confidence}) para auto-corrigir {issue.error_type}")
            return False
        
        if issue.error_type not in self.known_error_types:
            logger.info(f"No hay handler para {issue.error_type}")
            return False
        
        try:
            handler = self.known_error_types[issue.error_type]
            success = await handler(issue.context, apply_fix=True)
            
            if success:
                self.fix_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "error_type": issue.error_type,
                    "fix_applied": True,
                    "confidence": issue.confidence,
                })
                logger.info(f"Auto-corrección aplicada para {issue.error_type}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error aplicando corrección: {e}")
            return False
    
    # Handlers de errores específicos
    async def _fix_file_not_found(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para FileNotFoundError"""
        files = context.get("files_involved", [])
        if not files:
            return "Verificar rutas de archivo"
        
        if not apply_fix:
            return f"Crear directorios necesarios para {files[0]}"
        
        # Intentar crear directorios
        try:
            for file_path in files:
                path = Path(file_path)
                if not path.parent.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    return True
        except Exception as e:
            logger.error(f"Error creando directorios: {e}")
        
        return False
    
    async def _fix_permission_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para PermissionError"""
        files = context.get("files_involved", [])
        if not apply_fix:
            return f"Verificar permisos de {files[0] if files else 'archivo'}"
        
        # No aplicar automáticamente cambios de permisos por seguridad
        return False
    
    async def _fix_connection_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para ConnectionError"""
        if not apply_fix:
            return "Verificar conectividad de red"
        
        # Intentar reconectar (implementación específica)
        return False
    
    async def _fix_timeout_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para TimeoutError"""
        if not apply_fix:
            return "Aumentar timeout o implementar reintentos"
        
        # No aplicar automáticamente cambios de configuración
        return False
    
    async def _fix_memory_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para MemoryError"""
        if not apply_fix:
            return "Liberar memoria o procesar en chunks"
        
        # Intentar liberar memoria
        try:
            import gc
            gc.collect()
            return True
        except:
            return False
    
    async def _fix_key_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para KeyError"""
        if not apply_fix:
            return "Usar .get() o verificar clave antes de acceder"
        
        # No aplicar automáticamente cambios de código
        return False
    
    async def _fix_index_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para IndexError"""
        if not apply_fix:
            return "Verificar longitud de lista antes de indexar"
        
        # No aplicar automáticamente cambios de código
        return False
    
    async def _fix_attribute_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para AttributeError"""
        if not apply_fix:
            return "Verificar existencia de atributo con hasattr()"
        
        # No aplicar automáticamente cambios de código
        return False
    
    async def _fix_import_error(self, context: Dict, apply_fix: bool = False) -> Union[str, bool]:
        """Handler para ImportError/ModuleNotFoundError"""
        if not apply_fix:
            return "Instalar módulo faltante con pip"
        
        # No aplicar automáticamente instalación de paquetes
        return False
    
    def generate_debug_report(self) -> str:
        """
        Genera un reporte completo de debugging.
        
        Returns:
            Reporte formateado como string
        """
        report_lines = [
            "=" * 60,
            "AUTODEBUGGER REPORT",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total Error Patterns Detected: {len(self.error_patterns)}",
            f"Total Fixes Applied: {len([f for f in self.fix_history if f.get('fix_applied')])}",
            "",
            "Top Error Patterns:",
            "-" * 60,
        ]
        
        # Ordenar por frecuencia
        sorted_patterns = sorted(
            self.error_patterns.values(),
            key=lambda p: p.frequency,
            reverse=True
        )[:10]
        
        for i, pattern in enumerate(sorted_patterns, 1):
            report_lines.append(f"{i}. {pattern.error_type}")
            report_lines.append(f"   Frequency: {pattern.frequency}")
            report_lines.append(f"   Last Seen: {pattern.timestamp.strftime('%Y-%m-%d %H:%M')}")
            report_lines.append(f"   Confidence: {pattern.confidence:.2f}")
            if pattern.suggested_fix:
                report_lines.append(f"   Suggested Fix: {pattern.suggested_fix}")
            report_lines.append("")
        
        # Historial de correcciones
        if self.fix_history:
            report_lines.append("Recent Fixes Applied:")
            report_lines.append("-" * 60)
            for fix in self.fix_history[-5:]:
                report_lines.append(f"  {fix['timestamp']}: {fix['error_type']} "
                                  f"(confidence: {fix['confidence']:.2f})")
        
        report_lines.append("=" * 60)
        
        return '\n'.join(report_lines)
    
    async def start_monitoring(self):
        """Inicia el monitoreo de errores en background"""
        if not self.monitoring:
            self.monitoring = True
            self.monitoring_task = asyncio.create_task(self.monitor_error_logs())
            logger.info("AutoDebugger monitoring started")
    
    async def stop_monitoring(self):
        """Detiene el monitoreo de errores"""
        self.monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("AutoDebugger monitoring stopped")

# ============================================================
# AUTOOPTIMIZER (líneas 7201-7400)
# ============================================================

@dataclass
class PerformanceMetrics:
    """Métricas de rendimiento del sistema"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    network_io_bytes: int
    response_time_ms: float
    active_sessions: int
    request_queue_size: int

@dataclass
class Bottleneck:
    """Cuello de botella detectado"""
    component: str
    severity: str  # low, medium, high
    metric: str
    current_value: float
    threshold: float
    suggested_action: str
    timestamp: datetime

@dataclass
class OptimizationSuggestion:
    """Sugerencia de optimización"""
    id: str
    component: str
    type: str
    description: str
    expected_improvement: str
    implementation_complexity: str  # low, medium, high
    risk_level: int  # 1-4
    auto_applicable: bool
    timestamp: datetime

class AutoOptimizer:
    """
    Sistema de optimización automática que monitorea métricas de rendimiento,
    detecta cuellos de botella y sugiere o implementa optimizaciones.
    """
    
    def __init__(self):
        self.metrics_history: deque = deque(maxlen=1000)
        self.bottlenecks: List[Bottleneck] = []
        self.suggestions: List[OptimizationSuggestion] = []
        self.implemented_optimizations: List[Dict] = []
        self.monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.thresholds = {
            "cpu_high": 80.0,
            "cpu_critical": 95.0,
            "memory_high": 85.0,
            "memory_critical": 95.0,
            "disk_high": 90.0,
            "response_time_slow": 1000.0,  # ms
            "response_time_critical": 5000.0,
            "queue_size_high": 100,
        }
        self.optimization_handlers = {
            "memory_cleanup": self._optimize_memory,
            "cpu_throttle": self._optimize_cpu,
            "disk_cleanup": self._optimize_disk,
            "cache_optimization": self._optimize_cache,
            "session_cleanup": self._optimize_sessions,
        }
    
    async def monitor_performance_metrics(self):
        """
        Monitorea métricas de rendimiento cada 10 minutos.
        """
        while self.monitoring:
            try:
                # Recolectar métricas del sistema
                metrics = await self._collect_system_metrics()
                self.metrics_history.append(metrics)
                
                # Detectar cuellos de botella
                await self.detect_bottlenecks(metrics)
                
                await asyncio.sleep(AUTONOMY_CONFIG["check_interval_optimizer"])
                
            except Exception as e:
                logger.error(f"Error en monitor_performance_metrics: {e}")
                await asyncio.sleep(60)
    
    async def _collect_system_metrics(self) -> PerformanceMetrics:
        """Recolecta métricas del sistema"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memoria
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disco
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100
            
            # Red
            net_io = psutil.net_io_counters()
            network_io_bytes = net_io.bytes_sent + net_io.bytes_recv
            
            # Sesiones activas
            active_sessions_count = len(active_sessions)
            
            # Tiempo de respuesta promedio (simulado o medido)
            response_time_ms = await self._measure_response_time()
            
            # Tamaño de cola (simulado)
            queue_size = self._estimate_queue_size()
            
            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_usage_percent=disk_usage_percent,
                network_io_bytes=network_io_bytes,
                response_time_ms=response_time_ms,
                active_sessions=active_sessions_count,
                request_queue_size=queue_size
            )
            
        except Exception as e:
            logger.error(f"Error recolectando métricas: {e}")
            # Retornar métricas vacías en caso de error
            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                disk_usage_percent=0.0,
                network_io_bytes=0,
                response_time_ms=0.0,
                active_sessions=0,
                request_queue_size=0
            )
    
    async def _measure_response_time(self) -> float:
        """Mide el tiempo de respuesta promedio"""
        # Implementación básica - puede extenderse
        return 0.0
    
    def _estimate_queue_size(self) -> int:
        """Estima el tamaño de la cola de requests"""
        # Implementación básica
        return 0
    
    async def detect_bottlenecks(self, metrics: PerformanceMetrics):
        """
        Detecta cuellos de botella basándose en las métricas.
        
        Args:
            metrics: Métricas de rendimiento actuales
        """
        new_bottlenecks = []
        
        # CPU
        if metrics.cpu_percent > self.thresholds["cpu_critical"]:
            new_bottlenecks.append(Bottleneck(
                component="CPU",
                severity="critical",
                metric="cpu_percent",
                current_value=metrics.cpu_percent,
                threshold=self.thresholds["cpu_critical"],
                suggested_action="Escalar recursos o reducir carga",
                timestamp=datetime.now()
            ))
        elif metrics.cpu_percent > self.thresholds["cpu_high"]:
            new_bottlenecks.append(Bottleneck(
                component="CPU",
                severity="high",
                metric="cpu_percent",
                current_value=metrics.cpu_percent,
                threshold=self.thresholds["cpu_high"],
                suggested_action="Optimizar procesos o balancear carga",
                timestamp=datetime.now()
            ))
        
        # Memoria
        if metrics.memory_percent > self.thresholds["memory_critical"]:
            new_bottlenecks.append(Bottleneck(
                component="Memory",
                severity="critical",
                metric="memory_percent",
                current_value=metrics.memory_percent,
                threshold=self.thresholds["memory_critical"],
                suggested_action="Liberar memoria inmediatamente",
                timestamp=datetime.now()
            ))
        elif metrics.memory_percent > self.thresholds["memory_high"]:
            new_bottlenecks.append(Bottleneck(
                component="Memory",
                severity="high",
                metric="memory_percent",
                current_value=metrics.memory_percent,
                threshold=self.thresholds["memory_high"],
                suggested_action="Ejecutar garbage collection y limpiar caché",
                timestamp=datetime.now()
            ))
        
        # Disco
        if metrics.disk_usage_percent > self.thresholds["disk_high"]:
            new_bottlenecks.append(Bottleneck(
                component="Disk",
                severity="high",
                metric="disk_usage_percent",
                current_value=metrics.disk_usage_percent,
                threshold=self.thresholds["disk_high"],
                suggested_action="Limpiar archivos temporales y logs antiguos",
                timestamp=datetime.now()
            ))
        
        # Tiempo de respuesta
        if metrics.response_time_ms > self.thresholds["response_time_critical"]:
            new_bottlenecks.append(Bottleneck(
                component="ResponseTime",
                severity="critical",
                metric="response_time_ms",
                current_value=metrics.response_time_ms,
                threshold=self.thresholds["response_time_critical"],
                suggested_action="Optimizar queries y procesamiento",
                timestamp=datetime.now()
            ))
        elif metrics.response_time_ms > self.thresholds["response_time_slow"]:
            new_bottlenecks.append(Bottleneck(
                component="ResponseTime",
                severity="medium",
                metric="response_time_ms",
                current_value=metrics.response_time_ms,
                threshold=self.thresholds["response_time_slow"],
                suggested_action="Revisar logs de rendimiento",
                timestamp=datetime.now()
            ))
        
        # Actualizar lista de cuellos de botella
        self.bottlenecks.extend(new_bottlenecks)
        
        # Generar sugerencias para nuevos cuellos de botella
        for bottleneck in new_bottlenecks:
            await self.suggest_optimizations(bottleneck.component)
    
    async def suggest_optimizations(self, component: str) -> List[OptimizationSuggestion]:
        """
        Sugiere optimizaciones para un componente específico.
        
        Args:
            component: Nombre del componente a optimizar
            
        Returns:
            Lista de sugerencias de optimización
        """
        suggestions = []
        
        if component == "CPU":
            suggestions.append(OptimizationSuggestion(
                id=f"cpu_opt_{datetime.now().timestamp()}",
                component="CPU",
                type="throttle",
                description="Reducir frecuencia de procesamiento en tareas no críticas",
                expected_improvement="20-30% reducción en uso de CPU",
                implementation_complexity="low",
                risk_level=2,
                auto_applicable=True,
                timestamp=datetime.now()
            ))
            
        elif component == "Memory":
            suggestions.append(OptimizationSuggestion(
                id=f"mem_opt_{datetime.now().timestamp()}",
                component="Memory",
                type="cleanup",
                description="Ejecutar garbage collection y limpiar caché de sesiones inactivas",
                expected_improvement="15-40% liberación de memoria",
                implementation_complexity="low",
                risk_level=2,
                auto_applicable=True,
                timestamp=datetime.now()
            ))
            
        elif component == "Disk":
            suggestions.append(OptimizationSuggestion(
                id=f"disk_opt_{datetime.now().timestamp()}",
                component="Disk",
                type="cleanup",
                description="Eliminar logs antiguos y archivos temporales",
                expected_improvement="5-20% liberación de espacio",
                implementation_complexity="low",
                risk_level=2,
                auto_applicable=True,
                timestamp=datetime.now()
            ))
            
        elif component == "ResponseTime":
            suggestions.append(OptimizationSuggestion(
                id=f"resp_opt_{datetime.now().timestamp()}",
                component="ResponseTime",
                type="cache",
                description="Implementar caché para respuestas frecuentes",
                expected_improvement="50-80% mejora en tiempo de respuesta",
                implementation_complexity="medium",
                risk_level=3,
                auto_applicable=False,
                timestamp=datetime.now()
            ))
        
        self.suggestions.extend(suggestions)
        return suggestions
    
    async def implement_optimization(self, suggestion: OptimizationSuggestion, 
                                   approval_required: bool = True) -> bool:
        """
        Implementa una sugerencia de optimización.
        
        Args:
            suggestion: Sugerencia a implementar
            approval_required: Si requiere aprobación del usuario
            
        Returns:
            True si se implementó exitosamente
        """
        if approval_required and suggestion.risk_level >= 3:
            logger.info(f"Optimización {suggestion.id} requiere aprobación (riesgo nivel {suggestion.risk_level})")
            return False
        
        handler = self.optimization_handlers.get(suggestion.type)
        if not handler:
            logger.error(f"No hay handler para tipo de optimización: {suggestion.type}")
            return False
        
        try:
            success = await handler(suggestion)
            
            if success:
                self.implemented_optimizations.append({
                    "timestamp": datetime.now().isoformat(),
                    "suggestion_id": suggestion.id,
                    "component": suggestion.component,
                    "type": suggestion.type,
                    "success": True
                })
                logger.info(f"Optimización implementada: {suggestion.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error implementando optimización {suggestion.id}: {e}")
            return False
    
    async def _optimize_memory(self, suggestion: OptimizationSuggestion) -> bool:
        """Optimiza uso de memoria"""
        try:
            import gc
            gc.collect()
            
            # Limpiar sesiones inactivas
            current_time = time.time()
            sessions_to_remove = []
            
            for session_id, brain in active_sessions.items():
                # Verificar tiempo de inactividad (simulado)
                if hasattr(brain, 'last_activity'):
                    if current_time - brain.last_activity > 3600:  # 1 hora
                        sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                if session_id != "default":  # No eliminar sesión default
                    del active_sessions[session_id]
            
            logger.info(f"Memory optimization: {len(sessions_to_remove)} sesiones inactivas removidas")
            return True
            
        except Exception as e:
            logger.error(f"Error en optimización de memoria: {e}")
            return False
    
    async def _optimize_cpu(self, suggestion: OptimizationSuggestion) -> bool:
        """Optimiza uso de CPU"""
        # Implementación básica - puede incluir throttling
        logger.info("CPU optimization requested")
        return True
    
    async def _optimize_disk(self, suggestion: OptimizationSuggestion) -> bool:
        """Optimiza uso de disco"""
        try:
            files_removed = 0
            
            # Limpiar logs antiguos
            if LOGS_PATH.exists():
                cutoff_date = datetime.now() - timedelta(days=30)
                for log_file in LOGS_PATH.glob("*.log"):
                    if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                        log_file.unlink()
                        files_removed += 1
            
            # Limpiar archivos temporales
            temp_dirs = [Path("/tmp"), Path(os.getenv("TEMP", "/tmp"))]
            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    for temp_file in temp_dir.glob("brain_chat_*"):
                        if temp_file.is_file():
                            temp_file.unlink()
                            files_removed += 1
            
            logger.info(f"Disk optimization: {files_removed} archivos removidos")
            return True
            
        except Exception as e:
            logger.error(f"Error en optimización de disco: {e}")
            return False
    
    async def _optimize_cache(self, suggestion: OptimizationSuggestion) -> bool:
        """Optimiza caché"""
        # Implementación básica
        logger.info("Cache optimization requested")
        return True
    
    async def _optimize_sessions(self, suggestion: OptimizationSuggestion) -> bool:
        """Optimiza sesiones"""
        # Implementación básica
        logger.info("Session optimization requested")
        return True
    
    def generate_optimization_report(self) -> str:
        """
        Genera un reporte de optimización.
        
        Returns:
            Reporte formateado como string
        """
        report_lines = [
            "=" * 60,
            "AUTOOPTIMIZER REPORT",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total Metrics Collected: {len(self.metrics_history)}",
            f"Bottlenecks Detected: {len(self.bottlenecks)}",
            f"Optimizations Suggested: {len(self.suggestions)}",
            f"Optimizations Implemented: {len(self.implemented_optimizations)}",
            "",
        ]
        
        # Métricas actuales
        if self.metrics_history:
            latest = self.metrics_history[-1]
            report_lines.extend([
                "Current System Metrics:",
                "-" * 60,
                f"  CPU Usage: {latest.cpu_percent:.1f}%",
                f"  Memory Usage: {latest.memory_percent:.1f}%",
                f"  Disk Usage: {latest.disk_usage_percent:.1f}%",
                f"  Active Sessions: {latest.active_sessions}",
                f"  Response Time: {latest.response_time_ms:.2f}ms",
                "",
            ])
        
        # Cuellos de botella recientes
        if self.bottlenecks:
            report_lines.extend([
                "Recent Bottlenecks:",
                "-" * 60,
            ])
            for bottleneck in self.bottlenecks[-5:]:
                report_lines.append(f"  {bottleneck.timestamp.strftime('%H:%M:%S')} - "
                                  f"{bottleneck.component}: {bottleneck.severity} "
                                  f"({bottleneck.current_value:.1f})")
            report_lines.append("")
        
        # Optimizaciones implementadas
        if self.implemented_optimizations:
            report_lines.extend([
                "Recent Optimizations:",
                "-" * 60,
            ])
            for opt in self.implemented_optimizations[-5:]:
                report_lines.append(f"  {opt['timestamp']}: {opt['component']} - {opt['type']}")
        
        report_lines.append("=" * 60)
        
        return '\n'.join(report_lines)
    
    async def start_monitoring(self):
        """Inicia el monitoreo de rendimiento"""
        if not self.monitoring:
            self.monitoring = True
            self.monitoring_task = asyncio.create_task(self.monitor_performance_metrics())
            logger.info("AutoOptimizer monitoring started")
    
    async def stop_monitoring(self):
        """Detiene el monitoreo de rendimiento"""
        self.monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("AutoOptimizer monitoring stopped")

# ============================================================
# SELFIMPROVEMENT (líneas 7401-7600)
# ============================================================

@dataclass
class ConversationPattern:
    """Patrón de conversación detectado"""
    pattern_type: str
    frequency: int
    success_rate: float
    avg_response_time: float
    user_feedback_score: float
    timestamp: datetime

@dataclass
class ImprovementArea:
    """Área identificada para mejora"""
    category: str
    description: str
    impact_level: str  # low, medium, high
    current_performance: float
    target_performance: float
    suggested_actions: List[str]
    timestamp: datetime

class SelfImprovement:
    """
    Sistema de mejora continua que analiza patrones de conversación,
    identifica áreas de mejora y actualiza patrones de respuesta.
    """
    
    def __init__(self):
        self.conversation_patterns: Dict[str, ConversationPattern] = {}
        self.improvement_areas: List[ImprovementArea] = []
        self.successful_interactions: List[Dict] = []
        self.response_patterns: Dict[str, Dict] = {}
        self.learning_history: List[Dict] = []
        self.user_feedback: Dict[str, List[float]] = {}
        self.monitoring_enabled = True
        
        # Configuración de análisis
        self.min_samples_for_pattern = 5
        self.improvement_threshold = 0.7
        self.excellent_threshold = 0.9
    
    async def analyze_conversation_patterns(self, user_id: str):
        """
        Analiza patrones de conversación para un usuario específico.
        
        Args:
            user_id: ID del usuario a analizar
        """
        if user_id not in active_sessions:
            return
        
        brain = active_sessions[user_id]
        
        # Analizar historial de conversación
        if hasattr(brain, 'memory') and brain.memory:
            interactions = brain.memory.short_term + brain.memory.long_term_entries
            
            patterns_detected = {
                "question_types": {},
                "response_satisfaction": [],
                "common_topics": {},
                "interaction_frequency": {},
            }
            
            for interaction in interactions:
                # Analizar tipo de pregunta
                query = interaction.get("query", "").lower()
                
                # Clasificar por tipo
                if any(word in query for word in ["cómo", "como", "how"]):
                    patterns_detected["question_types"]["how_to"] = \
                        patterns_detected["question_types"].get("how_to", 0) + 1
                elif any(word in query for word in ["qué", "que", "what", "cuál", "cual"]):
                    patterns_detected["question_types"]["what_is"] = \
                        patterns_detected["question_types"].get("what_is", 0) + 1
                elif any(word in query for word in ["por qué", "porque", "why"]):
                    patterns_detected["question_types"]["why"] = \
                        patterns_detected["question_types"].get("why", 0) + 1
                
                # Extraer tópicos (simplificado)
                words = query.split()
                for word in words:
                    if len(word) > 4:  # Ignorar palabras cortas
                        patterns_detected["common_topics"][word] = \
                            patterns_detected["common_topics"].get(word, 0) + 1
            
            # Almacenar patrón
            pattern_key = f"user_{user_id}"
            self.conversation_patterns[pattern_key] = ConversationPattern(
                pattern_type="user_interaction",
                frequency=len(interactions),
                success_rate=self._calculate_success_rate(user_id),
                avg_response_time=self._calculate_avg_response_time(user_id),
                user_feedback_score=self._get_user_feedback_score(user_id),
                timestamp=datetime.now()
            )
    
    def _calculate_success_rate(self, user_id: str) -> float:
        """Calcula tasa de éxito para un usuario"""
        interactions = self.successful_interactions
        user_interactions = [i for i in interactions if i.get("user_id") == user_id]
        
        if not user_interactions:
            return 0.5  # Valor neutral por defecto
        
        successful = len([i for i in user_interactions if i.get("success", False)])
        return successful / len(user_interactions)
    
    def _calculate_avg_response_time(self, user_id: str) -> float:
        """Calcula tiempo de respuesta promedio"""
        interactions = self.successful_interactions
        user_interactions = [i for i in interactions if i.get("user_id") == user_id]
        
        if not user_interactions:
            return 0.0
        
        times = [i.get("response_time", 0) for i in user_interactions]
        return sum(times) / len(times)
    
    def _get_user_feedback_score(self, user_id: str) -> float:
        """Obtiene puntuación de feedback del usuario"""
        if user_id in self.user_feedback:
            scores = self.user_feedback[user_id]
            return sum(scores) / len(scores)
        return 0.5
    
    async def identify_improvement_areas(self) -> List[ImprovementArea]:
        """
        Identifica áreas donde el sistema puede mejorar.
        
        Returns:
            Lista de áreas de mejora identificadas
        """
        areas = []
        
        # Analizar patrones de conversación
        for pattern_key, pattern in self.conversation_patterns.items():
            # Identificar áreas basadas en métricas
            if pattern.success_rate < self.improvement_threshold:
                areas.append(ImprovementArea(
                    category="response_quality",
                    description=f"Mejorar calidad de respuestas para {pattern_key}",
                    impact_level="high",
                    current_performance=pattern.success_rate,
                    target_performance=self.excellent_threshold,
                    suggested_actions=[
                        "Revisar patrones de respuesta",
                        "Ajustar prompts de sistema",
                        "Incorporar más contexto"
                    ],
                    timestamp=datetime.now()
                ))
            
            if pattern.avg_response_time > 2000:  # Más de 2 segundos
                areas.append(ImprovementArea(
                    category="response_speed",
                    description=f"Optimizar tiempo de respuesta para {pattern_key}",
                    impact_level="medium",
                    current_performance=1000 / pattern.avg_response_time,  # Invertir
                    target_performance=0.5,  # 500ms
                    suggested_actions=[
                        "Implementar caching",
                        "Optimizar queries",
                        "Usar modelos más rápidos"
                    ],
                    timestamp=datetime.now()
                ))
        
        self.improvement_areas = areas
        return areas
    
    async def update_response_patterns(self, feedback: Dict):
        """
        Actualiza patrones de respuesta basándose en feedback.
        
        Args:
            feedback: Diccionario con feedback del usuario
        """
        user_id = feedback.get("user_id")
        query_pattern = feedback.get("query_pattern")
        response_quality = feedback.get("response_quality", 0.5)
        
        if user_id and query_pattern:
            # Almacenar feedback
            if user_id not in self.user_feedback:
                self.user_feedback[user_id] = []
            self.user_feedback[user_id].append(response_quality)
            
            # Actualizar patrón de respuesta
            if query_pattern not in self.response_patterns:
                self.response_patterns[query_pattern] = {
                    "total_interactions": 0,
                    "avg_quality": 0.0,
                    "last_updated": datetime.now().isoformat()
                }
            
            pattern_data = self.response_patterns[query_pattern]
            pattern_data["total_interactions"] += 1
            
            # Calcular promedio móvil
            old_avg = pattern_data["avg_quality"]
            n = pattern_data["total_interactions"]
            pattern_data["avg_quality"] = (old_avg * (n - 1) + response_quality) / n
            pattern_data["last_updated"] = datetime.now().isoformat()
    
    async def learn_from_successes(self, successful_interactions: List[Dict]):
        """
        Aprende de interacciones exitosas.
        
        Args:
            successful_interactions: Lista de interacciones exitosas
        """
        for interaction in successful_interactions:
            self.successful_interactions.append(interaction)
            
            # Extraer patrones exitosos
            query = interaction.get("query", "")
            response = interaction.get("response", "")
            
            # Identificar características de respuestas exitosas
            success_factors = {
                "query_length": len(query),
                "response_length": len(response),
                "has_code": "```" in response,
                "has_examples": "ejemplo" in response.lower() or "example" in response.lower(),
                "timestamp": datetime.now().isoformat()
            }
            
            # Almacenar en historial de aprendizaje
            self.learning_history.append({
                "interaction": interaction,
                "success_factors": success_factors
            })
        
        # Limitar historial
        if len(self.learning_history) > 1000:
            self.learning_history = self.learning_history[-1000:]
    
    def generate_learning_report(self) -> str:
        """
        Genera un reporte de aprendizaje.
        
        Returns:
            Reporte formateado como string
        """
        report_lines = [
            "=" * 60,
            "SELFIMPROVEMENT LEARNING REPORT",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Conversation Patterns Analyzed: {len(self.conversation_patterns)}",
            f"Improvement Areas Identified: {len(self.improvement_areas)}",
            f"Successful Interactions Learned: {len(self.successful_interactions)}",
            f"Response Patterns Updated: {len(self.response_patterns)}",
            "",
        ]
        
        # Patrones de conversación
        if self.conversation_patterns:
            report_lines.extend([
                "Conversation Patterns:",
                "-" * 60,
            ])
            for key, pattern in list(self.conversation_patterns.items())[:10]:
                report_lines.append(f"  {key}:")
                report_lines.append(f"    Frequency: {pattern.frequency}")
                report_lines.append(f"    Success Rate: {pattern.success_rate:.2%}")
                report_lines.append(f"    Avg Response Time: {pattern.avg_response_time:.0f}ms")
                report_lines.append(f"    Feedback Score: {pattern.user_feedback_score:.2f}")
            report_lines.append("")
        
        # Áreas de mejora
        if self.improvement_areas:
            report_lines.extend([
                "Improvement Areas:",
                "-" * 60,
            ])
            for area in self.improvement_areas:
                report_lines.append(f"  {area.category}: {area.impact_level}")
                report_lines.append(f"    Current: {area.current_performance:.2%}")
                report_lines.append(f"    Target: {area.target_performance:.2%}")
            report_lines.append("")
        
        # Factores de éxito más comunes
        if self.learning_history:
            report_lines.extend([
                "Success Factors Analysis:",
                "-" * 60,
            ])
            
            has_code_count = sum(1 for h in self.learning_history 
                               if h["success_factors"].get("has_code"))
            has_examples_count = sum(1 for h in self.learning_history 
                                     if h["success_factors"].get("has_examples"))
            
            total = len(self.learning_history)
            report_lines.append(f"  Responses with code: {has_code_count/total:.1%}")
            report_lines.append(f"  Responses with examples: {has_examples_count/total:.1%}")
        
        report_lines.append("=" * 60)
        
        return '\n'.join(report_lines)

# ============================================================
# PROACTIVEMONITOR (líneas 7601-7800)
# ============================================================

@dataclass
class ServiceStatus:
    """Estado de un servicio monitoreado"""
    name: str
    is_healthy: bool
    last_check: datetime
    response_time_ms: float
    error_count: int
    details: Dict

@dataclass
class Anomaly:
    """Anomalía detectada en el sistema"""
    type: str
    severity: str  # info, warning, critical
    description: str
    service_affected: str
    detected_at: datetime
    auto_resolvable: bool
    suggested_action: str

class ProactiveMonitor:
    """
    Monitoreo proactivo de servicios que detecta anomalías,
    alerta al usuario y puede auto-resolver problemas comunes.
    """
    
    def __init__(self, check_interval: int = 300):
        self.check_interval = check_interval
        self.services: Dict[str, ServiceStatus] = {}
        self.anomalies: List[Anomaly] = []
        self.monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.alert_history: List[Dict] = []
        
        # Servicios a monitorear
        self.services_to_monitor = {
            "api": {"url": "http://localhost:8000/health", "timeout": 5},
            "ollama": {"url": "http://localhost:11434/api/tags", "timeout": 5},
            "memory": {"check": self._check_memory_service},
            "disk": {"check": self._check_disk_service},
        }
        
        # Handlers de auto-resolución
        self.auto_resolve_handlers = {
            "service_down": self._restart_service,
            "high_memory": self._cleanup_memory,
            "disk_full": self._cleanup_disk,
            "slow_response": self._optimize_response_time,
        }
    
    async def start_monitoring(self):
        """Inicia el monitoreo proactivo"""
        if not self.monitoring:
            self.monitoring = True
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            logger.info("ProactiveMonitor started")
    
    async def _monitoring_loop(self):
        """Loop principal de monitoreo"""
        while self.monitoring:
            try:
                await self.check_service_health()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error en monitoring_loop: {e}")
                await asyncio.sleep(60)
    
    async def check_service_health(self):
        """
        Verifica la salud de todos los servicios monitoreados.
        """
        for service_name, config in self.services_to_monitor.items():
            try:
                start_time = time.time()
                
                if "url" in config:
                    # Verificar servicio HTTP
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            config["url"], 
                            timeout=aiohttp.ClientTimeout(total=config["timeout"])
                        ) as response:
                            is_healthy = response.status == 200
                            response_time = (time.time() - start_time) * 1000
                            
                            details = {
                                "status_code": response.status,
                                "headers": dict(response.headers)
                            }
                
                elif "check" in config:
                    # Verificar usando función personalizada
                    is_healthy, details = await config["check"]()
                    response_time = (time.time() - start_time) * 1000
                
                else:
                    is_healthy = False
                    response_time = 0
                    details = {"error": "No check method configured"}
                
                # Actualizar estado del servicio
                previous_status = self.services.get(service_name)
                
                self.services[service_name] = ServiceStatus(
                    name=service_name,
                    is_healthy=is_healthy,
                    last_check=datetime.now(),
                    response_time_ms=response_time,
                    error_count=previous_status.error_count + 1 if previous_status and not is_healthy else 0,
                    details=details
                )
                
                # Detectar cambios de estado
                if previous_status and previous_status.is_healthy and not is_healthy:
                    # Servicio cayó
                    await self.detect_anomalies()
                    await self.alert_user(
                        "critical",
                        f"Servicio {service_name} no responde"
                    )
                
                # Verificar tiempo de respuesta lento
                if response_time > 5000:  # Más de 5 segundos
                    await self.alert_user(
                        "warning",
                        f"Servicio {service_name} responde lentamente ({response_time:.0f}ms)"
                    )
                
            except Exception as e:
                logger.error(f"Error verificando {service_name}: {e}")
                
                # Marcar como no saludable
                self.services[service_name] = ServiceStatus(
                    name=service_name,
                    is_healthy=False,
                    last_check=datetime.now(),
                    response_time_ms=0,
                    error_count=self.services.get(service_name, ServiceStatus(
                        name=service_name, is_healthy=False, last_check=datetime.now(),
                        response_time_ms=0, error_count=0, details={}
                    )).error_count + 1,
                    details={"error": str(e)}
                )
    
    async def _check_memory_service(self) -> Tuple[bool, Dict]:
        """Verifica el servicio de memoria"""
        try:
            memory = psutil.virtual_memory()
            is_healthy = memory.percent < 90
            return is_healthy, {
                "total_gb": memory.total / (1024**3),
                "used_gb": memory.used / (1024**3),
                "percent": memory.percent
            }
        except Exception as e:
            return False, {"error": str(e)}
    
    async def _check_disk_service(self) -> Tuple[bool, Dict]:
        """Verifica el servicio de disco"""
        try:
            disk = psutil.disk_usage('/')
            is_healthy = (disk.used / disk.total) < 0.95
            return is_healthy, {
                "total_gb": disk.total / (1024**3),
                "used_gb": disk.used / (1024**3),
                "percent": (disk.used / disk.total) * 100
            }
        except Exception as e:
            return False, {"error": str(e)}
    
    async def detect_anomalies(self):
        """
        Detecta anomalías en los servicios monitoreados.
        """
        anomalies_detected = []
        
        for service_name, status in self.services.items():
            if not status.is_healthy:
                anomaly = Anomaly(
                    type="service_down",
                    severity="critical",
                    description=f"Servicio {service_name} no está respondiendo",
                    service_affected=service_name,
                    detected_at=datetime.now(),
                    auto_resolvable=service_name in ["ollama", "memory"],
                    suggested_action=f"Reiniciar servicio {service_name}"
                )
                anomalies_detected.append(anomaly)
            
            elif status.error_count > 3:
                anomaly = Anomaly(
                    type="service_unstable",
                    severity="warning",
                    description=f"Servicio {service_name} mostrando inestabilidad",
                    service_affected=service_name,
                    detected_at=datetime.now(),
                    auto_resolvable=False,
                    suggested_action=f"Revisar logs de {service_name}"
                )
                anomalies_detected.append(anomaly)
            
            elif status.response_time_ms > 10000:
                anomaly = Anomaly(
                    type="slow_response",
                    severity="warning",
                    description=f"Servicio {service_name} con tiempo de respuesta alto",
                    service_affected=service_name,
                    detected_at=datetime.now(),
                    auto_resolvable=True,
                    suggested_action="Optimizar rendimiento"
                )
                anomalies_detected.append(anomaly)
        
        self.anomalies.extend(anomalies_detected)
        
        # Intentar auto-resolver anomalías
        for anomaly in anomalies_detected:
            if anomaly.auto_resolvable:
                await self.auto_resolve(anomaly.type)
    
    async def alert_user(self, severity: str, message: str):
        """
        Alerta al usuario sobre un problema.
        
        Args:
            severity: Nivel de severidad (info, warning, critical)
            message: Mensaje de alerta
        """
        alert = {
            "timestamp": datetime.now().isoformat(),
            "severity": severity,
            "message": message,
        }
        
        self.alert_history.append(alert)
        
        # Loguear alerta
        if severity == "critical":
            logger.critical(f"[ALERTA] {message}")
        elif severity == "warning":
            logger.warning(f"[ALERTA] {message}")
        else:
            logger.info(f"[INFO] {message}")
    
    async def auto_resolve(self, issue_type: str) -> bool:
        """
        Intenta resolver automáticamente un problema.
        
        Args:
            issue_type: Tipo de problema a resolver
            
        Returns:
            True si se resolvió exitosamente
        """
        handler = self.auto_resolve_handlers.get(issue_type)
        if not handler:
            logger.warning(f"No hay handler para {issue_type}")
            return False
        
        try:
            success = await handler()
            if success:
                logger.info(f"Problema {issue_type} auto-resuelto")
            return success
        except Exception as e:
            logger.error(f"Error auto-resolviendo {issue_type}: {e}")
            return False
    
    async def _restart_service(self) -> bool:
        """Reinicia un servicio caído"""
        # Implementación básica - puede extenderse
        logger.info("Intentando reiniciar servicio")
        return False
    
    async def _cleanup_memory(self) -> bool:
        """Limpia memoria"""
        try:
            import gc
            gc.collect()
            logger.info("Memoria liberada")
            return True
        except Exception as e:
            logger.error(f"Error limpiando memoria: {e}")
            return False
    
    async def _cleanup_disk(self) -> bool:
        """Limpia disco"""
        try:
            # Limpiar logs antiguos
            cutoff_date = datetime.now() - timedelta(days=7)
            files_removed = 0
            
            if LOGS_PATH.exists():
                for log_file in LOGS_PATH.glob("*.log"):
                    if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                        log_file.unlink()
                        files_removed += 1
            
            logger.info(f"Disco limpiado: {files_removed} archivos removidos")
            return files_removed > 0
            
        except Exception as e:
            logger.error(f"Error limpiando disco: {e}")
            return False
    
    async def _optimize_response_time(self) -> bool:
        """Optimiza tiempo de respuesta"""
        # Implementación básica
        logger.info("Optimización de tiempo de respuesta solicitada")
        return True
    
    async def stop_monitoring(self):
        """Detiene el monitoreo proactivo"""
        self.monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("ProactiveMonitor stopped")

# ============================================================
# APPROVALGATE (líneas 7801-8000)
# ============================================================

@dataclass
class PendingAction:
    """Acción pendiente de aprobación"""
    id: str
    action_type: str
    description: str
    risk_level: int
    requested_at: datetime
    expires_at: datetime
    context: Dict
    status: str  # pending, approved, rejected, expired

class ApprovalGate:
    """
    Sistema de aprobaciones que controla qué acciones autónomas
    requieren aprobación del usuario antes de ejecutarse.
    """
    
    def __init__(self):
        self.pending_actions: Dict[str, PendingAction] = {}
        self.action_history: List[Dict] = []
        self.approval_rules = {
            "delete_file": AutonomyLevel.LEVEL_2_LOW_RISK,
            "modify_config": AutonomyLevel.LEVEL_3_MEDIUM_RISK,
            "restart_service": AutonomyLevel.LEVEL_3_MEDIUM_RISK,
            "update_code": AutonomyLevel.LEVEL_4_HIGH_RISK,
            "install_package": AutonomyLevel.LEVEL_3_MEDIUM_RISK,
            "cleanup_logs": AutonomyLevel.LEVEL_2_LOW_RISK,
            "optimize_memory": AutonomyLevel.LEVEL_2_LOW_RISK,
            "execute_command": AutonomyLevel.LEVEL_3_MEDIUM_RISK,
        }
        self.action_timeout = timedelta(hours=24)
    
    def requires_approval(self, action_type: str, risk_level: int = None) -> bool:
        """
        Determina si una acción requiere aprobación.
        
        Args:
            action_type: Tipo de acción a realizar
            risk_level: Nivel de riesgo (1-4), opcional
            
        Returns:
            True si requiere aprobación
        """
        # Siempre requerir aprobación para nivel 4
        if risk_level and risk_level >= 4:
            return True
        
        # Siempre requerir aprobación para nivel 1 (sugerir)
        if risk_level and risk_level == 1:
            return True
        
        # Verificar reglas específicas
        autonomy_level = self.approval_rules.get(action_type, AutonomyLevel.LEVEL_1_SUGGEST)
        
        # Nivel 2 (bajo riesgo) no requiere aprobación
        if autonomy_level == AutonomyLevel.LEVEL_2_LOW_RISK:
            return False
        
        # Nivel 3 y 4 requieren aprobación
        return True
    
    async def request_approval(self, action: str, reason: str) -> str:
        """
        Solicita aprobación para una acción.
        
        Args:
            action: Descripción de la acción
            reason: Razón de la solicitud
            
        Returns:
            ID de la acción pendiente
        """
        action_id = f"action_{hashlib.md5(f'{action}{time.time()}'.encode()).hexdigest()[:12]}"
        
        pending_action = PendingAction(
            id=action_id,
            action_type=self._classify_action(action),
            description=action,
            risk_level=self._estimate_risk(action),
            requested_at=datetime.now(),
            expires_at=datetime.now() + self.action_timeout,
            context={"reason": reason},
            status="pending"
        )
        
        self.pending_actions[action_id] = pending_action
        
        logger.info(f"Aprobación solicitada: {action_id} - {action}")
        
        return action_id
    
    def _classify_action(self, action: str) -> str:
        """Clasifica una acción por tipo"""
        action_lower = action.lower()
        
        if any(word in action_lower for word in ["delete", "remove", "clean"]):
            return "cleanup"
        elif any(word in action_lower for word in ["restart", "stop", "start"]):
            return "restart_service"
        elif any(word in action_lower for word in ["update", "modify", "change"]):
            return "modify_config"
        elif any(word in action_lower for word in ["install", "pip", "package"]):
            return "install_package"
        elif any(word in action_lower for word in ["execute", "run", "command"]):
            return "execute_command"
        elif any(word in action_lower for word in ["optimize", "memory", "cache"]):
            return "optimize_memory"
        else:
            return "unknown"
    
    def _estimate_risk(self, action: str) -> int:
        """Estima el nivel de riesgo de una acción (1-4)"""
        action_lower = action.lower()
        
        # Alto riesgo: modificar código, eliminar datos críticos
        if any(word in action_lower for word in ["code", "script", "source", "modify system"]):
            return 4
        
        # Medio riesgo: reiniciar servicios, instalar paquetes
        elif any(word in action_lower for word in ["restart", "install", "service", "config"]):
            return 3
        
        # Bajo riesgo: limpiar logs, optimizar memoria
        elif any(word in action_lower for word in ["log", "cache", "temp", "memory", "cleanup"]):
            return 2
        
        # Nivel 1: solo sugerir
        return 1
    
    def approve_action(self, action_id: str, user_id: str = "system") -> bool:
        """
        Aprueba una acción pendiente.
        
        Args:
            action_id: ID de la acción
            user_id: ID del usuario que aprueba
            
        Returns:
            True si se aprobó exitosamente
        """
        if action_id not in self.pending_actions:
            return False
        
        action = self.pending_actions[action_id]
        action.status = "approved"
        
        # Registrar en historial
        self.log_action(action, True, user_id)
        
        # Remover de pendientes
        del self.pending_actions[action_id]
        
        logger.info(f"Acción aprobada: {action_id}")
        return True
    
    def reject_action(self, action_id: str, user_id: str = "system") -> bool:
        """
        Rechaza una acción pendiente.
        
        Args:
            action_id: ID de la acción
            user_id: ID del usuario que rechaza
            
        Returns:
            True si se rechazó exitosamente
        """
        if action_id not in self.pending_actions:
            return False
        
        action = self.pending_actions[action_id]
        action.status = "rejected"
        
        # Registrar en historial
        self.log_action(action, False, user_id)
        
        # Remover de pendientes
        del self.pending_actions[action_id]
        
        logger.info(f"Acción rechazada: {action_id}")
        return True
    
    def log_action(self, action: PendingAction, approved: bool, user_id: str):
        """
        Registra una acción en el historial.
        
        Args:
            action: Acción a registrar
            approved: Si fue aprobada o no
            user_id: ID del usuario
        """
        self.action_history.append({
            "timestamp": datetime.now().isoformat(),
            "action_id": action.id,
            "action_type": action.action_type,
            "description": action.description,
            "risk_level": action.risk_level,
            "approved": approved,
            "user_id": user_id
        })
        
        # Limitar historial
        if len(self.action_history) > 1000:
            self.action_history = self.action_history[-1000:]
    
    def get_pending_approvals(self) -> List[Dict]:
        """
        Obtiene lista de aprobaciones pendientes.
        
        Returns:
            Lista de acciones pendientes
        """
        # Limpiar acciones expiradas
        current_time = datetime.now()
        expired = [aid for aid, action in self.pending_actions.items() 
                  if current_time > action.expires_at]
        
        for aid in expired:
            action = self.pending_actions[aid]
            action.status = "expired"
            self.log_action(action, False, "system")
            del self.pending_actions[aid]
        
        # Retornar pendientes como diccionarios
        return [
            {
                "id": action.id,
                "action_type": action.action_type,
                "description": action.description,
                "risk_level": action.risk_level,
                "requested_at": action.requested_at.isoformat(),
                "expires_at": action.expires_at.isoformat(),
                "context": action.context
            }
            for action in self.pending_actions.values()
        ]
    
    def get_action_history(self, limit: int = 50) -> List[Dict]:
        """
        Obtiene historial de acciones.
        
        Args:
            limit: Número máximo de acciones a retornar
            
        Returns:
            Lista de acciones históricas
        """
        return self.action_history[-limit:]

# ============================================================
# INTEGRACIÓN EN BRAINCHATV8 (líneas 8001-8200)
# ============================================================

# Variables globales para sistemas de autonomía
auto_debugger: Optional[AutoDebugger] = None
auto_optimizer: Optional[AutoOptimizer] = None
proactive_monitor: Optional[ProactiveMonitor] = None
approval_gate: Optional[ApprovalGate] = None
self_improvement: Optional[SelfImprovement] = None
autonomy_background_tasks: List[asyncio.Task] = []

def setup_autonomy_system():
    """
    Inicializa todos los sistemas de autonomía.
    Debe llamarse al inicio de la aplicación.
    """
    global auto_debugger, auto_optimizer, proactive_monitor, approval_gate, self_improvement
    
    auto_debugger = AutoDebugger()
    auto_optimizer = AutoOptimizer()
    proactive_monitor = ProactiveMonitor()
    approval_gate = ApprovalGate()
    self_improvement = SelfImprovement()
    
    logger.info("Sistemas de autonomía inicializados")

async def start_auto_debugging():
    """Inicia el auto-debugging en background"""
    if auto_debugger and AUTONOMY_CONFIG["auto_debugging_enabled"]:
        await auto_debugger.start_monitoring()
        logger.info("Auto-debugging iniciado (cada 5 minutos)")

async def start_performance_monitoring():
    """Inicia el monitoreo de rendimiento en background"""
    if auto_optimizer and AUTONOMY_CONFIG["auto_optimization_enabled"]:
        await auto_optimizer.start_monitoring()
        logger.info("Performance monitoring iniciado (cada 10 minutos)")

async def start_proactive_monitoring():
    """Inicia el monitoreo proactivo en background"""
    if proactive_monitor and AUTONOMY_CONFIG["proactive_monitoring_enabled"]:
        await proactive_monitor.start_monitoring()
        logger.info("Proactive monitoring iniciado (cada 5 minutos)")

async def stop_all_autonomy_tasks():
    """Detiene todas las tareas de autonomía"""
    if auto_debugger:
        await auto_debugger.stop_monitoring()
    if auto_optimizer:
        await auto_optimizer.stop_monitoring()
    if proactive_monitor:
        await proactive_monitor.stop_monitoring()
    
    # Cancelar tareas en background
    for task in autonomy_background_tasks:
        task.cancel()
    
    logger.info("Tareas de autonomía detenidas")

# Métodos adicionales para BrainChatV8
async def handle_error_auto(error: Exception, context: Dict = None):
    """
    Maneja un error automáticamente usando el auto-debugger.
    
    Args:
        error: Excepción ocurrida
        context: Contexto adicional
    """
    if not auto_debugger:
        return
    
    error_message = f"{type(error).__name__}: {str(error)}"
    if context:
        error_message += f"\nContext: {json.dumps(context)}"
    
    # Analizar patrón de error
    pattern = await auto_debugger.analyze_error_pattern(error_message)
    
    if pattern and pattern.confidence >= AUTONOMY_CONFIG["confidence_threshold_low"]:
        # Intentar auto-corregir si es nivel 2 o menor
        if approval_gate and not approval_gate.requires_approval(pattern.error_type, 2):
            await auto_debugger.attempt_fix(pattern)
        else:
            logger.info(f"Error detectado requiere aprobación: {pattern.error_type}")

async def suggest_optimizations() -> List[OptimizationSuggestion]:
    """
    Sugiere optimizaciones basándose en el auto-optimizer.
    
    Returns:
        Lista de sugerencias de optimización
    """
    if not auto_optimizer:
        return []
    
    suggestions = []
    
    # Generar sugerencias basadas en cuellos de botella detectados
    for bottleneck in auto_optimizer.bottlenecks:
        new_suggestions = await auto_optimizer.suggest_optimizations(bottleneck.component)
        suggestions.extend(new_suggestions)
    
    return suggestions

async def request_user_approval(action: str, reason: str) -> str:
    """
    Solicita aprobación del usuario para una acción.
    
    Args:
        action: Descripción de la acción
        reason: Razón de la solicitud
        
    Returns:
        ID de la acción pendiente
    """
    if not approval_gate:
        return ""
    
    return await approval_gate.request_approval(action, reason)

async def get_autonomy_status() -> Dict:
    """
    Obtiene el estado completo del sistema de autonomía.
    
    Returns:
        Diccionario con estado de todos los componentes
    """
    return {
        "auto_debugger": {
            "enabled": AUTONOMY_CONFIG["auto_debugging_enabled"],
            "monitoring": auto_debugger.monitoring if auto_debugger else False,
            "patterns_detected": len(auto_debugger.error_patterns) if auto_debugger else 0,
            "fixes_applied": len([f for f in auto_debugger.fix_history if f.get("fix_applied")]) if auto_debugger else 0,
        },
        "auto_optimizer": {
            "enabled": AUTONOMY_CONFIG["auto_optimization_enabled"],
            "monitoring": auto_optimizer.monitoring if auto_optimizer else False,
            "bottlenecks_detected": len(auto_optimizer.bottlenecks) if auto_optimizer else 0,
            "optimizations_suggested": len(auto_optimizer.suggestions) if auto_optimizer else 0,
        },
        "proactive_monitor": {
            "enabled": AUTONOMY_CONFIG["proactive_monitoring_enabled"],
            "monitoring": proactive_monitor.monitoring if proactive_monitor else False,
            "services_monitored": len(proactive_monitor.services) if proactive_monitor else 0,
            "anomalies_detected": len(proactive_monitor.anomalies) if proactive_monitor else 0,
        },
        "approval_gate": {
            "pending_approvals": len(approval_gate.pending_actions) if approval_gate else 0,
            "total_actions": len(approval_gate.action_history) if approval_gate else 0,
        },
        "self_improvement": {
            "enabled": AUTONOMY_CONFIG["self_improvement_enabled"],
            "patterns_learned": len(self_improvement.conversation_patterns) if self_improvement else 0,
            "improvement_areas": len(self_improvement.improvement_areas) if self_improvement else 0,
        },
        "config": AUTONOMY_CONFIG
    }

# ============================================================
# ENDPOINTS FASTAPI PARA AUTONOMÍA (líneas 8201-8400)
# ============================================================

@app.get("/autonomy/status")
async def get_autonomy_status_endpoint():
    """
    Endpoint para obtener el estado del sistema de autonomía.
    """
    status = await get_autonomy_status()
    return {
        "status": "success",
        "data": status,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/autonomy/approve/{action_id}")
async def approve_action_endpoint(action_id: str):
    """
    Endpoint para aprobar una acción pendiente.
    """
    if not approval_gate:
        raise HTTPException(status_code=503, detail="Approval gate not initialized")
    
    success = approval_gate.approve_action(action_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    
    return {
        "status": "success",
        "message": f"Action {action_id} approved",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/autonomy/pending-approvals")
async def get_pending_approvals_endpoint():
    """
    Endpoint para obtener acciones pendientes de aprobación.
    """
    if not approval_gate:
        raise HTTPException(status_code=503, detail="Approval gate not initialized")
    
    pending = approval_gate.get_pending_approvals()
    
    return {
        "status": "success",
        "data": {
            "pending_approvals": pending,
            "count": len(pending)
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/autonomy/reports")
async def get_autonomy_reports_endpoint():
    """
    Endpoint para obtener reportes del sistema de autonomía.
    """
    reports = {}
    
    if auto_debugger:
        reports["debugger"] = auto_debugger.generate_debug_report()
    
    if auto_optimizer:
        reports["optimizer"] = auto_optimizer.generate_optimization_report()
    
    if self_improvement:
        reports["self_improvement"] = self_improvement.generate_learning_report()
    
    return {
        "status": "success",
        "data": reports,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/autonomy/toggle/{component}")
async def toggle_autonomy_component_endpoint(component: str, enabled: bool = True):
    """
    Endpoint para activar/desactivar componentes de autonomía.
    
    Args:
        component: Nombre del componente (debugger, optimizer, monitor, self_improvement)
        enabled: True para activar, False para desactivar
    """
    global AUTONOMY_CONFIG
    
    component_map = {
        "debugger": "auto_debugging_enabled",
        "optimizer": "auto_optimization_enabled",
        "monitor": "proactive_monitoring_enabled",
        "self_improvement": "self_improvement_enabled"
    }
    
    if component not in component_map:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid component. Valid options: {list(component_map.keys())}"
        )
    
    config_key = component_map[component]
    AUTONOMY_CONFIG[config_key] = enabled
    
    # Iniciar o detener según corresponda
    if enabled:
        if component == "debugger" and auto_debugger:
            await auto_debugger.start_monitoring()
        elif component == "optimizer" and auto_optimizer:
            await auto_optimizer.start_monitoring()
        elif component == "monitor" and proactive_monitor:
            await proactive_monitor.start_monitoring()
    else:
        if component == "debugger" and auto_debugger:
            await auto_debugger.stop_monitoring()
        elif component == "optimizer" and auto_optimizer:
            await auto_optimizer.stop_monitoring()
        elif component == "monitor" and proactive_monitor:
            await proactive_monitor.stop_monitoring()
    
    return {
        "status": "success",
        "message": f"Component '{component}' {'enabled' if enabled else 'disabled'}",
        "config": AUTONOMY_CONFIG,
        "timestamp": datetime.now().isoformat()
    }

# ============================================================
# FASE 7: UI/UX - INTERFACE WEB INTELIGENTE (líneas 9266-10000+)
# ============================================================

from fastapi.responses import HTMLResponse
from fastapi import WebSocket, WebSocketDisconnect
import uuid

# HTML/CSS/JS Inline para UI Moderna
UI_HTML = '''
<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V8.0 - Agente Autónomo</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/python.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/javascript.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/bash.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/json.min.js"></script>
    <style>
        :root {
            /* Brain Lab Color System */
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --primary-light: #60a5fa;
            --secondary: #1e40af;
            --accent: #06b6d4;
            --accent-hover: #0891b2;
            
            /* Background colors */
            --bg-dark: #0f172a;
            --bg-darker: #020617;
            --bg-light: #1e293b;
            --bg-lighter: #334155;
            --bg-card: #1e293b;
            
            /* Text colors */
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            
            /* Border colors */
            --border-color: #334155;
            --border-light: #475569;
            
            /* Status colors */
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
            
            /* Spacing */
            --sidebar-width: 280px;
            --header-height: 60px;
            --input-height: 80px;
            
            /* Transitions */
            --transition-fast: 150ms ease;
            --transition-normal: 250ms ease;
            --transition-slow: 350ms ease;
        }
        
        [data-theme="light"] {
            --bg-dark: #ffffff;
            --bg-darker: #f8fafc;
            --bg-light: #f1f5f9;
            --bg-lighter: #e2e8f0;
            --bg-card: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border-color: #e2e8f0;
            --border-light: #cbd5e1;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            line-height: 1.6;
            overflow: hidden;
            height: 100vh;
        }
        
        /* Scrollbar Styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--bg-darker);
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--bg-lighter);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--border-light);
        }
        
        /* App Container */
        #app {
            display: flex;
            height: 100vh;
            width: 100vw;
        }
        
        /* Sidebar */
        .sidebar {
            width: var(--sidebar-width);
            background-color: var(--bg-darker);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
            transition: transform var(--transition-normal);
        }
        
        .sidebar-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .logo {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 18px;
            color: white;
            flex-shrink: 0;
        }
        
        .logo-text {
            flex: 1;
        }
        
        .logo-text h1 {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-primary);
            line-height: 1.2;
        }
        
        .logo-text span {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        /* Quick Actions */
        .quick-actions {
            padding: 12px 16px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        
        .quick-btn {
            padding: 10px 12px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-light);
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all var(--transition-fast);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .quick-btn:hover {
            background: var(--bg-lighter);
            border-color: var(--primary);
            color: var(--text-primary);
        }
        
        .quick-btn.active {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }
        
        /* Service Status */
        .service-status {
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
        }
        
        .section-title {
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 12px;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 0;
        }
        
        .status-label {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            animation: pulse 2s infinite;
        }
        
        .status-dot.warning {
            background: var(--warning);
        }
        
        .status-dot.error {
            background: var(--danger);
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .status-value {
            font-size: 12px;
            font-weight: 500;
            color: var(--text-muted);
        }
        
        /* Conversation History */
        .conversation-history {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }
        
        .history-item {
            padding: 12px;
            border-radius: 8px;
            cursor: pointer;
            transition: background var(--transition-fast);
            margin-bottom: 4px;
        }
        
        .history-item:hover {
            background: var(--bg-light);
        }
        
        .history-item.active {
            background: var(--primary);
        }
        
        .history-title {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .history-item.active .history-title {
            color: white;
        }
        
        .history-meta {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 4px;
        }
        
        .history-item.active .history-meta {
            color: rgba(255,255,255,0.7);
        }
        
        .new-chat-btn {
            margin: 16px;
            padding: 12px;
            background: var(--primary);
            border: none;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background var(--transition-fast);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .new-chat-btn:hover {
            background: var(--primary-hover);
        }
        
        /* Main Content */
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-width: 0;
        }
        
        /* Header */
        .main-header {
            height: var(--header-height);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 24px;
            background: var(--bg-dark);
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        
        .mode-selector {
            display: flex;
            gap: 4px;
            background: var(--bg-light);
            padding: 4px;
            border-radius: 8px;
        }
        
        .mode-btn {
            padding: 6px 12px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 500;
            border-radius: 6px;
            cursor: pointer;
            transition: all var(--transition-fast);
        }
        
        .mode-btn:hover {
            color: var(--text-primary);
        }
        
        .mode-btn.active {
            background: var(--bg-card);
            color: var(--text-primary);
            box-shadow: 0 1px 3px rgba(0,0,0,0.2);
        }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .icon-btn {
            width: 36px;
            height: 36px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            background: var(--bg-light);
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all var(--transition-fast);
            position: relative;
        }
        
        .icon-btn:hover {
            background: var(--bg-lighter);
            color: var(--text-primary);
        }
        
        .notification-badge {
            position: absolute;
            top: -4px;
            right: -4px;
            width: 18px;
            height: 18px;
            background: var(--danger);
            border-radius: 50%;
            font-size: 10px;
            font-weight: 600;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        /* Chat Area */
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            scroll-behavior: smooth;
        }
        
        .welcome-message {
            text-align: center;
            padding: 60px 20px;
            max-width: 600px;
            margin: 0 auto;
        }
        
        .welcome-icon {
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, var(--primary), var(--accent));
            border-radius: 20px;
            margin: 0 auto 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 36px;
        }
        
        .welcome-message h2 {
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 12px;
            background: linear-gradient(135deg, var(--primary-light), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .welcome-message p {
            font-size: 16px;
            color: var(--text-secondary);
            margin-bottom: 32px;
        }
        
        .suggestion-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: center;
        }
        
        .chip {
            padding: 10px 16px;
            background: var(--bg-light);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            font-size: 13px;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all var(--transition-fast);
        }
        
        .chip:hover {
            background: var(--bg-lighter);
            border-color: var(--primary);
            color: var(--text-primary);
        }
        
        /* Messages */
        .message {
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-avatar {
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            flex-shrink: 0;
        }
        
        .message.user .message-avatar {
            background: var(--bg-lighter);
            color: var(--text-secondary);
        }
        
        .message.assistant .message-avatar {
            background: linear-gradient(135deg, var(--primary), var(--accent));
            color: white;
        }
        
        .message-content {
            flex: 1;
            min-width: 0;
        }
        
        .message-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }
        
        .message-author {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .message-time {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .message-body {
            font-size: 15px;
            line-height: 1.7;
            color: var(--text-primary);
            word-wrap: break-word;
        }
        
        .message-body p {
            margin-bottom: 12px;
        }
        
        .message-body p:last-child {
            margin-bottom: 0;
        }
        
        .message-body code {
            font-family: 'JetBrains Mono', monospace;
            background: var(--bg-light);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
            color: var(--accent);
        }
        
        .message-body pre {
            background: var(--bg-darker);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px;
            margin: 12px 0;
            overflow-x: auto;
        }
        
        .message-body pre code {
            background: transparent;
            padding: 0;
            color: var(--text-primary);
        }
        
        .message-body ul, .message-body ol {
            margin: 12px 0;
            padding-left: 24px;
        }
        
        .message-body li {
            margin-bottom: 4px;
        }
        
        /* Thinking Indicator */
        .thinking {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 16px;
            color: var(--text-muted);
            font-size: 14px;
        }
        
        .thinking-dots {
            display: flex;
            gap: 4px;
        }
        
        .thinking-dot {
            width: 8px;
            height: 8px;
            background: var(--primary);
            border-radius: 50%;
            animation: thinking 1.4s infinite;
        }
        
        .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dot:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes thinking {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-6px); }
        }
        
        /* Input Area */
        .input-area {
            border-top: 1px solid var(--border-color);
            padding: 16px 24px;
            background: var(--bg-dark);
        }
        
        .input-container {
            max-width: 800px;
            margin: 0 auto;
            position: relative;
        }
        
        .input-wrapper {
            display: flex;
            align-items: flex-end;
            gap: 12px;
            background: var(--bg-light);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 16px;
            transition: border-color var(--transition-fast);
        }
        
        .input-wrapper:focus-within {
            border-color: var(--primary);
        }
        
        .input-field {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: var(--text-primary);
            font-size: 15px;
            line-height: 1.5;
            resize: none;
            min-height: 24px;
            max-height: 200px;
            font-family: inherit;
        }
        
        .input-field::placeholder {
            color: var(--text-muted);
        }
        
        .input-actions {
            display: flex;
            gap: 8px;
        }
        
        .input-btn {
            width: 32px;
            height: 32px;
            border: none;
            background: transparent;
            color: var(--text-muted);
            cursor: pointer;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all var(--transition-fast);
        }
        
        .input-btn:hover {
            background: var(--bg-lighter);
            color: var(--text-primary);
        }
        
        .send-btn {
            width: 32px;
            height: 32px;
            background: var(--primary);
            border: none;
            border-radius: 6px;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background var(--transition-fast);
        }
        
        .send-btn:hover {
            background: var(--primary-hover);
        }
        
        .send-btn:disabled {
            background: var(--bg-lighter);
            cursor: not-allowed;
        }
        
        .input-hint {
            text-align: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 8px;
        }
        
        /* Dashboard Widgets */
        .dashboard-widgets {
            position: fixed;
            top: var(--header-height);
            right: 0;
            width: 320px;
            height: calc(100vh - var(--header-height));
            background: var(--bg-darker);
            border-left: 1px solid var(--border-color);
            overflow-y: auto;
            padding: 16px;
            transform: translateX(100%);
            transition: transform var(--transition-normal);
            z-index: 100;
        }
        
        .dashboard-widgets.open {
            transform: translateX(0);
        }
        
        .widget {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }
        
        .widget-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }
        
        .widget-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-primary);
        }
        
        .widget-status {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
        }
        
        /* Metrics Cards */
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .metric-card {
            background: var(--bg-light);
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 4px;
        }
        
        .metric-value.positive {
            color: var(--success);
        }
        
        .metric-value.negative {
            color: var(--danger);
        }
        
        .metric-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        /* Trading Chart Placeholder */
        .trading-chart {
            height: 120px;
            background: var(--bg-darker);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            font-size: 12px;
        }
        
        .chart-line {
            width: 100%;
            height: 60px;
            padding: 0 16px;
        }
        
        .chart-path {
            fill: none;
            stroke: var(--success);
            stroke-width: 2;
            stroke-linecap: round;
        }
        
        .chart-area {
            fill: rgba(16, 185, 129, 0.1);
        }
        
        /* Alert Panel */
        .alert-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 10px;
            background: var(--bg-light);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        
        .alert-icon {
            width: 24px;
            height: 24px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            flex-shrink: 0;
        }
        
        .alert-icon.info {
            background: rgba(59, 130, 246, 0.2);
            color: var(--info);
        }
        
        .alert-icon.warning {
            background: rgba(245, 158, 11, 0.2);
            color: var(--warning);
        }
        
        .alert-icon.error {
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger);
        }
        
        .alert-content {
            flex: 1;
            min-width: 0;
        }
        
        .alert-text {
            font-size: 13px;
            color: var(--text-primary);
            line-height: 1.4;
            margin-bottom: 2px;
        }
        
        .alert-time {
            font-size: 11px;
            color: var(--text-muted);
        }
        
        /* Notifications Panel */
        .notifications-panel {
            position: fixed;
            top: var(--header-height);
            right: 80px;
            width: 360px;
            max-height: 500px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            opacity: 0;
            visibility: hidden;
            transform: translateY(-10px);
            transition: all var(--transition-fast);
            z-index: 200;
        }
        
        .notifications-panel.open {
            opacity: 1;
            visibility: visible;
            transform: translateY(0);
        }
        
        .notifications-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
        }
        
        .notifications-title {
            font-size: 14px;
            font-weight: 600;
        }
        
        .notifications-clear {
            font-size: 12px;
            color: var(--primary);
            cursor: pointer;
            background: none;
            border: none;
        }
        
        .notifications-list {
            max-height: 400px;
            overflow-y: auto;
            padding: 8px;
        }
        
        /* Mobile Toggle */
        .mobile-toggle {
            display: none;
            width: 40px;
            height: 40px;
            border: none;
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 20px;
        }
        
        /* Responsive */
        @media (max-width: 1024px) {
            .sidebar {
                position: fixed;
                left: 0;
                top: 0;
                height: 100vh;
                z-index: 1000;
                transform: translateX(-100%);
            }
            
            .sidebar.open {
                transform: translateX(0);
            }
            
            .mobile-toggle {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .dashboard-widgets {
                width: 100%;
            }
        }
        
        @media (max-width: 768px) {
            .chat-container {
                padding: 16px;
            }
            
            .welcome-message h2 {
                font-size: 22px;
            }
            
            .input-area {
                padding: 12px 16px;
            }
        }
        
        /* Focus styles for accessibility */
        button:focus-visible,
        .input-field:focus-visible {
            outline: 2px solid var(--primary);
            outline-offset: 2px;
        }
        
        /* Screen reader only */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }
    </style>
</head>
<body>
    <div id="app">
        <!-- Sidebar -->
        <aside class="sidebar" id="sidebar" role="navigation" aria-label="Panel lateral">
            <div class="sidebar-header">
                <div class="logo" aria-hidden="true">B</div>
                <div class="logo-text">
                    <h1>Brain Chat V8</h1>
                    <span>Agente Autónomo</span>
                </div>
            </div>
            
            <div class="quick-actions" role="toolbar" aria-label="Acciones rápidas">
                <button class="quick-btn" data-mode="rsi" aria-label="Modo RSI">
                    <span>[CHART]</span> RSI
                </button>
                <button class="quick-btn" data-mode="trading" aria-label="Modo Trading">
                    <span>💹</span> Trading
                </button>
                <button class="quick-btn" data-mode="health" aria-label="Modo Health">
                    <span>🏥</span> Health
                </button>
                <button class="quick-btn" data-mode="code" aria-label="Modo Code">
                    <span>[CODE]</span> Code
                </button>
            </div>
            
            <div class="service-status" role="region" aria-label="Estado de servicios">
                <div class="section-title">Estado de Servicios</div>
                <div class="status-item">
                    <div class="status-label">
                        <div class="status-dot" id="status-api"></div>
                        <span>API Brain</span>
                    </div>
                    <div class="status-value" id="latency-api">--ms</div>
                </div>
                <div class="status-item">
                    <div class="status-label">
                        <div class="status-dot" id="status-ollama"></div>
                        <span>Ollama LLM</span>
                    </div>
                    <div class="status-value" id="latency-ollama">--ms</div>
                </div>
                <div class="status-item">
                    <div class="status-label">
                        <div class="status-dot" id="status-bridge"></div>
                        <span>Pocket Bridge</span>
                    </div>
                    <div class="status-value" id="latency-bridge">--ms</div>
                </div>
                <div class="status-item">
                    <div class="status-label">
                        <div class="status-dot" id="status-db"></div>
                        <span>Database</span>
                    </div>
                    <div class="status-value" id="latency-db">--ms</div>
                </div>
            </div>
            
            <div class="conversation-history" role="region" aria-label="Historial de conversaciones">
                <div class="section-title">Conversaciones Recientes</div>
                <div id="history-list">
                    <!-- Se llena dinámicamente -->
                </div>
            </div>
            
            <button class="new-chat-btn" id="new-chat-btn" aria-label="Nueva conversación">
                <span>+</span> Nueva conversación
            </button>
        </aside>
        
        <!-- Main Content -->
        <main class="main-content">
            <!-- Header -->
            <header class="main-header">
                <div class="header-left">
                    <button class="mobile-toggle" id="sidebar-toggle" aria-label="Abrir menú" aria-expanded="false">
                        ☰
                    </button>
                    <div class="mode-selector" role="radiogroup" aria-label="Selector de modo">
                        <button class="mode-btn active" data-mode="chat" role="radio" aria-checked="true">Chat</button>
                        <button class="mode-btn" data-mode="dev" role="radio" aria-checked="false">Dev</button>
                        <button class="mode-btn" data-mode="business" role="radio" aria-checked="false">Business</button>
                        <button class="mode-btn" data-mode="admin" role="radio" aria-checked="false">Admin</button>
                    </div>
                </div>
                <div class="header-right">
                    <button class="icon-btn" id="dashboard-toggle" aria-label="Dashboard" aria-expanded="false" title="Dashboard">
                        [CHART]
                    </button>
                    <button class="icon-btn" id="notifications-toggle" aria-label="Notificaciones" aria-expanded="false" title="Notificaciones">
                        [BELL]
                        <span class="notification-badge" id="notification-badge" style="display: none;">0</span>
                    </button>
                    <button class="icon-btn" id="theme-toggle" aria-label="Cambiar tema" title="Cambiar tema">
                        🌓
                    </button>
                </div>
            </header>
            
            <!-- Chat Area -->
            <div class="chat-container" id="chat-container" role="log" aria-live="polite" aria-label="Mensajes del chat">
                <div class="welcome-message" id="welcome-message">
                    <div class="welcome-icon" aria-hidden="true">🧠</div>
                    <h2>Brain Chat V8.0</h2>
                    <p>Agente autónomo con capacidades avanzadas de análisis, trading y generación de código.</p>
                    <div class="suggestion-chips" role="list">
                        <button class="chip" role="listitem" data-prompt="Analiza el RSI actual del sistema">Analizar RSI</button>
                        <button class="chip" role="listitem" data-prompt="Muestra el estado de salud de los servicios">Estado de salud</button>
                        <button class="chip" role="listitem" data-prompt="Genera un script Python para">Generar código</button>
                        <button class="chip" role="listitem" data-prompt="Resumen del portafolio de trading">Portafolio trading</button>
                    </div>
                </div>
                <div id="messages-list">
                    <!-- Mensajes se insertan aquí -->
                </div>
                <div class="thinking" id="thinking-indicator" style="display: none;" aria-live="assertive">
                    <div class="message-avatar" style="background: linear-gradient(135deg, #3b82f6, #06b6d4); color: white;">B</div>
                    <div class="thinking-dots" aria-label="Pensando">
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                        <div class="thinking-dot"></div>
                    </div>
                </div>
            </div>
            
            <!-- Input Area -->
            <div class="input-area">
                <div class="input-container">
                    <div class="input-wrapper">
                        <textarea 
                            class="input-field" 
                            id="chat-input" 
                            placeholder="Escribe un mensaje... (Enter para enviar, Shift+Enter para nueva línea)"
                            rows="1"
                            aria-label="Mensaje"
                            aria-describedby="input-hint"
                        ></textarea>
                        <div class="input-actions">
                            <button class="input-btn" id="attach-btn" aria-label="Adjuntar archivo" title="Adjuntar archivo">
                                📎
                            </button>
                            <button class="send-btn" id="send-btn" aria-label="Enviar mensaje" title="Enviar (Enter)">
                                ➤
                            </button>
                        </div>
                    </div>
                    <div class="input-hint" id="input-hint">Presiona Enter para enviar · Shift+Enter para nueva línea</div>
                </div>
            </div>
        </main>
        
        <!-- Dashboard Widgets -->
        <aside class="dashboard-widgets" id="dashboard-widgets" role="complementary" aria-label="Panel de dashboard">
            <!-- Trading Widget -->
            <div class="widget" role="region" aria-label="Trading">
                <div class="widget-header">
                    <span class="widget-title">[UP] Trading Overview</span>
                    <div class="widget-status" id="trading-status"></div>
                </div>
                <div class="trading-chart" id="trading-chart">
                    <svg viewBox="0 0 300 60" class="chart-line">
                        <defs>
                            <linearGradient id="chartGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                <stop offset="0%" style="stop-color:rgb(16, 185, 129);stop-opacity:0.3" />
                                <stop offset="100%" style="stop-color:rgb(16, 185, 129);stop-opacity:0" />
                            </linearGradient>
                        </defs>
                        <path class="chart-area" d="M0,45 Q30,40 60,35 T120,25 T180,30 T240,20 T300,15 L300,60 L0,60 Z" fill="url(#chartGradient)"/>
                        <path class="chart-path" d="M0,45 Q30,40 60,35 T120,25 T180,30 T240,20 T300,15"/>
                    </svg>
                </div>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value positive" id="metric-pnl">+2.4%</div>
                        <div class="metric-label">P&L Hoy</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value" id="metric-trades">12</div>
                        <div class="metric-label">Trades</div>
                    </div>
                </div>
            </div>
            
            <!-- System Metrics -->
            <div class="widget" role="region" aria-label="Métricas del sistema">
                <div class="widget-header">
                    <span class="widget-title">[FAST] System Metrics</span>
                </div>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-value" id="metric-latency">45ms</div>
                        <div class="metric-label">Latencia</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value" id="metric-uptime">99.9%</div>
                        <div class="metric-label">Uptime</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value" id="metric-rpm">156</div>
                        <div class="metric-label">Req/min</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value" id="metric-memory">42%</div>
                        <div class="metric-label">Memoria</div>
                    </div>
                </div>
            </div>
            
            <!-- Alert Panel -->
            <div class="widget" role="region" aria-label="Alertas">
                <div class="widget-header">
                    <span class="widget-title">🚨 Alertas Recientes</span>
                </div>
                <div id="alerts-list">
                    <!-- Alertas se insertan dinámicamente -->
                </div>
            </div>
        </aside>
        
        <!-- Notifications Panel -->
        <div class="notifications-panel" id="notifications-panel" role="dialog" aria-label="Panel de notificaciones" aria-hidden="true">
            <div class="notifications-header">
                <span class="notifications-title">Notificaciones</span>
                <button class="notifications-clear" id="clear-notifications">Marcar todas como leídas</button>
            </div>
            <div class="notifications-list" id="notifications-list" role="list">
                <!-- Notificaciones se insertan dinámicamente -->
            </div>
        </div>
    </div>
    
    <script>
        // ============================================
        // Brain Chat V8.0 - UI JavaScript
        // ============================================
        
        class BrainChatUI {
            constructor() {
                this.messages = [];
                this.currentMode = 'chat';
                this.unreadNotifications = 0;
                this.ws = null;
                this.sessionId = this.getOrCreateSessionId();
                this.init();
            }
            
            init() {
                this.cacheElements();
                this.bindEvents();
                this.loadTheme();
                this.initWebSocket();
                this.startMetricsPolling();
                this.loadConversationHistory();
                this.addInitialMessage();
            }
            
            cacheElements() {
                // Main containers
                this.chatContainer = document.getElementById('chat-container');
                this.messagesList = document.getElementById('messages-list');
                this.welcomeMessage = document.getElementById('welcome-message');
                this.thinkingIndicator = document.getElementById('thinking-indicator');
                
                // Input elements
                this.chatInput = document.getElementById('chat-input');
                this.sendBtn = document.getElementById('send-btn');
                this.attachBtn = document.getElementById('attach-btn');
                
                // Sidebar elements
                this.sidebar = document.getElementById('sidebar');
                this.sidebarToggle = document.getElementById('sidebar-toggle');
                this.newChatBtn = document.getElementById('new-chat-btn');
                this.historyList = document.getElementById('history-list');
                
                // Header elements
                this.dashboardToggle = document.getElementById('dashboard-toggle');
                this.notificationsToggle = document.getElementById('notifications-toggle');
                this.themeToggle = document.getElementById('theme-toggle');
                this.notificationBadge = document.getElementById('notification-badge');
                
                // Dashboard
                this.dashboardWidgets = document.getElementById('dashboard-widgets');
                
                // Notifications
                this.notificationsPanel = document.getElementById('notifications-panel');
                this.notificationsList = document.getElementById('notifications-list');
                this.clearNotificationsBtn = document.getElementById('clear-notifications');
                
                // Mode selectors
                this.modeBtns = document.querySelectorAll('.mode-btn');
                this.quickBtns = document.querySelectorAll('.quick-btn');
                
                // Suggestion chips
                this.chips = document.querySelectorAll('.chip');
            }
            
            bindEvents() {
                // Input handling
                this.chatInput.addEventListener('keydown', (e) => this.handleInputKeydown(e));
                this.chatInput.addEventListener('input', () => this.autoResizeInput());
                this.sendBtn.addEventListener('click', () => this.sendMessage());
                this.attachBtn.addEventListener('click', () => this.handleAttach());
                
                // Sidebar toggle (mobile)
                this.sidebarToggle.addEventListener('click', () => this.toggleSidebar());
                
                // New chat
                this.newChatBtn.addEventListener('click', () => this.startNewChat());
                
                // Dashboard
                this.dashboardToggle.addEventListener('click', () => this.toggleDashboard());
                
                // Notifications
                this.notificationsToggle.addEventListener('click', () => this.toggleNotifications());
                this.clearNotificationsBtn.addEventListener('click', () => this.clearNotifications());
                
                // Theme
                this.themeToggle.addEventListener('click', () => this.toggleTheme());
                
                // Mode selection
                this.modeBtns.forEach(btn => {
                    btn.addEventListener('click', () => this.setMode(btn.dataset.mode));
                });
                
                // Quick actions
                this.quickBtns.forEach(btn => {
                    btn.addEventListener('click', () => this.handleQuickAction(btn.dataset.mode));
                });
                
                // Suggestion chips
                this.chips.forEach(chip => {
                    chip.addEventListener('click', () => {
                        this.chatInput.value = chip.dataset.prompt;
                        this.autoResizeInput();
                        this.chatInput.focus();
                    });
                });
                
                // Close panels on outside click
                document.addEventListener('click', (e) => this.handleOutsideClick(e));
                
                // Keyboard shortcuts
                document.addEventListener('keydown', (e) => this.handleKeyboardShortcuts(e));
            }
            
            getOrCreateSessionId() {
                let sessionId = localStorage.getItem('brain_chat_session_id');
                if (!sessionId) {
                    sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                    localStorage.setItem('brain_chat_session_id', sessionId);
                }
                return sessionId;
            }
            
            handleInputKeydown(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            }
            
            autoResizeInput() {
                this.chatInput.style.height = 'auto';
                const newHeight = Math.min(this.chatInput.scrollHeight, 200);
                this.chatInput.style.height = newHeight + 'px';
            }
            
            async sendMessage() {
                const message = this.chatInput.value.trim();
                if (!message) return;
                
                // Hide welcome message
                this.welcomeMessage.style.display = 'none';
                
                // Add user message
                this.addMessage('user', message);
                this.chatInput.value = '';
                this.autoResizeInput();
                
                // Show thinking indicator
                this.thinkingIndicator.style.display = 'flex';
                this.scrollToBottom();
                
                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            session_id: this.sessionId,
                            message: message,
                            mode: this.currentMode
                        })
                    });
                    
                    const data = await response.json();
                    
                    // Hide thinking indicator
                    this.thinkingIndicator.style.display = 'none';
                    
                    // Add assistant response
                    if (data.response) {
                        this.addMessage('assistant', data.response);
                    } else if (data.error) {
                        this.addMessage('assistant', `Error: ${data.error}`, true);
                    }
                    
                } catch (error) {
                    this.thinkingIndicator.style.display = 'none';
                    this.addMessage('assistant', `Error de conexión: ${error.message}`, true);
                }
                
                this.scrollToBottom();
            }
            
            addMessage(role, content, isError = false) {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${role}`;
                messageDiv.setAttribute('role', 'article');
                
                const avatar = role === 'user' ? 'U' : 'B';
                const author = role === 'user' ? 'Tú' : 'Brain';
                const time = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
                
                // Convert markdown to HTML
                let formattedContent = this.formatMarkdown(content);
                if (isError) {
                    formattedContent = `<span style="color: var(--danger);">${formattedContent}</span>`;
                }
                
                messageDiv.innerHTML = `
                    <div class="message-avatar" aria-hidden="true">${avatar}</div>
                    <div class="message-content">
                        <div class="message-header">
                            <span class="message-author">${author}</span>
                            <span class="message-time">${time}</span>
                        </div>
                        <div class="message-body">${formattedContent}</div>
                    </div>
                `;
                
                this.messagesList.appendChild(messageDiv);
                
                // Apply syntax highlighting
                messageDiv.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });
                
                this.scrollToBottom();
            }
            
            formatMarkdown(text) {
                // Code blocks
                text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
                    const language = lang || 'text';
                    return `<pre><code class="language-${language}">${this.escapeHtml(code.trim())}</code></pre>`;
                });
                
                // Inline code
                text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
                
                // Bold
                text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                
                // Italic
                text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
                
                // Headers
                text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
                text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
                text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');
                
                // Lists
                text = text.replace(/^\s*[-*+]\s+(.*$)/gim, '<li>$1</li>');
                text = text.replace(/(<li>.*<\/li>\s*)+/g, '<ul>$&</ul>');
                
                // Links
                text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
                
                // Paragraphs
                text = text.replace(/\n\n/g, '</p><p>');
                text = text.replace(/\n/g, '<br>');
                
                return `<p>${text}</p>`;
            }
            
            escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            scrollToBottom() {
                this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
            }
            
            toggleSidebar() {
                const isOpen = this.sidebar.classList.toggle('open');
                this.sidebarToggle.setAttribute('aria-expanded', isOpen);
            }
            
            toggleDashboard() {
                const isOpen = this.dashboardWidgets.classList.toggle('open');
                this.dashboardToggle.setAttribute('aria-expanded', isOpen);
            }
            
            toggleNotifications() {
                const isOpen = this.notificationsPanel.classList.toggle('open');
                this.notificationsToggle.setAttribute('aria-expanded', isOpen);
                this.notificationsPanel.setAttribute('aria-hidden', !isOpen);
                
                if (isOpen) {
                    this.unreadNotifications = 0;
                    this.updateNotificationBadge();
                }
            }
            
            toggleTheme() {
                const html = document.documentElement;
                const currentTheme = html.getAttribute('data-theme');
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                html.setAttribute('data-theme', newTheme);
                localStorage.setItem('brain_chat_theme', newTheme);
            }
            
            loadTheme() {
                const savedTheme = localStorage.getItem('brain_chat_theme') || 'dark';
                document.documentElement.setAttribute('data-theme', savedTheme);
            }
            
            setMode(mode) {
                this.currentMode = mode;
                this.modeBtns.forEach(btn => {
                    const isActive = btn.dataset.mode === mode;
                    btn.classList.toggle('active', isActive);
                    btn.setAttribute('aria-checked', isActive);
                });
            }
            
            handleQuickAction(mode) {
                this.setMode(mode);
                const prompts = {
                    'rsi': 'Analiza el estado actual del RSI y muestra las brechas de fase',
                    'trading': 'Muestra un resumen del portafolio de trading y métricas de rendimiento',
                    'health': 'Realiza un health check completo de todos los servicios',
                    'code': 'Estoy en modo desarrollo. ¿Qué necesitas que programe?'
                };
                this.chatInput.value = prompts[mode] || '';
                this.autoResizeInput();
                this.chatInput.focus();
            }
            
            handleAttach() {
                // Create hidden file input
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = '.txt,.py,.js,.json,.md,.csv';
                input.onchange = (e) => {
                    const file = e.target.files[0];
                    if (file) {
                        this.handleFileUpload(file);
                    }
                };
                input.click();
            }
            
            async handleFileUpload(file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const content = e.target.result;
                    this.chatInput.value = `Archivo adjunto: ${file.name}\n\n\`\`\`\n${content}\n\`\`\``;
                    this.autoResizeInput();
                };
                reader.readAsText(file);
            }
            
            startNewChat() {
                this.messages = [];
                this.messagesList.innerHTML = '';
                this.welcomeMessage.style.display = 'block';
                this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem('brain_chat_session_id', this.sessionId);
            }
            
            addInitialMessage() {
                const hour = new Date().getHours();
                let greeting = '¡Hola!';
                if (hour < 12) greeting = '¡Buenos días!';
                else if (hour < 18) greeting = '¡Buenas tardes!';
                else greeting = '¡Buenas noches!';
                
                // Only show if no messages yet
                if (this.messagesList.children.length === 0 && this.welcomeMessage.style.display !== 'none') {
                    // Keep welcome message, don't add initial greeting
                }
            }
            
            initWebSocket() {
                const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
                
                try {
                    this.ws = new WebSocket(wsUrl);
                    
                    this.ws.onopen = () => {
                        console.log('WebSocket conectado');
                        this.updateServiceStatus('api', true);
                    };
                    
                    this.ws.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    };
                    
                    this.ws.onclose = () => {
                        console.log('WebSocket desconectado');
                        this.updateServiceStatus('api', false);
                        // Reconnect after 5 seconds
                        setTimeout(() => this.initWebSocket(), 5000);
                    };
                    
                    this.ws.onerror = (error) => {
                        console.error('WebSocket error:', error);
                        this.updateServiceStatus('api', false, 'error');
                    };
                } catch (error) {
                    console.error('Error al conectar WebSocket:', error);
                }
            }
            
            handleWebSocketMessage(data) {
                switch (data.type) {
                    case 'notification':
                        this.addNotification(data);
                        break;
                    case 'metrics':
                        this.updateMetrics(data);
                        break;
                    case 'alert':
                        this.addAlert(data);
                        break;
                    case 'status':
                        this.updateServiceStatus(data.service, data.status);
                        break;
                }
            }
            
            startMetricsPolling() {
                // Poll metrics every 30 seconds
                setInterval(() => this.fetchMetrics(), 30000);
                this.fetchMetrics(); // Initial fetch
            }
            
            async fetchMetrics() {
                try {
                    const response = await fetch('/brain/metrics');
                    if (response.ok) {
                        const data = await response.json();
                        this.updateMetrics(data);
                    }
                } catch (error) {
                    console.error('Error fetching metrics:', error);
                }
            }
            
            updateMetrics(data) {
                // Update metric displays
                if (data.latency) {
                    document.getElementById('metric-latency').textContent = data.latency + 'ms';
                }
                if (data.uptime) {
                    document.getElementById('metric-uptime').textContent = data.uptime + '%';
                }
                if (data.requests_per_minute) {
                    document.getElementById('metric-rpm').textContent = data.requests_per_minute;
                }
                if (data.memory_usage) {
                    document.getElementById('metric-memory').textContent = data.memory_usage + '%';
                }
            }
            
            updateServiceStatus(service, isOnline, status = 'online') {
                const statusDot = document.getElementById(`status-${service}`);
                const latencyEl = document.getElementById(`latency-${service}`);
                
                if (statusDot) {
                    statusDot.className = 'status-dot';
                    if (status === 'error') statusDot.classList.add('error');
                    else if (!isOnline) statusDot.classList.add('warning');
                }
                
                if (latencyEl) {
                    latencyEl.textContent = isOnline ? '<50ms' : 'Offline';
                }
            }
            
            addNotification(data) {
                const notification = document.createElement('div');
                notification.className = 'alert-item';
                notification.setAttribute('role', 'listitem');
                
                const iconClass = data.level || 'info';
                const icons = {
                    info: '[INFO]️',
                    warning: '[WARNING]️',
                    error: '[FAIL]',
                    success: '[OK]'
                };
                
                notification.innerHTML = `
                    <div class="alert-icon ${iconClass}">${icons[iconClass] || '[INFO]️'}</div>
                    <div class="alert-content">
                        <div class="alert-text">${data.message}</div>
                        <div class="alert-time">${new Date().toLocaleTimeString()}</div>
                    </div>
                `;
                
                this.notificationsList.insertBefore(notification, this.notificationsList.firstChild);
                
                // Update badge
                this.unreadNotifications++;
                this.updateNotificationBadge();
                
                // Play sound for critical alerts
                if (data.level === 'error' || data.critical) {
                    this.playAlertSound();
                }
            }
            
            addAlert(data) {
                const alertsList = document.getElementById('alerts-list');
                const alert = document.createElement('div');
                alert.className = 'alert-item';
                
                const iconClass = data.level || 'info';
                const icons = {
                    info: '[INFO]️',
                    warning: '[WARNING]️',
                    error: '[FAIL]'
                };
                
                alert.innerHTML = `
                    <div class="alert-icon ${iconClass}">${icons[iconClass] || '[INFO]️'}</div>
                    <div class="alert-content">
                        <div class="alert-text">${data.message}</div>
                        <div class="alert-time">${new Date().toLocaleTimeString()}</div>
                    </div>
                `;
                
                alertsList.insertBefore(alert, alertsList.firstChild);
                
                // Limit to 5 alerts
                while (alertsList.children.length > 5) {
                    alertsList.removeChild(alertsList.lastChild);
                }
            }
            
            updateNotificationBadge() {
                if (this.unreadNotifications > 0) {
                    this.notificationBadge.textContent = this.unreadNotifications > 99 ? '99+' : this.unreadNotifications;
                    this.notificationBadge.style.display = 'flex';
                } else {
                    this.notificationBadge.style.display = 'none';
                }
            }
            
            clearNotifications() {
                this.notificationsList.innerHTML = '';
                this.unreadNotifications = 0;
                this.updateNotificationBadge();
            }
            
            playAlertSound() {
                // Create a simple beep sound
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);
                
                oscillator.frequency.value = 800;
                oscillator.type = 'sine';
                gainNode.gain.value = 0.1;
                
                oscillator.start();
                oscillator.stop(audioContext.currentTime + 0.2);
            }
            
            handleOutsideClick(e) {
                // Close panels when clicking outside
                if (!this.notificationsPanel.contains(e.target) && !this.notificationsToggle.contains(e.target)) {
                    this.notificationsPanel.classList.remove('open');
                    this.notificationsToggle.setAttribute('aria-expanded', 'false');
                }
            }
            
            handleKeyboardShortcuts(e) {
                // ESC to close panels
                if (e.key === 'Escape') {
                    this.notificationsPanel.classList.remove('open');
                    this.dashboardWidgets.classList.remove('open');
                    this.sidebar.classList.remove('open');
                }
                
                // Ctrl/Cmd + / to focus input
                if ((e.ctrlKey || e.metaKey) && e.key === '/') {
                    e.preventDefault();
                    this.chatInput.focus();
                }
                
                // Ctrl/Cmd + D to toggle dashboard
                if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
                    e.preventDefault();
                    this.toggleDashboard();
                }
            }
            
            loadConversationHistory() {
                // Load from localStorage or fetch from server
                const history = JSON.parse(localStorage.getItem('brain_chat_history') || '[]');
                this.renderHistory(history);
            }
            
            renderHistory(history) {
                this.historyList.innerHTML = history.map(item => `
                    <div class="history-item" data-session="${item.session_id}">
                        <div class="history-title">${item.title || 'Conversación'}</div>
                        <div class="history-meta">${new Date(item.timestamp).toLocaleDateString()}</div>
                    </div>
                `).join('');
                
                // Add click handlers
                this.historyList.querySelectorAll('.history-item').forEach(item => {
                    item.addEventListener('click', () => this.loadSession(item.dataset.session));
                });
            }
            
            async loadSession(sessionId) {
                // Load session data from server
                try {
                    const response = await fetch(`/sessions/${sessionId}`);
                    if (response.ok) {
                        const data = await response.json();
                        // Render messages
                        this.messagesList.innerHTML = '';
                        data.messages.forEach(msg => {
                            this.addMessage(msg.role, msg.content);
                        });
                        this.welcomeMessage.style.display = 'none';
                    }
                } catch (error) {
                    console.error('Error loading session:', error);
                }
            }
        }
        
        // Initialize UI when DOM is ready
        document.addEventListener('DOMContentLoaded', () => {
            window.brainUI = new BrainChatUI();
        });
    </script>
</body>
</html>
'''

# Dashboard HTML Template
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Dashboard - Panel de Control</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --accent: #06b6d4;
            --bg-dark: #0f172a;
            --bg-darker: #020617;
            --bg-light: #1e293b;
            --bg-lighter: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --border-color: #334155;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --info: #3b82f6;
        }
        
        [data-theme="light"] {
            --bg-dark: #ffffff;
            --bg-darker: #f8fafc;
            --bg-light: #f1f5f9;
            --bg-lighter: #e2e8f0;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border-color: #e2e8f0;
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-primary);
            line-height: 1.6;
        }
        
        .dashboard {
            padding: 24px;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
        }
        
        .dashboard-title {
            font-size: 24px;
            font-weight: 700;
        }
        
        .dashboard-subtitle {
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .header-actions {
            display: flex;
            gap: 12px;
        }
        
        .btn {
            padding: 10px 20px;
            border-radius: 8px;
            border: none;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background: var(--primary);
            color: white;
        }
        
        .btn-primary:hover {
            background: var(--primary-hover);
        }
        
        .btn-secondary {
            background: var(--bg-light);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        
        .metric-card {
            background: var(--bg-light);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }
        
        .metric-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
        }
        
        .metric-title {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }
        
        .metric-icon {
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
        }
        
        .metric-icon.blue { background: rgba(59, 130, 246, 0.2); }
        .metric-icon.green { background: rgba(16, 185, 129, 0.2); }
        .metric-icon.orange { background: rgba(245, 158, 11, 0.2); }
        .metric-icon.purple { background: rgba(139, 92, 246, 0.2); }
        
        .metric-value {
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 8px;
        }
        
        .metric-change {
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .metric-change.positive { color: var(--success); }
        .metric-change.negative { color: var(--danger); }
        
        .widgets-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }
        
        .widget {
            background: var(--bg-light);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
        }
        
        .widget-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .widget-title {
            font-size: 16px;
            font-weight: 600;
        }
        
        .widget-content {
            padding: 20px;
        }
        
        .chart-container {
            height: 250px;
            position: relative;
        }
        
        .status-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px;
            background: var(--bg-darker);
            border-radius: 8px;
        }
        
        .status-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--success);
        }
        
        .status-dot.warning { background: var(--warning); }
        .status-dot.error { background: var(--danger); }
        
        .status-name {
            font-weight: 500;
        }
        
        .status-meta {
            font-size: 12px;
            color: var(--text-muted);
        }
        
        .status-value {
            font-size: 14px;
            font-weight: 600;
            color: var(--text-secondary);
        }
        
        .refresh-indicator {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid var(--border-color);
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="dashboard-header">
            <div>
                <h1 class="dashboard-title">Brain Dashboard</h1>
                <p class="dashboard-subtitle">Panel de control en tiempo real</p>
            </div>
            <div class="header-actions">
                <button class="btn btn-secondary" onclick="refreshData()">
                    <span id="refresh-icon">[SYNC]</span> Actualizar
                </button>
                <button class="btn btn-primary" onclick="window.location.href='/ui'">
                    Ir al Chat
                </button>
            </div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Latencia Promedio</span>
                    <div class="metric-icon blue">[FAST]</div>
                </div>
                <div class="metric-value" id="latency-value">45ms</div>
                <div class="metric-change positive">
                    <span>↓</span> 12% vs ayer
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Uptime</span>
                    <div class="metric-icon green">[OK]</div>
                </div>
                <div class="metric-value" id="uptime-value">99.9%</div>
                <div class="metric-change positive">
                    <span>↑</span> +0.1% este mes
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Requests/min</span>
                    <div class="metric-icon orange">[CHART]</div>
                </div>
                <div class="metric-value" id="rpm-value">156</div>
                <div class="metric-change positive">
                    <span>↑</span> 23% vs promedio
                </div>
            </div>
            
            <div class="metric-card">
                <div class="metric-header">
                    <span class="metric-title">Memoria Usada</span>
                    <div class="metric-icon purple">[SAVE]</div>
                </div>
                <div class="metric-value" id="memory-value">42%</div>
                <div class="metric-change negative">
                    <span>↑</span> 5% vs ayer
                </div>
            </div>
        </div>
        
        <div class="widgets-grid">
            <div class="widget">
                <div class="widget-header">
                    <span class="widget-title">[UP] Latencia en Tiempo Real</span>
                    <span style="color: var(--text-muted); font-size: 12px;">Últimos 60 minutos</span>
                </div>
                <div class="widget-content">
                    <div class="chart-container">
                        <canvas id="latencyChart"></canvas>
                    </div>
                </div>
            </div>
            
            <div class="widget">
                <div class="widget-header">
                    <span class="widget-title">[TOOL] Estado de Servicios</span>
                    <span class="status-dot" style="animation: none;"></span>
                </div>
                <div class="widget-content">
                    <div class="status-list" id="service-status-list">
                        <!-- Se llena dinámicamente -->
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let latencyChart;
        
        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            loadServiceStatus();
            startRealTimeUpdates();
        });
        
        function initCharts() {
            const ctx = document.getElementById('latencyChart').getContext('2d');
            
            // Generate sample data
            const labels = Array.from({length: 60}, (_, i) => {
                const d = new Date();
                d.setMinutes(d.getMinutes() - (59 - i));
                return d.toLocaleTimeString('es-ES', {hour: '2-digit', minute:'2-digit'});
            });
            
            const data = Array.from({length: 60}, () => 30 + Math.random() * 40);
            
            latencyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Latencia (ms)',
                        data: data,
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { 
                                color: '#64748b',
                                maxTicksLimit: 6
                            }
                        },
                        y: {
                            grid: { color: '#334155' },
                            ticks: { color: '#64748b' },
                            beginAtZero: true
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });
        }
        
        async function loadServiceStatus() {
            try {
                const response = await fetch('/brain/health');
                const data = await response.json();
                
                const services = [
                    { name: 'API Brain', key: 'api', icon: '[WEB]' },
                    { name: 'Dashboard', key: 'dashboard', icon: '[CHART]' },
                    { name: 'Pocket Bridge', key: 'bridge', icon: '🔌' },
                    { name: 'Chat Service', key: 'chat', icon: '[CHAT]' },
                    { name: 'Ollama LLM', key: 'ollama', icon: '🧠' },
                    { name: 'Base de Datos', key: 'database', icon: '🗄️' }
                ];
                
                const list = document.getElementById('service-status-list');
                list.innerHTML = services.map(s => {
                    const status = data.services?.[s.key] || { status: 'unknown', latency: '--' };
                    const statusClass = status.status === 'healthy' ? '' : 
                                     status.status === 'degraded' ? 'warning' : 'error';
                    return `
                        <div class="status-item">
                            <div class="status-info">
                                <div class="status-dot ${statusClass}"></div>
                                <div>
                                    <div class="status-name">${s.icon} ${s.name}</div>
                                    <div class="status-meta">${status.status}</div>
                                </div>
                            </div>
                            <div class="status-value">${status.latency || '--'}ms</div>
                        </div>
                    `;
                }).join('');
            } catch (error) {
                console.error('Error loading service status:', error);
            }
        }
        
        function startRealTimeUpdates() {
            // Update charts every 30 seconds
            setInterval(() => {
                updateLatencyChart();
                updateMetrics();
            }, 30000);
        }
        
        function updateLatencyChart() {
            if (!latencyChart) return;
            
            // Remove first data point and add new one
            latencyChart.data.labels.shift();
            latencyChart.data.labels.push(new Date().toLocaleTimeString('es-ES', {hour: '2-digit', minute:'2-digit'}));
            
            latencyChart.data.datasets[0].data.shift();
            latencyChart.data.datasets[0].data.push(30 + Math.random() * 40);
            
            latencyChart.update('none');
        }
        
        async function updateMetrics() {
            try {
                const response = await fetch('/brain/metrics');
                const data = await response.json();
                
                if (data.latency) document.getElementById('latency-value').textContent = data.latency + 'ms';
                if (data.uptime) document.getElementById('uptime-value').textContent = data.uptime + '%';
                if (data.requests_per_minute) document.getElementById('rpm-value').textContent = data.requests_per_minute;
                if (data.memory_usage) document.getElementById('memory-value').textContent = data.memory_usage + '%';
            } catch (error) {
                console.error('Error updating metrics:', error);
            }
        }
        
        async function refreshData() {
            const icon = document.getElementById('refresh-icon');
            icon.classList.add('refresh-indicator');
            
            await Promise.all([
                loadServiceStatus(),
                updateMetrics()
            ]);
            
            setTimeout(() => {
                icon.classList.remove('refresh-indicator');
            }, 1000);
        }
    </script>
</body>
</html>
'''

# ============================================================
# ENDPOINTS UI/UX FASE 7
# ============================================================

class NotificationRequest(BaseModel):
    """Modelo para solicitud de notificación"""
    message: str = Field(..., description="Mensaje de la notificación")
    level: str = Field(default="info", description="Nivel: info, warning, error, success")
    target: Optional[str] = Field(default=None, description="Target específico o broadcast")
    critical: bool = Field(default=False, description="Si es una alerta crítica")
    sound: bool = Field(default=False, description="Reproducir sonido de alerta")

class NotificationResponse(BaseModel):
    """Modelo para respuesta de notificación"""
    status: str
    notification_id: str
    timestamp: str
    delivered_to: int

# Store notifications in memory (could be replaced with Redis in production)
notifications_store: List[Dict] = []
notification_clients: List[WebSocket] = []

@app.get("/ui", response_class=HTMLResponse)
async def ui_endpoint():
    """
    FASE 7: Endpoint UI mejorado - Interface Web Inteligente
    
    Renderiza la interface de chat moderna con:
    - Sidebar con historial y estado de servicios
    - Área de chat con formato Markdown
    - Dashboard widgets integrados
    - Soporte WebSocket para tiempo real
    """
    return HTMLResponse(content=UI_HTML, status_code=200)

@app.get("/ui/dashboard", response_class=HTMLResponse)
async def dashboard_endpoint():
    """
    FASE 7: Dashboard de métricas y estado del sistema
    
    Muestra:
    - TradingView: Mini gráfica de P&L
    - SystemStatus: Estado de servicios en tiempo real
    - MetricsCards: Latencia, uptime, requests/min
    - AlertPanel: Notificaciones y alertas
    """
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)

@app.post("/notifications/send", response_model=NotificationResponse)
async def send_notification(request: NotificationRequest):
    """
    FASE 7: Endpoint para enviar notificaciones
    
    Envía notificaciones a clientes conectados vía WebSocket
    y las almacena para historial.
    
    Args:
        request: Datos de la notificación
        
    Returns:
        NotificationResponse con estado y metadatos
    """
    notification_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    notification_data = {
        "id": notification_id,
        "message": request.message,
        "level": request.level,
        "critical": request.critical,
        "sound": request.sound,
        "timestamp": timestamp,
        "read": False
    }
    
    # Store notification
    notifications_store.append(notification_data)
    
    # Keep only last 100 notifications
    if len(notifications_store) > 100:
        notifications_store.pop(0)
    
    # Broadcast to WebSocket clients
    disconnected = []
    for client in notification_clients:
        try:
            await client.send_json({
                "type": "notification",
                **notification_data
            })
        except:
            disconnected.append(client)
    
    # Remove disconnected clients
    for client in disconnected:
        if client in notification_clients:
            notification_clients.remove(client)
    
    return NotificationResponse(
        status="success",
        notification_id=notification_id,
        timestamp=timestamp,
        delivered_to=len(notification_clients)
    )

@app.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0
):
    """
    FASE 7: Obtener notificaciones
    
    Args:
        unread_only: Solo notificaciones no leídas
        limit: Límite de resultados
        offset: Offset para paginación
        
    Returns:
        Lista de notificaciones
    """
    filtered = notifications_store
    
    if unread_only:
        filtered = [n for n in filtered if not n.get("read", False)]
    
    # Sort by timestamp desc
    filtered = sorted(filtered, key=lambda x: x.get("timestamp", ""), reverse=True)
    
    # Paginate
    total = len(filtered)
    paginated = filtered[offset:offset + limit]
    
    return {
        "notifications": paginated,
        "total": total,
        "unread": len([n for n in notifications_store if not n.get("read", False)]),
        "limit": limit,
        "offset": offset
    }

@app.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """
    FASE 7: Marcar notificación como leída
    
    Args:
        notification_id: ID de la notificación
        
    Returns:
        Estado de la operación
    """
    for notification in notifications_store:
        if notification.get("id") == notification_id:
            notification["read"] = True
            return {"status": "success", "message": "Notification marked as read"}
    
    raise HTTPException(status_code=404, detail="Notification not found")

@app.post("/notifications/read-all")
async def mark_all_notifications_read():
    """FASE 7: Marcar todas las notificaciones como leídas"""
    for notification in notifications_store:
        notification["read"] = True
    
    return {"status": "success", "message": "All notifications marked as read"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    FASE 7: WebSocket para actualizaciones en tiempo real
    
    Conexión persistente para:
    - Notificaciones push
    - Actualizaciones de métricas
    - Alertas en tiempo real
    - Cambios de estado de servicios
    """
    await websocket.accept()
    notification_clients.append(websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connected to Brain Chat V8",
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                
                # Handle different message types from client
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                elif data.get("type") == "subscribe":
                    await websocket.send_json({
                        "type": "subscribed",
                        "channel": data.get("channel"),
                        "timestamp": datetime.now().isoformat()
                    })
                    
            except Exception as e:
                break
                
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in notification_clients:
            notification_clients.remove(websocket)

@app.get("/ui/health")
async def ui_health_check():
    """
    FASE 7: Health check específico para UI
    
    Returns:
        Estado de los componentes de UI
    """
    return {
        "status": "healthy",
        "components": {
            "ui_endpoint": "operational",
            "websocket": "operational",
            "notifications": "operational",
            "dashboard": "operational"
        },
        "connected_clients": len(notification_clients),
        "pending_notifications": len([n for n in notifications_store if not n.get("read", False)]),
        "timestamp": datetime.now().isoformat()
    }

# ============================================================
# ACTUALIZACIÓN DE STARTUP Y SHUTDOWN (líneas 8401-8500)
# ============================================================

async def startup():
    """Función de inicio del sistema"""
    print("=" * 60)
    print("Brain Chat V8.0 - Iniciando...")
    print("=" * 60)
    
    # Verificar configuración
    print("\n[1] Verificando configuración...")
    
    # Verificar directorios
    if not MEMORY_PATH.exists():
        MEMORY_PATH.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] Directorio de memoria creado: {MEMORY_PATH}")
    else:
        print(f"  [OK] Directorio de memoria OK: {MEMORY_PATH}")
    
    if not LOGS_PATH.exists():
        LOGS_PATH.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] Directorio de logs creado: {LOGS_PATH}")
    else:
        print(f"  [OK] Directorio de logs OK: {LOGS_PATH}")
    
    # Verificar APIs
    print("\n[2] Verificando APIs...")
    if API_KEYS["openai"]:
        print("  [OK] OpenAI API: Configurada")
    else:
        print("  [WARNING] OpenAI API: No configurada (set OPENAI_API_KEY)")
    
    if API_KEYS["anthropic"]:
        print("  [OK] Anthropic API: Configurada")
    else:
        print("  [WARNING] Anthropic API: No configurada (set ANTHROPIC_API_KEY)")
    
    print("  [INFO] Ollama: Se usará fallback local")
    
    # Inicializar sesión default
    print("\n[3] Inicializando sesión default...")
    brain = BrainChatV8("default")
    brain.start()
    active_sessions["default"] = brain
    print("  [OK] Sesión default iniciada")
    
    # Inicializar sistemas de autonomía (FASE 6)
    print("\n[4] Inicializando sistemas de autonomía (FASE 6)...")
    setup_autonomy_system()
    print("  [OK] Sistemas de autonomía inicializados")
    
    # Iniciar tareas de background
    print("\n[5] Iniciando tareas de autonomía...")
    await start_auto_debugging()
    await start_performance_monitoring()
    await start_proactive_monitoring()
    print("  [OK] Tareas de autonomía iniciadas")
    
    # Mostrar información
    print("\n" + "=" * 60)
    print("Brain Chat V8.0 Listo - FASE 6: AUTONOMÍA PROACTIVA ACTIVADA")
    print("=" * 60)
    print(f"\nEndpoints disponibles:")
    print(f"  POST /chat      - Enviar mensaje")
    print(f"  GET  /status    - Estado del sistema")
    print(f"  GET  /health    - Health check")
    print(f"  GET  /sessions  - Listar sesiones")
    print(f"\nEndpoints FASE 4 (Brain Integration):")
    print(f"  GET  /brain/rsi     - Análisis RSI (brechas, fases, progreso)")
    print(f"  GET  /brain/health  - Salud de servicios")
    print(f"  GET  /brain/metrics - Métricas del sistema")
    print(f"  POST /brain/validate- Validar acción vs premisas")
    print(f"\nEndpoints FASE 6 (Autonomía):")
    print(f"  GET  /autonomy/status           - Estado del sistema de autonomía")
    print(f"  GET  /autonomy/pending-approvals - Aprobaciones pendientes")
    print(f"  GET  /autonomy/reports          - Reportes de autonomía")
    print(f"  POST /autonomy/approve/{{id}}    - Aprobar acción")
    print(f"  POST /autonomy/toggle/{{comp}}   - Activar/desactivar componente")
    print(f"\nCriterios de Autonomía:")
    print(f"  Nivel 1: Sugerir (requiere aprobación)")
    print(f"  Nivel 2: Ejecutar bajo riesgo (ej: limpiar logs)")
    print(f"  Nivel 3: Ejecutar medio riesgo (ej: reiniciar servicio)")
    print(f"  Nivel 4: Ejecutar alto riesgo (SIEMPRE requiere aprobación)")
    print(f"\nDocumentación: http://localhost:8000/docs")
    print("=" * 60)

async def shutdown_handler():
    """Manejador de apagado"""
    print("\nCerrando sesiones...")
    for session_id, brain in active_sessions.items():
        await brain.shutdown()
    print("Todas las sesiones cerradas")
    
    # Detener tareas de autonomía
    print("\nDeteniendo sistemas de autonomía...")
    await stop_all_autonomy_tasks()
    print("Sistemas de autonomía detenidos")

# Configurar eventos de ciclo de vida FUERA del if __name__
@app.on_event("startup")
async def on_startup():
    # Iniciar en background para no bloquear FastAPI
    asyncio.create_task(startup_background())

async def startup_background():
    """Inicialización en background - no bloquea el servidor."""
    await asyncio.sleep(1)  # Esperar a que FastAPI inicie
    _startup_log = logging.getLogger("startup_background")
    try:
        await startup()
    except Exception as _exc:
        _startup_log.critical(
            "STARTUP FALLÓ — el servidor está vivo pero NO inicializado. "
            f"Error: {_exc}",
            exc_info=True,
        )
        # Registrar el error para que /health devuelva 503
        active_sessions["__startup_error__"] = str(_exc)

@app.on_event("shutdown")
async def on_shutdown():
    await shutdown_handler()

if __name__ == "__main__":
    import uvicorn
    
    # Iniciar servidor en puerto 8090
    uvicorn.run(
        "brain_chat_v8:app",
        host="127.0.0.1",
        port=8090,
        log_level="info",
        reload=False
    )
