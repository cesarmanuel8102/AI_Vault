"""R9.2 planning-only boundary for a controlled curated-knowledge canary."""
from __future__ import annotations

from dataclasses import dataclass

from tmp_agent.brain_v9.core.curated_knowledge_catalog import lookup_curated_knowledge


_MAX_CANARY_LIMIT = 10
_EFFECTFUL_OPERATIONS = frozenset(
    {
        "source_ingestion",
        "semantic_memory_write",
        "network_fetch",
        "provider_call",
        "automatic_promotion",
    }
)


@dataclass(frozen=True)
class CanaryIngestionPlan:
    """A bounded proposal that intentionally cannot execute or promote knowledge."""

    knowledge_id: str
    version: str
    catalog_provenance: str
    candidate_reference: str
    benchmark_id: str
    canary_limit: int
    execution_permitted: bool = False
    automatic_promotion_permitted: bool = False


def plan_canary_ingestion(
    *,
    knowledge_id: str,
    version: str,
    candidate_reference: str,
    benchmark_id: str,
    canary_limit: int,
) -> CanaryIngestionPlan:
    """Create an offline, bounded benchmark plan from a versioned catalog entry."""

    entry = lookup_curated_knowledge(knowledge_id, version=version)
    if not isinstance(candidate_reference, str) or not candidate_reference:
        raise ValueError("candidate_reference_required")
    if not candidate_reference.startswith("candidate://"):
        raise ValueError("external_source_reference_forbidden")
    if not isinstance(benchmark_id, str) or not benchmark_id:
        raise ValueError("benchmark_id_required")
    if isinstance(canary_limit, bool) or not isinstance(canary_limit, int) or not 1 <= canary_limit <= _MAX_CANARY_LIMIT:
        raise ValueError("invalid_canary_limit")
    return CanaryIngestionPlan(
        knowledge_id=entry.knowledge_id,
        version=entry.version,
        catalog_provenance=entry.provenance_reference,
        candidate_reference=candidate_reference,
        benchmark_id=benchmark_id,
        canary_limit=canary_limit,
    )


def reject_canary_execution(operation: object) -> None:
    """Fail closed for all external or stateful operations under the planning boundary."""

    if operation in _EFFECTFUL_OPERATIONS:
        raise ValueError("canary_planning_only")
    raise ValueError("canary_operation_forbidden")
