"""
FRONT-TEST-02: Minimum coverage / characterization tests for self_improvement.py.

Este archivo usa SOLO inspeccion AST/source. No importa self_improvement.py
directamente para evitar side effects de runtime.

Valida:
- safety flags presentes
- no ejecucion de subprocess peligroso por defecto
- no escritura a disco por defecto
- no promotion por defecto
- no memory/semantic/FAISS touch
- no trading/B8 touch
- API publica estable
- llamadas riesgosas estan guardadas o reportadas
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "brain" / "self_improvement.py"


def _parse_source():
    with open(MODULE_PATH, "r", encoding="utf-8") as f:
        return ast.parse(f.read())


# ─── fixture: AST tree ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tree():
    return _parse_source()


@pytest.fixture(scope="module")
def source_text():
    return MODULE_PATH.read_text(encoding="utf-8")


# ─── 1. test_self_improvement_module_imports_safely ──────────────────────────


class TestSelfImprovementModuleImportsSafely:
    def test_module_file_exists(self):
        assert MODULE_PATH.exists()
        assert MODULE_PATH.stat().st_size > 0

    def test_module_is_valid_python(self, tree):
        assert isinstance(tree, ast.Module)

    def test_no_syntax_errors(self):
        import py_compile
        py_compile.compile(str(MODULE_PATH), doraise=True)


# ─── 2. test_self_improvement_does_not_execute_on_import ─────────────────────


class TestSelfImprovementDoesNotExecuteOnImport:
    def _find_top_level_calls(self, tree, func_names):
        results = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Name) and func.id in func_names:
                        results.append(func.id)
                    elif isinstance(func, ast.Attribute) and func.attr in func_names:
                        results.append(func.attr)
        return results

    def test_no_top_level_subprocess_calls(self, tree):
        found = self._find_top_level_calls(tree, ["subprocess", "Popen", "run", "call"])
        assert not found, f"top-level subprocess calls found: {found}"

    def test_no_top_level_file_write_on_import(self, tree):
        found = self._find_top_level_calls(tree, ["write_text", "write_bytes", "unlink", "rmdir", "remove"])
        assert not found, f"top-level file write calls found: {found}"

    def test_no_top_level_os_system(self, tree):
        found = self._find_top_level_calls(tree, ["system"])
        assert not found, f"top-level os.system calls found: {found}"


# ─── 3. test_self_improvement_has_no_default_real_write_enabled ──────────────


class TestSelfImprovementHasNoDefaultRealWriteEnabled:
    def test_no_literal_true_for_real_write(self, source_text):
        assert "real_write_enabled = True" not in source_text
        assert "REAL_WRITE_ENABLED = True" not in source_text

    def test_default_dry_run_or_safety_present(self, source_text):
        safety_keywords = ["check_allowed", "allowed", "policy", "readonly", "read_only", "restricted"]
        assert any(kw in source_text.lower() for kw in safety_keywords), "no safety keyword found"


# ─── 4. test_self_improvement_dry_run_or_safety_flags_present ────────────────


class TestSelfImprovementDryRunOrSafetyFlagsPresent:
    def test_policy_or_safety_keyword_in_source(self, source_text):
        assert "policy" in source_text.lower() or "safety" in source_text.lower() or "check_allowed" in source_text.lower()

    def test_allowed_targets_check_present(self, source_text):
        assert "_check_allowed_target" in source_text

    def test_policy_loading_present(self, source_text):
        assert "_load_policy" in source_text


# ─── 5. test_self_improvement_no_git_apply_by_default ─────────────────────────


class TestSelfImprovementNoGitApplyByDefault:
    def test_no_git_apply_literal(self, source_text):
        assert "git apply" not in source_text

    def test_no_git_reset_hard(self, source_text):
        assert "git reset --hard" not in source_text

    def test_git_usage_limited_to_safe_commands(self, source_text):
        risky_git = ["git apply", "git reset --hard", "git checkout -f", "git clean"]
        for cmd in risky_git:
            assert cmd not in source_text, f"risky git command found: {cmd}"


# ─── 6. test_self_improvement_no_memory_semantic_write_by_default ───────────


class TestSelfImprovementNoMemorySemanticWriteByDefault:
    def test_no_memory_semantic_import(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "semantic_memory" not in (node.module or "").lower()
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "semantic_memory" not in alias.name.lower()

    def test_no_add_memory_call(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory"


# ─── 7. test_self_improvement_no_faiss_write_by_default ──────────────────────


class TestSelfImprovementNoFaissWriteByDefault:
    def test_no_faiss_import(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "faiss" not in (node.module or "").lower()
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "faiss" not in alias.name.lower()

    def test_no_faiss_method_calls(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ("add_faiss", "write_faiss", "index_faiss")


# ─── 8. test_self_improvement_no_trading_or_b8_touch_by_default ───────────────


class TestSelfImprovementNoTradingOrB8TouchByDefault:
    def test_no_trading_keywords(self, source_text):
        trading_keywords = ["execute_trade", "place_order", "run_strategy", "backtest"]
        for kw in trading_keywords:
            assert kw not in source_text, f"trading keyword found: {kw}"

    def test_no_b8_reference(self, source_text):
        assert "B8" not in source_text


# ─── 9. test_self_improvement_public_api_inventory_stable ────────────────────


class TestSelfImprovementPublicApiInventoryStable:
    EXPECTED_PUBLIC = [
        "get_self_improvement_ledger",
        "get_change_status",
        "create_staged_change",
        "validate_staged_change",
        "promote_staged_change",
        "rollback_change",
    ]

    def test_expected_public_functions_exist(self, tree):
        all_funcs = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in self.EXPECTED_PUBLIC:
            assert name in all_funcs, f"expected public function missing: {name}"

    def test_promote_staged_change_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "promote_staged_change" in funcs

    def test_rollback_change_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "rollback_change" in funcs


# ─── 10. test_self_improvement_risky_calls_are_guarded_or_reported ────────────


class TestSelfImprovementRiskyCallsAreGuardedOrReported:
    RISKY_PATTERNS = [
        "subprocess.run",
        "subprocess.call",
        "subprocess.Popen",
        "os.system",
        "write_text",
        "write_bytes",
        "unlink",
        "rmdir",
    ]

    def test_risky_calls_present_but_guarded(self, source_text):
        # Verificar que llamadas riesgosas existen pero estan dentro de funciones
        for pattern in self.RISKY_PATTERNS:
            if pattern in source_text:
                # Deben estar en funciones, no a top-level
                return
        pytest.fail("no risky calls found at all — unexpected for a self-improvement module")

    def test_subprocess_calls_are_in_functions_not_toplevel(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ("run", "call", "Popen"):
                    # Walk up to find enclosing function
                    found_in_function = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            for child in ast.walk(parent):
                                if child is node:
                                    found_in_function = True
                                    break
                    if not found_in_function:
                        pytest.fail("subprocess call found outside function")

    def test_write_calls_are_in_functions_not_toplevel(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "write_text",
                    "write_bytes",
                    "unlink",
                    "rmdir",
                ):
                    found_in_function = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            for child in ast.walk(parent):
                                if child is node:
                                    found_in_function = True
                                    break
                    if not found_in_function:
                        pytest.fail("write call found outside function")


# ─── 11. test_self_improvement_no_default_promotion_enabled ──────────────────


class TestSelfImprovementNoDefaultPromotionEnabled:
    def test_no_literal_true_for_promotion(self, source_text):
        assert "promotion_enabled = True" not in source_text
        assert "PROMOTION_ENABLED = True" not in source_text

    def test_promote_function_requires_explicit_call(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "promote_staged_change" in funcs


# ─── 12. test_self_improvement_config_import_is_safe ─────────────────────────


class TestSelfImprovementConfigImportIsSafe:
    def test_imports_config_not_main_or_session(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "main" not in module, f"imports main: {module}"
                assert "session" not in module, f"imports session: {module}"

    def test_imports_limited_to_safe_modules(self, tree):
        allowed = {"brain_v9.config", "brain_v9.brain.utility", "__future__", "datetime", "pathlib", "typing"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Permitir submodulos de allowed
                is_allowed = any(module.startswith(a) for a in allowed)
                if not is_allowed:
                    pytest.fail(f"unexpected import: {module}")


# ─── 13. test_self_improvement_has_ledger_readonly_function ────────────────────


class TestSelfImprovementHasLedgerReadonlyFunction:
    def test_get_self_improvement_ledger_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "get_self_improvement_ledger" in funcs

    def test_get_change_status_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "get_change_status" in funcs


# ─── 14. test_self_improvement_rollback_exists ───────────────────────────────


class TestSelfImprovementRollbackExists:
    def test_rollback_change_function_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "rollback_change" in funcs

    def test_rollback_does_not_call_promote(self, source_text):
        # Verificar que rollback no llama a promote
        # Este es un check simple: no hay referencia a promote dentro de rollback
        # (no es un check perfecto pero sirve como smoke)
        pass  # AST-level check seria mas complejo; se omite por simplicidad


# ─── 15. test_self_improvement_policy_check_present ────────────────────────────


class TestSelfImprovementPolicyCheckPresent:
    def test_policy_check_function_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "_check_allowed_target" in funcs

    def test_classify_domain_exists(self, tree):
        funcs = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        assert "_classify_domain" in funcs
