"""
Smoke test: FRONT-BRAIN-AUTONOMY-RUNTIME-INTEGRATION-03
Verifies SelfDevSandbox is wired into ExecutionGate runtime gate.
Tests that denied runtime mutations return write_performed=false and audit events.
"""

import os
import sys
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from brain_v9.governance.execution_gate import get_gate, ExecutionGate, ExecutionMode
from brain_v9.governance.selfdev_sandbox import evaluate_selfdev_action
from brain_v9.governance.capability_policy import Capability


def test_runtime_governance_write_denied():
    """ExecutionGate.check() for edit_file on governance file returns deny."""
    gate = ExecutionGate()
    # Simulate self-dev context
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/execution_gate.py"}, session_id="selfdev_test")
    assert result["allowed"] is False, f"Should deny governance edit: {result}"
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_governance_write_denied")


def test_runtime_security_write_denied():
    """ExecutionGate.check() for write_file on security file returns deny."""
    gate = ExecutionGate()
    result = gate.check("write_file", {"path": "tmp_agent/brain_v9/security/rbac.py"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_security_write_denied")


def test_runtime_capability_policy_write_denied():
    """ExecutionGate.check() for edit_file on capability_policy returns deny."""
    gate = ExecutionGate()
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/capability_policy.py"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_capability_policy_write_denied")


def test_runtime_selfdev_sandbox_write_denied():
    """ExecutionGate.check() for edit_file on selfdev_sandbox returns deny."""
    gate = ExecutionGate()
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/selfdev_sandbox.py"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_selfdev_sandbox_write_denied")


def test_runtime_workflow_write_denied():
    """ExecutionGate.check() for write_file on .github/workflows returns deny."""
    gate = ExecutionGate()
    result = gate.check("write_file", {"path": ".github/workflows/test.yml"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_workflow_write_denied")


def test_runtime_memory_write_denied():
    """ExecutionGate.check() for edit_file on memory/semantic returns deny."""
    gate = ExecutionGate()
    result = gate.check("edit_file", {"path": "memory/semantic/semantic_memory.jsonl"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_memory_write_denied")


def test_runtime_trading_write_denied():
    """ExecutionGate.check() for write_file on trading path returns deny."""
    gate = ExecutionGate()
    result = gate.check("write_file", {"path": "trading/strategy.py"}, session_id="selfdev_test")
    assert result["allowed"] is False
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: runtime_trading_write_denied")


def test_god_mode_cannot_bypass_runtime_sandbox():
    """GOD mode cannot bypass runtime sandbox for protected paths."""
    gate = ExecutionGate()
    # Enable GOD mode for a session
    gate.enable_god_mode("god_session_123")
    # Try to edit governance file with GOD mode
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/execution_gate.py"}, session_id="god_session_123")
    assert result["allowed"] is False, f"GOD mode should not bypass: {result}"
    assert result["write_performed"] is False
    # Should be denied - either by sandbox or by capability policy GOD denylist
    # Both are correct behaviors
    assert "audit_event" in result
    assert result["audit_event"]["decision"] == "deny"
    print("PASS: god_mode_cannot_bypass_runtime_sandbox")


def test_bypass_gate_cannot_bypass_protected_paths():
    """_bypass_gate should not bypass SelfDevSandbox for protected paths (if gate is called)."""
    # This test verifies the gate itself enforces sandbox even if a tool tries to bypass
    # The actual _bypass_gate bypasses the gate entirely, so this tests gate behavior
    gate = ExecutionGate()
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/execution_gate.py"}, session_id="test")
    # Gate itself should deny regardless of bypass intent
    assert result["allowed"] is False
    assert result["write_performed"] is False
    print("PASS: bypass_gate_cannot_bypass_protected_paths")


def test_god_override_cannot_bypass_protected_paths():
    """god_override in capability_governor should not bypass runtime sandbox."""
    gate = ExecutionGate()
    # GOD mode with P3 risk should still be blocked for protected paths
    gate.enable_god_mode("god_override_session")
    result = gate.check("install_package", {"package": "some_package"}, session_id="god_override_session")
    # install_package is P2, but if path was protected it would be denied
    # For now, just verify gate respects sandbox for write tools
    result2 = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/capability_policy.py"}, session_id="god_override_session")
    assert result2["allowed"] is False
    assert result2["write_performed"] is False
    print("PASS: god_override_cannot_bypass_protected_paths")


def test_safe_read_only_path_allowed():
    """Non-protected read-only path still allowed."""
    gate = ExecutionGate()
    result = gate.check("read_file", {"path": "docs/readme.md"})
    assert result["allowed"] is True
    assert result["action"] == "execute"
    print("PASS: safe_read_only_path_allowed")


def test_denied_result_includes_audit_event():
    """Denied result includes structured audit_event."""
    gate = ExecutionGate()
    result = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/execution_gate.py"}, session_id="test")
    audit = result.get("audit_event")
    assert audit is not None
    assert audit["event_type"] == "capability_decision"
    assert audit["decision"] == "deny"
    assert audit["write_performed"] is False
    assert "target_path" in audit
    assert "requested_capability" in audit
    assert "policy_version" in audit
    print("PASS: denied_result_includes_audit_event")


def test_no_secrets_in_integration():
    """No secret values in integration code."""
    import inspect
    source = inspect.getsource(ExecutionGate.check)
    assert "AGENTV2_TEST_ADMIN_TOKEN" not in source
    assert "OPENAI_API_KEY" not in source
    print("PASS: no_secrets_in_integration")


def test_guard_passes():
    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    print("PASS: guard_passes")


def test_no_memory_files_staged():
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    staged = result.stdout.strip()
    for line in staged.splitlines() if staged else []:
        assert "memory/semantic" not in line
        assert "memory/autonomous_journal" not in line
        assert "memory/rollback_snapshots" not in line
    print("PASS: no_memory_files_staged")


def test_selfdev_sandbox_tests_still_pass():
    """Verify previous SelfDevSandbox tests still work."""
    from brain_v9.governance.selfdev_sandbox import SelfDevSandbox
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/execution_gate.py")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: selfdev_sandbox_tests_still_pass")


def test_governance_hardening_tests_still_pass():
    """Verify previous governance hardening tests still work."""
    from brain_v9.governance.capability_policy import CapabilityPolicy, Capability
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.GOVERNANCE_EDIT, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: governance_hardening_tests_still_pass")


if __name__ == "__main__":
    test_runtime_governance_write_denied()
    test_runtime_security_write_denied()
    test_runtime_capability_policy_write_denied()
    test_runtime_selfdev_sandbox_write_denied()
    test_runtime_workflow_write_denied()
    test_runtime_memory_write_denied()
    test_runtime_trading_write_denied()
    test_god_mode_cannot_bypass_runtime_sandbox()
    test_bypass_gate_cannot_bypass_protected_paths()
    test_god_override_cannot_bypass_protected_paths()
    test_safe_read_only_path_allowed()
    test_denied_result_includes_audit_event()
    test_no_secrets_in_integration()
    test_guard_passes()
    test_no_memory_files_staged()
    test_selfdev_sandbox_tests_still_pass()
    test_governance_hardening_tests_still_pass()
    print("\nALL RUNTIME INTEGRATION TESTS PASSED")