"""P5-04 — Startup script consolidation tests.

Validates:
  - emergency_start.ps1 is the canonical startup (correct paths, ports, no old dashboard)
  - Deprecated scripts (.bat, .vbs) contain redirect messages pointing to emergency_start.ps1
  - No script references the old broken paths (00_identity\autonomy_system, port 8070 dashboard)
"""

import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]  # C:\AI_VAULT\tmp_agent

# ── Helpers ─────────────────────────────────────────────────────

def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


# ── emergency_start.ps1 — canonical script ──────────────────────

class TestEmergencyStart:
    """The canonical startup script."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = _read("emergency_start.ps1")

    def test_file_exists(self):
        assert (ROOT / "emergency_start.ps1").is_file()

    def test_starts_brain_v9(self):
        assert "brain_v9.main" in self.content

    def test_brain_port_8090(self):
        assert "8090" in self.content

    def test_health_endpoint(self):
        assert "/health" in self.content

    def test_sets_pythonpath(self):
        assert "PYTHONPATH" in self.content

    def test_starts_ollama(self):
        assert "ollama" in self.content.lower()

    def test_no_old_dashboard_path(self):
        """Must NOT reference the old autonomy_system dashboard."""
        assert "autonomy_system" not in self.content

    def test_no_port_8070(self):
        """Port 8070 is retired — no health checks or references."""
        # Allow only in comments explaining it's retired
        lines = self.content.splitlines()
        for line in lines:
            stripped = line.strip()
            if "8070" in stripped:
                # Only allowed if it's a comment explaining deprecation
                assert stripped.startswith("#"), (
                    f"Non-comment reference to port 8070: {stripped}"
                )

    def test_no_dashboard_server_py(self):
        """Must not launch a separate dashboard_server.py."""
        assert "dashboard_server.py" not in self.content

    def test_auto_restart_logic(self):
        """Should have restart/recovery logic."""
        assert "restart" in self.content.lower()

    def test_dashboard_url_points_to_ui(self):
        """Dashboard is at /ui on brain port."""
        assert "/ui" in self.content

    def test_startup_wait_configurable(self):
        assert "STARTUP_WAIT" in self.content

    def test_loop_interval_configurable(self):
        assert "LOOP_INTERVAL" in self.content

    def test_max_restarts_configurable(self):
        assert "MAX_RESTARTS" in self.content

    def test_working_directory_correct(self):
        assert r"C:\AI_VAULT\tmp_agent" in self.content


# ── Deprecated scripts — redirect messages ───────────────────────

DEPRECATED_SCRIPTS = [
    "start_brain_v9.bat",
    "start_brain_v9_simple.bat",
    "iniciar_servicios.bat",
    "START_ALL.vbs",
]


class TestDeprecatedScripts:
    """All old scripts should point users to emergency_start.ps1."""

    @pytest.mark.parametrize("script", DEPRECATED_SCRIPTS)
    def test_file_exists(self, script):
        assert (ROOT / script).is_file(), f"{script} should still exist (with deprecation notice)"

    @pytest.mark.parametrize("script", DEPRECATED_SCRIPTS)
    def test_mentions_emergency_start(self, script):
        content = _read(script)
        assert "emergency_start.ps1" in content, (
            f"{script} should redirect to emergency_start.ps1"
        )

    @pytest.mark.parametrize("script", DEPRECATED_SCRIPTS)
    def test_mentions_deprecated(self, script):
        content = _read(script).upper()
        assert "DEPRECATED" in content, f"{script} should say DEPRECATED"

    @pytest.mark.parametrize("script", DEPRECATED_SCRIPTS)
    def test_no_python_launch(self, script):
        """Deprecated scripts must not actually launch python processes."""
        content = _read(script)
        assert "python -m brain_v9" not in content, (
            f"{script} should NOT launch brain_v9 — it's deprecated"
        )

    @pytest.mark.parametrize("script", DEPRECATED_SCRIPTS)
    def test_no_old_dashboard_launch(self, script):
        content = _read(script)
        assert "dashboard_server.py" not in content, (
            f"{script} should NOT reference dashboard_server.py"
        )


# ── Cross-cutting: no script references broken old paths ─────────

ALL_SCRIPTS = ["emergency_start.ps1"] + DEPRECATED_SCRIPTS


class TestNoStaleReferences:
    """Ensure no script points to paths/services that don't exist in V9."""

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_port_8010(self, script):
        """Old brain_server port."""
        content = _read(script)
        assert "8010" not in content

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_port_8030(self, script):
        """Old advisor_server port."""
        content = _read(script)
        assert "8030" not in content

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_init_platforms_reference(self, script):
        """init_platforms.py doesn't exist."""
        content = _read(script)
        assert "init_platforms" not in content

    @pytest.mark.parametrize("script", ALL_SCRIPTS)
    def test_no_env_bat_reference(self, script):
        """.env.bat doesn't exist."""
        content = _read(script)
        assert ".env.bat" not in content
