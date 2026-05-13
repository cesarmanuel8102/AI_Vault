#!/usr/bin/env python3
"""
Servidor WebSocket - Comunicación en Tiempo Real
Permite comunicación bidireccional entre agente y clientes
"""

import asyncio
import json
import websockets
from datetime import datetime
from typing import Dict, Set
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from brain_agent_v8_final import BrainAgentV8Final
    AGENT_AVAILABLE = True
except ImportError:
    AGENT_AVAILABLE = False


class WebSocketServer:
    """Servidor WebSocket para comunicación realtime"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8091):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.agent = BrainAgentV8Final("websocket_session") if AGENT_AVAILABLE else None
        
    async def register(self, websocket: websockets.WebSocketServerProtocol):
        """Registra un nuevo cliente"""
        self.clients.add(websocket)
        print(f"[WebSocket] Cliente conectado. Total: {len(self.clients)}")
        await self.broadcast({
            "type": "system",
            "message": "Cliente conectado",
            "clients": len(self.clients)
        })
    
    async def unregister(self, websocket: websockets.WebSocketServerProtocol):
        """Desregistra un cliente"""
        self.clients.discard(websocket)
        print(f"[WebSocket] Cliente desconectado. Total: {len(self.clients)}")
    
    async def broadcast(self, message: Dict):
        """Envía mensaje a todos los clientes"""
        if self.clients:
            message_json = json.dumps(message)
            await asyncio.gather(
                *[client.send(message_json) for client in self.clients],
                return_exceptions=True
            )
    
    async def handle_client(self, websocket: websockets.WebSocketServerProtocol, path: str):
        """Maneja conexión con un cliente"""
        await self.register(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.process_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "JSON inválido"
                    }))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)
    
    async def process_message(self, websocket: websockets.WebSocketServerProtocol, data: Dict):
        """Procesa mensaje del cliente"""
        msg_type = data.get("type", "unknown")
        
        if msg_type == "chat":
            # Procesar mensaje de chat
            user_message = data.get("message", "")
            
            if self.agent:
                result = await self.agent.process_message(user_message)
                
                response = {
                    "type": "response",
                    "original_message": user_message,
                    "response": result.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                    "metadata": result.get("metadata", {})
                }
            else:
                response = {
                    "type": "error",
                    "message": "Agente no disponible"
                }
            
            await websocket.send(json.dumps(response))
            
        elif msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            
        elif msg_type == "status":
            await websocket.send(json.dumps({
                "type": "status",
                "clients": len(self.clients),
                "agent_available": AGENT_AVAILABLE,
                "timestamp": datetime.now().isoformat()
            }))
    
    async def start(self):
        """Inicia el servidor WebSocket"""
        print(f"[WebSocket] Iniciando servidor en ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever


if __name__ == "__main__":
    server = WebSocketServer()
    asyncio.run(server.start())
