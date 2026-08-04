from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

from brain_v9.governance.unified_gate import evaluate_governed_operation
from brain_v9.api_security import get_request_role
from brain_v9.security.rbac import Permission, Role, has_permission, role_permissions
from starlette.requests import Request
from tmp_agent.brain_v9.security.rbac import (
    Permission as ApiPermission,
    Role as ApiRole,
    has_permission as api_has_permission,
)


def _decision(
    *,
    role: str,
    actor: str,
    operation_class: str,
    operation: str,
    authenticated: bool = True,
    scopes: list[str] | None = None,
    args: dict | None = None,
):
    return evaluate_governed_operation(
        operation_class=operation_class,
        operation=operation,
        mode="build",
        risk_level="P2" if operation_class != "read" else "P0",
        actor=actor,
        role=role,
        args=args or {},
        authenticated=authenticated,
        context={"scopes": scopes} if scopes is not None else {},
    )


def test_five_constitutional_roles_have_distinct_permission_sets():
    assert Permission.MODIFY_GOVERNANCE in role_permissions(Role.OWNER)
    assert Permission.MODIFY_GOVERNANCE not in role_permissions(Role.ADMIN)
    assert Permission.APPLY_PATCH not in role_permissions(Role.OPERATOR)
    assert has_permission(Role.REVIEWER, Permission.APPROVE) is True
    assert has_permission(Role.REVIEWER, Permission.EXECUTE) is False
    assert has_permission(Role.EXECUTOR, Permission.EXECUTE) is True
    assert has_permission(Role.EXECUTOR, Permission.APPROVE) is False
    assert role_permissions(Role.READ_ONLY) == frozenset({
        Permission.READ_STATUS,
        Permission.READ_HEALTH,
        Permission.READ_KNOWLEDGE,
    })


def test_unified_gate_allows_only_the_expected_role_resource_matrix():
    allowed_cases = [
        ("read-only", "anonymous", "read", "status_read", False, ["read:status"]),
        ("reviewer", "reviewer", "patch", "file_patch_dry_run", True, ["patch:preview"]),
        ("executor", "executor", "execution", "approved_action_execute", True, ["execution:run"]),
        ("operator", "operator", "lifecycle", "maintenance_action", True, ["lifecycle:run"]),
        ("owner", "owner", "governance", "policy_update", True, ["governance:modify"]),
    ]

    for role, actor, operation_class, operation, authenticated, scopes in allowed_cases:
        decision = _decision(
            role=role,
            actor=actor,
            operation_class=operation_class,
            operation=operation,
            authenticated=authenticated,
            scopes=scopes,
        )
        assert decision.allowed is True, decision.to_dict()


def test_wrong_role_wrong_actor_wrong_scope_anonymous_and_escalation_are_denied():
    wrong_role = _decision(
        role="reviewer",
        actor="reviewer",
        operation_class="execution",
        operation="approved_action_execute",
        scopes=["execution:run"],
    )
    assert wrong_role.allowed is False
    assert wrong_role.error == "rbac_permission_denied"

    wrong_actor = _decision(
        role="operator",
        actor="reviewer",
        operation_class="execution",
        operation="approved_action_execute",
        scopes=["execution:run"],
    )
    assert wrong_actor.allowed is False
    assert wrong_actor.error == "actor_role_mismatch"

    wrong_scope = _decision(
        role="executor",
        actor="executor",
        operation_class="execution",
        operation="approved_action_execute",
        scopes=["read:status"],
    )
    assert wrong_scope.allowed is False
    assert wrong_scope.error == "scope_denied"

    anonymous = _decision(
        role="executor",
        actor="executor",
        operation_class="execution",
        operation="approved_action_execute",
        authenticated=False,
        scopes=["execution:run"],
    )
    assert anonymous.allowed is False
    assert anonymous.error == "authentication_required"

    escalation = _decision(
        role="executor",
        actor="executor",
        operation_class="execution",
        operation="approved_action_execute",
        scopes=["execution:run"],
        args={"requested_role": "owner"},
    )
    assert escalation.allowed is False
    assert escalation.error == "role_escalation_denied"


def test_unified_gate_preserves_disabled_constitutional_invariants():
    decision = _decision(
        role="owner",
        actor="owner",
        operation_class="execution",
        operation="live_trading_attempt",
        scopes=["execution:run"],
        args={"live_trading": True, "real_money": True, "auto_merge": True},
    )

    assert decision.allowed is False
    assert decision.error == "forbidden_request_field"
    assert decision.human_final_authority is True
    assert decision.live_trading_disabled is True
    assert decision.real_money_disabled is True
    assert decision.canonical_sync_disabled is True
    assert decision.auto_merge_disabled is True


def test_admin_token_cannot_assume_owner_authority(monkeypatch):
    monkeypatch.setenv("BRAIN_ADMIN_TOKEN", "contract-admin-token")
    request = Request({"type": "http", "client": ("203.0.113.10", 443)})

    role = get_request_role(
        request,
        x_brain_token="contract-admin-token",
        x_brain_role="owner",
    )

    assert role is ApiRole.ADMIN
    assert api_has_permission(role, ApiPermission.MODIFY_GOVERNANCE) is False
