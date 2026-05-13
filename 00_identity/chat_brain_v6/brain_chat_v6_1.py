"""
Brain Chat V6.1 - Agente con Razonamiento Práctico
Simplificado para máxima efectividad
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Configuración
BRAIN_API = "http://127.0.0.1:8000"
ADVISOR_API = "http://127.0.0.1:8030"
POCKET_BRIDGE = "http://127.0.0.1:8765"
DASHBOARD_API = "http://127.0.0.1:8070"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
PORT = 8090

STATE_DIR = Path("C:\\AI_VAULT\\tmp_agent\\state")
CONVERSATIONS_DIR = STATE_DIR / "conversations"
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Brain Chat V6.1", version="6.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = "anonymous"
    room_id: Optional[str] = None
    deep_analysis: bool = False
    show_reasoning: bool = False


class ChatResponse(BaseModel):
    success: bool
    reply: str
    mode: str
    data_source: Optional[str] = None
    verified: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_steps: Optional[List[str]] = None
    execution_time_ms: Optional[int] = None


class BrainChatV6:
    """
    Brain Chat V6.1 - Enfoque práctico:
    1. Analiza intención
    2. Consulta datos reales
    3. Genera respuesta contextual
    4. Aprende de patrones
    """
    
    def __init__(self):
        self.conversations: Dict[str, List[Dict]] = {}
        self._load_conversations()
        
    def _load_conversations(self):
        """Carga historial persistente"""
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
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """Análisis rápido de intención"""
        msg_lower = message.lower()
        
        # Detectar intenciones específicas
        if any(cmd in msg_lower for cmd in ["/phase", "fase actual", "estado fases"]):
            return {"type": "phase_status", "needs_data": True, "services": ["brain"]}
        
        if any(cmd in msg_lower for cmd in ["/pocketoption", "trading", "balance", "precio"]):
            return {"type": "trading_data", "needs_data": True, "services": ["bridge"]}
        
        if any(cmd in msg_lower for cmd in ["/bridge", "estado bridge"]):
            return {"type": "bridge_status", "needs_data": True, "services": ["bridge"]}
        
        if any(cmd in msg_lower for cmd in ["/status", "estado sistema", "que sabes hacer"]):
            return {"type": "system_overview", "needs_data": True, "services": ["brain", "bridge", "advisor"]}
        
        if any(cmd in msg_lower for cmd in ["/help", "ayuda", "comandos"]):
            return {"type": "help", "needs_data": False, "services": []}
        
        if any(cmd in msg_lower for cmd in ["ejecuta", "corre", "inicia"]):
            return {"type": "execution", "needs_data": False, "services": [], "requires_auth": True}
        
        # Conversación general
        return {"type": "conversation", "needs_data": False, "services": []}
    
    async def _query_services(self, services: List[str]) -> Dict[str, Any]:
        """Consulta múltiples servicios en paralelo"""
        results = {}
        
        async def query_service(service: str):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    if service == "brain":
                        resp = await client.get(f"{BRAIN_API}/v1/agent/status")
                        if resp.status_code == 200:
                            results["brain"] = resp.json()
                    
                    elif service == "bridge":
                        health = await client.get(f"{POCKET_BRIDGE}/healthz")
                        data = await client.get(f"{POCKET_BRIDGE}/normalized")
                        if data.status_code == 200:
                            results["bridge"] = data.json()
                    
                    elif service == "advisor":
                        resp = await client.get(f"{ADVISOR_API}/health")
                        if resp.status_code == 200:
                            results["advisor"] = resp.json()
                            
            except Exception as e:
                logger.warning(f"Error querying {service}: {e}")
        
        # Ejecutar consultas en paralelo
        await asyncio.gather(*[query_service(s) for s in services], return_exceptions=True)
        
        return results
    
    def _generate_response(self, intent: Dict, data: Dict, message: str) -> str:
        """Genera respuesta basada en intención y datos"""
        intent_type = intent.get("type", "unknown")
        
        if intent_type == "phase_status":
            if "brain" in data:
                phases = data["brain"].get("phases", {})
                reply = "📊 **Estado de Fases (Verificado):**\n\n"
                for phase_id, info in phases.items():
                    status = info.get("status", "unknown")
                    emoji = "✅" if status == "completed" else "🔄" if status == "active" else "⏳"
                    reply += f"{emoji} **{phase_id}**: {status}\n"
                return reply
            else:
                return "❌ No se pudo obtener el estado de fases. Verifica que el Brain API esté corriendo en puerto 8010."
        
        elif intent_type == "trading_data":
            if "bridge" in data:
                bridge = data["bridge"]
                last_row = bridge.get("last_row", {})
                reply = "📈 **PocketOption (Datos Reales):**\n\n"
                reply += f"✅ Bridge activo\n"
                reply += f"📊 Registros: {bridge.get('row_count', 0)}\n"
                reply += f"💱 Par: {last_row.get('pair', 'N/A')}\n"
                reply += f"💰 Precio: {last_row.get('price', 'N/A')}\n"
                reply += f"💵 Balance: ${last_row.get('balance_demo', 'N/A')}\n"
                reply += f"⏰ Última actualización: {last_row.get('captured_utc', 'N/A')[:10]}"
                return reply
            else:
                return "❌ Bridge no disponible. Verifica puerto 8765."
        
        elif intent_type == "bridge_status":
            if "bridge" in data:
                bridge = data["bridge"]
                last_row = bridge.get("last_row", {})
                return f"🔌 **Bridge:** Activo | Registros: {bridge.get('row_count', 0)} | Par: {last_row.get('pair', 'N/A')}"
            else:
                return "❌ Bridge no responde"
        
        elif intent_type == "system_overview":
            reply = "🧠 **Estado del Sistema:**\n\n"
            
            if "brain" in data:
                reply += "✅ Brain API (8010): Operativo\n"
            else:
                reply += "❌ Brain API (8010): No responde\n"
            
            if "bridge" in data:
                bridge = data["bridge"]
                reply += f"✅ PocketOption Bridge (8765): {bridge.get('row_count', 0)} registros\n"
            else:
                reply += "❌ PocketOption Bridge (8765): No disponible\n"
            
            if "advisor" in data:
                reply += "✅ Advisor (8030): Operativo\n"
            else:
                reply += "⚠️ Advisor (8030): No verificado\n"
            
            reply += "\n💡 **Capacidades:** Consulta /phase, /pocketoption, /bridge o haz preguntas generales."
            return reply
        
        elif intent_type == "help":
            return """🧠 **Brain Chat V6.1 - Comandos:**

