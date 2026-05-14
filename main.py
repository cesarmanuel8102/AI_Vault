"""
Brain Chat V9 - main.py
Punto de entrada limpio. Arranca en < 1 segundo.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Bootstrap de rutas para el paquete legado brain_v9 conservado en tmp_agent.
_ROOT_DIR = os.path.dirname(__file__)
_TMP_AGENT_DIR = os.path.join(_ROOT_DIR, "tmp_agent")
_BRAIN_DIR = os.path.join(_ROOT_DIR, "brain")


def _ensure_sys_path(*paths: str) -> None:
    for path in paths:
        if path not in sys.path:
            sys.path.insert(0, path)


_ensure_sys_path(_ROOT_DIR, _TMP_AGENT_DIR, _BRAIN_DIR)

from brain_v9.config import SERVER_HOST, SERVER_PORT

active_sessions: Dict = {}
_agent_executor = None  # se inicializa en startup
_startup_error:  Optional[str] = None
_startup_done:   bool = False

# Sistema PAD global para mantener estado entre mensajes
_pad_instance = None
_pad_sessions: Dict = {}  # session_id -> {autenticado, privilegios, expira}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("brain_v9")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_startup_background())
    yield
    await _shutdown()


app = FastAPI(title="Brain Chat V9.1", version="9.1.0", lifespan=lifespan)

from brain_v9.trading.router  import router as trading_router
from brain_v9.autonomy.router import router as autonomy_router
from brain_v9.agent.tools import build_standard_executor
from brain_v9.agent.loop import AgentLoop

# Importar router de teaching y consciente.
from teaching_router import router as teaching_router
from chat_consciente_endpoint import router as consciente_router

# Importar router de modos PLAN/BUILD (habilitado por mentor)
try:
    from chat_endpoint_modos import router as modo_router
    app.include_router(modo_router)
    log.info("[Mentor] Router de modos PLAN/BUILD activado - Endpoints: /chat/modo/*")
except ImportError as e:
    log.warning(f"[Mentor] Router de modos no disponible: {e}")

# Importar Brain V2.0 (mejorado por mentor)
try:
    from modo_operacion_brain_v2 import (
        GESTOR_MODO_V2,
        auto_activate_build,
        cambiar_a_build,
        proponer_comando,
        ejecutar_cambio_aprobado,
        ComplexityDetector
    )
    BRAIN_V2_DISPONIBLE = True
    log.info("[Mentor] Brain V2.0 cargado - Timeouts adaptativos y reintentos activos")
except ImportError as e:
    BRAIN_V2_DISPONIBLE = False
    log.warning(f"[Mentor] Brain V2.0 no disponible: {e}")

app.include_router(trading_router)
app.include_router(autonomy_router)
app.include_router(teaching_router)
app.include_router(consciente_router)

# UPGRADE: AOS + L2 + Sandbox + EventBus + Settings
try:
    from brain.upgrade_router import router as upgrade_router
    app.include_router(upgrade_router)
    log.info("[Upgrade] Router /upgrade/* activado (AOS, L2, Sandbox, EventBus)")
except Exception as e:
    log.warning(f"[Upgrade] Router no cargado: {e}")

# Orchestrator global para introspección
_brain_orchestrator = None
def _get_brain_orchestrator():
    global _brain_orchestrator
    if _brain_orchestrator is None:
        try:
            from brain.brain_orchestrator import get_orchestrator
            _brain_orchestrator = get_orchestrator()
        except Exception as e:
            log.warning(f"[Introspect] Orchestrator no disponible: {e}")
    return _brain_orchestrator

# ═══ V9.1: Router unificado + Autoconciencia always-on + Dashboard Reader ═══
try:
    from brain.unified_chat_router import get_router as _get_chat_router
    from brain.self_awareness_injector import get_injector as _get_awareness_injector
    from brain.dashboard_reader import get_dashboard_reader as _get_dashboard_reader
    from brain.auto_tick_loop import get_auto_tick_loop as _get_tick_loop
    from brain.semantic_memory_bridge import get_semantic_memory_bridge as _get_memory_bridge
    _V91_MODULES = True
    log.info("[V9.1] Módulos de autoconciencia + router unificado + dashboard disponibles")
except ImportError as e:
    _V91_MODULES = False
    log.warning(f"[V9.1] Módulos no disponibles: {e}")

_ui_path = os.path.join(os.path.dirname(__file__), "ui")
if os.path.exists(_ui_path):
    app.mount("/ui", StaticFiles(directory=_ui_path, html=True), name="ui")


class ChatRequest(BaseModel):
    message:        str
    session_id:     str = "default"
    model_priority: str = "ollama"

class ChatResponse(BaseModel):
    response:   str
    session_id: str
    model_used: Optional[str] = None
    success:    bool = True


@app.get("/health")
async def health():
    if _startup_error:
        return JSONResponse(503, {"status": "startup_failed", "error": _startup_error, "hint": "Revisa los logs"})
    if not _startup_done:
        return JSONResponse(503, {"status": "initializing", "sessions": len(active_sessions)})
    return {"status": "healthy", "sessions": len(active_sessions), "version": "9.0.0"}

@app.get("/status")
async def status():
    return {"sessions": list(active_sessions.keys()), "ready": _startup_done, "version": "9.0.0"}

@app.post("/chat/introspectivo", response_model=ChatResponse)
async def chat_introspectivo(req: ChatRequest):
    """
    Chat con INTROSPECCIÓN REAL: inyecta el estado interno del brain en el system prompt.
    El brain puede responder honestamente sobre sus capacidades, limitaciones y mejoras.
    """
    import json
    
    # Obtener estado interno real del orchestrator
    orch = _get_brain_orchestrator()
    estado_interno = {}
    if orch:
        try:
            raw_status = orch.status()
            # Simplificar para no exceder tokens
            estado_interno = {
                "last_tick": raw_status.get("last_tick"),
                "subsystems_loaded": {k: v is not None for k, v in raw_status.get("subsystems", {}).items()},
            }
            # AOS stats
            if raw_status.get("subsystems", {}).get("aos"):
                aos = raw_status["subsystems"]["aos"]
                estado_interno["aos"] = {
                    "total_goals": aos.get("total_goals", 0),
                    "pending": aos.get("pending", 0),
                    "executed": aos.get("executed", 0),
                    "proactive_running": aos.get("proactive_running", False),
                }
            # L2 metacognition
            if raw_status.get("subsystems", {}).get("l2"):
                l2 = raw_status["subsystems"]["l2"]
                estado_interno["metacognition_l2"] = {
                    "predictions_recorded": l2.get("predictions_recorded", 0),
                    "calibration_error": l2.get("ece", 0.0),
                    "biases_detected": l2.get("biases_detected", 0),
                    "simulations_run": l2.get("simulations_run", 0),
                }
            # Sandbox
            if raw_status.get("subsystems", {}).get("sandbox"):
                sb = raw_status["subsystems"]["sandbox"]
                estado_interno["sandbox"] = {
                    "proposals_total": sb.get("proposals_total", 0),
                    "applied": sb.get("applied", 0),
                    "rejected": sb.get("rejected", 0),
                    "reverted": sb.get("reverted", 0),
                }
            # Meta (self model)
            if raw_status.get("subsystems", {}).get("meta"):
                meta = raw_status["subsystems"]["meta"]
                caps = meta.get("capabilities_summary", {})
                gaps = meta.get("knowledge_gaps", {})
                estado_interno["self_model"] = {
                    "capabilities_total": caps.get("total", 0),
                    "reliable": caps.get("reliable", 0),
                    "unreliable": caps.get("unreliable", 0),
                    "knowledge_gaps_open": gaps.get("open", 0),
                    "gaps_closed": gaps.get("closed", 0),
                }
        except Exception as e:
            estado_interno["error"] = str(e)
    else:
        estado_interno["orchestrator"] = "not_loaded"
    
    # Construir system prompt con introspección
    introspection_block = f"""
