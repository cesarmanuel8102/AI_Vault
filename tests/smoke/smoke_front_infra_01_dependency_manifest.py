"""
FRONT-INFRA-01: Minimal dependency manifest validation smoke test.

Valida que requirements.txt existe, no está vacío, contiene las
dependencias third-party mínimas detectadas por inventory, y no
contiene secretos, rutas locales, URLs de git ni paquetes peligrosos.

No instala paquetes. Solo inspección de archivos.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
INVENTORY_PATH = REPO_ROOT / "tmp_agent" / "front_infra_01" / "dependency_inventory.json"


@pytest.fixture(scope="module")
def requirements_text():
    assert REQUIREMENTS_PATH.exists(), "requirements.txt not found"
    return REQUIREMENTS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def inventory():
    assert INVENTORY_PATH.exists(), "dependency_inventory.json not found"
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


# 1 ── file exists ────────────────────────────────────────────────────────────
class TestRequirementsFileExists:
    def test_requirements_file_exists(self):
        assert REQUIREMENTS_PATH.exists(), "requirements.txt not found"

# 2 ── not empty ──────────────────────────────────────────────────────────────
class TestRequirementsNotEmpty:
    def test_requirements_not_empty(self, requirements_text):
        assert requirements_text.strip(), "requirements.txt is empty"

# 3 ── fastapi present ────────────────────────────────────────────────────────
class TestRequirementsContainsFastapiIfFastapiImported:
    def test_requirements_contains_fastapi(self, requirements_text, inventory):
        if "fastapi" in inventory.get("third_party", []):
            assert "fastapi" in requirements_text.lower(), "fastapi missing from requirements"

# 4 ── uvicorn present ───────────────────────────────────────────────────────
class TestRequirementsContainsUvicornIfUvicornImported:
    def test_requirements_contains_uvicorn(self, requirements_text, inventory):
        if "uvicorn" in inventory.get("third_party", []):
            assert "uvicorn" in requirements_text.lower(), "uvicorn missing from requirements"

# 5 ── pydantic present ──────────────────────────────────────────────────────
class TestRequirementsContainsPydanticIfPydanticImported:
    def test_requirements_contains_pydantic(self, requirements_text, inventory):
        if "pydantic" in inventory.get("third_party", []):
            assert "pydantic" in requirements_text.lower(), "pydantic missing from requirements"

# 6 ── pytest present ────────────────────────────────────────────────────────
class TestRequirementsContainsPytestForTests:
    def test_requirements_contains_pytest(self, requirements_text):
        assert "pytest" in requirements_text.lower(), "pytest missing from requirements"

# 7 ── no obvious secrets ────────────────────────────────────────────────────
class TestRequirementsHasNoObviousSecrets:
    def test_no_api_keys(self, requirements_text):
        secret_keywords = ["api_key", "apikey", "secret", "password", "token", "bearer"]
        for kw in secret_keywords:
            assert kw not in requirements_text.lower(), f"possible secret keyword: {kw}"

# 8 ── no local paths ─────────────────────────────────────────────────────────
class TestRequirementsHasNoLocalPaths:
    def test_no_file_paths(self, requirements_text):
        assert "file://" not in requirements_text, "local file path in requirements"
        assert "C:/" not in requirements_text, "windows path in requirements"

# 9 ── no git URLs ───────────────────────────────────────────────────────────
class TestRequirementsHasNoGitUrls:
    def test_no_git_urls(self, requirements_text):
        assert "git+" not in requirements_text, "git URL in requirements"
        assert "github.com" not in requirements_text, "github.com URL in requirements"

# 10 ── no dangerous packages ─────────────────────────────────────────────────
class TestRequirementsHasNoDangerousPackages:
    def test_no_dangerous_packages(self, requirements_text):
        dangerous = ["rm -rf", "eval", "exec", "subprocess"]
        for pkg in dangerous:
            assert pkg not in requirements_text.lower(), f"dangerous reference: {pkg}"

# 11 ── inventory schema ──────────────────────────────────────────────────────
class TestDependencyInventorySchema:
    def test_inventory_has_required_fields(self, inventory):
        for field in ("third_party", "stdlib", "local"):
            assert field in inventory, f"missing field: {field}"

# 12 ── manifest covers detected third-party minimally ──────────────────────────
class TestManifestCoversDetectedThirdPartyImportsMinimally:
    def test_manifest_covers_third_party(self, requirements_text, inventory):
        third_party = set(inventory.get("third_party", []))
        for pkg in third_party:
            pkg_name = pkg.replace("_", "-").lower()
            assert pkg_name in requirements_text.lower(), f"third-party pkg not in requirements: {pkg}"

# 13 ── textual not included unless detected ──────────────────────────────────
class TestManifestDoesNotIncludeUndetectedTextualUnlessImported:
    def test_no_textual_unless_in_inventory(self, requirements_text, inventory):
        has_textual = "textual" in requirements_text.lower()
        detected = "textual" in [p.lower() for p in inventory.get("third_party", [])]
        if has_textual:
            assert detected, "textual in requirements but not detected in inventory"

# 14 ── faiss-cpu for faiss import ────────────────────────────────────────────
class TestManifestUsesFaissCpuIfFaissImported:
    def test_faiss_cpu_used(self, requirements_text, inventory):
        third_party = [p.lower() for p in inventory.get("third_party", [])]
        if "faiss" in third_party:
            assert "faiss-cpu" in requirements_text.lower(), "faiss import requires faiss-cpu in requirements"
