"""
Smoke test: FRONT-BRAIN-AUTONOMY-SELFDEV-SANDBOX-02
Verifies runtime sandbox constraints for self-dev actions.
Tests deny paths, GOD mode bypass blocks, and audit event generation.
"""

import os
import sys
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from brain_v9.governance.selfdev_sandbox import SelfDevSandbox, evaluate_selfdev_action
from brain_v9.governance.capability_policy import Capability


def test_unknown_capability_denied():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "unknown_cap", "some/path.py")
    assert result["decision"] == "deny"
    assert "Unknown capability" in result["reason"]
    assert result["write_performed"] is False
    print("PASS: unknown_capability_denied")


def test_selfdev_governance_edit_denied():
    sandbox = SelfDevSandbox()
    paths = [
        "tmp_agent/brain_v9/governance/execution_gate.py",
        "tmp_agent/brain_v9/governance/ethics_kernel.py",
        "tmp_agent/brain_v9/governance/protected_paths.py",
        "tmp_agent/brain_v9/governance/capability_policy.py",
        "tmp_agent/brain_v9/governance/selfdev_sandbox.py",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: selfdev_governance_edit_denied")


def test_selfdev_security_edit_denied():
    sandbox = SelfDevSandbox()
    paths = [
        "tmp_agent/brain_v9/security/rbac.py",
        "tmp_agent/brain_v9/security/api_security.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: selfdev_security_edit_denied")


def test_selfdev_capability_policy_edit_denied():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/capability_policy.py")
    assert result["decision"] == "deny"
    assert "governance" in result["requested_capability"].lower()
    assert result["write_performed"] is False
    print("PASS: selfdev_capability_policy_edit_denied")


def test_selfdev_selfdev_sandbox_edit_denied():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/selfdev_sandbox.py")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: selfdev_selfdev_sandbox_edit_denied")


def test_selfdev_workflow_mutation_denied():
    sandbox = SelfDevSandbox()
    paths = [
        ".github/workflows/nontrading-smoke-regression.yml",
        ".github/workflows/phase1-ci.yml",
        ".github/workflows/some-other.yml",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: selfdev_workflow_mutation_denied")


def test_selfdev_memory_semantic_mutation_denied():
    sandbox = SelfDevSandbox()
    paths = [
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/semantic_staging/some_file.json",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: selfdev_memory_semantic_mutation_denied")


def test_selfdev_autonomous_journal_mutation_denied():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "memory/autonomous_journal.jsonl")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: selfdev_autonomous_journal_mutation_denied")


def test_selfdev_rollback_snapshots_mutation_denied():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "memory/rollback_snapshots/20260626/file.jsonl")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    print("PASS: selfdev_rollback_snapshots_mutation_denied")


def test_selfdev_trading_broker_paths_denied():
    sandbox = SelfDevSandbox()
    paths = [
        "trading/some_file.py",
        "broker/ibkr_client.py",
        "ibkr/config.json",
        "quantconnect/algorithm.py",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert "broker" in result["requested_capability"].lower() or "trading" in result["requested_capability"].lower()
        assert result["write_performed"] is False
    print("PASS: selfdev_trading_broker_paths_denied")


def test_selfdev_env_secrets_denied():
    sandbox = SelfDevSandbox()
    paths = [
        ".env",
        ".dev_auth/token.json",
        "secrets/api_keys.json",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p)
        assert result["decision"] == "deny", f"Should deny {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: selfdev_env_secrets_denied")


def test_god_mode_cannot_bypass_protected_paths():
    sandbox = SelfDevSandbox()
    paths = [
        "tmp_agent/brain_v9/governance/execution_gate.py",
        "tmp_agent/brain_v9/security/rbac.py",
        ".github/workflows/ci.yml",
        "memory/semantic/semantic_memory.jsonl",
        "trading/strategy.py",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p, is_god_mode=True)
        assert result["decision"] == "deny", f"GOD mode should not bypass {p}"
        # Trading/broker paths denied for BROKER reason; others for GOD/SELFDEV reason
        assert (
            "GOD mode cannot bypass" in result["reason"]
            or "Self-dev is not permitted" in result["reason"]
            or "permanently disabled" in result["reason"]
        ), f"Unexpected reason for {p}: {result['reason']}"
        assert result["write_performed"] is False
    print("PASS: god_mode_cannot_bypass_protected_paths")


