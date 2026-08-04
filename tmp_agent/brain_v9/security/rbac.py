"""
tmp_agent/brain_v9/security/rbac.py
FRONT-SECURITY-RBAC-MINIMAL-01
BRAIN-101-R2-5-FIVE-ROLE-RBAC-MATRIX-01

Constitutional role-based access control (RBAC) for Brain Lab.
No external dependencies. No file IO. No env reads inside this module.
Roles are determined and passed by api_security.py or unified gate callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Optional


class Role(Enum):
    OWNER = "owner"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"
    READ_ONLY = "read-only"

    # Legacy names retained for compatibility with existing callers/tests.
    VIEWER = "viewer"
    ADMIN = "admin"


class Permission:
    # Read permissions
    READ_STATUS = "read_status"
    READ_HEALTH = "read_health"
    READ_KNOWLEDGE = "read_knowledge"

    # Review / execution / approval permissions
    REVIEW = "review"
    APPROVE = "approve"
    EXECUTE = "execute"
    MANAGE_LIFECYCLE = "manage_lifecycle"
    APPLY_PATCH = "apply_patch"

    # Restricted permissions
    MODIFY_GOVERNANCE = "modify_governance"
    ACCESS_DEV_ENDPOINTS = "access_dev_endpoints"


_READ_PERMISSIONS = frozenset({
    Permission.READ_STATUS,
    Permission.READ_HEALTH,
    Permission.READ_KNOWLEDGE,
})


# Role -> permissions mapping (as frozensets)
_ROLE_PERMISSIONS: Dict[Role, FrozenSet[str]] = {
    Role.OWNER: _READ_PERMISSIONS
    | frozenset({
        Permission.REVIEW,
        Permission.APPROVE,
        Permission.EXECUTE,
        Permission.MANAGE_LIFECYCLE,
        Permission.APPLY_PATCH,
        Permission.MODIFY_GOVERNANCE,
        Permission.ACCESS_DEV_ENDPOINTS,
    }),
    Role.OPERATOR: _READ_PERMISSIONS
    | frozenset({
        Permission.REVIEW,
        Permission.APPROVE,
        Permission.EXECUTE,
        Permission.MANAGE_LIFECYCLE,
    }),
    Role.REVIEWER: _READ_PERMISSIONS
    | frozenset({
        Permission.REVIEW,
        Permission.APPROVE,
    }),
    Role.EXECUTOR: _READ_PERMISSIONS
    | frozenset({
        Permission.EXECUTE,
        Permission.MANAGE_LIFECYCLE,
    }),
    Role.READ_ONLY: _READ_PERMISSIONS,
    Role.VIEWER: _READ_PERMISSIONS,
    Role.ADMIN: _READ_PERMISSIONS
    | frozenset({
        Permission.REVIEW,
        Permission.APPROVE,
        Permission.EXECUTE,
        Permission.MANAGE_LIFECYCLE,
        Permission.APPLY_PATCH,
        Permission.ACCESS_DEV_ENDPOINTS,
    }),
}

_ROLE_RANK: Dict[Role, int] = {
    Role.READ_ONLY: 0,
    Role.VIEWER: 0,
    Role.REVIEWER: 1,
    Role.EXECUTOR: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}

_ROLE_ACTORS: Dict[Role, FrozenSet[str]] = {
    Role.OWNER: frozenset({"owner", "human-owner"}),
    Role.ADMIN: frozenset({"admin", "operator", "human-owner"}),
    Role.OPERATOR: frozenset({"operator", "system", "agent"}),
    Role.REVIEWER: frozenset({"reviewer"}),
    Role.EXECUTOR: frozenset({"executor"}),
    Role.READ_ONLY: frozenset({"read-only", "viewer", "anonymous", "agent", ""}),
    Role.VIEWER: frozenset({"viewer", "anonymous", "agent", ""}),
}

_OPERATION_PERMISSION: Dict[str, str] = {
    "read": Permission.READ_STATUS,
    "approval": Permission.APPROVE,
    "patch": Permission.APPLY_PATCH,
    "dev": Permission.ACCESS_DEV_ENDPOINTS,
    "governance": Permission.MODIFY_GOVERNANCE,
    "lifecycle": Permission.MANAGE_LIFECYCLE,
    "execution": Permission.EXECUTE,
}

_OPERATION_SCOPES: Dict[str, FrozenSet[str]] = {
    "read": frozenset({"read:*", "read:status"}),
    "approval": frozenset({"approval:*", "approval:grant"}),
    "patch": frozenset({"patch:*", "patch:apply"}),
    "dev": frozenset({"dev:*", "dev:access"}),
    "governance": frozenset({"governance:*", "governance:modify"}),
    "lifecycle": frozenset({"lifecycle:*", "lifecycle:run"}),
    "execution": frozenset({"execution:*", "execution:run"}),
}


@dataclass(frozen=True)
class RBACDecision:
    allowed: bool
    role: str
    permission: str
    scope: str
    reason: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def normalize_role(value: Any) -> Role:
    """
    Normalize a raw value into a Role enum.
    Unknown values default to legacy Role.VIEWER, which is permission-equivalent
    to Role.READ_ONLY.
    """
    if isinstance(value, Role):
        return value
    if not isinstance(value, str):
        return Role.VIEWER
    value_clean = str(value).strip().lower().replace("_", "-")
    if value_clean in {"owner", "human-owner"}:
        return Role.OWNER
    if value_clean in {"admin", "root"}:
        return Role.ADMIN
    if value_clean in {"operator", "op", "user"}:
        return Role.OPERATOR
    if value_clean in {"reviewer", "review"}:
        return Role.REVIEWER
    if value_clean in {"executor", "execute"}:
        return Role.EXECUTOR
    if value_clean == "viewer":
        return Role.VIEWER
    if value_clean in {"read-only", "readonly", "read"}:
        return Role.READ_ONLY
    if value_clean in {"guest", "public", "anonymous", "agent"}:
        return Role.VIEWER
    return Role.VIEWER


def role_rank(role: Role | str) -> int:
    return _ROLE_RANK.get(normalize_role(role), 0)


def role_can_act_as(role: Role | str, requested_role: Role | str) -> bool:
    actual_permissions = _ROLE_PERMISSIONS.get(normalize_role(role), frozenset())
    requested_permissions = _ROLE_PERMISSIONS.get(
        normalize_role(requested_role), frozenset()
    )
    return actual_permissions.issuperset(requested_permissions)


def normalize_scope_values(value: Any) -> FrozenSet[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        raw_values = [part.strip().lower() for part in value.split(",")]
    else:
        try:
            raw_values = [str(part).strip().lower() for part in value]
        except TypeError:
            raw_values = [str(value).strip().lower()]
    return frozenset(part.replace("_", "-") for part in raw_values if part)


def required_permission_for_operation(operation_class: str, operation: str = "") -> str:
    op_class = str(operation_class or "").strip().lower()
    op = str(operation or "").strip().lower()
    if op_class == "patch" and (op.endswith("_dry_run") or "dry_run" in op):
        return Permission.READ_STATUS
    return _OPERATION_PERMISSION.get(op_class, Permission.READ_STATUS)


def required_scopes_for_operation(operation_class: str, operation: str = "") -> FrozenSet[str]:
    op_class = str(operation_class or "").strip().lower()
    op = str(operation or "").strip().lower()
    if op_class == "patch" and (op.endswith("_dry_run") or "dry_run" in op):
        return frozenset({"patch:*", "patch:preview", "review:*"})
    return _OPERATION_SCOPES.get(op_class, frozenset({"read:*"}))


def _actor_allowed_for_role(role: Role, actor: str) -> bool:
    normalized_actor = str(actor or "").strip().lower().replace("_", "-")
    return normalized_actor in _ROLE_ACTORS.get(role, frozenset())


def _requested_role_from(args: Mapping[str, Any], context: Mapping[str, Any]) -> Optional[Role]:
    for source in (args, context):
        for key in ("role", "requested_role", "assume_role", "run_as", "effective_role"):
            value = source.get(key)
            if value:
                return normalize_role(value)
    return None


def authorize_governed_operation(
    *,
    role: Role | str,
    operation_class: str,
    operation: str = "",
    actor: str = "",
    authenticated: bool = False,
    scopes: Any = None,
    args: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> RBACDecision:
    """
    Enforce the five-role RBAC matrix for the unified governance gate.

    Scopes are backward-compatible: callers that do not pass a scope list are
    evaluated by role only. If scopes are supplied, one matching scope or a
    wildcard scope is required.
    """
    role_obj = normalize_role(role)
    op_class = str(operation_class or "").strip().lower()
    args_map = args or {}
    context_map = context or {}
    permission = required_permission_for_operation(op_class, operation)
    required_scopes = required_scopes_for_operation(op_class, operation)

    requested_role = _requested_role_from(args_map, context_map)
    if requested_role is not None and not role_can_act_as(role_obj, requested_role):
        return RBACDecision(
            allowed=False,
            role=role_obj.value,
            permission=permission,
            scope=",".join(sorted(required_scopes)),
            error="role_escalation_denied",
            reason="Request attempted to assume a higher role than the authenticated role.",
            metadata={"requested_role": requested_role.value, "actual_role": role_obj.value},
        )

    if op_class != "read" and not authenticated:
        return RBACDecision(
            allowed=False,
            role=role_obj.value,
            permission=permission,
            scope=",".join(sorted(required_scopes)),
            error="authentication_required",
            reason="Governed non-read operation requires authenticated access.",
        )

    if not _actor_allowed_for_role(role_obj, actor):
        return RBACDecision(
            allowed=False,
            role=role_obj.value,
            permission=permission,
            scope=",".join(sorted(required_scopes)),
            error="actor_role_mismatch",
            reason="Actor is not allowed to operate under the supplied role.",
            metadata={"actor": actor, "role": role_obj.value},
        )

    if not has_permission(role_obj, permission):
        return RBACDecision(
            allowed=False,
            role=role_obj.value,
            permission=permission,
            scope=",".join(sorted(required_scopes)),
            error="rbac_permission_denied",
            reason="Role lacks the permission required for this governed operation.",
        )

    supplied_scopes = normalize_scope_values(scopes)
    if supplied_scopes:
        scope_grants = required_scopes | frozenset({"*", f"{op_class}:*"})
        if not (supplied_scopes & scope_grants):
            return RBACDecision(
                allowed=False,
                role=role_obj.value,
                permission=permission,
                scope=",".join(sorted(required_scopes)),
                error="scope_denied",
                reason="Request scope does not authorize this governed operation.",
                metadata={"supplied_scopes": sorted(supplied_scopes)},
            )

    return RBACDecision(
        allowed=True,
        role=role_obj.value,
        permission=permission,
        scope=",".join(sorted(required_scopes)),
        reason="RBAC matrix allowed the governed operation.",
    )


def has_permission(role: Role | str, permission: str) -> bool:
    """
    Check if a role has a specific permission.
    """
    role_obj = normalize_role(role)
    perms = _ROLE_PERMISSIONS.get(role_obj)
    if perms is None:
        return False
    return permission in perms


def require_permission(role: Role | str, permission: str) -> None:
    """
    Raise PermissionError if the role lacks the permission.
    Used for internal enforcement (not HTTP exceptions).
    """
    if not has_permission(role, permission):
        role_name = normalize_role(role).value
        raise PermissionError(
            f"Role '{role_name}' lacks permission '{permission}'."
        )


def role_permissions(role: Role | str) -> FrozenSet[str]:
    """
    Return the full set of permissions for a role.
    """
    role_obj = normalize_role(role)
    return _ROLE_PERMISSIONS.get(role_obj, frozenset())


def classify_request_role(
    *,
    admin_token_valid: bool = False,
    localhost_allowed: bool = False,
) -> Role:
    """
    Classify the request role based on token validity and locality.

    Rules:
    - Valid admin token -> ADMIN (legacy owner-grade authority)
    - Localhost (existing operator behavior) -> OPERATOR
    - Everything else -> VIEWER (legacy read-only authority)

    This function does NOT read env or request objects directly.
    Callers must pass pre-validated booleans.
    """
    if admin_token_valid:
        return Role.ADMIN
    if localhost_allowed:
        return Role.OPERATOR
    return Role.VIEWER
