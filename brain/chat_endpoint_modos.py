"""
CHAT_ENDPOINT_MODOS.PY
Endpoint completo para control de modos PLAN/BUILD desde el chat

Endpoints disponibles:
- POST /chat/modo/comando - Ejecutar comandos de modo
- GET  /chat/modo/estado   - Ver estado actual
- POST /chat/modo/cambiar  - Cambiar entre plan/build
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Importar sistema de modos
try:
    from modo_operacion_brain import (
        GESTOR_MODO, 
        cambiar_a_build, 
        cambiar_a_plan,
        ModoOperacion,
        proponer_modificacion_archivo,
        ejecutar_cambio_aprobado
    )
    from chat_modo_control import procesar_comando_chat
    
    MODULOS_DISPONIBLES = True
except ImportError as e:
    print(f"[Chat Modo] Error importando módulos: {e}")
    MODULOS_DISPONIBLES = False


router = APIRouter(prefix="/chat/modo", tags=["chat-modo"])


# Modelos Pydantic
class ComandoRequest(BaseModel):
    comando: str
    usuario: str = "anonymous"
    session_id: Optional[str] = None


class ComandoResponse(BaseModel):
    status: str
    tipo: str
    mensaje: str
    modo_actual: str
    requiere_aprobacion: Optional[bool] = False
    datos_adicionales: Optional[dict] = None


class CambioModoRequest(BaseModel):
    nuevo_modo: str  # "plan" o "build"
    razon: str = "Solicitado por usuario"
    usuario: str = "anonymous"


class EstadoResponse(BaseModel):
    modo_actual: str
    puede_modificar: bool
    cambios_pendientes: int
    cambios_ejecutados: int
    backups_disponibles: int
    historial: List[dict]


class EjecutarRequest(BaseModel):
    indice_cambio: int
    usuario: str = "anonymous"
    confirmacion: bool = False


# Endpoints

@router.post("/comando", response_model=ComandoResponse)
async def ejecutar_comando(request: ComandoRequest):
    """
    Ejecuta un comando de control de modos desde el chat.
    
    Comandos soportados:
    - /modo plan|build|estado
    - /ejecutar [n]
    - /rollback [archivo]
    - /cambios
    - /ayuda
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        # Procesar comando
        resultado = procesar_comando_chat(request.comando)
        
        # Obtener estado actual
        estado = GESTOR_MODO.get_estado()
        
        return ComandoResponse(
            status=resultado.get("status", "ok"),
            tipo=resultado.get("tipo", "unknown"),
            mensaje=resultado.get("mensaje", resultado.get("error", "Sin mensaje")),
            modo_actual=estado["modo_actual"],
            requiere_aprobacion=resultado.get("requiere_aprobacion", False),
            datos_adicionales=resultado
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando comando: {str(e)}")


@router.get("/estado", response_model=EstadoResponse)
async def obtener_estado():
    """
    Obtiene el estado actual del sistema de modos.
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        estado = GESTOR_MODO.get_estado()
        
        return EstadoResponse(
            modo_actual=estado["modo_actual"],
            puede_modificar=estado["puede_modificar"],
            cambios_pendientes=estado["cambios_pendientes"],
            cambios_ejecutados=estado["cambios_ejecutados"],
            backups_disponibles=estado["backups_disponibles"],
            historial=estado.get("historial_modo", [])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo estado: {str(e)}")


@router.post("/cambiar", response_model=ComandoResponse)
async def cambiar_modo(request: CambioModoRequest):
    """
    Cambia entre modo PLAN y BUILD.
    
    - plan: Modo análisis (solo lectura)
    - build: Modo ejecución (puede modificar archivos)
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        if request.nuevo_modo.lower() == "build":
            resultado = cambiar_a_build(request.razon)
        elif request.nuevo_modo.lower() == "plan":
            resultado = cambiar_a_plan(request.razon)
        else:
            raise HTTPException(status_code=400, detail=f"Modo inválido: {request.nuevo_modo}. Use 'plan' o 'build'")
        
        estado = GESTOR_MODO.get_estado()
        
        return ComandoResponse(
            status=resultado.get("status", "ok"),
            tipo="cambio_modo",
            mensaje=resultado.get("mensaje", f"Modo cambiado a {request.nuevo_modo.upper()}"),
            modo_actual=estado["modo_actual"],
            datos_adicionales=resultado
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cambiando modo: {str(e)}")


@router.post("/ejecutar", response_model=ComandoResponse)
async def ejecutar_cambio(request: EjecutarRequest):
    """
    Ejecuta un cambio aprobado (solo funciona en modo BUILD).
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        # Verificar que esté en modo BUILD
        if GESTOR_MODO.modo_actual != ModoOperacion.BUILD:
            return ComandoResponse(
                status="error",
                tipo="error_modo",
                mensaje="❌ No se puede ejecutar en modo PLAN. Cambia a modo BUILD primero con: /modo build",
                modo_actual="plan",
                requiere_aprobacion=False
            )
        
        # Ejecutar cambio
        resultado = ejecutar_cambio_aprobado(request.indice_cambio, request.usuario)
        
        estado = GESTOR_MODO.get_estado()
        
        if resultado.get("status") == "ok":
            return ComandoResponse(
                status="ok",
                tipo="ejecucion_exitosa",
                mensaje=f"✓ Cambio #{request.indice_cambio} ejecutado exitosamente\n{resultado.get('mensaje', '')}",
                modo_actual="build",
                datos_adicionales=resultado
            )
        else:
            return ComandoResponse(
                status="error",
                tipo="ejecucion_fallida",
                mensaje=f"✗ Error: {resultado.get('error', 'Error desconocido')}",
                modo_actual="build",
                datos_adicionales=resultado
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ejecutando cambio: {str(e)}")


@router.post("/proponer", response_model=ComandoResponse)
async def proponer_cambio_archivo(
    ruta: str,
    contenido: str,
    descripcion: str,
    usuario: str = "anonymous"
):
    """
    Propone un cambio de archivo (requiere BUILD + aprobación para ejecutar).
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        resultado = proponer_modificacion_archivo(ruta, contenido, descripcion)
        estado = GESTOR_MODO.get_estado()
        
        return ComandoResponse(
            status=resultado.get("status", "ok"),
            tipo="cambio_propuesto",
            mensaje=resultado.get("mensaje", "Cambio propuesto"),
            modo_actual=estado["modo_actual"],
            requiere_aprobacion=True,
            datos_adicionales={
                "ruta": ruta,
                "descripcion": descripcion,
                "indice": len(GESTOR_MODO.cambios_pendientes) - 1
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proponiendo cambio: {str(e)}")


@router.get("/cambios")
async def listar_cambios():
    """
    Lista todos los cambios pendientes.
    """
    if not MODULOS_DISPONIBLES:
        raise HTTPException(status_code=503, detail="Sistema de modos no disponible")
    
    try:
        cambios = GESTOR_MODO.cambios_pendientes
        estado = GESTOR_MODO.get_estado()
        
        return {
            "cantidad": len(cambios),
            "modo_actual": estado["modo_actual"],
            "cambios": [
                {
                    "indice": i,
                    "tipo": c.tipo,
                    "descripcion": c.descripcion,
                    "target": c.target,
                    "riesgo": c.riesgo,
                    "requiere_implementacion": c.target  # Verificar si requiere implementación
                }
                for i, c in enumerate(cambios)
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando cambios: {str(e)}")


# Función de inicialización
def initialize_modo_router(app):
    """
    Inicializa el router de modos en la aplicación FastAPI
    
    Usage:
        from chat_endpoint_modos import initialize_modo_router
        initialize_modo_router(app)
    """
    app.include_router(router)
    print("[Chat Modo] Router de modos PLAN/BUILD inicializado")
    print("  - POST /chat/modo/comando")
    print("  - GET  /chat/modo/estado")
    print("  - POST /chat/modo/cambiar")
    print("  - POST /chat/modo/ejecutar")
    print("  - GET  /chat/modo/cambios")


if __name__ == "__main__":
    # Test básico
    print("="*70)
    print("CHAT ENDPOINT MODOS - Test")
    print("="*70)
    
    if MODULOS_DISPONIBLES:
        print("\n✓ Módulos cargados correctamente")
        print(f"  Modo actual: {GESTOR_MODO.modo_actual.value}")
        print(f"  Cambios pendientes: {len(GESTOR_MODO.cambios_pendientes)}")
    else:
        print("\n✗ Módulos no disponibles")
    
    print("\nEndpoints disponibles:")
    print("  /chat/modo/comando")
    print("  /chat/modo/estado")
    print("  /chat/modo/cambiar")
    print("  /chat/modo/ejecutar")
    print("  /chat/modo/cambios")
