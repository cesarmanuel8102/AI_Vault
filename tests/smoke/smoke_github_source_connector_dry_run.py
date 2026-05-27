"""
P2-F Commit 1: GitHub Source Connector Smoke Test - Dry Run

Valida que el conector GitHub:
- Ejecuta dry-run correctamente
- Nunca escribe a SemanticMemory
- Mantiene promotion_allowed=False
- Produce evidence bundle válido
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.github_source_connector import (
    GitHubSourceRequest,
    GitHubEvidenceBundle,
    GitHubSourceConnector,
    GITHUB_WRITE_ALLOWED,
    SEMANTIC_WRITE_ALLOWED,
    PROMOTION_ALLOWED,
    DRY_RUN_ONLY,
)


def create_fake_tree_payload():
    """Crear payload fake de GitHub tree API."""
    return {
        "sha": "test_commit_abc123",
        "tree": [
            {"path": "README.md", "type": "blob", "sha": "sha_readme", "size": 1000},
            {"path": "brain/main.py", "type": "blob", "sha": "sha_main", "size": 5000},
            {"path": "docs/guide.md", "type": "blob", "sha": "sha_guide", "size": 2000},
            {"path": "tests/unit/test.py", "type": "blob", "sha": "sha_test", "size": 1500},
            {"path": ".gitignore", "type": "blob", "sha": "sha_gitignore", "size": 100},
            {"path": "node_modules/lib/index.js", "type": "blob", "sha": "sha_node", "size": 10000},
            {"path": "__pycache__/cache.pyc", "type": "blob", "sha": "sha_cache", "size": 500},
        ],
    }


class FakeOpener:
    """Opener fake para simular GitHub API."""
    
    def __init__(self, response_payload):
        self._response_payload = response_payload
    
    def open(self, request):
        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload
            
            def read(self):
                import json
                return json.dumps(self._payload).encode("utf-8")
        
        return FakeResponse(self._response_payload)


def test_smoke_dry_run():
    """Smoke test: dry run completo."""
    print("=" * 60)
    print("SMOKE TEST: GitHub Source Connector Dry Run")
    print("=" * 60)
    
    # 1. Verificar constantes de seguridad
    print("\n[1] Verificando constantes de seguridad...")
    assert GITHUB_WRITE_ALLOWED is False, "GITHUB_WRITE_ALLOWED must be False"
    assert SEMANTIC_WRITE_ALLOWED is False, "SEMANTIC_WRITE_ALLOWED must be False"
    assert PROMOTION_ALLOWED is False, "PROMOTION_ALLOWED must be False"
    assert DRY_RUN_ONLY is True, "DRY_RUN_ONLY must be True"
    print("   [OK] Constantes de seguridad OK")
    
    # 2. Crear conector
    print("\n[2] Creando conector...")
    connector = GitHubSourceConnector()
    constants = connector.get_security_constants()
    assert constants["GITHUB_WRITE_ALLOWED"] is False
    assert constants["SEMANTIC_WRITE_ALLOWED"] is False
    assert constants["PROMOTION_ALLOWED"] is False
    assert constants["DRY_RUN_ONLY"] is True
    print("   [OK] Conector creado con seguridad OK")
    
    # 3. Crear request
    print("\n[3] Configurando request...")
    request = GitHubSourceRequest(
        owner="cesarmanuel8102",
        repo="AI_Vault",
        branch="codex/own-capital-sustainable-return",
        include_globs=("*.py", "*.md"),
        exclude_globs=("node_modules/*", "__pycache__/*"),
        max_files=10,
    )
    print(f"   Owner: {request.owner}")
    print(f"   Repo: {request.repo}")
    print(f"   Branch: {request.branch}")
    print(f"   Include: {request.include_globs}")
    print(f"   Exclude: {request.exclude_globs}")
    
    # 4. Ejecutar dry-run con fake opener
    print("\n[4] Ejecutando dry-run (con fake opener)...")
    fake_payload = create_fake_tree_payload()
    fake_opener = FakeOpener(fake_payload)
    
    bundle = connector.inspect(request, opener=fake_opener)
    
    # 5. Validar bundle
    print("\n[5] Validando evidence bundle...")
    
    # Security checks
    assert bundle.promotion_allowed is False, "promotion_allowed must be False"
    assert bundle.semantic_write_allowed is False, "semantic_write_allowed must be False"
    assert bundle.dry_run is True, "dry_run must be True"
    assert bundle.token_mode in ["none", "env"], "token_mode must be none or env"
    print("   [OK] Security flags OK")
    
    # Content checks
    assert bundle.source_type == "github", "source_type must be 'github'"
    assert bundle.repo == "cesarmanuel8102/AI_Vault", f"repo mismatch: {bundle.repo}"
    assert bundle.branch == "codex/own-capital-sustainable-return", f"branch mismatch: {bundle.branch}"
    assert bundle.files_seen == 7, f"files_seen should be 7, got {bundle.files_seen}"
    print("   [OK] Files seen: {bundle.files_seen}")
    
    # Selected files
    print(f"\n   Files selected ({len(bundle.files_selected)}):")
    for path in bundle.files_selected:
        print(f"     - {path}")
    
    # Should include .py and .md files, exclude node_modules and __pycache__
    expected_selected = ["README.md", "brain/main.py", "docs/guide.md", "tests/unit/test.py"]
    for expected in expected_selected:
        assert expected in bundle.files_selected, f"Expected file {expected} not selected"
    
    # Should NOT include excluded patterns
    assert "node_modules/lib/index.js" not in bundle.files_selected, "node_modules should be excluded"
    assert "__pycache__/cache.pyc" not in bundle.files_selected, "__pycache__ should be excluded"
    print("   [OK] Inclusion/exclusion patterns OK")
    
    # Hashes - Git SHAs (desde API tree, no hay file_payloads)
    print(f"\n   Git SHAs ({len(bundle.selected_file_git_shas)}):")
    for path, hash_val in list(bundle.selected_file_git_shas.items())[:3]:
        print(f"     - {path}: {hash_val[:16]}...")
    
    # Verificar que todos los archivos seleccionados tienen Git SHA
    assert len(bundle.selected_file_git_shas) == len(bundle.files_selected), "Git SHA count mismatch"
    
    # Verificar que Content SHA-256 está vacío (no hay file_payloads en este test)
    assert len(bundle.selected_file_content_sha256) == 0, "Content SHA256 should be empty without file payloads"
    
    print("   [OK] Git SHAs OK (Content SHA-256 empty as expected)")
    
    # Bundle to_dict
    print("\n[6] Validando serialización...")
    bundle_dict = bundle.to_dict()
    assert bundle_dict["source_type"] == "github"
    assert bundle_dict["promotion_allowed"] is False
    assert bundle_dict["semantic_write_allowed"] is False
    assert bundle_dict["dry_run"] is True
    print("   [OK] Serialización OK")
    
    # 7. Verificar NO memory/semantic write
    print("\n[7] Verificando NO escritura a SemanticMemory...")
    # El bundle NO debe contener referencias a semantic_memory
    assert "semantic_memory" not in str(bundle_dict).lower(), "Bundle should not reference semantic_memory"
    print("   [OK] NO SemanticMemory references OK")
    
    # 8. Verificar NO GitHub write capability
    print("\n[8] Verificando NO GitHub write capability...")
    assert GITHUB_WRITE_ALLOWED is False, "GITHUB_WRITE_ALLOWED must remain False"
    print("   [OK] NO GitHub write capability OK")
    
    print("\n" + "=" * 60)
    print("SMOKE_GITHUB_SOURCE_CONNECTOR_DRY_RUN_OK")
    print("=" * 60)
    
    return True


def main():
    """Entry point."""
    try:
        test_smoke_dry_run()
        print("\n[OK] All smoke tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n[FAIL] Smoke test FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Smoke test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
