"""Compatibility facade for the R6.2 governed memory-promotion boundary.

Historical callers retain their import and call shape, but no longer receive a
write path. A caller must provide the typed candidate, the bound human
decision, and an explicit non-canonical root before the facade can delegate to
``MemoryService`` to prepare a no-write receipt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from tmp_agent.brain_v9.core.memory_service import MemoryService


def _rejected_report(
    candidate_id: str,
    errors: Optional[List[str]] = None,
    safety_flags: Optional[List[str]] = None,
    *,
    reason: str = "governed_receipt_required",
) -> Dict[str, Any]:
    """Keep the legacy result shape while denying all ungoverned effects."""
    del candidate_id, errors, safety_flags
    return {
        "ok": False,
        "reason": reason,
        "promotion_performed": False,
        "write_performed": False,
    }


def promote_candidate(
    candidate_id: str,
    source: str,
    mode: str,
    approval_token: str,
    operator_id: str,
    confirm_phrase: str,
    allowed_domains: Optional[set[str]] = None,
    queue_dir: Optional[Path] = None,
    staging_dir: Optional[Path] = None,
    staging_jsonl: Optional[Path] = None,
    *,
    candidate: Optional[Dict[str, Any]] = None,
    decision: Optional[Dict[str, Any]] = None,
    semantic_root: Optional[Path] = None,
    staging_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Prepare a typed receipt only; historical promotion arguments are denied."""
    del (
        candidate_id,
        source,
        mode,
        approval_token,
        operator_id,
        confirm_phrase,
        allowed_domains,
        queue_dir,
        staging_dir,
        staging_jsonl,
    )
    if candidate is None or decision is None or semantic_root is None or staging_root is None:
        return _rejected_report("")
    return MemoryService(Path(semantic_root)).prepare_governed_promotion(
        candidate,
        decision,
        Path(staging_root),
    )


def rollback_promotion(snapshot_path: str) -> Dict[str, Any]:
    """Deny historical canonical rollback; R6.2 requires an execution receipt."""
    del snapshot_path
    return _rejected_report("")
