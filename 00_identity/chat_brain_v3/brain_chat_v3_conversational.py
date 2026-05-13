"""
Brain Chat V3.1 - Servidor con Capacidad Conversacional
Combina chat conversacional (OpenAI) + Comandos directos Brain
Puerto: 8051
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Configuración
BRAIN_API = "http://127.0.0.1:8010"
ADVISOR_API = "http://127.0.0.1:8030"
PORT = 8090

# OpenAI config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Crear app
app = FastAPI(title="Brain Chat V3.1", version="3.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos
class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = "anonymous"
    room_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    reply: str
    mode: str
    error: Optional[str] = None

# Estado
chat_history: Dict[str, List[Dict]] = {}

# HTML UI
HTML_UI = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V3.1</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: #0a0f1a; 
            color: #edf2ff; 
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header { 
            background: #121936; 
            padding: 16px 24px; 
            border-bottom: 1px solid #28315e;
        }
        .header h1 { font-size: 20px; margin-bottom: 4px; }
        .header p { font-size: 12px; color: #9aa7d7; }
        .chat-container { 
            flex: 1; 
            overflow-y: auto; 
            padding: 20px;
            background: rgba(18,25,54,0.88);
        }
        .message { 
            max-width: 80%; 
            padding: 12px 16px; 
            border-radius: 12px; 
            margin-bottom: 12px;
            word-wrap: break-word;
            line-height: 1.5;
        }
        .message.user { 
            background: #20315d; 
            margin-left: auto; 
        }
        .message.assistant { 
            background: #162548; 
        }
        .message.system { 
            background: #1a3d1a; 
            font-size: 12px;
            color: #67d18d;
        }
        .message.error { 
            background: #4d1f2a; 
        }
        .input-container { 
            padding: 16px; 
            background: #121936; 
            border-top: 1px solid #28315e;
            display: flex;
            gap: 10px;
        }
        textarea { 
            flex: 1; 
            min-height: 50px; 
            max-height: 120px;
            padding: 12px; 
            border-radius: 8px; 
            border: 1px solid #28315e; 
            background: #0e1634; 
            color: #edf2ff;
            resize: vertical;
            font-family: inherit;
        }
        button { 
            padding: 12px 24px; 
            background: #2a4db6; 
            color: white; 
            border: none; 
            border-radius: 8px; 
            cursor: pointer;
            font-weight: 500;
        }
        button:hover { background: #3a5dc6; }
        .help {
            padding: 12px 24px;
            background: #0d1430;
            font-size: 12px;
            color: #9aa7d7;
            border-bottom: 1px solid #28315e;
        }
        .help code{
            background: #1a2247;
            padding: 2px 6px;
            border-radius: 4px;
            margin: 0 4px;
        }
        .meta {
            font-size: 10px;
            color: #9aa7d7;
            margin-top: 4px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Brain Chat V3.1</h1>
        <p>Chat conversacional + Comandos Brain directos</p>
    </div>
    
    <div class="help">
        <strong>Comandos especiales:</strong> 
        <code>/brain [cmd]</code> 
        <code>/advisor [msg]</code> 
        <code>/phase</code>
        <code>/pocketoption</code>
        <code>/clear</code>
        <code>/help</code>
    </div>
    
    <div class="chat-container" id="chat-log"></div>
    
    <div class="input-container">
        <textarea id="message-input" placeholder="Escribe tu mensaje..."></textarea>
        <button onclick="sendMessage()">Enviar</button>
    </div>

    <script>
        const chatLog = document.getElementById('chat-log');
        const input = document.getElementById('message-input');
        const userId = 'user_' + Date.now();
        const roomId = 'room_' + Date.now();
        
        function addMessage(role, text, meta='') {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.innerHTML = text.replace(/\\n/g, '<br>');
            if (meta) {
                div.innerHTML += '<div class="meta">' + meta + '</div>';
            }
            chatLog.appendChild(div);
            chatLog.scrollTop = chatLog.scrollHeight;
        }
        
        async function sendMessage() {
            const message = input.value.trim();
            if (!message) return;
            
            addMessage('user', message);
            input.value = '';
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message, 
                        user_id: userId,
                        room_id: roomId
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    addMessage('assistant', data.reply, 'modo: ' + data.mode);
                } else {
                    addMessage('error', 'Error: ' + (data.error || 'Desconocido'));
                }
            } catch (e) {
                addMessage('error', 'Error de conexion: ' + e.message);
            }
        }
        
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        // Mensaje de bienvenida
        addMessage('system', 'Bienvenido a Brain Chat V3.1\\nEstoy conectado al sistema Brain y listo para conversar.\\nEscribe /help para ver comandos disponibles.');
    </script>
</body>
</html>"""


