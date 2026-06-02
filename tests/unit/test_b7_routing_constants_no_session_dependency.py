"""B7-STRANGLER-04 isolation test: session_routing_constants must NOT depend on
brain_v9.core.session, BrainSession, or any ``self``/``cls`` reference.
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


class TestB7RoutingConstantsNoSessionDependency(unittest.TestCase):
    MODULE_PATH = os.path.join(
        _TMP_AGENT, "brain_v9", "core", "session_routing_constants.py"
    )

    def setUp(self):
        with open(self.MODULE_PATH, "r", encoding="utf-8") as fh:
            self.source = fh.read()

    def test_module_does_not_import_brain_v9_core_session(self):
        for line in self.source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                self.assertNotIn(
                    "brain_v9.core.session",
                    stripped,
                    f"Forbidden import of session module: {stripped!r}",
                )

    def test_module_does_not_reference_brain_session_class(self):
        import ast

        tree = ast.parse(self.source)
        body = list(tree.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        cleaned = "\n".join(ast.unparse(node) for node in body)
        for node in ast.walk(ast.parse(cleaned)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                node.value = ""
        wiped = ast.unparse(ast.parse(cleaned))
        self.assertNotIn("BrainSession", wiped)

    def test_module_has_no_self_or_cls_references(self):
        self.assertNotRegex(self.source, r"\bself\.")
        self.assertNotRegex(self.source, r"\bcls\.")

    def test_module_imports_are_minimal(self):
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
            f"Unexpected imports in session_routing_constants: {unexpected}",
        )

    def test_module_imports_in_isolation_without_session(self):
        for mod in [
            "brain_v9.core.session_routing_constants",
            "brain_v9.core.session",
        ]:
            sys.modules.pop(mod, None)
        importlib.import_module("brain_v9.core.session_routing_constants")
        self.assertNotIn(
            "brain_v9.core.session",
            sys.modules,
            "Importing session_routing_constants pulled in session.py (circular risk)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
