"""
P2-F Commit 1: GitHub Source Connector

Conector read-only/dry-run para fuentes GitHub.
NO escribe a SemanticMemory.
NO usa GitHub write APIs.
NO expone tokens en logs.

REGLAS DURAS:
- Solo lectura de GitHub API (tree endpoint)
- NO escribe archivos por defecto
- NO toca memory/semantic
- GITHUB_WRITE_ALLOWED = False SIEMPRE
- SEMANTIC_WRITE_ALLOWED = False SIEMPRE
- PROMOTION_ALLOWED = False SIEMPRE
- DRY_RUN_ONLY = True SIEMPRE
- Token solo desde variable de entorno
- Token nunca logueado (máscara: ***)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import os
import urllib.request
import urllib.error


# Constantes de seguridad - SIEMPRE False
GITHUB_WRITE_ALLOWED = False
SEMANTIC_WRITE_ALLOWED = False
PROMOTION_ALLOWED = False
DRY_RUN_ONLY = True


class GitHubSourceError(Exception):
    """Error específico del conector GitHub."""
    pass


class GitHubSourceTokenMode(str, Enum):
    """Modo de token para GitHub API."""
    NONE = "none"  # Sin token, modo público
    ENV = "env"  # Token desde variable de entorno


@dataclass
class GitHubSourceRequest:
    """
    Solicitud de fuente GitHub.
    
    Attributes:
        owner: Owner del repositorio
        repo: Nombre del repositorio
        branch: Branch a inspeccionar (default: "main")
        include_globs: Patrones glob para incluir archivos
        exclude_globs: Patrones glob para excluir archivos
        max_files: Máximo de archivos a seleccionar
        max_bytes_per_file: Máximo de bytes por archivo
    """
    owner: str
    repo: str
    branch: str = "main"
    include_globs: Tuple[str, ...] = ("*.py", "*.md", "*.json", "*.yaml", "*.yml")
    exclude_globs: Tuple[str, ...] = ("node_modules/*", ".git/*", "__pycache__/*", "*.pyc")
    max_files: int = 50
    max_bytes_per_file: int = 200_000


@dataclass
class GitHubSourceFile:
    """
    Archivo fuente de GitHub.
    
    Attributes:
        path: Ruta del archivo en el repo
        sha: SHA del blob
        size: Tamaño en bytes
        download_url: URL para descargar contenido
        html_url: URL para ver en GitHub
        content_hash: Hash SHA-256 del contenido (si descargado)
        selected: Si fue seleccionado según filtros
        reason: Razón de selección/rechazo
    """
    path: str
    sha: Optional[str] = None
    size: Optional[int] = None
    download_url: Optional[str] = None
    html_url: Optional[str] = None
    content_hash: Optional[str] = None
    selected: bool = False
    reason: str = ""


@dataclass
class GitHubEvidenceBundle:
    """
    Bundle de evidencia de fuente GitHub.
    
    Este bundle representa el resultado de inspeccionar
    un repositorio GitHub en modo read-only.
    
    Attributes:
        source_type: Tipo de fuente (siempre "github")
        repo: Repositorio completo (owner/repo)
        branch: Branch inspeccionado
        commit: Commit hash (si disponible)
        fetched_at_utc: Timestamp UTC de fetch
        files_seen: Total de archivos vistos
        files_selected: Lista de paths seleccionados
        selected_file_git_shas: Mapa path -> Git blob SHA (desde GitHub API tree)
        selected_file_content_sha256: Mapa path -> SHA-256 calculado localmente
                                     (solo si se recibió contenido real)
        promotion_allowed: Siempre False
        semantic_write_allowed: Siempre False
        dry_run: Siempre True
        token_mode: Modo de token usado
        errors: Lista de errores no fatales
    """
    source_type: str = "github"
    repo: str = ""
    branch: str = "main"
    commit: Optional[str] = None
    fetched_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    files_seen: int = 0
    files_selected: List[str] = field(default_factory=list)
    selected_file_git_shas: Dict[str, str] = field(default_factory=dict)
    selected_file_content_sha256: Dict[str, str] = field(default_factory=dict)
    promotion_allowed: bool = False  # SIEMPRE False
    semantic_write_allowed: bool = False  # SIEMPRE False
    dry_run: bool = True  # SIEMPRE True
    token_mode: str = GitHubSourceTokenMode.NONE.value
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir bundle a dict."""
        return {
            "source_type": self.source_type,
            "repo": self.repo,
            "branch": self.branch,
            "commit": self.commit,
            "fetched_at_utc": self.fetched_at_utc,
            "files_seen": self.files_seen,
            "files_selected": self.files_selected,
            "selected_file_git_shas": self.selected_file_git_shas,
            "selected_file_content_sha256": self.selected_file_content_sha256,
            "promotion_allowed": self.promotion_allowed,
            "semantic_write_allowed": self.semantic_write_allowed,
            "dry_run": self.dry_run,
            "token_mode": self.token_mode,
            "errors": self.errors,
        }


