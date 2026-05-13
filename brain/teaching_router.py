"""
TEACHING_ROUTER.PY
Endpoints FastAPI para sistema de Teaching y Meta-Cognición

Integra con:
- brain/meta_cognition_core.py
- brain/teaching_interface.py
- agent/loop.py (modo agente)
- ui/index.html (dashboard)
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime

# Importar sistemas de consciencia ampliada
import sys
sys.path.insert(0, 'C:/AI_VAULT')

from brain.meta_cognition_core import initialize_enhanced_consciousness
from brain.teaching_interface import initialize_teaching_system


# ─── INICIALIZACIÓN ─────────────────────────────────────────────────────────────
router = APIRouter(prefix="/teaching", tags=["teaching"])

# Singletons - se inicializan una vez
meta_cognition = None
teaching_system = None

def get_meta_cognition():
    global meta_cognition
    if meta_cognition is None:
        meta_cognition = initialize_enhanced_consciousness()
    return meta_cognition

def get_teaching_system():
    global teaching_system
    if teaching_system is None:
        teaching_system = initialize_teaching_system()
    return teaching_system


# ─── MODELOS Pydantic ─────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    topic: str
    objectives: Optional[List[str]] = None

class PhaseRequest(BaseModel):
    phase: str  # ingesta, prueba, resultados, evaluacion, mejora
    content: Optional[str] = None
    type: Optional[str] = "conceptual"
    result: Optional[str] = None
    self_assessment: Optional[Dict[str, Any]] = None
    action: Optional[str] = None
    mentor_notes: Optional[str] = None

class ValidateRequest(BaseModel):
    passed: bool
    score: float
    feedback: str

class CheckpointApprovalRequest(BaseModel):
    checkpoint_id: str
    approver: str

class CommandRequest(BaseModel):
    command: str
    args: Optional[Dict[str, Any]] = {}


# ─── ENDPOINTS ──────────────────────────────────────────────────────────────────

@router.post("/session/start")
async def start_session(request: StartSessionRequest):
    """Inicia nueva sesión de enseñanza"""
    try:
        teaching = get_teaching_system()
        result = teaching.handle_chat_command("start", {
            "topic": request.topic,
            "objectives": request.objectives or []
        })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/status")
async def get_session_status():
    """Obtiene estado actual de la sesión"""
    try:
        teaching = get_teaching_system()
        return teaching.get_chat_state()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/phase")
async def process_phase(request: PhaseRequest):
    """Procesa una fase del teaching loop"""
    try:
        teaching = get_teaching_system()
        
        if request.phase == "ingesta":
            return teaching.process_ingesta(request.content or "")
        
        elif request.phase == "prueba":
            return teaching.process_prueba(request.type or "conceptual")
        
        elif request.phase == "resultados":
            return teaching.submit_prueba_result(
                request.result or "",
                request.self_assessment or {}
            )
        
        elif request.phase == "evaluacion":
            return teaching.process_evaluacion(request.mentor_notes)
        
        elif request.phase == "mejora":
            return teaching.process_mejora(request.action or "auto")
        
        else:
            raise HTTPException(status_code=400, detail=f"Fase inválida: {request.phase}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/validate")
async def validate_result(request: ValidateRequest):
    """Valida resultado de prueba"""
    try:
        teaching = get_teaching_system()
        outcome = {
            "passed": request.passed,
            "score": request.score,
            "feedback": request.feedback
        }
        return teaching.process_resultados(outcome)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/checkpoint")
async def create_checkpoint():
    """Crea checkpoint de validación"""
    try:
        teaching = get_teaching_system()
        checkpoint = teaching.create_checkpoint()
        return {
            "status": "checkpoint_created",
            "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None,
            "requires_approval": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/checkpoint/approve")
async def approve_checkpoint(request: CheckpointApprovalRequest):
    """Aprueba checkpoint"""
    try:
        teaching = get_teaching_system()
        return teaching.approve_checkpoint(request.checkpoint_id, request.approver)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/rollback")
async def rollback_session():
    """Hace rollback a checkpoint anterior"""
    try:
        teaching = get_teaching_system()
        return teaching.rollback_checkpoint()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/session/end")
async def end_session():
    """Finaliza sesión actual"""
    try:
        teaching = get_teaching_system()
        return teaching.handle_chat_command("end")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── ENDPOINTS DE META-COGNICIÓN ────────────────────────────────────────────────

@router.get("/metacognition/self-awareness")
async def get_self_awareness():
    """Obtiene reporte completo de auto-conciencia"""
    try:
        meta = get_meta_cognition()
        return meta.get_self_awareness_report()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metacognition/teaching-status")
async def get_teaching_readiness():
    """Obtiene estado de preparación para teaching"""
    try:
        meta = get_meta_cognition()
        return meta.get_teaching_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metacognition/capabilities")
async def get_capabilities():
    """Lista todas las capacidades del sistema"""
    try:
        meta = get_meta_cognition()
        caps = meta.self_model.capabilities
        return {
            "capabilities": [
                {
                    "name": name,
                    "confidence": cap.confidence,
                    "evidence_count": cap.evidence_count,
                    "reliable": cap.is_reliable(),
                    "limitations": cap.known_limitations
                }
                for name, cap in caps.items()
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metacognition/gaps")
async def get_knowledge_gaps():
    """Lista brechas de conocimiento"""
    try:
        meta = get_meta_cognition()
        gaps = meta.self_model.known_gaps
        return {
            "gaps": [
                {
                    "id": gap.gap_id,
                    "domain": gap.domain,
                    "description": gap.description,
                    "impact": gap.impact_if_known,
                    "status": gap.resolution_status,
                    "attempts": len(gap.attempted_approaches)
                }
                for gap in gaps
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metacognition/assess-capability")
async def assess_capability(name: str, success: bool, context: str = ""):
    """Actualiza evaluación de una capacidad"""
    try:
        meta = get_meta_cognition()
        cap = meta.assess_capability(name, success, context)
        return {
            "capability": name,
            "confidence": cap.confidence,
            "evidence_count": cap.evidence_count,
            "reliable": cap.is_reliable()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/metacognition/identify-gap")
async def identify_gap(domain: str, description: str, impact: float = 0.5):
    """Registra nueva brecha de conocimiento"""
    try:
        meta = get_meta_cognition()
        gap = meta.identify_knowledge_gap(domain, description, impact)
        return {
            "gap_id": gap.gap_id,
            "domain": gap.domain,
            "impact": gap.impact_if_known,
            "status": "registered"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── ENDPOINTS DE DASHBOARD ─────────────────────────────────────────────────────

@router.get("/dashboard/state")
async def get_dashboard_state():
    """Obtiene estado completo para dashboard"""
    try:
        teaching = get_teaching_system()
        meta = get_meta_cognition()
        
        teaching_state = teaching.get_dashboard_state()
        meta_report = meta.get_self_awareness_report()
        
        # Unificar estado
        unified_state = {
            "teaching": teaching_state,
            "metacognition": meta_report,
            "timestamp": datetime.now().isoformat(),
            "system_ready": meta_report["stress_level"] < 0.5
        }
        
        return unified_state
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/chat-messages")
async def get_chat_messages(limit: int = 20):
    """Obtiene mensajes recientes para chat"""
    try:
        teaching = get_teaching_system()
        state = teaching.get_chat_state()
        messages = state.get("messages", [])
        return {
            "messages": messages[-limit:],
            "has_active_session": state.get("active", False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/metrics")
async def get_dashboard_metrics():
    """Obtiene métricas para visualización"""
    try:
        teaching = get_teaching_system()
        meta = get_meta_cognition()
        
        teaching_state = teaching.get_dashboard_state()
        
        metrics = {
            "learning_progress": teaching_state.get("teaching_session", {}).get("progress_percentage", 0),
            "success_rate": teaching_state.get("teaching_session", {}).get("success_rate", 0),
            "self_awareness": teaching_state.get("meta_cognition", {}).get("metacognition_metrics", {}).get("self_awareness_depth", 0),
            "prediction_accuracy": teaching_state.get("meta_cognition", {}).get("metacognition_metrics", {}).get("prediction_accuracy", 0),
            "unknown_unknowns_risk": teaching_state.get("meta_cognition", {}).get("unknown_unknowns_risk", 0),
            "stress_level": teaching_state.get("meta_cognition", {}).get("stress_level", 0),
            "resilience_mode": teaching_state.get("meta_cognition", {}).get("resilience_mode", "unknown"),
        }
        
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── COMANDOS DEL CHAT ────────────────────────────────────────────────────────────

@router.post("/chat/command")
async def handle_chat_command(request: CommandRequest):
    """Procesa comandos del chat"""
    try:
        teaching = get_teaching_system()
        result = teaching.handle_chat_command(request.command, request.args)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── ENDPOINTS UTILITARIOS ──────────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """Health check del sistema de teaching"""
    try:
        meta = get_meta_cognition()
        teaching = get_teaching_system()
        
        return {
            "status": "healthy",
            "meta_cognition_ready": True,
            "teaching_system_ready": True,
            "session_active": teaching.current_session is not None,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


@router.post("/reset")
async def reset_system():
    """Resetea sistemas (usar con precaución)"""
    global meta_cognition, teaching_system
    meta_cognition = None
    teaching_system = None
    return {"status": "reset_complete"}


# ─── INTEGRACIÓN CON AGENTE ─────────────────────────────────────────────────────

@router.post("/agent/simulate-action")
async def simulate_action(action: str, prerequisites: Optional[List[str]] = None):
    """Simula una acción antes de ejecutarla (integración con agente)"""
    try:
        meta = get_meta_cognition()
        sim = meta.simulate_action(action, prerequisites or [])
        return {
            "simulation_id": sim.simulation_id,
            "confidence": sim.confidence,
            "risks": sim.risks_identified,
            "prerequisites": sim.prerequisites,
            "rollback_plan": sim.rollback_plan
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/record-outcome")
async def record_simulation_outcome(simulation_id: str, outcome: Dict[str, Any]):
    """Registra outcome real de una simulación"""
    try:
        meta = get_meta_cognition()
        meta.record_actual_outcome(simulation_id, outcome)
        return {"status": "recorded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── FUNCIÓN DE INICIALIZACIÓN ─────────────────────────────────────────────────

def initialize_teaching_router(app):
    """
    Inicializa el router en la aplicación FastAPI
    
    Usage:
        from fastapi import FastAPI
        from brain.teaching_router import initialize_teaching_router
        
        app = FastAPI()
        initialize_teaching_router(app)
    """
    app.include_router(router)
    print("[Teaching Router] Inicializado correctamente")
    print("  - Endpoints disponibles en: /teaching/*")
    print("  - Dashboard: GET /teaching/dashboard/state")
    print("  - Meta-cognición: GET /teaching/metacognition/self-awareness")
    print("  - Session: POST /teaching/session/start")


# Para testing directo
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(title="Brain Teaching System")
    initialize_teaching_router(app)
    
    uvicorn.run(app, host="0.0.0.0", port=8091)
