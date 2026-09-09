"""R9.1 static curated-knowledge inventory with no ingestion or runtime effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class CuratedKnowledgeEntry:
    """A versioned repository-owned knowledge reference with read-only provenance."""

    knowledge_id: str
    taxonomy: str
    version: str
    provenance_kind: str
    provenance_reference: str
    read_only: bool = True


_CATALOG: Tuple[CuratedKnowledgeEntry, ...] = (
    CuratedKnowledgeEntry(
        knowledge_id="BRAIN-101-CURATED-GOVERNANCE",
        taxonomy="governance",
        version="1.0.0",
        provenance_kind="canonical_repository",
        provenance_reference="docs/roadmap/BRAIN_101_MANIFEST.json",
    ),
    CuratedKnowledgeEntry(
        knowledge_id="BRAIN-101-CURATED-OPERATIONS",
        taxonomy="operations",
        version="1.0.0",
        provenance_kind="canonical_repository",
        provenance_reference="docs/roadmap/BRAIN_101_ROADMAP.md",
    ),
)
_BY_ID = {entry.knowledge_id: entry for entry in _CATALOG}
_FORBIDDEN_OPERATIONS = frozenset(
    {
        "semantic_memory_write",
        "source_ingestion",
        "network_fetch",
        "provider_call",
        "catalog_mutation",
    }
)


def curated_knowledge_inventory() -> Tuple[CuratedKnowledgeEntry, ...]:
    """Return the deterministic repository inventory; callers receive no mutable state."""

    return _CATALOG


def lookup_curated_knowledge(knowledge_id: str, *, version: Optional[str]) -> CuratedKnowledgeEntry:
    """Resolve one exact, versioned entry without querying an external source."""

    if not isinstance(version, str) or not version:
        raise ValueError("version_required")
    entry = _BY_ID.get(knowledge_id)
    if entry is None:
        raise ValueError("unknown_curated_knowledge")
    if entry.version != version:
        raise ValueError("unknown_curated_knowledge_version")
    return entry


def reject_curated_knowledge_operation(operation: object) -> None:
    """Fail closed for every stateful or external operation under the R9.1 boundary."""

    if operation in _FORBIDDEN_OPERATIONS:
        raise ValueError("curated_knowledge_read_only")
    raise ValueError("curated_knowledge_operation_forbidden")
