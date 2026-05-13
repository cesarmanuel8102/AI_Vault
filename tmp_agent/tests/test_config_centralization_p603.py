"""
P6-03  Hardcoded value centralization — Phase 6 Sprint 1.

Verifies:
 1. config.py defines all P6-03 constants with correct defaults
 2. Consumer files reference config instead of hardcoded literals
 3. health.py retired-port 8070 entry removed
 4. pocketoption_bridge_server.py PORT derived from config
 5. utility_util.py uses config.MAX_LEDGER_ENTRIES
 6. No consumer file re-declares a constant that should come from config
"""
import ast
import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
B9 = ROOT / "brain_v9"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read(relpath: str) -> str:
    return (B9 / relpath).read_text(encoding="utf-8")


def _parse_imports(src: str) -> set[str]:
    """Return all names imported from brain_v9.config in *src*."""
    names: set[str] = set()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "brain_v9.config" in node.module:
                for alias in node.names:
                    names.add(alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "brain_v9.config" in alias.name:
                    names.add(alias.asname or alias.name)
    return names


# ===================================================================
# 1. Config constants exist with correct defaults
# ===================================================================

class TestConfigConstantsExist:
    """All P6-03 constants are defined in config.py."""

    def test_ibkr_host(self):
        from brain_v9.config import IBKR_HOST
        assert IBKR_HOST == "127.0.0.1"

    def test_ibkr_port(self):
        from brain_v9.config import IBKR_PORT
        assert IBKR_PORT == 4002

    def test_pocketoption_bridge_url(self):
        from brain_v9.config import POCKETOPTION_BRIDGE_URL
        assert POCKETOPTION_BRIDGE_URL == "http://127.0.0.1:8765"

    def test_max_ledger_entries(self):
        from brain_v9.config import MAX_LEDGER_ENTRIES
        assert MAX_LEDGER_ENTRIES == 500

    def test_action_cooldown_seconds(self):
        from brain_v9.config import ACTION_COOLDOWN_SECONDS
        assert ACTION_COOLDOWN_SECONDS == 120

    def test_paper_trade_default_amount(self):
        from brain_v9.config import PAPER_TRADE_DEFAULT_AMOUNT
        assert PAPER_TRADE_DEFAULT_AMOUNT == 10.0

    def test_cpu_threshold_pct(self):
        from brain_v9.config import CPU_THRESHOLD_PCT
        assert CPU_THRESHOLD_PCT == 85

    def test_memory_threshold_pct(self):
        from brain_v9.config import MEMORY_THRESHOLD_PCT
        assert MEMORY_THRESHOLD_PCT == 90

    def test_disk_threshold_pct(self):
        from brain_v9.config import DISK_THRESHOLD_PCT
        assert DISK_THRESHOLD_PCT == 90


# ===================================================================
# 2. Consumer files import from config (not hardcoded)
# ===================================================================

class TestConsumerImportsFromConfig:
    """Each updated consumer file imports the relevant constant from config."""

    _EXPECTED = {
        "autonomy/action_executor.py": {
            "IBKR_HOST", "IBKR_PORT",
            "ACTION_COOLDOWN_SECONDS", "MAX_LEDGER_ENTRIES",
        },
        "autonomy/manager.py": {
            "CPU_THRESHOLD_PCT", "MEMORY_THRESHOLD_PCT",
            "DISK_THRESHOLD_PCT", "ACTION_COOLDOWN_SECONDS",
        },
        "trading/strategy_engine.py": {"IBKR_HOST", "IBKR_PORT"},
        "trading/connectors.py": {
            "IBKR_HOST", "IBKR_PORT", "POCKETOPTION_BRIDGE_URL",
        },
        "trading/ibkr_order_executor.py": {"IBKR_HOST", "IBKR_PORT"},
    }

    @pytest.mark.parametrize("relpath, expected_names", list(_EXPECTED.items()))
    def test_imports_present(self, relpath: str, expected_names: set[str]):
        src = _read(relpath)
        imported = _parse_imports(src)
        missing = expected_names - imported
        assert not missing, (
            f"{relpath} is missing imports: {missing}"
        )


class TestModuleImportStyle:
    """Files that use `import brain_v9.config as _cfg` pattern."""

    _EXPECTED_MODULE_IMPORT = [
        "trading/paper_execution.py",
        "brain/health.py",
        "trading/pocketoption_bridge_server.py",
        "trading/utility_util.py",
    ]

    @pytest.mark.parametrize("relpath", _EXPECTED_MODULE_IMPORT)
    def test_module_import(self, relpath: str):
        src = _read(relpath)
        assert "import brain_v9.config as _cfg" in src, (
            f"{relpath} should use `import brain_v9.config as _cfg`"
        )

    def test_sample_accumulator_imports_config(self):
        """sample_accumulator_agent.py uses named imports from config."""
        src = _read("autonomy/sample_accumulator_agent.py")
        assert "from brain_v9.config import" in src, (
            "sample_accumulator_agent.py should import from brain_v9.config"
        )


# ===================================================================
# 3. health.py — no retired port 8070 entry
# ===================================================================

class TestHealthCleaned:

    def test_no_port_8070(self):
        src = _read("brain/health.py")
        assert "8070" not in src, "health.py should not reference retired port 8070"

    def test_no_dashboard_service_key(self):
        src = _read("brain/health.py")
        assert '"dashboard"' not in src, (
            "health.py SERVICES dict should not have a 'dashboard' entry "
            "(port 8070 retired)"
        )

    def test_bridge_uses_config(self):
        src = _read("brain/health.py")
        assert "_cfg.POCKETOPTION_BRIDGE_URL" in src


# ===================================================================
# 4. pocketoption_bridge_server.py — PORT from config
# ===================================================================

class TestBridgeServerPort:

    def test_port_not_hardcoded(self):
        """PORT should NOT be a bare literal 8765 assignment."""
        src = _read("trading/pocketoption_bridge_server.py")
        # Match `PORT = 8765` as a standalone assignment (not derived from config)
        assert not re.search(r"^PORT\s*=\s*8765\s*$", src, re.MULTILINE), (
            "PORT should be derived from config, not hardcoded as 8765"
        )

    def test_port_derived_from_config(self):
        src = _read("trading/pocketoption_bridge_server.py")
        assert "_cfg.POCKETOPTION_BRIDGE_URL" in src


# ===================================================================
# 5. utility_util.py — uses config.MAX_LEDGER_ENTRIES
# ===================================================================

class TestUtilityUtilCentralized:

    def test_no_sys_path_hack(self):
        src = _read("trading/utility_util.py")
        assert "sys.path.insert" not in src, (
            "utility_util.py should not use sys.path hacks"
        )

    def test_uses_config_max_ledger(self):
        src = _read("trading/utility_util.py")
        assert "_cfg.MAX_LEDGER_ENTRIES" in src

    def test_no_hardcoded_limit_500(self):
        src = _read("trading/utility_util.py")
        assert "limit=500" not in src, (
            "utility_util.py should use _cfg.MAX_LEDGER_ENTRIES, not limit=500"
        )


# ===================================================================
# 6. No consumer re-declares centralized constants locally
# ===================================================================

class TestNoLocalRedeclarations:
    """Consumer files should NOT define their own copies of centralized values."""

    _FILES_TO_CHECK = [
        "autonomy/action_executor.py",
        "autonomy/manager.py",
        "trading/strategy_engine.py",
        "trading/connectors.py",
        "trading/ibkr_order_executor.py",
        "trading/paper_execution.py",
        "autonomy/sample_accumulator_agent.py",
    ]

    _PATTERNS = [
        (r"MAX_LEDGER_ENTRIES\s*=\s*500", "MAX_LEDGER_ENTRIES = 500"),
        (r"ACTION_COOLDOWN_SECONDS\s*=\s*300", "ACTION_COOLDOWN_SECONDS = 300"),
    ]

    @pytest.mark.parametrize("relpath", _FILES_TO_CHECK)
    def test_no_local_max_ledger_or_cooldown(self, relpath: str):
        src = _read(relpath)
        for pattern, desc in self._PATTERNS:
            assert not re.search(pattern, src), (
                f"{relpath} still has local '{desc}' — should use config"
            )
