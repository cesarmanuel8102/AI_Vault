"""Curated knowledge routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-EXTRA-AGGRESSIVE-COMPLETE-MIGRATION-14A
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict

from fastapi import Body, Depends, HTTPException, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brain.curated_runtime_lookup import (
    ALLOWED_STATES_FOR_LOOKUP,
    DEFAULT_FRESHNESS_DAYS,
    DEFAULT_LOOKUP_INDEX_PATH,
    DEFAULT_MIN_CURATION_SCORE,
    DEFAULT_MIN_VALIDATION_SCORE,
    FAISS_WRITE_ALLOWED,
    LOOKUP_VERSION,
    REAL_WRITE_ALLOWED,
    load_curated_lookup_index,
    search_curated_candidates,
)
from brain_v9.api_security import require_operator_access

log = logging.getLogger("brain_v9")
router = APIRouter(tags=["curated-knowledge"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


class CuratedKnowledgeDemoSearchRequest(BaseModel):
    query: str
    demo_index_path: str
    top_k: int = 5
    min_validation_score: float = DEFAULT_MIN_VALIDATION_SCORE
    min_curation_score: float = DEFAULT_MIN_CURATION_SCORE
    require_provenance: bool = True
    include_stale: bool = False
    demo_mode: bool = True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _curated_knowledge_status_payload() -> Dict[str, Any]:
    index_path = DEFAULT_LOOKUP_INDEX_PATH
    records = load_curated_lookup_index(index_path)
    warnings: list[str] = []
    total_records = 0
    malformed_count = 0
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            total_records += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                malformed_count += 1
        last_updated = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc).isoformat()
    else:
        last_updated = None
        warnings.append("readonly lookup index not found")
    if malformed_count:
        warnings.append(f"malformed records skipped: {malformed_count}")

    stale_count = 0
    now = datetime.now(timezone.utc)
    for record in records:
        try:
            freshness = datetime.fromisoformat(record.freshness)
            if (now - freshness).days > DEFAULT_FRESHNESS_DAYS:
                stale_count += 1
        except Exception:
            stale_count += 1

    return {
        "ok": True,
        "label": "verified_curated_readonly",
        "index_exists": index_path.exists(),
        "index_path": str(index_path),
        "total_records": total_records,
        "allowed_records": len(records),
        "blocked_filtered_count": max(0, total_records - len(records)),
        "stale_count": stale_count,
        "last_updated": last_updated,
        "lookup_version": LOOKUP_VERSION,
        "real_write_allowed": REAL_WRITE_ALLOWED,
        "faiss_write_allowed": FAISS_WRITE_ALLOWED,
        "warnings": warnings,
    }


def _curated_lookup_result_payload(result: Any) -> Dict[str, Any]:
    return {
        "candidate_id": result.candidate_id,
        "state": result.state,
        "text": result.text,
        "source_id": result.source_id,
        "evidence_refs": list(result.evidence_refs),
        "validation_score": result.validation_score,
        "curation_score": result.curation_score,
        "trust_score": result.trust_score,
        "freshness": result.freshness,
        "dry_run_id": result.dry_run_id,
        "label": result.label,
    }


def _resolve_demo_curated_index_path(demo_index_path: str) -> Path:
    raw = str(demo_index_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="demo_index_path is required")

    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "file://")):
        raise HTTPException(status_code=403, detail="demo_index_path URL schemes are not allowed")

    candidate = Path(raw)
    if candidate.suffix.lower() != ".jsonl":
        raise HTTPException(status_code=422, detail="demo_index_path must point to a .jsonl file")

    repo_root = _repo_root()
    tmp_agent_root = (repo_root / "tmp_agent").resolve()
    resolved = (repo_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()

    try:
        resolved.relative_to(tmp_agent_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="demo_index_path must resolve under tmp_agent")

    protected_roots = [
        (repo_root / "memory" / "semantic").resolve(),
        (repo_root / "tmp_agent" / "strategies").resolve(),
        (repo_root / ".git").resolve(),
    ]
    for protected in protected_roots:
        try:
            resolved.relative_to(protected)
            raise HTTPException(status_code=403, detail="demo_index_path targets a protected path")
        except ValueError:
            pass

    if not resolved.exists():
        raise HTTPException(status_code=404, detail="demo index not found")
    if not resolved.is_file():
        raise HTTPException(status_code=422, detail="demo_index_path must be a file")
    if resolved.stat().st_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="demo index exceeds 5 MB limit")

    return resolved


@router.get("/brain/curated-knowledge/status")
async def brain_curated_knowledge_status(_operator: OperatorAccess):
    try:
        return _curated_knowledge_status_payload()
    except Exception as exc:
        log.warning("curated-knowledge/status failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "label": "verified_curated_readonly",
                "error": "curated lookup status failed",
                "real_write_allowed": False,
                "faiss_write_allowed": False,
            },
        )


@router.post("/brain/curated-knowledge/search")
async def brain_curated_knowledge_search(_operator: OperatorAccess, payload: Dict[str, Any] = Body(default={})):
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    top_k = max(1, min(int(payload.get("top_k") or 5), 25))
    requested_states = payload.get("allowed_states")
    if isinstance(requested_states, list):
        allowed_states = tuple(s for s in requested_states if s in ALLOWED_STATES_FOR_LOOKUP)
    else:
        allowed_states = tuple(sorted(ALLOWED_STATES_FOR_LOOKUP))
    if not allowed_states:
        allowed_states = tuple(sorted(ALLOWED_STATES_FOR_LOOKUP))

    min_validation_score = float(payload.get("min_validation_score", DEFAULT_MIN_VALIDATION_SCORE))
    min_curation_score = float(payload.get("min_curation_score", DEFAULT_MIN_CURATION_SCORE))
    require_provenance = bool(payload.get("require_provenance", True))
    include_stale = bool(payload.get("include_stale", False))

    try:
        record = search_curated_candidates(
            query,
            allowed_states=allowed_states,
            top_k=top_k,
            min_validation_score=min_validation_score,
            min_curation_score=min_curation_score,
            require_provenance=require_provenance,
            include_stale=include_stale,
        )
        return {
            "ok": True,
            "label": "verified_curated_readonly",
            "query": query,
            "result_count": len(record.results),
            "total_available": record.total_available,
            "filtered_out": record.filtered_out,
            "results": [_curated_lookup_result_payload(r) for r in record.results],
            "warnings": [],
            "real_write_allowed": REAL_WRITE_ALLOWED,
            "faiss_write_allowed": FAISS_WRITE_ALLOWED,
        }
    except Exception as exc:
        log.warning("curated-knowledge/search failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "label": "verified_curated_readonly",
                "query": query,
                "results": [],
                "error": "curated lookup search failed",
                "real_write_allowed": False,
                "faiss_write_allowed": False,
            },
        )


@router.post("/brain/curated-knowledge/demo-search")
async def brain_curated_knowledge_demo_search(
    payload: CuratedKnowledgeDemoSearchRequest,
    _operator: OperatorAccess,
):
    query = str(payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if not payload.demo_mode:
        raise HTTPException(status_code=400, detail="demo_mode must be true")
    if payload.require_provenance is False:
        raise HTTPException(status_code=400, detail="require_provenance cannot be false")

    resolved_demo_index_path = _resolve_demo_curated_index_path(payload.demo_index_path)
    repo_root = _repo_root()
    top_k = max(1, min(int(payload.top_k or 5), 10))
    warnings = ["demo_index_override_request_scoped"]

    try:
        record = search_curated_candidates(
            query,
            index_path=resolved_demo_index_path,
            top_k=top_k,
            min_validation_score=float(payload.min_validation_score),
            min_curation_score=float(payload.min_curation_score),
            require_provenance=True,
            include_stale=bool(payload.include_stale),
        )
        return {
            "ok": True,
            "label": "verified_curated_readonly_demo",
            "demo_mode": True,
            "query": query,
            "demo_index_path": str(resolved_demo_index_path.relative_to(repo_root).as_posix()),
            "result_count": len(record.results),
            "total_available": record.total_available,
            "filtered_out": record.filtered_out,
            "results": [_curated_lookup_result_payload(r) for r in record.results],
            "warnings": warnings,
            "real_write_allowed": False,
            "faiss_write_allowed": False,
            "global_config_mutated": False,
            "automatic_context_injection": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("curated-knowledge/demo-search failed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "label": "verified_curated_readonly_demo",
                "demo_mode": True,
                "query": query,
                "results": [],
                "error": "curated demo lookup failed",
                "real_write_allowed": False,
                "faiss_write_allowed": False,
                "global_config_mutated": False,
                "automatic_context_injection": False,
            },
        )
