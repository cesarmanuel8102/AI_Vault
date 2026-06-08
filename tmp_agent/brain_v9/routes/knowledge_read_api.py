"""
tmp_agent/brain_v9/routes/knowledge_read_api.py
FRONT-BRAIN-KNOWLEDGE-READ-API-01

FastAPI router exposing real knowledge read API.
Supports keyword search, filtering, and pagination.
No writes. No FAISS. No mutation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

# Ensure brain/ is discoverable
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from brain.knowledge_read_api import (
    DEFAULT_LIMIT,
    DEFAULT_MAX_LIMIT,
    DEFAULT_OFFSET,
    query_knowledge,
    KnowledgeQueryResult,
)

router = APIRouter(tags=["knowledge"])


@router.get("/brain/knowledge/read")
async def get_knowledge_read(
    query: Optional[str] = Query(None, description="Keyword search string"),
    kind: Optional[str] = Query(None, description="Filter by record kind"),
    source: Optional[str] = Query(None, description="Filter by record source"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=DEFAULT_MAX_LIMIT, description="Max records to return"),
    offset: int = Query(DEFAULT_OFFSET, ge=0, description="Records to skip"),
    include_full_text: bool = Query(False, description="Include full text in response"),
) -> Dict[str, Any]:
    """
    Read-only knowledge query endpoint.

    Searches the semantic memory JSONL file with optional keyword query
    and filters. Returns paginated results.

    No writes. No FAISS. No mutation.
    """
    try:
        result = query_knowledge(
            query=query,
            kind=kind,
            source=source,
            session_id=session_id,
            limit=limit,
            offset=offset,
            include_full_text=include_full_text,
        )
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "detail": str(exc)[:200],
            "no_write": True,
            "faiss_used": False,
            "promotion": False,
            "endpoint": "/brain/knowledge/read",
        }

    return result.to_dict(include_full_text=include_full_text)
