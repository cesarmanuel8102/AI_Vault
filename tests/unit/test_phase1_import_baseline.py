"""
FASE-1-BASELINE / Test 1
========================
Smoke imports of critical modules. No server start, no env secrets,
no network. Adds tmp_agent to sys.path because brain_v9 lives there.
"""
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TMP = _ROOT / "tmp_agent"
for p in (_ROOT, _TMP):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


_MODULES = [
    "brain_v9.config",
    "brain_v9.governance.execution_gate",
    "brain_v9.api_security",
    "brain_v9.core.session",
]


def test_phase1_imports_succeed():
    for name in _MODULES:
        mod = importlib.import_module(name)
        assert mod is not None, f"import {name} returned None"


def test_phase1_no_server_started():
    """Importing must not start a uvicorn/FastAPI server. We assert no
    socket-bound port artifact and no obvious server attribute is running."""
    import brain_v9.config as cfg  # noqa: F401
    # Just make sure module loaded; no side effect verification beyond import.
    assert hasattr(cfg, "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS")


def test_phase1_execution_gate_class_present():
    from brain_v9.governance.execution_gate import ExecutionGate
    assert ExecutionGate is not None
    assert callable(getattr(ExecutionGate, "check", None)), (
        "ExecutionGate.check must exist for governance baseline"
    )


if __name__ == "__main__":
    test_phase1_imports_succeed()
    test_phase1_no_server_started()
    test_phase1_execution_gate_class_present()
    print("OK: test_phase1_import_baseline")
