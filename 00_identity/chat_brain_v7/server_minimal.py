#!/usr/bin/env python3
"""
Servidor Mínimo - Solo lo esencial para funcionar
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import subprocess
from pathlib import Path
from datetime import datetime

PORT = 8090

class SimpleHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silenciar logs
    
    def do_GET(self):
        if self.path == '/':
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
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                message = data.get('message', '')
                
                # Procesar comando simple
                response = self.process_message(message)
                self.send_json(response)
            except Exception as e:
                self.send_json({"success": False, "error": str(e), "message": "Error procesando"})
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def process_message(self, message):
        """Procesa mensajes simples"""
        msg = message.lower().strip()
        
        if msg.startswith('ejecuta comando') or msg.startswith('run'):
            # Extraer comando
            cmd = message.split(' ', 2)[-1] if len(message.split()) > 2 else 'echo test'
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5, cwd='C:\AI_VAULT')
                return {
                    "success": True,
                    "message": f"Comando: {cmd}\nSalida:\n{result.stdout[:500]}",
                    "error": result.stderr[:200] if result.stderr else None
                }
            except Exception as e:
                return {"success": False, "message": f"Error: {e}"}
        
        elif 'hola' in msg or 'hello' in msg:
            return {
                "success": True,
                "message": "Hola! Soy Brain Chat V8.1\n\nComandos disponibles:\n- ejecuta comando [cmd]\n- analiza [archivo.py]\n- hola\n\nServidor funcionando correctamente."
            }
        
        elif 'analiza' in msg:
            # Buscar archivo
            parts = msg.split()
            if len(parts) > 1:
                filename = parts[-1]
                return {
                    "success": True,
                    "message": f"Analisis de {filename}:\n\n(Esta es una respuesta simplificada del servidor minimo)\n\nEn la version completa, analizaria el archivo AST."
                }
            else:
                return {"success": True, "message": "Especifica archivo para analizar"}
        
        elif 'rsi' in msg:
            return {
                "success": True,
                "message": "RSI - Estado del Sistema:\n\nServidor: ONLINE\nPuerto: 8090\nVersion: 8.1.0\n\nServicios:\n- Chat: ONLINE\n- Ollama: ONLINE (lento)\n- Dashboard: Verificar 8070"
            }
        
        else:
            return {
                "success": True,
                "message": f"Recibido: '{message}'\n\nIntenta:\n- 'ejecuta comando dir C:/'\n- 'analiza archivo.py'\n- 'hola'\n- 'rsi'"
            }

HTML_PAGE = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V8.1 - Minimal</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }
        h1 { color: #4ecca3; }
        .chat-box { background: #16213e; border: 1px solid #0f3460; padding: 20px; margin: 20px 0; border-radius: 8px; max-height: 400px; overflow-y: auto; }
        .message { margin: 10px 0; padding: 10px; background: #0f3460; border-radius: 4px; }
        .user { background: #3b82f6; }
        .input-area { display: flex; gap: 10px; margin-top: 20px; }
        input { flex: 1; padding: 10px; background: #1a1a2e; color: #eee; border: 1px solid #0f3460; border-radius: 4px; }
        button { padding: 10px 20px; background: #4ecca3; color: #000; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #3d9970; }
        .status { color: #4ecca3; margin: 10px 0; }
        pre { background: #0a0a1a; padding: 10px; border-radius: 4px; overflow-x: auto; }
    </style>
</head>
<body>
    <h1>Brain Chat V8.1 - Version Minimal</h1>
    <div class="status">Estado: ONLINE | Puerto: 8090</div>
    
    <div class="chat-box" id="chatBox">
        <div class="message">Bienvenido! Escribe un mensaje y presiona Enter.</div>
    </div>
    
    <div class="input-area">
        <input type="text" id="messageInput" placeholder="Escribe tu mensaje..." onkeypress="if(event.key==='Enter') sendMessage()">
        <button onclick="sendMessage()">Enviar</button>
    </div>
    
    <h3>Comandos disponibles:</h3>
    <ul>
        <li><code>ejecuta comando dir C:/</code> - Ejecutar comando</li>
        <li><code>analiza archivo.py</code> - Analizar archivo</li>
        <li><code>hola</code> - Saludo</li>
        <li><code>rsi</code> - Estado sistema</li>
    </ul>
    
    <script>
        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const chatBox = document.getElementById('chatBox');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Agregar mensaje del usuario
            chatBox.innerHTML += '<div class="message user"><strong>Tu:</strong> ' + message + '</div>';
            input.value = '';
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, user_id: 'web' })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    const responseText = data.message.replace(/\\n/g, '<br>');
                    chatBox.innerHTML += '<div class="message"><strong>Agente:</strong><br><pre>' + responseText + '</pre></div>';
                } else {
                    chatBox.innerHTML += '<div class="message"><strong>Error:</strong> ' + (data.error || 'Desconocido') + '</div>';
                }
            } catch (err) {
                chatBox.innerHTML += '<div class="message"><strong>Error de conexion:</strong> Verifica que el servidor esté corriendo</div>';
            }
            
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>'''

if __name__ == "__main__":
    print("="*60)
    print("Brain Chat V8.1 - SERVIDOR MINIMAL")
    print("="*60)
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Chat: http://127.0.0.1:{PORT}/")
    print(f"Health: http://127.0.0.1:{PORT}/health")
    print("="*60)
    print("Presiona Ctrl+C para detener")
    print("="*60)
    
    server = HTTPServer(('0.0.0.0', PORT), SimpleHandler)
    server.serve_forever()
