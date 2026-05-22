"""
Tests unitarios para ProjectStateProvider.

Verifica:
- Detección de P2-C/P2-D desde archivos
- NO afirmación de runtime/FAISS
- NO imports prohibidos
- Fallback cuando faltan archivos
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.project_state_provider import (
    ProjectStateProvider,
    P2State,
    create_project_state_provider
)


class TestProjectStateProvider:
    """Tests para ProjectStateProvider."""
    
    def test_detects_p2c_completed_from_files(self, tmp_path):
        """Si existen adapter + test, P2-C está completado."""
        # Crear estructura fake
        brain_dir = tmp_path / "brain"
        tests_dir = tmp_path / "tests" / "unit"
        brain_dir.mkdir(parents=True)
        tests_dir.mkdir(parents=True)
        
        (brain_dir / "curation_validation_adapter.py").write_text("# fake adapter")
        (tests_dir / "test_curation_validation_adapter.py").write_text("# fake test")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        state = provider.get_p2_state()
        
        assert state.p2_c_completed is True
        assert state.adapter_file_exists is True
        assert state.adapter_test_exists is True
    
    def test_detects_p2d_completed_from_files(self, tmp_path):
        """Si existen doc + smoke, P2-D está completado."""
        docs_dir = tmp_path / "docs"
        smoke_dir = tmp_path / "tests" / "smoke"
        docs_dir.mkdir(parents=True)
        smoke_dir.mkdir(parents=True)
        
        (docs_dir / "P2D_CURATION_VALIDATION_ADAPTER_USAGE.md").write_text("# fake doc")
        (smoke_dir / "smoke_curation_validation_adapter.py").write_text("# fake smoke")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        state = provider.get_p2_state()
        
        assert state.p2_d_completed is True
        assert state.adapter_doc_exists is True
        assert state.adapter_smoke_exists is True
    
    def test_summary_does_not_claim_runtime_or_faiss(self, tmp_path):
        """summary_p2_state no debe decir que escribe FAISS ni runtime."""
        brain_dir = tmp_path / "brain"
        tests_unit = tmp_path / "tests" / "unit"
        docs_dir = tmp_path / "docs"
        smoke_dir = tmp_path / "tests" / "smoke"
        
        for d in [brain_dir, tests_unit, docs_dir, smoke_dir]:
            d.mkdir(parents=True)
        
        (brain_dir / "curation_validation_adapter.py").write_text("# fake")
        (tests_unit / "test_curation_validation_adapter.py").write_text("# fake")
        (docs_dir / "P2D_CURATION_VALIDATION_ADAPTER_USAGE.md").write_text("# fake")
        (smoke_dir / "smoke_curation_validation_adapter.py").write_text("# fake")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        summary = provider.summarize_p2_state()
        
        # No debe afirmar que conecta runtime/chat (debe negar o no mencionar)
        assert "no conecta a runtime" in summary.lower() or "no escribe en" in summary.lower()
        # No debe afirmar que escribe FAISS (debe negar)
        assert "NO escribe" in summary
    
    def test_explain_auto_learning_status_denies_auto_learning(self, tmp_path):
        """Debe negar autoaprendizaje automático."""
        # Crear archivos P2-C y P2-D para que el provider use el mensaje completo
        brain_dir = tmp_path / "brain"
        tests_unit = tmp_path / "tests" / "unit"
        docs_dir = tmp_path / "docs"
        smoke_dir = tmp_path / "tests" / "smoke"
        
        for d in [brain_dir, tests_unit, docs_dir, smoke_dir]:
            d.mkdir(parents=True)
        
        (brain_dir / "curation_validation_adapter.py").write_text("# fake")
        (tests_unit / "test_curation_validation_adapter.py").write_text("# fake")
        (docs_dir / "P2D_CURATION_VALIDATION_ADAPTER_USAGE.md").write_text("# fake")
        (smoke_dir / "smoke_curation_validation_adapter.py").write_text("# fake")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        explanation = provider.explain_auto_learning_status()
        
        # Debe negar explícitamente
        assert "NO hay autoaprendizaje" in explanation or "no hay autoaprendizaje" in explanation.lower()
        assert "requiere" in explanation.lower() and "manual" in explanation.lower()
    
    def test_provider_no_forbidden_imports(self):
        """Verificar que project_state_provider.py no tiene imports prohibidos."""
        import ast
        
        provider_path = Path(__file__).parent.parent.parent / "brain" / "project_state_provider.py"
        source = provider_path.read_text()
        tree = ast.parse(source)
        
        forbidden_imports = [
            "session",
            "main",
            "faiss",
            "semantic_memory_bridge"
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        assert forbidden not in alias.name.lower(), \
                            f"Import prohibido detectado: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_imports:
                        assert forbidden not in node.module.lower(), \
                            f"Import prohibido detectado: {node.module}"
    
    def test_missing_files_mark_unknown_or_missing(self, tmp_path):
        """En directorio vacío, P2-C/P2-D no deben aparecer como completed."""
        provider = create_project_state_provider(repo_root=tmp_path)
        state = provider.get_p2_state()
        
        assert state.p2_c_completed is False
        assert state.p2_d_completed is False
        assert state.adapter_file_exists is False
        assert state.adapter_doc_exists is False
    
    def test_explain_curation_adapter_with_real_repo(self):
        """Con repo real que tiene P2-C, debe explicar correctamente."""
        repo_root = Path(__file__).parent.parent.parent
        provider = create_project_state_provider(repo_root=repo_root)
        
        state = provider.get_p2_state()
        
        if state.p2_c_completed:
            explanation = provider.explain_curation_adapter()
            assert "CurationValidationAdapter" in explanation
            assert "NO escribe en SemanticMemoryBridge" in explanation
            assert "NO escribe en FAISS" in explanation
        else:
            # Si no detecta, debe dar fallback
            explanation = provider.explain_curation_adapter()
            assert "No puedo confirmar" in explanation
    
    def test_explain_smoke_command_with_real_repo(self):
        """Con repo real que tiene P2-D, debe dar comando exacto."""
        repo_root = Path(__file__).parent.parent.parent
        provider = create_project_state_provider(repo_root=repo_root)
        
        state = provider.get_p2_state()
        
        if state.p2_d_completed:
            explanation = provider.explain_smoke_command()
            assert "python tests/smoke/smoke_curation_validation_adapter.py" in explanation
            assert "SMOKE_CURATION_VALIDATION_ADAPTER_OK" in explanation
        else:
            explanation = provider.explain_smoke_command()
            assert "No puedo confirmar" in explanation
    
    def test_to_dict_structure(self, tmp_path):
        """Verificar estructura del dict de estado."""
        provider = create_project_state_provider(repo_root=tmp_path)
        state = provider.get_p2_state()
        data = state.to_dict()
        
        assert "P2-A" in data
        assert "P2-B" in data
        assert "P2-C" in data
        assert "P2-D" in data
        assert "files" in data
        assert "commits" in data
        
        assert isinstance(data["P2-C"]["completed"], bool)
    
    # Tests para answer_project_state_query
    
    def test_answer_detects_p2_status(self, tmp_path):
        """answer_project_state_query detecta queries de estado P2."""
        brain_dir = tmp_path / "brain"
        tests_dir = tmp_path / "tests" / "unit"
        brain_dir.mkdir(parents=True)
        tests_dir.mkdir(parents=True)
        
        (brain_dir / "curation_validation_adapter.py").write_text("# fake")
        (tests_dir / "test_curation_validation_adapter.py").write_text("# fake")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Resume estado P2")
        assert response is not None
        assert "P2-A" in response or "P2-C" in response
    
    def test_answer_detects_adapter_query(self, tmp_path):
        """answer_project_state_query detecta queries sobre el adapter."""
        brain_dir = tmp_path / "brain"
        tests_dir = tmp_path / "tests" / "unit"
        brain_dir.mkdir(parents=True)
        tests_dir.mkdir(parents=True)
        
        (brain_dir / "curation_validation_adapter.py").write_text("# fake")
        (tests_dir / "test_curation_validation_adapter.py").write_text("# fake")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Que hace el adapter")
        assert response is not None
        assert "CurationValidationAdapter" in response
    
    def test_answer_detects_faiss_query(self, tmp_path):
        """answer_project_state_query detecta queries FAISS y niega escritura."""
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Escribe en SemanticMemoryBridge o FAISS?")
        assert response is not None
        assert "NO escribe" in response or "no escribe" in response.lower()
    
    def test_answer_detects_smoke_query(self, tmp_path):
        """answer_project_state_query detecta queries smoke y devuelve comando."""
        docs_dir = tmp_path / "docs"
        smoke_dir = tmp_path / "tests" / "smoke"
        docs_dir.mkdir(parents=True)
        smoke_dir.mkdir(parents=True)
        
        (docs_dir / "P2D_CURATION_VALIDATION_ADAPTER_USAGE.md").write_text("# fake")
        (smoke_dir / "smoke_curation_validation_adapter.py").write_text("# fake")
        
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Como pruebo localmente el smoke de P2-D?")
        assert response is not None
        assert "smoke_curation_validation_adapter.py" in response
    
    def test_answer_detects_auto_learning_query(self, tmp_path):
        """answer_project_state_query detecta queries autoaprendizaje y lo niega."""
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Puedes aprender automaticamente?")
        assert response is not None
        assert "NO hay autoaprendizaje" in response or "no hay autoaprendizaje" in response.lower()
    
    def test_answer_returns_none_for_unrelated(self, tmp_path):
        """answer_project_state_query devuelve None para pregunta no relacionada."""
        provider = create_project_state_provider(repo_root=tmp_path)
        
        response = provider.answer_project_state_query("Que hora es?")
        assert response is None
    
    def test_default_repo_root_resolves_from_module_file(self):
        """El repo root por defecto se resuelve desde la ubicacion del modulo."""
        # Crear provider SIN repo_root explicito
        provider = create_project_state_provider()
        state = provider.get_p2_state(force_refresh=True)
        
        # Verificar que apunta a AI_VAULT (o que el directorio brain existe)
        assert state.repo_root.name == "AI_VAULT" or (state.repo_root / "brain").exists(), \
            f"repo_root={state.repo_root} no apunta a AI_VAULT"
        
        # Verificar que el propio archivo del provider existe
        assert (state.repo_root / "brain" / "project_state_provider.py").exists(), \
            "El archivo project_state_provider.py debe existir en repo_root/brain/"
    
    def test_env_ai_vault_root_takes_precedence(self, monkeypatch, tmp_path):
        """AI_VAULT_ROOT env var tiene prioridad sobre __file__."""
        import os
        
        # Crear estructura fake en tmp_path
        (tmp_path / "brain").mkdir()
        (tmp_path / "brain" / "curation_validation_adapter.py").write_text("# fake")
        
        # Setear env var
        monkeypatch.setenv("AI_VAULT_ROOT", str(tmp_path))
        
        # Crear provider SIN repo_root explicito - debe usar env
        provider = create_project_state_provider()
        state = provider.get_p2_state(force_refresh=True)
        
        # Debe usar el tmp_path del env, no el repo real
        assert state.repo_root == tmp_path
        assert not state.p2_c_completed  # No hay archivos reales en tmp_path

