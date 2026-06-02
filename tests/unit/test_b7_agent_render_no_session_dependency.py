"""B7-STRANGLER-11 no-session-dependency audit.

Verifies that the new module does NOT depend on brain_v9.core.session.
"""
import ast
import os
import subprocess
import sys

import pytest


@pytest.mark.unit
class TestAgentRenderNoSessionDependency:
    """AST + subprocess isolation checks."""

    MODULE_PATH = "tmp_agent/brain_v9/core/session_agent_render.py"

    def _ast(self):
        import pathlib
        src = pathlib.Path(self.MODULE_PATH).read_text(encoding="utf-8")
        return ast.parse(src)

    # ------------------------------------------------------------------
    # 1. AST: no import of session
    # ------------------------------------------------------------------
    def test_no_import_session(self):
        tree = self._ast()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "session" not in alias.name, f"forbidden import: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "session" not in module, f"forbidden from-import: {module}"

    def test_no_brain_session_reference(self):
        tree = self._ast()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id != "BrainSession"
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    assert node.value.id != "BrainSession"

    def test_no_self_or_cls_in_public_functions(self):
        tree = self._ast()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                args = node.args.args
                if args:
                    first = args[0].arg
                    assert first not in ("self", "cls"), (
                        f"public function {node.name} has forbidden first arg {first!r}"
                    )

    def test_no_self_or_cls_names_in_bodies(self):
        tree = self._ast()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in ("self", "cls"), (
                    f"found forbidden name {node.id!r} in AST"
                )

    # ------------------------------------------------------------------
    # 2. Subprocess: importing module does not load session
    # ------------------------------------------------------------------
    def test_subprocess_import_does_not_load_session(self):
        code = """
import sys
if 'brain_v9.core.session' in sys.modules:
    sys.modules.pop('brain_v9.core.session')

from brain_v9.core import session_agent_render as ar

loaded = 'brain_v9.core.session' in sys.modules
print("SESSION_LOADED=" + str(loaded))
"""
        env = dict(os.environ)
        env["PYTHONPATH"] = r"C:\AI_VAULT\tmp_agent"
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=r"C:\AI_VAULT",
            env=env,
        )
        output = result.stdout.strip()
        assert "SESSION_LOADED=False" in output, (
            f"session loaded unexpectedly; stdout={output!r} stderr={result.stderr!r}"
        )

    # ------------------------------------------------------------------
    # 3. Allowed imports only
    # ------------------------------------------------------------------
    def test_imports_are_allowed(self):
        tree = self._ast()
        allowed = {
            "__future__",
            "typing",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("brain_v9"):
                    assert module in allowed, f"unexpected import from {module!r}"
