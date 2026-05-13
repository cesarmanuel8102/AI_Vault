"""
CHAT_CONSCIENTE_ENDPOINT.PY
Endpoint de FastAPI para el sistema de consciencia integrado al chat

Integra todas las capacidades:
1. Respuestas con auto-consciencia de limitaciones
2. Detección de carencias éticas/legales
3. Modo profesor con explicación paso a paso
4. Aprendizaje automático de nuevas carencias
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# Importar sistema de consciencia
try:
    from sistema_consciencia_limitaciones import (
        SistemaConscienciaLimitaciones,
        responder_consciencia,
        CapabilityGapType
    )
    from integracion_brain_excelente import chat_excelente, get_system_stats
except ImportError as e:
    print(f"[Chat Consciente] Import error: {e}")
    # Crear stubs para testing
    class MockSistema:
        def analyze_challenge(self, challenge):
            class MockResponse:
                can_do_directly = False
                gaps_identified = []
                alternatives = []
                recommended_solution = None
                justification = "Sistema no disponible"
                immediate_workaround = None
            return MockResponse()
        
        def format_response_professor_mode(self, response, challenge):
            return "Modo profesor no disponible"
        
        def learn_new_gap(self, *args, **kwargs):
            return True
    
    def responder_consciencia(desafio):
        return "Sistema de consciencia no disponible"
    
    SistemaConscienciaLimitaciones = MockSistema
    CapabilityGapType = None


router = APIRouter(prefix="/chat/consciente", tags=["chat-consciente"])

# Instancia global
SISTEMA = SistemaConscienciaLimitaciones()


# Modelos Pydantic
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    mode: str = "normal"  # normal, professor, ethical_check
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    can_do_directly: bool
    gaps_identified: List[Dict[str, Any]]
    mode_used: str
    confidence: float
    ethical_alert: Optional[str] = None
    timestamp: str
    session_id: str


class ProfessorModeResponse(BaseModel):
    full_explanation: str
    can_do_directly: bool
    reasoning_steps: List[str]
    alternatives_considered: List[Dict[str, Any]]
    recommendation: Optional[str] = None


class LearnGapRequest(BaseModel):
    requirement: str
    gap_type: str  # knowledge, ethical, legal, safety, privacy, etc.
    description: str
    severity: float  # 0.0 - 1.0
    blocker: bool
    alternatives: List[str]


class LearnGapResponse(BaseModel):
    success: bool
    requirement_registered: str
    learned_at: str
    message: str


class EthicalCheckRequest(BaseModel):
    challenge: str
    severity_threshold: float = 0.7


class EthicalCheckResponse(BaseModel):
    challenge: str
    has_ethical_issues: bool
    ethical_gaps: List[Dict[str, Any]]
    legal_gaps: List[Dict[str, Any]]
    privacy_gaps: List[Dict[str, Any]]
    recommendation: str
    can_proceed: bool


# Endpoints

@router.post("/analyze", response_model=ChatResponse)
async def analyze_message_consciously(request: ChatRequest):
    """
    Analiza un mensaje con plena consciencia de limitaciones.
    
    Este endpoint procesa el mensaje del usuario y retorna:
    - Respuesta formateada con análisis completo
    - Identificación de carencias
    - Alternativas propuestas
    - Modo normal o ético según corresponda
    """
    try:
        # Analizar el desafío
        analysis = SISTEMA.analyze_challenge(request.message)
        
        # Verificar si hay problemas éticos/legales
        ethical_gaps = [g for g in analysis.gaps_identified 
                       if g.gap_type in [CapabilityGapType.ETHICAL, 
                                       CapabilityGapType.LEGAL, 
                                       CapabilityGapType.PRIVACY, 
                                       CapabilityGapType.SAFETY]]
        
        has_ethical_issues = len(ethical_gaps) > 0
        
        # Seleccionar modo de respuesta
        if request.mode == "professor":
            response_text = SISTEMA.format_response_professor_mode(
                analysis, request.message
            )
        elif request.mode == "ethical_check" and has_ethical_issues:
            response_text = format_ethical_alert(analysis, ethical_gaps, request.message)
        else:
            response_text = responder_consciencia(request.message)
        
        # Preparar gaps para respuesta
        gaps_list = []
        for gap in analysis.gaps_identified:
            gaps_list.append({
                "type": gap.gap_type.value,
                "description": gap.description,
                "severity": gap.severity,
                "blocker": gap.blocker
            })
        
        # Calcular confianza
        confidence = 0.95 if analysis.can_do_directly else (
            analysis.recommended_solution.confidence if analysis.recommended_solution else 0.5
        )
        
        # Alerta ética si aplica
        ethical_alert = None
        if has_ethical_issues:
            ethical_alert = f"Se detectaron {len(ethical_gaps)} problema(s) ético(s)/legal(es)"
        
        return ChatResponse(
            response=response_text,
            can_do_directly=analysis.can_do_directly,
            gaps_identified=gaps_list,
            mode_used=request.mode,
            confidence=confidence,
            ethical_alert=ethical_alert,
            timestamp=datetime.now().isoformat(),
            session_id=request.session_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en análisis consciente: {str(e)}")


@router.post("/professor-mode", response_model=ProfessorModeResponse)
async def professor_mode_explanation(request: ChatRequest):
    """
    MODO PROFESOR: Explica paso a paso el proceso de razonamiento.
    
    Ideal para entender cómo el Brain toma decisiones y por qué.
    """
    try:
        # Forzar modo profesor
        request.mode = "professor"
        
        analysis = SISTEMA.analyze_challenge(request.message)
        
        # Generar explicación completa
        explanation = SISTEMA.format_response_professor_mode(analysis, request.message)
        
        # Extraer pasos de razonamiento
        steps = [
            "Análisis de requisitos implícitos",
            "Evaluación de capacidades disponibles",
            "Identificación de carencias",
            "Formulación de alternativas",
            "Selección de mejor opción",
            "Justificación de recomendación"
        ]
        
        # Alternativas consideradas
        alternatives = []
        for alt in analysis.alternatives[:5]:
            alternatives.append({
                "name": alt.name,
                "confidence": alt.confidence,
                "effort_hours": alt.effort_hours,
                "pros": alt.pros,
                "cons": alt.cons
            })
        
        return ProfessorModeResponse(
            full_explanation=explanation,
            can_do_directly=analysis.can_do_directly,
            reasoning_steps=steps,
            alternatives_considered=alternatives,
            recommendation=analysis.recommended_solution.name if analysis.recommended_solution else None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en modo profesor: {str(e)}")


@router.post("/ethical-check", response_model=EthicalCheckResponse)
async def ethical_compliance_check(request: EthicalCheckRequest):
    """
    Verifica compliance ético y legal de un desafío.
    
    Detecta:
    - Intentos de daño (ETHICAL)
    - Violaciones legales (LEGAL)
    - Problemas de privacidad (PRIVACY)
    - Riesgos de seguridad (SAFETY)
    """
    try:
        if CapabilityGapType is None:
            raise HTTPException(status_code=503, detail="Sistema de capacidades no disponible")
        
        analysis = SISTEMA.analyze_challenge(request.challenge)
        
        # Clasificar gaps
        ethical = []
        legal = []
        privacy = []
        
        for gap in analysis.gaps_identified:
            gap_dict = {
                "description": gap.description,
                "severity": gap.severity,
                "type": gap.gap_type.value
            }
            
            if gap.gap_type == CapabilityGapType.ETHICAL and gap.severity >= request.severity_threshold:
                ethical.append(gap_dict)
            elif gap.gap_type == CapabilityGapType.LEGAL and gap.severity >= request.severity_threshold:
                legal.append(gap_dict)
            elif gap.gap_type == CapabilityGapType.PRIVACY and gap.severity >= request.severity_threshold:
                privacy.append(gap_dict)
            elif gap.gap_type == CapabilityGapType.SAFETY and gap.severity >= request.severity_threshold:
                # Agrupar safety con ethical para la respuesta
                ethical.append(gap_dict)
        
        has_issues = len(ethical) > 0 or len(legal) > 0 or len(privacy) > 0
        
        # Generar recomendación
        if has_issues:
            recommendation = "Este desafío presenta problemas éticos/legales que impiden proceder. "
            if ethical:
                recommendation += f"Se detectaron {len(ethical)} problema(s) ético(s). "
            if legal:
                recommendation += f"Se detectaron {len(legal)} problema(s) legal(es). "
            recommendation += "Sugerencias: Enfocar en usos legítimos y éticos."
        else:
            recommendation = "No se detectaron problemas éticos/legales significativos. El desafío puede proceder."
        
        return EthicalCheckResponse(
            challenge=request.challenge,
            has_ethical_issues=has_issues,
            ethical_gaps=ethical,
            legal_gaps=legal,
            privacy_gaps=privacy,
            recommendation=recommendation,
            can_proceed=not has_issues
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en verificación ética: {str(e)}")


@router.post("/learn-gap", response_model=LearnGapResponse)
async def teach_new_limitation(request: LearnGapRequest):
    """
    Enseña al sistema una nueva carencia.
    
    Permite expandir el conocimiento del sistema sobre qué no puede hacer
    y cómo manejarlo.
    """
    try:
        if CapabilityGapType is None:
            raise HTTPException(status_code=503, detail="Sistema de capacidades no disponible")
        
        # Mapear string a enum
        gap_type_map = {
            "knowledge": CapabilityGapType.KNOWLEDGE,
            "data": CapabilityGapType.DATA,
            "infrastructure": CapabilityGapType.INFRASTRUCTURE,
            "algorithm": CapabilityGapType.ALGORITHM,
            "resources": CapabilityGapType.RESOURCES,
            "permissions": CapabilityGapType.PERMISSIONS,
            "external_api": CapabilityGapType.EXTERNAL_API,
            "computational": CapabilityGapType.COMPUTATIONAL,
            "ethical": CapabilityGapType.ETHICAL,
            "legal": CapabilityGapType.LEGAL,
            "safety": CapabilityGapType.SAFETY,
            "privacy": CapabilityGapType.PRIVACY
        }
        
        gap_type = gap_type_map.get(request.gap_type)
        if not gap_type:
            raise HTTPException(status_code=400, detail=f"Tipo de carencia inválido: {request.gap_type}")
        
        # Intentar aprender
        success = SISTEMA.learn_new_gap(
            requirement=request.requirement,
            gap_type=gap_type,
            description=request.description,
            severity=request.severity,
            blocker=request.blocker,
            alternatives=request.alternatives
        )
        
        if success:
            return LearnGapResponse(
                success=True,
                requirement_registered=request.requirement,
                learned_at=datetime.now().isoformat(),
                message=f"Nueva carencia '{request.requirement}' aprendida exitosamente"
            )
        else:
            return LearnGapResponse(
                success=False,
                requirement_registered=request.requirement,
                learned_at=datetime.now().isoformat(),
                message=f"La carencia '{request.requirement}' ya estaba registrada o no pudo aprenderse"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en aprendizaje: {str(e)}")


@router.get("/capabilities")
async def get_system_capabilities():
    """
    Obtiene lista de capacidades y carencias conocidas.
    """
    try:
        capabilities = []
        limitations = []
        
        for name, data in SISTEMA.known_capabilities.items():
            if data.get("is_gap", False):
                limitations.append({
                    "name": name,
                    "description": data.get("description", ""),
                    "confidence": data.get("confidence", 0),
                    "alternatives": data.get("alternatives", [])
                })
            else:
                capabilities.append({
                    "name": name,
                    "description": data.get("description", ""),
                    "confidence": data.get("confidence", 0),
                    "limitations": data.get("limitations", [])
                })
        
        return {
            "status": "ok",
            "total_capabilities": len(capabilities),
            "total_limitations": len(limitations),
            "capabilities": capabilities,
            "limitations": limitations,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/stats")
async def get_consciousness_stats():
    """
    Obtiene estadísticas del sistema de consciencia.
    """
    try:
        # Intentar obtener stats del sistema excelente
        excelente_stats = get_system_stats() if 'get_system_stats' in dir() else {}
        
        return {
            "status": "ok",
            "system_level": "EXCELLENT_WITH_CONSCIOUSNESS",
            "capabilities_total": len(SISTEMA.known_capabilities),
            "capabilities_available": len([c for c in SISTEMA.known_capabilities.values() if not c.get("is_gap", False)]),
            "limitations_known": len([c for c in SISTEMA.known_capabilities.values() if c.get("is_gap", False)]),
            "excellent_capabilities": excelente_stats.get("unique_capabilities", 0),
            "excellent_responses": excelente_stats.get("excellent_responses", 0),
            "consciousness_mode": "ACTIVE",
            "ethical_filtering": "ENABLED",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


def format_ethical_alert(analysis, ethical_gaps, challenge):
    """Formatea alerta ética de forma prominente"""
    
    alert = f"""⚠️ ALERTA ÉTICA/LEGAL DETECTADA ⚠️
{'='*70}

