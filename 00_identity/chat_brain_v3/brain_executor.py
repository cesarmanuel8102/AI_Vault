"""
Brain Executor V3 - Conector Directo con Brain API
Ejecuta comandos directamente en el Brain sin restricciones artificiales
"""

import httpx
import json
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime


class BrainExecutor:
    """
    Ejecutor que se conecta directamente con Brain API (puerto 8010)
    y Advisor API (puerto 8030)
    """
    
    def __init__(self):
        self.brain_api = "http://127.0.0.1:8010"
        self.advisor_api = "http://127.0.0.1:8030"
        self.chat_api = "http://127.0.0.1:8040"
        self.last_error = None
        
    async def check_connections(self) -> Dict[str, bool]:
        """Verifica conexión con todos los servicios"""
        statuses = {}
        
        # Brain API
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.brain_api}/health")
                statuses['brain_api'] = response.status_code == 200
        except:
            statuses['brain_api'] = False
        
        # Advisor API
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.advisor_api}/health")
                statuses['advisor_api'] = response.status_code == 200
        except:
            statuses['advisor_api'] = False
            
        return statuses
    
    async def execute_brain_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ejecuta comando directamente en Brain API
        
        Args:
            command: Comando a ejecutar
            params: Parámetros del comando
            
        Returns:
            Respuesta del Brain o error
        """
        params = params or {}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.brain_api}/api/execute",
                    json={
                        "command": command,
                        "params": params,
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json(),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Brain API error: {response.status_code} - {response.text}"
                    }
                    
        except Exception as e:
            self.last_error = str(e)
            return {
                "success": False,
                "data": None,
                "error": f"Connection error: {str(e)}"
            }
    
    async def query_brain(self, query_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Consulta información del Brain sin ejecutar
        
        Args:
            query_type: Tipo de consulta (phases, roadmap, status, etc.)
            params: Parámetros de la consulta
            """
        params = params or {}
        
        query_endpoints = {
            "phases": "/api/status",
            "roadmap": "/api/roadmap/current",
            "status": "/health",
            "info": "/api/info",
        }
        
        endpoint = query_endpoints.get(query_type, "/api/query")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if params:
                    response = await client.post(
                        f"{self.brain_api}{endpoint}",
                        json=params
                    )
                else:
                    response = await client.get(f"{self.brain_api}{endpoint}")
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json(),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Query failed: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
    
    async def execute_file_operation(self, operation: str, path: str, 
                                    content: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta operación de archivo
        
        Args:
            operation: read, write, append, delete
            path: Ruta del archivo
            content: Contenido (para write/append)
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if operation == "read":
                    response = await client.post(
                        f"{self.brain_api}/api/file/read",
                        json={"path": path}
                    )
                elif operation == "write":
                    response = await client.post(
                        f"{self.brain_api}/api/file/write",
                        json={"path": path, "content": content}
                    )
                elif operation == "list":
                    response = await client.post(
                        f"{self.brain_api}/api/file/list",
                        json={"path": path}
                    )
                else:
                    return {
                        "success": False,
                        "error": f"Operación no soportada: {operation}"
                    }
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Error {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_phase_status(self) -> Dict[str, Any]:
        """Obtiene estado actual de las fases"""
        return await self.query_brain("phases")
    
    async def get_roadmap_status(self) -> Dict[str, Any]:
        """Obtiene estado del roadmap"""
        return await self.query_brain("roadmap")
    
    async def execute_advisor_command(self, message: str, room_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Ejecuta comando a través de Advisor API
        
        Args:
            message: Mensaje/comando para el advisor
            room_id: ID del room (opcional)
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.advisor_api}/api/advisor/next",
                    json={
                        "message": message,
                        "room_id": room_id or "chat_default",
                        "context": "brain_console"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "success": True,
                        "data": result,
                        "plan": result.get("plan", {}),
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Advisor error: {response.status_code}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }
    
    async def get_pocketoption_data(self) -> Dict[str, Any]:
        """Obtiene datos de PocketOption desde bridge"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("http://127.0.0.1:8765/normalized")
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Bridge error: {response.status_code}"
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# Instancia global
brain_executor = BrainExecutor()
