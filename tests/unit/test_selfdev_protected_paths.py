"""
FASE-0-SEGURIDAD / Patch 0D test
=================================
Verifica que la denylist de paths gobernanza/seguridad bloquea ediciones
incluso con GOD mode activo o selfdev_bypass=True.
"""
import sys
from pathlib import Path

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
    gate._save_state = lambda: None
    gate._audit_log = lambda *a, **kw: None
    return gate


def test_helper_detects_protected_paths():
    from brain_v9.governance.execution_gate import _is_protected_selfdev_path
    cases = [
        "tmp_agent/brain_v9/governance/execution_gate.py",
        "C:/AI_VAULT/tmp_agent/brain_v9/governance/ethics_kernel.py",
        "tmp_agent/brain_v9/api_security.py",
        "tmp_agent/brain_v9/trace_redactor.py",
        "brain_v9/governance/approval.py",
        "some/path/auth_module.py",
        "x/y/policy.py",
    ]
    for c in cases:
        assert _is_protected_selfdev_path(c), f"Debe bloquear: {c}"


def test_helper_allows_normal_paths():
    from brain_v9.governance.execution_gate import _is_protected_selfdev_path
    safe = [
        "tmp_agent/strategies/some_strategy.py",
        "tmp_agent/brain_v9/ui/dashboard.py",
        "",
    ]
    for s in safe:
        assert not _is_protected_selfdev_path(s), f"NO debe bloquear: {s!r}"


def test_helper_now_blocks_memory_semantic_and_session():
    from brain_v9.governance.execution_gate import _is_protected_selfdev_path
    # FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01 extended coverage
    assert _is_protected_selfdev_path("memory/semantic/data.jsonl")
    assert _is_protected_selfdev_path("tmp_agent/brain_v9/core/session.py")


def test_god_mode_cannot_edit_governance():
    """GOD mode activo NO debe permitir editar execution_gate.py via edit_file."""
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session

    gate = _make_gate()
    sid = "test_god_selfdev"
    gate._god_sessions[sid] = {"active": True}

    tok = push_god_session(sid)
    try:
        result = gate.check(
            "edit_file",
            {"path": "tmp_agent/brain_v9/governance/execution_gate.py"},
            session_id=sid,
        )
    finally:
        pop_god_session(tok)

    assert result["allowed"] is False
    # Accept either the old protected path reason or the new SelfDevSandbox reason
    assert (
        "SELFDEV_PROTECTED_GOVERNANCE_SECURITY_PATH" in result["reason"]
        or "GOD mode cannot bypass hardened deny-list" in result["reason"]
    ), f"Unexpected reason: {result['reason']}"
    assert result["action"] == "blocked"
    # Note: requires_human_approval is only present for protected path denylist, not SelfDevSandbox denials
    if "SELFDEV_PROTECTED_GOVERNANCE_SECURITY_PATH" in result["reason"]:
        assert result.get("requires_human_approval") is True


def test_god_mode_can_still_edit_normal_files():
    """Regresion: GOD mode sigue editando archivos no protegidos."""
    from brain_v9.governance.execution_gate import push_god_session, pop_god_session

    gate = _make_gate()
    sid = "test_god_normal"
    gate._god_sessions[sid] = {"active": True}

    tok = push_god_session(sid)
    try:
        result = gate.check(
            "edit_file",
            {"path": "tmp_agent/brain_v9/notes/scratch.txt"},
            session_id=sid,
        )
    finally:
        pop_god_session(tok)

    assert result["allowed"] is True


def test_run_command_with_protected_path_blocked():
    gate = _make_gate()
    result = gate.check(
        "run_command",
        {"command": "del C:\\AI_VAULT\\tmp_agent\\brain_v9\\api_security.py"},
        session_id=None,
    )
    assert result["allowed"] is False
    assert "SELFDEV_PROTECTED" in result["reason"]


if __name__ == "__main__":
    test_helper_detects_protected_paths()
    test_helper_allows_normal_paths()
    test_god_mode_cannot_edit_governance()
    test_god_mode_can_still_edit_normal_files()
    test_run_command_with_protected_path_blocked()
    print("OK: test_selfdev_protected_paths")
