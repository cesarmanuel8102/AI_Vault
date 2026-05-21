"""Authority Precedence Resolution - Minimal Helper

FASE 2: Minimal Precedence Enforcement
NO god object, NO singleton, NO mega-controller.
Solo una función pura que resuelve precedencia de autoridad.
"""

from typing import Dict, List, Tuple, Optional
from enum import Enum, auto


class EpistemicMode(str, Enum):
    """Modos epistémicos ordenados por nivel de certeza."""
    UNKNOWN = "unknown"           # Menor certeza
    NO_TOOLS_REASONING = "no_tools_reasoning"
    FALLBACK = "fallback"
    DEGRADED = "degraded"
    INFERRED = "inferred"
    VERIFIED = "verified"          # Mayor certeza


class AuthorityLevel(int, Enum):
    """Jerarquía de autoridad. Mayor número = mayor precedencia."""
    TEMPLATES = 10
    FASTPATH_CONVENIENCE = 20
    ROUTE_SELECTION = 30
    VERIFICATION_POLICY = 40
    EPISTEMIC_SAFETY = 50
    USER_CONSTRAINTS = 60        # Mayor precedencia


def resolve_authority_precedence(
    user_constraints: Dict[str, bool],
    epistemic_risk: Dict[str, any],
    verification_required: bool,
    proposed_route: str,
    proposed_mode: Optional[str] = None,
) -> Dict[str, any]:
    """Resuelve precedencia de autoridad de forma determinística.
    
    NO tiene estado. NO es clase. NO es singleton.
    Es función pura: mismos inputs → mismo output.
    
    Args:
        user_constraints: {"no_tools": True, "no_modify": True, ...}
        epistemic_risk: {"fake_grounded_risk": True, ...}
        verification_required: True si se requiere evidencia
        proposed_route: Ruta propuesta (fastpath, agent, llm, ...)
        proposed_mode: Modo epistémico propuesto
        
    Returns:
        Dict con resolución de autoridad:
        {
            "allowed": bool,
            "final_mode": str,
            "blocked_routes": List[str],
            "authority_applied": str,
            "reason": str,
        }
    """
    
    # Inicializar resultado
    result = {
        "allowed": True,
        "final_mode": proposed_mode or "unknown",
        "blocked_routes": [],
        "authority_applied": "route_selection",
        "reason": "Default route selection",
    }
    
    # 1. USER CONSTRAINTS (Precedencia máxima)
    if user_constraints.get("no_tools") and proposed_route in ["agent", "grounded_code_fastpath"]:
        result["allowed"] = False
        result["final_mode"] = EpistemicMode.NO_TOOLS_REASONING
        result["blocked_routes"] = ["agent", "grounded_code_fastpath"]
        result["authority_applied"] = "user_constraints"
        result["reason"] = "User prohibited tools"
        return result
    
    if user_constraints.get("no_modify") and proposed_route == "grounded_ui_edit_fastpath":
        result["allowed"] = False
        result["final_mode"] = EpistemicMode.DEGRADED
        result["blocked_routes"] = ["grounded_ui_edit_fastpath"]
        result["authority_applied"] = "user_constraints"
        result["reason"] = "User prohibited modifications"
        return result
    
    if user_constraints.get("no_trading") and proposed_route == "qc_live_fastpath":
        result["allowed"] = False
        result["final_mode"] = EpistemicMode.NO_TOOLS_REASONING
        result["blocked_routes"] = ["qc_live_fastpath"]
        result["authority_applied"] = "user_constraints"
        result["reason"] = "User prohibited trading analysis"
        return result
    
    # 2. EPISTEMIC SAFETY (Precedencia alta)
    if epistemic_risk.get("fake_grounded_risk") and proposed_route in [
        "fastpath", "qc_live_fastpath", "grounded_ui_edit_fastpath"
    ]:
        result["allowed"] = False
        result["final_mode"] = EpistemicMode.DEGRADED
        result["blocked_routes"] = [proposed_route]
        result["authority_applied"] = "epistemic_safety"
        result["reason"] = "Fake grounded risk detected"
        return result
    
    if epistemic_risk.get("ghost_completion_risk") and proposed_route == "agent":
        result["allowed"] = False
        result["final_mode"] = EpistemicMode.FALLBACK
        result["blocked_routes"] = ["agent"]
        result["authority_applied"] = "epistemic_safety"
        result["reason"] = "Ghost completion risk"
        return result
    
    # 3. VERIFICATION POLICY (Precedencia media-alta)
    if verification_required:
        # Si requiere verificación pero va a fastpath sin evidencia
        if proposed_route in ["fastpath", "qc_live_fastpath"]:
            result["allowed"] = False
            result["final_mode"] = EpistemicMode.DEGRADED
            result["blocked_routes"] = [proposed_route]
            result["authority_applied"] = "verification_policy"
            result["reason"] = "Verification required but no evidence available"
            return result
        
        # Si requiere verificación y va a agent, permitir pero marcar
        if proposed_route == "agent":
            result["final_mode"] = EpistemicMode.VERIFIED
            result["authority_applied"] = "verification_policy"
            result["reason"] = "Agent route with verification"
            return result
    
    # 4. FASTPATH_CONVENIENCE (Precedencia baja)
    # Fastpaths solo permitidos si no hay conflictos superiores
    if proposed_route in ["fastpath", "qc_live_fastpath"]:
        result["final_mode"] = EpistemicMode.INFERRED
        result["authority_applied"] = "fastpath_convenience"
        result["reason"] = "Fastpath convenience allowed"
        return result
    
    # 5. Default: permitir ruta propuesta
    return result


