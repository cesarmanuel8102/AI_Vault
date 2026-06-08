# FRONT-BRAIN-KNOWLEDGE-READ-API-01

## Status: COMPLETE

**Decision:** KNOWLEDGE_READ_API_READY
**Date:** 2026-06-08
**Branch:** codex/own-capital-sustainable-return

## Purpose

Create a real knowledge read API that queries the semantic memory store (`memory/semantic/semantic_memory.jsonl`) with keyword search, filtering, and pagination — all read-only.

## Files Created

- `brain/knowledge_read_api.py` — Core knowledge query module with dataclasses `KnowledgeRecord` and `KnowledgeQueryResult`
- `tmp_agent/brain_v9/routes/knowledge_read_api.py` — FastAPI router exposing `GET /brain/knowledge/read`
- `tests/smoke/smoke_front_brain_knowledge_read_api_01.py` — Smoke tests (10 passed)
- `docs/FRONT_BRAIN_KNOWLEDGE_READ_API_01.md` — This document

## Files Modified

- `tmp_agent/brain_v9/main.py` — Added `knowledge_read_api_router` import and `app.include_router(knowledge_read_api_router)`

## Endpoint

`GET /brain/knowledge/read`

Query parameters:
- `query` — keyword search string
- `kind` — filter by record kind (e.g., "session_fragment")
- `source` — filter by record source
- `session_id` — filter by session ID
- `limit` — max records to return (1-100, default 10)
- `offset` — records to skip (default 0)
- `include_full_text` — if true, return full text instead of preview

## Guarantees

- `no_memory_semantic_write`: true
- `no_faiss_write`: true
- `no_real_write`: true
- `no_promotion`: true
- `no_patch_application`: true
- `no_trading_b8`: true

## Test Results

```
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_read_api_module_exists PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_read_api_route_exists PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_read_api_imports PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_query_no_filters PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_query_with_keyword PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_query_kind_filter PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_query_pagination PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_record_dataclass PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_query_result_structure PASSED
tests/smoke/smoke_front_brain_knowledge_read_api_01.py::test_knowledge_read_api_route_has_endpoint PASSED
============================= 10 passed in 0.61s =============================
```

## Next Recommended

FRONT-REAL-MEMORY-FAISS-PROMOTION-01 — controlled memory→FAISS promotion