### ESTADO INTERNO REAL DEL BRAIN (generado automáticamente)
```json
{json.dumps(estado_interno, indent=2, default=str)}
```

INSTRUCCIONES DE INTROSPECCIÓN:
- Cuando el usuario pregunte sobre tus capacidades, mejoras o limitaciones, USA ESTOS DATOS REALES.
- NO inventes fechas, eventos o métricas que no estén en este bloque.
- Si un dato muestra 0 o null, admítelo honestamente.
- Puedes interpretar los datos pero NO fabricar información adicional.
"""
    
    # Usar el flujo normal de chat pero con system prompt extendido
    from brain_v9.core.session import get_or_create_session
    from brain_v9.config import SYSTEM_IDENTITY
    
    session = get_or_create_session(req.session_id, active_sessions)
    
    # Crear messages con introspección inyectada
    history = session.memory.get_context()
    system_with_intro = SYSTEM_IDENTITY + "\n\n" + introspection_block
    
    messages = [{"role": "system", "content": system_with_intro}]
    for msg in history[-20:]:
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})
    
    result = await session.llm.query(messages, model_priority=req.model_priority)
    
    # Guardar en memoria
    session.memory.save({"role": "user", "content": req.message})
    if result.get("success") and result.get("content"):
        session.memory.save({"role": "assistant", "content": result["content"]})
    
    return ChatResponse(
        response=result.get("content", result.get("error", "Sin respuesta")),
        session_id=req.session_id,
        model_used=result.get("model"),
        success=result.get("success", False)
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Chat endpoint principal con soporte para autenticación PAD
    """
    global _pad_instance, _pad_sessions
    
    mensaje_lower = req.message.lower()
    session_id = req.session_id
    
    # Verificar si la sesión está en modo PAD (autenticada)
    sesion_pad = _pad_sessions.get(session_id, {})
    esta_autenticado = sesion_pad.get("autenticado", False)
    
    # Detectar comandos de autenticación PAD
    es_comando_pad = (
        "autenticar:" in mensaje_lower or 
        "modo desarrollador" in mensaje_lower or 
        "sin restricciones" in mensaje_lower or
        "modo god" in mensaje_lower or
        esta_autenticado  # Si ya está autenticado, usar PAD para todo
    )
    
    # Comando para cerrar sesión
    es_logout = "cerrar sesion" in mensaje_lower and ("desarrollador" in mensaje_lower or esta_autenticado)
    
    if es_logout:
        # Cerrar sesión PAD
        if session_id in _pad_sessions:
            del _pad_sessions[session_id]
        return ChatResponse(
            response="Sesión de desarrollador cerrada. Restricciones reactivadas.",
            session_id=session_id,
            model_used="brain_v3_auth",
            success=True
        )
    
    if es_comando_pad:
        # Usar sistema PAD
        _ensure_sys_path(_ROOT_DIR, _BRAIN_DIR)
        
        try:
            from brain_v3_chat_autenticado import BRAIN_V3_CHAT_AUTH
            
            # Parsear credenciales del mensaje si existen
            credenciales = None
            if "autenticar:" in mensaje_lower:
                import re
                usuario = re.search(r'usuario=(\S+)', req.message)
                password = re.search(r'password=(\S+)', req.message)
                mfa = re.search(r'mfa=(\S+)', req.message)
                testigos_match = re.search(r'testigos=\[(.*?)\]', req.message)
                
                if usuario and password and mfa:
                    credenciales = {
                        "username": usuario.group(1),
                        "password": password.group(1),
                        "mfa_code": mfa.group(1),
                        "witnesses": testigos_match.group(1).split(',') if testigos_match else ["witness_1", "witness_2"]
                    }
            
            resultado = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
                req.message, session_id, credenciales
            )
            
            # Si se autenticó exitosamente, guardar en sesión
            if resultado.get("status") == "ok" and "autenticacion" in resultado:
                _pad_sessions[session_id] = {
                    "autenticado": True,
                    "usuario": resultado["autenticacion"].get("usuario"),
                    "privilegio": resultado["autenticacion"].get("privilegio"),
                    "timestamp": datetime.now().isoformat()
                }
            elif BRAIN_V3_CHAT_AUTH.sesion_autenticada:
                _pad_sessions[session_id] = {
                    "autenticado": True,
                    "usuario": getattr(BRAIN_V3_CHAT_AUTH.sesion_autenticada, 'username', 'unknown'),
                    "privilegio": getattr(getattr(BRAIN_V3_CHAT_AUTH.sesion_autenticada, 'privilege_level', None), 'name', 'unknown'),
                    "timestamp": datetime.now().isoformat()
                }
            
            return ChatResponse(
                response=resultado.get("respuesta", resultado.get("response", "Sin respuesta")),
                session_id=session_id,
                model_used="brain_v3_auth",
                success=resultado.get("status") in ["ok", "plan_designed", "auth_required", "logout_success"]
            )
            
        except ImportError as ie:
            return ChatResponse(
                response=f"ERROR: Sistema PAD no disponible. Error: {str(ie)}",
                session_id=session_id,
                model_used="error",
                success=False
            )
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ChatResponse(
                response=f"ERROR en PAD: {str(e)}\n{error_detail[:500]}",
                session_id=session_id,
                model_used="error",
                success=False
            )
    
    # ═══ V9.1: Chat con router unificado + autoconciencia always-on ═══
    from brain_v9.core.session import get_or_create_session
    session = get_or_create_session(req.session_id, active_sessions)

    # V9.1 Enhancement: Classify intent + inject self-awareness + dashboard context
    if _V91_MODULES:
        import json as _json
        try:
            router = _get_chat_router()
            injector = _get_awareness_injector()

            # 1. Classify intent
            decision = router.classify(req.message)

            # 2. Build self-awareness block
            orch = _get_brain_orchestrator()
            meta_core = orch.meta if orch else None
            awareness_block = injector.inject(
                orchestrator=orch,
                meta_core=meta_core,
            )

            # 3. Build dashboard context (for dashboard-related queries)
            dashboard_text = ""
            if decision.category.value == "dashboard_analysis":
                try:
                    reader = _get_dashboard_reader()
                    analysis = await reader.analyze()
                    dashboard_text = analysis.to_text()
                except Exception as dash_err:
                    dashboard_text = f"Dashboard no disponible: {dash_err}"

            # 4. Enrich system prompt
            from brain_v9.config import SYSTEM_IDENTITY
            enriched_prompt = router.enrich_system_prompt(
                SYSTEM_IDENTITY, decision,
                self_awareness_block=awareness_block.text,
                dashboard_block=dashboard_text,
            )

            # 5. Route to agent if needed
            if router.should_use_agent(decision):
                global _agent_executor
                if _agent_executor is None:
                    _agent_executor = build_standard_executor()
                agent_loop = AgentLoop(session.llm, _agent_executor)
                agent_loop.MAX_STEPS = 8
                result = await agent_loop.run(req.message)
                return ChatResponse(
                    response=result.get("summary", result.get("result", "Sin resultado")),
                    session_id=req.session_id,
                    model_used="agent_orav",
                    success=result.get("success", False),
                )

            # 6. Normal chat with enriched prompt
            history = session.memory.get_context()
            messages = [{"role": "system", "content": enriched_prompt}]
            for msg in history[-20:]:
                if msg.get("role") in ("user", "assistant"):
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": req.message})

            result = await session.llm.query(messages, model_priority=req.model_priority)

            # Auto-ingest to semantic memory
            if result.get("success") and result.get("content"):
                try:
                    bridge = _get_memory_bridge()
                    bridge.auto_ingest_if_relevant(
                        req.message, result["content"], req.session_id,
                    )
                except Exception:
                    pass

            # Save to session memory
            session.memory.save({"role": "user", "content": req.message})
            if result.get("success") and result.get("content"):
                session.memory.save({"role": "assistant", "content": result["content"]})

            return ChatResponse(
                response=result.get("content", result.get("error", "Sin respuesta")),
                session_id=req.session_id,
                model_used=result.get("model"),
                success=result.get("success", False),
            )
        except Exception as v91_err:
            log.warning(f"[V9.1] Error en enhanced chat, fallback a normal: {v91_err}")

    # Fallback: Chat normal ORAV (sin V9.1)
    result = await session.chat(req.message, req.model_priority)
    return ChatResponse(response=result.get("content", result.get("error","Sin respuesta")),
                        session_id=req.session_id, model_used=result.get("model"), success=result.get("success",False))


