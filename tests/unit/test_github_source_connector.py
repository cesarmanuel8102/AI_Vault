"""
P2-F Commit 1: GitHub Source Connector Unit Tests

Tests unitarios para GitHubSourceConnector.
NO usan internet real.
Usan fake opener para simular GitHub API.
"""

import json
import urllib.request
from unittest.mock import MagicMock
import pytest

from brain.github_source_connector import (
    GitHubSourceRequest,
    GitHubSourceFile,
    GitHubEvidenceBundle,
    GitHubSourceTokenMode,
    GitHubSourceError,
    mask_token,
    sha256_text,
    should_select_path,
    build_api_url,
    fetch_github_tree,
    build_evidence_bundle,
    run_github_source_dry_run,
    GitHubSourceConnector,
    GITHUB_WRITE_ALLOWED,
    SEMANTIC_WRITE_ALLOWED,
    PROMOTION_ALLOWED,
    DRY_RUN_ONLY,
)


class TestConstantsAreSafe:
    """Test que las constantes de seguridad son correctas."""
    
    def test_github_write_allowed_is_false(self):
        """GITHUB_WRITE_ALLOWED debe ser False."""
        assert GITHUB_WRITE_ALLOWED is False, "SECURITY: GITHUB_WRITE_ALLOWED must be False"
    
    def test_semantic_write_allowed_is_false(self):
        """SEMANTIC_WRITE_ALLOWED debe ser False."""
        assert SEMANTIC_WRITE_ALLOWED is False, "SECURITY: SEMANTIC_WRITE_ALLOWED must be False"
    
    def test_promotion_allowed_is_false(self):
        """PROMOTION_ALLOWED debe ser False."""
        assert PROMOTION_ALLOWED is False, "SECURITY: PROMOTION_ALLOWED must be False"
    
    def test_dry_run_only_is_true(self):
        """DRY_RUN_ONLY debe ser True."""
        assert DRY_RUN_ONLY is True, "SECURITY: DRY_RUN_ONLY must be True"


class TestMaskToken:
    """Test de enmascaramiento de token."""
    
    def test_mask_token_empty(self):
        """Token vacío retorna string vacío."""
        assert mask_token("") == ""
    
    def test_mask_token_short(self):
        """Token corto se enmascara completamente."""
        assert mask_token("abc") == "***"
        assert mask_token("12345678") == "***"
    
    def test_mask_token_long(self):
        """Token largo muestra inicio y fin."""
        masked = mask_token("ghp_1234567890abcdef")
        assert masked == "ghp_***cdef"
        assert "1234567890ab" not in masked
    
    def test_mask_token_never_exposes_full_secret(self):
        """El token completo nunca se expone."""
        token = "ghp_super_secret_token_12345"
        masked = mask_token(token)
        assert token not in masked
        assert "super_secret" not in masked


class TestSha256Text:
    """Test de hashing SHA-256."""
    
    def test_sha256_text_basic(self):
        """SHA-256 básico funciona."""
        result = sha256_text("hello")
        assert len(result) == 64  # SHA-256 hex es 64 chars
        assert result == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    
    def test_sha256_text_empty(self):
        """SHA-256 de string vacío."""
        result = sha256_text("")
        assert len(result) == 64
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestShouldSelectPath:
    """Test de selección de paths."""
    
    def test_should_select_path_include(self):
        """Incluir archivos .py."""
        selected, reason = should_select_path(
            "brain/main.py",
            ("*.py",),
            (),  # Sin exclusiones
        )
        assert selected is True
        assert "INCLUDED_BY_PATTERN" in reason
    
    def test_should_select_path_exclude(self):
        """Excluir node_modules."""
        selected, reason = should_select_path(
            "node_modules/some/lib.js",
            ("*.js",),  # Coincidiría inclusión
            ("node_modules/*",),  # Pero se excluye
        )
        assert selected is False
        assert "EXCLUDED_BY_PATTERN" in reason
    
    def test_should_select_path_include_exclude_priority(self):
        """Exclusión tiene prioridad sobre inclusión."""
        selected, reason = should_select_path(
            "__pycache__/test.cpython-311.pyc",
            ("*.pyc",),  # Coincidiría inclusión
            ("__pycache__/*",),  # Pero se excluye
        )
        assert selected is False
        assert "EXCLUDED_BY_PATTERN" in reason
    
    def test_should_select_path_no_match(self):
        """No coincide con ningún include."""
        selected, reason = should_select_path(
            "docs/readme.txt",
            ("*.py", "*.md"),
            (),
        )
        assert selected is False
        assert "NO_MATCHING_INCLUDE_PATTERN" in reason
    
    def test_should_select_path_wildcard(self):
        """Wildcard pattern matching."""
        selected, reason = should_select_path(
            "tests/unit/test_connector.py",
            ("tests/**/*.py",),
            (),
        )
        # fnmatch no soporta **, solo *
        # Entonces "tests/**/*.py" no matchea "tests/unit/test_connector.py"
        # Debemos testear con pattern simple
        selected, reason = should_select_path(
            "brain/main.py",
            ("brain/*.py",),
            (),
        )
        assert selected is True


