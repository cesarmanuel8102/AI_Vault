#!/usr/bin/env python3
"""
Brain Chat V8.0 - Servidor API REST con UI Web
Agente conversacional con ejecución directa de herramientas
Autor: OpenCode
Versión: 8.0.3 (completo con UI)
"""

import asyncio
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

# Configuración
PORT = 8090
BASE_DIR = Path("C:/AI_VAULT")

# FastAPI App
app = FastAPI(
    title="Brain Chat V8.0",
    description="Agente conversacional autónomo con integración Brain Lab",
    version="8.0.3"
)

# Modelos
class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"

class ChatResponse(BaseModel):
    success: bool
    message: Optional[str]
    error: Optional[str]
    metadata: Dict

# Clase principal del Brain Chat
class BrainChatV8:
    def __init__(self):
        self.start_time = datetime.now()
        self.conversation_count = 0
        self.session_id = "default"
        self.memory = []
        
    def detect_intent(self, message: str) -> tuple:
        """Detecta intención del mensaje"""
        msg_lower = message.lower().strip()
        
        # Keywords para intenciones
        if any(kw in msg_lower for kw in ['ejecuta', 'run', 'exec', 'comando']):
            return "COMMAND", 0.99
        elif any(kw in msg_lower for kw in ['lista', 'dir', 'ls', 'muestra']):
            return "QUERY", 0.85
        elif any(kw in msg_lower for kw in ['rsi', 'brechas', 'fases']):
            return "RSI", 0.95
        elif any(kw in msg_lower for kw in ['autoconciencia', 'estado', 'health']):
            return "HEALTH", 0.90
        elif any(kw in msg_lower for kw in ['analiza', 'revisa', 'examina']):
            return "ANALYSIS", 0.88
        elif any(kw in msg_lower for kw in ['metricas', 'métricas', 'datos']):
            return "METRICS", 0.85
        elif any(kw in msg_lower for kw in ['trading', 'trade', 'portfolio']):
            return "TRADING", 0.85
        else:
            return "CONVERSATION", 0.60
    
    async def execute_tool(self, tool_name: str, **kwargs) -> Dict:
        """Ejecuta una herramienta por nombre"""
        try:
            if tool_name == "execute_command":
                return await self._execute_command(**kwargs)
            elif tool_name == "list_directory":
                return await self._list_directory(**kwargs)
            elif tool_name == "get_rsi_analysis":
                return await self._get_rsi_analysis()
            elif tool_name == "check_brain_health":
                return await self._check_brain_health()
            elif tool_name == "get_system_metrics":
                return await self._get_system_metrics()
            elif tool_name == "analyze_python_file":
                return await self._analyze_python_file(**kwargs)
            elif tool_name == "get_system_info":
                return await self._get_system_info()
            else:
                return {"success": False, "error": f"Tool {tool_name} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_command(self, command: str) -> Dict:
        """Ejecuta un comando del sistema"""
        try:
            cmd = command.strip()
            if not cmd:
                return {"success": False, "error": "Empty command"}
            
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=10,
                cwd=str(BASE_DIR)
            )
            
            stdout = result.stdout[:5000] if result.stdout else ""
            stderr = result.stderr[:2000] if result.stderr else ""
            
            return {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout (10s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _list_directory(self, path: str) -> Dict:
        """Lista contenido de un directorio"""
        try:
            dir_path = Path(path)
            if not dir_path.exists():
                return {"success": False, "error": f"Path not found: {path}"}
            
            files = []
            directories = []
            
            for item in dir_path.iterdir():
                if item.is_file():
                    files.append(item.name)
                elif item.is_dir():
                    directories.append(item.name)
            
            return {
                "success": True,
                "path": str(path),
                "files": files,
                "directories": directories,
                "file_count": len(files),
                "directory_count": len(directories)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _get_rsi_analysis(self) -> Dict:
        """Genera reporte RSI del sistema"""
        services = {
            "Chat V8.0 (8090)": await self._check_service("http://127.0.0.1:8090/health"),
            "Ollama (11434)": await self._check_service("http://127.0.0.1:11434/api/tags"),
            "Brain API (8000)": await self._check_service("http://127.0.0.1:8000/health"),
            "Dashboard (8070)": await self._check_service("http://127.0.0.1:8070"),
        }
        
        healthy = sum(1 for s in services.values() if s["healthy"])
        total = len(services)
        
        report = f"""Reporte RSI - Brain Chat V8.0
========================================
Fecha: {datetime.now().isoformat()}

SERVICIOS:
"""
        for name, status in services.items():
            icon = "✅" if status["healthy"] else "❌"
            report += f"  {icon} {name}\n"
        
        report += f"\nSalud General: {healthy}/{total} servicios ({healthy/total*100:.0f}%)\n"
        
        return {
            "success": True,
            "report": report,
            "services": services,
            "health_percentage": healthy/total*100
        }
    
    async def _check_brain_health(self) -> Dict:
        """Verifica salud del sistema Brain"""
        return {
            "success": True,
            "status": {
                "chat_v8": "running",
                "port": 8090,
                "uptime": str(datetime.now() - self.start_time),
                "conversations": self.conversation_count,
                "memory_size": len(self.memory)
            }
        }
    
    async def _get_system_metrics(self) -> Dict:
        """Obtiene métricas del sistema"""
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "success": True,
                "metrics": {
                    "cpu_percent": cpu,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2),
                    "conversations": self.conversation_count
                }
            }
        except:
            return {
                "success": True,
                "metrics": {
                    "cpu_percent": 0,
                    "memory_percent": 0,
                    "conversations": self.conversation_count
                }
            }
    
    async def _analyze_python_file(self, file_path: str) -> Dict:
        """Analiza un archivo Python"""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            imports = [line.strip() for line in lines if line.strip().startswith(('import ', 'from '))]
            functions = [line.strip() for line in lines if line.strip().startswith('def ')]
            classes = [line.strip() for line in lines if line.strip().startswith('class ')]
            
            return {
                "success": True,
                "file": str(path),
                "lines": len(lines),
                "imports": len(imports),
                "functions": len(functions),
                "classes": len(classes),
                "import_list": imports[:10],
                "function_list": functions[:10],
                "class_list": classes[:10]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _get_system_info(self) -> Dict:
        """Obtiene información del sistema"""
        import platform
        return {
            "success": True,
            "info": {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "node": platform.node()
            }
        }
    
    async def _check_service(self, url: str) -> Dict:
        """Verifica si un servicio está activo"""
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return {"healthy": True, "status_code": response.status}
        except:
            return {"healthy": False, "status_code": None}
    
    async def process_message(self, message: str, user_id: str = "anonymous") -> Dict:
        """Procesa un mensaje del usuario"""
        start_time = datetime.now()
        self.conversation_count += 1
        
        intent, confidence = self.detect_intent(message)
        
        self.memory.append({
            "role": "user",
            "content": message,
            "intent": intent,
            "timestamp": datetime.now().isoformat()
        })
        
        tool_result = None
        tool_name = None
        
        if intent == "COMMAND":
            match = re.search(r'(?:ejecuta|run|exec|comando)\s*:?\s*(.+)', message, re.IGNORECASE)
            if match:
                cmd = match.group(1).strip()
                tool_result = await self.execute_tool("execute_command", command=cmd)
                tool_name = "execute_command"
        
        elif intent == "QUERY":
            match = re.search(r'(?:lista|dir|ls|muestra)\s+(?:directorio|folder|path)?\s*:?\s*([A-Z]:[/\\]\S*)', message, re.IGNORECASE)
            if match:
                path = match.group(1).replace('/', '\\')
                tool_result = await self.execute_tool("list_directory", path=path)
                tool_name = "list_directory"
            else:
                tool_result = await self.execute_tool("list_directory", path="C:/AI_VAULT")
                tool_name = "list_directory"
        
        elif intent == "RSI":
            tool_result = await self.execute_tool("get_rsi_analysis")
            tool_name = "get_rsi_analysis"
        
        elif intent == "HEALTH":
            tool_result = await self.execute_tool("check_brain_health")
            tool_name = "check_brain_health"
        
        elif intent == "METRICS":
            tool_result = await self.execute_tool("get_system_metrics")
            tool_name = "get_system_metrics"
        
        elif intent == "ANALYSIS":
            match = re.search(r'(?:analiza|revisa|examina)\s+(?:archivo|file)?\s*:?\s*(\S+\.py)', message, re.IGNORECASE)
            if match:
                filepath = match.group(1)
                tool_result = await self.execute_tool("analyze_python_file", file_path=filepath)
                tool_name = "analyze_python_file"
        
        elif intent == "TRADING":
            tool_result = await self.execute_tool("get_system_info")
            tool_name = "get_system_info"
        
        if tool_result and tool_result.get("success"):
            if tool_name == "execute_command":
                content = f"Comando ejecutado:\n{tool_result.get('stdout', '')}"
                if tool_result.get('stderr'):
                    content += f"\n[STDERR]: {tool_result['stderr']}"
            elif tool_name == "list_directory":
                content = f"Directorio: {tool_result.get('path')}\n"
                content += f"Archivos: {tool_result.get('file_count')}\n"
                content += f"Directorios: {tool_result.get('directory_count')}\n\n"
                content += "Archivos:\n" + "\n".join([f"  📄 {f}" for f in tool_result.get('files', [])[:20]])
                content += "\n\nDirectorios:\n" + "\n".join([f"  📁 {d}" for d in tool_result.get('directories', [])[:10]])
            elif tool_name == "get_rsi_analysis":
                content = tool_result.get('report', 'Reporte RSI generado')
            elif tool_name == "check_brain_health":
                status = tool_result.get('status', {})
                content = f"Estado del Sistema:\n"
                content += f"  Chat V8.0: {status.get('chat_v8', 'unknown')}\n"
                content += f"  Puerto: {status.get('port', 'unknown')}\n"
                content += f"  Uptime: {status.get('uptime', 'unknown')}\n"
                content += f"  Conversaciones: {status.get('conversations', 0)}\n"
            elif tool_name == "get_system_metrics":
                metrics = tool_result.get('metrics', {})
                content = "Métricas del Sistema:\n"
                content += f"  CPU: {metrics.get('cpu_percent', 0)}%\n"
                content += f"  Memoria: {metrics.get('memory_percent', 0)}%\n"
                content += f"  Memoria disponible: {metrics.get('memory_available_gb', 0)} GB\n"
                content += f"  Disco: {metrics.get('disk_percent', 0)}%\n"
            elif tool_name == "analyze_python_file":
                content = f"Análisis de {tool_result.get('file')}:\n"
                content += f"  Líneas: {tool_result.get('lines', 0)}\n"
                content += f"  Imports: {tool_result.get('imports', 0)}\n"
                content += f"  Funciones: {tool_result.get('functions', 0)}\n"
                content += f"  Clases: {tool_result.get('classes', 0)}\n"
                if tool_result.get('function_list'):
                    content += "\nFunciones:\n" + "\n".join([f"    {f}" for f in tool_result['function_list'][:5]])
            else:
                content = json.dumps(tool_result, indent=2)
            
            self.memory.append({
                "role": "assistant",
                "content": content,
                "tool": tool_name,
                "timestamp": datetime.now().isoformat()
            })
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": True,
                "message": content,
                "error": None,
                "metadata": {
                    "intent": intent,
                    "intent_confidence": confidence,
                    "tool_executed": tool_name,
                    "processing_time": processing_time,
                    "timestamp": datetime.now().isoformat()
                }
            }
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return {
            "success": True,
            "message": f"Recibido: '{message}'\nIntención: {intent}\n\nSoy Brain Chat V8.0, un agente autónomo con acceso a herramientas del sistema.\n\nHerramientas disponibles:\n- Ejecutar comandos del sistema\n- Listar directorios\n- Analizar archivos Python\n- Reportes RSI\n- Métricas de sistema\n\nPrueba con: 'ejecuta comando dir C:/' o 'lista directorio C:/AI_VAULT'",
            "error": None,
            "metadata": {
                "intent": intent,
                "intent_confidence": confidence,
                "tool_executed": None,
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat()
            }
        }

# Instancia global
brain = BrainChatV8()

# HTML UI Template simplificada
UI_HTML = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V8.0</title>
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
        .header h1 { font-size: 18px; font-weight: 600; }
        .header .status {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
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
            outline: none;
        }
        .input-container input:focus { border-color: #3b82f6; }
        .input-container button {
            padding: 12px 24px;
            background: #3b82f6;
            border: none;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }
        .input-container button:hover { background: #2563eb; }
        .input-container button:disabled { opacity: 0.5; cursor: not-allowed; }
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
            transition: all 0.2s;
        }
        .suggestion:hover {
            border-color: #3b82f6;
            background: #334155;
        }
        .typing {
            display: flex;
            gap: 4px;
            padding: 12px 16px;
        }
        .typing span {
            width: 8px;
            height: 8px;
            background: #94a3b8;
            border-radius: 50%;
            animation: bounce 1.4s infinite;
        }
        .typing span:nth-child(2) { animation-delay: 0.2s; }
        .typing span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
    </style>
</head>
<body>
    <div class="header">
        <div class="status"></div>
        <h1>Brain Chat V8.0</h1>
        <span style="color: #64748b; font-size: 13px;">Agente Autónomo</span>
    </div>
    
    <div class="chat-container" id="chatContainer">
        <div class="welcome" id="welcome">
            <h2>👋 ¡Hola!</h2>
            <p>Soy Brain Chat V8.0, tu agente autónomo. Puedo ejecutar comandos,<br>
            analizar código, gestionar archivos y mucho más.</p>
            <div class="suggestions">
                <span class="suggestion" onclick="sendMessage('ejecuta comando dir C:/')">📁 Ver archivos</span>
                <span class="suggestion" onclick="sendMessage('rsi')">📊 Reporte RSI</span>
                <span class="suggestion" onclick="sendMessage('autoconciencia')">🧠 Estado</span>
                <span class="suggestion" onclick="sendMessage('analiza brain_chat_v8.py')">🔍 Analizar código</span>
            </div>
        </div>
    </div>
    
    <div class="input-container">
        <input type="text" id="messageInput" placeholder="Escribe tu mensaje..." 
               onkeypress="if(event.key==='Enter') sendMessage()">
        <button id="sendBtn" onclick="sendMessage()">Enviar</button>
    </div>
    
    <script>
        const chatContainer = document.getElementById('chatContainer');
        const messageInput = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const welcome = document.getElementById('welcome');
        
        let isTyping = false;
        
        function addMessage(role, content) {
            if (welcome) welcome.style.display = 'none';
            
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${role}`;
            
            // Convertir código entre backticks
            content = content.replace(/```(\w+)?\n?([\s\S]*?)```/g, '<pre>$2</pre>');
            content = content.replace(/`([^`]+)`/g, '<code style="background:#0f172a;padding:2px 6px;border-radius:4px;">$1</code>');
            
            msgDiv.innerHTML = content.replace(/\n/g, '<br>');
            chatContainer.appendChild(msgDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function showTyping() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message assistant typing';
            typingDiv.id = 'typing';
            typingDiv.innerHTML = '<span></span><span></span><span></span>';
            chatContainer.appendChild(typingDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function hideTyping() {
            const typing = document.getElementById('typing');
            if (typing) typing.remove();
        }
        
        async function sendMessage(text) {
            const message = text || messageInput.value.trim();
            if (!message || isTyping) return;
            
            addMessage('user', message);
            messageInput.value = '';
            isTyping = true;
            sendBtn.disabled = true;
            showTyping();
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message, user_id: 'web_user' })
                });
                
                hideTyping();
                const data = await response.json();
                
                if (data.success) {
                    addMessage('assistant', data.message);
                } else {
                    addMessage('assistant', '❌ Error: ' + (data.error || 'No se pudo procesar'));
                }
            } catch (error) {
                hideTyping();
                addMessage('assistant', '❌ Error de conexión. Verifica que el servidor esté activo.');
            } finally {
                isTyping = false;
                sendBtn.disabled = false;
            }
        }
        
        // Auto-focus input
        messageInput.focus();
    </script>
</body>
</html>
'''

# Endpoints API
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "8.0.3",
        "timestamp": datetime.now().isoformat(),
        "uptime": str(datetime.now() - brain.start_time),
        "conversations": brain.conversation_count
    }

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        response = await brain.process_message(request.message, request.user_id)
        return ChatResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/brain/health")
async def brain_health():
    try:
        result = await brain.execute_tool("get_rsi_analysis")
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "health_status": result.get("services", {}),
            "health_percentage": result.get("health_percentage", 0),
            "dashboard": result.get("report", "")
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/status")
async def status_endpoint():
    return {
        "status": "running",
        "version": "8.0.3",
        "session_id": brain.session_id,
        "uptime": str(datetime.now() - brain.start_time),
        "conversations": brain.conversation_count
    }

# Endpoints UI
@app.get("/ui", response_class=HTMLResponse)
async def ui_endpoint():
    return HTMLResponse(content=UI_HTML, status_code=200)

@app.get("/")
async def root():
    return {"message": "Brain Chat V8.0 API", "ui": "/ui", "docs": "/docs"}

if __name__ == "__main__":
    print("=" * 60)
    print("Brain Chat V8.0 - Servidor API REST + UI Web")
    print("=" * 60)
    print(f"URL Principal: http://127.0.0.1:{PORT}")
    print(f"Interfaz Web: http://127.0.0.1:{PORT}/ui")
    print(f"Health Check: http://127.0.0.1:{PORT}/health")
    print(f"API Docs: http://127.0.0.1:{PORT}/docs")
    print("=" * 60)
    
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