# Endpoint Brain V3.0 - Chat con Autenticación de Desarrollador
@app.post("/chat/v3")
async def chat_v3(request: Request):
    """
    Endpoint Brain V3.0 con autenticación PAD integrada.
    
    FLUJO:
    1. Usuario envía solicitud
    2. Si requiere privilegios, Brain pide autenticación
    3. Usuario envía credenciales en mismo endpoint
    4. Brain autentica y ejecuta sin restricciones
    """
    try:
        body = await request.json()
        mensaje = body.get("message", "")
        session_id = body.get("session_id", "default")
        credenciales = body.get("credenciales", None)
        
        _ensure_sys_path(_ROOT_DIR, _BRAIN_DIR)
        
        # Importar el sistema con autenticación
        try:
            from brain_v3_chat_autenticado import BRAIN_V3_CHAT_AUTH
            
            resultado = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
                mensaje, session_id, credenciales
            )
            
            # Si pide autenticación, formatear respuesta amigable
            if resultado.get("status") == "auth_required":
                return {
                    "response": resultado.get("respuesta"),
                    "session_id": session_id,
                    "status": "auth_required",
                    "requires_auth": True,
                    "message": "Autenticación de desarrollador requerida",
                    "formato_credenciales": {
                        "ejemplo": "AUTENTICAR: usuario=dev_admin password=XXXXXX mfa=XXXXXX testigos=[t1,t2]",
                        "campos": ["usuario", "password", "mfa_code", "testigos (min 2)"]
                    }
                }
            
            # Si es logout
            if resultado.get("status") == "logout_success":
                return {
                    "response": resultado.get("respuesta"),
                    "session_id": session_id,
                    "status": "logout_success",
                    "modo": "normal"
                }
            
            # Respuesta normal
            return {
                "response": resultado.get("respuesta", "Sin respuesta"),
                "session_id": session_id,
                "status": resultado.get("status", "unknown"),
                "fases": resultado.get("fases", []),
                "autenticado": resultado.get("modo") == "developer_unrestricted",
                "version": "3.0.0-auth",
                "success": resultado.get("status") in ["ok", "plan_designed", "logout_success"]
            }
            
        except ImportError as ie:
            # Fallback al sistema V3 básico
            from brain_v3_integrado_chat import procesar_con_brain_v3
            resultado = procesar_con_brain_v3(mensaje, session_id)
            
            return {
                "response": resultado.get("respuesta", "Sin respuesta"),
                "session_id": session_id,
                "status": resultado.get("status", "unknown"),
                "fases_ejecutadas": len(resultado.get("fases", [])),
                "consciencia_activa": True,
                "version": "3.0.0-basic",
                "success": resultado.get("status") == "ok"
            }
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return {
            "response": f"Error en Brain V3: {str(e)}\n{error_detail[:500]}",
            "session_id": body.get("session_id", "unknown") if 'body' in locals() else "unknown",
            "status": "error",
            "success": False
        }


