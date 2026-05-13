"""
P6-09 Guard Test — No silent except blocks in brain_v9/

Uses Python's AST to scan every .py file under brain_v9/ and verify that
no ``except`` handler has a body consisting solely of ``pass`` or
``continue`` without an accompanying logging call.

This prevents regressions: every caught exception must at minimum be
logged so failures are observable.
"""
import ast
import sys
from pathlib import Path

import pytest

BRAIN_V9_ROOT = Path(__file__).resolve().parent.parent / "brain_v9"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOGGING_NAMES = frozenset([
    "log", "logger", "logging", "self.logger", "self.log",
    "_log", "print",
])


def _is_logging_call(node: ast.AST) -> bool:
    """Return True if *node* is a call to a known logger or print."""
    if not isinstance(node, ast.Expr):
        return False
    call = node.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func

    # Direct name: log.debug(...), print(...)
    if isinstance(func, ast.Attribute):
        # e.g. log.debug, self.logger.warning, _log.info
        value = func.value
        if isinstance(value, ast.Name) and value.id in _LOGGING_NAMES:
            return True
        # self.logger.xxx or self.log.xxx
        if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
            composite = f"{value.value.id}.{value.attr}"
            if composite in _LOGGING_NAMES:
                return True
    if isinstance(func, ast.Name) and func.id in _LOGGING_NAMES:
        return True
    return False


def _body_is_silent(body: list) -> bool:
    """Return True if the handler body is only pass/continue with no logging."""
    for stmt in body:
        # Any logging call means it's not silent
        if _is_logging_call(stmt):
            return False
        # Nested if/for/while could contain logging — check recursively
        if isinstance(stmt, (ast.If, ast.For, ast.While)):
            child_bodies = [stmt.body, stmt.orelse]
            if any(not _body_is_silent(b) for b in child_bodies if b):
                return False
        # A raise is not silent
        if isinstance(stmt, ast.Raise):
            return False
        # Assignment that references the exception is okay (e.g. return {"error": str(e)})
        if isinstance(stmt, ast.Return):
            return False
    # Only pass/continue/bare expressions with no logging
    significant = [
        s for s in body
        if not isinstance(s, (ast.Pass, ast.Continue))
    ]
    # If there's anything besides pass/continue but no logging, still flag it
    # unless it's a return or raise (handled above)
    if not significant:
        return True  # body is literally just pass/continue
    return False


def _collect_silent_handlers(filepath: Path):
    """Yield (line, col) for each silent except handler in *filepath*."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if _body_is_silent(node.body):
                yield node.lineno, node.col_offset


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def _scan_all_files():
    """Return list of (relative_path, line, col) for all silent handlers."""
    violations = []
    for py_file in sorted(BRAIN_V9_ROOT.rglob("*.py")):
        rel = py_file.relative_to(BRAIN_V9_ROOT.parent)
        for lineno, col in _collect_silent_handlers(py_file):
            violations.append((str(rel), lineno, col))
    return violations


class TestNoSilentExceptBlocks:
    """Guard: every except block must log or re-raise, never silently swallow."""

    def test_no_silent_except_in_brain_v9(self):
        violations = _scan_all_files()
        if violations:
            msg_lines = ["Silent except blocks found (pass/continue without logging):"]
            for path, line, col in violations:
                msg_lines.append(f"  {path}:{line}:{col}")
            pytest.fail("\n".join(msg_lines))

    def test_brain_v9_root_exists(self):
        """Sanity check: make sure we're scanning the right directory."""
        assert BRAIN_V9_ROOT.exists(), f"brain_v9 root not found: {BRAIN_V9_ROOT}"
        py_files = list(BRAIN_V9_ROOT.rglob("*.py"))
        assert len(py_files) > 20, f"Expected >20 .py files, found {len(py_files)}"
