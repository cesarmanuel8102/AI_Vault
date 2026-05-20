"""Routing Semantic Guards Module

Extracted from session.py as part of architectural hardening Phase C.
Pure functions for semantic analysis without side effects.

Responsibility:
- Negative constraint detection (no-tools preferences)
- Intent classification helpers
- Pattern matching for routing decisions
- Tool target identification

Design Principles:
- Pure functions only (no side effects)
- No dependencies on BrainSession state
- Reusable across routing layers
- Testable independently
"""

import re
from typing import Tuple, Dict, Any

# ═══════════════════════════════════════════════════════════════════════════
# HEURISTIC CONSTANTS - Semantic markers for routing decisions
# ═══════════════════════════════════════════════════════════════════════════

# Markers indicating user does NOT want tools to be used
NO_TOOL_MARKERS: Tuple[str, ...] = (
    "no uses tools",
    "no use tools",
    "no herramientas",
    "sin herramientas",
    "sin tools",
    "no ejecutes herramientas",
    "no ejecutar herramientas",
    "no modifiques",
    "no modificar",
    "no cambies",
    "no cambiar",
    "no edites",
    "no editar",
    "no toques",
    "sin cambios",
    "sin modificar",
    "no hagas cambios",
    "solo analiza",
    "solo analizar",
    "solo razona",
    "solo explica",
)

# Regex for code analysis paths
CODE_ANALYSIS_PATH_RE = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*\.(py|js|ts|json|yaml|yml|toml|ini|cfg|txt|md|rst|html|css|jsx|tsx|vue|svelte|sh|bash|zsh|ps1|bat|cmd|rs|go|java|kt|scala|rb|php|cpp|c|h|hpp|cs|swift|m|mm)\b",
    re.IGNORECASE,
)

