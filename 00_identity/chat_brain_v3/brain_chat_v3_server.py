"""
Brain Chat V3 Server - Servidor de Ejecución Inteligente
Integra execution_authority.py y brain_executor.py
Puerto: 8050

Características:
- Conexión directa a Brain API (8010) y Advisor API (8030)
- Tres modos de operación: CONSULTA, EJECUCION, CRITICO
- Sistema de autorización para operaciones críticas
- Comandos especiales: /confirm, /cancel, /mode, /brain, /advisor, /phase, /pocketoption
- Manejo de errores y logging completo
- UI HTML con diálogos de confirmación
"""

import asyncio
import json
import logging
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Importar módulos locales
sys.path.insert(0, str(Path(__file__).parent))
try:
    from execution_authority import ExecutionAuthority, OperationLevel, authority
    from brain_executor import BrainExecutor, brain_executor
except ImportError:
    # Fallback: importar desde el mismo directorio
    import importlib.util
    base_path = Path(__file__).parent
    
    exec_auth_path = base_path / "execution_authority.py"
    if exec_auth_path.exists():
        spec = importlib.util.spec_from_file_location("execution_authority", str(exec_auth_path))
        if spec and spec.loader:
            execution_authority_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(execution_authority_module)
            ExecutionAuthority = execution_authority_module.ExecutionAuthority
            OperationLevel = execution_authority_module.OperationLevel
            authority = execution_authority_module.authority
    
    brain_exec_path = base_path / "brain_executor.py"
    if brain_exec_path.exists():
        spec2 = importlib.util.spec_from_file_location("brain_executor", str(brain_exec_path))
        if spec2 and spec2.loader:
            brain_executor_module = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(brain_executor_module)
            BrainExecutor = brain_executor_module.BrainExecutor
            brain_executor = brain_executor_module.brain_executor


# ============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ============================================================================

APP_NAME = "Brain Chat V3 Server"
APP_VERSION = "3.0.0"
PORT = 8050

# URLs de servicios
BRAIN_API_URL = "http://127.0.0.1:8010"
ADVISOR_API_URL = "http://127.0.0.1:8030"
POCKET_BRIDGE_URL = "http://127.0.0.1:8765"

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / 'brain_chat_v3.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# MODELOS DE DATOS
# ============================================================================

class OperationMode(str, Enum):
    """Modos de operación del servidor"""
    CONSULTA = "CONSULTA"      # Solo lectura
    EJECUCION = "EJECUCION"    # Ejecución estándar
    CRITICO = "CRITICO"        # Requiere autorización


class ChatMessage(BaseModel):
    """Modelo para mensajes de chat"""
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: Optional[str] = None


class ConfirmOperation(BaseModel):
    """Modelo para confirmar operación"""
    code: str
    command: str
    target: str
    user_id: Optional[str] = None


class CancelOperation(BaseModel):
    """Modelo para cancelar operación"""
    code: str


class ChangeMode(BaseModel):
    """Modelo para cambiar modo"""
    mode: OperationMode


class ExecutionResponse(BaseModel):
    """Respuesta de ejecución"""
    success: bool
    message: str
    data: Optional[Dict] = None
    requires_confirmation: bool = False
    confirmation_code: Optional[str] = None
    operation_level: Optional[str] = None
    execution_time_ms: Optional[float] = None


# ============================================================================
# CLASE PRINCIPAL: CHAT BRAIN SERVER
# ============================================================================

