"""Memory/semantic routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from brain_v9.api_security import require_operator_access

log = logging.getLogger("brain_v9")
router = APIRouter(tags=["memory-semantic"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


class SemanticIngestRequest(BaseModel):
    text: str
    source: str = "manual"
    session_id: str = "default"
    kind: str = "note"


class SemanticIngestSessionRequest(BaseModel):
    session_id: str = "default"
    limit: int = 200


@router.get("/brain/semantic-memory/search")
async def brain_semantic_memory_search(query: str, top_k: int = 5):
    # Input hardening: previene queries patologicas que tumban Ollama embeddings
    # (queries gigantes, vacias, solo whitespace) y devuelve respuesta vacia limpia.
    q = (query or "").strip()
    if not q:
        return {"ok": True, "query": query, "results": [], "note": "empty_query_skipped"}
    # cap a 1000 chars: nomic-embed-text contexto util ~512 tokens
    if len(q) > 1000:
        q = q[:1000]
    # cap top_k razonable
    top_k = max(1, min(int(top_k or 5), 50))
    try:
        from brain_v9.core.semantic_memory import get_semantic_memory

        memory = get_semantic_memory()
        results = memory.search(q, top_k=top_k)
        return {"ok": True, "query": query, "results": results}
    except Exception as e:
        log.warning("semantic-memory/search failed: %s", e)
        return {"ok": False, "query": query, "results": [], "error": str(e)[:200]}


@router.post("/brain/semantic-memory/ingest")
async def brain_semantic_memory_ingest(req: SemanticIngestRequest, _operator: OperatorAccess):
    from brain_v9.core.semantic_memory import get_semantic_memory

    return get_semantic_memory().ingest_text(
        text=req.text,
        source=req.source,
        session_id=req.session_id,
        kind=req.kind,
    )


@router.post("/brain/semantic-memory/ingest-session")
async def brain_semantic_memory_ingest_session(req: SemanticIngestSessionRequest, _operator: OperatorAccess):
    from brain_v9.core.semantic_memory import get_semantic_memory

    return get_semantic_memory().ingest_session_memory(session_id=req.session_id, limit=req.limit)
