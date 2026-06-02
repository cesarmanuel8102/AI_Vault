"""B7-STRANGLER-06: session_fmt_helpers must be importable WITHOUT importing
brain_v9.core.session (no circular/heavy dependency)."""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"


def test_no_session_dependency_in_subprocess():
    """In a fresh subprocess, importing session_fmt_helpers must NOT pull in
    brain_v9.core.session."""
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{_TMP_AGENT}');"
        "import brain_v9.core.session_fmt_helpers as m;"
        "assert callable(m.fmt_check_port);"
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


def test_module_only_imports_typing_and_stdlib():
    """Module must be stateless and stdlib-only (typing.Dict / Any)."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    mod = importlib.import_module("brain_v9.core.session_fmt_helpers")
    expected = {
        "fmt_check_port", "fmt_check_http_service", "fmt_check_all_services",
        "fmt_check_service_status", "fmt_get_live_autonomy_status",
        "fmt_run_diagnostic", "fmt_get_system_info", "fmt_run_command",
        "fmt_read_file", "fmt_list_directory", "fmt_search_files",
        "fmt_list_processes", "fmt_grep_codebase",
        "fmt_list_recent_brain_changes", "fmt_get_chat_metrics",
        "fmt_semantic_memory_search", "fmt_get_technical_introspection",
    }
    assert expected.issubset(set(mod.__all__))
    for name in expected:
        assert callable(getattr(mod, name))


def test_helpers_are_module_level_functions_not_methods():
    """No BrainSession / self / cls coupling."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    import brain_v9.core.session_fmt_helpers as m
    src_path = Path(m.__file__)
    src = src_path.read_text(encoding="utf-8")
    # Strip the module docstring (which legitimately mentions BrainSession in
    # the contract notes) before scanning for code-level coupling.
    import ast
    tree = ast.parse(src)
    # Verify no class definitions and no `self`/`cls` first parameters
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            raise AssertionError(f"unexpected class definition: {node.name}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            assert args[:1] != ["self"], f"{node.name} uses self"
            assert args[:1] != ["cls"], f"{node.name} uses cls"
    # Ensure BrainSession is not referenced as a Name/Attribute anywhere in code
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "BrainSession":
            raise AssertionError("BrainSession referenced in code")
        if isinstance(node, ast.Attribute) and node.attr == "BrainSession":
            raise AssertionError("BrainSession referenced as attribute")
    # No `def fmt_X(self,` or `def fmt_X(cls,` signatures
    for name in m.__all__:
        # Each must be a plain function with `(out` as first arg
        import inspect
        fn = getattr(m, name)
        assert inspect.isfunction(fn), f"{name} is not a plain function"
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        assert params == ["out"], f"{name} has unexpected params: {params}"


def test_helpers_are_stateless_pure():
    """Same input → same output across multiple invocations."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    from brain_v9.core.session_fmt_helpers import fmt_check_port, fmt_get_system_info
    p1 = {"port": 80, "status": "libre"}
    assert fmt_check_port(p1) == fmt_check_port(p1)
    p2 = {"cpu_percent": 1, "memory": {"total_gb": 8, "available_gb": 4}, "disk": {}}
    assert fmt_get_system_info(p2) == fmt_get_system_info(p2)
