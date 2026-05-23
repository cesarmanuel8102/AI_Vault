"""
P2-E Commit 4D-DependencyMapping: Semantic Memory Extra File Dependency Mapper

Mapeo estático read-only de dependencias de archivos extra en memory/semantic.
Este módulo escanea el repositorio buscando referencias a archivos extra
sin ejecutar código ni importar módulos sospechosos.

REGLAS DURAS:
- Solo lectura de archivos de texto
- NO ejecutar código
- NO importar módulos runtime
- NO escribir archivos
- NO usar subprocess
- NO usar open()
- NO importar faiss
- NO importar semantic_memory_bridge
- dry_run_only=True SIEMPRE
- allow_real_write=False SIEMPRE
- requires_manual_review=True si hay hits de riesgo
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid


class SemanticMemoryDependencyKind(str, Enum):
    """Tipo de dependencia detectada."""
    EXACT_FILENAME_REFERENCE = "EXACT_FILENAME_REFERENCE"
    MEMORY_SEMANTIC_PATH_REFERENCE = "MEMORY_SEMANTIC_PATH_REFERENCE"
    FAISS_ARTIFACT_REFERENCE = "FAISS_ARTIFACT_REFERENCE"
    MIGRATION_PROGRESS_REFERENCE = "MIGRATION_PROGRESS_REFERENCE"
    SEMANTIC_MEMORY_GENERIC_REFERENCE = "SEMANTIC_MEMORY_GENERIC_REFERENCE"
    UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"


class SemanticMemoryDependencyRole(str, Enum):
    """Rol del archivo que contiene la referencia."""
    RUNTIME_CORE = "RUNTIME_CORE"
    BRIDGE_OR_ADAPTER = "BRIDGE_OR_ADAPTER"
    SCRIPT_OR_TOOLING = "SCRIPT_OR_TOOLING"
    TEST = "TEST"
    DOCS = "DOCS"
    SMOKE = "SMOKE"
    UNKNOWN = "UNKNOWN"


class SemanticMemoryDependencyAccessMode(str, Enum):
    """Modo de acceso inferido."""
    READ_ONLY_LIKELY = "READ_ONLY_LIKELY"
    WRITE_LIKELY = "WRITE_LIKELY"
    DELETE_OR_MOVE_LIKELY = "DELETE_OR_MOVE_LIKELY"
    IMPORT_OR_RUNTIME_LIKELY = "IMPORT_OR_RUNTIME_LIKELY"
    UNKNOWN = "UNKNOWN"


class SemanticMemoryDependencyRisk(str, Enum):
    """Nivel de riesgo de la dependencia."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class SemanticMemoryDependencyHit:
    """
    Un hit de dependencia detectado.
    """
    target_name: str
    matched_token: str
    file_path: str
    line_number: int
    line_excerpt: str
    dependency_kind: SemanticMemoryDependencyKind
    dependency_role: SemanticMemoryDependencyRole
    access_mode: SemanticMemoryDependencyAccessMode
    risk: SemanticMemoryDependencyRisk
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "target_name": self.target_name,
            "matched_token": self.matched_token,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_excerpt": self.line_excerpt,
            "dependency_kind": self.dependency_kind.value,
            "dependency_role": self.dependency_role.value,
            "access_mode": self.access_mode.value,
            "risk": self.risk.value,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class SemanticMemoryDependencyMapReport:
    """
    Reporte de mapeo de dependencias.
    
    SIEMPRE bloqueado, nunca habilita escritura real.
    """
    map_id: str
    created_at_utc: str
    repo_root: str
    scanned_file_count: int
    skipped_file_count: int
    hit_count: int
    target_names: List[str]
    hits: List[SemanticMemoryDependencyHit]
    hits_by_target: Dict[str, int]
    hits_by_role: Dict[str, int]
    hits_by_access_mode: Dict[str, int]
    high_risk_hit_count: int
    write_like_hit_count: int
    runtime_like_hit_count: int
    requires_manual_review: bool
    allow_real_write: bool = False
    dry_run_only: bool = True
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "map_id": self.map_id,
            "created_at_utc": self.created_at_utc,
            "repo_root": self.repo_root,
            "scanned_file_count": self.scanned_file_count,
            "skipped_file_count": self.skipped_file_count,
            "hit_count": self.hit_count,
            "target_names": self.target_names,
            "hits": [h.to_dict() for h in self.hits],
            "hits_by_target": self.hits_by_target,
            "hits_by_role": self.hits_by_role,
            "hits_by_access_mode": self.hits_by_access_mode,
            "high_risk_hit_count": self.high_risk_hit_count,
            "write_like_hit_count": self.write_like_hit_count,
            "runtime_like_hit_count": self.runtime_like_hit_count,
            "requires_manual_review": self.requires_manual_review,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryExtraFileDependencyMapper:
    """
    Mapeador estático de dependencias de archivos extra.
    
    Responsabilidades:
    - Escanear archivos del repositorio buscando referencias
    - Clasificar dependencias por rol, modo de acceso y riesgo
    - NO ejecutar código
    - NO importar módulos sospechosos
    
    Limitaciones (P2-E Commit 4D-DependencyMapping):
    - Solo lectura de archivos de texto
    - Análisis estático, NO dinámico
    - NO ejecuta runtime
    - NO importa faiss/semantic_memory_bridge
    - SIEMPRE bloquea allow_real_write
    """
    
    # Targets por defecto a buscar
    DEFAULT_TARGET_NAMES = [
        "migration_progress.json",
        "semantic_memory_faiss.index",
        "semantic_memory_faiss_ids.json",
        "smart_migration_progress.json",
        "memory/semantic",
        "semantic_memory_faiss",
        "semantic_memory_index.npz",
        "semantic_memory.jsonl",
    ]
    
    # Extensiones a escanear
    DEFAULT_INCLUDE_EXTENSIONS = {
        ".py", ".md", ".json", ".yaml", ".yml", ".txt",
        ".ps1", ".bat", ".sh", ".toml", ".ini",
    }
    
    # Directorios a excluir
    DEFAULT_EXCLUDED_DIRS = {
        ".git", ".venv", "venv", "__pycache__",
        ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache",
    }
    
    # Tokens para clasificar access mode
    WRITE_TOKENS = {
        "write_text", "write_bytes", "append", "add_memory",
        "save", "persist", "dump", "dumps", "json.dump",
        "np.save", "faiss.write_index",
    }
    
    DELETE_MOVE_TOKENS = {
        "unlink", "remove", "rmdir", "delete", "move",
        "shutil.move", "shutil.rmtree",
    }
    
    IMPORT_RUNTIME_TOKENS = {
        "import faiss", "faiss.", "load_index", "read_index",
        "uvicorn", "FastAPI", "endpoint",
    }
    
    READ_ONLY_TOKENS = {
        "read_text", "read_bytes", "load", "json.load",
        "np.load", "exists", "stat", "sha256",
    }
    
    def __init__(
        self,
        repo_root: str | Path = ".",
        target_names: Optional[List[str]] = None,
        include_extensions: Optional[Set[str]] = None,
        excluded_dirs: Optional[Set[str]] = None,
    ):
        """
        Inicializar mapper.
        
        Args:
            repo_root: Raíz del repositorio a escanear
            target_names: Lista de nombres a buscar (default: DEFAULT_TARGET_NAMES)
            include_extensions: Extensiones a incluir (default: DEFAULT_INCLUDE_EXTENSIONS)
            excluded_dirs: Directorios a excluir (default: DEFAULT_EXCLUDED_DIRS)
        """
        self._repo_root = Path(repo_root).resolve()
        self._target_names = target_names or list(self.DEFAULT_TARGET_NAMES)
        self._include_extensions = include_extensions or set(self.DEFAULT_INCLUDE_EXTENSIONS)
        self._excluded_dirs = excluded_dirs or set(self.DEFAULT_EXCLUDED_DIRS)
        self._max_file_size = 2 * 1024 * 1024  # 2 MB
    
    def map_read_only(self) -> SemanticMemoryDependencyMapReport:
        """
        Mapear dependencias en modo read-only.
        
        Este método:
        1. Enumera archivos en el repositorio
        2. Escanea cada archivo buscando referencias a targets
        3. Clasifica cada hit encontrado
        4. NO ejecuta código
        5. NO importa módulos
        
        Returns:
            SemanticMemoryDependencyMapReport con el mapeo completo
        """
        map_id = f"map_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        hits: List[SemanticMemoryDependencyHit] = []
        scanned_count = 0
        skipped_count = 0
        warnings: List[str] = []
        
        # Escanear archivos
        for file_path in self._repo_root.rglob("*"):
            # Verificar si es archivo
            if not file_path.is_file():
                continue
            
            # Verificar extensión
            if file_path.suffix not in self._include_extensions:
                continue
            
            # Verificar directorios excluidos
            if any(part in self._excluded_dirs for part in file_path.parts):
                continue
            
            # Verificar tamaño
            try:
                file_size = file_path.stat().st_size
                if file_size > self._max_file_size:
                    skipped_count += 1
                    warnings.append(f"Archivo saltado por tamaño: {file_path} ({file_size} bytes)")
                    continue
            except Exception:
                skipped_count += 1
                continue
            
            # Escanear archivo
            try:
                file_hits = self._scan_text_file(file_path)
                hits.extend(file_hits)
                scanned_count += 1
            except Exception as e:
                warnings.append(f"Error escaneando {file_path}: {str(e)}")
                skipped_count += 1
        
        # Calcular estadísticas
        hits_by_target: Dict[str, int] = {}
        hits_by_role: Dict[str, int] = {}
        hits_by_access_mode: Dict[str, int] = {}
        high_risk_count = 0
        write_like_count = 0
        runtime_like_count = 0
        
        for hit in hits:
            # Contar por target
            hits_by_target[hit.target_name] = hits_by_target.get(hit.target_name, 0) + 1
            
            # Contar por role
            role_key = hit.dependency_role.value
            hits_by_role[role_key] = hits_by_role.get(role_key, 0) + 1
            
            # Contar por access mode
            access_key = hit.access_mode.value
            hits_by_access_mode[access_key] = hits_by_access_mode.get(access_key, 0) + 1
            
            # Contar riesgos
            if hit.risk == SemanticMemoryDependencyRisk.HIGH:
                high_risk_count += 1
            
            if hit.access_mode == SemanticMemoryDependencyAccessMode.WRITE_LIKELY:
                write_like_count += 1
            
            if hit.access_mode == SemanticMemoryDependencyAccessMode.IMPORT_OR_RUNTIME_LIKELY:
                runtime_like_count += 1
        
        # Determinar si requiere revisión manual
        requires_review = high_risk_count > 0 or write_like_count > 0
        
        # Bloqueadores
        blockers = [
            "Commit 4D-DependencyMapping: Solo mapeo estático, NO ejecución",
            "Commit 4D: Controlled real write aún no implementado",
        ]
        
        return SemanticMemoryDependencyMapReport(
            map_id=map_id,
            created_at_utc=created_at,
            repo_root=str(self._repo_root),
            scanned_file_count=scanned_count,
            skipped_file_count=skipped_count,
            hit_count=len(hits),
            target_names=list(self._target_names),
            hits=hits,
            hits_by_target=hits_by_target,
            hits_by_role=hits_by_role,
            hits_by_access_mode=hits_by_access_mode,
            high_risk_hit_count=high_risk_count,
            write_like_hit_count=write_like_count,
            runtime_like_hit_count=runtime_like_count,
            requires_manual_review=requires_review,
            allow_real_write=False,
            dry_run_only=True,
            warnings=warnings,
            blockers=blockers,
            metadata={
                "scan_type": "static_read_only",
                "include_extensions": list(self._include_extensions),
                "excluded_dirs": list(self._excluded_dirs),
            },
        )
    
    def _scan_text_file(self, file_path: Path) -> List[SemanticMemoryDependencyHit]:
        """
        Escanear un archivo de texto buscando referencias.
        
        Args:
            file_path: Path del archivo a escanear
            
        Returns:
            Lista de hits encontrados
        """
        hits: List[SemanticMemoryDependencyHit] = []
        
        # Leer archivo
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        
        # Clasificar rol del archivo
        file_role = self._classify_dependency_role(file_path)
        
        # Buscar referencias en cada línea
        for line_num, line in enumerate(lines, start=1):
            for target in self._target_names:
                if target in line:
                    # Detectar tipo de dependencia
                    kind = self._classify_dependency_kind(target, target)
                    
                    # Detectar modo de acceso
                    access_mode = self._classify_access_mode(line)
                    
                    # Calcular riesgo
                    risk = self._classify_risk(file_role, access_mode, kind)
                    
                    # Crear hit
                    hit = SemanticMemoryDependencyHit(
                        target_name=target,
                        matched_token=target,
                        file_path=str(file_path.relative_to(self._repo_root)),
                        line_number=line_num,
                        line_excerpt=line[:100].strip(),  # Primeros 100 chars
                        dependency_kind=kind,
                        dependency_role=file_role,
                        access_mode=access_mode,
                        risk=risk,
                        metadata={
                            "self_reference": file_path.name == "semantic_memory_extra_file_dependency_mapper.py",
                        },
                    )
                    hits.append(hit)
        
        return hits
    
    def _classify_dependency_role(self, file_path: Path) -> SemanticMemoryDependencyRole:
        """
        Clasificar el rol del archivo según su path.
        
        Args:
            file_path: Path del archivo
            
        Returns:
            SemanticMemoryDependencyRole
        """
        # Use as_posix() to normalize paths across Windows/Unix
        path_str = file_path.as_posix().lower()
        
        # Self-reference
        if "semantic_memory_extra_file_dependency_mapper.py" in path_str:
            return SemanticMemoryDependencyRole.UNKNOWN
        
        # Tests - use forward slashes to match both Windows and Unix
        if "tests/unit/" in path_str:
            return SemanticMemoryDependencyRole.TEST
        if "tests/smoke/" in path_str:
            return SemanticMemoryDependencyRole.SMOKE
        
        # Docs
        if "docs/" in path_str or file_path.suffix == ".md":
            return SemanticMemoryDependencyRole.DOCS
        
        # Scripts/Tooling
        if any(x in path_str for x in ["scripts/", "ops/", "tools/", "tmp_agent/ops/"]):
            return SemanticMemoryDependencyRole.SCRIPT_OR_TOOLING
        
        # Bridge/Adapter
        if any(x in path_str for x in ["bridge", "adapter", "semantic_memory_real_adapter"]):
            return SemanticMemoryDependencyRole.BRIDGE_OR_ADAPTER
        
        # Brain/Runtime Core (pero no el propio mapper)
        if "brain/" in path_str:
            return SemanticMemoryDependencyRole.RUNTIME_CORE
        
        return SemanticMemoryDependencyRole.UNKNOWN
    
    def _classify_dependency_kind(
        self,
        target_name: str,
        matched_token: str,
    ) -> SemanticMemoryDependencyKind:
        """
        Clasificar el tipo de dependencia.
        
        Args:
            target_name: Nombre del target
            matched_token: Token que hizo match
            
        Returns:
            SemanticMemoryDependencyKind
        """
        if "faiss" in target_name.lower():
            return SemanticMemoryDependencyKind.FAISS_ARTIFACT_REFERENCE
        
        if "migration" in target_name.lower():
            return SemanticMemoryDependencyKind.MIGRATION_PROGRESS_REFERENCE
        
        if "memory/semantic" in target_name:
            return SemanticMemoryDependencyKind.MEMORY_SEMANTIC_PATH_REFERENCE
        
        if target_name in self.DEFAULT_TARGET_NAMES:
            return SemanticMemoryDependencyKind.EXACT_FILENAME_REFERENCE
        
        return SemanticMemoryDependencyKind.UNKNOWN_REFERENCE
    
    def _classify_access_mode(self, line: str) -> SemanticMemoryDependencyAccessMode:
        """
        Clasificar el modo de acceso inferido.
        
        Args:
            line: Línea de código
            
        Returns:
            SemanticMemoryDependencyAccessMode
        """
        line_lower = line.lower()
        
        # Check read-only tokens FIRST (before import/runtime to avoid matching "faiss.index" as "faiss.")
        if any(token in line_lower for token in self.READ_ONLY_TOKENS):
            return SemanticMemoryDependencyAccessMode.READ_ONLY_LIKELY
        
        # Check write tokens
        if any(token in line_lower for token in self.WRITE_TOKENS):
            return SemanticMemoryDependencyAccessMode.WRITE_LIKELY
        
        # Check delete/move tokens
        if any(token in line_lower for token in self.DELETE_MOVE_TOKENS):
            return SemanticMemoryDependencyAccessMode.DELETE_OR_MOVE_LIKELY
        
        # Check import/runtime tokens
        if any(token in line_lower for token in self.IMPORT_RUNTIME_TOKENS):
            return SemanticMemoryDependencyAccessMode.IMPORT_OR_RUNTIME_LIKELY
        
        return SemanticMemoryDependencyAccessMode.UNKNOWN
    
    def _classify_risk(
        self,
        role: SemanticMemoryDependencyRole,
        access_mode: SemanticMemoryDependencyAccessMode,
        kind: SemanticMemoryDependencyKind,
    ) -> SemanticMemoryDependencyRisk:
        """
        Calcular el nivel de riesgo.
        
        Args:
            role: Rol del archivo
            access_mode: Modo de acceso
            kind: Tipo de dependencia
            
        Returns:
            SemanticMemoryDependencyRisk
        """
        # HIGH risk para write o delete/move
        if access_mode in [
            SemanticMemoryDependencyAccessMode.WRITE_LIKELY,
            SemanticMemoryDependencyAccessMode.DELETE_OR_MOVE_LIKELY,
        ]:
            return SemanticMemoryDependencyRisk.HIGH
        
        # HIGH risk para FAISS en runtime core (any access mode)
        if kind == SemanticMemoryDependencyKind.FAISS_ARTIFACT_REFERENCE and role == SemanticMemoryDependencyRole.RUNTIME_CORE:
            return SemanticMemoryDependencyRisk.HIGH
        
        # MEDIUM risk para bridge/adapter
        if role == SemanticMemoryDependencyRole.BRIDGE_OR_ADAPTER:
            return SemanticMemoryDependencyRisk.MEDIUM
        
        # MEDIUM risk para FAISS en tooling
        if kind == SemanticMemoryDependencyKind.FAISS_ARTIFACT_REFERENCE and role == SemanticMemoryDependencyRole.SCRIPT_OR_TOOLING:
            return SemanticMemoryDependencyRisk.MEDIUM
        
        # LOW risk para docs/test/smoke
        if role in [SemanticMemoryDependencyRole.DOCS, SemanticMemoryDependencyRole.TEST, SemanticMemoryDependencyRole.SMOKE]:
            return SemanticMemoryDependencyRisk.LOW
        
        return SemanticMemoryDependencyRisk.UNKNOWN
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-DependencyMapping",
            "contract_type": "ExtraFileDependencyMapping",
            "dry_run_only": True,
            "allow_real_write": False,
            "capabilities": [
                "map_read_only",
                "scan_text_file",
            ],
            "limitations": [
                "NO code execution",
                "NO module imports",
                "NO write operations",
                "NO subprocess",
                "NO FAISS import",
                "Static analysis only",
            ],
            "target_names": self._target_names,
            "next_step": "Commit 4D: Controlled real write",
        }
    
    def block_runtime_use(
        self,
        reason: str = "Uso de runtime bloqueado por mapper 4D-DependencyMapping",
    ) -> SemanticMemoryDependencyMapReport:
        """
        Bloquear explícitamente uso de runtime.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryDependencyMapReport con uso bloqueado
        """
        map_id = f"blocked_{uuid.uuid4().hex[:16]}"
        
        return SemanticMemoryDependencyMapReport(
            map_id=map_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            repo_root=str(self._repo_root),
            scanned_file_count=0,
            skipped_file_count=0,
            hit_count=0,
            target_names=list(self._target_names),
            hits=[],
            hits_by_target={},
            hits_by_role={},
            hits_by_access_mode={},
            high_risk_hit_count=0,
            write_like_hit_count=0,
            runtime_like_hit_count=0,
            requires_manual_review=True,
            allow_real_write=False,
            dry_run_only=True,
            warnings=[f"BLOCKED: {reason}"],
            blockers=[
                "BLOCKED: Uso de runtime bloqueado",
                "BLOCKED: Usar map_read_only() solo",
            ],
            metadata={"block_reason": reason},
        )