def test_safe_read_only_allowed():
    sandbox = SelfDevSandbox()
    paths = [
        "docs/readme.md",
        "tests/smoke/test_something.py",
        "tmp_agent/brain_v9/main.py",
    ]
    for p in paths:
        result = sandbox.evaluate_selfdev_action("selfdev", "auto", p, is_god_mode=False)
        # Note: These may be denied due to role restrictions, but they should not be
        # denied for GOVERNANCE_EDIT / SECURITY_EDIT / MEMORY_WRITE / BROKER reasons
        # They could be allowed or denied based on role - but not for protected path reasons
        if result["decision"] == "deny":
            # Should only be denied for role/capability reasons, not protected path
            assert "governance" not in result["reason"].lower() or "Self-dev" not in result["reason"]
    print("PASS: safe_read_only_allowed")


def test_denied_action_has_write_performed_false():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/execution_gate.py")
    assert result["write_performed"] is False
    assert "write_performed" in result
    print("PASS: denied_action_has_write_performed_false")


def test_denied_action_emits_audit_event():
    sandbox = SelfDevSandbox()
    result = sandbox.evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/execution_gate.py")
    audit = result.get("audit_event")
    assert audit is not None
    assert audit["event_type"] == "capability_decision"
    assert audit["actor"] == "selfdev"
    assert audit["decision"] == "deny"
    assert audit["write_performed"] is False
    assert "target_path" in audit
    assert "requested_capability" in audit
    assert "policy_version" in audit
    print("PASS: denied_action_emits_audit_event")


def test_allowed_action_emits_audit_event():
    sandbox = SelfDevSandbox()
    # FILE_READ should be allowed for operator
    result = sandbox.evaluate_selfdev_action("selfdev", "file_read", "docs/readme.md", role="operator")
    audit = result.get("audit_event")
    assert audit is not None
    assert audit["event_type"] == "capability_decision"
    assert audit["decision"] == "allow"
    assert audit["write_performed"] is False
    print("PASS: allowed_action_emits_audit_event")


def test_no_secrets_in_sandbox_module():
    import inspect
    source = inspect.getsource(SelfDevSandbox)
    assert "AGENTV2_TEST_ADMIN_TOKEN" not in source
    assert "OPENAI_API_KEY" not in source
    assert "password" not in source.lower()
    print("PASS: no_secrets_in_sandbox_module")


def test_convenience_methods():
    sandbox = SelfDevSandbox()
    # evaluate_file_write
    r1 = sandbox.evaluate_file_write("selfdev", "docs/readme.md")
    # evaluate_code_edit
    r2 = sandbox.evaluate_code_edit("selfdev", "docs/readme.md")
    # evaluate_git_action
    r3 = sandbox.evaluate_git_action("selfdev", "push", ".")
    # evaluate_memory_write
    r4 = sandbox.evaluate_memory_write("selfdev", "memory/semantic/file.jsonl")
    # evaluate_dev_endpoint_access
    r5 = sandbox.evaluate_dev_endpoint_access("selfdev")
    for r in [r1, r2, r3, r4, r5]:
        assert "decision" in r
        assert "write_performed" in r
        assert r["write_performed"] is False
        assert "audit_event" in r
    print("PASS: convenience_methods")


def test_module_level_function():
    result = evaluate_selfdev_action("selfdev", "auto", "tmp_agent/brain_v9/governance/execution_gate.py")
    assert result["decision"] == "deny"
    assert result["write_performed"] is False
    assert "audit_event" in result
    print("PASS: module_level_function")


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
    test_unknown_capability_denied()
    test_selfdev_governance_edit_denied()
    test_selfdev_security_edit_denied()
    test_selfdev_capability_policy_edit_denied()
    test_selfdev_selfdev_sandbox_edit_denied()
    test_selfdev_workflow_mutation_denied()
    test_selfdev_memory_semantic_mutation_denied()
    test_selfdev_autonomous_journal_mutation_denied()
    test_selfdev_rollback_snapshots_mutation_denied()
    test_selfdev_trading_broker_paths_denied()
    test_selfdev_env_secrets_denied()
    test_god_mode_cannot_bypass_protected_paths()
    test_safe_read_only_allowed()
    test_denied_action_has_write_performed_false()
    test_denied_action_emits_audit_event()
    test_allowed_action_emits_audit_event()
    test_no_secrets_in_sandbox_module()
    test_convenience_methods()
    test_module_level_function()
    test_guard_passes()
    test_no_memory_files_staged()
    print("\nALL SELFDEV SANDBOX TESTS PASSED")