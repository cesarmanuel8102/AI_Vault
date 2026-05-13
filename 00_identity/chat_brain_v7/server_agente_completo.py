#!/usr/bin/env python3
"""
Brain Agent V8.1 - SERVIDOR COMPLETO CON UI FUNCIONAL
Integra todas las capacidades del agente con interfaz web
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent))

# Intentar importar agente completo
try:
    from brain_agent_v8_final import BrainAgentV8Final
    AGENTE_OK = True
    print("[OK] Agente completo importado")
except ImportError as e:
    print(f"[WARN] Agente no disponible: {e}")
    AGENTE_OK = False

PORT = 8090

# HTML FUNCIONAL - Sin complicaciones de regex
HTML_UI = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Agent V8.1</title>
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
        }
        .header h1 { font-size: 20px; color: #4ecca3; }
        .chat-box { 
            flex: 1; 
            overflow-y: auto; 
            padding: 20px; 
            background: #0f172a;
        }
        .message { 
            margin: 10px 0; 
            padding: 12px 16px; 
            background: #1e293b; 
            border-radius: 8px; 
            border-left: 3px solid #3b82f6;
        }
        .message.user { 
            background: #3b82f6; 
            color: white; 
            border-left: 3px solid #60a5fa;
        }
        .input-area { 
            padding: 20px; 
            background: #1e293b; 
            display: flex; 
            gap: 10px;
        }
        #msgInput { 
            flex: 1; 
            padding: 12px; 
            font-size: 16px; 
            background: #0f172a; 
            color: #e2e8f0; 
            border: 1px solid #334155; 
            border-radius: 6px;
        }
        #sendBtn { 
            padding: 12px 24px; 
            background: #4ecca3; 
            color: #000; 
            border: none; 
            border-radius: 6px; 
            font-size: 16px; 
            cursor: pointer;
        }
        #sendBtn:hover { background: #3d9970; }
        pre { 
            background: #000; 
            padding: 10px; 
            border-radius: 4px; 
            overflow-x: auto; 
            margin-top: 8px;
        }
        .suggestions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0;
        }
        .suggestion {
            padding: 6px 12px;
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 15px;
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
        <h1>Brain Agent V8.1 - Agente Autonomo</h1>
    </div>
    
    <div class="chat-box" id="chatBox">
        <div class="suggestions">
            <span class="suggestion" onclick="quickMsg('hola')">Hola</span>
            <span class="suggestion" onclick="quickMsg('ejecuta comando dir C:/')">Ver archivos</span>
            <span class="suggestion" onclick="quickMsg('analiza agent_core.py')">Analizar codigo</span>
            <span class="suggestion" onclick="quickMsg('rsi')">Estado sistema</span>
        </div>
    </div>
    
    <div class="input-area">
        <input type="text" id="msgInput" placeholder="Escribe tu mensaje...">
        <button id="sendBtn">Enviar</button>
    </div>
    
    <script>
        const chatBox = document.getElementById('chatBox');
        const msgInput = document.getElementById('msgInput');
        const sendBtn = document.getElementById('sendBtn');
        
        function addMsg(text, isUser) {
            const div = document.createElement('div');
            div.className = 'message ' + (isUser ? 'user' : '');
            // Convertir saltos de linea simples
            div.innerHTML = text.split('\n').join('<br>');
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
        function quickMsg(text) {
            msgInput.value = text;
            sendMsg();
        }
        
        async function sendMsg() {
            const text = msgInput.value.trim();
            if (!text) return;
            
            msgInput.value = '';
            addMsg('<strong>Tu:</strong> ' + text, true);
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, user_id: 'web' })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // Escapar HTML basico
                    let msg = data.message
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    addMsg('<strong>Agente:</strong><pre>' + msg + '</pre>', false);
                } else {
                    addMsg('<strong>Error:</strong> ' + (data.error || 'Error desconocido'), false);
                }
            } catch (e) {
                addMsg('<strong>Error:</strong> No se pudo conectar con el servidor', false);
            }
        }
        
        // Event listeners simples
        sendBtn.onclick = sendMsg;
        msgInput.onkeypress = function(e) {
            if (e.key === 'Enter') sendMsg();
        };
        
        addMsg('<strong>Sistema:</strong> Chat iniciado. Escribe un mensaje o usa las sugerencias.', false);
        msgInput.focus();
    </script>
</body>
</html>'''

class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path in ['/', '/ui', '/index.html']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(HTML_UI.encode('utf-8'))
        elif self.path == '/health':
            self.send_json({"status": "healthy", "version": "8.1.0", "agent_available": AGENTE_OK})
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/chat':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    post_data = self.rfile.read(content_length)
                    data = json.loads(post_data.decode('utf-8'))
                    message = data.get('message', '')
                    
                    if AGENTE_OK:
                        # Usar agente completo
                        asyncio.run(self.process_with_agent(message))
                    else:
                        # Fallback simple
                        response = self.process_simple(message)
                        self.send_json(response)
                else:
                    self.send_json({"success": False, "message": "No data"})
            except Exception as e:
                self.send_json({"success": False, "message": f"Error: {str(e)}"})
        else:
            self.send_response(404)
            self.end_headers()
    
    async def process_with_agent(self, message):
        """Procesa con el agente completo"""
        try:
            agent = BrainAgentV8Final("web_session")
            result = await agent.process_message(message)
            self.send_json(result)
        except Exception as e:
            self.send_json({"success": False, "message": f"Agent error: {str(e)}"})
    
    def process_simple(self, message: str) -> Dict:
        """Procesamiento simple sin agente"""
        msg = message.lower().strip()
        
        if 'hola' in msg:
            return {"success": True, "message": "Hola! Soy Brain Agent V8.1\n\nEstado: AGENTE NO CARGADO\nSe esta usando modo simple.\n\nComandos basicos disponibles."}
        elif 'ejecuta' in msg:
            return {"success": True, "message": "Ejecutando comandos requiere el agente completo.\n\nEstado: Modo simple activo."}
        else:
            return {"success": True, "message": f"Mensaje: {message}\n\nEstado: Agente cargandose...\n\nIntenta en unos segundos."}
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

def main():
    print("=" * 70)
    print("BRAIN AGENT V8.1 - SERVIDOR COMPLETO")
    print("=" * 70)
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Chat: http://127.0.0.1:{PORT}/")
    print(f"Agente disponible: {'SI' if AGENTE_OK else 'NO (modo simple)'}")
    print("=" * 70)
    print("Abre tu navegador en la URL de arriba")
    print("=" * 70)
    
    server = HTTPServer(('0.0.0.0', PORT), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido")

if __name__ == "__main__":
    main()
