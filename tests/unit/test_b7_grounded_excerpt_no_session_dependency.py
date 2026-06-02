"""B7-STRANGLER-07: session_grounded_excerpt must be importable WITHOUT importing
brain_v9.core.session (no circular/heavy dependency)."""
from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"


def test_no_session_dependency_in_subprocess():
    """In a fresh subprocess, importing session_grounded_excerpt must NOT pull in
    brain_v9.core.session."""
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{_TMP_AGENT}');"
        "import brain_v9.core.session_grounded_excerpt as m;"
        "assert callable(m.extract_symbol_hint);"
        "assert 'brain_v9.core.session' not in sys.modules, "
        "    sorted(k for k in sys.modules if k.startswith('brain_v9'));"
        "print('OK')"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0, f"stdout={res.stdout!r} stderr={res.stderr!r}"
    assert "OK" in res.stdout


def test_module_exposes_six_helpers_only():
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    mod = importlib.import_module("brain_v9.core.session_grounded_excerpt")
    expected = {
        "extract_candidate_paths",
        "extract_symbol_hint",
        "slice_lines",
        "build_grounded_file_excerpt",
        "find_test_references",
        "build_test_reference_excerpt",
    }
    for name in expected:
        assert callable(getattr(mod, name)), f"{name} missing"


def test_helpers_are_module_level_functions_not_methods():
    """No BrainSession / self / cls coupling at the *code* level.
    The module docstring may legitimately mention BrainSession; we strip it
    by walking the AST and inspecting Name/Attribute nodes only.
    """
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    import brain_v9.core.session_grounded_excerpt as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            raise AssertionError(f"unexpected class: {node.name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            assert args[:1] != ["self"], f"{node.name} uses self"
            assert args[:1] != ["cls"], f"{node.name} uses cls"
        if isinstance(node, ast.Name) and node.id == "BrainSession":
            raise AssertionError("BrainSession referenced in code (Name)")
        if isinstance(node, ast.Attribute) and node.attr == "BrainSession":
            raise AssertionError("BrainSession referenced as attribute")
    # All public helpers are plain functions
    for name in (
        "extract_candidate_paths", "extract_symbol_hint", "slice_lines",
        "build_grounded_file_excerpt", "find_test_references",
        "build_test_reference_excerpt",
    ):
        fn = getattr(m, name)
        assert inspect.isfunction(fn), f"{name} is not a plain function"


def test_helpers_pure_outputs_stable():
    """Same input → same output across multiple invocations."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    from brain_v9.core.session_grounded_excerpt import (
        extract_symbol_hint, slice_lines,
    )
    msg = "revisa `foo_bar` por favor"
    assert extract_symbol_hint(msg) == extract_symbol_hint(msg) == "foo_bar"
    lines = ["x", "y", "z"]
    assert slice_lines(lines, 1, 1) == slice_lines(lines, 1, 1)
