"""
Smoke test: FRONT-BRAIN-AUTONOMY-CRYPTO-APPROVALS-05
Verifies signed approval token creation and validation.
"""

import sys
import time
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from brain_v9.governance.signed_approvals import (
    create_approval_token,
    verify_approval_token,
    ApprovalTokenManager,
    _test_create_token,
    _test_verify_token,
    TEST_SECRET,
)


def test_valid_token_accepted():
    """Valid token is accepted."""
    token = _test_create_token()
    result = _test_verify_token(token)
    assert result["valid"] is True
    assert result["actor"] == "operator"
    assert result["scope"] == "governance"
    assert result["action"] == "edit_file"
    assert result["target"] == "tmp_agent/brain_v9/governance/execution_gate.py"
    print("PASS: valid_token_accepted")


def test_expired_token_denied():
    """Expired token is denied."""
    token = create_approval_token(
        actor="operator",
        scope="governance",
        action="edit_file",
        target="tmp_agent/brain_v9/governance/execution_gate.py",
        expires_in_seconds=-3600,  # Expired 1 hour ago
        secret=TEST_SECRET,
        nonce="expired-nonce",
    )
    result = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
    )
    assert result["valid"] is False
    assert "expired" in result["reason"].lower()
    print("PASS: expired_token_denied")


def test_wrong_scope_denied():
    """Wrong scope is denied."""
    token = _test_create_token()
    result = verify_approval_token(
        token=token,
        expected_scope="security",  # Wrong scope
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
    )
    assert result["valid"] is False
    assert "scope" in result["reason"].lower()
    print("PASS: wrong_scope_denied")


def test_wrong_action_denied():
    """Wrong action is denied."""
    token = _test_create_token()
    result = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="write_file",  # Wrong action
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
    )
    assert result["valid"] is False
    assert "action" in result["reason"].lower()
    print("PASS: wrong_action_denied")


def test_wrong_target_denied():
    """Wrong target is denied."""
    token = _test_create_token()
    result = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/security/rbac.py",  # Wrong target
        secret=TEST_SECRET,
    )
    assert result["valid"] is False
    assert "target" in result["reason"].lower()
    print("PASS: wrong_target_denied")


def test_invalid_signature_denied():
    """Invalid signature is denied."""
    token = "invalid.token.signature"
    result = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
    )
    assert result["valid"] is False
    print("PASS: invalid_signature_denied")


def test_replayed_nonce_denied():
    """Replayed nonce is denied."""
    # Use a unique nonce for this test to avoid interference from other tests
    unique_nonce = "replay-test-unique-nonce-456"
    token = create_approval_token(
        actor="operator",
        scope="governance",
        action="edit_file",
        target="tmp_agent/brain_v9/governance/execution_gate.py",
        expires_in_seconds=3600,
        secret=TEST_SECRET,
        nonce=unique_nonce,
    )
    # First verification should succeed (fresh nonce set)
    fresh_nonce_set = set()
    result1 = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
        used_nonces=fresh_nonce_set,
    )
    assert result1["valid"] is True

    # Second verification with same nonce should fail (replay protection)
    # The nonce is now in fresh_nonce_set
    result2 = verify_approval_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
        secret=TEST_SECRET,
        used_nonces=fresh_nonce_set,  # Same set, nonce already used
    )
    assert result2["valid"] is False
    assert "replay" in result2["reason"].lower() or result2.get("replay_detected") is True
    print("PASS: replayed_nonce_denied")


def test_token_contains_nonce():
    """Token contains nonce."""
    token = _test_create_token()
    import base64
    token_b64, _ = token.rsplit(".", 1)
    padding = "=" * ((4 - len(token_b64) % 4) % 4)
    import json
    payload_str = base64.urlsafe_b64decode(token_b64 + "=" * ((4 - len(token_b64) % 4) % 4)).decode()
    payload = json.loads(payload_str)
    assert "nonce" in payload
    assert payload["nonce"] == "test-nonce-123"
    print("PASS: token_contains_nonce")


