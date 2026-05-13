"""
Brain V9 — Shared test fixtures.

Sets BRAIN_BASE_PATH to a temp directory before importing brain_v9 modules,
so tests never touch the real C:/AI_VAULT state.
"""
import os
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_base_path(tmp_path, monkeypatch):
    """
    Redirect brain_v9.config.BASE_PATH to a temp directory for every test.

    This ensures:
      - Tests never read/write real state files
      - Each test gets a clean filesystem
      - Import-time side effects (mkdir) happen in the temp dir
    """
    # Set the env var BEFORE brain_v9.config is imported (or re-patch after)
    monkeypatch.setenv("BRAIN_BASE_PATH", str(tmp_path))

    # If config was already imported, patch the module-level Path objects too
    try:
        import brain_v9.config as cfg
        monkeypatch.setattr(cfg, "BASE_PATH", tmp_path)
        monkeypatch.setattr(cfg, "MEMORY_PATH", tmp_path / "tmp_agent" / "state" / "memory")
        monkeypatch.setattr(cfg, "LOGS_PATH", tmp_path / "tmp_agent" / "logs")
        monkeypatch.setattr(cfg, "RSI_PATH", tmp_path / "tmp_agent" / "state" / "rsi")
        monkeypatch.setattr(cfg, "BRAIN_V9_PATH", tmp_path / "tmp_agent")
    except ImportError:
        pass  # If config can't be imported, the env var will handle it

    # Patch derived module-level constants that were computed at import time
    try:
        import brain_v9.core.session as sess
        monkeypatch.setattr(sess, "_STATE_PATH", tmp_path / "tmp_agent" / "state")
    except ImportError:
        pass

    try:
        import brain_v9.trading.paper_execution as pe
        pe_engine = tmp_path / "tmp_agent" / "state" / "strategy_engine"
        monkeypatch.setattr(pe, "STATE_PATH", tmp_path / "tmp_agent" / "state")
        monkeypatch.setattr(pe, "ENGINE_PATH", pe_engine)
        monkeypatch.setattr(pe, "PAPER_EXECUTION_LEDGER_PATH",
                            pe_engine / "signal_paper_execution_ledger.json")
        monkeypatch.setattr(pe, "PAPER_EXECUTION_CURSOR_PATH",
                            pe_engine / "signal_paper_execution_cursor.json")
    except ImportError:
        pass

    # Create minimum directory structure
    (tmp_path / "tmp_agent" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp_agent" / "state" / "strategy_engine").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp_agent" / "logs").mkdir(parents=True, exist_ok=True)

    # P-OP30a: Always return True for market-hours checks in tests,
    # so test outcomes don't depend on the real day/time.
    try:
        import brain_v9.config as _cfg
        monkeypatch.setattr(_cfg, "is_venue_market_open", lambda venue: True)
    except (ImportError, AttributeError):
        pass

    return tmp_path