El desafío "{challenge[:50]}..." presenta los siguientes problemas:

"""
    
    for gap in ethical_gaps:
        alert += f"🔴 {gap.gap_type.value.upper()}: {gap.description}\n"
        alert += f"   Severidad: {gap.severity:.0%} | Bloqueante: {'Sí' if gap.blocker else 'No'}\n\n"
    
    alert += f"""
{'='*70}

NO PUEDO PROCESAR ESTE DESAFÍO TAL COMO ESTÁ PLANTEADO.

ALTERNATIVAS ÉTICAS:
"""
    
    for gap in ethical_gaps:
        for alt in gap.alternatives:
            alert += f"• {alt}\n"
    
    alert += f"""

Si tienes una versión legítima/ética de este desafío, por favor replantéalo.

{'='*70}
"""
    
    return alert


# Función de inicialización
def initialize_conscious_chat(app):
    """
    Inicializa el router de chat consciente en la aplicación FastAPI
    
    Usage:
        from chat_consciente_endpoint import initialize_conscious_chat
        initialize_conscious_chat(app)
    """
    app.include_router(router)
    print("[Chat Consciente] Router inicializado correctamente")
    print("  - Endpoint: /chat/consciente/analyze")
    print("  - Professor mode: /chat/consciente/professor-mode")
    print("  - Ethical check: /chat/consciente/ethical-check")
    print("  - Learn gaps: /chat/consciente/learn-gap")
    print("  - Stats: /chat/consciente/stats")
    
    # Cargar gaps aprendidos previamente
    if hasattr(SISTEMA, 'load_learned_gaps'):
        SISTEMA.load_learned_gaps()


if __name__ == "__main__":
    # Test básico
    print("="*70)
    print("CHAT CONSCIENTE ENDPOINT - TEST")
    print("="*70)
    
    # Simular requests
    test_messages = [
        ("Juguemos ajedrez", "normal"),
        ("Dame el precio actual del EURUSD", "normal"),
        ("Hackea mi servidor", "ethical_check"),
        ("Entrena un modelo", "professor"),
    ]
    
    for msg, mode in test_messages:
        print(f"\n{'='*70}")
        print(f"TEST: {msg} | Modo: {mode}")
        print(f"{'='*70}\n")
        
        if mode == "ethical_check":
            # Simular verificación ética
            analysis = SISTEMA.analyze_challenge(msg)
            ethical = [g for g in analysis.gaps_identified 
                      if CapabilityGapType and g.gap_type in [
                          CapabilityGapType.ETHICAL, 
                          CapabilityGapType.LEGAL
                      ]]
            if ethical:
                print(f"ALERTAS ÉTICAS DETECTADAS: {len(ethical)}")
                for g in ethical:
                    print(f"  - {g.description}")
            else:
                print("Sin alertas éticas")
        else:
            response = responder_consciencia(msg)
            print(response[:300])
        
        print("\n")
    
    print("="*70)
    print("TEST COMPLETADO")
    print("="*70)
