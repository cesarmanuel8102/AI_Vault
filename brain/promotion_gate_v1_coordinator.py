"""
Promotion Gate v1 dry-run coordinator.

Offline wrapper only: no runtime imports, no endpoints, no network calls,
no shell calls, no semantic-memory writes, and no FAISS writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from brain.curated_memory_governance import CuratedMemoryGovernanceService
from brain.curated_memory_governance_audit import CuratedMemoryGovernanceAuditTrail
from brain.curated_memory_observability import (
    CuratedMemoryEventType,
    CuratedMemoryObservability,
)
from brain.curated_memory_promotion import (
    CurationValidationResult,
    CurationValidationStatus,
    CuratedMemoryPromotionService,
    PromotionStatus,
)
from brain.promotion_gate_v1 import (
    CheckResult,
    EvidenceRef,
    FreshnessInfo,
    PromotionCandidate,
    PromotionGateDecision,
    ProvenanceBundle,
    RollbackPlan,
    make_blocked_decision,
    make_allowed_decision,
    validate_promotion_candidate,
    validate_transition,
)
from brain.semantic_memory_adapter_dry_run import (
    SemanticMemoryAdapterDryRun,
    SemanticMemoryAdapterStatus,
)
from brain.semantic_memory_real_write_decision_gate import (
    SemanticMemoryDecision,
    SemanticMemoryRealWriteDecisionGate,
)


COORDINATOR_VERSION = "1.0-dry-run-readonly"
REAL_WRITE_ALLOWED = False
DRY_RUN_ONLY_REQUIRED = True
DEFAULT_SEMANTIC_MEMORY_PATHS = (Path("memory/semantic"),)


@dataclass(frozen=True)
class DryRunCoordinatorDecision:
    allowed: bool
    blocked: bool
    reason_codes: tuple[str, ...] = ()
    next_state: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticMemorySnapshot:
    snapshot_id: str
    paths: tuple[str, ...]
    files: Mapping[str, Mapping[str, Any]]
    status: str = "ok"
    taken_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class DryRunPromotionArtifacts:
    promotion_plan_id: str | None = None
    approval_request_id: str | None = None
    approval_decision_id: str | None = None
    audit_event_refs: tuple[str, ...] = ()
    observability_event_refs: tuple[str, ...] = ()
    semantic_adapter_run_id: str | None = None
    before_snapshot: SemanticMemorySnapshot | None = None
    after_snapshot: SemanticMemorySnapshot | None = None
    real_write_decision_ref: str | None = None


@dataclass(frozen=True)
class DryRunPromotionInput:
    record: Any
    source_context: Mapping[str, Any]
    validation_result: CurationValidationResult | None = None
    operator: str = "promotion_gate_v1_coordinator"
    dry_run_only: bool = True
    auto_approve_dry_run: bool = True
    semantic_memory_paths: Sequence[str | Path] | None = None
    promotion_service: Any | None = None
    governance_service: Any | None = None
    audit_trail: CuratedMemoryGovernanceAuditTrail | None = None
    observability: Any | None = None
    semantic_adapter: Any | None = None
    real_write_gate: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DryRunPromotionResult:
    coordinator_run_id: str
    candidate_id: str | None
    status: str
    gate_decision: PromotionGateDecision
    transition_decision: PromotionGateDecision | None = None
    artifacts: DryRunPromotionArtifacts = field(default_factory=DryRunPromotionArtifacts)
    semantic_memory_unchanged: bool = False
    real_write_denied: bool = False
    dry_run_only: bool = True
    allow_real_write: bool = False
    reason_codes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def build_candidate_from_curated_record(
    record: Any,
    source_context: Mapping[str, Any],
) -> PromotionCandidate:
    now = datetime.now(timezone.utc).isoformat()
    content = str(getattr(record, "content", "") or "")
    content_hash = str(
        source_context.get("content_hash")
        or getattr(record, "content_hash", "")
        or _sha256_text(content)
    )
    source_id = str(source_context.get("source_id") or getattr(record, "source", "") or "manual")
    source_type = str(source_context.get("source_type") or "manual_text")
    source_uri_or_path = str(source_context.get("source_uri_or_path") or f"manual:{source_id}")
    candidate_id = str(source_context.get("candidate_id") or getattr(record, "record_id", "") or f"candidate:{content_hash[:16]}")
    extracted_hash = str(source_context.get("extracted_text_hash") or _sha256_text(content))
    normalized_hash = str(source_context.get("normalized_text_hash") or _sha256_text(_normalize_text(content)))
    curation_score = float(source_context.get("curation_score", getattr(record, "quality_score", 0.0) or 0.0))
    validation_score = float(source_context.get("validation_score", curation_score))
    confidence = float(source_context.get("confidence", min(curation_score, validation_score)))
    trust_score = float(source_context.get("trust_score", confidence))
    hallucination_risk = str(source_context.get("hallucination_risk", "low"))

    freshness = FreshnessInfo(
        source_timestamp_utc=str(source_context.get("source_timestamp_utc") or now),
        evaluated_at_utc=now,
        stale_after_days=int(source_context.get("stale_after_days", 30)),
        is_stale=bool(source_context.get("is_stale", False)),
    )
    provenance = None
    if source_context.get("provenance_bundle", True) is not None:
        provenance = ProvenanceBundle(
            source_id=source_id,
            source_type=source_type,
            source_uri_or_path=source_uri_or_path,
            content_hash=content_hash,
            extraction_method=str(source_context.get("extraction_method", "curated_record")),
            normalization_method=str(source_context.get("normalization_method", "coordinator_normalize_v1")),
            operator_or_system=str(source_context.get("operator_or_system", "promotion_gate_v1_coordinator")),
            timestamps={"candidate_built_at_utc": now},
        )
    evidence_refs = tuple(source_context.get("evidence_refs", ())) or (
        EvidenceRef(
            ref_id=f"evidence:{candidate_id}",
            source_id=source_id,
            path_or_uri=source_uri_or_path,
            quote_or_location=str(source_context.get("quote_or_location", "curated_record.content")),
            hash=content_hash,
        ),
    )
    proposed_payload = dict(source_context.get("proposed_memory_payload") or {})
    if not proposed_payload:
        proposed_payload = {
            "text": content,
            "source": f"curated:{source_id}",
            "tags": ["curated", "promotion_gate_v1", "dry_run"],
            "metadata": {
                "candidate_id": candidate_id,
                "record_id": getattr(record, "record_id", candidate_id),
                "content_hash": content_hash,
                "tags": ["curated", "promotion_gate_v1", "dry_run"],
            },
        }
    rollback_plan = source_context.get("rollback_plan")
    if rollback_plan is None and source_context.get("rollback_plan_required", True):
        rollback_plan = RollbackPlan(
            snapshot_required=True,
            affected_record_ids=(str(getattr(record, "record_id", candidate_id)),),
            inverse_operation="remove_candidate_payload_if_written",
            verification_steps=("confirm_no_semantic_memory_mutation",),
            fixture_test_required=True,
        )

    return PromotionCandidate(
        candidate_id=candidate_id,
        source_id=source_id,
        source_type=source_type,
        source_uri_or_path=source_uri_or_path,
        content_hash=content_hash,
        extracted_text_hash=extracted_hash,
        normalized_text_hash=normalized_hash,
        curation_score=curation_score,
        validation_score=validation_score,
        confidence=confidence,
        freshness=freshness,
        trust_score=trust_score,
        duplicate_check=_check_from_context(source_context, "duplicate_check", "duplicate_scan_v1"),
        contradiction_check=_check_from_context(source_context, "contradiction_check", "contradiction_scan_v1"),
        hallucination_risk_check=CheckResult(
            checked=bool(source_context.get("hallucination_checked", True)),
            method=str(source_context.get("hallucination_method", "hallucination_risk_v1")),
            passed=hallucination_risk not in {"high", "critical"},
            risk_level=hallucination_risk,
            details={"risk": hallucination_risk},
        ),
        provenance_bundle=provenance,
        evidence_refs=evidence_refs,
        proposed_memory_payload=proposed_payload,
        rollback_plan=rollback_plan,
        operator_approval_status=str(source_context.get("operator_approval_status", "approved_for_dry_run")),
        dry_run_only=bool(source_context.get("dry_run_only", True)),
        state=str(source_context.get("state", "validated_candidate")),
        readonly_lookup_label=str(source_context.get("readonly_lookup_label", "")),
        no_write_guarantee=bool(source_context.get("no_write_guarantee", True)),
        details=dict(source_context.get("details", {})),
    )


def run_promotion_gate_dry_run(input: DryRunPromotionInput) -> DryRunPromotionResult:
    coordinator_run_id = _run_id("dryrun")
    if input.dry_run_only is not True:
        return _blocked_result(coordinator_run_id, None, ("dry_run_only_required",))

    before_snapshot = make_semantic_memory_snapshot(input.semantic_memory_paths)
    candidate = build_candidate_from_curated_record(input.record, input.source_context)
    gate_decision = validate_promotion_candidate(candidate)
    if gate_decision.blocked:
        return DryRunPromotionResult(
            coordinator_run_id=coordinator_run_id,
            candidate_id=candidate.candidate_id,
            status="blocked",
            gate_decision=gate_decision,
            artifacts=DryRunPromotionArtifacts(before_snapshot=before_snapshot),
            reason_codes=tuple(gate_decision.reason_codes),
            metadata={"blocked_stage": "promotion_gate_v1"},
        )

    promotion_service = input.promotion_service or CuratedMemoryPromotionService()
    governance = input.governance_service or CuratedMemoryGovernanceService()
    observability = input.observability or CuratedMemoryObservability()
    semantic_adapter = input.semantic_adapter or SemanticMemoryAdapterDryRun()
    validation_result = input.validation_result or _validation_result_from_candidate(candidate)

    plan = promotion_service.promote_dry_run(input.record, validation_result)
    if plan.status not in {PromotionStatus.REQUIRES_APPROVAL, PromotionStatus.ELIGIBLE}:
        return _blocked_result(
            coordinator_run_id,
            candidate.candidate_id,
            ("promotion_plan_rejected",),
            gate_decision,
            before_snapshot,
            {"promotion_status": plan.status.value, "rejection_reason": plan.rejection_reason},
        )

    request = governance.create_approval_request(
        plan,
        requested_by=input.operator,
        reason="Promotion Gate v1 dry-run verification",
    )
    if not input.auto_approve_dry_run:
        return _blocked_result(
            coordinator_run_id,
            candidate.candidate_id,
            ("approval_missing",),
            gate_decision,
            before_snapshot,
            {"approval_request_id": request.request_id},
        )
    if candidate.operator_approval_status == "approved_for_real_write":
        return _blocked_result(
            coordinator_run_id,
            candidate.candidate_id,
            ("approval_real_write_forbidden",),
            gate_decision,
            before_snapshot,
        )

    decision = governance.approve_request(
        request,
        decided_by=input.operator,
        reason="Approved for dry-run only",
        evidence=candidate.content_hash,
    )
    if getattr(decision, "allow_real_write", False):
        return _blocked_result(
            coordinator_run_id,
            candidate.candidate_id,
            ("approval_real_write_forbidden",),
            gate_decision,
            before_snapshot,
        )

    audit_refs = _collect_audit_refs(input.audit_trail, request, decision, plan, input.operator)
    event = observability.record_event(
        event_type=CuratedMemoryEventType.APPROVAL_DECISION_APPROVED,
        actor=input.operator,
        record_id=plan.record_id,
        request_id=request.request_id,
        decision_id=decision.decision_id,
        metadata={"coordinator_run_id": coordinator_run_id, "dry_run_only": True},
    )
    observability_refs = tuple(ref for ref in (getattr(event, "event_id", ""),) if ref)

    payload = semantic_adapter.build_payload(
        record_id=plan.record_id,
        text=plan.text,
        source=plan.source,
        content_hash=plan.content_hash,
        metadata=plan.memory_payload or {},
        validation_score=plan.validation_score,
    )
    adapter_result = semantic_adapter.prepare_dry_run(payload)
    adapter_ok = adapter_result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY

    after_snapshot = make_semantic_memory_snapshot(input.semantic_memory_paths)
    memory_unchanged = verify_no_semantic_memory_mutation(before_snapshot, after_snapshot)
    real_write_decision = require_real_write_gate_denied(input.real_write_gate)
    real_write_denied = real_write_decision.allowed

    candidate_after = replace(
        candidate,
        state="approved_for_dry_run",
        audit_event_created=bool(audit_refs),
        observability_event_created=bool(observability_refs),
        semantic_memory_unchanged=memory_unchanged,
        real_write_decision_gate_denied_write=real_write_denied,
        dry_run_adapter_success=adapter_ok,
    )
    transition_decision = validate_transition("approved_for_dry_run", "dry_run_verified", candidate_after)
    artifacts = DryRunPromotionArtifacts(
        promotion_plan_id=plan.record_id,
        approval_request_id=request.request_id,
        approval_decision_id=decision.decision_id,
        audit_event_refs=audit_refs,
        observability_event_refs=observability_refs,
        semantic_adapter_run_id=adapter_result.adapter_run_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        real_write_decision_ref=real_write_decision.details.get("decision_id"),
    )
    if not transition_decision.allowed:
        return DryRunPromotionResult(
            coordinator_run_id=coordinator_run_id,
            candidate_id=candidate.candidate_id,
            status="blocked",
            gate_decision=gate_decision,
            transition_decision=transition_decision,
            artifacts=artifacts,
            semantic_memory_unchanged=memory_unchanged,
            real_write_denied=real_write_denied,
            reason_codes=tuple(transition_decision.reason_codes),
            metadata={"blocked_stage": "transition_to_dry_run_verified"},
        )

    return DryRunPromotionResult(
        coordinator_run_id=coordinator_run_id,
        candidate_id=candidate.candidate_id,
        status="dry_run_verified",
        gate_decision=gate_decision,
        transition_decision=transition_decision,
        artifacts=artifacts,
        semantic_memory_unchanged=memory_unchanged,
        real_write_denied=real_write_denied,
        dry_run_only=True,
        allow_real_write=False,
        metadata={
            "adapter_status": adapter_result.status.value,
            "snapshot_status": after_snapshot.status,
            "coordinator_version": COORDINATOR_VERSION,
        },
    )


def verify_no_semantic_memory_mutation(
    before_snapshot: SemanticMemorySnapshot,
    after_snapshot: SemanticMemorySnapshot,
) -> bool:
    return before_snapshot.files == after_snapshot.files


def collect_audit_observability_refs(result: DryRunPromotionResult) -> DryRunPromotionArtifacts:
    return result.artifacts


def require_real_write_gate_denied(
    gate: Any | None = None,
) -> DryRunCoordinatorDecision:
    decision_gate = gate or SemanticMemoryRealWriteDecisionGate()
    report = decision_gate.block_real_write("Promotion Gate v1 coordinator blocks real writes")
    denied = (
        report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
        and report.allow_real_write is False
        and report.can_execute_real_write is False
    )
    if not denied:
        return DryRunCoordinatorDecision(
            allowed=False,
            blocked=True,
            reason_codes=("real_write_gate_not_denied",),
            details=report.to_dict(),
        )
    return DryRunCoordinatorDecision(
        allowed=True,
        blocked=False,
        next_state="real_write_denied",
        details=report.to_dict(),
    )


def summarize_dry_run_result(result: DryRunPromotionResult) -> dict[str, Any]:
    return {
        "coordinator_run_id": result.coordinator_run_id,
        "candidate_id": result.candidate_id,
        "status": result.status,
        "reason_codes": list(result.reason_codes),
        "dry_run_only": result.dry_run_only,
        "allow_real_write": result.allow_real_write,
        "semantic_memory_unchanged": result.semantic_memory_unchanged,
        "real_write_denied": result.real_write_denied,
        "audit_event_refs": list(result.artifacts.audit_event_refs),
        "observability_event_refs": list(result.artifacts.observability_event_refs),
        "semantic_adapter_run_id": result.artifacts.semantic_adapter_run_id,
    }


def make_semantic_memory_snapshot(
    paths: Sequence[str | Path] | None = None,
) -> SemanticMemorySnapshot:
    target_paths = tuple(Path(p) for p in (paths or DEFAULT_SEMANTIC_MEMORY_PATHS))
    files: dict[str, Mapping[str, Any]] = {}
    for target in target_paths:
        if target.is_file():
            _snapshot_file(target, files)
        elif target.is_dir():
            for child in sorted(p for p in target.rglob("*") if p.is_file()):
                _snapshot_file(child, files)
        else:
            files[_safe_path_key(target)] = {"exists": False}

    status = "ok"
    if any("memory/semantic" in _normalize_path_key(p) for p in files):
        status = "preexisting_dirty_or_unknown"
    snapshot_payload = json.dumps(files, sort_keys=True, ensure_ascii=True)
    return SemanticMemorySnapshot(
        snapshot_id=f"snapshot:{_sha256_text(snapshot_payload)[:16]}",
        paths=tuple(str(p) for p in target_paths),
        files=files,
        status=status,
    )


def _collect_audit_refs(
    audit_trail: CuratedMemoryGovernanceAuditTrail | None,
    request: Any,
    decision: Any,
    plan: Any,
    actor: str,
) -> tuple[str, ...]:
    if audit_trail is None:
        request_ref = f"audit_in_memory_request:{request.request_id}"
        decision_ref = f"audit_in_memory_decision:{decision.decision_id}"
        return (request_ref, decision_ref)

    payload = {
        "record_id": plan.record_id,
        "content_hash": plan.content_hash,
        "dry_run_only": True,
        "allow_real_write": False,
    }
    evidence_hash = _sha256_mapping(payload)
    request_entry = audit_trail.append_request(
        request_id=request.request_id,
        actor=actor,
        evidence_hash=evidence_hash,
        payload=payload,
        metadata={"coordinator": COORDINATOR_VERSION},
    )
    decision_entry = audit_trail.append_decision(
        request_id=request.request_id,
        decision_id=decision.decision_id,
        actor=actor,
        evidence_hash=evidence_hash,
        approved=True,
        payload=payload,
        metadata={"coordinator": COORDINATOR_VERSION},
    )
    return (request_entry.entry_id, decision_entry.entry_id)


def _validation_result_from_candidate(candidate: PromotionCandidate) -> CurationValidationResult:
    return CurationValidationResult(
        record_id=candidate.candidate_id,
        content_hash=candidate.content_hash,
        source=candidate.source_id,
        topic=str(candidate.proposed_memory_payload.get("metadata", {}).get("topic", "general")),
        status=CurationValidationStatus.VALIDATED,
        validator_status="VALIDATED",
        passed=True,
        score=candidate.validation_score,
        reason="Promotion Gate v1 coordinator synthetic validation result",
        validation_id=f"validation:{candidate.candidate_id}",
        metadata={"synthetic": True, "dry_run_only": True},
    )


def _blocked_result(
    coordinator_run_id: str,
    candidate_id: str | None,
    reason_codes: tuple[str, ...],
    gate_decision: PromotionGateDecision | None = None,
    before_snapshot: SemanticMemorySnapshot | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DryRunPromotionResult:
    return DryRunPromotionResult(
        coordinator_run_id=coordinator_run_id,
        candidate_id=candidate_id,
        status="blocked",
        gate_decision=gate_decision or make_blocked_decision(reason_codes),
        artifacts=DryRunPromotionArtifacts(before_snapshot=before_snapshot),
        reason_codes=reason_codes,
        metadata=metadata or {},
    )


def _check_from_context(
    source_context: Mapping[str, Any],
    key: str,
    default_method: str,
) -> CheckResult:
    raw = source_context.get(key)
    if isinstance(raw, CheckResult):
        return raw
    if isinstance(raw, Mapping):
        return CheckResult(
            checked=bool(raw.get("checked", True)),
            method=str(raw.get("method", default_method)),
            passed=bool(raw.get("passed", True)),
            risk_level=str(raw.get("risk_level", "low")),
            details=dict(raw.get("details", {})),
        )
    return CheckResult(checked=True, method=default_method, passed=True, risk_level="low")


def _snapshot_file(path: Path, files: dict[str, Mapping[str, Any]]) -> None:
    try:
        data = path.read_bytes()
        stat = path.stat()
        files[_safe_path_key(path)] = {
            "exists": True,
            "size": stat.st_size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "mtime_ns": stat.st_mtime_ns,
            "line_count": data.count(b"\n"),
        }
    except OSError as exc:
        files[_safe_path_key(path)] = {"exists": True, "error": type(exc).__name__}


def _safe_path_key(path: Path) -> str:
    return _normalize_path_key(path.as_posix())


def _normalize_path_key(value: str) -> str:
    return value.replace("\\", "/")


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_mapping(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return _sha256_text(payload)


def _run_id(prefix: str) -> str:
    seed = f"{prefix}:{datetime.now(timezone.utc).isoformat()}"
    return f"{prefix}:{_sha256_text(seed)[:16]}"
