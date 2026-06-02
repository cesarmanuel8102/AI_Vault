"""
FASE-0-SEGURIDAD / Patch 0B test
=================================
Verifica que GOD mode NO auto-aprueba acciones P3 (destructivas).
P3 SIEMPRE debe requerir aprobacion humana explicita, incluso con GOD activo.
"""
import sys
from pathlib import Path

# Asegura que tmp_agent este en sys.path
_ROOT = Path(__file__).resolve().parents[2]
_TMP = _ROOT / "tmp_agent"
for p in (_ROOT, _TMP):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _make_gate():
    from brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode
    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._god_sessions = {}
    gate._audit_buffer = []
    # stub persistence
    gate._save_state = lambda: None
    gate._audit_log = lambda *a, **kw: None
    return gate


def test_god_mode_blocks_p3_destructive():
    """GOD mode activo NO debe auto-aprobar P3."""
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session

    gate = _make_gate()
    sid = "test_god_session_p3"
    gate._god_sessions[sid] = {"active": True}

    tok = push_god_session(sid)
    try:
        # restart_service => P3 (clasificado en _TOOL_RISK)
        result = gate.check("restart_service", {"service": "brain_v9"}, session_id=sid)
    finally:
        pop_god_session(tok)

    assert result["allowed"] is False, f"P3 NO debe ser auto-aprobado por GOD mode: {result}"
    assert result["risk"] == "P3"
    assert result.get("requires_human_approval") is True
    assert "P3_REQUIRES_EXPLICIT_HUMAN_APPROVAL" in result["reason"]
    assert result["action"] == "confirm"
    assert result["pending_id"] is not None


def test_god_mode_blocks_p3_run_command():
    """Tambien P3 detectado via classify_command_risk."""
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session

    gate = _make_gate()
    sid = "test_god_session_p3_cmd"
    gate._god_sessions[sid] = {"active": True}

    tok = push_god_session(sid)
    try:
        # run_command usa args["cmd"]; rm -rf matchea _P3_PATTERNS
        result = gate.check("run_command", {"cmd": "rm -rf /tmp/foo"}, session_id=sid)
    finally:
        pop_god_session(tok)

    assert result["allowed"] is False
    assert result["risk"] == "P3"


def test_god_mode_still_approves_p2():
    """GOD mode sigue auto-aprobando P2 (regresion check)."""
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session

    gate = _make_gate()
    sid = "test_god_session_p2"
    gate._god_sessions[sid] = {"active": True}

    tok = push_god_session(sid)
    try:
        # taskkill => P2 via classify_command_risk
        result = gate.check("run_command", {"cmd": "taskkill /F /IM notepad.exe"}, session_id=sid)
    finally:
        pop_god_session(tok)

    assert result["allowed"] is True
    assert result.get("god_mode") is True


if __name__ == "__main__":
    test_god_mode_blocks_p3_destructive()
    test_god_mode_blocks_p3_run_command()
    test_god_mode_still_approves_p2()
    print("OK: test_execution_gate_god_p3")
