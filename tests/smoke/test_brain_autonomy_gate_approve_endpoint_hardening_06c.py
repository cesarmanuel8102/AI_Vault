"""FRONT 06C smoke tests: harden /gate/approve/{pending_id} endpoint.

Tests verify that P3/protected-path pending approvals require a valid signed
approval token before the endpoint executes a tool with _bypass_gate=True.

Strategy:
- FastAPI TestClient against main.app (imported as tmp_agent.brain_v9.main).
- Override require_strict_operator_access so tests can run without BRAIN_ADMIN_TOKEN.
- Monkeypatch build_standard_executor to a fake executor that records tool calls.
- One test exercises the real ExecutionGate + real signed token path to avoid
  faking the core safety property.
"""
from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from tmp_agent.brain_v9.main import app  # noqa: E402
import tmp_agent.brain_v9.api_security as _api_security  # noqa: E402
from tmp_agent.brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode  # noqa: E402
from tmp_agent.brain_v9.governance.signed_approvals import TEST_SECRET, create_approval_token  # noqa: E402

async def _require_strict_operator_access_passthrough(request, x_brain_token=None):
    """Test-only override: bypass strict operator token for gate endpoint tests."""
    return None


@pytest.fixture(autouse=True, scope="module")
def _override_strict_operator_access():
    import brain_v9.api_security

    original_code = brain_v9.api_security.require_strict_operator_access.__code__
    brain_v9.api_security.require_strict_operator_access.__code__ = _require_strict_operator_access_passthrough.__code__
    yield
    brain_v9.api_security.require_strict_operator_access.__code__ = original_code


client = TestClient(app)


def _make_pending(tool="restart_service", risk="P3", args=None):
    return {
        "id": "pending-06c-test",
        "tool": tool,
        "args": args if args is not None else {"service": "brain_v9"},
        "risk": risk,
        "reason": "test pending",
        "created_at": "2026-06-28T12:00:00",
        "status": "pending_approval",
    }


def _make_token(*, action="restart_service", target="brain_v9", nonce="06c-token", scope="governance"):
    return create_approval_token(
        actor="operator",
        scope=scope,
        action=action,
        target=target,
        expires_in_seconds=3600,
        secret=TEST_SECRET,
        nonce=nonce,
    )


class FakeExecutor:
    """Executor mock that exposes one tool and records invocations."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.calls = []
        self._tools = {tool_name: {"func": self._tool_func}}

    def _tool_func(self, **kwargs):
        self.calls.append(kwargs)
        return "executed"


def _patch_gate(monkeypatch, pending_item, requires_signed=False):
    """Patch get_gate() so approve() returns pending_item."""
    class FakeGate:
        def approve(self, pending_id, approval_token=None, approval_secret=None):
            return pending_item

        def _pending_requires_signed_approval(self, item):
            return requires_signed

    monkeypatch.setattr("brain_v9.governance.execution_gate.get_gate", lambda: FakeGate())


def test_p3_without_token_denied(monkeypatch):
    item = _make_pending()
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    response = client.post("/gate/approve/pending-06c-test", json={})
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert fake.calls == []


def test_p3_with_invalid_token_denied(monkeypatch):
    item = _make_pending()
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": "invalid-token"},
    )
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert fake.calls == []


def test_p3_with_valid_token_executes(monkeypatch):
    item = _make_pending()
    item["signed_approval_validated"] = True
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    token = _make_token(nonce="06c-valid")
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data.get("signed_approval_validated") is True
    assert len(fake.calls) == 1
    assert fake.calls[0].get("_bypass_gate") is True


def test_p3_approved_but_validation_missing_denied(monkeypatch):
    item = _make_pending()
    item["status"] = "approved"
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    response = client.post("/gate/approve/pending-06c-test", json={})
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert response.json().get("signed_approval_validated") is False
    assert fake.calls == []


def test_protected_path_without_token_denied(monkeypatch):
    item = _make_pending(
        tool="edit_file",
        risk="P2",
        args={"path": "tmp_agent/brain_v9/governance/execution_gate.py"},
    )
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    response = client.post("/gate/approve/pending-06c-test", json={})
    assert response.status_code == 403
    assert response.json()["success"] is False
    assert fake.calls == []


def test_protected_path_with_valid_token_executes(monkeypatch):
    item = _make_pending(
        tool="edit_file",
        risk="P2",
        args={"path": "tmp_agent/brain_v9/governance/execution_gate.py"},
    )
    item["signed_approval_validated"] = True
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    token = _make_token(
        action="edit_file",
        target="tmp_agent/brain_v9/governance/execution_gate.py",
        nonce="06c-prot",
    )
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": token},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert len(fake.calls) == 1
    assert fake.calls[0].get("_bypass_gate") is True


def test_legacy_low_risk_works_without_token(monkeypatch):
    item = _make_pending(tool="install_package", risk="P2", args={"package": "pytest"})
    _patch_gate(monkeypatch, item, requires_signed=False)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    response = client.post("/gate/approve/pending-06c-test", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(fake.calls) == 1
    assert fake.calls[0].get("_bypass_gate") is True


def test_response_does_not_include_token(monkeypatch):
    item = _make_pending()
    item["signed_approval_validated"] = True
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    token = _make_token(nonce="06c-no-leak")
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": token},
    )
    assert response.status_code == 200
    assert token not in response.text


def test_response_does_not_include_secret(monkeypatch):
    item = _make_pending()
    item["signed_approval_validated"] = True
    _patch_gate(monkeypatch, item, requires_signed=True)
    fake = FakeExecutor(item["tool"])
    monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: fake)
    token = _make_token(nonce="06c-no-secret-leak")
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": token},
    )
    assert response.status_code == 200
    assert TEST_SECRET not in response.text


def test_real_p3_approve_requires_valid_token(monkeypatch):
    """Real ExecutionGate path: P3 without token stays pending; valid token approves."""
    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._audit = []
    gate._god_sessions = set()
    gate._save_state = lambda: None
    gate._audit_log = lambda *args, **kwargs: None
    gate._expire_stale_pending = lambda: 0

    # Use a tool that accepts arbitrary kwargs so _bypass_gate injection works
    item = _make_pending(tool="place_paper_order", args={"symbol": "AAPL", "action": "buy", "quantity": 1})
    gate._pending.append(item)

    monkeypatch.setattr("brain_v9.governance.execution_gate.get_gate", lambda: gate)
    # Provide the test secret via environment so gate.approve can verify the token
    import os
    monkeypatch.setenv("BRAIN_SIGNED_APPROVAL_SECRET", TEST_SECRET)

    response = client.post("/gate/approve/pending-06c-test", json={})
    assert response.status_code == 403
    assert item["status"] == "pending_approval"

    token = _make_token(
        action="place_paper_order",
        target="place_paper_order",
        nonce="06c-real-valid",
    )
    response = client.post(
        "/gate/approve/pending-06c-test",
        json={"approval_token": token},
    )
    assert response.status_code == 200
    assert item["status"] == "approved"
    assert item["signed_approval_validated"] is True
