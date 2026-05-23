"""
P2-E Commit 4D-CleanClassification: Semantic Memory Extra File Classifier

Clasificación read-only de archivos extra detectados en memory/semantic.
Este módulo clasifica y documenta los archivos sin modificarlos.

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
- can_delete_without_review=False SIEMPRE
- can_move_without_review=False SIEMPRE
- requires_manual_review=True para todo archivo extra
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import uuid


class SemanticMemoryExtraFileClass(str, Enum):
    """Clasificación de archivos."""
    REQUIRED_STORE = "REQUIRED_STORE"
    REQUIRED_INDEX = "REQUIRED_INDEX"
    OPTIONAL_METADATA = "OPTIONAL_METADATA"
    FAISS_INDEX_ARTIFACT = "FAISS_INDEX_ARTIFACT"
    FAISS_ID_MAP_ARTIFACT = "FAISS_ID_MAP_ARTIFACT"
    MIGRATION_PROGRESS_METADATA = "MIGRATION_PROGRESS_METADATA"
    UNKNOWN_EXTRA = "UNKNOWN_EXTRA"
    MISSING = "MISSING"


class SemanticMemoryExtraFileRisk(str, Enum):
    """Niveles de riesgo."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass
class SemanticMemoryExtraFileClassification:
    """
    Clasificación de un archivo individual.
    """
    relative_path: str
    exists: bool
    size_bytes: int
    sha256: Optional[str] = None
    file_class: SemanticMemoryExtraFileClass = SemanticMemoryExtraFileClass.UNKNOWN_EXTRA
    risk: SemanticMemoryExtraFileRisk = SemanticMemoryExtraFileRisk.UNKNOWN
    can_delete_without_review: bool = False
    can_move_without_review: bool = False
    requires_manual_review: bool = True
    json_readable: bool = False
    json_top_level_type: Optional[str] = None
    summary: str = ""
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "relative_path": self.relative_path,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "file_class": self.file_class.value,
            "risk": self.risk.value,
            "can_delete_without_review": self.can_delete_without_review,
            "can_move_without_review": self.can_move_without_review,
            "requires_manual_review": self.requires_manual_review,
            "json_readable": self.json_readable,
            "json_top_level_type": self.json_top_level_type,
            "summary": self.summary,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class SemanticMemoryExtraFileClassificationReport:
    """
    Reporte de clasificación de archivos extra.
    
    SIEMPRE bloqueado, nunca habilita escritura real.
    """
    classification_id: str
    created_at_utc: str
    source_root: str
    file_count: int
    extra_file_count: int
    required_file_count: int
    classifications: List[SemanticMemoryExtraFileClassification] = field(default_factory=list)
    dirty_state_detected: bool = False
    requires_manual_review: bool = True
    allow_real_write: bool = False
    dry_run_only: bool = True
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "classification_id": self.classification_id,
            "created_at_utc": self.created_at_utc,
            "source_root": self.source_root,
            "file_count": self.file_count,
            "extra_file_count": self.extra_file_count,
            "required_file_count": self.required_file_count,
            "classifications": [c.to_dict() for c in self.classifications],
            "dirty_state_detected": self.dirty_state_detected,
            "requires_manual_review": self.requires_manual_review,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryExtraFileClassifier:
    """
    Clasificador de archivos extra en memory/semantic.
    
    Responsabilidades:
    - Clasificar archivos por tipo y riesgo
    - Documentar archivos extra sin modificarlos
    - Asignar nivel de riesgo a cada archivo
    - Requerir revisión manual para todo archivo extra
    
    Limitaciones (P2-E Commit 4D-CleanClassification):
    - Solo lectura, nunca escritura
    - NO borra archivos
    - NO mueve archivos
    - NO copia archivos
    - SIEMPRE requiere revisión manual para extras
    - SIEMPRE bloquea allow_real_write
    """
    
    # Definición de archivos esperados y sus clases
    FILE_CLASSIFICATIONS = {
        "semantic_memory.jsonl": (SemanticMemoryExtraFileClass.REQUIRED_STORE, SemanticMemoryExtraFileRisk.LOW),
        "semantic_memory_index.npz": (SemanticMemoryExtraFileClass.REQUIRED_INDEX, SemanticMemoryExtraFileRisk.LOW),
        "semantic_memory_meta.json": (SemanticMemoryExtraFileClass.OPTIONAL_METADATA, SemanticMemoryExtraFileRisk.LOW),
        "semantic_memory_faiss.index": (SemanticMemoryExtraFileClass.FAISS_INDEX_ARTIFACT, SemanticMemoryExtraFileRisk.HIGH),
        "semantic_memory_faiss_ids.json": (SemanticMemoryExtraFileClass.FAISS_ID_MAP_ARTIFACT, SemanticMemoryExtraFileRisk.HIGH),
        "migration_progress.json": (SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA, SemanticMemoryExtraFileRisk.MEDIUM),
        "smart_migration_progress.json": (SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA, SemanticMemoryExtraFileRisk.MEDIUM),
    }
    
    def __init__(
        self,
        source_root: str | Path = "memory/semantic",
    ):
        """
        Inicializar clasificador.
        
        Args:
            source_root: Directorio a clasificar (default: memory/semantic)
        """
        self._source_root = Path(source_root)
    
    def classify_read_only(self) -> SemanticMemoryExtraFileClassificationReport:
        """
        Clasificar archivos en modo read-only.
        
        Este método:
        1. Lista todos los archivos en source_root
        2. Clasifica cada archivo por nombre y extensión
        3. Calcula fingerprints SHA-256
        4. Detecta si es JSON legible
        5. Asigna nivel de riesgo
        6. NO modifica archivos
        
        Returns:
            SemanticMemoryExtraFileClassificationReport con clasificaciones
        """
        classification_id = f"classify_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        classifications: List[SemanticMemoryExtraFileClassification] = []
        extra_count = 0
        required_count = 0
        warnings: List[str] = []
        
        # Clasificar archivos conocidos
        for filename, (file_class, risk) in self.FILE_CLASSIFICATIONS.items():
            file_path = self._source_root / filename
            classification = self._classify_path(file_path)
            classifications.append(classification)
            
            if classification.exists:
                if file_class in [
                    SemanticMemoryExtraFileClass.REQUIRED_STORE,
                    SemanticMemoryExtraFileClass.REQUIRED_INDEX,
                ]:
                    required_count += 1
                else:
                    extra_count += 1
        
        # Buscar archivos desconocidos
        if self._source_root.is_dir():
            for file_path in self._source_root.iterdir():
                if file_path.is_file():
                    filename = file_path.name
                    if filename not in self.FILE_CLASSIFICATIONS:
                        classification = self._classify_path(file_path)
                        classifications.append(classification)
                        extra_count += 1
                        warnings.append(f"Archivo desconocido detectado: {filename}")
        
        # Determinar si hay estado dirty
        dirty_detected = extra_count > 0
        
        # Bloqueadores siempre presentes
        blockers = [
            "Commit 4D-CleanClassification: Solo clasificación, NO modificación",
            "Commit 4D: Controlled real write aún no implementado",
        ]
        
        return SemanticMemoryExtraFileClassificationReport(
            classification_id=classification_id,
            created_at_utc=created_at,
            source_root=str(self._source_root),
            file_count=len(classifications),
            extra_file_count=extra_count,
            required_file_count=required_count,
            classifications=classifications,
            dirty_state_detected=dirty_detected,
            requires_manual_review=True,
            allow_real_write=False,
            dry_run_only=True,
            warnings=warnings,
            blockers=blockers,
            metadata={
                "classification_type": "read_only",
                "known_files_count": len(self.FILE_CLASSIFICATIONS),
            },
        )
    
    def _classify_path(self, file_path: Path) -> SemanticMemoryExtraFileClassification:
        """
        Clasificar un archivo individual.
        
        Args:
            file_path: Path del archivo a clasificar
            
        Returns:
            SemanticMemoryExtraFileClassification con información del archivo
        """
        relative_path = file_path.name
        
        # Obtener clasificación base por nombre
        if relative_path in self.FILE_CLASSIFICATIONS:
            file_class, risk = self.FILE_CLASSIFICATIONS[relative_path]
        else:
            file_class = SemanticMemoryExtraFileClass.UNKNOWN_EXTRA
            risk = SemanticMemoryExtraFileRisk.UNKNOWN
        
        # Verificar existencia
        if not file_path.exists():
            return SemanticMemoryExtraFileClassification(
                relative_path=relative_path,
                exists=False,
                size_bytes=0,
                sha256=None,
                file_class=SemanticMemoryExtraFileClass.MISSING,
                risk=SemanticMemoryExtraFileRisk.UNKNOWN,
                summary=f"Archivo no encontrado",
                requires_manual_review=True,
            )
        
        try:
            stat = file_path.stat()
            size_bytes = stat.st_size
            
            # Calcular SHA-256
            if size_bytes > 0:
                content = file_path.read_bytes()
                sha256 = hashlib.sha256(content).hexdigest()
            else:
                sha256 = None
            
            # Intentar leer JSON
            json_readable = False
            json_top_level_type = None
            json_warnings = []
            
            if relative_path.endswith('.json') and size_bytes > 0:
                try:
                    json_content = file_path.read_text(encoding="utf-8", errors="ignore")
                    data = json.loads(json_content)
                    json_readable = True
                    json_top_level_type = type(data).__name__
                except Exception as e:
                    json_warnings.append(f"No es JSON legible: {str(e)}")
            
            # Generar summary
            if file_class == SemanticMemoryExtraFileClass.FAISS_INDEX_ARTIFACT:
                summary = f"Índice FAISS detectado. Riesgo ALTO. Requiere revisión manual."
            elif file_class == SemanticMemoryExtraFileClass.FAISS_ID_MAP_ARTIFACT:
                summary = f"Mapeo de IDs FAISS detectado. Riesgo ALTO. Requiere revisión manual."
            elif file_class == SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA:
                summary = f"Metadata de migración detectado. Riesgo MEDIO. Requiere revisión manual."
            elif file_class == SemanticMemoryExtraFileClass.UNKNOWN_EXTRA:
                summary = f"Archivo desconocido. Riesgo DESCONOCIDO. Requiere revisión manual."
            elif file_class == SemanticMemoryExtraFileClass.REQUIRED_STORE:
                summary = f"Almacenamiento principal requerido. Riesgo BAJO."
            elif file_class == SemanticMemoryExtraFileClass.REQUIRED_INDEX:
                summary = f"Índice principal requerido. Riesgo BAJO."
            elif file_class == SemanticMemoryExtraFileClass.OPTIONAL_METADATA:
                summary = f"Metadata opcional. Riesgo BAJO."
            else:
                summary = f"Archivo {relative_path}. Riesgo {risk.value}."
            
            return SemanticMemoryExtraFileClassification(
                relative_path=relative_path,
                exists=True,
                size_bytes=size_bytes,
                sha256=sha256,
                file_class=file_class,
                risk=risk,
                can_delete_without_review=False,
                can_move_without_review=False,
                requires_manual_review=True,
                json_readable=json_readable,
                json_top_level_type=json_top_level_type,
                summary=summary,
                warnings=json_warnings,
                metadata={
                    "file_type": file_path.suffix,
                },
            )
            
        except Exception as e:
            return SemanticMemoryExtraFileClassification(
                relative_path=relative_path,
                exists=True,
                size_bytes=0,
                sha256=None,
                file_class=file_class,
                risk=risk,
                summary=f"Error al clasificar: {str(e)}",
                requires_manual_review=True,
                warnings=[f"Error: {str(e)}"],
            )
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-CleanClassification",
            "contract_type": "ExtraFileClassification",
            "dry_run_only": True,
            "allow_real_write": False,
            "capabilities": [
                "classify_read_only",
                "classify_path",
            ],
            "limitations": [
                "NO file delete",
                "NO file move",
                "NO file copy",
                "NO write operations",
                "NO FAISS import",
                "Requires manual review for all extras",
            ],
            "known_file_types": list(self.FILE_CLASSIFICATIONS.keys()),
            "next_step": "Commit 4D: Controlled real write",
        }
    
    def block_cleanup(
        self,
        reason: str = "Limpieza bloqueada por classifier 4D-CleanClassification",
    ) -> SemanticMemoryExtraFileClassificationReport:
        """
        Bloquear explícitamente limpieza de archivos.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryExtraFileClassificationReport con limpieza bloqueada
        """
        classification_id = f"blocked_{uuid.uuid4().hex[:16]}"
        
        return SemanticMemoryExtraFileClassificationReport(
            classification_id=classification_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            source_root=str(self._source_root),
            file_count=0,
            extra_file_count=0,
            required_file_count=0,
            dirty_state_detected=False,
            requires_manual_review=True,
            allow_real_write=False,
            dry_run_only=True,
            warnings=[f"BLOCKED: {reason}"],
            blockers=[
                "BLOCKED: Limpieza de archivos bloqueada",
                "BLOCKED: Usar classify_read_only() solo",
            ],
            metadata={"block_reason": reason},
        )
