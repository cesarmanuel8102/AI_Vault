"""B7-STRANGLER-09: AST guard — session_tool_analysis_prefs has no session dependency.

Verifies that the extracted module:

* Does not import (directly or via ``from``) ``brain_v9.core.session``.
* Does not reference ``BrainSession`` as a name anywhere in its AST.
* No public function takes ``self`` or ``cls`` as its first parameter.
* No function body uses ``self`` or ``cls`` as a free name.
* All imports come from the allow-list:
    - ``__future__``
    - ``re``
    - ``brain_v9.core.session_routing_constants``

Also checks at runtime that importing the module does NOT pull
``brain_v9.core.session`` into ``sys.modules`` if it was not already loaded.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

_MODULE_PATH = _TMP_AGENT / "brain_v9" / "core" / "session_tool_analysis_prefs.py"

ALLOWED_IMPORT_PREFIXES = (
    "__future__",
    "re",
    "brain_v9.core.session_routing_constants",
)


def _load_ast() -> ast.Module:
    src = _MODULE_PATH.read_text(encoding="utf-8")
    return ast.parse(src, filename=str(_MODULE_PATH))


# ── Static (AST) checks ─────────────────────────────────────────────────────


def test_module_file_exists():
    assert _MODULE_PATH.exists(), f"missing: {_MODULE_PATH}"


def test_no_import_of_session_module():
    tree = _load_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "brain_v9.core.session", (
                    f"forbidden absolute import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod != "brain_v9.core.session", (
                f"forbidden from-import: from {mod} import ..."
            )


def test_no_reference_to_brain_session_name():
    tree = _load_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "BrainSession", (
                "session_tool_analysis_prefs must not reference BrainSession"
            )
        if isinstance(node, ast.Attribute):
            assert node.attr != "BrainSession", (
                "session_tool_analysis_prefs must not reference BrainSession via attribute"
            )


def test_public_functions_have_no_self_or_cls_first_param():
    tree = _load_ast()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            args = node.args.args
            if args:
                first = args[0].arg
                assert first not in ("self", "cls"), (
                    f"public function {node.name!r} has '{first}' first arg"
                )


def test_no_self_or_cls_in_function_bodies():
    tree = _load_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in ("self", "cls"):
                    raise AssertionError(
                        f"function {node.name!r} references free name "
                        f"{sub.id!r} (line {sub.lineno})"
                    )


def test_imports_only_from_allowlist():
    tree = _load_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert any(alias.name == p or alias.name.startswith(p + ".")
                           for p in ALLOWED_IMPORT_PREFIXES), (
                    f"disallowed import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert any(mod == p or mod.startswith(p + ".")
                       for p in ALLOWED_IMPORT_PREFIXES), (
                f"disallowed from-import: from {mod} import ..."
            )


# ── Runtime check: importing the module does not load session ───────────────


def test_importing_module_does_not_load_session():
    code = (
        "import sys; "
        f"sys.path.insert(0, r'{_TMP_AGENT}'); "
        "import brain_v9.core.session_tool_analysis_prefs as tap; "
        "loaded_session = 'brain_v9.core.session' in sys.modules; "
        "print('SESSION_LOADED:', loaded_session)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "SESSION_LOADED: False" in result.stdout, (
        f"session module was unexpectedly loaded; stdout={result.stdout!r}"
    )


def test_module_importable_directly():
    mod = importlib.import_module("brain_v9.core.session_tool_analysis_prefs")
    assert callable(mod.prefers_no_tool_analysis)
    assert callable(mod.has_explicit_tool_target)
    assert set(mod.__all__) == {"prefers_no_tool_analysis", "has_explicit_tool_target"}
