"""
P2-E Commit 4D-Preflight: Real Memory/FAISS State Audit

Auditoría read-only del estado real de memory/semantic antes de cualquier
consideración de escritura real.

Este módulo:
- Lista archivos en memory/semantic
- Calcula fingerprints SHA-256
- Detecta estado dirty (faltantes, extras, vacíos)
- NO escribe archivos
- NO crea backups reales
- NO restaura archivos

REGLAS DURAS:
- Solo read_bytes() para auditoría
- NO write_text/write_bytes
- NO open(..., "w") ni open(..., "a")
- NO shutil.copy/copy2/copytree/move/rmtree
- NO unlink/remove/rmdir
- NO importar faiss
- NO importar requests/httpx
- NO importar semantic_memory_bridge
- dry_run_only=True SIEMPRE
- allow_real_write=False SIEMPRE
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import uuid


class SemanticMemoryRealStateAuditStatus(str, Enum):
    """Estados del audit."""
    NOT_STARTED = "NOT_STARTED"
    AUDIT_COMPLETED = "AUDIT_COMPLETED"
    AUDIT_COMPLETED_WITH_WARNINGS = "AUDIT_COMPLETED_WITH_WARNINGS"
    BLOCKED_REAL_WRITE = "BLOCKED_REAL_WRITE"
    FAILED = "FAILED"


@dataclass
class SemanticMemoryFileAuditRecord:
    """
    Registro de auditoría de un archivo.
    """
    relative_path: str
    exists: bool
    size_bytes: int
    sha256: Optional[str] = None
    modified_at_utc: Optional[str] = None
    role: str = "unknown"
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "relative_path": self.relative_path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "modified_at_utc": self.modified_at_utc,
            "role": self.role,
            "warnings": self.warnings,
        }


@dataclass
class SemanticMemoryRealStateAuditReport:
    """
    Reporte de auditoría del estado real.
    
    SIEMPRE bloqueado, nunca habilita escritura real.
    """
    audit_id: str
    created_at_utc: str
    status: SemanticMemoryRealStateAuditStatus
    source_root: str
    file_count: int
    total_bytes: int
    files: List[SemanticMemoryFileAuditRecord] = field(default_factory=list)
    expected_files_present: bool = False
    dirty_state_detected: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "audit_id": self.audit_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "source_root": self.source_root,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "files": [f.to_dict() for f in self.files],
            "expected_files_present": self.expected_files_present,
            "dirty_state_detected": self.dirty_state_detected,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryRealStateAudit:
    """
    Auditoría read-only del estado de memory/semantic.
    
    Responsabilidades:
    - Auditar archivos en memory/semantic (solo lectura)
    - Detectar estado dirty (faltantes, extras, vacíos)
    - Calcular fingerprints para integridad
    - Bloquear explícitamente escritura real
    
    Limitaciones (P2-E Commit 4D-Preflight):
    - Solo lectura, nunca escritura
    - NO crea backups reales
    - NO restaura archivos
    - NO importa FAISS
    - SIEMPRE bloquea allow_real_write
    
    Archivos esperados:
    - semantic_memory.jsonl (jsonl_store)
    - semantic_memory_index.npz (vector_index_npz)
    - semantic_memory_meta.json (metadata_optional)
    """
    
    # Archivos esperados y sus roles
    EXPECTED_FILES = {
        "semantic_memory.jsonl": "jsonl_store",
        "semantic_memory_index.npz": "vector_index_npz",
        "semantic_memory_meta.json": "metadata_optional",
    }
    
    def __init__(
        self,
        source_root: str | Path = "memory/semantic",
    ):
        """
        Inicializar auditoría.
        
        Args:
            source_root: Directorio a auditar (default: memory/semantic)
        """
        self._source_root = Path(source_root)
    
    def audit_read_only(self) -> SemanticMemoryRealStateAuditReport:
        """
        Auditar estado real en modo read-only.
        
        Este método:
        1. Verifica que source_root existe
        2. Lista todos los archivos
        3. Calcula fingerprints SHA-256
        4. Detecta estado dirty
        5. NO escribe archivos
        
        Returns:
            SemanticMemoryRealStateAuditReport con estado auditado
        """
        audit_id = f"audit_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Verificar que source_root existe
        if not self._source_root.exists():
            return SemanticMemoryRealStateAuditReport(
                audit_id=audit_id,
                created_at_utc=created_at,
                status=SemanticMemoryRealStateAuditStatus.FAILED,
                source_root=str(self._source_root),
                file_count=0,
                total_bytes=0,
                validation_errors=[f"source_root no existe: {self._source_root}"],
                allow_real_write=False,
                dry_run_only=True,
            )
        
        files_audit: List[SemanticMemoryFileAuditRecord] = []
        total_bytes = 0
        warnings: List[str] = []
        
        # Auditar archivos esperados
        for expected_file, role in self.EXPECTED_FILES.items():
            file_path = self._source_root / expected_file
            file_audit = self._audit_file(expected_file, file_path, role)
            files_audit.append(file_audit)
            total_bytes += file_audit.size_bytes
            
            if not file_audit.exists:
                # Solo warning si no es metadata_optional
                if role != "metadata_optional":
                    warnings.append(f"Archivo esperado faltante: {expected_file}")
            elif file_audit.size_bytes == 0:
                warnings.append(f"Archivo vacío: {expected_file}")
        
        # Buscar archivos extra (no esperados)
        if self._source_root.is_dir():
            for file_path in self._source_root.iterdir():
                if file_path.is_file():
                    relative = file_path.name
                    if relative not in self.EXPECTED_FILES:
                        file_audit = self._audit_file(relative, file_path, "extra_file")
                        files_audit.append(file_audit)
                        total_bytes += file_audit.size_bytes
                        warnings.append(f"Archivo extra detectado: {relative}")
        
        # Determinar estado dirty
        expected_present = all(
            f.exists for f in files_audit 
            if f.role in ["jsonl_store", "vector_index_npz"]
        )
        
        dirty_detected = (
            not expected_present or
            any(f.role == "extra_file" for f in files_audit) or
            any(f.size_bytes == 0 for f in files_audit if f.exists)
        )
        
        # Determinar status
        if warnings:
            status = SemanticMemoryRealStateAuditStatus.AUDIT_COMPLETED_WITH_WARNINGS
        else:
            status = SemanticMemoryRealStateAuditStatus.AUDIT_COMPLETED
        
        # Bloqueadores siempre presentes
        blockers = [
            "Commit 4D-Preflight: Solo auditoría, NO escritura real",
            "Commit 4D: Controlled real write aún no implementado",
        ]
        
        return SemanticMemoryRealStateAuditReport(
            audit_id=audit_id,
            created_at_utc=created_at,
            status=status,
            source_root=str(self._source_root),
            file_count=len(files_audit),
            total_bytes=total_bytes,
            files=files_audit,
            expected_files_present=expected_present,
            dirty_state_detected=dirty_detected,
            allow_real_write=False,
            dry_run_only=True,
            validation_errors=[],
            warnings=warnings,
            blockers=blockers,
            metadata={
                "audit_type": "read_only",
                "expected_files_count": len(self.EXPECTED_FILES),
                "extra_files_count": sum(1 for f in files_audit if f.role == "extra_file"),
            },
        )
    
    def _audit_file(
        self,
        relative_path: str,
        file_path: Path,
        role: str,
    ) -> SemanticMemoryFileAuditRecord:
        """
        Auditar un archivo individual.
        
        Args:
            relative_path: Ruta relativa al source_root
            file_path: Path completo del archivo
            role: Rol del archivo (jsonl_store, vector_index_npz, etc.)
            
        Returns:
            SemanticMemoryFileAuditRecord con información del archivo
        """
        file_warnings: List[str] = []
        
        if not file_path.exists():
            return SemanticMemoryFileAuditRecord(
                relative_path=relative_path,
                exists=False,
                size_bytes=0,
                sha256=None,
                modified_at_utc=None,
                role=role,
                warnings=file_warnings,
            )
        
        try:
            stat = file_path.stat()
            size_bytes = stat.st_size
            modified_at = datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat()
            
            # Calcular SHA-256 (solo lectura)
            if size_bytes > 0:
                content = file_path.read_bytes()
                sha256 = hashlib.sha256(content).hexdigest()
            else:
                sha256 = None
                file_warnings.append("Archivo vacío")
            
            return SemanticMemoryFileAuditRecord(
                relative_path=relative_path,
                exists=True,
                size_bytes=size_bytes,
                sha256=sha256,
                modified_at_utc=modified_at,
                role=role,
                warnings=file_warnings,
            )
            
        except Exception as e:
            file_warnings.append(f"Error al auditar: {str(e)}")
            return SemanticMemoryFileAuditRecord(
                relative_path=relative_path,
                exists=True,
                size_bytes=0,
                sha256=None,
                modified_at_utc=None,
                role=role,
                warnings=file_warnings,
            )
    
    def validate_expected_files(
        self,
        report: SemanticMemoryRealStateAuditReport,
    ) -> Tuple[List[str], List[str]]:
        """
        Validar que los archivos esperados estén presentes.
        
        Args:
            report: Reporte de auditoría
            
        Returns:
            Tuple[List[str], List[str]] - (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        expected_files = ["semantic_memory.jsonl", "semantic_memory_index.npz"]
        
        for expected in expected_files:
            found = any(f.relative_path == expected and f.exists for f in report.files)
            if not found:
                errors.append(f"Archivo requerido faltante: {expected}")
        
        optional = ["semantic_memory_meta.json"]
        for opt in optional:
            found = any(f.relative_path == opt and f.exists for f in report.files)
            if not found:
                warnings.append(f"Archivo opcional faltante: {opt}")
        
        return errors, warnings
    
    def block_real_write(
        self,
        reason: str = "Escritura real bloqueada por audit 4D-Preflight",
    ) -> SemanticMemoryRealStateAuditReport:
        """
        Bloquear explícitamente escritura real.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRealStateAuditReport con status BLOCKED_REAL_WRITE
        """
        audit_id = f"blocked_{uuid.uuid4().hex[:16]}"
        
        return SemanticMemoryRealStateAuditReport(
            audit_id=audit_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRealStateAuditStatus.BLOCKED_REAL_WRITE,
            source_root=str(self._source_root),
            file_count=0,
            total_bytes=0,
            validation_errors=[],
            warnings=[f"BLOCKED: {reason}"],
            blockers=[
                "BLOCKED: Escritura real bloqueada",
                "BLOCKED: Usar audit_read_only() solo",
            ],
            allow_real_write=False,
            dry_run_only=True,
            metadata={"block_reason": reason},
        )
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-Preflight",
            "contract_type": "RealStateAudit",
            "dry_run_only": True,
            "allow_real_write": False,
            "capabilities": [
                "audit_read_only",
                "validate_expected_files",
                "block_real_write",
            ],
            "limitations": [
                "NO real write",
                "NO backup real",
                "NO restore real",
                "NO FAISS",
                "NO semantic_memory_bridge",
            ],
            "expected_files": list(self.EXPECTED_FILES.keys()),
            "next_step": "Commit 4D: Controlled real write",
        }