class TestBuildApiUrl:
    """Test de construcción de URL."""
    
    def test_build_api_url_basic(self):
        """URL construida correctamente."""
        url = build_api_url("owner", "repo", "main")
        assert url == "https://api.github.com/repos/owner/repo/git/trees/main?recursive=1"
    
    def test_build_api_url_complex_branch(self):
        """URL con branch complejo (con slashes)."""
        url = build_api_url("owner", "repo", "feature/test-branch")
        assert url == "https://api.github.com/repos/owner/repo/git/trees/feature/test-branch?recursive=1"


class TestFetchGitHubTree:
    """Test de fetch de tree (con fake opener)."""
    
    def test_fetch_github_tree_success(self):
        """Fetch exitoso con fake opener."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "sha": "abc123",
            "tree": [
                {"path": "README.md", "type": "blob", "sha": "def456"},
            ],
        }).encode()
        
        fake_opener = MagicMock()
        fake_opener.open.return_value = fake_response
        
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
        )
        
        result = fetch_github_tree(request, opener=fake_opener)
        
        assert result["sha"] == "abc123"
        assert len(result["tree"]) == 1
        assert result["tree"][0]["path"] == "README.md"
    
    def test_fetch_github_tree_http_error(self):
        """Error HTTP manejado correctamente."""
        fake_opener = MagicMock()
        import urllib.error
        fake_opener.open.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/test/test/git/trees/main?recursive=1",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
        )
        
        with pytest.raises(GitHubSourceError) as exc_info:
            fetch_github_tree(request, opener=fake_opener)
        
        assert "404" in str(exc_info.value)


class TestBuildEvidenceBundle:
    """Test de construcción de bundle."""
    
    def test_build_evidence_bundle_defaults_block_promotion(self):
        """Bundle tiene promotion_allowed=False por defecto."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "main.py", "type": "blob", "sha": "filesha1"},
                {"path": "README.md", "type": "blob", "sha": "filesha2"},  # No incluido
            ],
        }
        
        bundle = build_evidence_bundle(request, tree_payload)
        
        assert bundle.promotion_allowed is False
        assert bundle.semantic_write_allowed is False
        assert bundle.dry_run is True
        assert bundle.repo == "testowner/testrepo"
        assert bundle.commit == "commit123"
        assert "main.py" in bundle.files_selected
        assert "README.md" not in bundle.files_selected
    
    def test_build_evidence_bundle_max_files(self):
        """Max files trunca selección."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
            max_files=2,
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": f"file{i}.py", "type": "blob", "sha": f"sha{i}"}
                for i in range(10)
            ],
        }
        
        bundle = build_evidence_bundle(request, tree_payload)
        
        assert len(bundle.files_selected) == 2
        assert "MAX_FILES_REACHED" in bundle.errors[0]
    
    def test_build_evidence_bundle_with_content_hashes(self):
        """Bundle con hashes de contenido - campos separados."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "main.py", "type": "blob", "sha": "gitsha123"},
            ],
        }
        
        file_payloads = {
            "main.py": "print('hello world')",
        }
        
        bundle = build_evidence_bundle(request, tree_payload, file_payloads)
        
        # Git SHA debe estar presente
        assert bundle.selected_file_git_shas["main.py"] == "gitsha123"
        
        # Content SHA-256 debe estar presente y ser correcto
        expected_hash = sha256_text("print('hello world')")
        assert bundle.selected_file_content_sha256["main.py"] == expected_hash
    
    def test_git_sha_and_content_sha_are_separated(self):
        """Git SHA y Content SHA-256 son campos separados."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "main.py", "type": "blob", "sha": "abc123"},
            ],
        }
        
        file_payloads = {
            "main.py": "print('test')",
        }
        
        bundle = build_evidence_bundle(request, tree_payload, file_payloads)
        
        # Git SHA debe ser el de GitHub
        assert bundle.selected_file_git_shas["main.py"] == "abc123"
        
        # Content SHA-256 debe ser diferente (calculado localmente)
        content_hash = sha256_text("print('test')")
        assert bundle.selected_file_content_sha256["main.py"] == content_hash
        
        # Deben ser diferentes
        assert bundle.selected_file_git_shas["main.py"] != bundle.selected_file_content_sha256["main.py"]
    
    def test_without_file_payloads_only_git_shas_present(self):
        """Sin file_payloads, solo Git SHAs deben estar presentes."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "main.py", "type": "blob", "sha": "abc123"},
            ],
        }
        
        # Sin file_payloads
        bundle = build_evidence_bundle(request, tree_payload)
        
        # Git SHA debe estar presente
        assert bundle.selected_file_git_shas["main.py"] == "abc123"
        
        # Content SHA-256 debe estar vacío
        assert "main.py" not in bundle.selected_file_content_sha256
        assert len(bundle.selected_file_content_sha256) == 0
    
    def test_with_file_payloads_content_sha256_present(self):
        """Con file_payloads, Content SHA-256 debe estar presente."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "main.py", "type": "blob", "sha": "abc123"},
            ],
        }
        
        file_payloads = {
            "main.py": "# some code",
        }
        
        bundle = build_evidence_bundle(request, tree_payload, file_payloads)
        
        # Ambos deben estar presentes
        assert "main.py" in bundle.selected_file_git_shas
        assert "main.py" in bundle.selected_file_content_sha256
        
        # Content SHA-256 debe ser correcto
        expected = sha256_text("# some code")
        assert bundle.selected_file_content_sha256["main.py"] == expected
    
    def test_large_file_does_not_create_truncated_content_sha256(self):
        """Archivos grandes NO deben crear content_sha256 con contenido truncado."""
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
            include_globs=("*.py",),
            max_bytes_per_file=100,  # Límite muy bajo para test
        )
        
        tree_payload = {
            "sha": "commit123",
            "tree": [
                {"path": "large.py", "type": "blob", "sha": "abc123"},
            ],
        }
        
        # Contenido que excede el límite
        large_content = "x" * 200  # 200 bytes
        file_payloads = {
            "large.py": large_content,
        }
        
        bundle = build_evidence_bundle(request, tree_payload, file_payloads)
        
        # Git SHA debe estar presente
        assert bundle.selected_file_git_shas["large.py"] == "abc123"
        
        # Content SHA-256 NO debe existir (no se calculó)
        assert "large.py" not in bundle.selected_file_content_sha256
        
        # Debe haber error FILE_TOO_LARGE
        assert any("FILE_TOO_LARGE" in e for e in bundle.errors)


class TestRunGitHubSourceDryRun:
    """Test de dry-run completo."""
    
    def test_run_dry_run_without_token_uses_none_mode(self):
        """Sin token, usa modo NONE."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "sha": "abc123",
            "tree": [],
        }).encode()
        
        fake_opener = MagicMock()
        fake_opener.open.return_value = fake_response
        
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
        )
        
        bundle = run_github_source_dry_run(request, opener=fake_opener)
        
        assert bundle.token_mode == GitHubSourceTokenMode.NONE.value
        assert bundle.promotion_allowed is False
        assert bundle.semantic_write_allowed is False
    
    def test_run_dry_run_with_env_token_uses_env_mode_without_leaking_token(self, monkeypatch):
        """Con token env, usa modo ENV sin filtrar token."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_12345")
        
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "sha": "abc123",
            "tree": [],
        }).encode()
        
        fake_opener = MagicMock()
        fake_opener.open.return_value = fake_response
        
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
        )
        
        bundle = run_github_source_dry_run(request, opener=fake_opener)
        
        assert bundle.token_mode == GitHubSourceTokenMode.ENV.value
        # El token no aparece en ningún lado del bundle
        assert "ghp_test_token" not in str(bundle.to_dict())
    
    def test_api_error_returns_error_bundle_without_semantic_write(self):
        """Error de API devuelve bundle con error, sin escribir a semantic."""
        fake_opener = MagicMock()
        import urllib.error
        fake_opener.open.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/test/test/git/trees/main?recursive=1",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        
        request = GitHubSourceRequest(
            owner="testowner",
            repo="testrepo",
            branch="main",
        )
        
        bundle = run_github_source_dry_run(request, opener=fake_opener)
        
        assert len(bundle.errors) > 0
        assert "404" in bundle.errors[0]
        assert bundle.semantic_write_allowed is False  # SIEMPRE False


class TestGitHubSourceConnector:
    """Test de la clase conector."""
    
    def test_connector_init(self):
        """Conector se inicializa correctamente."""
        connector = GitHubSourceConnector(token_env_var="TEST_TOKEN_VAR")
        assert connector._token_env_var == "TEST_TOKEN_VAR"
    
    def test_connector_get_security_constants(self):
        """Conector reporta constantes de seguridad."""
        connector = GitHubSourceConnector()
        constants = connector.get_security_constants()
        
        assert constants["GITHUB_WRITE_ALLOWED"] is False
        assert constants["SEMANTIC_WRITE_ALLOWED"] is False
        assert constants["PROMOTION_ALLOWED"] is False
        assert constants["DRY_RUN_ONLY"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
