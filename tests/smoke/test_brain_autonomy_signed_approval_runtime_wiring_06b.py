"""
FRONT 06B smoke tests: ExecutionGate signed approval runtime wiring.

P3 and protected-path approvals must fail closed unless a valid signed token is
provided. Legacy non-P3/non-protected approvals remain compatible.
"""
from __future__ import annotations

import sys
from pathlib import Path

from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode
from brain_v9.governance.signed_approvals import TEST_SECRET, create_approval_token


PROTECTED_TARGET = "tmp_agent/brain_v9/governance/execution_gate.py"


def _make_gate() -> ExecutionGate:
    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._audit = []
    gate._god_sessions = set()
    gate._save_state = lambda: None
    gate._audit_log = lambda *args, **kwargs: None
    gate._expire_stale_pending = lambda: 0
    return gate


def _pending(
    *,
    pending_id: str = "pending-test",
    tool: str = "restart_service",
    risk: str = "P3",
    args: dict | None = None,
) -> dict:
    return {
        "id": pending_id,
        "tool": tool,
        "args": args if args is not None else {"service": "brain_v9"},
        "risk": risk,
        "reason": "test pending",
        "created_at": "2026-06-16T17:07:33",
        "status": "pending_approval",
    }


def _token(
    *,
    scope: str = "governance",
    action: str = "restart_service",
    target: str = "brain_v9",
    secret: str = TEST_SECRET,
    expires_in_seconds: int = 3600,
    nonce: str = "front-06b-nonce",
) -> str:
    return create_approval_token(
        actor="operator",
        scope=scope,
        action=action,
        target=target,
        expires_in_seconds=expires_in_seconds,
        secret=secret,
        nonce=nonce,
    )


def _add_pending(gate: ExecutionGate, item: dict) -> dict:
    gate._pending.append(item)
    return item


def test_p3_without_token_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    assert gate.approve(item["id"], approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_p3_with_valid_token_accepted():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    approved = gate.approve(item["id"], approval_token=_token(), approval_secret=TEST_SECRET)
    assert approved is item
    assert item["status"] == "approved"
    assert item["signed_approval_validated"] is True
    assert item["signed_approval_actor"] == "operator"
    assert item["signed_approval_scope"] == "governance"
    assert item["signed_approval_target"] == "brain_v9"


def test_expired_token_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    expired = _token(expires_in_seconds=-3600, nonce="front-06b-expired")
    assert gate.approve(item["id"], approval_token=expired, approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_wrong_scope_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(scope="memory", nonce="front-06b-wrong-scope")
    assert gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_wrong_action_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(action="edit_file", nonce="front-06b-wrong-action")
    assert gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_wrong_target_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(target="other_service", nonce="front-06b-wrong-target")
    assert gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_invalid_signature_denied():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(nonce="front-06b-invalid-signature")
    bad_token = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert gate.approve(item["id"], approval_token=bad_token, approval_secret=TEST_SECRET) is None
    assert item["status"] == "pending_approval"


def test_missing_secret_fails_closed():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    assert gate.approve(item["id"], approval_token=_token(nonce="front-06b-no-secret")) is None
    assert item["status"] == "pending_approval"


def test_status_remains_pending_after_failed_approval():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(target="wrong", nonce="front-06b-pending-after-fail")
    gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET)
    assert item["status"] == "pending_approval"


def test_status_becomes_approved_after_valid_token():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    gate.approve(item["id"], approval_token=_token(nonce="front-06b-valid-status"), approval_secret=TEST_SECRET)
    assert item["status"] == "approved"


def test_token_not_returned():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    token = _token(nonce="front-06b-token-not-returned")
    approved = gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET)
    assert token not in str(approved)


def test_secret_not_returned():
    gate = _make_gate()
    item = _add_pending(gate, _pending())
    approved = gate.approve(
        item["id"],
        approval_token=_token(nonce="front-06b-secret-not-returned"),
        approval_secret=TEST_SECRET,
    )
    assert TEST_SECRET not in str(approved)


def test_legacy_non_p3_approval_still_works():
    gate = _make_gate()
    item = _add_pending(gate, _pending(tool="install_package", risk="P2", args={"package": "example"}))
    approved = gate.approve(item["id"])
    assert approved is item
    assert item["status"] == "approved"
    assert "signed_approval_validated" not in item


def test_protected_path_requires_signed_token():
    gate = _make_gate()
    item = _add_pending(gate, _pending(tool="edit_file", risk="P2", args={"path": PROTECTED_TARGET}))
    assert gate.approve(item["id"]) is None
    assert item["status"] == "pending_approval"


def test_protected_path_accepts_valid_signed_token():
    gate = _make_gate()
    item = _add_pending(gate, _pending(tool="edit_file", risk="P2", args={"path": PROTECTED_TARGET}))
    token = _token(action="edit_file", target=PROTECTED_TARGET, nonce="front-06b-protected-valid")
    approved = gate.approve(item["id"], approval_token=token, approval_secret=TEST_SECRET)
    assert approved is item
    assert item["status"] == "approved"
    assert item["signed_approval_validated"] is True
    assert item["signed_approval_target"] == PROTECTED_TARGET