# Patterns for explicit tool targets
TOOL_TARGET_PATTERNS = [
    # Code paths
    ("code_path", r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*\.(py|js|ts|json|yaml|yml|toml|ini|cfg|txt|md|rst|html|css|jsx|tsx|vue|svelte|sh|bash|zsh|ps1|bat|cmd|rs|go|java|kt|scala|rb|php|cpp|c|h|hpp|cs|swift|m|mm)\b"),
    # File system paths
    ("filesystem", r"\b(?:[a-z]:[\\\\/]|/[\w.-]+/)"),
    # Ports
    ("port", r"\b(?:puerto|port)\s*\d{2,5}\b"),
    # IP addresses
    ("ip", r"\b\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?\b"),
    # Execution commands
    ("execute", r"\b(?:ejecuta|ejecutar|corre|run|execute)\s+[\w./:-]+"),
]

# Service and system markers
TOOL_TARGET_TOKENS: Tuple[str, ...] = (
    "servicio brain",
    "servicios brain",
    "ollama",
    "dashboard",
    "log",
    "logs",
    "archivo",
    "carpeta",
    "directorio",
    "file",
    "folder",
    "directory",
)


# ═══════════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS - Semantic Analysis Helpers
# ═══════════════════════════════════════════════════════════════════════════

def prefers_no_tool_analysis(message: str) -> bool:
    """Detect explicit user preference for pure analysis/chat without tools.
    
    Returns True if user explicitly requested no-tool analysis.
    
    Examples:
        - "no uses tools, solo analiza"
        - "sin herramientas"
        - "solo explica el concepto"
    
    Args:
        message: User message to analyze
        
    Returns:
        True if no-tool preference detected
    """
    if not message:
        return False
    msg = message.lower()
    return any(marker in msg for marker in NO_TOOL_MARKERS)


def has_explicit_tool_target(message: str) -> bool:
    """Check if user named a concrete file/service/command target.
    
    Returns True if message contains specific targets that justify tool usage.
    
    Examples:
        - File paths: "/path/to/file.py"
        - Services: "dashboard", "servicio brain"
        - Ports: "puerto 8080"
        - IPs: "127.0.0.1"
        - Execution: "ejecuta script.sh"
    
    Args:
        message: User message to analyze
        
    Returns:
        True if explicit tool target found
    """
    if not message:
        return False
    
    msg = message.lower()
    
    # Check code analysis paths
    if CODE_ANALYSIS_PATH_RE.search(message):
        return True
    
    # Check tool target patterns
    for pattern_type, pattern in TOOL_TARGET_PATTERNS:
        if re.search(pattern, msg if pattern_type != "code_path" else message, re.IGNORECASE):
            return True
    
    # Check service tokens
    return any(token in msg for token in TOOL_TARGET_TOKENS)


def is_confirmation(msg: str) -> bool:
    """Return True if the message is a short confirmation phrase.
    
    Examples:
        - "si", "sí", "ok", "dale", "yes"
        - "confirmo", "confirmado", "adelante"
        - "hazlo", "ejecuta", "proceed"
    
    Args:
        msg: Message to check
        
    Returns:
        True if confirmation detected
    """
    if not msg or len(msg) > 40:
        return False
    
    stripped = msg.strip().lower()
    
    # Short confirmation patterns
    confirm_patterns = [
        r"^(si|sí|ok|dale|yes|ya|aprueba|aprobar|confirma|confirmo|confirmado|adelante|hazlo|ejecuta|proceed|approve|do\s+it|go\s+ahead)$",
    ]
    
    for pattern in confirm_patterns:
        if re.match(pattern, stripped, re.IGNORECASE):
            return True
    
    # Token-based check for multi-word confirmations
    allowed_tokens = {
        "si", "sí", "ok", "dale", "yes", "ya", "aprueba", "aprobar",
        "confirma", "confirmo", "confirmado", "adelante", "hazlo",
        "ejecuta", "proceed", "approve", "do", "it", "go", "ahead",
    }
    
    tokens = [t for t in re.split(r"[\s,;:.!¡¿?\-_/]+", stripped) if t]
    return bool(tokens) and all(token in allowed_tokens for token in tokens)


def is_code_change_request(message: str) -> bool:
    """Detect if message is requesting code/file modifications.
    
    Examples:
        - "modifica el archivo"
        - "cambia el color de fondo"
        - "edita el código"
        - "fix the bug"
    
    Args:
        message: Message to analyze
        
    Returns:
        True if code change request detected
    """
    if not message:
        return False
    
    msg = message.lower()
    
    action_markers = (
        "modifica", "modificar", "cambia", "cambiar", "edita", "editar",
        "arregla", "fix", "refactor", "crea", "crear", "implementa",
        "implement", "ajusta", "patch", "reemplaza",
    )
    
    scope_markers = (
        ".py", ".json", "ui", "frontend", "chat", "dashboard", "index.html",
        "background", "fondo", "color", "css", "html", "javascript",
        "archivo", "archivos", "brain", "session.py", "llm.py",
    )
    
    return any(a in msg for a in action_markers) and any(s in msg for s in scope_markers)


def is_tool_confirmation_request_response(response: str) -> bool:
    """Detect chat-only replies that asked the user to confirm tool execution.
    
    Returns True if the response is asking for confirmation to use tools.
    
    Args:
        response: Brain response to analyze
        
    Returns:
        True if confirmation request detected
    """
    if not response:
        return False
    
    text = response.lower()
    
    return (
        "confirma si quieres que" in text
        and (
            "endpoint de agente" in text
            or "ejecute" in text
            or "llame" in text
            or "herramientas" in text
            or "tools" in text
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE GUARDS - Combined checks for routing decisions
# ═══════════════════════════════════════════════════════════════════════════

def should_route_to_llm_instead_of_agent(
    message: str,
    intent: str = "",
    confidence: float = 1.0,
) -> Tuple[bool, str]:
    """Determine if message should route to LLM instead of Agent.
    
    Combines multiple semantic guards to make routing decision.
    Returns tuple of (should_use_llm, reason).
    
    Args:
        message: User message
        intent: Detected intent (optional)
        confidence: Intent confidence (optional)
        
    Returns:
        Tuple of (use_llm: bool, reason: str)
    """
    # Check no-tool preference without explicit target
    if prefers_no_tool_analysis(message) and not has_explicit_tool_target(message):
        return True, "No-tool preference without explicit target"
    
    # Analysis intent without operational signals
    if intent == "ANALYSIS":
        return True, "Intent 'ANALYSIS' without operational signals"
    
    # Low confidence operational intent
    if intent and "OPERATIONAL" in intent and confidence < 0.5:
        return True, f"Low confidence ({confidence:.2f}) operational intent"
    
    return False, "No LLM routing preference detected"


# ═══════════════════════════════════════════════════════════════════════════
# GROUNDED VERIFICATION GUARDS
# Detect when user requests require evidence-based, grounded analysis
# ═══════════════════════════════════════════════════════════════════════════

# Markers indicating user wants grounded/real verification (not templates)
GROUNDED_VERIFICATION_MARKERS: Tuple[str, ...] = (
    "estado real",
    "verdadero estado",
    "revisa",
    "verifica",
    "comprueba",
    "diagnostica",
    "analiza real",
    "dime brechas",
    "dime problemas",
    "dime el estado",
    "evidencia",
    "datos reales",
    "información actual",
    "qué está pasando",
    "cómo está",
    "health check",
    "estado actual",
)

# URL patterns that indicate need for live verification
URL_PATTERNS = [
    r"https?://[^\s]+",  # http/https URLs
    r"localhost:\d+",    # localhost with port
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+",  # any IP:port (not just 127.x)
    r"/[^\s]+/[^\s]+",   # file paths
]

# Markers that indicate template/static response is insufficient
REJECTS_TEMPLATE_MARKERS: Tuple[str, ...] = (
    "no me des teoría",
    "no me des plantilla",
    "no me des template",
    "dame real",
    "dame concreto",
    "solo datos",
    "solo hechos",
    "evita generalidades",
)

def requires_grounded_verification(message: str) -> bool:
    """Detect if user message requires grounded, evidence-based verification.
    
    Returns True when the user explicitly asks for real status,
    actual data, or verification of claims - not templates or generic responses.
    
    Examples:
        - "revisa http://127.0.0.1:8090/dashboard-v2 y dime el estado real"
        - "verifica el estado real del sistema"
        - "dime brechas reales, no teoría"
        - "diagnostica problemas reales"
    
    Args:
        message: User message to analyze
        
    Returns:
        True if grounded verification required
    """
    if not message:
        return False
    
    msg_lower = message.lower()
    
    # Check for explicit grounded verification markers
    has_grounded_marker = any(
        marker in msg_lower for marker in GROUNDED_VERIFICATION_MARKERS
    )
    
    # Check for "real" modifiers (e.g., "brechas reales", "problemas reales")
    has_real_modifier = bool(re.search(r"\b(brechas?|problemas?|estado|datos?)\s+reales?\b", msg_lower))
    
    # Check for URLs (indicates need for live verification)
    has_url = any(
        re.search(pattern, message) for pattern in URL_PATTERNS
    )
    
    # Check for explicit rejection of templates
    rejects_template = any(
        marker in msg_lower for marker in REJECTS_TEMPLATE_MARKERS
    )
    
    # Return True if:
    # 1. Explicitly asks for grounded verification, OR
    # 2. Contains URL + asks for status/info, OR  
    # 3. Explicitly rejects templates + asks for real data
    # 4. Has "real" modifier + grounded marker (e.g., "dime brechas reales")
    if has_grounded_marker and has_url:
        return True
    
    if rejects_template and has_grounded_marker:
        return True
    
    if has_real_modifier and has_grounded_marker:
        return True
    
    # If just URL mentioned with "revisa"/"verifica", likely needs verification
    if has_url and any(word in msg_lower for word in ["revisa", "verifica", "chequea", "dime"]):
        return True
    
    return False


def get_verification_priority(message: str) -> int:
    """Return priority level (0-3) for verification requirements.
    
    Higher priority = more urgent need for grounded verification.
    
    Args:
        message: User message to analyze
        
    Returns:
        Priority level (0=none, 1=low, 2=medium, 3=high)
    """
    if not message:
        return 0
    
    msg_lower = message.lower()
    
    priority = 0
    
    # High priority: explicit "estado real" with URL
    if "estado real" in msg_lower and any(
        re.search(pattern, message) for pattern in URL_PATTERNS
    ):
        priority = max(priority, 3)
    
    # Medium priority: generic verification request with URL
    if any(marker in msg_lower for marker in GROUNDED_VERIFICATION_MARKERS[:5]):
        if any(re.search(pattern, message) for pattern in URL_PATTERNS):
            priority = max(priority, 2)
    
    # Low priority: just URL mentioned
    if any(re.search(pattern, message) for pattern in URL_PATTERNS):
        priority = max(priority, 1)
    
    # Boost priority if explicitly rejects templates
    if any(marker in msg_lower for marker in REJECTS_TEMPLATE_MARKERS):
        priority = min(priority + 1, 3)
    
    return priority


def should_degrade_fastpath(message: str) -> bool:
    """Determine if fastpath should be degraded to allow verification.
    
    When user asks for "estado real" with URLs, fastpath templates
    should not be used - actual verification is needed.
    
    Args:
        message: User message to analyze
        
    Returns:
        True if fastpath should be bypassed for verification
    """
    if not message:
        return False
    
    msg_lower = message.lower()
    
    # Always degrade if "estado real" + URL
    if "estado real" in msg_lower and any(
        re.search(pattern, message) for pattern in URL_PATTERNS
    ):
        return True
    
    # Degrade if explicit rejection of templates
    if any(marker in msg_lower for marker in REJECTS_TEMPLATE_MARKERS):
        return True
    
    # Degrade if priority 3 (highest)
    if get_verification_priority(message) >= 3:
        return True
    
    return False


# ═══════════════════════════════════════════════════════════════════════════
# ROUTING AUTHORITY BOUNDARY
# Detect and resolve conflicts between V9.1 semantic routing and BrainSession operational routing
# ═══════════════════════════════════════════════════════════════════════════

# Markers that indicate V9.1 unified_chat_router classification was used
V9_ROUTING_MARKERS: Tuple[str, ...] = (
    "self_awareness",
    "dashboard_analysis",
    "learning_request",
    "goal_management",
    "agent_task",
    "general_conversation",
)

# Markers that indicate BrainSession routing was used
BRAINSESSION_ROUTING_MARKERS: Tuple[str, ...] = (
    "fastpath",
    "command",
    "agent",
    "llm",
    "context_resume",
    "user_correction_ack",
)


def detect_routing_authority_conflict(
    v9_category: str = "",
    brainsession_route: str = "",
    v9_confidence: float = 0.0,
    brainsession_confidence: float = 0.0,
) -> Tuple[bool, str, str]:
    """Detect if there's a conflict between V9.1 and BrainSession routing decisions.
    
    NOTE: This function exists as INFRASTRUCTURE but is NOT integrated into the
    main chat() flow yet. It provides the capability for future authority
    boundary resolution but currently operates as standalone detection.
    
    Returns tuple of (has_conflict, winner, reason).
    
    Args:
        v9_category: Category from unified_chat_router (e.g., "agent_task")
        brainsession_route: Route from BrainSession (e.g., "llm")
        v9_confidence: Confidence score from V9.1 router
        brainsession_confidence: Confidence score from BrainSession
        
    Returns:
        Tuple of (has_conflict: bool, winner: str, reason: str)
    """
    if not v9_category or not brainsession_route:
        return False, "none", "insufficient_data"
    
    # Normalize to lowercase
    v9 = v9_category.lower()
    brain = brainsession_route.lower()
    
    # Check for known conflict patterns
    # Pattern 1: V9.1 says "agent_task" but BrainSession says "llm" (no-tool preference)
    if v9 == "agent_task" and brain == "llm":
        # This is a conflict - user likely said "no uses tools"
        if brainsession_confidence > v9_confidence:
            return True, "BrainSession", "user_no_tool_preference_overrides_agent"
        else:
            return True, "V9.1", "high_confidence_operational_request"
    
    # Pattern 2: V9.1 says "general_conversation" but BrainSession says "agent"
    if v9 == "general_conversation" and brain == "agent":
        # BrainSession detected explicit tool target that V9.1 missed
        return True, "BrainSession", "explicit_tool_target_detected"
    
    # Pattern 3: V9.1 says "dashboard_analysis" but BrainSession says "fastpath"
    if v9 == "dashboard_analysis" and brain == "fastpath":
        # Fastpath has real dashboard data, V9.1 might be using stale patterns
        return True, "BrainSession", "fastpath_has_real_data"
    
    # Pattern 4: V9.1 says "learning_request" but BrainSession says "llm"
    if v9 == "learning_request" and brain == "llm":
        # User just asking about learning, not requesting learning action
        return True, "BrainSession", "informational_not_operational"
    
    # No conflict detected
    return False, "none", "routes_aligned"


def get_route_confidence(
    intent: str = "",
    matched_patterns: int = 0,
    total_patterns: int = 1,
    has_explicit_target: bool = False,
    verification_priority: int = 0,
) -> Tuple[float, str]:
    """Calculate confidence score for routing decision with explanation.
    
    Returns tuple of (confidence_score, confidence_source).
    
    Args:
        intent: Detected intent
        matched_patterns: Number of patterns that matched
        total_patterns: Total patterns available for that intent
        has_explicit_target: Whether explicit tool target was found
        verification_priority: Grounded verification priority (0-3)
        
    Returns:
        Tuple of (confidence: float, source: str)
    """
    base_confidence = 0.5
    
    # Boost confidence based on pattern matches
    if total_patterns > 0:
        pattern_ratio = matched_patterns / total_patterns
        base_confidence += pattern_ratio * 0.3
    
    # Boost for explicit targets
    if has_explicit_target:
        base_confidence += 0.15
    
    # Adjust for verification needs
    if verification_priority >= 3:
        base_confidence += 0.05  # High verification needs = more certain
    elif verification_priority == 0:
        base_confidence -= 0.1   # No verification = less certain
    
    # Cap at 0.95 to allow for uncertainty
    confidence = min(0.95, max(0.1, base_confidence))
    
    # Determine source of confidence
    if matched_patterns >= 3 and has_explicit_target:
        source = "strong_intent_plus_target"
    elif matched_patterns >= 2:
        source = "multiple_patterns_matched"
    elif has_explicit_target:
        source = "explicit_target_only"
    elif intent:
        source = "intent_classification"
    else:
        source = "default"
    
    return confidence, source


def build_authority_trace(
    v9_category: str = "",
    v9_confidence: float = 0.0,
    brainsession_route: str = "",
    brainsession_confidence: float = 0.0,
    conflict_detected: bool = False,
    winner: str = "",
    reason: str = "",
    fallback_marker: str = "",
) -> Dict[str, Any]:
    """Build complete authority trace for routing decision.
    
    This trace records who made the routing decision and why, enabling
    post-hoc analysis of routing authority conflicts.
    
    Args:
        v9_category: V9.1 router category
        v9_confidence: V9.1 confidence
        brainsession_route: BrainSession route
        brainsession_confidence: BrainSession confidence
        conflict_detected: Whether conflict was detected
        winner: Who won the conflict resolution
        reason: Why they won
        fallback_marker: What fallback mechanism was used
        
    Returns:
        Dictionary with complete authority trace
    """
    return {
        "v9_router": {
            "category": v9_category,
            "confidence": v9_confidence,
            "advisory": True,  # V9.1 is advisory only
        },
        "brainsession_router": {
            "route": brainsession_route,
            "confidence": brainsession_confidence,
            "operational": True,  # BrainSession is operational SSOT
        },
        "conflict_resolution": {
            "detected": conflict_detected,
            "winner": winner if conflict_detected else "none",
            "reason": reason if conflict_detected else "no_conflict",
            "timestamp": __import__("time").time(),
        },
        "fallback_marker": fallback_marker or "none",
        "semantic_origin": "routing_authority_boundary",
    }


def get_fallback_marker(
    verification_required: bool = False,
    verification_priority: int = 0,
    fastpath_used: bool = False,
    agent_used: bool = False,
    llm_used: bool = False,
    conflict_detected: bool = False,
) -> str:
    """Generate fallback marker for traceability.
    
    Fallback markers indicate what degradation/compensation mechanism
    was used when the primary path couldn't be followed.
    
    Args:
        verification_required: Whether grounded verification was needed
        verification_priority: Priority level (0-3)
        fastpath_used: Whether fastpath was used
        agent_used: Whether agent was used
        llm_used: Whether LLM was used
        conflict_detected: Whether routing conflict was detected
        
    Returns:
        Fallback marker string
    """
    markers = []
    
    if conflict_detected:
        markers.append("authority_conflict_resolved")
    
    if verification_required:
        if verification_priority >= 3:
            markers.append("verification_degraded_fastpath")
        elif verification_priority >= 2:
            markers.append("verification_bypassed_template")
        else:
            markers.append("verification_noted")
    
    if fastpath_used:
        markers.append("fastpath")
    elif agent_used:
        markers.append("agent_orchestration")
    elif llm_used:
        markers.append("llm_direct")
    else:
        markers.append("no_route")
    
    return "|".join(markers) if markers else "none"


# ═══════════════════════════════════════════════════════════════════════════
# MODULE METADATA
# ═══════════════════════════════════════════════════════════════════════════

__version__ = "1.1.0"
__author__ = "Claude Code"
__description__ = "Routing semantic guards for BrainSession with Authority Boundary"

# What this module does NOT contain:
# - NO chat orchestration logic
# - NO memory management
# - NO tool execution
# - NO response generation
# - NO stateful operations
# - NO side effects
