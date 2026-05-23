"""
P2-E Commit 3B: Tests para Curated Memory Governance Audit Trail

Tests unitarios para validar el audit trail de governance.
NO escribe en archivos permanentes.
NO requiere FAISS.
NO requiere runtime 8090.
Usa tmp_path para aislamiento de tests.
"""

import pytest
import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_governance_audit import (
    AuditEntryType,
    AuditEntryStatus,
    GovernanceAuditEntry,
    CuratedMemoryGovernanceAuditTrail,
    create_audit_trail,
)


class TestGovernanceAuditEntry:
    """Tests para GovernanceAuditEntry."""
    
    def test_entry_creation(self):
        """Test que se puede crear una entrada básica."""
        entry = GovernanceAuditEntry(
            entry_id="entry_001",
            entry_type=AuditEntryType.REQUEST,
            request_id="req_001",
            actor="test_user",
            evidence_hash="abc123",
            payload_hash="def456",
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert entry.entry_id == "entry_001"
        assert entry.entry_type == AuditEntryType.REQUEST
        assert entry.request_id == "req_001"
        assert entry.actor == "test_user"
        assert entry.dry_run_only is True
        assert entry.allow_real_write is False
    
    def test_entry_to_dict(self):
        """Test que to_dict serializa correctamente."""
        entry = GovernanceAuditEntry(
            entry_id="entry_002",
            entry_type=AuditEntryType.DECISION,
            request_id="req_002",
            decision_id="dec_002",
            status=AuditEntryStatus.VALIDATED,
            actor="approver",
            created_at_utc="2026-01-01T00:00:00+00:00",
            evidence_hash="xyz789",
            payload_hash="uvw012",
            dry_run_only=True,
            allow_real_write=False,
            metadata={"test": "data"},
        )
        
        d = entry.to_dict()
        assert d["entry_id"] == "entry_002"
        assert d["entry_type"] == "DECISION"
        assert d["decision_id"] == "dec_002"
        assert d["status"] == "VALIDATED"
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False
        assert d["metadata"] == {"test": "data"}
    
    def test_entry_from_dict(self):
        """Test que from_dict deserializa correctamente."""
        data = {
            "entry_id": "entry_003",
            "entry_type": "REQUEST",
            "request_id": "req_003",
            "decision_id": None,
            "status": "PENDING",
            "actor": "user",
            "created_at_utc": "2026-01-01T00:00:00+00:00",
            "evidence_hash": "hash1",
            "payload_hash": "hash2",
            "dry_run_only": True,
            "allow_real_write": False,
            "metadata": {},
        }
        
        entry = GovernanceAuditEntry.from_dict(data)
        assert entry.entry_id == "entry_003"
        assert entry.entry_type == AuditEntryType.REQUEST
        assert entry.status == AuditEntryStatus.PENDING


class TestCuratedMemoryGovernanceAuditTrail:
    """Tests para CuratedMemoryGovernanceAuditTrail."""
    
    def test_default_audit_path_not_in_memory_semantic(self):
        """Test que el audit path por defecto NO está en memory/semantic."""
        trail = CuratedMemoryGovernanceAuditTrail()
        path_str = str(trail.audit_path).lower()
        
        assert "memory/semantic" not in path_str
        assert "memory\\semantic" not in path_str
        # Debe estar en tmp_agent/state/governance
        assert "tmp_agent" in path_str
    
    def test_compute_payload_hash_is_deterministic(self):
        """Test que compute_payload_hash es determinista."""
        trail = CuratedMemoryGovernanceAuditTrail()
        
        payload = {"key": "value", "number": 42}
        hash1 = trail.compute_payload_hash(payload)
        hash2 = trail.compute_payload_hash(payload)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex
    
    def test_compute_payload_hash_different_payloads(self):
        """Test que payloads diferentes producen hashes diferentes."""
        trail = CuratedMemoryGovernanceAuditTrail()
        
        payload1 = {"key": "value1"}
        payload2 = {"key": "value2"}
        
        hash1 = trail.compute_payload_hash(payload1)
        hash2 = trail.compute_payload_hash(payload2)
        
        assert hash1 != hash2
    
    def test_append_request_creates_audit_entry(self, tmp_path):
        """Test que append_request crea una entrada de audit."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = trail.append_request(
            request_id="req_test_001",
            actor="test_user",
            evidence_hash="evidence_hash_001",
            payload={"test": "data"},
            metadata={"source": "test"},
        )
        
        assert entry.entry_type == AuditEntryType.REQUEST
        assert entry.request_id == "req_test_001"
        assert entry.actor == "test_user"
        assert entry.dry_run_only is True
        assert entry.allow_real_write is False
        assert entry.payload_hash != ""
    
    def test_append_decision_creates_audit_entry(self, tmp_path):
        """Test que append_decision crea una entrada de audit."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = trail.append_decision(
            request_id="req_test_002",
            decision_id="dec_test_001",
            actor="approver",
            evidence_hash="evidence_hash_002",
            approved=True,
            payload={"result": "approved"},
        )
        
        assert entry.entry_type == AuditEntryType.DECISION
        assert entry.request_id == "req_test_002"
        assert entry.decision_id == "dec_test_001"
        assert entry.status == AuditEntryStatus.VALIDATED
        assert entry.dry_run_only is True
        assert entry.allow_real_write is False
    
    def test_append_decision_rejected(self, tmp_path):
        """Test que append_decision con approved=False crea entrada REJECTED."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = trail.append_decision(
            request_id="req_test_003",
            decision_id="dec_test_002",
            actor="rejector",
            evidence_hash="evidence_hash_003",
            approved=False,
        )
        
        assert entry.status == AuditEntryStatus.REJECTED
    
    def test_validate_entry_accepts_well_formed(self, tmp_path):
        """Test que validate_entry acepta entrada bien formada."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = GovernanceAuditEntry(
            entry_id="entry_valid",
            entry_type=AuditEntryType.REQUEST,
            request_id="req_valid",
            actor="user",
            evidence_hash="valid_hash",
            payload_hash="payload_hash",
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = trail.validate_entry(entry)
        assert is_valid is True
    
    def test_validate_entry_rejects_allow_real_write_true(self, tmp_path):
        """Test que validate_entry rechaza allow_real_write=True."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = GovernanceAuditEntry(
            entry_id="entry_invalid",
            entry_type=AuditEntryType.REQUEST,
            request_id="req_invalid",
            actor="user",
            evidence_hash="valid_hash",
            payload_hash="payload_hash",
            dry_run_only=True,
            allow_real_write=True,  # No permitido
        )
        
        is_valid = trail.validate_entry(entry)
        assert is_valid is False
    
    def test_validate_entry_rejects_without_evidence_hash(self, tmp_path):
        """Test que validate_entry rechaza entrada sin evidence_hash."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = GovernanceAuditEntry(
            entry_id="entry_no_evidence",
            entry_type=AuditEntryType.REQUEST,
            request_id="req_no_evidence",
            actor="user",
            evidence_hash="",  # Vacío
            payload_hash="payload_hash",
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = trail.validate_entry(entry)
        assert is_valid is False
    
    def test_list_entries_retrieves_persisted(self, tmp_path):
        """Test que list_entries recupera entradas persistidas."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        # Crear entradas
        trail.append_request(
            request_id="req_list_001",
            actor="user1",
            evidence_hash="hash1",
        )
        trail.append_request(
            request_id="req_list_002",
            actor="user2",
            evidence_hash="hash2",
        )
        
        # Recuperar
        entries = trail.list_entries()
        assert len(entries) == 2
        
        # Filtrar por tipo
        request_entries = trail.list_entries(entry_type=AuditEntryType.REQUEST)
        assert len(request_entries) == 2
    
    def test_list_entries_filter_by_request_id(self, tmp_path):
        """Test que list_entries filtra por request_id."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        trail.append_request(
            request_id="req_filter_001",
            actor="user",
            evidence_hash="hash1",
        )
        trail.append_decision(
            request_id="req_filter_001",
            decision_id="dec_filter_001",
            actor="approver",
            evidence_hash="hash2",
            approved=True,
        )
        trail.append_request(
            request_id="req_filter_002",
            actor="user",
            evidence_hash="hash3",
        )
        
        # Filtrar por request_id
        entries = trail.list_entries(request_id="req_filter_001")
        assert len(entries) == 2
    
    def test_get_entry_by_id(self, tmp_path):
        """Test que get_entry_by_id recupera entrada específica."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        entry = trail.append_request(
            request_id="req_get_001",
            actor="user",
            evidence_hash="hash",
        )
        
        retrieved = trail.get_entry_by_id(entry.entry_id)
        assert retrieved is not None
        assert retrieved.entry_id == entry.entry_id
    
    def test_get_audit_stats(self, tmp_path):
        """Test que get_audit_stats retorna estadísticas correctas."""
        audit_file = tmp_path / "test_audit.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        # Crear mix de entradas
        trail.append_request(
            request_id="req_stat_001",
            actor="user1",
            evidence_hash="hash1",
        )
        trail.append_decision(
            request_id="req_stat_001",
            decision_id="dec_stat_001",
            actor="approver",
            evidence_hash="hash2",
            approved=True,
        )
        trail.append_decision(
            request_id="req_stat_002",
            decision_id="dec_stat_002",
            actor="rejector",
            evidence_hash="hash3",
            approved=False,
        )
        
        stats = trail.get_audit_stats()
        assert stats["total_entries"] == 3
        assert stats["requests"] == 1
        assert stats["decisions"] == 2
        assert stats["validated"] == 1
        assert stats["rejected"] == 1
    
    def test_persist_and_reload(self, tmp_path):
        """Test que las entradas persisten y se recargan."""
        audit_file = tmp_path / "test_persist.ndjson"
        
        # Crear trail y agregar entradas
        trail1 = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        trail1.append_request(
            request_id="req_persist_001",
            actor="user",
            evidence_hash="hash_persist",
        )
        
        # Crear nuevo trail con mismo archivo (debe recargar)
        trail2 = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        entries = trail2.list_entries()
        
        assert len(entries) == 1
        assert entries[0].request_id == "req_persist_001"


class TestNoForbiddenModules:
    """Tests para verificar que no hay imports prohibidos."""
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import sys
        # Limpiar módulos prohibidos si existen
        forbidden = ["faiss", "semantic_memory", "requests", "httpx"]
        for mod in list(sys.modules.keys()):
            if any(f in mod.lower() for f in forbidden):
                del sys.modules[mod]
        
        # Importar el módulo
        import brain.curated_memory_governance_audit as audit_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_memory_semantic_write(self, tmp_path):
        """Test que no se escribe en memory/semantic."""
        # Crear trail en path temporal (no memory/semantic)
        audit_file = tmp_path / "test_safe.ndjson"
        trail = CuratedMemoryGovernanceAuditTrail(audit_path=str(audit_file))
        
        # Verificar path seguro
        path_str = str(audit_file).lower()
        assert "memory/semantic" not in path_str
        assert "memory\\semantic" not in path_str
        
        # Operar
        trail.append_request(
            request_id="req_safe_001",
            actor="user",
            evidence_hash="hash_safe",
        )
        
        # Verificar archivo creado en path correcto
        assert audit_file.exists()


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    trail = create_audit_trail()
    assert isinstance(trail, CuratedMemoryGovernanceAuditTrail)
    assert len(trail._entries) == 0


def test_factory_with_custom_path(tmp_path):
    """Test que la factory acepta path personalizado."""
    custom_path = tmp_path / "custom_audit.ndjson"
    trail = create_audit_trail(audit_path=str(custom_path))
    assert str(trail.audit_path) == str(custom_path)
