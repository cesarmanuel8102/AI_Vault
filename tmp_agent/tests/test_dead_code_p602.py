"""
P6-02  Dead code cleanup — Phase 6 Sprint 1.

Verifies:
 1. core/nlp.py deleted (deprecated, never imported)
 2. agent/tools_new.py deleted (duplicate of tools.py)
 3. core/conversation_memory.py deleted (deprecated, superseded by memory.py)
 4. tools.py still exists and has build_standard_executor
 5. No production imports reference deleted modules
 6. No bare except: in any brain_v9 module
"""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class TestDeadFilesDeleted:

    def test_nlp_deleted(self):
        """1. core/nlp.py should be deleted (deprecated, never imported)."""
        path = ROOT / "brain_v9" / "core" / "nlp.py"
        assert not path.exists(), f"Dead file still exists: {path}"

    def test_tools_new_deleted(self):
        """2. agent/tools_new.py should be deleted (duplicate of tools.py)."""
        path = ROOT / "brain_v9" / "agent" / "tools_new.py"
        assert not path.exists(), f"Dead file still exists: {path}"

    def test_conversation_memory_deleted(self):
        """3. core/conversation_memory.py should be deleted (deprecated)."""
        path = ROOT / "brain_v9" / "core" / "conversation_memory.py"
        assert not path.exists(), f"Dead file still exists: {path}"

    def test_tools_py_still_exists(self):
        """4. agent/tools.py (canonical) should still exist."""
        path = ROOT / "brain_v9" / "agent" / "tools.py"
        assert path.exists()

    def test_build_standard_executor_in_tools(self):
        """5. build_standard_executor is still in tools.py."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        assert "def build_standard_executor" in src


class TestNoImportsOfDeletedModules:

    @pytest.fixture(autouse=True)
    def _collect_sources(self):
        self.py_files = list((ROOT / "brain_v9").rglob("*.py"))
        assert len(self.py_files) > 10  # sanity

    def test_no_import_nlp(self):
        """6. No production module imports core.nlp."""
        for f in self.py_files:
            src = f.read_text(encoding="utf-8", errors="ignore")
            assert "from brain_v9.core.nlp" not in src, f"Stale import in {f}"
            assert "from brain_v9.core import nlp" not in src, f"Stale import in {f}"

    def test_no_import_tools_new(self):
        """7. No production module imports agent.tools_new."""
        for f in self.py_files:
            src = f.read_text(encoding="utf-8", errors="ignore")
            assert "from brain_v9.agent.tools_new" not in src, f"Stale import in {f}"
            assert "import tools_new" not in src, f"Stale import in {f}"

    def test_no_import_conversation_memory(self):
        """8. No production module imports core.conversation_memory."""
        for f in self.py_files:
            src = f.read_text(encoding="utf-8", errors="ignore")
            assert "from brain_v9.core.conversation_memory" not in src, f"Stale import in {f}"


class TestNoBareExceptInBrainV9:
    """P6-01 verification: no bare except: in any brain_v9 module."""

    def test_zero_bare_except(self):
        """9. No bare 'except:' in any brain_v9 .py file."""
        violations = []
        for f in (ROOT / "brain_v9").rglob("*.py"):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Try):
                    continue
                for handler in node.handlers:
                    if handler.type is None:
                        violations.append(f"{f.relative_to(ROOT)}:{handler.lineno}")
        assert violations == [], f"Bare except: found at: {violations}"