def lock_epistemic_mode(
    current_mode: str,
    proposed_elevation: str,
    evidence_level: str,
) -> Tuple[str, bool]:
    """Lock epistemic mode - no puede elevarse sin evidencia suficiente.
    
    Reglas de locking:
    - degraded NO puede pasar a verified sin tool/evidence real
    - inferred NO puede pasar a verified por memoria
    - template NO puede presentarse como verified
    - no_tools_reasoning NO puede activar agent/tools
    - unknown NO puede convertirse en operational_status por fastpath
    
    Returns:
        (final_mode, can_elevate)
    """
    mode_hierarchy = {
        EpistemicMode.UNKNOWN: 0,
        EpistemicMode.NO_TOOLS_REASONING: 1,
        EpistemicMode.FALLBACK: 2,
        EpistemicMode.DEGRADED: 3,
        EpistemicMode.INFERRED: 4,
        EpistemicMode.VERIFIED: 5,
    }
    
    current_level = mode_hierarchy.get(current_mode, 0)
    proposed_level = mode_hierarchy.get(proposed_elevation, 0)
    
    # Si está bajando o igual, permitir
    if proposed_level <= current_level:
        return proposed_elevation, True
    
    # Si está subiendo, verificar evidencia
    if proposed_level > current_level:
        # Requiere evidence_level "tool" o "http" para subir a verified
        if proposed_elevation == EpistemicMode.VERIFIED:
            if evidence_level not in ["tool", "http", "observed"]:
                return current_mode, False
        
        # Requiere evidence_level "memory" o superior para subir a inferred
        if proposed_elevation == EpistemicMode.INFERRED:
            if evidence_level not in ["memory", "tool", "http", "observed"]:
                return current_mode, False
    
    return proposed_elevation, True


def validate_emission_safety(
    response_content: str,
    response_mode: str,
    user_constraints: Dict[str, bool],
    blocked_routes: List[str],
) -> Tuple[bool, str, Optional[str]]:
    """Valida que la emisión sea segura antes de emitir.
    
    Returns:
        (is_safe, reason, safe_response)
        safe_response es alternativa si is_safe=False
    """
    # Check 1: ¿El modo está lockeado?
    if response_mode == "unknown":
        return False, "Response mode not locked", None
    
    # Check 2: ¿Contradice user constraints?
    if user_constraints.get("no_tools") and "tool" in response_content.lower():
        return False, "Response mentions tools but user prohibited them", \
               "No puedo usar tools. Te explico sin ejecutar nada."
    
    # Check 3: ¿Contiene claim operacional sin evidencia?
    operational_claims = [
        "dashboard está", "runtime está", "servicio está",
        "pipeline tiene", "sistema está", "api responde"
    ]
    has_operational_claim = any(claim in response_content.lower() 
                                  for claim in operational_claims)
    
    if has_operational_claim and response_mode in ["inferred", "unknown"]:
        return False, "Operational claim without evidence", \
               "No puedo afirmar el estado operativo sin evidencia real. " \
               "Puedo razonar conceptualmente."
    
    # Check 4: ¿Ruta está bloqueada?
    # Nota: Esto se chequea antes de llegar aquí
    
    # Check 5: ¿Mezcla template y degraded?
    if "*" in response_content and response_mode == "degraded":
        # Markdown formatting in degraded mode = mixed emission
        return False, "Mixed emission: template formatting in degraded mode", \
               "No puedo responder con certeza. El estado queda UNKNOWN."
    
    return True, "Emission safe", None