async def query_openai(messages: List[Dict]) -> str:
    """Consulta OpenAI para conversación"""
    if not OPENAI_API_KEY:
        return "[Modo conversacional limitado - Sin API key de OpenAI]\\n\\nPero puedo ejecutar comandos directos usando:\\n/brain [comando]\\n/advisor [mensaje]\\n/phase\\n/pocketoption"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1000
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                return f"[Error OpenAI: {response.status_code}]"
    except Exception as e:
        return f"[Error conectando a OpenAI: {str(e)}]"


async def query_brain_api(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """Consulta Brain API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "GET":
                response = await client.get(f"{BRAIN_API}{endpoint}")
            else:
                response = await client.post(f"{BRAIN_API}{endpoint}", json=data)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def query_advisor_api(message: str) -> dict:
    """Consulta Advisor API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ADVISOR_API}/api/advisor/next",
                json={"message": message}
            )
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_special_command(message: str) -> tuple:
    """Procesa comandos especiales"""
    msg = message.strip().lower()
    
    if msg.startswith("/help"):
        return True, """Comandos disponibles:

**Chat Conversacional:**
Escribe normalmente para conversar conmigo.

**Comandos Especiales:**
/brain [comando] - Ejecuta comando directo en Brain API
/advisor [mensaje] - Consulta Advisor API
/phase - Muestra estado de fases del sistema
/pocketoption - Datos de trading desde bridge
/clear - Limpia el historial del chat
/help - Muestra esta ayuda

**Ejemplos:**
/brain get_status
/advisor Que fase estamos?
/phase
/pocketoption"""
    
    if msg.startswith("/clear"):
        return True, "[HISTORIAL_LIMPIO]"
    
    return False, None


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """UI HTML"""
    return HTMLResponse(content=HTML_UI)


