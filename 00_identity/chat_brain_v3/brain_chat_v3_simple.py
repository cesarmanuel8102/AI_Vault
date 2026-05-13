"""
Brain Chat V3 - Servidor Simplificado
Puerto: 8050
Funcionalidad: Chat con conexión directa a Brain API
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

# Configuración
BRAIN_API = "http://127.0.0.1:8010"
ADVISOR_API = "http://127.0.0.1:8030"
PORT = 8051

# Logging simple
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Crear app
app = FastAPI(title="Brain Chat V3", version="3.0.0")

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

class ChatResponse(BaseModel):
    success: bool
    reply: str
    mode: str
    error: Optional[str] = None

# Estado simple
chat_sessions: Dict[str, Any] = {}

# HTML UI simplificado
HTML_UI = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V3</title>
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
        }
        .message.user { 
            background: #20315d; 
            margin-left: auto; 
        }
        .message.assistant { 
            background: #162548; 
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
        }
        button { 
            padding: 12px 24px; 
            background: #2a4db6; 
            color: white; 
            border: none; 
            border-radius: 8px; 
            cursor: pointer;
        }
        button:hover { background: #3a5dc6; }
        .help {
            padding: 12px 24px;
            background: #0d1430;
            font-size: 12px;
            color: #9aa7d7;
        }
        .help code {
            background: #1a2247;
            padding: 2px 6px;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Brain Chat V3</h1>
        <p>Consola de ejecucion inteligente - Conectado a Brain API</p>
    </div>
    
    <div class="help">
        <strong>Comandos especiales:</strong> 
        <code>/brain [comando]</code> 
        <code>/phase</code> 
        <code>/advisor [msg]</code>
        <code>/pocketoption</code>
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
        
        function addMessage(role, text) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.textContent = text;
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
                    body: JSON.stringify({message: message, user_id: userId})
                });
                
                const data = await response.json();
                
                if (data.success) {
                    addMessage('assistant', data.reply);
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
    </script>
</body>
</html>"""


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
    """
    Procesa comandos especiales que comienzan con /
    Returns: (is_special, response)
    """
    msg = message.strip().lower()
    
    if msg.startswith("/help"):
        return True, """Comandos disponibles:
/brain [comando] - Ejecuta comando en Brain API
/advisor [mensaje] - Consulta Advisor API
/phase - Muestra estado de fases
/pocketoption - Datos de trading
/clear - Limpia el chat
/help - Muestra esta ayuda"""
    
    if msg.startswith("/clear"):
        return True, "[CHAT_LIMPIO]"
    
    return False, None


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    """UI HTML"""
    return HTMLResponse(content=HTML_UI)


@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "service": "Brain Chat V3",
        "version": "3.0.0",
        "endpoints": ["/ui", "/api/chat", "/health"]
    }


@app.get("/health")
async def health():
    """Health check"""
    # Verificar conexiones
    brain_ok = False
    advisor_ok = False
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            brain_resp = await client.get(f"{BRAIN_API}/health")
            brain_ok = brain_resp.status_code == 200
    except:
        pass
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            advisor_resp = await client.get(f"{ADVISOR_API}/health")
            advisor_ok = advisor_resp.status_code == 200
    except:
        pass
    
    return {
        "status": "healthy",
        "version": "3.0.0",
        "connections": {
            "brain_api": brain_ok,
            "advisor_api": advisor_ok
        }
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """
    Endpoint principal de chat
    """
    user_msg = message.message.strip()
    
    if not user_msg:
        return ChatResponse(success=False, reply="Mensaje vacio", mode="error")
    
    # Procesar comandos especiales
    is_special, special_response = process_special_command(user_msg)
    if is_special:
        return ChatResponse(success=True, reply=special_response, mode="special")
    
    # Comando /brain - Ejecutar directamente en Brain API
    if user_msg.startswith("/brain "):
        command = user_msg[7:].strip()
        result = await query_brain_api(f"/api/execute", "POST", {"command": command})
        
        if result["success"]:
            return ChatResponse(
                success=True, 
                reply=f"Brain ejecuto: {command}\\nRespuesta: {json.dumps(result['data'], indent=2)}",
                mode="brain_direct"
            )
        else:
            return ChatResponse(
                success=False,
                reply=f"Error ejecutando en Brain: {result.get('error', 'Desconocido')}",
                mode="brain_error"
            )
    
    # Comando /advisor - Consultar Advisor
    if user_msg.startswith("/advisor "):
        advisor_msg = user_msg[9:].strip()
        result = await query_advisor_api(advisor_msg)
        
        if result["success"]:
            data = result["data"]
            reply = f"Advisor responde:\\n{json.dumps(data, indent=2)[:500]}"
            return ChatResponse(success=True, reply=reply, mode="advisor")
        else:
            return ChatResponse(
                success=False,
                reply=f"Error en Advisor: {result.get('error', 'Desconocido')}",
                mode="advisor_error"
            )
    
    # Comando /phase - Obtener estado de fases
    if user_msg.startswith("/phase"):
        result = await query_brain_api("/api/status", "GET")
        
        if result["success"]:
            data = result["data"]
            phases = data.get("phases", {})
            reply = "Estado de fases:\\n"
            for phase_id, phase_info in phases.items():
                status = phase_info.get("status", "unknown")
                reply += f"  {phase_id}: {status}\\n"
            return ChatResponse(success=True, reply=reply, mode="phase_status")
        else:
            return ChatResponse(
                success=False,
                reply="No se pudo obtener estado de fases. Brain API no responde.",
                mode="phase_error"
            )
    
    # Comando /pocketoption - Obtener datos de trading
    if user_msg.startswith("/pocketoption"):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://127.0.0.1:8765/normalized")
                if response.status_code == 200:
                    data = response.json()
                    reply = f"PocketOption Data:\\n"
                    reply += f"  Registros: {data.get('row_count', 0)}\\n"
                    if data.get('last_row'):
                        last = data['last_row']
                        reply += f"  Par: {last.get('pair', 'N/A')}\\n"
                        reply += f"  Precio: {last.get('price', 'N/A')}\\n"
                        reply += f"  Balance: ${last.get('balance_demo', 'N/A')}\\n"
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
    
    # Mensaje normal - Consultar Advisor API
    result = await query_advisor_api(user_msg)
    
    if result["success"]:
        data = result["data"]
        # Extraer respuesta del advisor
        reply = data.get("reply", "No reply from advisor")
        if not reply:
            reply = json.dumps(data, indent=2)[:500]
        
        return ChatResponse(success=True, reply=reply, mode="normal")
    else:
        # Fallback: respuesta local
        return ChatResponse(
            success=True,
            reply=f"[Mensaje recibido: {user_msg}]\\n\\nEstoy conectado al sistema Brain. Usa /help para ver comandos disponibles.",
            mode="local_fallback"
        )


if __name__ == "__main__":
    import uvicorn
    
    print(f"""
    =========================================
      BRAIN CHAT V3 SERVER
      Version 3.0.0
    =========================================
      Puerto: {PORT}
      Brain API: {BRAIN_API}
      Advisor API: {ADVISOR_API}
    =========================================
      Endpoints:
        - http://127.0.0.1:{PORT}/ui
        - http://127.0.0.1:{PORT}/api/chat
        - http://127.0.0.1:{PORT}/health
    =========================================
    """)
    
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
