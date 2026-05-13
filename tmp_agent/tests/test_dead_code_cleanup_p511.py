"""
P5-11  Dead-code cleanup — Sprint 3.

Tests that dead code was properly removed:
 1-3.  connectors.py: no duplicate except, no bare except:
 4.    sample_accumulator.py deleted (dead, never imported)
 5-7.  dashboard_professional/ deleted + refs updated
 8-12. diagnose_dashboard / start_dashboard point to :8090/ui
"""
import ast
import inspect
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# 1-3: connectors.py — no duplicate except, no bare except:
# ===========================================================================

class TestConnectorsExceptCleanup:

    @pytest.fixture(autouse=True)
    def _load_source(self):
        src = (ROOT / "brain_v9" / "trading" / "connectors.py").read_text(encoding="utf-8")
        self.source = src
        self.tree = ast.parse(src)

    def test_no_duplicate_except_exception_in_same_try(self):
        """1. Each try block has at most one 'except Exception' handler."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Try):
                continue
            exception_handlers = [
                h for h in node.handlers
                if h.type and isinstance(h.type, ast.Name) and h.type.id == "Exception"
            ]
            assert len(exception_handlers) <= 1, (
                f"Duplicate 'except Exception' at lines "
                f"{[h.lineno for h in exception_handlers]}"
            )

    def test_no_bare_except_blocks(self):
        """2. No bare 'except:' (catches SystemExit/KeyboardInterrupt)."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                assert handler.type is not None, (
                    f"Bare 'except:' found at line {handler.lineno} in connectors.py"
                )

    def test_merged_except_has_duration_fields(self):
        """3. The merged except block includes the duration/indicator fields
        that were previously only in the unreachable second block."""
        assert "selected_duration_label" in self.source
        assert "duration_candidates" in self.source
        assert "indicator_candidates" in self.source


# ===========================================================================
# 4: sample_accumulator.py — deleted
# ===========================================================================

class TestSampleAccumulatorDeleted:

    def test_file_does_not_exist(self):
        """4. brain_v9/trading/sample_accumulator.py should be deleted."""
        path = ROOT / "brain_v9" / "trading" / "sample_accumulator.py"
        assert not path.exists(), f"Dead file still exists: {path}"

    def test_real_accumulator_exists(self):
        """5. The real sample accumulator agent should still exist."""
        path = ROOT / "brain_v9" / "autonomy" / "sample_accumulator_agent.py"
        assert path.exists()


# ===========================================================================
# 5-7: dashboard_professional/ — deleted
# ===========================================================================

class TestDashboardProfessionalDeleted:

    def test_directory_does_not_exist(self):
        """6. dashboard_professional/ directory should be deleted."""
        path = ROOT / "dashboard_professional"
        assert not path.exists(), f"Dead directory still exists: {path}"

    def test_no_dashboard_professional_path_in_tools(self):
        """7. tools.py should not use dashboard_professional as a functional path."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        # Check for path assignments / os.path usage, not docstring mentions
        assert r'C:\AI_VAULT\tmp_agent\dashboard_professional' not in src
        assert 'os.path.join(dashboard_dir, "dashboard_server.py")' not in src

    def test_no_dashboard_professional_path_in_http_tools(self):
        """8. http_tools.py should not use dashboard_professional as a functional path."""
        src = (ROOT / "brain_v9" / "agent" / "http_tools.py").read_text(encoding="utf-8")
        assert r'C:\AI_VAULT\tmp_agent\dashboard_professional' not in src

    def test_no_dashboard_professional_path_in_tools_new(self):
        """9. tools_new.py was deleted in P6-02 (duplicate of tools.py)."""
        path = ROOT / "brain_v9" / "agent" / "tools_new.py"
        assert not path.exists(), f"Dead file still exists: {path}"


# ===========================================================================
# 8-12: Dashboard functions point to :8090/ui
# ===========================================================================

class TestDashboardFunctionsUpdated:

    def _extract_func_code(self, source: str, func_name: str) -> str:
        """Extract function body (code lines only, skip docstring) by parsing AST."""
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == func_name:
                lines = source.splitlines()
                # Get line range of the function body, skip the docstring
                body_start = node.body[0].end_lineno if (
                    node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Constant, ast.Str))
                ) else node.body[0].lineno - 1
                body_end = node.end_lineno
                return "\n".join(lines[body_start:body_end])
        raise ValueError(f"Function {func_name} not found")

    def test_tools_diagnose_dashboard_uses_8090(self):
        """10. diagnose_dashboard in tools.py should check port 8090, not 8070."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        code = self._extract_func_code(src, "diagnose_dashboard")
        assert "8090" in code
        assert "8070" not in code

    def test_http_tools_diagnose_dashboard_uses_8090(self):
        """11. diagnose_dashboard in http_tools.py should check port 8090, not 8070."""
        src = (ROOT / "brain_v9" / "agent" / "http_tools.py").read_text(encoding="utf-8")
        code = self._extract_func_code(src, "diagnose_dashboard")
        assert "8090" in code
        assert "8070" not in code

    def test_start_dashboard_uses_8090(self):
        """12. start_dashboard in tools.py should check port 8090, not 8070."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        code = self._extract_func_code(src, "start_dashboard")
        assert "8090" in code
        assert "8070" not in code

    def test_start_dashboard_autonomy_uses_8090(self):
        """13. start_dashboard_autonomy in tools.py should check port 8090, not 8070."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        code = self._extract_func_code(src, "start_dashboard_autonomy")
        assert "8090" in code
        assert "8070" not in code

    def test_tools_new_start_dashboard_autonomy_uses_8090(self):
        """14. tools_new.py was deleted in P6-02 (duplicate of tools.py)."""
        path = ROOT / "brain_v9" / "agent" / "tools_new.py"
        assert not path.exists(), f"Dead file still exists: {path}"

    def test_registration_descriptions_updated(self):
        """15. Tool registration descriptions should mention :8090/ui, not 8070."""
        src = (ROOT / "brain_v9" / "agent" / "tools.py").read_text(encoding="utf-8")
        for line in src.splitlines():
            if "register" in line and "diagnose_dashboard" in line:
                assert "8090" in line, f"Registration still says 8070: {line}"
                break