@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "service": "Brain Chat V3.1",
        "version": "3.1.0",
        "features": ["conversational", "brain_commands", "advisor_integration"],
        "endpoints": ["/ui", "/api/chat", "/health"]
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "version": "3.1.0",
        "openai_configured": bool(OPENAI_API_KEY),
        "brain_api": BRAIN_API,
        "advisor_api": ADVISOR_API
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Endpoint principal de chat con capacidad conversacional
    """
    user_msg = message.message.strip()
    user_id = message.user_id or "anonymous"
    room_id = message.room_id or "default"
    
    if not user_msg:
        return ChatResponse(success=False, reply="Mensaje vacio", mode="error")
    
    # Inicializar historial si no existe
    if room_id not in chat_history:
        chat_history[room_id] = []
    
    # Procesar comandos especiales
    is_special, special_response = process_special_command(user_msg)
    if is_special:
        if special_response == "[HISTORIAL_LIMPIO]":
            chat_history[room_id] = []
            return ChatResponse(success=True, reply="Historial limpiado.", mode="system")
        return ChatResponse(success=True, reply=special_response, mode="help")
    
    # Comando /brain
    if user_msg.startswith("/brain "):
        command = user_msg[7:].strip()
        result = await query_brain_api("/api/execute", "POST", {"command": command})
        
        if result["success"]:
            reply = f"Comando ejecutado: {command}\\n\\nRespuesta:\\n{json.dumps(result['data'], indent=2, ensure_ascii=False)[:800]}"
        else:
            reply = f"Error ejecutando comando: {result.get('error', 'Desconocido')}"
        
        return ChatResponse(success=True, reply=reply, mode="brain_direct")
    
    # Comando /advisor
    if user_msg.startswith("/advisor "):
        advisor_msg = user_msg[9:].strip()
        result = await query_advisor_api(advisor_msg)
        
        if result["success"]:
            data = result["data"]
            reply = f"Advisor responde:\\n{json.dumps(data, indent=2, ensure_ascii=False)[:600]}"
        else:
            reply = f"Error en Advisor: {result.get('error', 'Desconocido')}"
        
        return ChatResponse(success=True, reply=reply, mode="advisor")
    
    # Comando /phase
    if user_msg.startswith("/phase"):
        result = await query_brain_api("/api/status", "GET")
        
        if result["success"]:
            data = result["data"]
            phases = data.get("phases", {})
            reply = "Estado de fases:\\n"
            for phase_id, phase_info in phases.items():
                status = phase_info.get("status", "unknown")
                reply += f"  • {phase_id}: {status}\\n"
            return ChatResponse(success=True, reply=reply, mode="phase_status")
        else:
            return ChatResponse(
                success=False,
                reply="No se pudo obtener estado de fases.",
                mode="phase_error"
            )
    
    # Comando /pocketoption
    if user_msg.startswith("/pocketoption"):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://127.0.0.1:8765/normalized")
                if response.status_code == 200:
                    data = response.json()
                    reply = "PocketOption Data:\\n"
                    reply += f"  Registros: {data.get('row_count', 0)}\\n"
                    if data.get('last_row'):
                        last = data['last_row']
                        reply += f"  Par: {last.get('pair', 'N/A')}\\n"
                        reply += f"  Precio: {last.get('price', 'N/A')}\\n"
                        reply += f"  Balance: ${last.get('balance_demo', 'N/A')}"
                    return ChatResponse(success=True, reply=reply, mode="pocketoption")
                else:
                    return ChatResponse(
                        success=False,
                        reply=f"PocketOption bridge error: HTTP {response.status_code}",
                        mode="pocketoption_error"
                    )
        except Exception as e:
            return ChatResponse(
                success=False,
                reply=f"No se pudo conectar a PocketOption: {str(e)}",
                mode="pocketoption_error"
            )
    
    # Mensaje normal - Chat conversacional con OpenAI
    # Agregar al historial
    chat_history[room_id].append({"role": "user", "content": user_msg})
    
    # Preparar mensajes para OpenAI con contexto del sistema
    system_message = """Eres Brain Chat V3.1, un asistente inteligente conectado al sistema AI_VAULT.

Tienes acceso a:
- Brain API (puerto 8010) - Sistema core
- Advisor API (puerto 8030) - Asesoramiento
- PocketOption Bridge (puerto 8765) - Trading

El sistema está en Fase 6.3 (Autonomía) con BL-03 activo.

Puedes ayudar al usuario con:
1. Conversación general
2. Información sobre el sistema AI_VAULT
3. Ejecutar comandos usando los comandos especiales
4. Consultar estado de fases y roadmap

Responde de manera útil, conversacional y profesional."""
    
    messages = [
        {"role": "system", "content": system_message},
        *chat_history[room_id][-10:]  # Últimos 10 mensajes para contexto
    ]
    
    # Obtener respuesta de OpenAI
    reply = await query_openai(messages)
    
    # Agregar respuesta al historial
    chat_history[room_id].append({"role": "assistant", "content": reply})
    
    # Limitar historial
    if len(chat_history[room_id]) > 20:
        chat_history[room_id] = chat_history[room_id][-20:]
    
    return ChatResponse(success=True, reply=reply, mode="conversational")


if __name__ == "__main__":
    import uvicorn
    
    print(f"""
    =========================================
      BRAIN CHAT V3.1 - CONVERSACIONAL
      Version 3.1.0
    =========================================
      Puerto: {PORT}
      Brain API: {BRAIN_API}
      Advisor API: {ADVISOR_API}
      OpenAI: {'Configurado' if OPENAI_API_KEY else 'No configurado'}
    =========================================
      Endpoints:
        - http://127.0.0.1:{PORT}/ui
        - http://127.0.0.1:{PORT}/api/chat
        - http://127.0.0.1:{PORT}/health
    =========================================
    """)
    
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
