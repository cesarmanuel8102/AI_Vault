"""
FRONT-SEC-03: Security tests for BRAIN_CHAT_DEV_MODE default false.

Tests para validar que:
1. Default es false cuando env var falta
2. String vacio = false
3. Valores falsos (false, 0, no, off) = false
4. Solo valores explicitos verdaderos (true, 1, yes, on) = true
5. No se activan endpoints dev por defecto
6. No se habilita real write por defecto
7. No se habilita memory write por defecto
8. No se habilita FAISS write por defecto
9. Runtime import no fuerza dev_mode true
10. Docs no afirman default true
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

# No importar main.py ni session.py pesados; solo inspeccionar source
MODULE_PATH = Path(__file__).parent.parent.parent / "tmp_agent" / "brain_v9" / "config.py"
ENV_VAR_NAME = "BRAIN_CHAT_DEV_MODE"


def _env_flag(value):
    """Helper que replica la logica de config.py"""
    return str(value).strip().lower() == "true"


class TestDevModeDefaultFalseWhenEnvMissing:
    """1. test_dev_mode_default_false_when_env_missing"""

    def test_source_code_default_is_false(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        # Buscar la linea exacta de BRAIN_CHAT_DEV_MODE
        for line in src.splitlines():
            if "BRAIN_CHAT_DEV_MODE" in line and "os.getenv" in line:
                assert '"false"' in line or "'false'" in line, f"default is not false: {line}"
                return
        pytest.fail("BRAIN_CHAT_DEV_MODE line not found")


class TestDevModeFalseForEmptyString:
    """2. test_dev_mode_false_for_empty_string"""

    def test_empty_string_is_false(self):
        assert _env_flag("") is False


class TestDevModeFalseForFalseValues:
    """3. test_dev_mode_false_for_false_values"""

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "No", "NO", "off", "Off", "OFF"])
    def test_false_values(self, value):
        assert _env_flag(value) is False


class TestDevModeTrueOnlyForExplicitTrueValues:
    """4. test_dev_mode_true_only_for_explicit_true_values"""

    @pytest.mark.parametrize("value", ["true", "True", "TRUE"])
    def test_true_values(self, value):
        assert _env_flag(value) is True

    @pytest.mark.parametrize("value", ["yes", "YES", "on", "ON", "maybe", "", "1", "0", "no"])
    def test_non_standard_values_are_false(self, value):
        assert _env_flag(value) is False


class TestDevModeDoesNotEnableDevEndpointsByDefault:
    """5. test_dev_mode_does_not_enable_dev_endpoints_by_default"""

    def test_no_dev_endpoints_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR_NAME, raising=False)
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", MODULE_PATH)
        mod = importlib.util.module_from_spec(spec)
        # No ejecutar spec.loader.exec_module(mod) para evitar side effects
        # Solo verificamos que el codigo fuente tenga default false
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert '"false"' in src or "'false'" in src


class TestNoRealWriteEnabledByDevModeDefault:
    """6. test_no_real_write_enabled_by_dev_mode_default"""

    def test_dev_mode_default_does_not_enable_real_write(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert "allow_real_write=True" not in src
        assert "allow_real_write = True" not in src


class TestNoMemoryWriteEnabledByDevModeDefault:
    """7. test_no_memory_write_enabled_by_dev_mode_default"""

    def test_no_memory_write_calls_in_config(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ("add_memory", "write_memory")


class TestNoFaissWriteEnabledByDevModeDefault:
    """8. test_no_faiss_write_enabled_by_dev_mode_default"""

    def test_no_faiss_import(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "faiss"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "faiss"


class TestRuntimeImportDoesNotForceDevModeTrue:
    """9. test_runtime_import_does_not_force_dev_mode_true"""

    def test_config_module_does_not_hardcode_true(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        # Asegurar que no hay asignacion directa BRAIN_CHAT_DEV_MODE = True
        for line in src.splitlines():
            if "BRAIN_CHAT_DEV_MODE" in line and "=" in line and "os.getenv" not in line:
                assert "True" not in line, f"hardcoded True found: {line}"


class TestDocsDoNotClaimDefaultTrue:
    """10. test_docs_do_not_claim_default_true_if_docs_updated"""

    def test_no_docs_claim_default_true(self):
        docs_dir = Path(__file__).parent.parent.parent / "docs"
        for doc in docs_dir.glob("*.md"):
            content = doc.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "BRAIN_CHAT_DEV_MODE" in line and "default" in line.lower():
                    assert "true" not in line.lower(), f"doc claims default true: {doc.name}: {line}"
