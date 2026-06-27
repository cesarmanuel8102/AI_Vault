"""
Signed Approval Module for Brain/Agent Autonomy
FRONT-BRAIN-AUTONOMY-CRYPTO-APPROVALS-05

Provides HMAC-SHA256 based signed approval tokens with:
- Scope, action, target binding
- Expiration
- Nonce for replay protection
- No external dependencies (stdlib only)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import secrets
from typing import Dict, Optional, Set, Any


class SignedApprovalError(Exception):
    """Base exception for signed approval errors."""
    pass


class ApprovalExpiredError(SignedApprovalError):
    pass


class InvalidSignatureError(SignedApprovalError):
    pass


class InvalidScopeError(SignedApprovalError):
    pass


class InvalidActionError(SignedApprovalError):
    pass


class InvalidTargetError(SignedApprovalError):
    pass


class ReplayDetectedError(SignedApprovalError):
    pass


def _hmac_sha256(secret: str, message: str) -> str:
    """Compute HMAC-SHA256 signature."""
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _create_payload(
    actor: str,
    scope: str,
    action: str,
    target: str,
    expires_in_seconds: int,
    nonce: str,
) -> Dict[str, Any]:
    """Create the token payload."""
    now = int(time.time())
    return {
        "actor": actor,
        "scope": scope,
        "action": action,
        "target": target,
        "issued_at": now,
        "expires_at": now + expires_in_seconds,
        "nonce": nonce,
    }


def _payload_to_string(payload: Dict[str, Any]) -> str:
    """Convert payload to deterministic string for signing."""
    # Sort keys for deterministic ordering
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def create_approval_token(
    actor: str,
    scope: str,
    action: str,
    target: str,
    expires_in_seconds: int,
    secret: str,
    nonce: Optional[str] = None,
) -> str:
    """
    Create a signed approval token.

    Args:
        actor: Who is requesting approval (e.g., "operator", "selfdev")
        scope: Permission scope (e.g., "governance", "security", "memory")
        action: Action being approved (e.g., "edit_file", "promote_staged_change")
        target: Target resource (e.g., "tmp_agent/brain_v9/governance/execution_gate.py")
        expires_in_seconds: Token lifetime in seconds
        secret: HMAC secret (must be kept secure, not logged)
        nonce: Optional nonce for replay protection (generated if not provided)

    Returns:
        Token string: base64url(payload).signature
    """
    if nonce is None:
        nonce = secrets.token_urlsafe(16)

    payload = _create_payload(actor, scope, action, target, expires_in_seconds, nonce)
    payload_str = _payload_to_string(payload)
    signature = _hmac_sha256(secret, payload_str)

    import base64
    token_b64 = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip("=")
    return f"{token_b64}.{signature}"


def verify_approval_token(
    token: str,
    expected_scope: str,
    expected_action: str,
    expected_target: str,
    secret: str,
    used_nonces: Optional[Set[str]] = None,
    clock_skew_seconds: int = 60,
) -> Dict[str, Any]:
    """
    Verify a signed approval token.

    Args:
        token: Token string to verify
        expected_scope: Expected scope value
        expected_action: Expected action value
        expected_target: Expected target value
        secret: HMAC secret for verification
        used_nonces: Optional set of already-used nonces for replay protection
        clock_skew_seconds: Allowed clock skew for expiration check

    Returns:
        Dict with verification result:
        {
            "valid": bool,
            "reason": str,
            "actor": str,
            "scope": str,
            "action": str,
            "target": str,
            "expires_at": int,
            "nonce": str,
            "replay_detected": bool
        }
    """
    if not token or "." not in token:
        return {"valid": False, "reason": "Invalid token format"}

    try:
        token_b64, signature = token.rsplit(".", 1)

        import base64
        # Add padding if needed
        padding = "=" * ((4 - len(token_b64) % 4) % 4)
        payload_str = base64.urlsafe_b64decode(token_b64 + padding).decode()
        payload = json.loads(payload_str)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {"valid": False, "reason": "Invalid token encoding"}

    # Verify signature
    expected_sig = _hmac_sha256(secret, payload_str)
    if not hmac.compare_digest(signature, expected_sig):
        return {"valid": False, "reason": "Invalid signature"}

    # Check expiration
    now = int(time.time())
    expires_at = payload.get("expires_at", 0)
    if expires_at + clock_skew_seconds < now:
        return {"valid": False, "reason": "Token expired"}

    # Check scope
    if payload.get("scope") != expected_scope:
        return {"valid": False, "reason": f"Invalid scope: expected {expected_scope}, got {payload.get('scope')}"}

    # Check action
    if payload.get("action") != expected_action:
        return {"valid": False, "reason": f"Invalid action: expected {expected_action}, got {payload.get('action')}"}

    # Check target
    if payload.get("target") != expected_target:
        return {"valid": False, "reason": f"Invalid target: expected {expected_target}, got {payload.get('target')}"}

    # Check replay
    nonce = payload.get("nonce", "")
    replay_detected = False
    if used_nonces is not None:
        if nonce in used_nonces:
            replay_detected = True
            return {
                "valid": False,
                "reason": "Replay detected: nonce already used",
                "replay_detected": True
            }
        used_nonces.add(nonce)

    return {
        "valid": True,
        "reason": "Token valid",
        "actor": payload.get("actor", ""),
        "scope": payload.get("scope", ""),
        "action": payload.get("action", ""),
        "target": payload.get("target", ""),
        "expires_at": payload.get("expires_at", 0),
        "nonce": nonce,
        "replay_detected": replay_detected,
    }


class ApprovalTokenManager:
    """
    Manager for signed approval tokens with replay protection.
    """

    def __init__(self, secret: str, max_used_nonces: int = 10000):
        self.secret = secret
        self.used_nonces: Set[str] = set()
        self.max_used_nonces = max_used_nonces

    def create_token(
        self,
        actor: str,
        scope: str,
        action: str,
        target: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Create a new approval token."""
        nonce = secrets.token_urlsafe(16)
        return create_approval_token(
            actor=actor,
            scope=scope,
            action=action,
            target=target,
            expires_in_seconds=expires_in_seconds,
            secret=self.secret,
            nonce=nonce,
        )

    def verify_token(
        self,
        token: str,
        expected_scope: str,
        expected_action: str,
        expected_target: str,
    ) -> Dict[str, Any]:
        """Verify a token with replay protection."""
        return verify_approval_token(
            token=token,
            expected_scope=expected_scope,
            expected_action=expected_action,
            expected_target=expected_target,
            secret=self.secret,
            used_nonces=self.used_nonces,
        )

    def _prune_nonces(self):
        """Prune old nonces if set grows too large."""
        if len(self.used_nonces) > self.max_used_nonces:
            # Keep only the newest half
            # Note: This is a simple approach; in production use a more sophisticated structure
            self.used_nonces = set(list(self.used_nonces)[-self.max_used_nonces // 2:])


# Test-only deterministic secret for tests
TEST_SECRET = "test-secret-do-not-use-in-production"
TEST_NONCE_SET: Set[str] = set()


def _test_create_token(
    actor: str = "operator",
    scope: str = "governance",
    action: str = "edit_file",
    target: str = "tmp_agent/brain_v9/governance/execution_gate.py",
    expires_in_seconds: int = 3600,
) -> str:
    """Create a test token with deterministic values."""
    return create_approval_token(
        actor=actor,
        scope=scope,
        action=action,
        target=target,
        expires_in_seconds=expires_in_seconds,
        secret=TEST_SECRET,
        nonce="test-nonce-123",
    )


def _test_verify_token(
    token: str,
    expected_scope: str = "governance",
    expected_action: str = "edit_file",
    expected_target: str = "tmp_agent/brain_v9/governance/execution_gate.py",
) -> Dict[str, Any]:
    """Verify a test token."""
    return verify_approval_token(
        token=token,
        expected_scope=expected_scope,
        expected_action=expected_action,
        expected_target=expected_target,
        secret=TEST_SECRET,
        used_nonces=TEST_NONCE_SET,
    )