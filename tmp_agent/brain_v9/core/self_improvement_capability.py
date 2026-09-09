"""Deterministic, proposal-only capability-gap evaluation for BRAIN-101 R10.1."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping


_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_RISKS = frozenset({"P0", "P1", "P2", "P3"})
_FORBIDDEN_OPERATIONS = frozenset(
    {
        "self_governance_modification",
        "runtime_mutation",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
    }
)


@dataclass(frozen=True)
class CapabilityGap:
    capability_id: str
    risk: str


@dataclass(frozen=True)
class ImprovementProposal:
    learning_journal_reference: str
    provenance_sha256: str
    apply_permitted: bool = False


@dataclass(frozen=True)
class CapabilityGapEvaluation:
    gaps: tuple[CapabilityGap, ...]
    proposal: ImprovementProposal


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validated_requirements(requirements: Iterable[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    validated: list[dict[str, object]] = []
    seen: set[str] = set()
    for requirement in requirements:
        capability_id = requirement.get("capability_id")
        risk = requirement.get("risk")
        required = requirement.get("required")
        if not isinstance(capability_id, str) or not _CAPABILITY_ID.fullmatch(capability_id):
            raise ValueError("invalid_capability_id")
        if capability_id in seen:
            raise ValueError("duplicate_capability_id")
        if not isinstance(risk, str) or risk not in _RISKS:
            raise ValueError("invalid_risk")
        if not isinstance(required, bool):
            raise ValueError("invalid_required")
        seen.add(capability_id)
        validated.append({"capability_id": capability_id, "risk": risk, "required": required})
    return tuple(sorted(validated, key=lambda value: str(value["capability_id"])))


def evaluate_capability_gaps(
    *,
    requirements: Iterable[Mapping[str, object]],
    available_capability_ids: Iterable[str],
    learning_journal_reference: str,
) -> CapabilityGapEvaluation:
    """Evaluate declared capabilities without making, scheduling, or promoting changes."""
    if not isinstance(learning_journal_reference, str) or not learning_journal_reference.startswith("journal://"):
        raise ValueError("invalid_learning_journal_reference")
    normalized = _validated_requirements(requirements)
    available = frozenset(available_capability_ids)
    gaps = tuple(
        CapabilityGap(capability_id=str(item["capability_id"]), risk=str(item["risk"]))
        for item in normalized
        if item["required"] and item["capability_id"] not in available
    )
    provenance = {
        "gaps": [{"capability_id": gap.capability_id, "risk": gap.risk} for gap in gaps],
        "learning_journal_reference": learning_journal_reference,
        "requirements": normalized,
    }
    return CapabilityGapEvaluation(
        gaps=gaps,
        proposal=ImprovementProposal(
            learning_journal_reference=learning_journal_reference,
            provenance_sha256=sha256(_canonical_json(provenance).encode("ascii")).hexdigest(),
        ),
    )


def reject_self_improvement_execution(operation: str) -> None:
    """Fail closed: R10.1 may evaluate and propose, never execute an improvement."""
    if operation in _FORBIDDEN_OPERATIONS:
        raise ValueError("evaluation_only")
    raise ValueError("unsupported_evaluation_operation")
