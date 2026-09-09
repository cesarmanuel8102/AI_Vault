"""Deterministic proposal-only patch benchmarking for BRAIN-101 R10.2."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping


_PROPOSAL_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_OPERATIONS = frozenset(
    {
        "patch_apply",
        "filesystem_write",
        "runtime_mutation",
        "self_governance_modification",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
    }
)


@dataclass(frozen=True)
class SandboxedPatchProposal:
    proposal_id: str
    base_revision: str
    patch_sha256: str
    apply_permitted: bool = False


@dataclass(frozen=True)
class BenchmarkReceipt:
    proposal_id: str
    benchmark_case_ids: tuple[str, ...]
    benchmark_sha256: str


@dataclass(frozen=True)
class SandboxedPatchBenchmark:
    proposal: SandboxedPatchProposal
    receipt: BenchmarkReceipt


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validated_cases(cases: Iterable[Mapping[str, object]]) -> tuple[dict[str, str], ...]:
    validated: list[dict[str, str]] = []
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        expected = case.get("expected")
        if not isinstance(case_id, str) or not _PROPOSAL_ID.fullmatch(case_id):
            raise ValueError("invalid_benchmark_case_id")
        if case_id in seen:
            raise ValueError("duplicate_benchmark_case_id")
        if not isinstance(expected, str) or not expected:
            raise ValueError("invalid_benchmark_expected")
        seen.add(case_id)
        validated.append({"case_id": case_id, "expected": expected})
    if not validated:
        raise ValueError("empty_benchmark_cases")
    return tuple(sorted(validated, key=lambda item: item["case_id"]))


def benchmark_sandboxed_patch_proposal(
    *,
    proposal_id: str,
    base_revision: str,
    unified_diff: str,
    benchmark_cases: Iterable[Mapping[str, object]],
) -> SandboxedPatchBenchmark:
    """Seal a candidate and its benchmark inputs without applying the candidate."""
    if not isinstance(proposal_id, str) or not _PROPOSAL_ID.fullmatch(proposal_id):
        raise ValueError("invalid_proposal_id")
    if not isinstance(base_revision, str) or not _SHA40.fullmatch(base_revision):
        raise ValueError("invalid_base_revision")
    if not isinstance(unified_diff, str) or not unified_diff:
        raise ValueError("invalid_unified_diff")
    cases = _validated_cases(benchmark_cases)
    proposal = SandboxedPatchProposal(
        proposal_id=proposal_id,
        base_revision=base_revision,
        patch_sha256=sha256(unified_diff.encode("utf-8")).hexdigest(),
    )
    receipt_provenance = {
        "base_revision": base_revision,
        "benchmark_cases": cases,
        "patch_sha256": proposal.patch_sha256,
        "proposal_id": proposal_id,
    }
    return SandboxedPatchBenchmark(
        proposal=proposal,
        receipt=BenchmarkReceipt(
            proposal_id=proposal_id,
            benchmark_case_ids=tuple(case["case_id"] for case in cases),
            benchmark_sha256=sha256(_canonical_json(receipt_provenance).encode("ascii")).hexdigest(),
        ),
    )


def reject_sandboxed_patch_execution(operation: str) -> None:
    """Fail closed: R10.2 records candidates and benchmarks, never executes either."""
    if operation in _FORBIDDEN_OPERATIONS:
        raise ValueError("proposal_only")
    raise ValueError("unsupported_sandboxed_patch_operation")
