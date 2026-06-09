"""
tmp_agent/brain_v9/security/rbac.py
FRONT-SECURITY-RBAC-MINIMAL-01

Minimal role-based access control (RBAC) for Brain Lab.
No external dependencies. No file IO. No env reads inside this module.
Roles are determined and passed by api_security.py.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Any, Dict, FrozenSet


@unique
class Role(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Permission:
    # Read permissions
    READ_STATUS = "read_status"
    READ_HEALTH = "read_health"
    READ_KNOWLEDGE = "read_knowledge"

    # Write / approval permissions
    APPROVE = "approve"
    APPLY_PATCH = "apply_patch"

    # Restricted permissions
    MODIFY_GOVERNANCE = "modify_governance"
    ACCESS_DEV_ENDPOINTS = "access_dev_endpoints"


# Role → permissions mapping (as frozensets)
_ROLE_PERMISSIONS: Dict[Role, FrozenSet[str]] = {
    Role.VIEWER: frozenset({
        Permission.READ_STATUS,
        Permission.READ_HEALTH,
        Permission.READ_KNOWLEDGE,
    }),
    Role.OPERATOR: frozenset({
        Permission.READ_STATUS,
        Permission.READ_HEALTH,
        Permission.READ_KNOWLEDGE,
        Permission.APPROVE,
    }),
    Role.ADMIN: frozenset({
        Permission.READ_STATUS,
        Permission.READ_HEALTH,
        Permission.READ_KNOWLEDGE,
        Permission.APPROVE,
        Permission.APPLY_PATCH,
        Permission.ACCESS_DEV_ENDPOINTS,
    }),
}

# Note: MODIFY_GOVERNANCE is not granted to any role by default.
# It remains blocked at the ExecutionGate / self-dev protection layer.


def normalize_role(value: Any) -> Role:
    """
    Normalize a raw value into a Role enum.
    Unknown values default to Role.VIEWER.
    """
    if isinstance(value, Role):
        return value
    if not isinstance(value, str):
        return Role.VIEWER
    value_clean = str(value).strip().lower()
    if value_clean in ("admin", "root"):
        return Role.ADMIN
    if value_clean in ("operator", "op", "user"):
        return Role.OPERATOR
    if value_clean in ("viewer", "guest", "public"):
        return Role.VIEWER
    return Role.VIEWER


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
    - Valid admin token -> ADMIN
    - Localhost (existing operator behavior) -> OPERATOR
    - Everything else -> VIEWER

    This function does NOT read env or request objects directly.
    Callers must pass pre-validated booleans.
    """
    if admin_token_valid:
        return Role.ADMIN
    if localhost_allowed:
        return Role.OPERATOR
    return Role.VIEWER