def test_token_contains_expiration():
    """Token contains expiration timestamp."""
    token = _test_create_token()
    import base64
    token_b64, _ = token.rsplit(".", 1)
    padding = "=" * ((4 - len(token_b64) % 4) % 4)
    import json
    payload_str = base64.urlsafe_b64decode(token_b64 + padding).decode()
    payload = json.loads(payload_str)
    assert "expires_at" in payload
    assert payload["expires_at"] > int(time.time())
    print("PASS: token_contains_expiration")


def test_secret_not_printed():
    """Secret is not printed in token."""
    token = _test_create_token()
    assert TEST_SECRET not in token
    print("PASS: secret_not_printed")


def test_full_token_not_logged():
    """Full token not logged in audit (verify function doesn't print token)."""
    token = _test_create_token()
    result = _test_verify_token(token)
    # Result should not contain the full token
    assert token not in str(result)
    print("PASS: full_token_not_logged")


def test_manager_create_and_verify():
    """ApprovalTokenManager creates and verifies tokens."""
    manager = ApprovalTokenManager(secret=TEST_SECRET)
    token = manager.create_token(
        actor="operator",
        scope="governance",
        action="edit_file",
        target="tmp_agent/brain_v9/governance/execution_gate.py",
        expires_in_seconds=3600,
    )
    result = manager.verify_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
    )
    assert result["valid"] is True
    print("PASS: manager_create_and_verify")


def test_manager_replay_protection():
    """ApprovalTokenManager replay protection works."""
    manager = ApprovalTokenManager(secret=TEST_SECRET)
    token = manager.create_token(
        actor="operator",
        scope="governance",
        action="edit_file",
        target="tmp_agent/brain_v9/governance/execution_gate.py",
        expires_in_seconds=3600,
    )
    result1 = manager.verify_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
    )
    assert result1["valid"] is True

    # Replay should fail
    result2 = manager.verify_token(
        token=token,
        expected_scope="governance",
        expected_action="edit_file",
        expected_target="tmp_agent/brain_v9/governance/execution_gate.py",
    )
    assert result2["valid"] is False
    assert result2.get("replay_detected") is True
    print("PASS: manager_replay_protection")


def test_token_contains_all_fields():
    """Token contains all required fields."""
    token = _test_create_token()
    import base64
    token_b64, _ = token.rsplit(".", 1)
    padding = "=" * ((4 - len(token_b64) % 4) % 4)
    import json
    payload_str = base64.urlsafe_b64decode(token_b64 + "=" * ((4 - len(token_b64) % 4) % 4)).decode()
    payload = json.loads(payload_str)

    required_fields = ["actor", "scope", "action", "target", "issued_at", "expires_at", "nonce"]
    for field in required_fields:
        assert field in payload, f"Missing field: {field}"
    print("PASS: token_contains_all_fields")


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


def test_previous_tests_still_pass():
    """Quick sanity: previous tests still work."""
    from brain_v9.governance.execution_gate import get_gate
    gate = get_gate()
    r = gate.check("edit_file", {"path": "tmp_agent/brain_v9/governance/execution_gate.py"})
    assert r["allowed"] is False
    assert r.get("write_performed") is False
    print("PASS: previous_tests_still_pass")


if __name__ == "__main__":
    import json
    import base64
    import time

    test_valid_token_accepted()
    test_expired_token_denied()
    test_wrong_scope_denied()
    test_wrong_action_denied()
    test_wrong_target_denied()
    test_invalid_signature_denied()
    test_replayed_nonce_denied()
    test_token_contains_nonce()
    test_token_contains_expiration()
    test_secret_not_printed()
    test_full_token_not_logged()
    test_manager_create_and_verify()
    test_manager_replay_protection()
    test_token_contains_all_fields()
    test_guard_passes()
    test_no_memory_files_staged()
    test_previous_tests_still_pass()
    print("\nALL CRYPTO APPROVAL TESTS PASSED")