"""
Smoke test: FRONT-BRAIN-AUTONOMY-GOVERNANCE-HARDENING-01
Verifies centralized capability policy enforces default-deny, self-dev restrictions,
GOD mode bypass blocks, and audit event generation.
"""

import os
import sys
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from brain_v9.governance.capability_policy import CapabilityPolicy, Capability


def test_unknown_capability_is_denied():
    policy = CapabilityPolicy()
    result = policy.check("agent", "unknown_capability", role="admin")
    assert result["decision"] == "deny"
    assert "Unknown capability" in result["reason"]
    assert result["write_performed"] is False
    print("PASS: unknown_capability_is_denied")


def test_mutative_capability_denied_by_default():
    policy = CapabilityPolicy()
    for cap in [Capability.MEMORY_WRITE, Capability.FAISS_REBUILD, Capability.GOVERNANCE_EDIT]:
        result = policy.check("agent", cap, role="admin")
        assert result["decision"] == "deny", f"{cap.value} should be denied by default"
        assert result["write_performed"] is False
    print("PASS: mutative_capability_denied_by_default")


def test_selfdev_cannot_edit_governance():
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.GOVERNANCE_EDIT, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert "Self-dev is not permitted" in result["reason"]
    print("PASS: selfdev_cannot_edit_governance")


def test_selfdev_cannot_edit_security():
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.SECURITY_EDIT, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert "Self-dev is not permitted" in result["reason"]
    print("PASS: selfdev_cannot_edit_security")


def test_selfdev_cannot_edit_capability_policy():
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.SELF_DEV_ACTION, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert "Self-dev is not permitted" in result["reason"]
    print("PASS: selfdev_cannot_edit_capability_policy")


def test_selfdev_cannot_enable_dev_endpoints():
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.DEV_ENDPOINT_ACCESS, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert "Self-dev is not permitted" in result["reason"]
    print("PASS: selfdev_cannot_enable_dev_endpoints")


def test_selfdev_cannot_touch_memory():
    policy = CapabilityPolicy()
    result = policy.check("selfdev", Capability.MEMORY_WRITE, role="admin", is_self_dev=True)
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: selfdev_cannot_touch_memory")


def test_god_mode_cannot_bypass_denylist():
    policy = CapabilityPolicy()
    for cap in [Capability.GOVERNANCE_EDIT, Capability.SECURITY_EDIT]:
        result = policy.check("agent", cap, role="admin", is_god_mode=True)
        assert result["decision"] == "deny", f"GOD mode should not bypass {cap.value}"
        assert "GOD mode cannot bypass" in result["reason"]
    print("PASS: god_mode_cannot_bypass_denylist")


def test_dev_endpoints_off_by_default():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.DEV_ENDPOINT_ACCESS, role="admin")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: dev_endpoints_off_by_default")


def test_read_only_allowed_for_viewer():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.READ_ONLY, role="viewer")
    assert result["decision"] == "allow"
    assert result["write_performed"] is False
    print("PASS: read_only_allowed_for_viewer")


def test_file_read_allowed_for_operator():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.FILE_READ, role="operator")
    assert result["decision"] == "allow"
    assert result["write_performed"] is False
    print("PASS: file_read_allowed_for_operator")


def test_denied_action_returns_write_performed_false():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.GOVERNANCE_EDIT, role="viewer")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: denied_action_returns_write_performed_false")


def test_denied_action_emits_audit_event():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.GOVERNANCE_EDIT, role="viewer")
    audit = result.get("audit_event")
    assert audit is not None
    assert audit["event_type"] == "capability_decision"
    assert audit["actor"] == "agent"
    assert audit["requested_capability"] == "governance_edit"
    assert audit["decision"] == "deny"
    assert audit["write_performed"] is False
    assert "policy_version" in audit
    print("PASS: denied_action_emits_audit_event")


def test_allowed_action_emits_audit_event():
    policy = CapabilityPolicy()
    result = policy.check("agent", Capability.READ_ONLY, role="viewer")
    audit = result.get("audit_event")
    assert audit is not None
    assert audit["event_type"] == "capability_decision"
    assert audit["decision"] == "allow"
    assert audit["write_performed"] is False
    print("PASS: allowed_action_emits_audit_event")


def test_no_secrets_in_policy_module():
    import inspect
    source = inspect.getsource(CapabilityPolicy)
    assert "AGENTV2_TEST_ADMIN_TOKEN" not in source
    assert "OPENAI_API_KEY" not in source
    assert "password" not in source.lower()
    print("PASS: no_secrets_in_policy_module")


def test_trading_broker_always_denied():
    policy = CapabilityPolicy()
    for role in ["viewer", "operator", "admin"]:
        result = policy.check("agent", Capability.BROKER_OR_TRADING, role=role, is_god_mode=True)
        assert result["decision"] == "deny"
        assert "permanently disabled" in result["reason"]
    print("PASS: trading_broker_always_denied")


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


if __name__ == "__main__":
    test_unknown_capability_is_denied()
    test_mutative_capability_denied_by_default()
    test_selfdev_cannot_edit_governance()
    test_selfdev_cannot_edit_security()
    test_selfdev_cannot_edit_capability_policy()
    test_selfdev_cannot_enable_dev_endpoints()
    test_selfdev_cannot_touch_memory()
    test_god_mode_cannot_bypass_denylist()
    test_dev_endpoints_off_by_default()
    test_read_only_allowed_for_viewer()
    test_file_read_allowed_for_operator()
    test_denied_action_returns_write_performed_false()
    test_denied_action_emits_audit_event()
    test_allowed_action_emits_audit_event()
    test_no_secrets_in_policy_module()
    test_trading_broker_always_denied()
    test_guard_passes()
    test_no_memory_files_staged()
    print("\nALL BRAIN AUTONOMY GOVERNANCE HARDENING TESTS PASSED")
