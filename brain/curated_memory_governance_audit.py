"""
P2-E Commit 3B: Curated Memory Governance Audit Trail

Capa de audit trail local para governance de promoción curada.
Este módulo extiende el servicio de governance con persistencia de audit,
pero SIN habilitar escritura real en memoria semántica.

RUTA DE AUDIT:
tmp_agent/state/governance/curated_memory_audit.ndjson

Características:
- Persistencia local en formato NDJSON
- Hash de payload para integridad
- Validación de entradas de audit
- Bloqueo de escritura real (allow_real_write=False)
- Modo dry-run only (dry_run_only=True)

Limitaciones:
- NO escribe en memory/semantic
- NO importa FAISS
- NO importa requests/httpx
- NO llama endpoints
- NO implementa promote_real
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import uuid


class AuditEntryType(str, Enum):
    """Tipos de entrada en el audit trail."""
    REQUEST = "REQUEST"
    DECISION = "DECISION"
    ROLLBACK = "ROLLBACK"
    SYSTEM = "SYSTEM"


class AuditEntryStatus(str, Enum):
    """Estados de una entrada de audit."""
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"
    INVALID = "INVALID"


@dataclass
class GovernanceAuditEntry:
    """
    Entrada de audit trail para governance de promoción curada.
    
    Esta entrada documenta cada paso del proceso de governance,
    incluyendo solicitudes, decisiones, y estado del sistema.
    """
    # Identificación
    entry_id: str
    entry_type: AuditEntryType
    
    # Referencias
    request_id: Optional[str] = None
    decision_id: Optional[str] = None
    
    # Estado
    status: AuditEntryStatus = AuditEntryStatus.PENDING
    actor: str = "system"
    
    # Timestamp UTC ISO 8601
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Hashes para integridad
    evidence_hash: str = ""
    payload_hash: str = ""
    
    # Control de seguridad - SIEMPRE True en este commit
    dry_run_only: bool = True
    
    # Control de escritura - SIEMPRE False en este commit
    allow_real_write: bool = False
    
    # Metadata adicional
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "entry_id": self.entry_id,
            "entry_type": self.entry_type.value,
            "request_id": self.request_id,
            "decision_id": self.decision_id,
            "status": self.status.value,
            "actor": self.actor,
            "created_at_utc": self.created_at_utc,
            "evidence_hash": self.evidence_hash,
            "payload_hash": self.payload_hash,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GovernanceAuditEntry':
        """Crear instancia desde diccionario."""
        return cls(
            entry_id=data["entry_id"],
            entry_type=AuditEntryType(data["entry_type"]),
            request_id=data.get("request_id"),
            decision_id=data.get("decision_id"),
            status=AuditEntryStatus(data["status"]),
            actor=data.get("actor", "system"),
            created_at_utc=data["created_at_utc"],
            evidence_hash=data.get("evidence_hash", ""),
            payload_hash=data.get("payload_hash", ""),
            dry_run_only=data.get("dry_run_only", True),
            allow_real_write=data.get("allow_real_write", False),
            metadata=data.get("metadata", {}),
        )


class CuratedMemoryGovernanceAuditTrail:
    """
    Servicio de audit trail para governance de promoción curada.
    
    Responsabilidades:
    - Persistir solicitudes de approval
    - Persistir decisiones de approval/rechazo
    - Validar integridad de entradas
    - Proporcionar historial de audit
    
    Ruta de Audit:
    tmp_agent/state/governance/curated_memory_audit.ndjson
    
    Limitaciones:
    - Solo escribe en path seguro (fuera de memory/semantic)
    - NO implementa promoción real
    - NO importa FAISS ni SemanticMemory
    - NO llama endpoints HTTP
    """
    
    DEFAULT_AUDIT_PATH = "tmp_agent/state/governance/curated_memory_audit.ndjson"
    
    def __init__(self, audit_path: Optional[str] = None):
        """
        Inicializar servicio de audit trail.
        
        Args:
            audit_path: Ruta al archivo de audit. Si es None, usa default.
        """
        self.audit_path = Path(audit_path) if audit_path else Path(self.DEFAULT_AUDIT_PATH)
        self._entries: List[GovernanceAuditEntry] = []
        self._load_existing()
    
    def _load_existing(self) -> None:
        """Cargar entradas existentes del archivo de audit."""
        if self.audit_path.exists():
            try:
                with open(self.audit_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            entry = GovernanceAuditEntry.from_dict(data)
                            self._entries.append(entry)
            except (json.JSONDecodeError, KeyError) as e:
                # Si hay errores de parsing, ignorar esa línea
                pass
    
    def _ensure_directory(self) -> None:
        """Asegurar que el directorio de audit existe."""
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _validate_audit_path(self) -> bool:
        """
        Validar que la ruta de audit es segura.
        
        Returns:
            True si la ruta está fuera de memory/semantic
        """
        # Verificar que no está dentro de memory/semantic
        path_str = str(self.audit_path.resolve()).lower()
        if "memory/semantic" in path_str or "memory\\semantic" in path_str:
            return False
        return True
    
    def compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """
        Calcular hash SHA-256 de un payload.
        
        Args:
            payload: Diccionario con datos del payload
            
        Returns:
            Hash hexadecimal del payload
        """
        # Serializar de manera determinista
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    
    def append_request(
        self,
        request_id: str,
        actor: str,
        evidence_hash: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GovernanceAuditEntry:
        """
        Agregar una solicitud al audit trail.
        
        Args:
            request_id: ID de la solicitud
            actor: Quien solicita
            evidence_hash: Hash de evidencia
            payload: Datos del payload (opcional)
            metadata: Metadata adicional (opcional)
            
        Returns:
            GovernanceAuditEntry creada
            
        Raises:
            ValueError: Si la ruta de audit no es segura
        """
        if not self._validate_audit_path():
            raise ValueError(f"Audit path {self.audit_path} no es segura. NO debe estar en memory/semantic")
        
        entry_id = f"audit_req_{uuid.uuid4().hex[:16]}"
        
        # Calcular payload hash si hay payload
        payload_hash = self.compute_payload_hash(payload) if payload else ""
        
        entry = GovernanceAuditEntry(
            entry_id=entry_id,
            entry_type=AuditEntryType.REQUEST,
            request_id=request_id,
            status=AuditEntryStatus.PENDING,
            actor=actor,
            evidence_hash=evidence_hash,
            payload_hash=payload_hash,
            dry_run_only=True,  # SIEMPRE True
            allow_real_write=False,  # SIEMPRE False
            metadata=metadata or {},
        )
        
        # Agregar a memoria y persistir
        self._entries.append(entry)
        self._persist_entry(entry)
        
        return entry
    
    def append_decision(
        self,
        request_id: str,
        decision_id: str,
        actor: str,
        evidence_hash: str,
        approved: bool,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GovernanceAuditEntry:
        """
        Agregar una decisión al audit trail.
        
        Args:
            request_id: ID de la solicitud relacionada
            decision_id: ID de la decisión
            actor: Quien decide
            evidence_hash: Hash de evidencia
            approved: True si fue aprobada, False si rechazada
            payload: Datos del payload (opcional)
            metadata: Metadata adicional (opcional)
            
        Returns:
            GovernanceAuditEntry creada
            
        Raises:
            ValueError: Si la ruta de audit no es segura
        """
        if not self._validate_audit_path():
            raise ValueError(f"Audit path {self.audit_path} no es segura. NO debe estar en memory/semantic")
        
        entry_id = f"audit_dec_{uuid.uuid4().hex[:16]}"
        
        # Calcular payload hash si hay payload
        payload_hash = self.compute_payload_hash(payload) if payload else ""
        
        # Estado basado en aprobación
        status = AuditEntryStatus.VALIDATED if approved else AuditEntryStatus.REJECTED
        
        entry = GovernanceAuditEntry(
            entry_id=entry_id,
            entry_type=AuditEntryType.DECISION,
            request_id=request_id,
            decision_id=decision_id,
            status=status,
            actor=actor,
            evidence_hash=evidence_hash,
            payload_hash=payload_hash,
            dry_run_only=True,  # SIEMPRE True
            allow_real_write=False,  # SIEMPRE False
            metadata=metadata or {},
        )
        
        # Agregar a memoria y persistir
        self._entries.append(entry)
        self._persist_entry(entry)
        
        return entry
    
    def _persist_entry(self, entry: GovernanceAuditEntry) -> None:
        """Persistir una entrada en el archivo NDJSON."""
        self._ensure_directory()
        
        with open(self.audit_path, 'a', encoding='utf-8') as f:
            json.dump(entry.to_dict(), f, ensure_ascii=True)
            f.write('\n')
    
    def list_entries(
        self,
        entry_type: Optional[AuditEntryType] = None,
        request_id: Optional[str] = None,
        status: Optional[AuditEntryStatus] = None,
    ) -> List[GovernanceAuditEntry]:
        """
        Listar entradas del audit trail con filtros opcionales.
        
        Args:
            entry_type: Filtrar por tipo de entrada
            request_id: Filtrar por ID de solicitud
            status: Filtrar por estado
            
        Returns:
            Lista de entradas filtradas
        """
        results = self._entries
        
        if entry_type:
            results = [e for e in results if e.entry_type == entry_type]
        
        if request_id:
            results = [e for e in results if e.request_id == request_id]
        
        if status:
            results = [e for e in results if e.status == status]
        
        return results
    
    def validate_entry(self, entry: GovernanceAuditEntry) -> bool:
        """
        Validar que una entrada de audit está bien formada.
        
        Reglas de validación:
        1. Debe tener entry_id no vacío
        2. Debe tener evidence_hash no vacío
        3. NO debe tener allow_real_write=True (bloqueado en este commit)
        4. Debe tener dry_run_only=True
        
        Args:
            entry: Entrada a validar
            
        Returns:
            True si la entrada es válida
        """
        # Verificar entry_id
        if not entry.entry_id or len(entry.entry_id) == 0:
            return False
        
        # Verificar evidence_hash
        if not entry.evidence_hash or len(entry.evidence_hash) == 0:
            return False
        
        # Bloquear allow_real_write=True
        if entry.allow_real_write:
            return False
        
        # Verificar dry_run_only=True
        if not entry.dry_run_only:
            return False
        
        return True
    
    def get_entry_by_id(self, entry_id: str) -> Optional[GovernanceAuditEntry]:
        """Obtener entrada por ID."""
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None
    
    def get_audit_stats(self) -> Dict[str, int]:
        """
        Obtener estadísticas del audit trail.
        
        Returns:
            Diccionario con conteos por tipo y estado
        """
        stats = {
            "total_entries": len(self._entries),
            "requests": len([e for e in self._entries if e.entry_type == AuditEntryType.REQUEST]),
            "decisions": len([e for e in self._entries if e.entry_type == AuditEntryType.DECISION]),
            "pending": len([e for e in self._entries if e.status == AuditEntryStatus.PENDING]),
            "validated": len([e for e in self._entries if e.status == AuditEntryStatus.VALIDATED]),
            "rejected": len([e for e in self._entries if e.status == AuditEntryStatus.REJECTED]),
        }
        return stats


def create_audit_trail(audit_path: Optional[str] = None) -> CuratedMemoryGovernanceAuditTrail:
    """
    Factory para crear instancia del audit trail.
    
    Args:
        audit_path: Ruta personalizada para el archivo de audit.
                     Si es None, usa el default seguro.
    
    Returns:
        CuratedMemoryGovernanceAuditTrail configurado
    """
    return CuratedMemoryGovernanceAuditTrail(audit_path=audit_path)
