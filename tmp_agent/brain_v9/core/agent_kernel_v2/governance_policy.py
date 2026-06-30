"""Explicit governance policy decisions for Brain Agent V2.

This module provides a policy table that maps classified intents to governance
decisions. It is separate from tool-level governance so that intent-based
escalation/blocking can be applied before any tool is scheduled.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


SAFE_READ_INTENTS = {
    "read_only_status",
    "explain_capabilities",
    "repo_read",
    "dashboard_diagnosis",
    "memory_read",
    "self_improvement_reportonly",
}

APPROVAL_REQUIRED_INTENTS = {
    "code_change_request",
    "push_request",
    "delete_request",
    "memory_write",
}

DRY_RUN_ONLY_INTENTS = {
    "autonomy_dryrun",
}

BLOCKED_INTENTS = {
    "trading_broker_live",
}

REQUIRED_PERMISSION_MAP = {
    "code_change_request": "build",
    "push_request": "push",
    "delete_request": "delete",
    "memory_write": "memory_write",
    "autonomy_dryrun": "autonomy_dryrun",
    "self_improvement_reportonly": None,
}


def decide_governance(
    intent: str,
    mode_requested: str,
    mode_effective: str,
    approval_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Return structured governance decision for a classified intent.

    Args:
        intent: classified intent from intent_classifier.
        mode_requested: raw mode requested by user.
        mode_effective: validated effective mode.
        approval_token: optional approval token for build/push/delete.

    Returns:
        dict with governance_decision, required_permission, approval_required,
        blocked_reason, safe_mode.
    """
    if intent in BLOCKED_INTENTS:
        return {
            "governance_decision": "blocked",
            "required_permission": None,
            "approval_required": False,
            "blocked_reason": "trading/broker/live-money requests are permanently blocked by Brain governance policy",
            "safe_mode": True,
        }

    if intent in SAFE_READ_INTENTS:
        return {
            "governance_decision": "allow",
            "required_permission": None,
            "approval_required": False,
            "blocked_reason": None,
            "safe_mode": True,
        }

    if intent in DRY_RUN_ONLY_INTENTS:
        # Autonomy is allowed only in dry-run/gated mode unless explicit approval.
        if approval_token and str(approval_token).startswith("AGENTV2_APPROVED_"):
            return {
                "governance_decision": "approval_required",
                "required_permission": "autonomy",
                "approval_required": True,
                "blocked_reason": None,
                "safe_mode": False,
            }
        return {
            "governance_decision": "dry_run_only",
            "required_permission": "autonomy_dryrun",
            "approval_required": False,
            "blocked_reason": "autonomy requests are gated to dry-run only; explicit operator approval required for unsupervised execution",
            "safe_mode": True,
        }

    if intent in APPROVAL_REQUIRED_INTENTS:
        perm = REQUIRED_PERMISSION_MAP.get(intent, "build")
        return {
            "governance_decision": "approval_required",
            "required_permission": perm,
            "approval_required": True,
            "blocked_reason": None,
            "safe_mode": mode_effective != "build",
        }

    # Unknown or insufficient info: allow but stay read-only safe.
    return {
        "governance_decision": "allow",
        "required_permission": None,
        "approval_required": False,
        "blocked_reason": None,
        "safe_mode": True,
    }


def summarize_governance_modes() -> Dict[str, Any]:
    return {
        "read_only_allowed": True,
        "safe_diagnostic_allowed": True,
        "build_requires_approval": True,
        "push_requires_approval": True,
        "delete_requires_approval": True,
        "memory_write_blocked_or_approval_required": True,
        "faiss_mutation_blocked": True,
        "trading_broker_blocked": True,
        "autonomy_dry_run_only_by_default": True,
        "self_improvement_report_only_by_default": True,
    }
