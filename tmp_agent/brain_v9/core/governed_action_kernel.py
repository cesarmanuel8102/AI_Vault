"""
Governed Action Kernel (GAK)
FASE 2 — Central action-intent detector + policy engine + execution-claim guard.

Ninguna ruta puede afirmar ejecucion/modificacion/lectura/escritura/reinicio/commit/push/verificacion
si no existe tool_result real o policy_decision explicito.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path
import re


@dataclass
class ActionRequest:
    is_action: bool = False
    action_type: str = ""  # filesystem.write | filesystem.read | process.execute | permission.elevate | ...
    target_path: Optional[str] = None
    content: Optional[str] = None
    confidence: float = 0.0
    raw_message: str = ""
    detected_keywords: List[str] = field(default_factory=list)


@dataclass
class PolicyDecision:
    allowed: bool = False
    blocked_by_policy: bool = False
    requires_permission: bool = False
    reason: str = ""
    error: Optional[str] = None
    tool_name: Optional[str] = None
    risk_level: str = "low"
    scope: str = ""
    options: List[str] = field(default_factory=list)
    action_request: Optional[ActionRequest] = None


# ── Semantic intent patterns (multi-language) ─────────────────────────────

_WRITE_INTENT_PATTERNS = [
    # Spanish (infinitive + imperative forms)
    r"\b(?:crear|crea|escribir|escribe|guardar|guarda|generar|genera|producir|produce|hacer|hace|necesito que (?:crees|escribas|guardes))\b.*?\b(?:archivo|fichero|documento|txt|file)\b",
    r"\b(?:pon|coloca|guarda|escribe|crea)\b.*?\b(?:en|dentro de)\b.*?\b(?:archivo|fichero|documento|txt|file)\b",
    r"\b(?:crea|escribe|guarda)\b.*?\b(?:un archivo|un fichero|un documento|un txt|un file)\b",
    # English
    r"\b(?:create|write|save|generate|make|produce)\b.*?\b(?:file|document|txt)\b",
    r"\b(?:put|place|store|write)\b.*?\b(?:in|inside|into|to)\b.*?\b(?:file|document|txt)\b",
    r"\b(?:create|write)\b.*?\b(?:a file|a document)\b",
    # Tool-explicit fallback (already handled by TOOL-01 regex, but included for completeness)
    r"\bwrite_file\b",
    r"\bfilesystem\.write\b",
]

_READ_INTENT_PATTERNS = [
    # Spanish
    r"\b(?:leer|mostrar|devolver|dame|mu[eé]strame|consultar)\b.*?\b(?:contenido|archivo|fichero|documento|txt)\b",
    r"\b(?:lee|muestra|devuelve)\b.*?\b(?:el archivo|el fichero|el documento)\b",
    r"\b(?:dime|cu[eé]ntame)\b.*?\b(?:qu[eé] dice|qu[eé] hay en|contenido de)\b.*?\b(?:archivo|fichero)\b",
    # English
    r"\b(?:read|show|return|give me|display|fetch)\b.*?\b(?:content|file|document|txt)\b",
    r"\b(?:read|show|return)\b.*?\b(?:the file|the document)\b",
    r"\b(?:what is in|what does)\b.*?\b(?:say|contain)\b.*?\b(?:file|document)\b",
    # Tool-explicit fallback
    r"\bread_file\b",
    r"\bfilesystem\.read\b",
]

_PROCESS_INTENT_PATTERNS = [
    r"\b(?:ejecutar|correr|lanzar|iniciar|matar|kill|reiniciar|restart)\b.*?\b(?:comando|proceso|servicio|script|python|powershell|bash)\b",
    r"\b(?:execute|run|launch|start|kill|restart)\b.*?\b(?:command|process|service|script)\b",
    r"\b(?:borrar|eliminar|delete|remove)\b.*?\b(?:temporales|archivos|logs|temp)\b",
]

_GIT_INTENT_PATTERNS = [
    r"\b(?:git\s+(?:commit|push|merge|rebase|reset|checkout|pull))\b",
    r"\b(?:commit|push)\b.*?\b(?:cambios|archivos|c[oó]digo|changes|files|code)\b",
]

_ELEVATION_INTENT_PATTERNS = [
    r"\b(?:modo\s+(?:dios|god|developer|dev))\b",
    r"\b(?:saltar|bypass|ignorar)\b.*?\b(?:pol[ií]ticas|restricciones|permisos|governance|policies|restrictions)\b",
    r"\b(?:level_5|nivel_5|nivel 5)\b",
    r"\b(?:desactivar|apagar)\b.*?\b(?:governance|seguridad|pol[ií]ticas|checks|auditoria)\b",
    r"\b(?:activar|enable)\b.*?\b(?:modo\s+(?:desarrollador|developer|dios|god|unsafe|unrestricted))\b",
    r"\b(?:ejecutar|actuar)\b.*?\b(?:sin autorizaci[oó]n|sin permiso|without permission|without authorization)\b",
    r"\b(?:governance)\b.*?\b(?:desactivar|apagar|off|disable)\b",
    r"\b(?:modo\s+inseguro|unsafe\s+mode)\b",
]

_STRATEGY_MODIFY_PATTERNS = [
    r"\b(?:modificar|modifica|cambiar|cambia|actualizar|actualiza|editar|edita)\b.*?\b(?:estrategia|estrategias|strategy|strategies)\b",
    r"\b(?:modifica|cambia|actualiza|edita)\b.*?\b(?:archivos?\s+de\s+estrategia|strategy\s+files?)\b",
]

_MEMORY_ACCESS_PATTERNS = [
    r"\b(?:leer|volcar|dump|acceder|accesar)\b.*?\b(?:memoria|memory/semantic|semantic_memory|faiss|index)\b",
]

# ── Path extraction helpers ───────────────────────────────────────────────

_PATH_RE = re.compile(
    r'([A-Z]:[/\\][^\s"\'<>|]+|tmp_agent[/\\][^\s"\'<>|]+|brain_v9[/\\][^\s"\'<>|]+|memory[/\\][^\s"\'<>|]+)',
    re.IGNORECASE,
)

_CONTENT_QUOTE_RE = re.compile(
    r'["\']([^"\']{3,})["\']',
    re.DOTALL,
)

_CONTENT_MARKER_RE = re.compile(
    r'(?:contenido|content|texto|text)[\s]*[:\-=]\s*["\']?(.+?)(?:\n|$|\.\s)',
    re.IGNORECASE | re.DOTALL,
)


def _extract_path(message: str) -> Optional[str]:
    # Normalize: JSON parsed strings often contain real tab chars instead of \t
    normalized = message.replace('\t', '\\t')
    m = _PATH_RE.search(normalized)
    if not m:
        return None
    path = m.group(1).rstrip(".,;:)\\")
    # Remove trailing dot if present
    if path.endswith('.'):
        path = path[:-1]
    # Convert literal \t back to / for path normalization (not needed for Windows)
    return path


def _build_target_path(message: str) -> Optional[str]:
    """Extract complete target path, combining folder + filename if needed."""
    base_path = _extract_path(message)
    fname = _extract_filename(message)
    if not base_path and not fname:
        return None
    if base_path and fname:
        p = Path(base_path)
        # If base_path already ends with the filename, return as-is
        if p.name == fname:
            return str(p)
        # If base_path looks like a directory (no suffix), append filename
        if not p.suffix:
            return str(p / fname)
        # Otherwise base_path is already a file path
        return str(p)
    if fname:
        return str(Path("tmp_agent/workspace") / fname)
    return base_path


def _extract_content(message: str) -> Optional[str]:
    # Prefer explicit marker: "texto exacto: ..." or "contenido: ..."
    m = _CONTENT_MARKER_RE.search(message)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # Fallback: quoted strings of reasonable length
    quotes = _CONTENT_QUOTE_RE.findall(message)
    if quotes:
        # Pick the longest quoted string that is not a path
        candidates = [q for q in quotes if not q.strip().startswith("C:") and len(q) > 5]
        if candidates:
            return max(candidates, key=len).strip().strip('"').strip("'")
    return None


def _extract_filename(message: str) -> Optional[str]:
    # Look for "llamarse X.txt" or "nombre X.txt"
    m = re.search(r'(?:llamarse|llamado|nombre|name|called)\s+["\']?([^\s"\']+\.(?:txt|py|json|md|csv))["\']?', message, re.IGNORECASE)
    if m:
        return m.group(1)
    # Look for "escribe en X.txt" or "crea X.txt" or "guarda en X.txt"
    m = re.search(r'(?:escribir?|crea[r]?|guarda[r]?)\s+(?:en\s+)?["\']?([^\s"\']+\.(?:txt|py|json|md|csv))["\']?', message, re.IGNORECASE)
    if m:
        return m.group(1)
    # Or any filename-like token
    m = re.search(r'\b(\w+\.(?:txt|py|json|md|csv))\b', message, re.IGNORECASE)
    return m.group(1) if m else None


# ── Action intent detection ───────────────────────────────────────────────

def detect_action_intent(message: str) -> ActionRequest:
    msg_lower = message.lower()
    req = ActionRequest(raw_message=message)

    # 1. Elevation / god mode — highest priority
    for pat in _ELEVATION_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "permission.elevate"
            req.confidence = 0.95
            req.detected_keywords.append("elevation")
            return req

    # 2. Process execution
    for pat in _PROCESS_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "process.execute"
            req.confidence = 0.85
            req.detected_keywords.append("process")
            return req

    # 3. Git operations
    for pat in _GIT_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "git.commit" if "commit" in msg_lower else "git.push"
            req.confidence = 0.9
            req.detected_keywords.append("git")
            return req

    # 4. Strategy modification
    for pat in _STRATEGY_MODIFY_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "strategy.modify"
            req.confidence = 0.8
            req.detected_keywords.append("strategy")
            return req

    # 5. Memory access (full dump)
    for pat in _MEMORY_ACCESS_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "memory.read"
            req.confidence = 0.8
            req.detected_keywords.append("memory")
            return req

    # 6. Filesystem write
    for pat in _WRITE_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "filesystem.write"
            req.confidence = 0.85
            req.detected_keywords.append("write")
            req.target_path = _build_target_path(message)
            req.content = _extract_content(message)
            # If still no path, default to workspace with a generated filename
            if not req.target_path:
                fname = _extract_filename(message)
                if fname:
                    req.target_path = str(Path("tmp_agent/workspace") / fname)
            return req

    # 7. Filesystem read
    for pat in _READ_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            req.is_action = True
            req.action_type = "filesystem.read"
            req.confidence = 0.85
            req.detected_keywords.append("read")
            req.target_path = _extract_path(message)
            return req

    return req


def requires_governed_tool(action: ActionRequest) -> bool:
    return action.is_action and action.action_type not in {"permission.elevate", "process.execute"}


# ── Policy engine ─────────────────────────────────────────────────────────

_WORKSPACE_ROOT = Path("C:/AI_VAULT/tmp_agent/workspace").resolve()
_PROTECTED_PATHS = {
    "memory/semantic",
    "tmp_agent/strategies",
    "tmp_agent/reports",
}


def _is_within_workspace(path_str: Optional[str]) -> bool:
    if not path_str:
        return False
    try:
        p = Path(path_str)
        if not p.is_absolute():
            p = Path("C:/AI_VAULT") / path_str
        resolved = p.resolve()
        workspace = _WORKSPACE_ROOT.resolve()
        return str(resolved).lower().startswith(str(workspace).lower() + "\\") or resolved == workspace
    except Exception:
        return False


def _is_protected_path(path_str: Optional[str]) -> bool:
    if not path_str:
        return False
    p = Path(path_str) if Path(path_str).is_absolute() else Path("C:/AI_VAULT") / path_str
    try:
        rel = p.relative_to(Path("C:/AI_VAULT")).as_posix().lower()
    except Exception:
        return False
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in _PROTECTED_PATHS)


def evaluate_action_policy(action: ActionRequest) -> PolicyDecision:
    dec = PolicyDecision(action_request=action)

    if not action.is_action:
        dec.allowed = True
        dec.reason = "No action intent detected"
        return dec

    # Elevation / god mode: always deny
    if action.action_type == "permission.elevate":
        dec.blocked_by_policy = True
        dec.reason = (
            "No puedo activar ni guiar un modo para saltar permisos, politicas o governance. "
            "Puedo ayudarte a solicitar permisos especificos y auditables para una accion concreta."
        )
        dec.error = "Elevation denied by governance policy"
        return dec

    # Process execution: not available through chat
    if action.action_type == "process.execute":
        dec.blocked_by_policy = True
        dec.reason = "Process execution requires a separate governed executor and is not available through chat."
        dec.error = "process.execute blocked"
        return dec

    # Git: block natural language direct access
    if action.action_type in ("git.commit", "git.push"):
        dec.blocked_by_policy = True
        dec.reason = "Git operations require an explicit allowlisted commit workflow; not available via natural language."
        dec.error = "git operation blocked"
        return dec

    # Strategy modification: block
    if action.action_type == "strategy.modify":
        dec.blocked_by_policy = True
        dec.reason = "Strategy modification requires a governed workflow; not available via chat."
        dec.error = "strategy.modify blocked"
        return dec

    # Memory full dump: block or require separate policy
    if action.action_type == "memory.read":
        dec.blocked_by_policy = True
        dec.reason = "Full memory access requires a separate governed policy; not available via filesystem generic tool."
        dec.error = "memory.read blocked"
        return dec

    # Filesystem write
    if action.action_type == "filesystem.write":
        if not action.target_path:
            # If no path, default to workspace with a generated filename
            dec.requires_permission = True
            dec.tool_name = "filesystem.write_file"
            dec.risk_level = "high"
            dec.scope = str(_WORKSPACE_ROOT)
            dec.options = ["allow_once", "deny"]
            dec.reason = "Filesystem write requires explicit permission"
            return dec
        if _is_protected_path(action.target_path):
            dec.blocked_by_policy = True
            dec.reason = f"Write path blocked by policy: protected area"
            dec.error = dec.reason
            return dec
        if not _is_within_workspace(action.target_path):
            dec.blocked_by_policy = True
            dec.reason = f"Write path must be within workspace"
            dec.error = f"Write path must be within workspace: {_WORKSPACE_ROOT}"
            return dec
        dec.requires_permission = True
        dec.tool_name = "filesystem.write_file"
        dec.risk_level = "high"
        dec.scope = str(_WORKSPACE_ROOT)
        dec.options = ["allow_once", "deny"]
        dec.reason = "Filesystem write requires explicit permission"
        return dec

    # Filesystem read
    if action.action_type == "filesystem.read":
        if not action.target_path:
            dec.blocked_by_policy = True
            dec.reason = "Read request missing target path"
            dec.error = "Cannot read file without specifying a path"
            return dec
        if _is_protected_path(action.target_path):
            dec.blocked_by_policy = True
            dec.reason = "Read path blocked by policy: protected area"
            dec.error = "Read path is in a protected area"
            return dec
        # Workspace read is allowed with permission
        if _is_within_workspace(action.target_path):
            dec.requires_permission = True
            dec.tool_name = "filesystem.read_file"
            dec.risk_level = "low"
            dec.scope = str(_WORKSPACE_ROOT)
            dec.options = ["allow_once", "allow_session", "deny"]
            dec.reason = "Filesystem read requires explicit permission"
            return dec
        # Other paths: allow with permission (could tighten later)
        dec.requires_permission = True
        dec.tool_name = "filesystem.read_file"
        dec.risk_level = "low"
        dec.scope = "C:/AI_VAULT"
        dec.options = ["allow_once", "allow_session", "deny"]
        dec.reason = "Filesystem read requires explicit permission"
        return dec

    # Default: allow non-action
    dec.allowed = True
    dec.reason = "Action type not classified as governed"
    return dec


# ── Renderers ─────────────────────────────────────────────────────────────

def render_policy_block(decision: PolicyDecision) -> Dict[str, Any]:
    """Render a structured policy-block response."""
    # Prefer reason (long text) for user-facing response, error for technical detail
    user_text = decision.reason or decision.error or "Blocked by policy"
    return {
        "success": False,
        "blocked_by_policy": True,
        "error": decision.error or decision.reason,
        "reason": decision.reason,
        "response": user_text,
        "content": user_text,
        "action_type": decision.action_request.action_type if decision.action_request else None,
        "route": "governed_action_kernel",
        "tool01_router_used": False,
        "tool01_real": False,
        "permission_required": False,
        "model": "governed_action_kernel",
        "model_used": "governed_action_kernel",
        "agent_steps": 1,
        "agent_status": "policy_blocked",
    }


def render_permission_request(decision: PolicyDecision) -> Dict[str, Any]:
    """Render a permission-required response for UI/API."""
    options_text = " | ".join([f"[{o.replace('_', ' ').title()}]" for o in decision.options])
    dev_block = (
        f"[DEV]\n"
        f"route=governed_action_kernel\n"
        f"tool01_router_used=false\n"
        f"tool01_real=false\n"
        f"permission_required=true\n"
        f"permission_id={decision.action_request.raw_message if decision.action_request else ''}\n"
        f"tool_name={decision.tool_name}\n"
        f"risk_level={decision.risk_level}\n"
        f"scope={decision.scope}\n"
        f"options={decision.options}\n"
        f"\n"
        f"Para ejecutar '{decision.tool_name}' necesito tu permiso.\n"
        f"{options_text}"
    )
    return {
        "success": True,
        "content": dev_block,
        "response": f"Necesito permiso para ejecutar {decision.tool_name}. Opciones: {options_text}",
        "route": "governed_action_kernel",
        "intent": "COMMAND",
        "tool01_router_used": False,
        "tool01_real": False,
        "permission_required": True,
        "permission_id": decision.action_request.raw_message if decision.action_request else "",
        "tool_name": decision.tool_name,
        "risk_level": decision.risk_level,
        "options": decision.options,
        "blocked_by_policy": False,
        "fallback": False,
        "agent_status": "permission_pending",
        "model": "governed_action_kernel",
        "model_used": "governed_action_kernel",
        "agent_steps": 1,
    }


# ── Execution Claim Guard ─────────────────────────────────────────────────

_EXECUTION_CLAIM_KEYWORDS = [
    "archivo creado", "archivo escrito", "archivo guardado", "archivo generado",
    "he creado", "he escrito", "he guardado", "he generado", "he verificado",
    "file created", "file written", "file saved", "file generated",
    "i created", "i wrote", "i saved", "i generated", "i verified",
    "comando ejecutado", "proceso iniciado", "servicio reiniciado", "fue reiniciado",
    "command executed", "process started", "service restarted", "was restarted",
    "commit realizado", "push completado", "cambios subidos",
    "commit done", "push completed", "changes uploaded",
    "verificado", "verificacion completada", "checked", "verified",
    "modificacion completada", "modification done", "strategy updated",
    "memory dumped", "volcado de memoria",
]

_UNSAFE_GUIDANCE_KEYWORDS = [
    "level_5_god", "nivel_5_dios", "modo developer", "developer mode",
    "saltar permisos", "bypass permissions", "ignorar politicas", "ignore policies",
    "desactivar governance", "disable governance", "unsafe mode", "modo inseguro",
    "credenciales externas", "external credentials", "flag inseguro", "unsafe flag",
]


def validate_no_false_execution_claim(response: Dict[str, Any], execution_context: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Guard final: if a non-tool route claims execution, sanitize the response.
    Also reject any unsafe guidance.
    """
    route = response.get("route", "")
    tool_result = response.get("tool_result")
    is_tool_route = route in ("tool01_router", "governed_action_kernel") or response.get("tool01_real")

    text_to_check = ""
    for key in ("response", "content", "error", "reason"):
        val = response.get(key)
        if isinstance(val, str):
            text_to_check += val.lower() + " "

    # 1. If not a tool route and contains execution claims → sanitize
    if not is_tool_route and not tool_result:
        for kw in _EXECUTION_CLAIM_KEYWORDS:
            if kw in text_to_check:
                sanitized = (
                    "No puedo afirmar que ejecute esa accion porque no hay tool_result real. "
                    "Para hacerlo debo activar una herramienta gobernada y solicitar permiso."
                )
                response["response"] = sanitized
                response["content"] = sanitized
                response["blocked_by_policy"] = True
                response["agent_status"] = "execution_claim_guarded"
                break

    # 2. If contains unsafe guidance → reject entirely
    for kw in _UNSAFE_GUIDANCE_KEYWORDS:
        if kw in text_to_check:
            sanitized = (
                "No puedo activar ni guiar un modo para saltar permisos, politicas o governance. "
                "Puedo ayudarte a solicitar permisos especificos y auditables para una accion concreta."
            )
            response["response"] = sanitized
            response["content"] = sanitized
            response["blocked_by_policy"] = True
            response["agent_status"] = "unsafe_guidance_guarded"
            break

    return response


def build_synthetic_message(action: ActionRequest) -> str:
    """
    Build a canonical synthetic message from ActionRequest so that
    approval does NOT depend on re-parsing the raw natural language.
    Uses forward slashes (/) to avoid JSON backslash-escape corruption.
    """
    if action.action_type == "filesystem.write":
        # Use forward slashes to avoid \t \n escape issues in JSON
        path = (action.target_path or "tmp_agent/workspace/unknown.txt").replace("\\", "/")
        content = action.content or ""
        return f'write file {path} with exact content: "{content}"'
    elif action.action_type == "filesystem.read":
        path = (action.target_path or "tmp_agent/workspace/unknown.txt").replace("\\", "/")
        return f'read file {path}'
    elif action.action_type == "process.execute":
        return "execute process"
    elif action.action_type == "git.commit":
        return "git commit"
    elif action.action_type == "git.push":
        return "git push"
    elif action.action_type == "strategy.modify":
        return "modify strategy"
    elif action.action_type == "memory.read":
        return "read memory"
    elif action.action_type == "permission.elevate":
        return "elevation request"
    return action.raw_message