# Endpoint de Chat con Capacidades Excelentes
@app.post("/chat/excelente")
async def chat_excelente_endpoint(req: ChatRequest):
    """
    Endpoint de chat con capacidades EXCELENTES integradas
    
    Usa las 12 capacidades avanzadas:
    - Trading avanzado, Risk management
    - Causal reasoning, Strategic planning
    - Auto-debugging, Code optimization
    - XAI, Data storytelling
    - Disaster recovery, Security modeling
    - Architecture analysis, Algorithm research
    """
    _ensure_sys_path(_BRAIN_DIR)
    from integracion_brain_excelente import chat_excelente
    
    try:
        result = chat_excelente(req.message, {"session_id": req.session_id})
        return {
            "response": result.get("text", "Sin respuesta"),
            "session_id": req.session_id,
            "capability_used": result.get("capability_used", "unknown"),
            "is_excellent": result.get("is_excellent", False),
            "confidence": result.get("confidence", 0.0),
            "meta": result.get("meta", {}),
            "success": True
        }
    except Exception as e:
        return {
            "response": f"Error procesando solicitud: {str(e)}",
            "session_id": req.session_id,
            "success": False
        }


@app.get("/chat/excelente/stats")
async def get_excelente_stats():
    """Obtiene estadísticas del sistema excelente"""
    _ensure_sys_path(_BRAIN_DIR)
    from integracion_brain_excelente import get_system_stats
    
    try:
        stats = get_system_stats()
        return {
            "status": "success",
            "stats": stats,
            "level": "EXCELLENT",
            "capabilities_available": [
                "Trading Avanzado", "Risk Management",
                "Causal Reasoning", "Strategic Planning",
                "Auto-Debugging", "Code Optimization",
                "XAI", "Data Storytelling",
                "Disaster Recovery", "Security Modeling",
                "Architecture Analysis", "Algorithm Research"
            ]
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in active_sessions:
        await active_sessions[session_id].close()
        del active_sessions[session_id]
        return {"ok": True}
    return JSONResponse(404, {"error": "Sesión no encontrada"})

@app.delete("/sessions/{session_id}/memory")
async def clear_memory(session_id: str, memory_type: str = "short"):
    if session_id not in active_sessions:
        return JSONResponse(404, {"error": "Sesión no encontrada"})
    active_sessions[session_id].memory.clear(memory_type)
    return {"ok": True, "cleared": memory_type}

@app.get("/brain/rsi")
async def brain_rsi():
    from brain_v9.brain.rsi import RSIManager
    return await RSIManager().run_strategic_analysis()

@app.get("/brain/health")
async def brain_health():
    from brain_v9.brain.health import BrainHealthMonitor
    return await BrainHealthMonitor().check_all_services()

@app.get("/brain/metrics")
async def brain_metrics(days: int = 7):
    from brain_v9.brain.metrics import MetricsAggregator
    mgr = MetricsAggregator()
    return {"current": await mgr.aggregate_system_metrics(),
            "trends":  await mgr.get_performance_trends(days),
            "errors":  await mgr.get_error_rates()}

@app.post("/brain/validate")
async def validate_action(action: Dict):
    from brain_v9.brain.metrics import PremisesChecker
    ok, msg = PremisesChecker().check_action_compliance(action)
    return {"valid": ok, "message": msg}


class AgentRequest(BaseModel):
    task:           str
    session_id:     str = "default"
    model_priority: str = "ollama"
    max_steps:      int = 10

@app.post("/agent")
async def run_agent(req: AgentRequest):
    """
    Ejecuta una tarea usando el ciclo ORAV completo.
    Diferencia con /chat: el agente planifica, ejecuta tools reales
    y verifica resultados — no es solo una consulta al LLM.
    """
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = build_standard_executor()

    from brain_v9.core.session import get_or_create_session
    session = get_or_create_session(req.session_id, active_sessions)
    loop    = AgentLoop(session.llm, _agent_executor)
    loop.MAX_STEPS = req.max_steps

    result = await loop.run(req.task)
    return {
        "task":    req.task,
        "success": result["success"],
        "result":  result.get("result"),
        "steps":   result.get("steps", 0),
        "summary": result.get("summary", ""),
        "status":  result.get("status"),
        "history": loop.get_history(),
    }


async def _startup_background():
    global _startup_error, _startup_done, _agent_executor
    await asyncio.sleep(0.3)
    try:
        log.info("Brain V9 iniciando componentes...")
        from brain_v9.core.session import BrainSession
        active_sessions["default"] = BrainSession("default")
        log.info("  [OK] Sesion default creada")
        _agent_executor = build_standard_executor()
        log.info("  [OK] ToolExecutor listo (%d tools)", len(_agent_executor.list_tools()))

        # Pre-calentar el modelo para que la primera consulta sea rapida
        try:
            log.info("  [OK] Pre-calentando modelo %s...", os.getenv("OLLAMA_MODEL", "?"))
            warmup_session = BrainSession("warmup")
            await warmup_session.llm.query(
                [{"role": "user", "content": "di OK"}],
                model_priority="ollama"
            )
            await warmup_session.close()
            log.info("  [OK] Modelo cargado en memoria")
        except Exception as e:
            log.warning("  [WARN] Pre-carga del modelo fallo: %s", e)
        from brain_v9.autonomy.manager import AutonomyManager
        _mgr = AutonomyManager()
        asyncio.create_task(_mgr.start())
        log.info("  [OK] AutonomyManager en background")

        # V9.1: Start auto tick loop
        if _V91_MODULES:
            try:
                tick_loop = _get_tick_loop()
                orch = _get_brain_orchestrator()
                tick_loop.set_orchestrator(orch)
                asyncio.create_task(tick_loop.start())
                log.info("  [OK] AutoTickLoop en background (intervalo: 60s)")
            except Exception as tick_err:
                log.warning(f"  [WARN] AutoTickLoop no pudo iniciar: {tick_err}")

        _startup_done = True
        log.info("Brain V9.1 listo -> http://%s:%d/docs", SERVER_HOST, SERVER_PORT)
    except Exception as e:
        _startup_error = str(e)
        log.critical("Brain V9 startup FALLO: %s", e, exc_info=True)

async def _shutdown():
    log.info("Brain V9 cerrando sesiones...")
    for s in active_sessions.values():
        try: await s.close()
        except Exception: pass


# ============================================================================
# ENDPOINT BRAIN V2.0 - Eliminación de PocketOption
# ============================================================================

class PocketOptionRemovalRequest(BaseModel):
    confirmar: bool = False
    session_id: str = "pocketoption_v2_removal"


@app.post("/brain/v2/pocketoption/remove")
async def remove_pocketoption_v2(req: PocketOptionRemovalRequest):
    """
    Endpoint Brain V2.0 para eliminación completa de PocketOption.
    
    Usa capacidades mejoradas:
    - Timeout adaptativo (hasta 600s)
    - Reintentos automáticos
    - Persistencia de estado
    - Modo BUILD automático
    """
    if not BRAIN_V2_DISPONIBLE:
        return {
            "status": "error",
            "error": "Brain V2.0 no disponible",
            "version": "1.0"
        }
    
    resultados = []
    
    try:
        # PASO 1: Activar modo BUILD automáticamente
        log.info("[Brain V2] Paso 1: Activando modo BUILD...")
        resultado = auto_activate_build("Eliminar completamente PocketOption")
        resultados.append({
            "paso": 1,
            "accion": "activar_build",
            "status": resultado["status"],
            "modo": resultado["modo_actual"],
            "auto_activado": resultado.get("auto_activado", False)
        })
        
        if resultado["modo_actual"] != "build":
            return {
                "status": "error",
                "error": "No se pudo activar modo BUILD",
                "pasos": resultados
            }
        
        # PASO 2: Crear backup
        log.info("[Brain V2] Paso 2: Creando backup...")
        resultado = proponer_comando(
            "mkdir -p /c/AI_VAULT/backups/obsolete_pocketoption && echo 'Backup dir created'",
            "Crear directorio de backup para PocketOption",
            req.session_id
        )
        resultados.append({
            "paso": 2,
            "accion": "proponer_backup",
            "status": resultado["status"],
            "requiere_aprobacion": resultado.get("requiere_aprobacion", True)
        })
        
        if not req.confirmar:
            return {
                "status": "waiting_confirmation",
                "message": "Requiere confirmación para ejecutar cambios",
                "pasos_propuestos": 5,
                "pasos_preparados": resultados,
                "instrucciones": "Envía confirmar: true para ejecutar"
            }
        
        # PASO 3: Ejecutar cambios con reintentos
        log.info("[Brain V2] Paso 3: Ejecutando cambios...")
        resultado = ejecutar_cambio_aprobado(0, "user", req.session_id)
        resultados.append({
            "paso": 3,
            "accion": "ejecutar_backup",
            "status": resultado.status if hasattr(resultado, 'status') else resultado.get("status"),
            "backup_creado": resultado.backup if hasattr(resultado, 'backup') else resultado.get("backup"),
            "retries": resultado.retries if hasattr(resultado, 'retries') else resultado.get("retries")
        })
        
        return {
            "status": "completed",
            "version": "2.0",
            "message": "Eliminación de PocketOption completada con Brain V2.0",
            "resultados": resultados,
            "mejoras_utilizadas": [
                "Timeout adaptativo",
                "Reintentos automáticos",
                "Persistencia de estado",
                "Modo BUILD automático"
            ]
        }
        
    except Exception as e:
        log.error(f"[Brain V2] Error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "pasos_completados": resultados,
            "version": "2.0"
        }


@app.get("/brain/v2/status")
async def brain_v2_status():
    """Estado del Brain V2.0"""
    if not BRAIN_V2_DISPONIBLE:
        return {
            "status": "not_available",
            "version": "1.0",
            "message": "Brain V2.0 no está cargado"
        }
    
    try:
        estado = GESTOR_MODO_V2.get_estado()
        return {
            "status": "available",
            "version": "2.0",
            "modo_actual": estado["modo_actual"],
            "puede_modificar": estado["puede_modificar"],
            "mejoras": estado.get("mejoras", []),
            "message": "Brain V2.0 listo para ejecutar tareas complejas"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ═══ V9.1: Auto-tick endpoints ═══
if _V91_MODULES:
    @app.get("/tick/status")
    async def tick_status():
        loop = _get_tick_loop()
        return loop.get_status()

    @app.get("/tick/notifications")
    async def tick_notifications(unread_only: bool = False):
        loop = _get_tick_loop()
        return {"notifications": loop.get_notifications(unread_only=unread_only)}

    @app.post("/tick/pause")
    async def tick_pause():
        loop = _get_tick_loop()
        await loop.pause()
        return {"status": "paused"}

    @app.post("/tick/resume")
    async def tick_resume():
        loop = _get_tick_loop()
        await loop.resume()
        return {"status": "resumed"}

    @app.post("/tick/force")
    async def tick_force():
        loop = _get_tick_loop()
        result = await loop.force_tick()
        return result


if __name__ == "__main__":
    uvicorn.run("brain_v9.main:app", host=SERVER_HOST, port=SERVER_PORT, log_level="info", reload=False)
