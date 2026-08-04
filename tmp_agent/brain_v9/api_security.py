"""
Runtime API security helpers.

Policy:
- localhost and test clients are trusted for operator routes
- non-local mutating requests require X-Brain-Token when BRAIN_ADMIN_TOKEN is set
- if BRAIN_ADMIN_TOKEN is not configured, non-local mutating requests are denied

FRONT-SECURITY-RBAC-MINIMAL-01: Minimal RBAC added without breaking existing auth.
"""
from __future__ import annotations

import os
from hmac import compare_digest
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from tmp_agent.brain_v9.security.rbac import (
    Role,
    Permission,
    classify_request_role,
    has_permission,
    normalize_role,
    role_can_act_as,
    require_permission as _require_rbac_permission,
)


_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _client_host(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return ""
    return str(client.host).split("%", 1)[0].lower()


def is_local_request(request: Request) -> bool:
    return _client_host(request) in _LOCAL_CLIENT_HOSTS


# ── Existing functions preserved (backward compatible) ──

async def require_operator_access(
    request: Request,
    x_brain_token: Optional[str] = Header(default=None, alias="X-Brain-Token"),
) -> None:
    """Require operator access for non-local requests."""
    if is_local_request(request):
        return

    expected = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
    if expected and x_brain_token and compare_digest(x_brain_token, expected):
        return

    detail = (
        "Operator access required for non-local requests. Provide X-Brain-Token."
        if expected
        else "Operator access required for non-local requests. Configure BRAIN_ADMIN_TOKEN or use localhost."
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def require_strict_operator_access(
    request: Request,
    x_brain_token: Optional[str] = Header(default=None, alias="X-Brain-Token"),
) -> None:
    """Strict operator access for administrative endpoints.

    Does NOT allow local address bypass. Requires BRAIN_ADMIN_TOKEN and matching X-Brain-Token.
    """
    expected = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="strict operator token not configured")
    if not x_brain_token or not compare_digest(x_brain_token, expected):
        raise HTTPException(status_code=403, detail="strict operator access required")


# ── New RBAC helpers ──

def _validate_admin_token(x_brain_token: Optional[str]) -> bool:
    """Check if the provided token matches BRAIN_ADMIN_TOKEN."""
    expected = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
    if not expected or not x_brain_token:
        return False
    return compare_digest(x_brain_token, expected)


def get_request_role(
    request: Request,
    x_brain_token: Optional[str] = None,
    x_brain_role: Optional[str] = None,
) -> Role:
    """
    Determine the RBAC role for a request.

    - Valid admin token -> ADMIN by default, or OWNER/lesser requested role
    - Localhost -> OPERATOR (backward compatible with existing behavior)
    - Everything else -> VIEWER (legacy read-only authority)
    """
    admin_token_valid = _validate_admin_token(x_brain_token)
    localhost_allowed = is_local_request(request)
    base_role = classify_request_role(
        admin_token_valid=admin_token_valid,
        localhost_allowed=localhost_allowed,
    )
    if not x_brain_role:
        return base_role
    requested_role = normalize_role(x_brain_role)
    if admin_token_valid and requested_role in {
        Role.OWNER,
        Role.ADMIN,
        Role.OPERATOR,
        Role.REVIEWER,
        Role.EXECUTOR,
        Role.READ_ONLY,
        Role.VIEWER,
    }:
        return requested_role
    if role_can_act_as(base_role, requested_role):
        return requested_role
    return base_role


async def require_role(
    request: Request,
    role: Role | str,
    x_brain_token: Optional[str] = Header(default=None, alias="X-Brain-Token"),
    x_brain_role: Optional[str] = Header(default=None, alias="X-Brain-Role"),
) -> Role:
    """
    FastAPI dependency that enforces a minimum RBAC role.
    Raises 403 if the caller's role is insufficient.
    """
    actual_role = get_request_role(request, x_brain_token, x_brain_role)
    required_role = normalize_role(role)
    if not role_can_act_as(actual_role, required_role):
        raise HTTPException(
            status_code=403,
            detail=f"{required_role.value} access required. Current role: {actual_role.value}",
        )
    return actual_role


async def require_permission(
    request: Request,
    permission: str,
    x_brain_token: Optional[str] = Header(default=None, alias="X-Brain-Token"),
    x_brain_role: Optional[str] = Header(default=None, alias="X-Brain-Role"),
) -> Role:
    """
    FastAPI dependency that enforces a specific RBAC permission.
    Raises 403 if the caller lacks the permission.
    """
    actual_role = get_request_role(request, x_brain_token, x_brain_role)
    if not has_permission(actual_role, permission):
        raise HTTPException(
            status_code=403,
            detail=f"permission '{permission}' denied for role '{actual_role.value}'",
        )
    return actual_role


# Keep existing FastAPI dependency aliases
OperatorAccess = Annotated[None, Depends(require_operator_access)]
StrictOperatorAccess = Annotated[None, Depends(require_strict_operator_access)]
