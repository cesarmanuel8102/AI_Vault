#!/usr/bin/env python3
"""
Brain Chat V8.1 - SERVIDOR FUNCIONAL SIMPLIFICADO
Sin dependencias complejas, listo para usar
"""

import asyncio
import json
import subprocess
import re
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8090
BASE_DIR = Path("C:/AI_VAULT")

# HTML funcional y probado
HTML_PAGE = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V8.1</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: Arial, sans-serif; 
            background: #1a1a2e; 
            color: #eee; 
            height: 100vh; 
            display: flex; 
            flex-direction: column; 
        }
        .header { 
            background: #16213e; 
            padding: 20px; 
            border-bottom: 1px solid #0f3460;
        }
        .header h1 { color: #4ecca3; font-size: 24px; }
        .chat-box { 
            flex: 1; 
            overflow-y: auto; 
            padding: 20px; 
            background: #1a1a2e;
        }
        .message { 
            margin: 10px 0; 
            padding: 12px; 
            background: #16213e; 
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
            background: #16213e; 
            display: flex; 
            gap: 10px;
        }
        #msgInput { 
            flex: 1; 
            padding: 12px; 
            font-size: 16px; 
            background: #1a1a2e; 
            color: #eee; 
            border: 1px solid #0f3460; 
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
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Brain Chat V8.1</h1>
    </div>
    
    <div class="chat-box" id="chatBox"></div>
    
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
            div.innerHTML = text;
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
        async function sendMsg() {
            const text = msgInput.value.trim();
            if (!text) return;
            
            addMsg('<strong>Tu:</strong> ' + text, true);
            msgInput.value = '';
            sendBtn.disabled = true;
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    const msg = data.message
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/\n/g, '<br>');
                    addMsg('<strong>Agente:</strong><pre>' + msg + '</pre>', false);
                } else {
                    addMsg('<strong>Error:</strong> ' + (data.error || 'Error'), false);
                }
            } catch (e) {
                addMsg('<strong>Error:</strong> No se pudo conectar', false);
            }
            
            sendBtn.disabled = false;
        }
        
        sendBtn.onclick = sendMsg;
        msgInput.onkeypress = function(e) {
            if (e.key === 'Enter') sendMsg();
        };
        
        addMsg('<strong>Sistema:</strong> Chat listo', false);
        msgInput.focus();
    </script>
</body>
</html>'''

class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path in ['/', '/ui']:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        elif self.path == '/health':
            self.send_json({'status': 'healthy', 'version': '8.1.0'})
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/chat':
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    data = json.loads(self.rfile.read(content_length))
                    msg = data.get('message', '')
                    result = self.process_message(msg)
                    self.send_json(result)
                else:
                    self.send_json({'success': False, 'message': 'No data'})
            except Exception as e:
                self.send_json({'success': False, 'message': f'Error: {e}'})
        else:
            self.send_response(404)
            self.end_headers()
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def process_message(self, message):
        """Procesar mensajes con capacidades reales"""
        msg_lower = message.lower().strip()
        
        if 'hola' in msg_lower:
            return {
                'success': True,
                'message': 'Hola! Soy Brain Chat V8.1\n\nPuedo:\n- Ejecutar comandos\n- Analizar codigo\n- Buscar archivos\n- Procesar conversacion'
            }
        
        elif msg_lower.startswith('ejecuta comando') or msg_lower.startswith('run'):
            # Extraer comando
            cmd = message.split(' ', 2)[-1] if len(message.split()) > 2 else 'echo test'
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5, cwd=str(BASE_DIR))
                output = f"Comando: {cmd}\n\nSalida:\n{result.stdout[:1000]}"
                if result.stderr:
                    output += f"\n\nErrores:\n{result.stderr[:500]}"
                return {'success': True, 'message': output}
            except Exception as e:
                return {'success': False, 'message': f'Error ejecutando: {e}'}
        
        elif 'analiza' in msg_lower or 'analizar' in msg_lower:
            # Buscar archivo
            match = re.search(r'(\S+\.py)', message)
            if match:
                filepath = match.group(1)
                file_path = BASE_DIR / '00_identity' / 'chat_brain_v7' / filepath
                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        lines = content.split('\n')
                        funcs = [l for l in lines if l.strip().startswith('def ')]
                        classes = [l for l in lines if l.strip().startswith('class ')]
                        imports = [l for l in lines if l.strip().startswith('import ') or l.strip().startswith('from ')]
                        
                        report = f"Analisis de {filepath}:\n"
                        report += f"Lineas totales: {len(lines)}\n"
                        report += f"Funciones: {len(funcs)}\n"
                        report += f"Clases: {len(classes)}\n"
                        report += f"Imports: {len(imports)}\n\n"
                        if funcs:
                            report += "Funciones encontradas:\n"
                            for f in funcs[:10]:
                                report += f"  - {f.strip()}\n"
                        return {'success': True, 'message': report}
                    except Exception as e:
                        return {'success': False, 'message': f'Error leyendo: {e}'}
                else:
                    return {'success': False, 'message': f'Archivo no encontrado: {filepath}'}
            else:
                return {'success': True, 'message': 'Especifica archivo .py para analizar\nEjemplo: analiza brain_chat_v81_integrated.py'}
        
        elif 'busca' in msg_lower or 'find' in msg_lower:
            # Buscar patron en archivos
            pattern = re.search(r'busca\s+(\S+)', message)
            if pattern:
                search_term = pattern.group(1)
                try:
                    import glob
                    py_files = glob.glob(str(BASE_DIR / '00_identity' / 'chat_brain_v7' / '*.py'))
                    results = []
                    for f in py_files[:20]:
                        try:
                            with open(f, 'r', encoding='utf-8') as file:
                                content = file.read()
                                if search_term in content:
                                    lines = content.split('\n')
                                    for i, line in enumerate(lines, 1):
                                        if search_term in line:
                                            results.append(f"{Path(f).name}:{i}: {line.strip()[:80]}")
                                            break
                        except:
                            pass
                    
                    if results:
                        return {'success': True, 'message': f"Busqueda '{search_term}':\n" + '\n'.join(results[:15])}
                    else:
                        return {'success': True, 'message': f"No se encontro '{search_term}' en archivos"}
                except Exception as e:
                    return {'success': False, 'message': f'Error buscando: {e}'}
            else:
                return {'success': True, 'message': 'Especifica termino a buscar\nEjemplo: busca class Agent'}
        
        else:
            return {
                'success': True,
                'message': f'Mensaje: {message}\n\nIntenta:\n- "hola"\n- "ejecuta comando dir C:/"\n- "analiza archivo.py"\n- "busca class Agent"'
            }

def main():
    print("=" * 70)
    print("BRAIN CHAT V8.1 - SERVIDOR FUNCIONAL")
    print("=" * 70)
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Chat: http://127.0.0.1:{PORT}/")
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
