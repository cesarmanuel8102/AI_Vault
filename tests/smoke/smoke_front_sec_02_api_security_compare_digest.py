"""
FRONT-SEC-02: Security tests for timing attack hardening in api_security.py.

Tests para validar que:
1. Se usa hmac.compare_digest para comparar secretos
2. No hay comparaciones directas == o != con secretos/tokens/passwords
3. Token ausente falla cerrado
4. Token incorrecto deniega
5. Token correcto aprueba
6. No se loguean tokens, passwords ni headers de Authorization
7. No hay secretos por defecto hardcoded
8. No se modifica memory/semantic ni FAISS
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

MODULE_PATH = Path(__file__).parent.parent.parent / "tmp_agent" / "brain_v9" / "api_security.py"
TEST_MODULE = "tmp_agent.brain_v9.api_security"
ENV_VAR_NAME = "BRAIN_ADMIN_TOKEN"


class TestApiSecurityImports:
    """1. test_api_security_imports"""

    def test_imports_hmac(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(src):
            if isinstance(node, ast.ImportFrom):
                if node.module == "hmac":
                    found = True
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "hmac":
                        found = True
        assert found, "api_security.py does not import hmac"


class TestApiSecurityUsesHmacCompareDigest:
    """2. test_api_security_uses_hmac_compare_digest"""

    def test_compare_digest_called(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "compare_digest":
                    found = True
                elif isinstance(func, ast.Name) and func.id == "compare_digest":
                    found = True
        assert found, "api_security.py does not call compare_digest"


class TestNoDirectSecretEqualityComparison:
    """3. test_no_direct_secret_equality_comparison"""

    def test_no_double_equals_with_token(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Compare):
                if any(isinstance(op, ast.Eq) for op in node.ops):
                    for comparator in node.comparators:
                        if isinstance(comparator, ast.Name) and comparator.id in (
                            "expected",
                            "x_brain_token",
                        ):
                            pytest.fail("found == comparison involving secret variable")

    def test_no_not_equals_with_token(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Compare):
                if any(isinstance(op, ast.NotEq) for op in node.ops):
                    for comparator in node.comparators:
                        if isinstance(comparator, ast.Name) and comparator.id in (
                            "expected",
                            "x_brain_token",
                        ):
                            pytest.fail("found != comparison involving secret variable")


class TestMissingExpectedSecretFailsClosed:
    """4. test_missing_expected_secret_fails_closed"""

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR_NAME, raising=False)
        mod = pytest.importorskip(TEST_MODULE)
        import asyncio

        class FakeRequest:
            client = None

        with pytest.raises(Exception):
            asyncio.run(mod.require_strict_operator_access(FakeRequest(), "anything"))


class TestWrongSecretDenied:
    """5. test_wrong_secret_denied"""

    def test_wrong_token_denies(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "correct_secret_123")
        mod = pytest.importorskip(TEST_MODULE)
        import asyncio

        class FakeRequest:
            client = None

        with pytest.raises(Exception):
            asyncio.run(mod.require_strict_operator_access(FakeRequest(), "wrong_secret_456"))


class TestCorrectSecretAccepted:
    """6. test_correct_secret_accepted"""

    def test_correct_token_accepts(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "correct_secret_123")
        mod = pytest.importorskip(TEST_MODULE)
        import asyncio

        class FakeRequest:
            client = None

        # Should not raise
        asyncio.run(mod.require_strict_operator_access(FakeRequest(), "correct_secret_123"))


class TestNoSecretLogged:
    """7. test_no_secret_logged"""

    def test_no_print_or_log_of_token(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("print", "log"):
                    for arg in node.args:
                        if isinstance(arg, ast.Name) and arg.id in (
                            "expected",
                            "x_brain_token",
                        ):
                            pytest.fail("secret variable passed to print/log")


class TestNoAuthorizationValueLogged:
    """8. test_authorization_header_not_logged"""

    def test_no_authorization_in_logs(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("print", "log"):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and "authorization" in str(
                            arg.value
                        ).lower():
                            pytest.fail("authorization header logged")


class TestNoDefaultSecretLiteral:
    """9. test_no_default_secret_literal"""

    def test_getenv_no_default_secret(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "getenv":
                    if node.args and len(node.args) >= 2:
                        default = node.args[1]
                        if isinstance(default, ast.Constant) and default.value:
                            pytest.fail("os.getenv uses non-empty default that could be a secret")


class TestNoMemoryOrFaissMutation:
    """10. confirm protected paths untouched"""

    def test_no_faiss_import(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "faiss"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "faiss"

    def test_no_write_text_write_bytes_open(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in ["open"]
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in [
                        "write_text",
                        "write_bytes",
                        "unlink",
                        "remove",
                        "rmdir",
                    ]

    def test_no_memory_semantic_import(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert "memory/semantic" not in src
        assert "semantic_memory" not in src

    def test_no_add_memory_call(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory"


class TestExistingStatusCodePreserved:
    """11. test_existing_status_code_preserved_if_applicable"""

    def test_403_status_code_preserved(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "HTTPException":
                    for keyword in node.keywords:
                        if keyword.arg == "status_code":
                            if isinstance(keyword.value, ast.Constant):
                                assert keyword.value.value == 403

    def test_local_bypass_unchanged(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(src):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "require_operator_access":
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name) and child.func.id == "compare_digest":
                            found = True
                            break
                        elif isinstance(child.func, ast.Attribute) and child.func.attr == "compare_digest":
                            found = True
                            break
        assert found, "require_operator_access lost compare_digest usage"
