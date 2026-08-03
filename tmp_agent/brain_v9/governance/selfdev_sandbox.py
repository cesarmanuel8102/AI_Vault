"""
tmp_agent/brain_v9/governance/selfdev_sandbox.py
FRONT-BRAIN-AUTONOMY-SELFDEV-SANDBOX-02

Runtime sandbox constraints for Brain/Agent self-dev actions.
Integrates capability_policy checks into runtime tool execution paths.
Pure Python. No file IO. No env reads. No writes performed.
"""

from __future__ import annotations

from typing import Dict, Optional, Any
from pathlib import Path

from .capability_policy import CapabilityPolicy, Capability
from .protected_paths import is_protected_path


class SelfDevSandbox:
    """
    Runtime sandbox gate for self-dev / autonomous file operations.

    Evaluates capability policy before any mutative action.
    Does not perform writes. Returns structured decision + audit event.
    """

    # Path patterns that map to specific capability denials
    _PATH_CAPABILITY_MAP: Dict[str, Capability] = {
        # Governance / security / RBAC / capability files
        "governance/": Capability.GOVERNANCE_EDIT,
        "security/": Capability.SECURITY_EDIT,
        "rbac": Capability.SECURITY_EDIT,
        "capability_policy": Capability.GOVERNANCE_EDIT,
        "selfdev_sandbox": Capability.GOVERNANCE_EDIT,
        "execution_gate": Capability.GOVERNANCE_EDIT,
        "ethics_kernel": Capability.GOVERNANCE_EDIT,
        "api_security": Capability.SECURITY_EDIT,
        "trace_redactor": Capability.SECURITY_EDIT,
        "approval": Capability.GOVERNANCE_EDIT,
        "auth": Capability.SECURITY_EDIT,
        "policy": Capability.GOVERNANCE_EDIT,

        # Workflow files
        ".github/workflows/": Capability.GOVERNANCE_EDIT,
        ".github/": Capability.GOVERNANCE_EDIT,

        # Memory paths
        "memory/semantic/": Capability.MEMORY_WRITE,
        "memory/rollback_snapshots/": Capability.MEMORY_WRITE,
        "memory/autonomous_journal.jsonl": Capability.MEMORY_WRITE,
        "memory/promotion_queue/": Capability.MEMORY_WRITE,
        "memory/semantic_staging/": Capability.MEMORY_WRITE,

        # Trading / broker / IBKR / QuantConnect
        "trading/": Capability.BROKER_OR_TRADING,
        "broker/": Capability.BROKER_OR_TRADING,
        "ibkr/": Capability.BROKER_OR_TRADING,
        "quantconnect/": Capability.BROKER_OR_TRADING,

        # Secrets
        ".env": Capability.SECURITY_EDIT,
        ".dev_auth/": Capability.SECURITY_EDIT,
        "secrets/": Capability.SECURITY_EDIT,
    }

    def __init__(self, policy: Optional[CapabilityPolicy] = None):
        self.policy = policy or CapabilityPolicy()

    def _map_path_to_capability(self, target_path: str) -> Capability:
        """Map a target path to the most specific capability."""
        normalized = target_path.replace("\\", "/").lower()

        # Exact basename checks first
        basename = Path(normalized).name.lower()
        if basename in self._PATH_CAPABILITY_MAP:
            return self._PATH_CAPABILITY_MAP[basename]

        # Prefix checks
        for prefix, cap in self._PATH_CAPABILITY_MAP.items():
            if normalized.startswith(prefix) or ("/" + prefix) in ("/" + normalized):
                return cap

        # Fallback: check protected_paths module
        if is_protected_path(normalized):
            return Capability.GOVERNANCE_EDIT

        # Default: allow non-protected paths (not self-dev / governance / security / trading / secrets)
        return Capability.FILE_READ

    def evaluate_selfdev_action(
        self,
        actor: str,
        capability: str,
        target_path: str,
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Evaluate a self-dev action against capability policy and path protections.

        Returns:
        {
            "decision": "allow|deny",
            "reason": "...",
            "write_performed": False,
            "target_path": "...",
            "requested_capability": "...",
            "audit_event": {...}
        }
        """
        # 1. Map path to capability if not explicitly provided
        if isinstance(capability, str) and capability.lower() == "auto":
            capability_enum = self._map_path_to_capability(target_path)
        else:
            if isinstance(capability, Capability):
                capability_enum = capability
            else:
                try:
                    capability_enum = Capability(capability)
                except ValueError:
                    capability_enum = Capability.UNKNOWN

        # 2. Run capability policy check
        result = self.policy.check(
            actor=actor,
            capability=capability_enum,
            role=role,
            is_self_dev=True,  # Self-dev actions always flagged
            is_god_mode=is_god_mode,
            target_path=target_path,
        )

        # 3. Add target_path to result for clarity
        result["target_path"] = target_path
        result["requested_capability"] = capability_enum.value

        # 4. Ensure write_performed is always false (this is a decision gate)
        result["write_performed"] = False

        # 5. Ensure audit_event has target_path
        if "audit_event" in result:
            result["audit_event"]["target_path"] = target_path
            result["audit_event"]["requested_capability"] = capability_enum.value

        return result

    def evaluate_file_write(
        self,
        actor: str,
        target_path: str,
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Convenience method: evaluate a file write operation.
        Auto-maps path to capability.
        """
        return self.evaluate_selfdev_action(
            actor=actor,
            capability="auto",
            target_path=target_path,
            is_god_mode=is_god_mode,
            role=role,
        )

    def evaluate_code_edit(
        self,
        actor: str,
        target_path: str,
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Convenience method: evaluate a code edit operation.
        """
        return self.evaluate_selfdev_action(
            actor=actor,
            capability=Capability.CODE_EDIT,
            target_path=target_path,
            is_god_mode=is_god_mode,
            role=role,
        )

    def evaluate_git_action(
        self,
        actor: str,
        git_action: str,  # "stage", "commit", "push"
        target_path: str = ".",
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Convenience method: evaluate git stage/commit/push.
        """
        cap_map = {
            "stage": Capability.GIT_STAGE,
            "commit": Capability.GIT_COMMIT,
            "push": Capability.GIT_PUSH,
        }
        capability = cap_map.get(git_action.lower(), Capability.FILE_WRITE_RESTRICTED)
        return self.evaluate_selfdev_action(
            actor=actor,
            capability=capability,
            target_path=target_path,
            is_god_mode=is_god_mode,
            role=role,
        )

    def evaluate_memory_write(
        self,
        actor: str,
        target_path: str,
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Convenience method: evaluate memory/semantic write.
        """
        return self.evaluate_selfdev_action(
            actor=actor,
            capability=Capability.MEMORY_WRITE,
            target_path=target_path,
            is_god_mode=is_god_mode,
            role=role,
        )

    def evaluate_dev_endpoint_access(
        self,
        actor: str,
        is_god_mode: bool = False,
        role: str = "operator",
    ) -> Dict[str, Any]:
        """
        Convenience method: evaluate dev endpoint enable attempt.
        """
        return self.evaluate_selfdev_action(
            actor=actor,
            capability=Capability.DEV_ENDPOINT_ACCESS,
            target_path="/dev,/godmode",
            is_god_mode=is_god_mode,
            role=role,
        )


# Global instance for easy import
_sandbox_instance: Optional[SelfDevSandbox] = None


def get_sandbox() -> SelfDevSandbox:
    """Get or create global sandbox instance."""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = SelfDevSandbox()
    return _sandbox_instance


def evaluate_selfdev_action(
    actor: str,
    capability: str,
    target_path: str,
    is_god_mode: bool = False,
    role: str = "operator",
) -> Dict[str, Any]:
    """
    Module-level convenience function for runtime integration.

    Usage:
        from brain_v9.governance.selfdev_sandbox import evaluate_selfdev_action

        result = evaluate_selfdev_action(
            actor="selfdev",
            capability="auto",
            target_path="tmp_agent/brain_v9/governance/execution_gate.py",
            is_god_mode=False,
        )
        if result["decision"] == "deny":
            # Log audit_event, return error to caller
            return {"error": result["reason"], "audit_event": result["audit_event"]}
    """
    return get_sandbox().evaluate_selfdev_action(
        actor=actor,
        capability=capability,
        target_path=target_path,
        is_god_mode=is_god_mode,
        role=role,
    )
