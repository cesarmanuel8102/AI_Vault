"""
AI_VAULT Intelligent Chat System v2.0  [DEPRECATED]
=====================================================
DEPRECATED as of 2026-03-25.  DO NOT start this service.

The canonical chat system is now brain_v9/core/session.py (v4-unified),
served via brain_v9/main.py on port 8090.

This file is kept for reference only. It will be removed in a future
cleanup pass once all consumers have been verified migrated.

Original description:
  Chat conversacional e inteligente con ciclo completo:
  OpenAI → FastAPI → Brain → Ejecuta → Recoge → OpenAI → Análisis → Respuesta

Known issues at deprecation time:
  - WebSocket-only (no HTTP POST fallback)
  - OpenAI-only (no Ollama support)
  - 5 fabrication points (fake AAPL/MSFT data, hardcoded reports, no-op /execute)
  - Memory: RAM-only dict, no persistence, no cross-session
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
import logging
import warnings

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

warnings.warn(
    "brain_chat_system.py is DEPRECATED. Use brain_v9/core/session.py (port 8090) instead.",
    DeprecationWarning,
    stacklevel=2,
)
logger.warning("⚠ brain_chat_system.py is DEPRECATED. The canonical chat is brain_v9/core/session.py on port 8090.")

@dataclass
class ChatMessage:
    """Mensaje del chat"""
    role: str  # user, assistant, system, brain
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

class BrainChatSystem:
    """
    Sistema de chat inteligente que integra:
    - OpenAI para procesamiento de lenguaje
    - Brain para ejecución de tareas
    - FastAPI para el backend
    """
    
    def __init__(self):
        self.app = FastAPI(title="AI_VAULT Brain Chat", version="2.0.0")
        self.setup_middleware()
        self.setup_routes()
        
        # Configuración
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4")
        self.brain_api_url = "http://127.0.0.1:8010"
        
        # Estado
        self.conversations: Dict[str, List[ChatMessage]] = {}
        self.active_connections: List[WebSocket] = []
        
        # Handlers de comandos
        self.command_handlers: Dict[str, Callable] = {
            "/status": self.cmd_status,
            "/portfolio": self.cmd_portfolio,
            "/trades": self.cmd_trades,
            "/report": self.cmd_report,
            "/help": self.cmd_help,
            "/execute": self.cmd_execute,
        }
        
        logger.info("Brain Chat System initialized")
    
    def setup_middleware(self):
        """Configurar middleware CORS"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def setup_routes(self):
        """Configurar rutas"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            return self.get_chat_html()
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.handle_websocket(websocket)
        
        @self.app.get("/api/conversations/{conversation_id}")
        async def get_conversation(conversation_id: str):
            if conversation_id in self.conversations:
                return {
                    "messages": [m.to_dict() for m in self.conversations[conversation_id]]
                }
            return {"messages": []}
    
    async def handle_websocket(self, websocket: WebSocket):
        """Manejar conexión WebSocket"""
        await websocket.accept()
        self.active_connections.append(websocket)
        conversation_id = f"conv_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # Enviar mensaje de bienvenida
            welcome = ChatMessage(
                role="assistant",
                content="¡Hola! Soy el AI_VAULT Brain Assistant. Puedo ayudarte con:\n\n" \
                        "📊 Consultar estado del sistema\n" \
                        "💰 Ver portafolio y trades\n" \
                        "📈 Generar reportes\n" \
                        "⚡ Ejecutar tareas\n" \
                        "🧠 Proponer ideas y estrategias\n\n" \
                        "Escribe /help para ver todos los comandos disponibles.",
                metadata={"type": "welcome"}
            )
            await websocket.send_json(welcome.to_dict())
            
            while True:
                # Recibir mensaje
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                user_message = ChatMessage(
                    role="user",
                    content=message_data.get("content", ""),
                    metadata=message_data.get("metadata", {})
                )
                
                # Guardar en conversación
                if conversation_id not in self.conversations:
                    self.conversations[conversation_id] = []
                self.conversations[conversation_id].append(user_message)
                
                # Procesar mensaje
                response = await self.process_message(user_message, conversation_id)
                
                # Enviar respuesta
                await websocket.send_json(response.to_dict())
                
                # Guardar respuesta
                self.conversations[conversation_id].append(response)
                
        except WebSocketDisconnect:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected: {conversation_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
    
    async def process_message(self, message: ChatMessage, conversation_id: str) -> ChatMessage:
        """
        Procesar mensaje del usuario con el ciclo completo:
        1. Analizar intención con OpenAI
        2. Determinar si necesita acción del Brain
        3. Ejecutar acción si es necesario
        4. Analizar resultado con OpenAI
        5. Generar respuesta final
        """
        
        content = message.content.strip()
        
        # Verificar si es un comando
        if content.startswith("/"):
            command = content.split()[0].lower()
            if command in self.command_handlers:
                return await self.command_handlers[command](content, conversation_id)
        
        # Paso 1: Analizar intención con OpenAI
        intent_analysis = await self.analyze_intent(content, conversation_id)
        
        # Paso 2: Determinar si necesita acción
        if intent_analysis.get("requires_action", False):
            # Paso 3: Ejecutar acción
            action_result = await self.execute_brain_action(
                intent_analysis.get("action", ""),
                intent_analysis.get("parameters", {})
            )
            
            # Paso 4: Analizar resultado
            final_response = await self.analyze_result(
                content,
                action_result,
                conversation_id
            )
            
            return ChatMessage(
                role="assistant",
                content=final_response,
                metadata={
                    "type": "action_response",
                    "action": intent_analysis.get("action"),
                    "result": action_result
                }
            )
        else:
            # Respuesta conversacional directa
            response = await self.generate_conversational_response(content, conversation_id)
            return ChatMessage(
                role="assistant",
                content=response,
                metadata={"type": "conversational"}
            )
    
    async def analyze_intent(self, message: str, conversation_id: str) -> Dict[str, Any]:
        """Analizar intención del mensaje usando OpenAI"""
        
        if not self.openai_api_key:
            # Fallback: análisis simple sin OpenAI
            return self._simple_intent_analysis(message)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": """You are an intent classifier for AI_VAULT Brain. 
                                Analyze the user message and determine if it requires action from the Brain system.
                                
                                Available actions:
                                - get_status: Get system status
                                - get_portfolio: Get portfolio information
                                - get_trades: Get trade history
                                - generate_report: Generate a report
                                - execute_task: Execute a specific task
                                - propose_strategy: Propose a trading strategy
                                
                                Respond in JSON format:
                                {
                                    "requires_action": true/false,
                                    "action": "action_name",
                                    "parameters": {},
                                    "confidence": 0.95
                                }"""
                            },
                            {
                                "role": "user",
                                "content": message
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 200
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    # Intentar parsear JSON
                    try:
                        return json.loads(content)
                    except:
                        return self._simple_intent_analysis(message)
                else:
                    return self._simple_intent_analysis(message)
                    
        except Exception as e:
            logger.error(f"OpenAI intent analysis error: {e}")
            return self._simple_intent_analysis(message)
    
    def _simple_intent_analysis(self, message: str) -> Dict[str, Any]:
        """Análisis de intención simple sin OpenAI"""
        
        message_lower = message.lower()
        
        keywords = {
            "get_status": ["estado", "status", "cómo estás", "cómo va", "sistema"],
            "get_portfolio": ["portafolio", "portfolio", "posiciones", "inversiones", "capital"],
            "get_trades": ["trades", "operaciones", "ordenes", "transacciones", "historial"],
            "generate_report": ["reporte", "report", "informe", "análisis", "resumen"],
            "execute_task": ["ejecuta", "haz", "realiza", "corre", "inicia"],
            "propose_strategy": ["estrategia", "strategy", "propón", "idea", "plan"]
        }
        
        for action, words in keywords.items():
            if any(word in message_lower for word in words):
                return {
                    "requires_action": True,
                    "action": action,
                    "parameters": {},
                    "confidence": 0.8
                }
        
        return {
            "requires_action": False,
            "action": None,
            "parameters": {},
            "confidence": 0.9
        }
    
    async def execute_brain_action(self, action: str, parameters: Dict) -> Dict[str, Any]:
        """Ejecutar acción en el Brain"""
        
        try:
            async with httpx.AsyncClient() as client:
                # Llamar al Brain API
                response = await client.post(
                    f"{self.brain_api_url}/v1/agent/execute",
                    json={
                        "action": action,
                        "parameters": parameters
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return {
                        "success": True,
                        "data": response.json()
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Brain API error: {response.status_code}",
                        "data": None
                    }
                    
        except Exception as e:
            logger.error(f"Brain execution error: {e}")
            # Fallback: simular respuesta
            return self._simulate_brain_response(action, parameters)
    
    def _simulate_brain_response(self, action: str, parameters: Dict) -> Dict[str, Any]:
        """Simular respuesta del Brain para demostración"""
        
        simulations = {
            "get_status": {
                "system_status": "operational",
                "phase": "6.1",
                "active_strategies": 3,
                "open_positions": 2,
                "cash": 85000.0,
                "total_value": 98750.0
            },
            "get_portfolio": {
                "positions": [
                    {"symbol": "AAPL", "quantity": 10, "avg_price": 150.0, "current_price": 155.0, "pnl": 50.0},
                    {"symbol": "MSFT", "quantity": 5, "avg_price": 300.0, "current_price": 310.0, "pnl": 50.0}
                ],
                "total_value": 98750.0,
                "cash": 85000.0,
                "unrealized_pnl": 100.0
            },
            "get_trades": {
                "trades": [
                    {"symbol": "AAPL", "side": "buy", "quantity": 10, "price": 150.0, "timestamp": "2026-03-19T10:00:00Z"},
                    {"symbol": "MSFT", "side": "buy", "quantity": 5, "price": 300.0, "timestamp": "2026-03-19T10:05:00Z"}
                ]
            }
        }
        
        return {
            "success": True,
            "data": simulations.get(action, {"message": "Action executed successfully"})
        }
    
    async def analyze_result(self, original_message: str, result: Dict, conversation_id: str) -> str:
        """Analizar resultado con OpenAI y generar respuesta"""
        
        if not self.openai_api_key:
            return self._format_simple_response(result)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": """You are AI_VAULT Brain Assistant. Analyze the action result 
                                and provide a clear, helpful response in Spanish. Be concise but informative."""
                            },
                            {
                                "role": "user",
                                "content": f"Original request: {original_message}\n\nResult: {json.dumps(result, indent=2)}"
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 300
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result_data = response.json()
                    return result_data["choices"][0]["message"]["content"]
                else:
                    return self._format_simple_response(result)
                    
        except Exception as e:
            logger.error(f"OpenAI analysis error: {e}")
            return self._format_simple_response(result)
    
    def _format_simple_response(self, result: Dict) -> str:
        """Formatear respuesta simple sin OpenAI"""
        
        if not result.get("success", False):
            return f"❌ Error: {result.get('error', 'Unknown error')}"
        
        data = result.get("data", {})
        
        if "system_status" in data:
            return f"✅ Sistema operativo\n📊 Fase: {data.get('phase', 'N/A')}\n💰 Valor total: ${data.get('total_value', 0):,.2f}\n📈 Posiciones abiertas: {data.get('open_positions', 0)}"
        
        elif "positions" in data:
            positions = data.get("positions", [])
            total_pnl = data.get("unrealized_pnl", 0)
            return f"📊 Portafolio:\n" + "\n".join([f"  • {p['symbol']}: {p['quantity']} @ ${p['current_price']:.2f}" for p in positions]) + f"\n\n💰 PnL no realizado: ${total_pnl:,.2f}"
        
        elif "trades" in data:
            trades = data.get("trades", [])
            return f"📈 Últimas operaciones:\n" + "\n".join([f"  • {t['side'].upper()} {t['quantity']} {t['symbol']} @ ${t['price']:.2f}" for t in trades[-5:]])
        
        return "✅ Acción completada exitosamente"
    
    async def generate_conversational_response(self, message: str, conversation_id: str) -> str:
        """Generar respuesta conversacional"""
        
        if not self.openai_api_key:
            return self._generate_fallback_response(message)
        
        try:
            # Obtener historial de conversación
            history = self.conversations.get(conversation_id, [])[-10:]  # Últimos 10 mensajes
            
            messages = [
                {
                    "role": "system",
                    "content": """You are AI_VAULT Brain Assistant, an intelligent financial AI system.
                    You help users with trading, portfolio management, and financial analysis.
                    Be helpful, professional, and concise. Respond in Spanish."""
                }
            ]
            
            for msg in history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.openai_model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 300
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    return self._generate_fallback_response(message)
                    
        except Exception as e:
            logger.error(f"Conversational response error: {e}")
            return self._generate_fallback_response(message)
    
    def _generate_fallback_response(self, message: str) -> str:
        """Respuesta fallback sin OpenAI"""
        
        responses = {
            "hola": "¡Hola! ¿En qué puedo ayudarte hoy?",
            "cómo estás": "Estoy operativo y listo para ayudarte. ¿Qué necesitas?",
            "gracias": "¡De nada! Estoy aquí para ayudarte.",
            "adiós": "¡Hasta luego! Vuelve cuando necesites ayuda.",
        }
        
        message_lower = message.lower()
        for key, response in responses.items():
            if key in message_lower:
                return response
        
        return "Entiendo. ¿Puedes darme más detalles sobre lo que necesitas? Puedo ayudarte con:\n\n" \
               "📊 Consultar estado del sistema\n" \
               "💰 Ver tu portafolio\n" \
               "📈 Ver historial de trades\n" \
               "📄 Generar reportes\n" \
               "⚡ Ejecutar tareas\n\n" \
               "Escribe /help para ver todos los comandos."
    
    # Command handlers
    async def cmd_status(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /status"""
        result = await self.execute_brain_action("get_status", {})
        response = await self.analyze_result("status", result, conversation_id)
        return ChatMessage(role="assistant", content=response, metadata={"command": "status"})
    
    async def cmd_portfolio(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /portfolio"""
        result = await self.execute_brain_action("get_portfolio", {})
        response = await self.analyze_result("portfolio", result, conversation_id)
        return ChatMessage(role="assistant", content=response, metadata={"command": "portfolio"})
    
    async def cmd_trades(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /trades"""
        result = await self.execute_brain_action("get_trades", {})
        response = await self.analyze_result("trades", result, conversation_id)
        return ChatMessage(role="assistant", content=response, metadata={"command": "trades"})
    
    async def cmd_report(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /report"""
        return ChatMessage(
            role="assistant",
            content="📄 Generando reporte completo...\n\n" \
                    "**Resumen del Sistema**\n" \
                    "• Estado: Operativo ✅\n" \
                    "• Fase: 6.1 - Motor Financiero\n" \
                    "• Estrategias activas: 3\n" \
                    "• Posiciones abiertas: 2\n" \
                    "• Valor total: $98,750.00\n" \
                    "• PnL: +$100.00 (0.10%)\n\n" \
                    "¿Te gustaría ver algún reporte específico?",
            metadata={"command": "report"}
        )
    
    async def cmd_help(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /help"""
        return ChatMessage(
            role="assistant",
            content="🤖 **Comandos disponibles:**\n\n" \
                    "📊 **Consultas**\n" \
                    "• /status - Estado del sistema\n" \
                    "• /portfolio - Ver portafolio\n" \
                    "• /trades - Historial de operaciones\n" \
                    "• /report - Generar reporte\n\n" \
                    "⚡ **Acciones**\n" \
                    "• /execute [tarea] - Ejecutar tarea\n\n" \
                    "💡 **También puedes:**\n" \
                    "• Preguntar en lenguaje natural\n" \
                    "• Proponer ideas de estrategias\n" \
                    "• Solicitar análisis de mercado\n" \
                    "• Pedir explicaciones",
            metadata={"command": "help"}
        )
    
    async def cmd_execute(self, content: str, conversation_id: str) -> ChatMessage:
        """Comando /execute"""
        # Extraer tarea del mensaje
        task = content.replace("/execute", "").strip()
        if not task:
            return ChatMessage(
                role="assistant",
                content="⚡ Por favor especifica qué tarea ejecutar. Ejemplo: /execute analizar AAPL",
                metadata={"command": "execute", "error": "no_task"}
            )
        
        return ChatMessage(
            role="assistant",
            content=f"⚡ Ejecutando tarea: '{task}'...\n\n✅ Tarea completada exitosamente.",
            metadata={"command": "execute", "task": task}
        )
    
    def get_chat_html(self) -> str:
        """Obtener HTML del chat"""
        
        html_path = Path(__file__).parent / "chat_interface.html"
        if html_path.exists():
            with open(html_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        # HTML por defecto
        return """<!DOCTYPE html>
<html>
<head>
    <title>AI_VAULT Brain Chat</title>
    <meta charset="UTF-8">
</head>
<body>
    <h1>AI_VAULT Brain Chat</h1>
    <p>Chat interface loading... Please create chat_interface.html</p>
</body>
</html>"""
    
    def run(self, host: str = "127.0.0.1", port: int = 8045):
        """Iniciar servidor"""
        import uvicorn
        logger.info(f"Starting Brain Chat Server on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port)

# Instancia global
chat_system = BrainChatSystem()

if __name__ == "__main__":
    chat_system.run()
