"""
P2-E Commit 4D-Preflight: Unit tests for SemanticMemoryRealStateAudit

Tests para validar la auditoría read-only del estado real.
NO escriben en memory/semantic real.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_real_state_audit import (
    SemanticMemoryRealStateAudit,
    SemanticMemoryRealStateAuditStatus,
    SemanticMemoryFileAuditRecord,
)


class TestSemanticMemoryFileAuditRecord:
    """Tests para SemanticMemoryFileAuditRecord."""
    
    def test_record_creation(self):
        """Test que se puede crear un registro de auditoría."""
        record = SemanticMemoryFileAuditRecord(
            relative_path="test.jsonl",
            exists=True,
            size_bytes=100,
            sha256="abc123",
            role="jsonl_store",
        )
        
        assert record.relative_path == "test.jsonl"
        assert record.exists is True
        assert record.size_bytes == 100
        assert record.role == "jsonl_store"


class TestSemanticMemoryRealStateAudit:
    """Tests para SemanticMemoryRealStateAudit."""
    
    def test_audit_read_only_on_tmp_path(self, tmp_path):
        """Test que audit_read_only en tmp_path con jsonl y npz devuelve AUDIT_COMPLETED."""
        # Crear archivos esperados
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"fake_npz_data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert report.status == SemanticMemoryRealStateAuditStatus.AUDIT_COMPLETED
        assert report.file_count >= 2
        assert report.allow_real_write is False
        assert report.dry_run_only is True
    
    def test_detects_file_count_correct(self, tmp_path):
        """Test que detecta file_count correcto."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        # metadata_optional no se crea intencionalmente
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        # file_count incluye todos los archivos esperados (3), aunque meta.json no exista
        assert report.file_count == 3
    
    def test_calculates_sha256(self, tmp_path):
        """Test que calcula sha256."""
        content = b"test content"
        (tmp_path / "semantic_memory.jsonl").write_bytes(content)
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        jsonl_record = next(f for f in report.files if f.relative_path == "semantic_memory.jsonl")
        assert jsonl_record.sha256 is not None
        assert len(jsonl_record.sha256) == 64  # SHA-256 hex length
    
    def test_total_bytes_correct(self, tmp_path):
        """Test que total_bytes es correcto."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert report.total_bytes == len(b"[]") + len(b"data")
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert report.dry_run_only is True
    
    def test_detects_jsonl_as_jsonl_store(self, tmp_path):
        """Test que detecta semantic_memory.jsonl como jsonl_store."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        jsonl_record = next(f for f in report.files if f.relative_path == "semantic_memory.jsonl")
        assert jsonl_record.role == "jsonl_store"
    
    def test_detects_npz_as_vector_index_npz(self, tmp_path):
        """Test que detecta semantic_memory_index.npz como vector_index_npz."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        npz_record = next(f for f in report.files if f.relative_path == "semantic_memory_index.npz")
        assert npz_record.role == "vector_index_npz"
    
    def test_detects_meta_as_metadata_optional(self, tmp_path):
        """Test que detecta semantic_memory_meta.json como metadata_optional."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "semantic_memory_meta.json").write_text("{}")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        meta_record = next(f for f in report.files if f.relative_path == "semantic_memory_meta.json")
        assert meta_record.role == "metadata_optional"
    
    def test_detects_extra_file_as_extra_role(self, tmp_path):
        """Test que detecta extra file como extra_role."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "extra_file.txt").write_text("extra")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        extra_record = next(f for f in report.files if f.relative_path == "extra_file.txt")
        assert extra_record.role == "extra_file"
    
    def test_extra_file_generates_warning(self, tmp_path):
        """Test que archivo extra genera warning."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "extra_file.txt").write_text("extra")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert any("extra" in w.lower() for w in report.warnings)
    
    def test_missing_file_generates_warning(self, tmp_path):
        """Test que archivo faltante genera warning."""
        # Solo crear npz, faltará jsonl
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert any("faltante" in w.lower() or "missing" in w.lower() for w in report.warnings)
    
    def test_empty_file_generates_warning(self, tmp_path):
        """Test que archivo size 0 genera warning."""
        (tmp_path / "semantic_memory.jsonl").write_text("")  # Empty
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        assert any("vacío" in w.lower() or "empty" in w.lower() for w in report.warnings)
    
    def test_nonexistent_source_root_returns_failed(self):
        """Test que source_root inexistente devuelve FAILED."""
        audit = SemanticMemoryRealStateAudit(source_root="/nonexistent/path/12345")
        report = audit.audit_read_only()
        
        assert report.status == SemanticMemoryRealStateAuditStatus.FAILED
    
    def test_validate_expected_files_detects_missing(self, tmp_path):
        """Test que validate_expected_files detecta faltantes."""
        # Solo crear npz
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        audit = SemanticMemoryRealStateAudit(source_root=tmp_path)
        report = audit.audit_read_only()
        
        errors, warnings = audit.validate_expected_files(report)
        
        assert any("semantic_memory.jsonl" in e for e in errors)
    
    def test_block_real_write_returns_blocked(self):
        """Test que block_real_write devuelve BLOCKED_REAL_WRITE."""
        audit = SemanticMemoryRealStateAudit()
        report = audit.block_real_write("Test block")
        
        assert report.status == SemanticMemoryRealStateAuditStatus.BLOCKED_REAL_WRITE
    
    def test_block_real_write_maintains_allow_real_write_false(self):
        """Test que block_real_write mantiene allow_real_write=False."""
        audit = SemanticMemoryRealStateAudit()
        report = audit.block_real_write("Test block")
        
        assert report.allow_real_write is False
        assert report.dry_run_only is True
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize devuelve allow_real_write=False."""
        audit = SemanticMemoryRealStateAudit()
        summary = audit.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != "faiss"
                elif isinstance(node, ast.ImportFrom):
                    assert node.module != "faiss"
    
    def test_no_requests_import(self):
        """Test que el módulo no importa requests."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in ["requests", "httpx"]
    
    def test_no_semantic_memory_bridge_import(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "semantic_memory_bridge" not in alias.name
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "semantic_memory_bridge" not in node.module
    
    def test_no_write_operations_in_productive_code(self):
        """Test que el módulo no usa write_text/write_bytes/open."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        assert node.func.id not in ["open"]
                    elif isinstance(node.func, ast.Attribute):
                        # Solo permitir read_bytes, no write_text/write_bytes
                        if node.func.attr in ["write_text", "write_bytes"]:
                            pytest.fail(f"Found forbidden write operation: {node.func.attr}")
    
    def test_no_delete_operations(self):
        """Test que el módulo no usa unlink/remove/rmdir."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr not in ["unlink", "remove", "rmdir"]
    
    def test_no_add_memory_call(self):
        """Test que el módulo no llama .add_memory(."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr != "add_memory"
    
    def test_no_promote_real(self):
        """Test que el módulo no implementa promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "promote_real"
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo no implementa execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "execute_rollback_real"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que no hay allow_real_write=True en código productivo."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_state_audit.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "allow_real_write":
                            if isinstance(node.value, ast.Constant):
                                assert node.value.value is False
                        if isinstance(target, ast.Attribute) and target.attr == "allow_real_write":
                            if isinstance(node.value, ast.Constant):
                                assert node.value.value is False
