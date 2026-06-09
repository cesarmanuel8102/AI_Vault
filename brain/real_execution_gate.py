"""
brain/real_execution_gate.py
FRONT-RUNTIME-RECOVERY-REAL-EXECUTION-GATE-01

Real execution readiness gate.
Pure Python. No external deps. No network. No file writes. No env reads.
No token logging. No memory writes. No FAISS writes.
Deterministic. Importable in tests.

This module defines the gate that must pass before any real execution is
allowed. Default: real_execution_allowed = false.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ─── Immutable safety flags ────────────────────────────────────────────────

_DEFAULT_SAFETY_FLAGS: Dict[str, bool] = {
    "ingestion_executed": False,
    "memory_write_executed": False,
    "faiss_write_executed": False,
    "network_called": False,
    "connector_called": False,
    "content_read": False,
    "promotion_executed": False,
}


# ─── Helpers ─────────────────────────────────────────────────────────────

def _deep_copy_safety_flags() -> Dict[str, bool]:
    return dict(_DEFAULT_SAFETY_FLAGS)


# ─── Readiness builder ─────────────────────────────────────────────────────

def build_real_execution_readiness(
    runtime_status: Dict[str, Any],
    approval_status: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build a real execution readiness report from runtime and approval status.

    real_execution_allowed is true ONLY when all required conditions are met.
    Default: all conditions false, so real_execution_allowed = false.
    """
    # Extract runtime fields with defaults
    dashboard_ok = bool(runtime_status.get("dashboard_ok", False))
    brain_server_ok = bool(runtime_status.get("brain_server_ok", False))
    ollama_ok = bool(runtime_status.get("ollama_ok", False))
    git_tracked_clean = bool(runtime_status.get("git_tracked_clean", False))
    roadmap_valid = bool(runtime_status.get("roadmap_valid", False))

    # Extract approval fields with defaults
    operator_approval_visible = bool(
        approval_status.get("operator_approval_visible", False)
    )
    evidence_path_exists = bool(
        approval_status.get("evidence_path_exists", False)
    )

    # Hard constraints for this front
    semantic_memory_write_allowed = False
    faiss_write_allowed = False

    # Determine if real execution is allowed
    all_required = (
        dashboard_ok
        and brain_server_ok
        and ollama_ok
        and operator_approval_visible
        and git_tracked_clean
        and roadmap_valid
        and evidence_path_exists
        and not semantic_memory_write_allowed
        and not faiss_write_allowed
    )

    # Note: semantic_memory_write_allowed and faiss_write_allowed are False,
    # so all_required will always be False in this front. This is by design.
    real_execution_allowed = all_required

    denied_reasons: List[str] = []
    if not dashboard_ok:
        denied_reasons.append("dashboard not reachable")
    if not brain_server_ok:
        denied_reasons.append("brain server not reachable")
    if not ollama_ok:
        denied_reasons.append("ollama not reachable")
    if not operator_approval_visible:
        denied_reasons.append("operator approval not visible")
    if not git_tracked_clean:
        denied_reasons.append("git working tree not clean")
    if not roadmap_valid:
        denied_reasons.append("ROADMAP JSON invalid")
    if not evidence_path_exists:
        denied_reasons.append("evidence path not configured")
    if semantic_memory_write_allowed:
        denied_reasons.append("semantic memory write not allowed in this front")
    if faiss_write_allowed:
        denied_reasons.append("FAISS write not allowed in this front")

    return {
        "real_execution_allowed": real_execution_allowed,
        "dashboard_ok": dashboard_ok,
        "brain_server_ok": brain_server_ok,
        "ollama_ok": ollama_ok,
        "operator_approval_visible": operator_approval_visible,
        "git_tracked_clean": git_tracked_clean,
        "roadmap_valid": roadmap_valid,
        "evidence_path_exists": evidence_path_exists,
        "semantic_memory_write_allowed": semantic_memory_write_allowed,
        "faiss_write_allowed": faiss_write_allowed,
        "denied_reasons": denied_reasons,
        "safety_flags": _deep_copy_safety_flags(),
    }


# ─── Validator ───────────────────────────────────────────────────────────

def validate_real_execution_readiness(
    readiness: Dict[str, Any],
) -> Dict[str, Any]:
    errors: List[str] = []

    # Check safety flags
    safety_flags = readiness.get("safety_flags", {})
    for key, expected in _DEFAULT_SAFETY_FLAGS.items():
        actual = safety_flags.get(key)
        if actual is not expected:
            errors.append(f"Safety flag {key}={actual}, expected {expected}")

    # Check required keys
    required_keys = (
        "real_execution_allowed",
        "dashboard_ok",
        "brain_server_ok",
        "ollama_ok",
        "operator_approval_visible",
        "git_tracked_clean",
        "roadmap_valid",
        "evidence_path_exists",
        "semantic_memory_write_allowed",
        "faiss_write_allowed",
        "denied_reasons",
    )
    for key in required_keys:
        if key not in readiness:
            errors.append(f"Missing required key: {key}")

    # Check that write flags are false in this front
    if readiness.get("semantic_memory_write_allowed") is not False:
        errors.append("semantic_memory_write_allowed must be False")
    if readiness.get("faiss_write_allowed") is not False:
        errors.append("faiss_write_allowed must be False")

    # If real_execution_allowed is true, verify all conditions are true
    if readiness.get("real_execution_allowed") is True:
        for key in (
            "dashboard_ok",
            "brain_server_ok",
            "ollama_ok",
            "operator_approval_visible",
            "git_tracked_clean",
            "roadmap_valid",
            "evidence_path_exists",
        ):
            if readiness.get(key) is not True:
                errors.append(
                    f"real_execution_allowed=True but {key}={readiness.get(key)}"
                )

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "readiness": readiness,
    }


# ─── Summarizer ────────────────────────────────────────────────────────────

def summarize_real_execution_readiness(
    readiness: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "real_execution_allowed": readiness.get("real_execution_allowed", False),
        "dashboard_ok": readiness.get("dashboard_ok", False),
        "brain_server_ok": readiness.get("brain_server_ok", False),
        "ollama_ok": readiness.get("ollama_ok", False),
        "operator_approval_visible": readiness.get(
            "operator_approval_visible", False
        ),
        "git_tracked_clean": readiness.get("git_tracked_clean", False),
        "roadmap_valid": readiness.get("roadmap_valid", False),
        "evidence_path_exists": readiness.get("evidence_path_exists", False),
        "semantic_memory_write_allowed": readiness.get(
            "semantic_memory_write_allowed", False
        ),
        "faiss_write_allowed": readiness.get("faiss_write_allowed", False),
        "denied_reasons_count": len(readiness.get("denied_reasons", [])),
        "safety_flags": readiness.get("safety_flags", {}),
    }
