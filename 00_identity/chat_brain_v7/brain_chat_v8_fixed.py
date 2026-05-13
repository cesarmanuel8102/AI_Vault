#!/usr/bin/env python3
"""
Brain Chat V8.0 - Servidor API REST
Agente conversacional con ejecución directa de herramientas
Autor: OpenCode
Versión: 8.0.2 (fixes aplicados)
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
from pydantic import BaseModel
import uvicorn

# Configuración
PORT = 8090
BASE_DIR = Path("C:/AI_VAULT")

# FastAPI App
app = FastAPI(
    title="Brain Chat V8.0",
    description="Agente conversacional autónomo con integración Brain Lab",
    version="8.0.2"
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
            # Limpiar y validar comando
            cmd = command.strip()
            if not cmd:
                return {"success": False, "error": "Empty command"}
            
            # Ejecutar con timeout
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
        # Verificar servicios
        services = {
            "Chat V8.0 (8090)": await self._check_service("http://127.0.0.1:8090/health"),
            "Ollama (11434)": await self._check_service("http://127.0.0.1:11434/api/tags"),
            "Brain API (8000)": await self._check_service("http://127.0.0.1:8000/health"),
            "Dashboard (8070)": await self._check_service("http://127.0.0.1:8070"),
        }
        
        # Calcular métricas
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
        
        # Detectar intención
        intent, confidence = self.detect_intent(message)
        
        # Guardar en memoria
        self.memory.append({
            "role": "user",
            "content": message,
            "intent": intent,
            "timestamp": datetime.now().isoformat()
        })
        
        # Ejecutar herramienta según intención
        tool_result = None
        tool_name = None
        
        if intent == "COMMAND":
            # Extraer comando
            match = re.search(r'(?:ejecuta|run|exec|comando)\s*:?\s*(.+)', message, re.IGNORECASE)
            if match:
                cmd = match.group(1).strip()
                tool_result = await self.execute_tool("execute_command", command=cmd)
                tool_name = "execute_command"
        
        elif intent == "QUERY":
            # Extraer path
            match = re.search(r'(?:lista|dir|ls|muestra)\s+(?:directorio|folder|path)?\s*:?\s*([A-Z]:[/\\]\S*)', message, re.IGNORECASE)
            if match:
                path = match.group(1).replace('/', '\\')
                tool_result = await self.execute_tool("list_directory", path=path)
                tool_name = "list_directory"
            else:
                # Default a C:/AI_VAULT
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
            # Buscar archivo
            match = re.search(r'(?:analiza|revisa|examina)\s+(?:archivo|file)?\s*:?\s*(\S+\.py)', message, re.IGNORECASE)
            if match:
                filepath = match.group(1)
                tool_result = await self.execute_tool("analyze_python_file", file_path=filepath)
                tool_name = "analyze_python_file"
        
        elif intent == "TRADING":
            tool_result = await self.execute_tool("get_system_info")
            tool_name = "get_system_info"
        
        # Preparar respuesta
        if tool_result and tool_result.get("success"):
            # Formatear resultado según la herramienta
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
        
        # Fallback: respuesta genérica
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

# Endpoints
@app.get("/health")
async def health_check():
    """Endpoint de health check"""
    return {
        "status": "healthy",
        "version": "8.0.2",
        "timestamp": datetime.now().isoformat(),
        "uptime": str(datetime.now() - brain.start_time),
        "conversations": brain.conversation_count
    }

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Endpoint principal de chat"""
    try:
        response = await brain.process_message(request.message, request.user_id)
        return ChatResponse(**response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/brain/health")
async def brain_health():
    """Endpoint de salud de Brain"""
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
    """Estado del sistema"""
    return {
        "status": "running",
        "version": "8.0.2",
        "session_id": brain.session_id,
        "uptime": str(datetime.now() - brain.start_time),
        "conversations": brain.conversation_count
    }

if __name__ == "__main__":
    print("=" * 60)
    print("Brain Chat V8.0 - Servidor API REST")
    print("=" * 60)
    print(f"URL: http://127.0.0.1:{PORT}")
    print(f"Health: http://127.0.0.1:{PORT}/health")
    print(f"Chat: http://127.0.0.1:{PORT}/chat")
    print(f"Brain Health: http://127.0.0.1:{PORT}/brain/health")
    print("=" * 60)
    
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
