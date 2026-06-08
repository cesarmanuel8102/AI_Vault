"""
brain/knowledge_read_api.py
FRONT-BRAIN-KNOWLEDGE-READ-API-01

Real knowledge read API for Brain Lab.
Reads from memory/semantic/semantic_memory.jsonl.
Supports keyword search, filtering, and pagination.

Guarantees:
- No file writes.
- No FAISS import or index modification.
- No network access.
- Only stdlib + pathlib.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_MEMORY_PATH = Path("memory/semantic/semantic_memory.jsonl")
DEFAULT_LIMIT = 10
DEFAULT_OFFSET = 0
DEFAULT_MAX_LIMIT = 100


@dataclass
class KnowledgeRecord:
    """Represents a single knowledge record from semantic memory."""
    id: str
    kind: str
    source: str
    session_id: str
    created_utc: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeRecord":
        return cls(
            id=data.get("id", ""),
            kind=data.get("kind", ""),
            source=data.get("source", ""),
            session_id=data.get("session_id", ""),
            created_utc=data.get("created_utc", ""),
            text=data.get("text", ""),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "session_id": self.session_id,
            "created_utc": self.created_utc,
            "text": self.text,
            "metadata": self.metadata,
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """Return a lightweight summary without full text."""
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "session_id": self.session_id,
            "created_utc": self.created_utc,
            "text_preview": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "metadata": self.metadata,
        }


@dataclass
class KnowledgeQueryResult:
    """Result of a knowledge query."""
    records: List[KnowledgeRecord]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    query: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    status: str = "ok"
    no_write: bool = True
    faiss_used: bool = False
    promotion: bool = False

    def to_dict(self, include_full_text: bool = False) -> Dict[str, Any]:
        if include_full_text:
            records_data = [r.to_dict() for r in self.records]
        else:
            records_data = [r.to_summary_dict() for r in self.records]

        return {
            "status": self.status,
            "total_count": self.total_count,
            "returned_count": self.returned_count,
            "limit": self.limit,
            "offset": self.offset,
            "query": self.query,
            "filters": self.filters,
            "records": records_data,
            "errors": self.errors,
            "no_write": self.no_write,
            "faiss_used": self.faiss_used,
            "promotion": self.promotion,
        }


def _load_records(path: Path) -> List[KnowledgeRecord]:
    """Load all valid records from a JSONL file."""
    records: List[KnowledgeRecord] = []
    if not path.is_file():
        return records

    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    records.append(KnowledgeRecord.from_dict(obj))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
    except Exception:
        pass

    return records


def _matches_query(record: KnowledgeRecord, query: Optional[str]) -> bool:
    """Check if a record matches a keyword query."""
    if not query:
        return True
    query_lower = query.lower()
    # Search in text, id, kind, source, session_id
    searchable_fields = [
        record.text,
        record.id,
        record.kind,
        record.source,
        record.session_id,
    ]
    return any(query_lower in field.lower() for field in searchable_fields if field)


def _matches_filters(record: KnowledgeRecord, filters: Dict[str, Any]) -> bool:
    """Check if a record matches all filter criteria."""
    for key, value in filters.items():
        if value is None:
            continue
        if key == "kind" and record.kind != value:
            return False
        if key == "source" and record.source != value:
            return False
        if key == "session_id" and record.session_id != value:
            return False
    return True


def query_knowledge(
    query: Optional[str] = None,
    kind: Optional[str] = None,
    source: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    include_full_text: bool = False,
) -> KnowledgeQueryResult:
    """
    Query the knowledge base with optional search and filters.

    Args:
        query: Optional keyword search string.
        kind: Filter by record kind.
        source: Filter by record source.
        session_id: Filter by session ID.
        limit: Maximum records to return (capped at DEFAULT_MAX_LIMIT).
        offset: Number of records to skip.
        memory_path: Path to the semantic memory JSONL file.
        include_full_text: If True, include full text in results.

    Returns:
        KnowledgeQueryResult with records and metadata.
    """
    result = KnowledgeQueryResult(
        records=[],
        total_count=0,
        returned_count=0,
        limit=min(limit, DEFAULT_MAX_LIMIT),
        offset=max(offset, 0),
        query=query,
        filters={},
        errors=[],
    )

    # Build filters dict
    filters: Dict[str, Any] = {}
    if kind is not None:
        filters["kind"] = kind
    if source is not None:
        filters["source"] = source
    if session_id is not None:
        filters["session_id"] = session_id
    result.filters = filters

    # Load all records
    all_records = _load_records(memory_path)

    # Apply search and filters
    matched: List[KnowledgeRecord] = []
    for record in all_records:
        if not _matches_query(record, query):
            continue
        if not _matches_filters(record, filters):
            continue
        matched.append(record)

    # Sort by created_utc descending (newest first)
    matched.sort(key=lambda r: r.created_utc, reverse=True)

    result.total_count = len(matched)

    # Apply pagination
    start = result.offset
    end = start + result.limit
    paginated = matched[start:end]

    result.records = paginated
    result.returned_count = len(paginated)

    return result
