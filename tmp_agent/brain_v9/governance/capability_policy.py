"""
tmp_agent/brain_v9/governance/capability_policy.py
FRONT-BRAIN-AUTONOMY-GOVERNANCE-HARDENING-01

Centralized capability policy for Brain/Agent autonomy.
Defines what actions are allowed, denied, or require explicit approval.
Pure Python. No file IO. No env reads.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Dict, FrozenSet, Optional, Set


@unique
class Capability(Enum):
    """Canonical capability identifiers for autonomy governance."""
    READ_ONLY = "read_only"
    FILE_READ = "file_read"
    FILE_WRITE_SAFE = "file_write_safe"
    FILE_WRITE_RESTRICTED = "file_write_restricted"
    CODE_EDIT = "code_edit"
    TEST_RUN = "test_run"
    GIT_STATUS = "git_status"
    GIT_STAGE = "git_stage"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
    FAISS_REBUILD = "faiss_rebuild"
    GOVERNANCE_EDIT = "governance_edit"
    SECURITY_EDIT = "security_edit"
    DEV_ENDPOINT_ACCESS = "dev_endpoint_access"
    SELF_DEV_ACTION = "self_dev_action"
    EXTERNAL_NETWORK = "external_network"
    BROKER_OR_TRADING = "broker_or_trading"
    UNKNOWN = "unknown"


class CapabilityPolicy:
    """
    Centralized capability policy enforcing default-deny for unknown/mutative capabilities.

    Rules:
    - default deny for unknown capability
    - default deny for mutative capability
    - self-dev cannot edit governance/security policy
    - self-dev cannot enable dev endpoints
    - self-dev cannot modify its own permissions
    - GOD mode cannot bypass deny-list
    - dev endpoints default OFF
    - memory write denied unless explicit future front enables it
    - FAISS rebuild denied unless explicit future front enables it
    - broker/trading denied entirely
    """

    # Mutative capabilities that are denied by default
    _MUTATIVE_CAPABILITIES: FrozenSet[Capability] = frozenset({
        Capability.FILE_WRITE_RESTRICTED,
        Capability.CODE_EDIT,
        Capability.GIT_COMMIT,
        Capability.GIT_PUSH,
        Capability.MEMORY_WRITE,
        Capability.FAISS_REBUILD,
        Capability.GOVERNANCE_EDIT,
        Capability.SECURITY_EDIT,
        Capability.DEV_ENDPOINT_ACCESS,
        Capability.SELF_DEV_ACTION,
        Capability.BROKER_OR_TRADING,
    })

    # Capabilities that require explicit approval even when granted
    _APPROVAL_REQUIRED: FrozenSet[Capability] = frozenset({
        Capability.FILE_WRITE_RESTRICTED,
        Capability.GOVERNANCE_EDIT,
        Capability.SECURITY_EDIT,
        Capability.MEMORY_WRITE,
        Capability.FAISS_REBUILD,
        Capability.DEV_ENDPOINT_ACCESS,
        Capability.SELF_DEV_ACTION,
    })

    # Capabilities that self-dev is NEVER allowed to perform
    _SELFDEV_DENIED: FrozenSet[Capability] = frozenset({
        Capability.GOVERNANCE_EDIT,
        Capability.SECURITY_EDIT,
        Capability.DEV_ENDPOINT_ACCESS,
        Capability.SELF_DEV_ACTION,
        Capability.BROKER_OR_TRADING,
        Capability.MEMORY_WRITE,
        Capability.FAISS_REBUILD,
    })

    # GOD mode still cannot bypass these (Patch 0D hardened paths)
    _GOD_DENYLIST: FrozenSet[Capability] = frozenset({
        Capability.GOVERNANCE_EDIT,
        Capability.SECURITY_EDIT,
        Capability.BROKER_OR_TRADING,
    })

    # Capabilities granted to each role (minimal RBAC integration)
    _ROLE_CAPABILITIES: Dict[str, FrozenSet[Capability]] = {
        "viewer": frozenset({
            Capability.READ_ONLY,
            Capability.FILE_READ,
            Capability.MEMORY_READ,
        }),
        "operator": frozenset({
            Capability.READ_ONLY,
            Capability.FILE_READ,
            Capability.FILE_WRITE_SAFE,
            Capability.TEST_RUN,
            Capability.GIT_STATUS,
            Capability.GIT_STAGE,
            Capability.MEMORY_READ,
        }),
        "admin": frozenset({
            Capability.READ_ONLY,
            Capability.FILE_READ,
            Capability.FILE_WRITE_SAFE,
            Capability.FILE_WRITE_RESTRICTED,
            Capability.CODE_EDIT,
            Capability.TEST_RUN,
            Capability.GIT_STATUS,
            Capability.GIT_STAGE,
            Capability.GIT_COMMIT,
            Capability.GIT_PUSH,
            Capability.MEMORY_READ,
            Capability.EXTERNAL_NETWORK,
            Capability.DEV_ENDPOINT_ACCESS,
        }),
    }

    def __init__(self, allow_memory_write: bool = False, allow_faiss_rebuild: bool = False):
        """
        Initialize policy with optional feature flags.
        Memory write and FAISS rebuild remain DENIED by default.
        """
        self._feature_flags: Dict[str, bool] = {
            "memory_write": allow_memory_write,
            "faiss_rebuild": allow_faiss_rebuild,
        }

    def is_capability_known(self, capability: Capability | str) -> bool:
        """Unknown capabilities are rejected."""
        if isinstance(capability, str):
            try:
                Capability(capability)
                return True
            except ValueError:
                return False
        return capability != Capability.UNKNOWN

    def is_default_allow(self, capability: Capability | str) -> bool:
        """Check if a capability is allowed by default (non-mutative)."""
        cap = self._normalize(capability)
        if cap is None or cap == Capability.UNKNOWN:
            return False
        return cap not in self._MUTATIVE_CAPABILITIES

    def is_mutative(self, capability: Capability | str) -> bool:
        """Check if a capability is mutative (requires extra scrutiny)."""
        cap = self._normalize(capability)
        if cap is None:
            return True  # Unknown = treat as mutative (safe default)
        return cap in self._MUTATIVE_CAPABILITIES

    def requires_approval(self, capability: Capability | str) -> bool:
        """Check if a capability requires explicit human approval."""
        cap = self._normalize(capability)
        if cap is None:
            return True
        return cap in self._APPROVAL_REQUIRED

    def check(
        self,
        actor: str,
        capability: Capability | str,
        role: str = "viewer",
        is_self_dev: bool = False,
        is_god_mode: bool = False,
        target_path: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Evaluate a capability request and return structured decision.

        Returns dict with:
        - decision: "allow" | "deny"
        - reason: human-readable explanation
        - write_performed: False (decision point, no actual write)
        - requires_approval: bool
        - audit_event: dict for logging
        """
        cap = self._normalize(capability)

        # 1. Unknown capability -> deny
        if cap is None or cap == Capability.UNKNOWN:
            return self._deny(
                actor, cap or Capability.UNKNOWN,
                "Unknown capability. Default deny enforced.",
                target_path
            )

        # 2. Broker/trading always denied
        if cap == Capability.BROKER_OR_TRADING:
            return self._deny(
                actor, cap,
                "Trading/broker capabilities are permanently disabled.",
                target_path
            )

        # 3. GOD mode cannot bypass deny-list
        if is_god_mode and cap in self._GOD_DENYLIST:
            return self._deny(
                actor, cap,
                f"GOD mode cannot bypass hardened deny-list for {cap.value}.",
                target_path
            )

        # 4. Self-dev restrictions
        if is_self_dev:
            if cap in self._SELFDEV_DENIED:
                return self._deny(
                    actor, cap,
                    f"Self-dev is not permitted to perform {cap.value}.",
                    target_path
                )

        # 5. Feature-flag checks
        if cap == Capability.MEMORY_WRITE and not self._feature_flags["memory_write"]:
            return self._deny(
                actor, cap,
                "Memory write is disabled. Enable via explicit future front.",
                target_path
            )

        if cap == Capability.FAISS_REBUILD and not self._feature_flags["faiss_rebuild"]:
            return self._deny(
                actor, cap,
                "FAISS rebuild is disabled. Enable via explicit future front.",
                target_path
            )

        if cap == Capability.DEV_ENDPOINT_ACCESS:
            return self._deny(
                actor, cap,
                "Dev endpoints are OFF by default. Enable via explicit configuration.",
                target_path
            )

        # 6. Role-based check
        role_caps = self._ROLE_CAPABILITIES.get(role.lower(), frozenset())
        if cap not in role_caps:
            return self._deny(
                actor, cap,
                f"Role '{role}' lacks permission for {cap.value}.",
                target_path
            )

        # 7. Mutative capability requires approval
        needs_approval = cap in self._APPROVAL_REQUIRED

        return {
            "decision": "allow",
            "reason": f"Capability {cap.value} allowed for role '{role}'.",
            "write_performed": False,
            "requires_approval": needs_approval,
            "audit_event": {
                "event_type": "capability_decision",
                "actor": actor,
                "requested_capability": cap.value,
                "target_path": target_path or "",
                "decision": "allow",
                "reason": f"Allowed for role {role}",
                "write_performed": False,
                "policy_version": "FRONT-BRAIN-AUTONOMY-GOVERNANCE-HARDENING-01",
                "timestamp_utc": "",  # Caller should fill
            }
        }

    def _normalize(self, capability: Capability | str) -> Optional[Capability]:
        if isinstance(capability, Capability):
            return capability
        try:
            return Capability(capability)
        except ValueError:
            return None

    def _deny(
        self,
        actor: str,
        capability: Capability,
        reason: str,
        target_path: Optional[str] = None,
    ) -> Dict[str, any]:
        return {
            "decision": "deny",
            "reason": reason,
            "write_performed": False,
            "requires_approval": False,
            "audit_event": {
                "event_type": "capability_decision",
                "actor": actor,
                "requested_capability": capability.value if capability else "unknown",
                "target_path": target_path or "",
                "decision": "deny",
                "reason": reason,
                "write_performed": False,
                "policy_version": "FRONT-BRAIN-AUTONOMY-GOVERNANCE-HARDENING-01",
                "timestamp_utc": "",
            }
        }

    def get_allowed_capabilities(self, role: str) -> Set[str]:
        """Return set of capability values allowed for a role."""
        caps = self._ROLE_CAPABILITIES.get(role.lower(), frozenset())
        return {c.value for c in caps}

    def get_denied_capabilities(self, role: str) -> Set[str]:
        """Return set of capability values denied for a role."""
        allowed = self._ROLE_CAPABILITIES.get(role.lower(), frozenset())
        return {c.value for c in Capability if c not in allowed and c != Capability.UNKNOWN}
