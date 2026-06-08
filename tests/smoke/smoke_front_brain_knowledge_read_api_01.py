"""Smoke test for FRONT-BRAIN-KNOWLEDGE-READ-API-01."""

import json
import os
from pathlib import Path


def test_knowledge_read_api_module_exists():
    assert os.path.isfile("brain/knowledge_read_api.py")


def test_knowledge_read_api_route_exists():
    assert os.path.isfile("tmp_agent/brain_v9/routes/knowledge_read_api.py")


def test_knowledge_read_api_imports():
    from brain.knowledge_read_api import (
        query_knowledge,
        KnowledgeRecord,
        KnowledgeQueryResult,
        DEFAULT_LIMIT,
        DEFAULT_MAX_LIMIT,
    )
    assert callable(query_knowledge)
    assert DEFAULT_LIMIT == 10
    assert DEFAULT_MAX_LIMIT == 100


def test_knowledge_query_no_filters():
    from brain.knowledge_read_api import query_knowledge
    result = query_knowledge(limit=5)
    assert result.status == "ok"
    assert result.no_write is True
    assert result.faiss_used is False
    assert result.promotion is False
    assert result.total_count >= 0
    assert result.returned_count >= 0


def test_knowledge_query_with_keyword():
    from brain.knowledge_read_api import query_knowledge
    result = query_knowledge(query="session", limit=3)
    assert result.status == "ok"
    assert result.no_write is True
    assert result.total_count >= 0


def test_knowledge_query_kind_filter():
    from brain.knowledge_read_api import query_knowledge
    result = query_knowledge(kind="session_fragment", limit=2)
    assert result.status == "ok"
    assert result.no_write is True
    assert result.filters.get("kind") == "session_fragment"
    assert result.total_count >= 0


def test_knowledge_query_pagination():
    from brain.knowledge_read_api import query_knowledge
    result = query_knowledge(limit=2, offset=0)
    assert result.limit == 2
    assert result.offset == 0
    assert result.returned_count <= 2


def test_knowledge_record_dataclass():
    from brain.knowledge_read_api import KnowledgeRecord
    record = KnowledgeRecord(
        id="test-id",
        kind="test",
        source="test_source",
        session_id="test_session",
        created_utc="2026-01-01T00:00:00Z",
        text="Test content",
    )
    assert record.id == "test-id"
    assert record.to_dict()["text"] == "Test content"
    assert "text_preview" in record.to_summary_dict()


def test_knowledge_query_result_structure():
    from brain.knowledge_read_api import query_knowledge
    result = query_knowledge(limit=1)
    d = result.to_dict()
    assert d["status"] == "ok"
    assert d["no_write"] is True
    assert d["faiss_used"] is False
    assert d["promotion"] is False
    assert "total_count" in d
    assert "returned_count" in d
    assert "records" in d


def test_knowledge_read_api_route_has_endpoint():
    from tmp_agent.brain_v9.routes.knowledge_read_api import router
    routes = [r.path for r in router.routes]
    assert "/brain/knowledge/read" in routes