def mask_token(token: str) -> str:
    """
    Enmascarar token para logging.
    
    Args:
        token: Token a enmascarar
        
    Returns:
        String enmascarado (***... o empty)
    """
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return token[:4] + "***" + token[-4:]


def sha256_text(text: str) -> str:
    """
    Calcular SHA-256 de texto.
    
    Args:
        text: Texto a hashear
        
    Returns:
        Hash SHA-256 hex
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def should_select_path(
    path: str,
    include_globs: Tuple[str, ...],
    exclude_globs: Tuple[str, ...],
) -> Tuple[bool, str]:
    """
    Determinar si un path debe ser seleccionado.
    
    Args:
        path: Ruta del archivo
        include_globs: Patrones de inclusión
        exclude_globs: Patrones de exclusión
        
    Returns:
        Tuple de (seleccionado, razón)
    """
    import fnmatch
    
    # Primero verificar exclusiones
    for exclude_pattern in exclude_globs:
        if fnmatch.fnmatch(path, exclude_pattern) or fnmatch.fnmatch(
            path.split("/")[-1], exclude_pattern
        ):
            return False, f"EXCLUDED_BY_PATTERN:{exclude_pattern}"
    
    # Luego verificar inclusiones
    for include_pattern in include_globs:
        if fnmatch.fnmatch(path, include_pattern) or fnmatch.fnmatch(
            path.split("/")[-1], include_pattern
        ):
            return True, f"INCLUDED_BY_PATTERN:{include_pattern}"
    
    return False, "NO_MATCHING_INCLUDE_PATTERN"


def build_api_url(owner: str, repo: str, branch: str) -> str:
    """
    Construir URL de API GitHub para tree recursivo.
    
    Args:
        owner: Owner del repo
        repo: Nombre del repo
        branch: Branch a inspeccionar
        
    Returns:
        URL completa de la API
    """
    return f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"


def fetch_github_tree(
    request: GitHubSourceRequest,
    token: Optional[str] = None,
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> Dict[str, Any]:
    """
    Fetch tree de GitHub API.
    
    Args:
        request: Solicitud de fuente
        token: Token opcional para auth
        opener: Opener custom para testing
        
    Returns:
        Dict con respuesta de API
        
    Raises:
        GitHubSourceError: Si falla la petición
    """
    url = build_api_url(request.owner, request.repo, request.branch)
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI_Vault-P2F-GitHubSourceConnector/1.0",
    }
    
    if token:
        headers["Authorization"] = f"token {token}"
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        if opener:
            response = opener.open(req)
        else:
            response = urllib.request.urlopen(req, timeout=30)
        
        data = json.loads(response.read().decode("utf-8"))
        return data
        
    except urllib.error.HTTPError as e:
        raise GitHubSourceError(f"GitHub API HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise GitHubSourceError(f"GitHub API URL Error: {e.reason}")
    except json.JSONDecodeError as e:
        raise GitHubSourceError(f"Invalid JSON response: {e}")


def build_evidence_bundle(
    request: GitHubSourceRequest,
    tree_payload: Dict[str, Any],
    file_payloads: Optional[Dict[str, str]] = None,
) -> GitHubEvidenceBundle:
    """
    Construir bundle de evidencia desde tree payload.
    
    Args:
        request: Solicitud de fuente
        tree_payload: Respuesta de GitHub API tree
        file_payloads: Contenido de archivos descargados (opcional)
        
    Returns:
        GitHubEvidenceBundle completo
    """
    bundle = GitHubEvidenceBundle(
        repo=f"{request.owner}/{request.repo}",
        branch=request.branch,
        commit=tree_payload.get("sha"),
        token_mode=GitHubSourceTokenMode.NONE.value,  # Actualizar afuera si hay token
    )
    
    tree = tree_payload.get("tree", [])
    bundle.files_seen = len(tree)
    
    selected_files: List[str] = []
    selected_git_shas: Dict[str, str] = {}
    selected_content_sha256: Dict[str, str] = {}
    errors: List[str] = []
    
    for item in tree:
        if item.get("type") != "blob":
            continue
        
        path = item.get("path", "")
        selected, reason = should_select_path(
            path,
            request.include_globs,
            request.exclude_globs,
        )
        
        if selected:
            if len(selected_files) >= request.max_files:
                errors.append(f"MAX_FILES_REACHED: Truncated at {request.max_files}")
                break
            
            selected_files.append(path)
            
            # Siempre guardar Git SHA si está disponible
            if item.get("sha"):
                selected_git_shas[path] = item["sha"]
            
            # Si tenemos contenido real, calcular SHA-256 (si no excede límite)
            if file_payloads and path in file_payloads:
                content = file_payloads[path]
                content_bytes = len(content.encode("utf-8"))
                if content_bytes > request.max_bytes_per_file:
                    errors.append(f"FILE_TOO_LARGE: {path} exceeds {request.max_bytes_per_file} bytes, content SHA-256 not computed")
                    # NO calcular SHA-256 de contenido truncado
                else:
                    # Solo calcular SHA-256 de contenido completo
                    selected_content_sha256[path] = sha256_text(content)
    
    bundle.files_selected = selected_files
    bundle.selected_file_git_shas = selected_git_shas
    bundle.selected_file_content_sha256 = selected_content_sha256
    bundle.errors = errors
    
    return bundle


def run_github_source_dry_run(
    request: GitHubSourceRequest,
    token_env_var: str = "GITHUB_TOKEN",
    opener: Optional[urllib.request.OpenerDirector] = None,
) -> GitHubEvidenceBundle:
    """
    Ejecutar dry-run de fuente GitHub.
    
    Este es el entry point principal. Ejecuta todo el flujo:
    1. Obtiene token de env var (opcional)
    2. Fetch tree desde GitHub API
    3. Construye evidence bundle
    4. Valida seguridad
    
    Args:
        request: Solicitud de fuente
        token_env_var: Nombre de variable de entorno para token
        opener: Opener custom para testing
        
    Returns:
        GitHubEvidenceBundle
    """
    # Obtener token
    token = os.environ.get(token_env_var, "").strip()
    token_mode = GitHubSourceTokenMode.ENV if token else GitHubSourceTokenMode.NONE
    
    # Fetch tree
    try:
        tree_payload = fetch_github_tree(request, token if token else None, opener)
    except GitHubSourceError as e:
        # Devolver bundle con error
        return GitHubEvidenceBundle(
            repo=f"{request.owner}/{request.repo}",
            branch=request.branch,
            errors=[str(e)],
            token_mode=token_mode.value,
        )
    
    # Construir bundle
    bundle = build_evidence_bundle(request, tree_payload)
    bundle.token_mode = token_mode.value
    
    # Validaciones de seguridad (asserts para testing)
    assert bundle.promotion_allowed == False, "SECURITY: promotion_allowed must be False"
    assert bundle.semantic_write_allowed == False, "SECURITY: semantic_write_allowed must be False"
    assert bundle.dry_run == True, "SECURITY: dry_run must be True"
    
    return bundle


class GitHubSourceConnector:
    """
    Conector read-only para fuentes GitHub.
    
    Esta clase proporciona una interfaz orientada a objetos
    sobre las funciones puras del módulo.
    
    Ejemplo:
        connector = GitHubSourceConnector()
        request = GitHubSourceRequest(
            owner="cesarmanuel8102",
            repo="AI_Vault",
            branch="codex/own-capital-sustainable-return",
        )
        bundle = connector.inspect(request)
    """
    
    def __init__(self, token_env_var: str = "GITHUB_TOKEN"):
        """
        Inicializar conector.
        
        Args:
            token_env_var: Variable de entorno para token
        """
        self._token_env_var = token_env_var
    
    def inspect(
        self,
        request: GitHubSourceRequest,
        opener: Optional[urllib.request.OpenerDirector] = None,
    ) -> GitHubEvidenceBundle:
        """
        Inspeccionar repositorio GitHub.
        
        Args:
            request: Solicitud de fuente
            opener: Opener custom para testing
            
        Returns:
            GitHubEvidenceBundle
        """
        return run_github_source_dry_run(
            request,
            token_env_var=self._token_env_var,
            opener=opener,
        )
    
    def get_security_constants(self) -> Dict[str, bool]:
        """
        Obtener constantes de seguridad.
        
        Returns:
            Dict con flags de seguridad
        """
        return {
            "GITHUB_WRITE_ALLOWED": GITHUB_WRITE_ALLOWED,
            "SEMANTIC_WRITE_ALLOWED": SEMANTIC_WRITE_ALLOWED,
            "PROMOTION_ALLOWED": PROMOTION_ALLOWED,
            "DRY_RUN_ONLY": DRY_RUN_ONLY,
        }
