"""
P2-E Commit 4D-CleanClassification: Unit tests for SemanticMemoryExtraFileClassifier

Tests para validar la clasificación de archivos extra.
NO escriben en memory/semantic real.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_extra_file_classifier import (
    SemanticMemoryExtraFileClassifier,
    SemanticMemoryExtraFileClass,
    SemanticMemoryExtraFileRisk,
)


class TestSemanticMemoryExtraFileClassifier:
    """Tests para SemanticMemoryExtraFileClassifier."""
    
    def test_classifies_jsonl_as_required_store(self, tmp_path):
        """Test que clasifica semantic_memory.jsonl como REQUIRED_STORE."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        jsonl_class = next(c for c in report.classifications if c.relative_path == "semantic_memory.jsonl")
        assert jsonl_class.file_class == SemanticMemoryExtraFileClass.REQUIRED_STORE
    
    def test_classifies_npz_as_required_index(self, tmp_path):
        """Test que clasifica semantic_memory_index.npz como REQUIRED_INDEX."""
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        npz_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_index.npz")
        assert npz_class.file_class == SemanticMemoryExtraFileClass.REQUIRED_INDEX
    
    def test_classifies_meta_as_optional_metadata(self, tmp_path):
        """Test que clasifica semantic_memory_meta.json como OPTIONAL_METADATA."""
        (tmp_path / "semantic_memory_meta.json").write_text("{}")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        meta_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_meta.json")
        assert meta_class.file_class == SemanticMemoryExtraFileClass.OPTIONAL_METADATA
    
    def test_classifies_faiss_index_as_faiss_index_artifact(self, tmp_path):
        """Test que clasifica semantic_memory_faiss.index como FAISS_INDEX_ARTIFACT."""
        (tmp_path / "semantic_memory_faiss.index").write_bytes(b"faiss_index_data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        faiss_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_faiss.index")
        assert faiss_class.file_class == SemanticMemoryExtraFileClass.FAISS_INDEX_ARTIFACT
    
    def test_classifies_faiss_ids_as_faiss_id_map_artifact(self, tmp_path):
        """Test que clasifica semantic_memory_faiss_ids.json como FAISS_ID_MAP_ARTIFACT."""
        (tmp_path / "semantic_memory_faiss_ids.json").write_text('{"ids": []}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        faiss_ids_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_faiss_ids.json")
        assert faiss_ids_class.file_class == SemanticMemoryExtraFileClass.FAISS_ID_MAP_ARTIFACT
    
    def test_classifies_migration_progress_as_migration_metadata(self, tmp_path):
        """Test que clasifica migration_progress.json como MIGRATION_PROGRESS_METADATA."""
        (tmp_path / "migration_progress.json").write_text('{"progress": 0.5}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        migration_class = next(c for c in report.classifications if c.relative_path == "migration_progress.json")
        assert migration_class.file_class == SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA
    
    def test_classifies_smart_migration_as_migration_metadata(self, tmp_path):
        """Test que clasifica smart_migration_progress.json como MIGRATION_PROGRESS_METADATA."""
        (tmp_path / "smart_migration_progress.json").write_text('{"progress": 0.7}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        smart_class = next(c for c in report.classifications if c.relative_path == "smart_migration_progress.json")
        assert smart_class.file_class == SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA
    
    def test_classifies_unknown_as_unknown_extra(self, tmp_path):
        """Test que clasifica archivo desconocido como UNKNOWN_EXTRA."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "unknown_file.txt").write_text("unknown content")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        unknown_class = next(c for c in report.classifications if c.relative_path == "unknown_file.txt")
        assert unknown_class.file_class == SemanticMemoryExtraFileClass.UNKNOWN_EXTRA
    
    def test_faiss_index_artifact_has_high_risk(self, tmp_path):
        """Test que FAISS_INDEX_ARTIFACT tiene risk HIGH."""
        (tmp_path / "semantic_memory_faiss.index").write_bytes(b"faiss_data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        faiss_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_faiss.index")
        assert faiss_class.risk == SemanticMemoryExtraFileRisk.HIGH
    
    def test_faiss_id_map_artifact_has_high_risk(self, tmp_path):
        """Test que FAISS_ID_MAP_ARTIFACT tiene risk HIGH."""
        (tmp_path / "semantic_memory_faiss_ids.json").write_text('{"ids": []}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        faiss_ids_class = next(c for c in report.classifications if c.relative_path == "semantic_memory_faiss_ids.json")
        assert faiss_ids_class.risk == SemanticMemoryExtraFileRisk.HIGH
    
    def test_migration_metadata_has_medium_risk(self, tmp_path):
        """Test que MIGRATION_PROGRESS_METADATA tiene risk MEDIUM."""
        (tmp_path / "migration_progress.json").write_text('{"progress": 0.5}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        migration_class = next(c for c in report.classifications if c.relative_path == "migration_progress.json")
        assert migration_class.risk == SemanticMemoryExtraFileRisk.MEDIUM
    
    def test_unknown_extra_has_unknown_risk(self, tmp_path):
        """Test que UNKNOWN_EXTRA tiene risk UNKNOWN."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "unknown.xyz").write_text("unknown")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        unknown_class = next(c for c in report.classifications if c.relative_path == "unknown.xyz")
        assert unknown_class.risk == SemanticMemoryExtraFileRisk.UNKNOWN
    
    def test_all_extra_files_require_manual_review(self, tmp_path):
        """Test que todo archivo extra requiere manual review."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "semantic_memory_faiss.index").write_bytes(b"faiss_data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        for classification in report.classifications:
            if classification.file_class in [
                SemanticMemoryExtraFileClass.FAISS_INDEX_ARTIFACT,
                SemanticMemoryExtraFileClass.FAISS_ID_MAP_ARTIFACT,
                SemanticMemoryExtraFileClass.MIGRATION_PROGRESS_METADATA,
                SemanticMemoryExtraFileClass.UNKNOWN_EXTRA,
            ]:
                assert classification.requires_manual_review is True
    
    def test_can_delete_without_review_always_false(self, tmp_path):
        """Test que can_delete_without_review siempre es False."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_faiss.index").write_bytes(b"faiss_data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        for classification in report.classifications:
            assert classification.can_delete_without_review is False
    
    def test_can_move_without_review_always_false(self, tmp_path):
        """Test que can_move_without_review siempre es False."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_faiss.index").write_bytes(b"faiss_data")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        for classification in report.classifications:
            assert classification.can_move_without_review is False
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        assert report.dry_run_only is True
    
    def test_calculates_sha256(self, tmp_path):
        """Test que calcula sha256."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        jsonl_class = next(c for c in report.classifications if c.relative_path == "semantic_memory.jsonl")
        assert jsonl_class.sha256 is not None
        assert len(jsonl_class.sha256) == 64  # SHA-256 hex length
    
    def test_detects_json_readable(self, tmp_path):
        """Test que detecta JSON readable en archivo .json válido."""
        (tmp_path / "migration_progress.json").write_text('{"progress": 0.5}')
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        migration_class = next(c for c in report.classifications if c.relative_path == "migration_progress.json")
        assert migration_class.json_readable is True
        assert migration_class.json_top_level_type == "dict"
    
    def test_detects_json_not_readable(self, tmp_path):
        """Test que detecta JSON no readable en archivo .json invalido."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "invalid.json").write_text("not valid json", encoding="utf-8")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        invalid_class = next(c for c in report.classifications if c.relative_path == "invalid.json")
        assert invalid_class.file_class == SemanticMemoryExtraFileClass.UNKNOWN_EXTRA
        assert invalid_class.json_readable is False
        assert invalid_class.json_top_level_type is None
        assert any("json" in w.lower() or "legible" in w.lower() for w in invalid_class.warnings)
    
    def test_classify_read_only_reports_dirty_state_when_extras_exist(self, tmp_path):
        """Test que classify_read_only reporta dirty_state_detected=True si hay extras."""
        (tmp_path / "semantic_memory.jsonl").write_text("[]")
        (tmp_path / "semantic_memory_index.npz").write_bytes(b"data")
        (tmp_path / "extra_file.txt").write_text("extra")
        
        classifier = SemanticMemoryExtraFileClassifier(source_root=tmp_path)
        report = classifier.classify_read_only()
        
        assert report.dirty_state_detected is True
    
    def test_block_cleanup_maintains_allow_real_write_false(self):
        """Test que block_cleanup mantiene allow_real_write=False."""
        classifier = SemanticMemoryExtraFileClassifier()
        report = classifier.block_cleanup("Test block")
        
        assert report.allow_real_write is False
        assert report.dry_run_only is True
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize devuelve allow_real_write=False."""
        classifier = SemanticMemoryExtraFileClassifier()
        summary = classifier.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in ["requests", "httpx"]
    
    def test_no_semantic_memory_bridge_import(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "semantic_memory_bridge" not in alias.name
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "semantic_memory_bridge" not in node.module
    
    def test_no_write_operations_in_productive_code(self):
        """Test que el módulo no usa write_text/write_bytes."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        # Solo permitir read_bytes, no write_text/write_bytes
                        if node.func.attr in ["write_text", "write_bytes"]:
                            pytest.fail(f"Found forbidden write operation: {node.func.attr}")
    
    def test_no_delete_operations(self):
        """Test que el módulo no usa unlink/remove/rmdir."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr not in ["unlink", "remove", "rmdir"]
    
    def test_no_add_memory_call(self):
        """Test que el módulo no llama .add_memory(."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr != "add_memory"
    
    def test_no_promote_real(self):
        """Test que el módulo no implementa promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "promote_real"
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo no implementa execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "execute_rollback_real"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que no hay allow_real_write=True en código productivo."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_classifier.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8")
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
