from __future__ import annotations

import sys
from pathlib import Path

import pytest


WINDOWS_ONLY_FILES = {
    "test_auditor_provisioning.py",
    "test_auditor_runtime.py",
    "test_auditor_runtime_v2.py",
    "test_execution_lock.py",
    "test_prerequisite_finalizer.py",
}


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    marker = pytest.mark.skip(reason="Windows-only IBKR/Auditor host-boundary test")
    for item in items:
        if Path(str(item.fspath)).name in WINDOWS_ONLY_FILES:
            item.add_marker(marker)
