"""Smoke test for FRONT-SECURITY-RBAC-MINIMAL-01."""

import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure tmp_agent is on sys.path so brain_v9 imports resolve
_TMP_AGENT = str(Path(__file__).resolve().parent.parent.parent / "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)

from brain_v9.security.rbac import (
    Role, Permission, normalize_role, has_permission,
    require_permission, role_permissions, classify_request_role,
)
from brain_v9.api_security import (
    require_operator_access,
    require_strict_operator_access,
    get_request_role,
    require_role,
    require_permission as api_require_permission,
)


def test_unknown_role_normalizes_to_viewer():
    from tmp_agent.brain_v9.security.rbac import normalize_role, Role
    assert normalize_role("unknown") == Role.VIEWER
    assert normalize_role("hacker") == Role.VIEWER
    assert normalize_role(None) == Role.VIEWER
    assert normalize_role(42) == Role.VIEWER


def test_viewer_can_read_status():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.VIEWER, Permission.READ_STATUS) is True
    assert has_permission("viewer", Permission.READ_STATUS) is True


def test_viewer_cannot_approve():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.VIEWER, Permission.APPROVE) is False


def test_viewer_cannot_apply_patch():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.VIEWER, Permission.APPLY_PATCH) is False


def test_operator_can_approve():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.OPERATOR, Permission.APPROVE) is True


def test_operator_cannot_apply_patch():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.OPERATOR, Permission.APPLY_PATCH) is False


def test_operator_cannot_modify_governance():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.OPERATOR, Permission.MODIFY_GOVERNANCE) is False


def test_admin_can_approve():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.ADMIN, Permission.APPROVE) is True


def test_admin_can_apply_patch_permission():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.ADMIN, Permission.APPLY_PATCH) is True


def test_admin_cannot_modify_governance():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    assert has_permission(Role.ADMIN, Permission.MODIFY_GOVERNANCE) is False


def test_rbac_does_not_grant_p3_auto_approval():
    from tmp_agent.brain_v9.security.rbac import Role, has_permission, Permission
    # P3 is not an RBAC permission; it's handled by ExecutionGate
    # This test documents that RBAC does not override P3
    assert Permission.MODIFY_GOVERNANCE not in role_permissions(Role.ADMIN)
    assert Permission.APPLY_PATCH in role_permissions(Role.ADMIN)


def test_brain_admin_token_not_hardcoded():
    # Verify no hardcoded token in api_security.py
    with open("tmp_agent/brain_v9/api_security.py", "r", encoding="utf-8") as f:
        content = f.read()
    # Must use os.getenv, not a literal string assignment
    assert "os.getenv" in content and "BRAIN_ADMIN_TOKEN" in content
    # Ensure no literal token like "sk-..." or hardcoded key string is present
    assert "sk-" not in content or content.count("sk-") <= 0


def test_api_security_imports_cleanly():
    import tmp_agent.brain_v9.api_security as api_sec
    assert callable(api_sec.require_operator_access)
    assert callable(api_sec.require_strict_operator_access)
    assert callable(api_sec.get_request_role)
    assert callable(api_sec.require_role)
    assert callable(api_sec.require_permission)


def test_require_operator_access_still_exists():
    from tmp_agent.brain_v9.api_security import require_operator_access
    assert callable(require_operator_access)


def test_require_strict_operator_access_still_exists():
    from tmp_agent.brain_v9.api_security import require_strict_operator_access
    assert callable(require_strict_operator_access)


def test_get_request_role_exists():
    from tmp_agent.brain_v9.api_security import get_request_role
    assert callable(get_request_role)


def test_require_permission_exists():
    from tmp_agent.brain_v9.api_security import require_permission
    assert callable(require_permission)


def test_require_role_exists():
    from tmp_agent.brain_v9.api_security import require_role
    assert callable(require_role)


def test_no_memory_semantic_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower()


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0


def test_classify_request_role_admin():
    from tmp_agent.brain_v9.security.rbac import classify_request_role, Role
    assert classify_request_role(admin_token_valid=True) == Role.ADMIN


def test_classify_request_role_operator():
    from tmp_agent.brain_v9.security.rbac import classify_request_role, Role
    assert classify_request_role(admin_token_valid=False, localhost_allowed=True) == Role.OPERATOR


def test_classify_request_role_viewer():
    from tmp_agent.brain_v9.security.rbac import classify_request_role, Role
    assert classify_request_role(admin_token_valid=False, localhost_allowed=False) == Role.VIEWER