class ChatBrainServer:
    """
    Servidor principal de Chat Brain V3
    Gestiona operaciones, autorizaciones y conexiones
    """
    
    def __init__(self):
        self.current_mode = OperationMode.EJECUCION
        self.authority = authority
        self.executor = brain_executor
        self.sessions: Dict[str, Dict] = {}
        self.message_history: List[Dict] = []
        self.start_time = time.time()
        
    async def initialize(self):
        """Inicializa el servidor y verifica conexiones"""
        logger.info(f"🚀 Iniciando {APP_NAME} v{APP_VERSION}")
        
        # Verificar conexiones
        statuses = await self.executor.check_connections()
        
        logger.info(f"   Brain API: {'✅ Conectado' if statuses.get('brain_api') else '❌ No disponible'}")
        logger.info(f"   Advisor API: {'✅ Conectado' if statuses.get('advisor_api') else '❌ No disponible'}")
        
        return statuses
    
    def get_or_create_session(self, user_id: Optional[str] = None) -> str:
        """Obtiene o crea sesión de usuario"""
        if not user_id:
            user_id = f"user_{secrets.token_hex(4)}"
        
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                'created_at': time.time(),
                'last_activity': time.time(),
                'mode': self.current_mode,
                'message_count': 0
            }
        
        self.sessions[user_id]['last_activity'] = time.time()
        return user_id
    
    async def process_message(self, message: str, user_id: Optional[str] = None, 
                             session_id: Optional[str] = None) -> ExecutionResponse:
        """
        Procesa mensaje del usuario y determina acción
        
        Args:
            message: Mensaje del usuario
            user_id: ID de usuario
            session_id: ID de sesión
            
        Returns:
            ExecutionResponse con resultado
        """
        start_time = time.time()
        user_id = self.get_or_create_session(user_id)
        
        # Limpiar mensaje
        message = message.strip()
        
        # Guardar en historial
        self.message_history.append({
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'message': message,
            'type': 'user'
        })
        
        # Procesar comandos especiales
        if message.startswith('/'):
            return await self._process_command(message, user_id)
        
        # Procesar mensaje normal
        return await self._process_normal_message(message, user_id, start_time)
    
    async def _process_command(self, command: str, user_id: str) -> ExecutionResponse:
        """Procesa comandos especiales que comienzan con /"""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        command_handlers = {
            '/confirm': self._cmd_confirm,
            '/cancel': self._cmd_cancel,
            '/mode': self._cmd_mode,
            '/brain': self._cmd_brain,
            '/advisor': self._cmd_advisor,
            '/phase': self._cmd_phase,
            '/pocketoption': self._cmd_pocketoption,
            '/status': self._cmd_status,
            '/help': self._cmd_help,
            '/pending': self._cmd_pending,
        }
        
        handler = command_handlers.get(cmd)
        if handler:
            return await handler(args, user_id)
        
        return ExecutionResponse(
            success=False,
            message=f"Comando desconocido: {cmd}. Usa /help para ver comandos disponibles."
        )
    
    async def _process_normal_message(self, message: str, user_id: str, 
                                     start_time: float) -> ExecutionResponse:
        """Procesa mensaje normal (no comando)"""
        
        # Clasificar operación
        classification = self.authority.classify_operation("process", message)
        
        # Modo CONSULTA: solo permitir lecturas
        if self.current_mode == OperationMode.CONSULTA:
            if classification.level != OperationLevel.CONSULTA:
                return ExecutionResponse(
                    success=False,
                    message="🔒 Modo CONSULTA activo. Solo operaciones de lectura permitidas.",
                    operation_level="CONSULTA"
                )
        
        # Operación crítica: requerir autorización
        if classification.requires_auth:
            code = self.authority.generate_authorization_code(
                "process", message, user_id
            )
            
            return ExecutionResponse(
                success=False,
                message=f"⚠️ OPERACIÓN CRÍTICA DETECTADA\n\n"
                       f"Razón: {classification.reason}\n"
                       f"Factores de riesgo: {', '.join(classification.risk_factors)}\n\n"
                       f"Para ejecutar, usa: /confirm {code}",
                requires_confirmation=True,
                confirmation_code=code,
                operation_level="CRITICO"
            )
        
        # Ejecutar en modo normal
        try:
            # Intentar con Advisor API primero
            result = await self.executor.execute_advisor_command(message)
            
            if result['success']:
                execution_time = (time.time() - start_time) * 1000
                
                return ExecutionResponse(
                    success=True,
                    message=result['data'].get('response', 'Operación completada'),
                    data=result['data'],
                    operation_level=classification.level.name,
                    execution_time_ms=execution_time
                )
            else:
                # Fallback a Brain API
                brain_result = await self.executor.execute_brain_command(
                    "process_message", {"message": message}
                )
                
                if brain_result['success']:
                    return ExecutionResponse(
                        success=True,
                        message=brain_result['data'].get('response', 'Procesado por Brain'),
                        data=brain_result['data'],
                        operation_level=classification.level.name
                    )
                else:
                    return ExecutionResponse(
                        success=False,
                        message=f"Error: {brain_result.get('error', 'Unknown error')}"
                    )
                    
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
            return ExecutionResponse(
                success=False,
                message=f"Error de ejecución: {str(e)}"
            )
    
    # ============================================================================
    # HANDLERS DE COMANDOS
    # ============================================================================
    
    async def _cmd_confirm(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Confirma operación pendiente"""
        if not args:
            return ExecutionResponse(
                success=False,
                message="Uso: /confirm <código>"
            )
        
        code = args[0].upper()
        
        # Buscar operación pendiente
        pending = self.authority.get_pending_operations()
        operation = None
        
        for op in pending:
            if op['code'] == code:
                operation = op
                break
        
        if not operation:
            return ExecutionResponse(
                success=False,
                message="❌ Código de confirmación inválido o expirado"
            )
        
        # Verificar código
        valid, msg = self.authority.verify_authorization_code(
            code, operation['command'], operation['target']
        )
        
        if not valid:
            return ExecutionResponse(
                success=False,
                message=f"❌ {msg}"
            )
        
        # Ejecutar operación
        try:
            result = await self.executor.execute_advisor_command(operation['target'])
            
            self.authority.log_execution(
                operation['command'], operation['target'], user_id,
                True, result['success'], str(result.get('data', ''))
            )
            
            return ExecutionResponse(
                success=result['success'],
                message=f"✅ Operación confirmada y ejecutada\n\n{result.get('data', {}).get('response', 'Completado')}",
                data=result.get('data')
            )
            
        except Exception as e:
            return ExecutionResponse(
                success=False,
                message=f"❌ Error ejecutando operación: {str(e)}"
            )
    
    async def _cmd_cancel(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Cancela operación pendiente"""
        if not args:
            # Cancelar todas las operaciones del usuario
            pending = self.authority.get_pending_operations()
            cancelled = 0
            
            for op in pending:
                if self.authority.cancel_operation(op['code']):
                    cancelled += 1
            
            return ExecutionResponse(
                success=True,
                message=f"✅ {cancelled} operación(es) cancelada(s)"
            )
        
        code = args[0].upper()
        if self.authority.cancel_operation(code):
            return ExecutionResponse(
                success=True,
                message=f"✅ Operación {code} cancelada"
            )
        else:
            return ExecutionResponse(
                success=False,
                message=f"❌ No se encontró operación con código {code}"
            )
    
    async def _cmd_mode(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Cambia modo de operación"""
        if not args:
            return ExecutionResponse(
                success=True,
                message=f"Modo actual: {self.current_mode.value}\n\n"
                       f"Modos disponibles:\n"
                       f"  CONSULTA - Solo lectura\n"
                       f"  EJECUCION - Ejecución estándar\n"
                       f"  CRITICO - Requiere autorización para todo"
            )
        
        mode_str = args[0].upper()
        
        try:
            new_mode = OperationMode(mode_str)
            self.current_mode = new_mode
            
            return ExecutionResponse(
                success=True,
                message=f"✅ Modo cambiado a: {new_mode.value}"
            )
        except ValueError:
            return ExecutionResponse(
                success=False,
                message=f"❌ Modo inválido: {mode_str}. Usa: CONSULTA, EJECUCION, CRITICO"
            )
    
    async def _cmd_brain(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Ejecuta comando directo en Brain API"""
        if not args:
            return ExecutionResponse(
                success=False,
                message="Uso: /brain <comando> [parámetros JSON]"
            )
        
        command = args[0]
        params = {}
        
        if len(args) > 1:
            try:
                params = json.loads(' '.join(args[1:]))
            except:
                pass
        
        result = await self.executor.execute_brain_command(command, params)
        
        if result['success']:
            return ExecutionResponse(
                success=True,
                message=f"✅ Brain API Response:\n```json\n{json.dumps(result['data'], indent=2)}\n```",
                data=result['data']
            )
        else:
            return ExecutionResponse(
                success=False,
                message=f"❌ Brain API Error: {result.get('error', 'Unknown')}"
            )
    
    async def _cmd_advisor(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Consulta Advisor API"""
        message = ' '.join(args) if args else "status"
        
        result = await self.executor.execute_advisor_command(message)
        
        if result['success']:
            response_text = result['data'].get('response', 'No response')
            plan = result.get('plan', {})
            
            msg = f"🎯 Advisor Response:\n\n{response_text}"
            
            if plan:
                msg += f"\n\n📋 Plan: {plan.get('name', 'N/A')}\n"
                msg += f"   Fase: {plan.get('current_phase', 'N/A')}"
            
            return ExecutionResponse(
                success=True,
                message=msg,
                data=result['data']
            )
        else:
            return ExecutionResponse(
                success=False,
                message=f"❌ Advisor Error: {result.get('error', 'Unknown')}"
            )
    
    async def _cmd_phase(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Obtiene estado de fases"""
        result = await self.executor.get_phase_status()
        
        if result['success']:
            data = result['data']
            
            msg = "📊 Estado de Fases:\n\n"
            
            if isinstance(data, dict):
                for phase, status in data.items():
                    icon = "✅" if status == "completed" else "🔄" if status == "in_progress" else "⏳"
                    msg += f"{icon} {phase}: {status}\n"
            else:
                msg += json.dumps(data, indent=2)
            
            return ExecutionResponse(
                success=True,
                message=msg,
                data=data
            )
        else:
            return ExecutionResponse(
                success=False,
                message=f"❌ Error obteniendo fases: {result.get('error', 'Unknown')}"
            )
    
    async def _cmd_pocketoption(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Obtiene datos de PocketOption"""
        result = await self.executor.get_pocketoption_data()
        
        if result['success']:
            data = result['data']
            
            msg = "💹 PocketOption Data:\n\n"
            
            if 'price' in data:
                msg += f"💰 Precio: {data['price']}\n"
            if 'trend' in data:
                msg += f"📈 Tendencia: {data['trend']}\n"
            if 'timestamp' in data:
                msg += f"🕐 Timestamp: {data['timestamp']}\n"
            
            msg += f"\n```json\n{json.dumps(data, indent=2)}\n```"
            
            return ExecutionResponse(
                success=True,
                message=msg,
                data=data
            )
        else:
            return ExecutionResponse(
                success=False,
                message=f"❌ Error obteniendo datos: {result.get('error', 'Unknown')}"
            )
    
    async def _cmd_status(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Muestra estado del servidor"""
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        statuses = await self.executor.check_connections()
        pending = self.authority.get_pending_operations()
        
        msg = f"""
🖥️  {APP_NAME} v{APP_VERSION}

⏱️  Uptime: {hours}h {minutes}m
👥 Sesiones activas: {len(self.sessions)}
📝 Mensajes procesados: {len(self.message_history)}
🔒 Modo actual: {self.current_mode.value}
⏳ Operaciones pendientes: {len(pending)}

🔌 Conexiones:
   Brain API: {'✅' if statuses.get('brain_api') else '❌'}
   Advisor API: {'✅' if statuses.get('advisor_api') else '❌'}
        """
        
        return ExecutionResponse(
            success=True,
            message=msg.strip()
        )
    
    async def _cmd_help(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Muestra ayuda"""
        msg = """
🤖 Brain Chat V3 - Comandos Disponibles

Comandos de Control:
  /confirm <código>  - Confirma operación crítica
  /cancel [código]   - Cancela operación pendiente
  /mode [modo]       - Cambia modo (CONSULTA/EJECUCION/CRITICO)
  /pending           - Lista operaciones pendientes

Comandos de API:
  /brain <cmd>       - Ejecuta en Brain API
  /advisor <msg>     - Consulta Advisor API
  /phase             - Muestra estado de fases
  /pocketoption      - Datos de trading

Sistema:
  /status            - Estado del servidor
  /help              - Esta ayuda

Modos de Operación:
  CONSULTA  - Solo lectura, sin modificaciones
  EJECUCION - Ejecución estándar (default)
  CRITICO   - Todo requiere autorización

Para operaciones críticas se generará un código
 de confirmación de 8 caracteres.
        """
        
        return ExecutionResponse(
            success=True,
            message=msg.strip()
        )
    
    async def _cmd_pending(self, args: List[str], user_id: str) -> ExecutionResponse:
        """Lista operaciones pendientes"""
        pending = self.authority.get_pending_operations()
        
        if not pending:
            return ExecutionResponse(
                success=True,
                message="✅ No hay operaciones pendientes de confirmación"
            )
        
        msg = "⏳ Operaciones Pendientes:\n\n"
        
        for op in pending:
            msg += f"🔸 Código: {op['code']}\n"
            msg += f"   Comando: {op['command']}\n"
            msg += f"   Objetivo: {op['target'][:50]}...\n" if len(op['target']) > 50 else f"   Objetivo: {op['target']}\n"
            msg += f"   Expira en: {op['time_remaining']}s\n\n"
        
        msg += "Usa /confirm <código> para ejecutar o /cancel <código> para cancelar"
        
        return ExecutionResponse(
            success=True,
            message=msg
        )
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas del servidor"""
        return {
            'uptime_seconds': time.time() - self.start_time,
            'total_messages': len(self.message_history),
            'active_sessions': len(self.sessions),
            'current_mode': self.current_mode.value,
            'pending_operations': len(self.authority.get_pending_operations()),
            'version': APP_VERSION
        }


# Instancia global del servidor
chat_server = ChatBrainServer()


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación"""
    # Startup
    logger.info("🚀 Iniciando Brain Chat V3 Server...")
    await chat_server.initialize()
    yield
    # Shutdown
    logger.info("👋 Cerrando Brain Chat V3 Server...")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Servidor de ejecución inteligente con autorización",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# ENDPOINTS API
# ============================================================================

@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "mode": chat_server.current_mode.value,
        "endpoints": {
            "chat": "/api/chat",
            "confirm": "/api/confirm",
            "cancel": "/api/cancel",
            "mode": "/api/mode",
            "status": "/api/status",
            "ui": "/ui"
        }
    }


@app.get("/health")
async def health():
    """Health check"""
    statuses = await chat_server.executor.check_connections()
    
    return {
        "status": "healthy",
        "version": APP_VERSION,
        "mode": chat_server.current_mode.value,
        "connections": statuses,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/chat", response_model=ExecutionResponse)
async def chat_endpoint(message: ChatMessage):
    """
    Endpoint principal de chat
    Procesa mensajes y ejecuta comandos
    """
    try:
        response = await chat_server.process_message(
            message.message,
            message.user_id,
            message.session_id
        )
        return response
    except Exception as e:
        logger.error(f"Error en chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/confirm", response_model=ExecutionResponse)
async def confirm_endpoint(confirm: ConfirmOperation):
    """Confirma operación crítica"""
    try:
        user_id = confirm.user_id if confirm.user_id else "api_user"
        response = await chat_server._cmd_confirm(
            [confirm.code],
            user_id
        )
        return response
    except Exception as e:
        logger.error(f"Error en confirm endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cancel", response_model=ExecutionResponse)
async def cancel_endpoint(cancel: CancelOperation):
    """Cancela operación pendiente"""
    try:
        response = await chat_server._cmd_cancel(
            [cancel.code],
            "api_user"
        )
        return response
    except Exception as e:
        logger.error(f"Error en cancel endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mode", response_model=ExecutionResponse)
async def mode_endpoint(mode_change: ChangeMode):
    """Cambia modo de operación"""
    try:
        response = await chat_server._cmd_mode(
            [mode_change.mode.value],
            "api_user"
        )
        return response
    except Exception as e:
        logger.error(f"Error en mode endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def status_endpoint():
    """Obtiene estado del servidor"""
    return chat_server.get_stats()


@app.get("/api/pending")
async def pending_endpoint():
    """Lista operaciones pendientes"""
    pending = chat_server.authority.get_pending_operations()
    return {
        "count": len(pending),
        "operations": pending
    }


# ============================================================================
# WEBSOCKET PARA CHAT EN TIEMPO REAL
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket para chat en tiempo real"""
    await websocket.accept()
    client_id = str(uuid.uuid4())
    
    logger.info(f"🔌 Cliente WebSocket conectado: {client_id}")
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            response = await chat_server.process_message(
                message_data.get('message', ''),
                message_data.get('user_id'),
                client_id
            )
            
            await websocket.send_json(response.dict())
            
    except WebSocketDisconnect:
        logger.info(f"🔌 Cliente WebSocket desconectado: {client_id}")
    except Exception as e:
        logger.error(f"Error en WebSocket: {e}")
        await websocket.close()


# ============================================================================
# UI HTML
# ============================================================================

HTML_UI = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brain Chat V3</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #eee;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(10px);
        }
        
        .header h1 {
            color: #00d4ff;
            font-size: 24px;
        }
        
        .status-bar {
            display: flex;
            gap: 20px;
            align-items: center;
        }
        
        .mode-indicator {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 12px;
            text-transform: uppercase;
        }
        
        .mode-CONSULTA { background: #4CAF50; }
        .mode-EJECUCION { background: #2196F3; }
        .mode-CRITICO { background: #ff9800; }
        
        .connection-status {
            display: flex;
            gap: 10px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        
        .status-online { background: #4CAF50; }
        .status-offline { background: #f44336; }
        
        .main-content {
            flex: 1;
            display: flex;
            gap: 20px;
            overflow: hidden;
        }
        
        .chat-container {
            flex: 1;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            backdrop-filter: blur(10px);
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        
        .message {
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 10px;
            max-width: 80%;
            animation: fadeIn 0.3s ease;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-user {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin-left: auto;
            text-align: right;
        }
        
        .message-bot {
            background: rgba(255,255,255,0.1);
            margin-right: auto;
        }
        
        .message-system {
            background: rgba(255,193,7,0.2);
            border-left: 4px solid #ffc107;
            margin-right: auto;
        }
        
        .message-error {
            background: rgba(244,67,54,0.2);
            border-left: 4px solid #f44336;
            margin-right: auto;
        }
        
        .message-warning {
            background: rgba(255,152,0,0.2);
            border-left: 4px solid #ff9800;
            margin-right: auto;
        }
        
        .message-header {
            font-size: 12px;
            opacity: 0.7;
            margin-bottom: 5px;
        }
        
        .message-content {
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .chat-input-container {
            padding: 20px;
            background: rgba(0,0,0,0.2);
            display: flex;
            gap: 10px;
        }
        
        .chat-input {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 10px;
            background: rgba(255,255,255,0.1);
            color: #fff;
            font-size: 14px;
            outline: none;
        }
        
        .chat-input::placeholder {
            color: rgba(255,255,255,0.5);
        }
        
        .btn {
            padding: 15px 25px;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102,126,234,0.4);
        }
        
        .btn-danger {
            background: #f44336;
            color: white;
        }
        
        .btn-success {
            background: #4CAF50;
            color: white;
        }
        
        .sidebar {
            width: 300px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            overflow-y: auto;
            backdrop-filter: blur(10px);
        }
        
        .sidebar h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 16px;
        }
        
        .command-list {
            list-style: none;
        }
        
        .command-list li {
            padding: 10px;
            margin-bottom: 5px;
            background: rgba(255,255,255,0.05);
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s;
            font-family: monospace;
            font-size: 13px;
        }
        
        .command-list li:hover {
            background: rgba(255,255,255,0.1);
            transform: translateX(5px);
        }
        
        .pending-operations {
            margin-top: 20px;
        }
        
        .pending-item {
            background: rgba(255,152,0,0.1);
            border: 1px solid #ff9800;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 10px;
        }
        
        .pending-item .code {
            font-family: monospace;
            font-weight: bold;
            color: #ff9800;
        }
        
        .pending-actions {
            display: flex;
            gap: 5px;
            margin-top: 10px;
        }
        
        .pending-actions button {
            flex: 1;
            padding: 8px;
            font-size: 12px;
        }
        
        /* Modal de Confirmación */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        
        .modal-overlay.active {
            display: flex;
        }
        
        .modal {
            background: #1a1a2e;
            border-radius: 15px;
            padding: 30px;
            max-width: 500px;
            width: 90%;
            border: 2px solid #ff9800;
        }
        
        .modal h2 {
            color: #ff9800;
            margin-bottom: 20px;
        }
        
        .modal-content {
            margin-bottom: 20px;
        }
        
        .modal-content p {
            margin-bottom: 10px;
            line-height: 1.6;
        }
        
        .code-input {
            width: 100%;
            padding: 15px;
            font-size: 24px;
            text-align: center;
            letter-spacing: 5px;
            border: 2px solid #ff9800;
            border-radius: 10px;
            background: rgba(255,152,0,0.1);
            color: #ff9800;
            font-weight: bold;
            margin-bottom: 20px;
        }
        
        .modal-actions {
            display: flex;
            gap: 10px;
        }
        
        .modal-actions button {
            flex: 1;
            padding: 15px;
        }
        
        .typing-indicator {
            display: none;
            padding: 15px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            margin-bottom: 15px;
        }
        
        .typing-indicator.active {
            display: block;
        }
        
        .typing-indicator span {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #00d4ff;
            border-radius: 50%;
            margin-right: 5px;
            animation: typing 1s infinite;
        }
        
        .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
        .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes typing {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
        }
        
        .json-output {
            background: rgba(0,0,0,0.3);
            border-radius: 5px;
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            overflow-x: auto;
            margin-top: 10px;
        }
        
        @media (max-width: 768px) {
            .main-content {
                flex-direction: column;
            }
            
            .sidebar {
                width: 100%;
                height: 200px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧠 Brain Chat V3</h1>
            <div class="status-bar">
                <div class="connection-status">
                    <span>Brain: <span id="brain-status" class="status-dot status-offline"></span></span>
                    <span>Advisor: <span id="advisor-status" class="status-dot status-offline"></span></span>
                </div>
                <div id="mode-indicator" class="mode-indicator mode-EJECUCION">EJECUCION</div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="chat-container">
                <div class="chat-messages" id="chat-messages">
                    <div class="message message-bot">
                        <div class="message-header">🤖 Brain Chat V3</div>
                        <div class="message-content">¡Bienvenido! Estoy listo para ayudarte.

Usa /help para ver comandos disponibles.
Modo actual: EJECUCION</div>
                    </div>
                </div>
                
                <div class="typing-indicator" id="typing-indicator">
                    <span></span><span></span><span></span> Brain está pensando...
                </div>
                
                <div class="chat-input-container">
                    <input type="text" class="chat-input" id="message-input" 
                           placeholder="Escribe tu mensaje o comando..." 
                           onkeypress="handleKeyPress(event)">
                    <button class="btn btn-primary" onclick="sendMessage()">Enviar</button>
                </div>
            </div>
            
            <div class="sidebar">
                <h3>📋 Comandos Rápidos</h3>
                <ul class="command-list">
                    <li onclick="insertCommand('/status')">/status - Estado</li>
                    <li onclick="insertCommand('/phase')">/phase - Fases</li>
                    <li onclick="insertCommand('/pocketoption')">/pocketoption - Trading</li>
                    <li onclick="insertCommand('/advisor')">/advisor - Consultar</li>
                    <li onclick="insertCommand('/mode')">/mode - Cambiar modo</li>
                    <li onclick="insertCommand('/pending')">/pending - Pendientes</li>
                    <li onclick="insertCommand('/help')">/help - Ayuda</li>
                </ul>
                
                <div class="pending-operations" id="pending-operations">
                    <h3>⏳ Operaciones Pendientes</h3>
                    <div id="pending-list"></div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Modal de Confirmación -->
    <div class="modal-overlay" id="confirm-modal">
        <div class="modal">
            <h2>⚠️ Confirmación Requerida</h2>
            <div class="modal-content" id="modal-content">
                <p>Operación crítica detectada. Se requiere confirmación.</p>
            </div>
            <input type="text" class="code-input" id="confirm-code" 
                   placeholder="CÓDIGO" maxlength="8">
            <div class="modal-actions">
                <button class="btn btn-success" onclick="submitConfirmation()">Confirmar</button>
                <button class="btn btn-danger" onclick="closeModal()">Cancelar</button>
            </div>
        </div>
    </div>
    
    <script>
        let currentConfirmationCode = null;
        let ws = null;
        
        // Conectar WebSocket
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = function() {
                console.log('WebSocket conectado');
            };
            
            ws.onmessage = function(event) {
                const response = JSON.parse(event.data);
                handleResponse(response);
            };
            
            ws.onclose = function() {
                console.log('WebSocket desconectado, reconectando...');
                setTimeout(connectWebSocket, 3000);
            };
        }
        
        // Enviar mensaje
        async function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            // Agregar mensaje del usuario
            addMessage(message, 'user');
            input.value = '';
            
            // Mostrar indicador de escritura
            document.getElementById('typing-indicator').classList.add('active');
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                handleResponse(data);
                
            } catch (error) {
                addMessage('Error de conexión: ' + error.message, 'error');
            } finally {
                document.getElementById('typing-indicator').classList.remove('active');
            }
            
            // Actualizar pendientes
            updatePendingOperations();
        }
        
        // Manejar respuesta
        function handleResponse(data) {
            if (data.requires_confirmation) {
                currentConfirmationCode = data.confirmation_code;
                showConfirmationModal(data.message, data.confirmation_code);
            } else if (data.success) {
                addMessage(data.message, 'bot');
                if (data.data) {
                    addMessage(JSON.stringify(data.data, null, 2), 'system');
                }
            } else {
                addMessage(data.message, 'error');
            }
            
            // Actualizar modo si cambió
            if (data.operation_level) {
                updateModeIndicator(data.operation_level);
            }
        }
        
        // Agregar mensaje al chat
        function addMessage(text, type) {
            const container = document.getElementById('chat-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message message-${type}`;
            
            const header = document.createElement('div');
            header.className = 'message-header';
            header.textContent = type === 'user' ? '👤 Tú' : 
                                type === 'bot' ? '🤖 Brain' : 
                                type === 'error' ? '❌ Error' : 'ℹ️ Sistema';
            
            const content = document.createElement('div');
            content.className = 'message-content';
            
            if (type === 'system' && text.startsWith('{')) {
                content.innerHTML = `<div class="json-output">${escapeHtml(text)}</div>`;
            } else {
                content.textContent = text;
            }
            
            messageDiv.appendChild(header);
            messageDiv.appendChild(content);
            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }
        
        // Mostrar modal de confirmación
        function showConfirmationModal(message, code) {
            document.getElementById('modal-content').innerHTML = `<p>${escapeHtml(message)}</p>`;
            document.getElementById('confirm-code').value = '';
            document.getElementById('confirm-modal').classList.add('active');
            currentConfirmationCode = code;
        }
        
        // Cerrar modal
        function closeModal() {
            document.getElementById('confirm-modal').classList.remove('active');
            currentConfirmationCode = null;
        }
        
        // Enviar confirmación
        async function submitConfirmation() {
            const code = document.getElementById('confirm-code').value.toUpperCase();
            
            if (!code) {
                alert('Ingresa el código de confirmación');
                return;
            }
            
            try {
                const response = await fetch('/api/confirm', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        code: code,
                        command: 'process',
                        target: ''
                    })
                });
                
                const data = await response.json();
                closeModal();
                handleResponse(data);
                
            } catch (error) {
                alert('Error: ' + error.message);
            }
            
            updatePendingOperations();
        }
        
        // Actualizar operaciones pendientes
        async function updatePendingOperations() {
            try {
                const response = await fetch('/api/pending');
                const data = await response.json();
                
                const container = document.getElementById('pending-list');
                
                if (data.count === 0) {
                    container.innerHTML = '<p style="opacity: 0.5; font-size: 12px;">No hay operaciones pendientes</p>';
                    return;
                }
                
                container.innerHTML = data.operations.map(op => `
                    <div class="pending-item">
                        <div class="code">${op.code}</div>
                        <div style="font-size: 11px; opacity: 0.7;">${op.command}</div>
                        <div style="font-size: 11px; opacity: 0.7;">Expira: ${op.time_remaining}s</div>
                        <div class="pending-actions">
                            <button class="btn btn-success" onclick="confirmOperation('${op.code}')">✓</button>
                            <button class="btn btn-danger" onclick="cancelOperation('${op.code}')">✗</button>
                        </div>
                    </div>
                `).join('');
                
            } catch (error) {
                console.error('Error actualizando pendientes:', error);
            }
        }
        
        // Confirmar operación específica
        async function confirmOperation(code) {
            document.getElementById('confirm-code').value = code;
            submitConfirmation();
        }
        
        // Cancelar operación
        async function cancelOperation(code) {
            try {
                await fetch('/api/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                updatePendingOperations();
                addMessage(`Operación ${code} cancelada`, 'system');
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        // Actualizar indicador de modo
        function updateModeIndicator(mode) {
            const indicator = document.getElementById('mode-indicator');
            indicator.className = `mode-indicator mode-${mode}`;
            indicator.textContent = mode;
        }
        
        // Insertar comando
        function insertCommand(cmd) {
            document.getElementById('message-input').value = cmd;
            document.getElementById('message-input').focus();
        }
        
        // Manejar tecla Enter
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        // Escapar HTML
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Actualizar estado de conexiones
        async function updateConnectionStatus() {
            try {
                const response = await fetch('/health');
                const data = await response.json();
                
                document.getElementById('brain-status').className = 
                    `status-dot ${data.connections.brain_api ? 'status-online' : 'status-offline'}`;
                document.getElementById('advisor-status').className = 
                    `status-dot ${data.connections.advisor_api ? 'status-online' : 'status-offline'}`;
                
                updateModeIndicator(data.mode);
            } catch (error) {
                console.error('Error actualizando estado:', error);
            }
        }
        
        // Inicializar
        document.addEventListener('DOMContentLoaded', function() {
            connectWebSocket();
            updateConnectionStatus();
            updatePendingOperations();
            
            // Actualizar periódicamente
            setInterval(updateConnectionStatus, 5000);
            setInterval(updatePendingOperations, 3000);
        });
    </script>
</body>
</html>
"""


@app.get("/ui", response_class=HTMLResponse)
async def ui_endpoint():
    """Sirve la UI HTML"""
    return HTMLResponse(content=HTML_UI)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"""
╔══════════════════════════════════════════════════════════════╗
║                    BRAIN CHAT V3 SERVER                      ║
║                        Version {APP_VERSION}                          ║
╠══════════════════════════════════════════════════════════════╣
║  Puerto: {PORT}                                            ║
║  Modo: {chat_server.current_mode.value}                                          ║
╠══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                  ║
║    - http://127.0.0.1:{PORT}/          (API Root)              ║
║    - http://127.0.0.1:{PORT}/ui        (Interfaz Web)          ║
║    - http://127.0.0.1:{PORT}/api/chat  (API Chat)             ║
║    - ws://127.0.0.1:{PORT}/ws          (WebSocket)             ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="info"
    )
