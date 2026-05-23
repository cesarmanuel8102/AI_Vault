"""
P2-E Commit 4A: Tests unitarios para MemorySemanticBackupContract

Tests para validar contrato de backup/snapshot.
NO escriben en memory/semantic real.
Usan tmp_path para archivos temporales.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.memory_semantic_backup import (
    MemorySemanticBackupContract,
    MemorySemanticBackupStatus,
    MemorySemanticSnapshot,
    MemorySemanticFileFingerprint,
)


class TestMemorySemanticFileFingerprint:
    """Tests para MemorySemanticFileFingerprint."""
    
    def test_fingerprint_creation(self):
        """Test que se puede crear un fingerprint."""
        fp = MemorySemanticFileFingerprint(
            relative_path="test/file.txt",
            size_bytes=1024,
            sha256="abc123",
            modified_at_utc="2026-01-01T00:00:00+00:00",
        )
        
        assert fp.relative_path == "test/file.txt"
        assert fp.size_bytes == 1024
        assert fp.sha256 == "abc123"
        assert fp.modified_at_utc == "2026-01-01T00:00:00+00:00"


class TestMemorySemanticSnapshot:
    """Tests para MemorySemanticSnapshot."""
    
    def test_snapshot_creation(self):
        """Test que se puede crear un snapshot."""
        snapshot = MemorySemanticSnapshot(
            snapshot_id="snap_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            source_root="/test/source",
            file_count=5,
            total_bytes=10240,
            fingerprints=[],
        )
        
        assert snapshot.snapshot_id == "snap_001"
        assert snapshot.source_root == "/test/source"
        assert snapshot.file_count == 5
        assert snapshot.total_bytes == 10240
        assert snapshot.dry_run_only is True
        assert snapshot.allow_real_write is False
    
    def test_snapshot_to_dict(self):
        """Test que to_dict serializa correctamente."""
        snapshot = MemorySemanticSnapshot(
            snapshot_id="snap_002",
            created_at_utc="2026-01-01T00:00:00+00:00",
            source_root="/test",
            file_count=1,
            total_bytes=100,
            fingerprints=[
                MemorySemanticFileFingerprint("file.txt", 100, "hash123", "2026-01-01T00:00:00+00:00"),
            ],
        )
        
        d = snapshot.to_dict()
        assert d["snapshot_id"] == "snap_002"
        assert d["file_count"] == 1
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False
        assert len(d["fingerprints"]) == 1


class TestMemorySemanticBackupContract:
    """Tests para MemorySemanticBackupContract."""
    
    def test_contract_initialization(self):
        """Test que el contrato se inicializa correctamente."""
        contract = MemorySemanticBackupContract(
            source_root="/test/source",
            backup_root="/test/backup",
        )
        
        summary = contract.summarize_contract()
        assert summary["contract_version"] == "P2-E-Commit-4A"
        assert summary["dry_run_only"] is True
        assert summary["allow_real_write"] is False
    
    def test_create_snapshot_generates_id(self, tmp_path):
        """Test que create_snapshot genera snapshot_id."""
        # Crear archivos temporales
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert snapshot.snapshot_id.startswith("snapshot_")
        assert len(snapshot.snapshot_id) > len("snapshot_")
    
    def test_create_snapshot_calculates_file_count(self, tmp_path):
        """Test que snapshot calcula file_count correcto."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.txt").write_text("content3")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert snapshot.file_count == 3
    
    def test_create_snapshot_calculates_total_bytes(self, tmp_path):
        """Test que snapshot calcula total_bytes correcto."""
        (tmp_path / "file1.txt").write_text("abc")  # 3 bytes
        (tmp_path / "file2.txt").write_text("defgh")  # 5 bytes
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert snapshot.total_bytes == 8  # 3 + 5
    
    def test_create_snapshot_calculates_sha256(self, tmp_path):
        """Test que snapshot calcula sha256 correcto."""
        import hashlib
        
        content = "test content"
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        
        (tmp_path / "file.txt").write_text(content)
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert len(snapshot.fingerprints) == 1
        assert snapshot.fingerprints[0].sha256 == expected_hash
    
    def test_snapshot_maintains_dry_run_only(self, tmp_path):
        """Test que snapshot mantiene dry_run_only=True."""
        (tmp_path / "file.txt").write_text("content")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert snapshot.dry_run_only is True
    
    def test_snapshot_maintains_allow_real_write_false(self, tmp_path):
        """Test que snapshot mantiene allow_real_write=False."""
        (tmp_path / "file.txt").write_text("content")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        assert snapshot.allow_real_write is False
    
    def test_verify_snapshot_accepts_valid(self, tmp_path):
        """Test que verify_snapshot acepta snapshot válido."""
        (tmp_path / "file.txt").write_text("content")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        result = contract.verify_snapshot(snapshot)
        
        assert result.status == MemorySemanticBackupStatus.VERIFIED
        assert len(result.validation_errors) == 0
    
    def test_verify_snapshot_detects_modified_file(self, tmp_path):
        """Test que verify_snapshot detecta archivo modificado."""
        (tmp_path / "file.txt").write_text("original")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        # Modificar archivo
        (tmp_path / "file.txt").write_text("modified")
        
        result = contract.verify_snapshot(snapshot)
        
        assert result.status == MemorySemanticBackupStatus.FAILED
        assert len(result.validation_errors) > 0
        assert "Hash mismatch" in result.validation_errors[0]
    
    def test_simulate_backup_no_real_write(self, tmp_path):
        """Test que simulate_backup no escribe backup real."""
        (tmp_path / "file.txt").write_text("content")
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        result = contract.simulate_backup(snapshot)
        
        assert result.status == MemorySemanticBackupStatus.CREATED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
        assert "SIMULATED" in result.warnings[0]
    
    def test_simulate_restore_no_real_restore(self, tmp_path):
        """Test que simulate_restore no modifica archivos."""
        original_content = "original"
        (tmp_path / "file.txt").write_text(original_content)
        
        contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = contract.create_snapshot()
        
        # Modificar archivo
        (tmp_path / "file.txt").write_text("modified")
        
        # Simular restore
        result = contract.simulate_restore(snapshot)
        
        assert result.status == MemorySemanticBackupStatus.RESTORE_SIMULATED
        assert result.dry_run_only is True
        
        # Verificar que archivo NO fue restaurado
        current_content = (tmp_path / "file.txt").read_text()
        assert current_content == "modified"  # Sigue modificado
    
    def test_block_real_restore(self):
        """Test que block_real_restore devuelve REAL_RESTORE_BLOCKED."""
        contract = MemorySemanticBackupContract(source_root="/test")
        
        result = contract.block_real_restore("Test block reason")
        
        assert result.status == MemorySemanticBackupStatus.REAL_RESTORE_BLOCKED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
        assert "REAL_RESTORE_BLOCKED" in result.warnings[0]
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize_contract devuelve allow_real_write=False."""
        contract = MemorySemanticBackupContract(source_root="/test")
        
        summary = contract.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True


class TestSecurityNoForbiddenOperations:
    """Tests de seguridad para operaciones prohibidas usando AST."""
    
    def test_no_dangerous_imports(self):
        """Test que el módulo NO importa faiss, requests o httpx."""
        import ast
        import brain.memory_semantic_backup as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        dangerous = {"faiss", "requests", "httpx"}
        found = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in dangerous:
                        found.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in dangerous:
                    found.append(f"from {node.module}")
        
        assert len(found) == 0, f"Dangerous imports found: {found}"
    
    def test_no_dangerous_calls(self):
        """Test que el módulo NO usa open, promote_real, execute_rollback_real."""
        import ast
        import brain.memory_semantic_backup as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        dangerous_calls = {"open", "promote_real", "execute_rollback_real"}
        found = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in dangerous_calls:
                    found.append(f"{func.id}() at line {node.lineno}")
        
        assert len(found) == 0, f"Dangerous calls found: {found}"
    
    def test_no_dangerous_attrs(self):
        """Test que el módulo NO usa write_text, unlink, remove, rmdir, add_memory."""
        import ast
        import brain.memory_semantic_backup as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        dangerous_attrs = {"write_text", "write_bytes", "unlink", "remove", "rmdir", "add_memory"}
        found = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in dangerous_attrs:
                    found.append(f"{func.attr}() at line {node.lineno}")
        
        assert len(found) == 0, f"Dangerous attr calls found: {found}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
