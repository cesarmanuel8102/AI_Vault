"""
tmp_agent/brain_v9/routes/canary_lookup_read_only.py
FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-01

Read-only FastAPI router that exposes the canary lookup adapter
without modifying the main runtime or importing FAISS.

Guarantees:
- No file writes.
- No FAISS import or index modification.
- No server start or network access at import time.
- Only GET, no mutation endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

import sys
from pathlib import Path

# Ensure brain/ is discoverable without mutating global state permanently
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from brain.semantic_memory_canary_lookup_read_only import (
    lookup_canary_record as _lookup,
    DEFAULT_CANARY_ID,
    DEFAULT_TARGET_PATH,
)

router = APIRouter(tags=["read-only"])


@router.get("/brain/read-only/canary")
async def get_canary_lookup() -> Dict[str, Any]:
    """
    Read-only lookup of the canary record in semantic memory.
    No write. No FAISS. No mutation.
    """
    try:
        result = _lookup(
            target_path=DEFAULT_TARGET_PATH,
            canary_id=DEFAULT_CANARY_ID,
        )
    except Exception as exc:
        # Unexpected catastrophic error — still must not expose mutability
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "detail": str(exc)[:200],
            "no_write": True,
            "faiss_used": False,
            "promotion": False,
            "adapter": "brain.semantic_memory_canary_lookup_read_only",
            "endpoint": "/brain/read-only/canary",
        }

    # Compose safe response without exposing full record text
    response: Dict[str, Any] = {
        "status": "ok" if result["found"] else "not_found",
        "found": result["found"],
        "count": result["count"],
        "line_number": result["line_number"],
        "total_lines": result["total_lines"],
        "is_last_line": result["is_last_line"],
        "validation": result["validation"],
        "errors": result["errors"],
        "no_write": result["no_write"],
        "faiss_used": result["faiss_used"],
        "promotion": False,
        "adapter": "brain.semantic_memory_canary_lookup_read_only",
        "endpoint": "/brain/read-only/canary",
    }

    # If found, add safe lightweight record metadata—never the full text
    record = result.get("record")
    if record is not None:
        meta = record.get("metadata", {})
        response["record_summary"] = {
            "id": record.get("id"),
            "kind": record.get("kind"),
            "source": record.get("source"),
            "created_utc": record.get("created_utc"),
            "metadata_flags": {
                "canary": meta.get("canary"),
                "front": meta.get("front"),
                "single_record_canary": meta.get("single_record_canary"),
                "faiss_write": meta.get("faiss_write"),
                "promotion": meta.get("promotion"),
                "patch_application": meta.get("patch_application"),
                "trading": meta.get("trading"),
                "b8": meta.get("b8"),
            },
        }

    # Handle invalid validation explicitly with status override
    if result["found"] and result.get("validation") and not result["validation"].get("valid"):
        response["status"] = "invalid"
        response["errors"] = result["validation"].get("errors", [])

    # Always return HTTP 200 for controlled result; errors are in payload
    return response
