"""B7-STRANGLER-03 isolation test: session_query_predicates must NOT depend on
brain_v9.core.session, BrainSession, or any ``self``/``cls`` reference.

This guards against regressions where someone re-introduces a circular import
or class coupling.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_TMP_AGENT = os.path.join(_REPO_ROOT, "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)


class TestB7QueryPredicatesNoSessionDependency(unittest.TestCase):
    MODULE_PATH = os.path.join(
        _TMP_AGENT, "brain_v9", "core", "session_query_predicates.py"
    )

    def setUp(self):
        with open(self.MODULE_PATH, "r", encoding="utf-8") as fh:
            self.source = fh.read()

    def test_module_does_not_import_brain_v9_core_session(self):
        # Reject any direct import of brain_v9.core.session.
        # Tolerate occurrences inside docstrings/comments by checking only
        # actual import statements line-by-line.
        for line in self.source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                self.assertNotIn(
                    "brain_v9.core.session",
                    stripped,
                    f"Forbidden import of session module: {stripped!r}",
                )

    def test_module_does_not_reference_brain_session_class(self):
        # Strip module docstring and comments so prose mentions of BrainSession
        # in the header do not trip this check. We only care that the executable
        # code does not depend on / reference the BrainSession class.
        import ast

        tree = ast.parse(self.source)
        # Drop module docstring (first Expr/Constant) if present.
        body = list(tree.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        cleaned = "\n".join(ast.unparse(node) for node in body)
        # Remove any inline string literals (function docstrings) by re-walking.
        for node in ast.walk(ast.parse(cleaned)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Wipe string constants from the textual check space by
                # replacing them with empty placeholders.
                node.value = ""
        wiped = ast.unparse(ast.parse(cleaned))
        self.assertNotIn("BrainSession", wiped)

    def test_module_has_no_self_or_cls_references(self):
        # Ignore docstrings/comments by stripping them before regex check.
        # Simple approach: just ensure the tokens self. and cls. don't appear.
        self.assertNotRegex(self.source, r"\bself\.")
        self.assertNotRegex(self.source, r"\bcls\.")

    def test_module_imports_are_minimal(self):
        # Allowed imports: __future__, re. Anything else should be flagged
        # explicitly so reviewers notice scope creep.
        allowed_top = {"__future__", "re"}
        observed_top = set()
        for line in self.source.splitlines():
            m = re.match(r"^\s*from\s+(\S+)\s+import\b", line)
            if m:
                observed_top.add(m.group(1).split(".")[0])
                continue
            m = re.match(r"^\s*import\s+(\S+)", line)
            if m:
                observed_top.add(m.group(1).split(".")[0])
        unexpected = observed_top - allowed_top
        self.assertFalse(
            unexpected,
            f"Unexpected imports in session_query_predicates: {unexpected}",
        )

    def test_module_imports_in_isolation_without_session(self):
        # Import the module in a fresh state and ensure
        # brain_v9.core.session is NOT loaded as a side-effect.
        for mod in [
            "brain_v9.core.session_query_predicates",
            "brain_v9.core.session",
        ]:
            sys.modules.pop(mod, None)
        importlib.import_module("brain_v9.core.session_query_predicates")
        self.assertNotIn(
            "brain_v9.core.session",
            sys.modules,
            "Importing session_query_predicates pulled in session.py (circular risk)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