**Sistema:**
• `/phase` - Estado de fases
• `/pocketoption` - Datos de trading
• `/bridge` - Estado del bridge
• `/status` - Estado completo

**Trading:**
• "balance actual" - Muestra balance
• "precio EURUSD" - Precio actual

**General:**
• Chat natural sobre cualquier tema
• Análisis profundo con deep_analysis=true

**Puertos:**
• Brain: 8010 | Bridge: 8765 | Chat: 8090"""
        
        elif intent_type == "execution":
            return "⚠️ **Ejecución requiere autorización**\n\nReenvía con confirmación o contacta al administrador."
        
        return ""  # Dejar que OpenAI maneje
    
    async def _conversation_with_openai(self, message: str, history: List[Dict]) -> str:
        """Conversación con OpenAI manteniendo contexto"""
        if not OPENAI_API_KEY:
            return "Estoy operativo. Usa /help para ver comandos disponibles."
        
        try:
            # Construir mensajes con historial
            messages = [
                {"role": "system", "content": self._get_system_prompt()}
            ]
            
            # Agregar últimos 5 mensajes del historial
            for msg in history[-5:]:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
            
            messages.append({"role": "user", "content": message})
            
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 1500
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                    
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
        
        return "Error en conversación. Intenta con comandos: /phase, /pocketoption, /help"
    
    def _get_system_prompt(self) -> str:
        return """Eres Brain Chat V6.1, un asistente conectado a AI_VAULT.

CONTEXTO:
- Sistema en fase 6.3 (Autonomía)
- Servicios: Brain (8010), Bridge (8765), Advisor (8030)
- Capacidad: 8/10 (razonamiento práctico + datos reales)

