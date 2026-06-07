"""
FRONT-SEC-01: Security tests for hardcoded approval token fix.

Tests para validar que:
1. No hay token hardcoded en el código productivo
2. La aprobación falla cerrado sin env var
3. Token incorrecto deniega
4. Token correcto aprueba
5. Se usa hmac.compare_digest
6. No se loguean tokens
7. No hay default secreto en getenv
8. No se modifica memory/semantic ni FAISS
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

try:
    from hmac import compare_digest as hmac_compare_digest
except ImportError:
    hmac_compare_digest = None

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

MODULE_PATH = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
TEST_MODULE = "brain.semantic_memory_real_write_readiness_gate"

# Avoid redacting actual env values in CI
ENV_VAR_NAME = "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN"
OLD_TOKEN_LITERAL = "CESAR_APPROVES_" + "4D_DRY_GATE_ONLY"


# ─── shared fakes ──────────────────────────────────────────────────────────────

class FakeBackupContract:
    pass


class FakeRealAdapter:
    pass


class FakeRollbackSimulation:
    pass


# 1 ── no hardcoded literal ───────────────────────────────────────────────────


class TestNoHardcodedTokenInProductiveCode:
    """1. test_no_hardcoded_token_literal_in_target_module"""

    def test_no_hardcoded_token_literal(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert OLD_TOKEN_LITERAL not in src, "old hardcoded token still present in productive module"

    def test_uses_os_getenv_not_literal(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found_getenv = False
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "getenv":
                    found_getenv = True
        assert found_getenv, "module does not use os.getenv for token"

    def test_uses_hmac_compare_digest(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        found_compare = False
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "compare_digest":
                    found_compare = True
        assert found_compare, "module does not use hmac.compare_digest"


# 2 ── missing env var fails closed ────────────────────────────────────────────


class TestMissingEnvVarFailsClosed:
    """2. test_missing_env_token_denies_approval"""

    def test_no_env_var_denies(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR_NAME, raising=False)
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        assert gate.validate_user_approval_token("anything") is False
        assert gate.validate_user_approval_token(None) is False

    def test_empty_env_var_denies(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        assert gate.validate_user_approval_token(OLD_TOKEN_LITERAL) is False


# 3 ── wrong token denied ──────────────────────────────────────────────────────


class TestWrongEnvTokenDeniesApproval:
    """3. test_wrong_env_token_denies_approval"""

    def test_wrong_token_denies(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "env_value_123")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        assert gate.validate_user_approval_token("wrong_value_456") is False


# 4 ── correct token approves ─────────────────────────────────────────────────


class TestCorrectEnvTokenApproves:
    """4. test_correct_env_token_approves"""

    def test_exact_match_approves(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "exact_match_token_001")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        assert gate.validate_user_approval_token("exact_match_token_001") is True

    def test_no_side_effects_on_real_write(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "token")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        assert gate.validate_user_approval_token("token") is True
        report = gate.evaluate_readiness(
            snapshot_id="snap",
            user_approval_token="token",
        )
        assert report.allow_real_write is False
        assert report.dry_run_only is True


# 5 ── compare_digest used ────────────────────────────────────────────────────


class TestCompareDigestUsed:
    """5. test_compare_digest_used"""

    def test_compare_digest_is_hmac(self, monkeypatch):
        called = []
        monkeypatch.setenv(ENV_VAR_NAME, "A")

        import hmac
        original = hmac.compare_digest

        def mocked(a, b):
            called.append(True)
            return original(a, b)

        monkeypatch.setattr(hmac, "compare_digest", mocked)
        mod = pytest.importorskip(TEST_MODULE)
        try:
            gate = mod.SemanticMemoryRealWriteReadinessGate()
            gate.validate_user_approval_token("A")
        finally:
            monkeypatch.undo()
        assert any(called), "hmac.compare_digest was not called"


# 6 ── no token logged ─────────────────────────────────────────────────────────


class TestNoTokenLogged:
    """6. test_no_token_logged"""

    def test_summarize_contract_does_not_expose_token(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "secret_value_123")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        summary = gate.summarize_contract()
        for v in summary.values():
            assert "secret_value_123" not in str(v), "token leaked in summary output"
        assert "env_var_name" in summary
        assert summary["token_source"] == "environment_variable"


# 7 ── no default secret ───────────────────────────────────────────────────────


class TestNoDefaultSecret:
    """7. test_no_default_secret"""

    def test_getenv_no_default_secret(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "getenv":
                    if node.args and len(node.args) >= 2:
                        default = node.args[1]
                        if isinstance(default, ast.Constant) and default.value:
                            pytest.fail("os.getenv uses a non-empty default that could be a secret")

    def test_no_approval_token_class_attribute(self):
        mod = pytest.importorskip(TEST_MODULE)
        cls = mod.SemanticMemoryRealWriteReadinessGate
        assert not hasattr(cls, "APPROVAL_TOKEN"), "old APPROVAL_TOKEN class attr still exists"


# 8 ── no memory or FAISS mutation ────────────────────────────────────────────


class TestNoMemoryOrFaissMutation:
    """8. confirm protected paths untouched"""

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
                    assert node.func.attr not in ["write_text", "write_bytes", "unlink", "remove", "rmdir"]

    def test_no_memory_semantic_import(self):
        # Check AST instead of raw text to skip comments / docstring mentions
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in [
                    "semantic_memory",
                    "semantic_memory_faiss",
                    "tmp_agent.brain_v9.core.semantic_memory",
                    "tmp_agent.brain_v9.core.semantic_memory_faiss",
                ], f"forbidden import: {node.module}"
        # raw string check dropped because docstrings mention them in comments

    def test_no_add_memory_call(self):
        src = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for node in ast.walk(src):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory"


# 9 ── behavior outside gate unchanged ──────────────────────────────────────────


class TestBehaviorOutsideApprovalGateUnchanged:
    """Verify only approval token validation changed."""

    def test_block_real_write_unchanged(self, monkeypatch):
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        report = gate.block_real_write("reason")
        assert report.allow_real_write is False
        assert report.status.value == "REAL_WRITE_BLOCKED"

    def test_dry_run_only_always_true(self, monkeypatch):
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        report = gate.evaluate_readiness(snapshot_id=None, user_approval_token=None)
        assert report.dry_run_only is True
        assert report.allow_real_write is False

    def test_missing_snapshot_not_ready(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR_NAME, raising=False)
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate()
        report = gate.evaluate_readiness(snapshot_id=None, user_approval_token=None)
        assert report.status.value == "NOT_READY"

    def test_real_write_always_false(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "token")
        mod = pytest.importorskip(TEST_MODULE)
        gate = mod.SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        report = gate.evaluate_readiness(
            snapshot_id="snap",
            user_approval_token="token",
        )
        assert report.allow_real_write is False
        assert report.status.value == "READY_BLOCKED"


# 10 ── env var name consistent ───────────────────────────────────────────────


class TestEnvVarNameConsistent:
    """Verify env var name matches design doc."""

    def test_env_var_in_module(self):
        src = MODULE_PATH.read_text(encoding="utf-8")
        assert ENV_VAR_NAME in src, "expected env var name not found in module"

    def test_env_var_in_class_attribute(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR_NAME, "x")
        mod = pytest.importorskip(TEST_MODULE)
        assert mod.SemanticMemoryRealWriteReadinessGate._ENV_VAR_NAME == ENV_VAR_NAME
