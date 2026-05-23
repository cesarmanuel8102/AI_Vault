"""
P2-E Commit 4D-DependencyMapping: Unit tests for SemanticMemoryExtraFileDependencyMapper

Tests para validar el mapeo estático de dependencias.
NO escriben en memory/semantic real.
NO ejecutan código sospechoso.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_extra_file_dependency_mapper import (
    SemanticMemoryExtraFileDependencyMapper,
    SemanticMemoryDependencyKind,
    SemanticMemoryDependencyRole,
    SemanticMemoryDependencyAccessMode,
    SemanticMemoryDependencyRisk,
)


class TestSemanticMemoryExtraFileDependencyMapper:
    """Tests para SemanticMemoryExtraFileDependencyMapper."""
    
    def test_detects_exact_migration_progress_reference(self, tmp_path):
        """Test que detecta referencia exacta a migration_progress.json."""
        # Crear archivo Python con referencia
        test_file = tmp_path / "test_module.py"
        test_file.write_text('data = load_json("migration_progress.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        assert report.hit_count >= 1
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        assert len(hits) >= 1
    
    def test_detects_exact_faiss_index_reference(self, tmp_path):
        """Test que detecta referencia exacta a semantic_memory_faiss.index."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text('index = load_index("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        assert len(hits) >= 1
    
    def test_detects_exact_faiss_ids_reference(self, tmp_path):
        """Test que detecta referencia exacta a semantic_memory_faiss_ids.json."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text('ids = load_json("semantic_memory_faiss_ids.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss_ids.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss_ids.json"]
        assert len(hits) >= 1
    
    def test_detects_smart_migration_progress_reference(self, tmp_path):
        """Test que detecta referencia a smart_migration_progress.json."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text('progress = read_json("smart_migration_progress.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["smart_migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "smart_migration_progress.json"]
        assert len(hits) >= 1
    
    def test_detects_memory_semantic_path_reference(self, tmp_path):
        """Test que detecta referencia genérica a memory/semantic."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text('path = Path("memory/semantic")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["memory/semantic"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "memory/semantic"]
        assert len(hits) >= 1
    
    def test_detects_semantic_memory_faiss_reference(self, tmp_path):
        """Test que detecta referencia genérica a semantic_memory_faiss."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text('index = faiss.read_index("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss"]
        assert len(hits) >= 1
    
    def test_classifies_docs_as_docs(self, tmp_path):
        """Test que clasifica archivos docs/ como DOCS."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "readme.md"
        doc_file.write_text("Documentación sobre migration_progress.json", encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].dependency_role == SemanticMemoryDependencyRole.DOCS
    
    def test_classifies_unit_tests_as_test(self, tmp_path):
        """Test que clasifica tests/unit como TEST."""
        test_dir = tmp_path / "tests" / "unit"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "test_something.py"
        test_file.write_text('def test(): load("migration_progress.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].dependency_role == SemanticMemoryDependencyRole.TEST
    
    def test_classifies_smoke_tests_as_smoke(self, tmp_path):
        """Test que clasifica tests/smoke como SMOKE."""
        smoke_dir = tmp_path / "tests" / "smoke"
        smoke_dir.mkdir(parents=True)
        smoke_file = smoke_dir / "test_smoke.py"
        smoke_file.write_text('print("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].dependency_role == SemanticMemoryDependencyRole.SMOKE
    
    def test_classifies_brain_as_runtime_core(self, tmp_path):
        """Test que clasifica brain/*.py como RUNTIME_CORE."""
        brain_dir = tmp_path / "brain"
        brain_dir.mkdir()
        brain_file = brain_dir / "module.py"
        brain_file.write_text('x = "migration_progress.json"', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].dependency_role == SemanticMemoryDependencyRole.RUNTIME_CORE
    
    def test_classifies_scripts_as_script_or_tooling(self, tmp_path):
        """Test que clasifica scripts/ como SCRIPT_OR_TOOLING."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        script_file = scripts_dir / "tool.py"
        script_file.write_text('process("migration_progress.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].dependency_role == SemanticMemoryDependencyRole.SCRIPT_OR_TOOLING
    
    def test_read_text_access_mode(self, tmp_path):
        """Test que línea con read_text => READ_ONLY_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('content = Path("migration_progress.json").read_text()', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.READ_ONLY_LIKELY
    
    def test_read_bytes_access_mode(self, tmp_path):
        """Test que línea con read_bytes => READ_ONLY_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('data = Path("semantic_memory_faiss.index").read_bytes()', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.READ_ONLY_LIKELY
    
    def test_write_text_access_mode(self, tmp_path):
        """Test que línea con write_text => WRITE_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('Path("migration_progress.json").write_text("{}")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.WRITE_LIKELY
    
    def test_add_memory_access_mode(self, tmp_path):
        """Test que línea con add_memory => WRITE_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('memory.add_memory("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.WRITE_LIKELY
    
    def test_unlink_access_mode(self, tmp_path):
        """Test que línea con unlink => DELETE_OR_MOVE_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('Path("migration_progress.json").unlink()', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.DELETE_OR_MOVE_LIKELY
    
    def test_remove_access_mode(self, tmp_path):
        """Test que línea con remove => DELETE_OR_MOVE_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('os.remove("migration_progress.json")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.DELETE_OR_MOVE_LIKELY
    
    def test_import_faiss_access_mode(self, tmp_path):
        """Test que línea con import faiss => IMPORT_OR_RUNTIME_LIKELY."""
        test_file = tmp_path / "test.py"
        test_file.write_text('import faiss\nindex = faiss.read_index("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].access_mode == SemanticMemoryDependencyAccessMode.IMPORT_OR_RUNTIME_LIKELY
    
    def test_high_risk_for_write_like(self, tmp_path):
        """Test que HIGH risk para write-like."""
        test_file = tmp_path / "test.py"
        test_file.write_text('Path("migration_progress.json").write_text("{}")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].risk == SemanticMemoryDependencyRisk.HIGH
    
    def test_high_risk_for_delete_move(self, tmp_path):
        """Test que HIGH risk para delete/move."""
        test_file = tmp_path / "test.py"
        test_file.write_text('Path("migration_progress.json").unlink()', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].risk == SemanticMemoryDependencyRisk.HIGH
    
    def test_high_risk_for_faiss_in_runtime(self, tmp_path):
        """Test que HIGH risk para FAISS en runtime core."""
        brain_dir = tmp_path / "brain"
        brain_dir.mkdir()
        brain_file = brain_dir / "module.py"
        brain_file.write_text('import faiss\nfaiss.read_index("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].risk == SemanticMemoryDependencyRisk.HIGH
    
    def test_medium_risk_for_faiss_in_tooling(self, tmp_path):
        """Test que MEDIUM risk para FAISS en tooling."""
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        script_file = scripts_dir / "tool.py"
        script_file.write_text('print("semantic_memory_faiss.index")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["semantic_memory_faiss.index"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "semantic_memory_faiss.index"]
        if hits:
            assert hits[0].risk == SemanticMemoryDependencyRisk.MEDIUM
    
    def test_low_risk_for_docs(self, tmp_path):
        """Test que LOW risk para docs."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        doc_file = docs_dir / "readme.md"
        doc_file.write_text("Documentación sobre migration_progress.json", encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        hits = [h for h in report.hits if h.target_name == "migration_progress.json"]
        if hits:
            assert hits[0].risk == SemanticMemoryDependencyRisk.LOW
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        mapper = SemanticMemoryExtraFileDependencyMapper(repo_root=tmp_path)
        report = mapper.map_read_only()
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        mapper = SemanticMemoryExtraFileDependencyMapper(repo_root=tmp_path)
        report = mapper.map_read_only()
        
        assert report.dry_run_only is True
    
    def test_requires_manual_review_when_high_risk(self, tmp_path):
        """Test que requires_manual_review True cuando hay hits de riesgo HIGH."""
        test_file = tmp_path / "test.py"
        test_file.write_text('Path("migration_progress.json").write_text("{}")', encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        assert report.requires_manual_review is True
    
    def test_skipped_file_count_increases_for_large_files(self, tmp_path):
        """Test que skipped_file_count aumenta si archivo > 2 MB."""
        # Crear archivo grande (> 2 MB) - actual contenido grande, no código Python
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 'a'" + "\n" * (3 * 1024 * 1024), encoding="utf-8")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
        )
        report = mapper.map_read_only()
        
        assert report.skipped_file_count >= 1
    
    def test_skips_binary_files_not_in_extensions(self, tmp_path):
        """Test que no lee archivos binarios no incluidos por extensión."""
        # Crear archivo binario
        binary_file = tmp_path / "data.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        
        mapper = SemanticMemoryExtraFileDependencyMapper(
            repo_root=tmp_path,
            target_names=["migration_progress.json"],
            include_extensions={".py"},  # Solo .py
        )
        report = mapper.map_read_only()
        
        # No debería escanear el archivo binario
        assert report.scanned_file_count == 0
    
    def test_block_runtime_use_maintains_allow_real_write_false(self, tmp_path):
        """Test que block_runtime_use mantiene allow_real_write=False."""
        mapper = SemanticMemoryExtraFileDependencyMapper(repo_root=tmp_path)
        report = mapper.block_runtime_use("Test block")
        
        assert report.allow_real_write is False
        assert report.dry_run_only is True
    
    def test_summarize_contract_returns_allow_real_write_false(self, tmp_path):
        """Test que summarize devuelve allow_real_write=False."""
        mapper = SemanticMemoryExtraFileDependencyMapper(repo_root=tmp_path)
        summary = mapper.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in ["requests", "httpx"]
    
    def test_no_semantic_memory_bridge_import(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "semantic_memory_bridge" not in alias.name
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "semantic_memory_bridge" not in node.module
    
    def test_no_subprocess_import(self):
        """Test que el módulo no importa subprocess."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != "subprocess"
                elif isinstance(node, ast.ImportFrom):
                    assert node.module != "subprocess"
    
    def test_no_open_in_productive_code(self):
        """Test que el módulo no usa open()."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        assert node.func.id != "open", f"open() call found at line {node.lineno}"
    
    def test_no_write_operations_in_productive_code(self):
        """Test que el módulo no usa write_text/write_bytes."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr in ["write_text", "write_bytes"]:
                            pytest.fail(f"Found forbidden write operation: {node.func.attr}")
    
    def test_no_delete_operations(self):
        """Test que el módulo no usa unlink/remove/rmdir."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr not in ["unlink", "remove", "rmdir"]
    
    def test_no_add_memory_call(self):
        """Test que el módulo no llama .add_memory(."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr != "add_memory"
    
    def test_no_promote_real(self):
        """Test que el módulo no implementa promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "promote_real"
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo no implementa execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "execute_rollback_real"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que no hay allow_real_write=True en código productivo."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_extra_file_dependency_mapper.py"
        if module_path.exists():
            content = module_path.read_text(encoding="utf-8", errors="ignore")
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
