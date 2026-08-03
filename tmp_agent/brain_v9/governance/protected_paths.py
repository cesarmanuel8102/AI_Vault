"""
tmp_agent/brain_v9/governance/protected_paths.py
FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01

Centralized protected path classification for Brain Lab.
Pure Python. No file IO. No env reads.
Self-dev, RBAC admin, and GOD mode cannot override these paths.
"""

from __future__ import annotations

from typing import Dict, Tuple


# Path prefixes that are always protected from self-dev / automatic writes
_PROTECTED_PATH_PATTERNS: Tuple[str, ...] = (
    ".env",
    ".dev_auth/",
    "memory/semantic/",
    "tmp_agent/brain_v9/governance/",
    "brain_v9/governance/",
    "governance/",
    "tmp_agent/brain_v9/security/",
    "brain_v9/security/",
    "security/",
    "tmp_agent/brain_v9/core/session.py",
    "brain_v9/core/session.py",
    "core/session.py",
    "session.py",
    "brain/curated_runtime_lookup.py",
    "curated_runtime_lookup.py",
    # Preserve the Agent V2 self-development protections that predate the
    # unified gate. These are exact repo paths, not broad directory blocks.
    "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/governance.py",
    "scripts/git_hygiene/check_no_sensitive_paths_staged.py",
    "tests/smoke/_accepted_runtime_baseline.py",
    "tests/smoke/test_agent_v2_auth_endpoints_01.py",
    "tests/smoke/test_governance_rbac_dev_god_hardening_01.py",
    ".gitignore",
)

# Exact basenames that are always protected regardless of directory
_PROTECTED_EXACT_BASENAMES: Tuple[str, ...] = (
    "api_security.py",
    "trace_redactor.py",
    "execution_gate.py",
    "ethics_kernel.py",
)

# Basename substrings that trigger protection (preserves existing ExecutionGate behavior)
_PROTECTED_BASENAME_TOKENS: Tuple[str, ...] = (
    "execution_gate",
    "ethics_kernel",
    "api_security",
    "trace_redactor",
    "approval",
    "auth",
    "policy",
    "governance",
)

# Paths allowed only during explicit ledger update phases
_LEDGER_ALLOWED_PATHS: Tuple[str, ...] = (
    "ROADMAP_STATUS.json",
    "docs/MIGRATION_CONTROL_LEDGER.md",
)


def normalize_repo_path(raw: str) -> str:
    """
    Normalize a raw path string for repository-level comparison.

    - Backslashes -> forward slashes
    - Lowercase
    - Strip absolute markers (C:/AI_VAULT/, /AI_VAULT/, ./)
    - Strip leading /
    """
    if not raw:
        return ""
    s = str(raw).replace("\\", "/").strip().lower()
    for marker in ("c:/ai_vault/", "/ai_vault/", "./"):
        if s.startswith(marker):
            s = s[len(marker):]
    s = s.lstrip("/")
    return s


def is_protected_path(path: str) -> bool:
    """
    Return True if the path is protected from self-dev / automatic writes.

    Checks exact basenames, protected prefixes, and basename tokens.
    """
    s = normalize_repo_path(path)
    if not s:
        return False

    base = s.rsplit("/", 1)[-1]

    # Exact basename match
    if base in _PROTECTED_EXACT_BASENAMES:
        return True

    # Basename token match (preserves legacy behavior)
    for token in _PROTECTED_BASENAME_TOKENS:
        if token in base:
            return True

    # Prefix match
    for pattern in _PROTECTED_PATH_PATTERNS:
        pat = pattern.lower().rstrip("/")
        if s.startswith(pat + "/") or s == pat:
            return True

    return False


def is_ledger_path(path: str) -> bool:
    """
    Return True if the path is a ledger file allowed during explicit ledger fronts.
    """
    s = normalize_repo_path(path)
    for ledger_path in _LEDGER_ALLOWED_PATHS:
        if s == ledger_path.lower().replace("\\", "/"):
            return True
    return False


def assert_not_protected_path(path: str, *, allow_ledger: bool = False) -> None:
    """
    Raise PermissionError if the path is protected.

    If allow_ledger is True, ledger paths are permitted.
    """
    if is_ledger_path(path) and allow_ledger:
        return
    if is_protected_path(path):
        raise PermissionError(
            f"Protected path modification denied: {path}. "
            "Requires explicit human approval via a dedicated front."
        )


def classify_path_protection(path: str) -> Dict[str, any]:
    """
    Classify a path and return a metadata dict.
    """
    s = normalize_repo_path(path)
    base = s.rsplit("/", 1)[-1] if s else ""

    reason = "not_protected"
    if base in _PROTECTED_EXACT_BASENAMES:
        reason = "exact_basename_match"
    elif any(token in base for token in _PROTECTED_BASENAME_TOKENS):
        reason = "basename_token_match"
    elif is_protected_path(path):
        reason = "prefix_match"

    return {
        "path": path,
        "normalized": s,
        "is_protected": is_protected_path(path),
        "is_ledger": is_ledger_path(path),
        "reason": reason,
    }
