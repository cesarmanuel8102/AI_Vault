"""
P6-10  Retired port 8070 cleanup — Phase 6.

Verifies that no functional code in brain_v9 still references the retired
port 8070.  Comments that *explain* the retirement ("port 8070 retired") are
acceptable; what matters is that no URL, port number, or service dict still
routes traffic to that port.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
B9 = ROOT / "brain_v9"

# Files that were cleaned in P6-10
_CRITICAL_FILES = [
    "agent/tools.py",
    "core/session.py",
    "core/self_diagnostic.py",
    "config.py",
    "agent/http_tools.py",
    "brain/health.py",
]


def _read(relpath: str) -> str:
    return (B9 / relpath).read_text(encoding="utf-8")


# ===================================================================
# 1. No functional 8070 URLs anywhere in brain_v9
# ===================================================================

class TestNoFunctional8070URLs:
    """No file should make HTTP requests to localhost:8070."""

    @pytest.fixture(autouse=True)
    def _collect_py_files(self):
        self.py_files = sorted(B9.rglob("*.py"))

    def test_no_http_request_to_8070(self):
        """No Python file should contain a URL with port 8070."""
        # Match http://...:8070 patterns (functional URLs)
        pattern = re.compile(r"http[s]?://[^\"'\s]*:8070")
        violations = []
        for f in self.py_files:
            src = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(src.splitlines(), 1):
                # Skip pure comments
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if pattern.search(line):
                    violations.append(f"{f.relative_to(B9)}:{i}: {line.strip()}")
        assert not violations, (
            f"Found {len(violations)} functional URL(s) with port 8070:\n"
            + "\n".join(violations)
        )


# ===================================================================
# 2. Service dicts don't list 8070
# ===================================================================

class TestServiceDictsClean:

    def test_tools_check_service_status_no_8070(self):
        src = _read("agent/tools.py")
        # Find the check_service_status function and verify no 8070
        match = re.search(
            r"async def check_service_status.*?(?=\nasync def |\nclass |\ndef |\Z)",
            src, re.DOTALL,
        )
        assert match, "check_service_status function not found"
        assert "8070" not in match.group()

    def test_tools_stop_service_no_8070(self):
        src = _read("agent/tools.py")
        match = re.search(
            r"async def stop_service.*?(?=\nasync def |\nclass |\ndef |\Z)",
            src, re.DOTALL,
        )
        assert match, "stop_service function not found"
        assert "8070" not in match.group()

    def test_tools_check_all_services_no_8070(self):
        src = _read("agent/tools.py")
        match = re.search(
            r"async def check_all_services.*?(?=\nasync def |\nclass |\ndef |\Z)",
            src, re.DOTALL,
        )
        assert match, "check_all_services function not found"
        assert "8070" not in match.group()

    def test_health_py_no_8070(self):
        src = _read("brain/health.py")
        assert "8070" not in src


# ===================================================================
# 3. Dashboard fastpath points to 8090
# ===================================================================

class TestDashboardFastpath:

    def test_session_fastpath_checks_8090(self):
        src = _read("core/session.py")
        match = re.search(
            r"def _dashboard_status_fastpath.*?(?=\n    def |\Z)",
            src, re.DOTALL,
        )
        assert match, "_dashboard_status_fastpath not found"
        body = match.group()
        # The function uses SERVER_PORT variable (=8090), not the literal "8090"
        assert "SERVER_PORT" in body or "8090" in body, "fastpath should reference SERVER_PORT or 8090"
        assert "8070" not in body, "fastpath should not reference 8070"

    def test_session_route_to_agent_no_8070(self):
        src = _read("core/session.py")
        match = re.search(
            r"async def _route_to_agent.*?(?=\n    def |\n    async def |\Z)",
            src, re.DOTALL,
        )
        assert match, "_route_to_agent not found"
        assert "8070" not in match.group()


# ===================================================================
# 4. Self diagnostic checks 8090
# ===================================================================

class TestSelfDiagnosticClean:

    def test_check_dashboard_uses_8090(self):
        src = _read("core/self_diagnostic.py")
        match = re.search(
            r"async def _check_dashboard.*?(?=\n    async def |\Z)",
            src, re.DOTALL,
        )
        assert match, "_check_dashboard not found"
        body = match.group()
        assert "8090" in body
        assert "8070" not in body

    def test_diagnostic_key_renamed(self):
        src = _read("core/self_diagnostic.py")
        assert "dashboard_8070" not in src, (
            "Diagnostic key should be renamed from 'dashboard_8070'"
        )
        assert '"dashboard"' in src, (
            "Diagnostic key should be 'dashboard'"
        )


# ===================================================================
# 5. Config SYSTEM_IDENTITY updated
# ===================================================================

class TestSystemIdentityClean:

    def test_no_8070_in_services_section(self):
        from brain_v9.config import SYSTEM_IDENTITY
        # The services section should mention 8090/ui, not 8070
        assert "8070" not in SYSTEM_IDENTITY
        assert "8090" in SYSTEM_IDENTITY

    def test_dashboard_points_to_ui(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "8090/ui" in SYSTEM_IDENTITY


# ===================================================================
# 6. get_dashboard_data points to 8090
# ===================================================================

class TestGetDashboardData:

    def test_url_uses_8090(self):
        src = _read("agent/tools.py")
        match = re.search(
            r"async def get_dashboard_data.*?(?=\nasync def |\nclass |\ndef |\Z)",
            src, re.DOTALL,
        )
        assert match, "get_dashboard_data function not found"
        body = match.group()
        assert "8090" in body
        assert "8070" not in body
