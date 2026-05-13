#!/usr/bin/env python3
"""
Brain Chat V8.1 - VERSION SIMPLE QUE FUNCIONA GARANTIZADO
Sin complicaciones de JavaScript
"""

import asyncio
import json
import subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Optional

PORT = 8090

# HTML super simple y funcional
HTML_PAGE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Brain Chat V8.1</title>
    <style>
        body { font-family: Arial; background: #1a1a2e; color: #eee; padding: 20px; margin: 0; }
        h1 { color: #4ecca3; }
        #chat { background: #16213e; border: 1px solid #0f3460; height: 400px; overflow-y: auto; padding: 10px; margin: 10px 0; }
        .msg { margin: 5px 0; padding: 8px; background: #0f3460; border-radius: 4px; }
        .user { background: #3b82f6; }
        .system { background: #4ecca3; color: #000; }
        #inputArea { display: flex; gap: 10px; }
        #msgInput { flex: 1; padding: 10px; font-size: 16px; }
        #sendBtn { padding: 10px 20px; background: #4ecca3; border: none; cursor: pointer; font-size: 16px; }
        pre { background: #000; padding: 10px; border-radius: 4px; overflow-x: auto; }
    </style>
</head>
<body>
    <h1>Brain Chat V8.1</h1>
    <div id="status" class="system">Estado: ONLINE - Listo para usar</div>
    <div id="chat"></div>
    <div id="inputArea">
        <input type="text" id="msgInput" placeholder="Escribe tu mensaje...">
        <button id="sendBtn">Enviar</button>
    </div>
    
    <script>
        // Variables globales
        const chat = document.getElementById('chat');
        const input = document.getElementById('msgInput');
        const btn = document.getElementById('sendBtn');
        let isProcessing = false;
        
        // Función para agregar mensaje
        function addMsg(text, isUser) {
            const div = document.createElement('div');
            div.className = 'msg ' + (isUser ? 'user' : '');
            div.innerHTML = text.replace(/\\n/g, '<br>');
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }
        
        // Función principal enviar
        window.sendMsg = async function() {
            const text = input.value.trim();
            if (!text || isProcessing) return;
            
            isProcessing = true;
            input.value = '';
            addMsg('<strong>Tu:</strong> ' + text, true);
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    addMsg('<strong>Agente:</strong><pre>' + data.message + '</pre>');
                } else {
                    addMsg('<strong>Error:</strong> ' + (data.error || 'Error desconocido'));
                }
            } catch (e) {
                addMsg('<strong>Error de conexion:</strong> ' + e.message);
            }
            
            isProcessing = false;
        };
        
        // Event listeners
        btn.onclick = window.sendMsg;
        input.onkeypress = function(e) {
            if (e.key === 'Enter') window.sendMsg();
        };
        
        // Mensaje inicial
        addMsg('<strong>Sistema:</strong> Chat iniciado. Escribe un mensaje.');
        input.focus();
    </script>
</body>
</html>'''

class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path in ['/', '/ui', '/index.html']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path == '/health':
            self.send_json({"status": "healthy", "version": "8.1.0", "time": datetime.now().isoformat()})
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
                    response = self.process_message(message)
                else:
                    response = {"success": False, "message": "No data received"}
                self.send_json(response)
            except Exception as e:
                self.send_json({"success": False, "message": f"Error: {str(e)}"})
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def process_message(self, message: str) -> Dict:
        """Procesa mensajes simples"""
        msg = message.lower().strip()
        
        if 'hola' in msg or 'hi' in msg or 'hello' in msg:
            return {
                "success": True,
                "message": "Hola! Soy Brain Chat V8.1\n\nComandos:\n- 'ejecuta comando dir C:/'\n- 'analiza archivo.py'\n- 'hola'\n- 'estado'"
            }
        
        elif msg.startswith('ejecuta comando') or msg.startswith('run'):
            cmd = message.split(' ', 2)[-1] if len(message.split()) > 2 else 'echo test'
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5, cwd='C:\\AI_VAULT')
                return {
                    "success": True,
                    "message": f"Comando: {cmd}\n\nSalida:\n{result.stdout[:1000]}\n\nErrores:\n{result.stderr[:500] if result.stderr else 'Ninguno'}"
                }
            except Exception as e:
                return {"success": False, "message": f"Error ejecutando: {e}"}
        
        elif 'estado' in msg or 'status' in msg or 'rsi' in msg:
            return {
                "success": True,
                "message": "Estado del Sistema:\n- Servidor: ONLINE\n- Puerto: 8090\n- Version: 8.1.0\n- Chat: Funcionando\n\nTodo operativo!"
            }
        
        elif 'analiza' in msg or 'analizar' in msg:
            return {
                "success": True,
                "message": "Analisis:\n\nEn la version completa, analizaria el archivo AST.\n\nPara probar:\n1. Especifica archivo .py\n2. Sistema extrae funciones, clases, imports\n3. Calcula complejidad\n\nEjemplo: 'analiza agent_core.py'"
            }
        
        else:
            return {
                "success": True,
                "message": f"Mensaje recibido: '{message}'\n\nComandos disponibles:\n1. 'hola' - Saludo\n2. 'ejecuta comando [cmd]' - Ejecutar shell\n3. 'estado' - Ver estado sistema\n4. 'analiza [archivo.py]' - Analizar codigo"
            }

def run_server():
    print("="*60)
    print("BRAIN CHAT V8.1 - SERVIDOR SIMPLE")
    print("="*60)
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Chat: http://127.0.0.1:{PORT}/")
    print("="*60)
    print("Abre tu navegador y ve a la URL de arriba")
    print("="*60)
    
    server = HTTPServer(('0.0.0.0', PORT), SimpleHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido")

if __name__ == "__main__":
    run_server()