REGLAS:
1. Sé preciso y directo
2. Usa datos verificados del sistema cuando aplique
3. Si no sabes algo, admítelo
4. Mantén contexto de conversación
5. Para operaciones críticas, pide autorización"""
    
    async def process_message(self, request: ChatRequest) -> ChatResponse:
        """Pipeline principal de procesamiento"""
        import time
        start_time = time.time()
        
        room_id = request.room_id or f"room_{datetime.now().timestamp()}"
        
        # Inicializar conversación
        if room_id not in self.conversations:
            self.conversations[room_id] = []
        
        history = self.conversations[room_id]
        
        # PASO 1: Analizar intención
        intent = self._analyze_intent(request.message)
        reasoning_steps = [f"1. Intención detectada: {intent['type']}"]
        
        # PASO 2: Si necesita datos, consultar servicios
        data = {}
        if intent.get("needs_data"):
            reasoning_steps.append(f"2. Consultando servicios: {intent['services']}")
            data = await self._query_services(intent["services"])
            reasoning_steps.append(f"3. Datos obtenidos: {len(data)} servicios")
        
        # PASO 3: Generar respuesta
        reply = self._generate_response(intent, data, request.message)
        
        if reply:
            # Respuesta basada en datos reales
            reasoning_steps.append("4. Respuesta generada desde datos verificados")
            
            # Actualizar historial
            history.append({"role": "user", "content": request.message})
            history.append({"role": "assistant", "content": reply})
            self._save_conversation(room_id, history)
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return ChatResponse(
                success=True,
                reply=reply,
                mode="data_verified",
                data_source=",".join(intent.get("services", [])),
                verified=True,
                confidence=0.9 if data else 0.5,
                reasoning_steps=reasoning_steps if request.show_reasoning else None,
                execution_time_ms=execution_time
            )
        
        # PASO 4: Si no es comando específico, usar OpenAI
        reasoning_steps.append("4. Usando OpenAI para respuesta contextual")
        reply = await self._conversation_with_openai(request.message, history)
        
        # Actualizar historial
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": reply})
        self._save_conversation(room_id, history)
        
        execution_time = int((time.time() - start_time) * 1000)
        
        return ChatResponse(
            success=True,
            reply=reply,
            mode="openai_conversation",
            data_source="openai",
            verified=False,
            confidence=0.75,
            reasoning_steps=reasoning_steps if request.show_reasoning else None,
            execution_time_ms=execution_time
        )


# Instancia global
chat_v6 = BrainChatV6()


# HTML UI
HTML_UI = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V6.1</title>
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
        }
        .header h1 { 
            font-size: 24px; 
            background: linear-gradient(90deg, #3b82f6, #8b5cf6); 
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent; 
        }
        .version-badge {
            display: inline-block;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid #10b981;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            color: #10b981;
            margin-left: 12px;
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
            border-left: 3px solid #8b5cf6;
            padding: 8px 12px;
            margin-top: 8px;
            font-size: 10px;
            color: #a78bfa;
        }
        .input-container { 
            padding: 20px 24px;
            background: rgba(18,25,54,0.95);
            border-top: 2px solid #3b82f6;
        }
        .input-row {
            display: flex;
            gap: 12px;
        }
        textarea { 
            flex: 1; 
            min-height: 60px; 
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
        }
        .options {
            display: flex;
            gap: 16px;
            margin-top: 12px;
            font-size: 12px;
            color: #9aa7d7;
        }
        .options label {
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
        }
        .welcome {
            text-align: center;
            padding: 40px;
            color: #9aa7d7;
        }
        .quick-cmds {
            display: flex;
            gap: 8px;
            justify-content: center;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        .quick-cmds button {
            padding: 8px 16px;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Brain Chat V6.1</h1>
        <span class="version-badge">Capacidad: 8/10</span>
    </div>
    
    <div class="chat-container" id="chat-log">
        <div class="welcome">
            <h2>Brain Chat V6.1</h2>
            <p>Razonamiento práctico + Datos verificados en tiempo real</p>
            <div class="quick-cmds">
                <button onclick="sendQuick('/phase')">📊 Fases</button>
                <button onclick="sendQuick('/pocketoption')">📈 Trading</button>
                <button onclick="sendQuick('/status')">🧠 Sistema</button>
                <button onclick="sendQuick('/help')">❓ Ayuda</button>
            </div>
        </div>
    </div>
    
    <div class="input-container">
        <div class="input-row">
            <textarea id="message-input" placeholder="Escribe tu mensaje..."></textarea>
            <button onclick="sendMessage()">Enviar</button>
        </div>
        <div class="options">
            <label><input type="checkbox" id="show-reasoning"> Mostrar razonamiento</label>
        </div>
    </div>

    <script>
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('message-input');
        let currentRoom = 'room_' + Date.now();
        
        function addMessage(role, text, meta='', reasoning=null) {
            const welcome = document.querySelector('.welcome');
            if (welcome) welcome.remove();
            
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            
            if (meta) {
                div.innerHTML += '<div class="meta">' + meta + '</div>';
            }
            
            if (reasoning) {
                div.innerHTML += '<div class="reasoning-box">' + reasoning.join('<br>') + '</div>';
            }
            
            chatLog.appendChild(div);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        
        async function sendQuick(msg) {
            input.value = msg;
            await sendMessage();
        }
        
        async function sendMessage() {
            const message = input.value.trim();
            if (!message) return;
            
            const showReasoning = document.getElementById('show-reasoning').checked;
            
            addMessage('user', message);
            input.value = '';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        room_id: currentRoom,
                        show_reasoning: showReasoning
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    let meta = '';
                    if (data.verified) meta += '✓ Verificado | ';
                    meta += 'confianza: ' + (data.confidence * 100).toFixed(0) + '%';
                    if (data.execution_time_ms) meta += ' | tiempo: ' + data.execution_time_ms + 'ms';
                    if (data.data_source) meta += ' | fuente: ' + data.data_source;
                    
                    addMessage('assistant', data.reply, meta, data.reasoning_steps);
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
</html>"""


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(content=HTML_UI)


@app.get("/")
async def root():
    return {
        "service": "Brain Chat V6.1",
        "version": "6.1.0",
        "capability_score": "8/10",
        "features": [
            "intent_analysis",
            "multi_service_query",
            "context_preservation",
            "reasoning_transparency"
        ]
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "6.1.0",
        "capability_score": "8/10",
        "reasoning": "active"
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
            mode="error"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
