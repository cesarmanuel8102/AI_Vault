#!/usr/bin/env python3
"""
Brain Agent V8.1 - SERVIDOR COMPLETO CON AGENTE REAL
Integra FastAPI + BrainAgentV8Final + Todas las herramientas
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Configuración
PORT = 8090
BASE_DIR = Path("C:/AI_VAULT")

# Importar el AGENTE COMPLETO
sys.path.insert(0, str(Path(__file__).parent))

try:
    from brain_agent_v8_final import BrainAgentV8Final
    AGENTE_OK = True
    print("[OK] Agente V8 Final importado correctamente")
except ImportError as e:
    print(f"[ERROR] No se pudo importar agente: {e}")
    AGENTE_OK = False

# Crear app FastAPI
app = FastAPI(title="Brain Agent V8.1 - COMPLETO", version="8.1.1")

# Modelos
class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"

class ChatResponse(BaseModel):
    success: bool
    message: Optional[str]
    error: Optional[str]
    metadata: Dict

# Instancia global del agente
brain_agent = None
if AGENTE_OK:
    brain_agent = BrainAgentV8Final("web_session")
    print("[OK] Agente inicializado")

# HTML con JavaScript corregido
UI_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Agent V8.1 - COMPLETO</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            background: #0f172a; 
            color: #e2e8f0; 
            height: 100vh; 
            display: flex; 
            flex-direction: column; 
        }
        .header { 
            background: #1e293b; 
            padding: 16px 24px; 
            border-bottom: 1px solid #334155;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .header h1 { font-size: 20px; color: #4ecca3; }
        .status-dot {
            width: 10px;
            height: 10px;
            background: #4ecca3;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .chat-container { 
            flex: 1; 
            overflow-y: auto; 
            padding: 24px; 
            display: flex; 
            flex-direction: column; 
            gap: 16px;
        }
        .message { 
            max-width: 80%; 
            padding: 12px 16px; 
            border-radius: 12px; 
            line-height: 1.5; 
            word-wrap: break-word;
        }
        .message.user { 
            align-self: flex-end; 
            background: #3b82f6; 
            color: white; 
        }
        .message.assistant { 
            align-self: flex-start; 
            background: #1e293b; 
            border: 1px solid #334155;
        }
        .message pre { 
            background: #0f172a; 
            padding: 12px; 
            border-radius: 8px; 
            overflow-x: auto; 
            margin-top: 8px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
        }
        .input-container { 
            padding: 16px 24px; 
            background: #1e293b; 
            border-top: 1px solid #334155; 
            display: flex; 
            gap: 12px; 
        }
        .input-container input { 
            flex: 1; 
            padding: 12px 16px; 
            border: 1px solid #334155; 
            border-radius: 8px; 
            background: #0f172a; 
            color: #e2e8f0; 
            font-size: 14px;
        }
        .input-container button { 
            padding: 12px 24px; 
            background: #3b82f6; 
            border: none; 
            border-radius: 8px; 
            color: white; 
            font-weight: 500; 
            cursor: pointer;
        }
        .input-container button:hover { background: #2563eb; }
        .welcome { 
            text-align: center; 
            padding: 40px; 
            color: #94a3b8; 
        }
        .welcome h2 { 
            color: #e2e8f0; 
            margin-bottom: 12px;
            font-size: 24px;
        }
        .suggestions { 
            display: flex; 
            flex-wrap: wrap; 
            gap: 8px; 
            justify-content: center; 
            margin-top: 20px; 
        }
        .suggestion { 
            padding: 8px 16px; 
            background: #1e293b; 
            border: 1px solid #334155; 
            border-radius: 20px; 
            font-size: 13px; 
            cursor: pointer;
        }
        .suggestion:hover { 
            border-color: #3b82f6; 
            background: #334155; 
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="status-dot"></div>
        <h1>Brain Agent V8.1 - COMPLETO</h1>
        <span style="color: #64748b; font-size: 13px;">Agente Autonomo con AST, Debug y Generacion</span>
    </div>
    
    <div class="chat-container" id="chatContainer">
        <div class="welcome" id="welcome">
            <h2>Agente de Software Engineering</h2>
            <p>Puedo analizar codigo, debuggear, generar funciones y mas.</p>
            <div class="suggestions">
                <span class="suggestion" onclick="sendQuick('hola')">Saludar</span>
                <span class="suggestion" onclick="sendQuick('analiza agent_core.py')">Analizar codigo</span>
                <span class="suggestion" onclick="sendQuick('ejecuta comando dir C:/AI_VAULT')">Ver archivos</span>
                <span class="suggestion" onclick="sendQuick('debug NameError variable no definida')">Debuggear error</span>
            </div>
        </div>
    </div>
    
    <div class="input-container">
        <input type="text" id="messageInput" placeholder="Escribe tu mensaje...">
        <button id="sendBtn">Enviar</button>
    </div>
    
    <script>
        // Variables globales
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const welcome = document.getElementById('welcome');
        let isTyping = false;
        
        // Funcion para agregar mensaje
        function addMessage(role, content) {
            if (welcome) welcome.style.display = 'none';
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message ' + role;
            msgDiv.innerHTML = content;
            chatContainer.appendChild(msgDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        // Funcion para sugerencias rapidas
        function sendQuick(text) {
            messageInput.value = text;
            sendMessage();
        }
        
        // Funcion principal enviar mensaje
        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message || isTyping) return;
            
            addMessage('user', '<strong>Tu:</strong> ' + message);
            messageInput.value = '';
            isTyping = true;
            sendBtn.disabled = true;
            
            // Mostrar indicador de carga
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'message assistant';
            loadingDiv.id = 'loadingMsg';
            loadingDiv.innerHTML = '<strong>Agente:</strong> Procesando...';
            chatContainer.appendChild(loadingDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, user_id: 'web_user' })
                });
                
                // Quitar indicador de carga
                const loading = document.getElementById('loadingMsg');
                if (loading) loading.remove();
                
                const data = await response.json();
                
                if (data.success) {
                    // Formatear respuesta
                    let msg = data.message
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    msg = msg.replace(/\n/g, '<br>');
                    addMessage('assistant', '<strong>Agente:</strong><br><pre style="background:#0f172a;padding:10px;border-radius:4px;overflow-x:auto;">' + msg + '</pre>');
                } else {
                    addMessage('assistant', '<strong>Error:</strong> ' + (data.error || 'No se pudo procesar'));
                }
            } catch (error) {
                const loading = document.getElementById('loadingMsg');
                if (loading) loading.remove();
                addMessage('assistant', '<strong>Error:</strong> No se pudo conectar con el servidor');
            } finally {
                isTyping = false;
                sendBtn.disabled = false;
            }
        }
        
        // Event listeners
        sendBtn.onclick = sendMessage;
        messageInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
        
        // Mensaje inicial
        addMessage('assistant', '<strong>Sistema:</strong> Agente V8.1 listo. Hazme preguntas sobre codigo, errores, o pideme que genere funciones.');
        messageInput.focus();
    </script>
</body>
</html>
"""

# Endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=UI_HTML)

@app.get("/ui", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(content=UI_HTML)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "8.1.1",
        "agent_available": AGENTE_OK,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint de chat que usa el AGENTE COMPLETO"""
    if not AGENTE_OK or not brain_agent:
        return ChatResponse(
            success=False,
            message="Agente no disponible. Verificar imports.",
            error="Agent not initialized",
            metadata={}
        )
    
    try:
        # USAR EL AGENTE COMPLETO - esto ejecuta herramientas reales
        result = await brain_agent.process_message(request.message, request.user_id)
        return ChatResponse(**result)
    except Exception as e:
        return ChatResponse(
            success=False,
            message=f"Error: {str(e)}",
            error=str(e),
            metadata={}
        )

if __name__ == "__main__":
    print("=" * 70)
    print("BRAIN AGENT V8.1 - SERVIDOR COMPLETO")
    print("=" * 70)
    print(f"Estado Agente: {'OK' if AGENTE_OK else 'ERROR'}")
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Chat: http://127.0.0.1:{PORT}/ui")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=PORT)
