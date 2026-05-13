"""
BRAIN_V2_WRAPPER.PY
Integración del Brain V2.0 con el sistema existente

Este wrapper permite usar las capacidades mejoradas del Brain V2.0
mientras se mantiene compatibilidad con los endpoints existentes.
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json

# Importar sistema V2
try:
    from modo_operacion_brain_v2 import (
        GESTOR_MODO_V2,
        cambiar_a_build,
        cambiar_a_plan,
        auto_activate_build,
        proponer_modificacion_archivo,
        proponer_comando,
        ejecutar_cambio_aprobado,
        ComplexityDetector,
        Config
    )
    V2_DISPONIBLE = True
except ImportError as e:
    print(f"[Brain V2 Wrapper] Error importando V2: {e}")
    V2_DISPONIBLE = False

# Fallback a V1 si V2 no está disponible
if not V2_DISPONIBLE:
    from modo_operacion_brain import (
        GESTOR_MODO as GESTOR_MODO_V2,
        cambiar_a_build,
        cambiar_a_plan
    )

router = APIRouter(prefix="/brain/v2", tags=["brain-v2"])


# Modelos Pydantic
class TaskRequest(BaseModel):
    descripcion: str
    tipo: str = "auto"  # "auto", "plan", "build"
    session_id: Optional[str] = None


class TaskResponse(BaseModel):
    status: str
    modo_actual: str
    puede_ejecutar: bool
    mensaje: str
    complejidad: Optional[str] = None
    acciones_recomendadas: Optional[List[str]] = None
    timeout_configurado: int = 30


class CambioRequest(BaseModel):
    tipo: str  # "file", "command", "config"
    target: str
    descripcion: str
    contenido_nuevo: Optional[str] = None
    session_id: Optional[str] = None


class CambioResponse(BaseModel):
    status: str
    mensaje: str
    indice: Optional[int] = None
    requiere_aprobacion: bool = True


class EjecutarRequest(BaseModel):
    indice: int
    confirmacion: bool = False
    session_id: Optional[str] = None


class EjecutarResponse(BaseModel):
    status: str
    accion: Optional[str] = None
    resultado: Optional[Dict] = None
    backup: Optional[str] = None
    error: Optional[str] = None
    retries: Optional[int] = None


@router.post("/task/analyze", response_model=TaskResponse)
async def analyze_task(request: TaskRequest):
    """
    Analiza una tarea y recomienda modo de ejecución
    """
    if not V2_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Brain V2 no disponible")
    
    try:
        # Detectar complejidad
        complejidad = ComplexityDetector.detect(request.descripcion)
        timeout = ComplexityDetector.get_timeout(complejidad)
        
        # Auto-activar BUILD si es necesario
        if request.tipo == "auto" or request.tipo == "build":
            resultado = auto_activate_build(request.descripcion)
        else:
            resultado = cambiar_a_plan("Modo PLAN solicitado")
        
        # Recomendaciones
        recomendaciones = []
        if complejidad.value in ["complex", "meta"]:
            recomendaciones = [
                "Usar modo BUILD",
                "Dividir en sub-tareas",
                "Crear checkpoints",
                f"Tiempo estimado: {timeout}s"
            ]
        
        return TaskResponse(
            status="ok",
            modo_actual=resultado["modo_actual"],
            puede_ejecutar=resultado.get("puede_modificar", False),
            mensaje=resultado.get("mensaje", "Análisis completado"),
            complejidad=complejidad.value,
            acciones_recomendadas=recomendaciones,
            timeout_configurado=timeout
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/modo/build", response_model=TaskResponse)
async def activate_build_mode(request: TaskRequest):
    """
    Activa modo BUILD explícitamente
    """
    try:
        resultado = cambiar_a_build(request.descripcion, auto_detect=False)
        return TaskResponse(
            status="ok",
            modo_actual=resultado["modo_actual"],
            puede_ejecutar=True,
            mensaje=resultado["mensaje"],
            timeout_configurado=Config.TIMEOUT_COMPLEJO
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cambio/proponer", response_model=CambioResponse)
async def propose_change(request: CambioRequest):
    """
    Propone un cambio para ejecución
    """
    try:
        if request.tipo == "file":
            resultado = proponer_modificacion_archivo(
                request.target,
                request.contenido_nuevo or "",
                request.descripcion,
                request.session_id
            )
        elif request.tipo == "command":
            resultado = proponer_comando(
                request.target,
                request.descripcion,
                request.session_id
            )
        else:
            raise HTTPException(status_code=400, detail=f"Tipo no soportado: {request.tipo}")
        
        return CambioResponse(
            status=resultado["status"],
            mensaje=resultado["mensaje"],
            indice=resultado.get("indice"),
            requiere_aprobacion=resultado.get("requiere_aprobacion", True)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cambio/ejecutar", response_model=EjecutarResponse)
async def execute_change(request: EjecutarRequest):
    """
    Ejecuta un cambio aprobado con reintentos automáticos
    """
    try:
        resultado = ejecutar_cambio_aprobado(
            request.indice,
            "user",
            request.session_id
        )
        
        return EjecutarResponse(
            status=resultado["status"],
            accion=resultado.get("accion"),
            resultado=resultado,
            backup=resultado.get("backup"),
            error=resultado.get("error"),
            retries=resultado.get("retries")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/estado")
async def get_status():
    """
    Retorna estado actual del Brain V2
    """
    try:
        estado = GESTOR_MODO_V2.get_estado()
        return {
            "status": "ok",
            "version": "2.0.0",
            **estado
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ejecutar-completo")
async def execute_complete_task(request: TaskRequest):
    """
    Ejecuta una tarea completa: análisis + modo + ejecución
    """
    if not V2_DISPONIBLE:
        raise HTTPException(status_code=503, detail="Brain V2 no disponible")
    
    try:
        resultados = []
        
        # Paso 1: Analizar
        complejidad = ComplexityDetector.detect(request.descripcion)
        resultados.append({
            "paso": 1,
            "accion": "analizar",
            "complejidad": complejidad.value,
            "status": "ok"
        })
        
        # Paso 2: Activar modo BUILD
        if complejidad.value in ["complex", "meta"]:
            resultado = auto_activate_build(request.descripcion)
            resultados.append({
                "paso": 2,
                "accion": "activar_build",
                "modo": resultado["modo_actual"],
                "auto_activado": resultado.get("auto_activado", False),
                "status": "ok"
            })
        
        return {
            "status": "ok",
            "task_analyzed": True,
            "steps": resultados,
            "ready_to_execute": True,
            "message": "Tarea analizada y preparada para ejecución. Usa /cambio/proponer para cada acción."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INTEGRACIÓN CON CHAT EXISTENTE
# ============================================================================

def procesar_intencion_v2(mensaje: str, session_id: str = None) -> Dict[str, Any]:
    """
    Procesa un mensaje del chat usando capacidades V2
    """
    if not V2_DISPONIBLE:
        return {
            "status": "error",
            "mensaje": "Brain V2 no disponible",
            "fallback": True
        }
    
    # Detectar intenciones de modificación
    palabras_clave_modificacion = [
        "elimina", "eliminar", "borra", "borrar", "modifica", "modificar",
        "actualiza", "actualizar", "crea", "crear", "ejecuta", "ejecutar",
        "cambia", "cambiar", "configura", "configurar"
    ]
    
    requiere_modificacion = any(palabra in mensaje.lower() for palabra in palabras_clave_modificacion)
    
    if requiere_modificacion:
        # Auto-activar modo BUILD
        resultado = auto_activate_build(mensaje)
        
        return {
            "status": "ok",
            "modo": resultado["modo_actual"],
            "auto_activado": resultado.get("auto_activado", False),
            "mensaje": f"[Brain V2] {resultado['mensaje']}",
            "puede_ejecutar": resultado.get("puede_modificar", False),
            "siguiente_paso": "Proponer cambios usando el sistema de cambios"
        }
    
    return {
        "status": "ok",
        "modo": "plan",
        "mensaje": "Modo PLAN activo - Análisis y diseño",
        "puede_ejecutar": False
    }


if __name__ == "__main__":
    print("="*70)
    print("BRAIN V2 WRAPPER - TEST DE INTEGRACIÓN")
    print("="*70)
    
    # Test procesamiento de intenciones
    mensajes_test = [
        "Hola, como estás?",
        "Elimina PocketOption del sistema",
        "Crea un backup de los archivos",
        "Modifica config.py para quitar referencias"
    ]
    
    for msg in mensajes_test:
        resultado = procesar_intencion_v2(msg, "test_session")
        print(f"\nMensaje: '{msg[:40]}...'")
        print(f"  Modo: {resultado['modo']}")
        print(f"  Auto-activado: {resultado.get('auto_activado', False)}")
        print(f"  Puede ejecutar: {resultado['puede_ejecutar']}")
    
    print("\n" + "="*70)
    print("INTEGRACIÓN LISTA")
    print("="*70)