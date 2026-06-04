"""
Promotion Gate v1 contract and validators.

This module is intentionally pure: no runtime imports, no filesystem writes,
no semantic-memory imports and no network calls. V1 can only approve dry-run
planning states; real writes are permanently blocked here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


PROMOTION_GATE_V1_VERSION = "1.0-dry-run-readonly"
REAL_WRITE_ALLOWED = False
DRY_RUN_ONLY_REQUIRED = True

CURATION_SCORE_THRESHOLD = 0.70
VALIDATION_SCORE_THRESHOLD = 0.75
CONFIDENCE_THRESHOLD = 0.70
TRUST_SCORE_THRESHOLD = 0.70

ALLOWED_STATES = {
    "discovered",
    "extracted",
    "normalized",
    "curated_candidate",
    "validated_candidate",
    "promotion_plan_created",
    "approval_required",
    "approved_for_dry_run",
    "dry_run_verified",
    "ready_for_readonly_runtime_lookup",
    "blocked",
    "rejected",
    "deprecated",
}

FORBIDDEN_STATES_V1 = {
    "promoted_real_write",
    "active_write",
    "allow_real_write_true",
}

SOURCE_TYPES = {
    "manual_text",
    "file",
    "github",
    "document",
    "runtime_correction",
    "test_fixture",
}

ALLOWED_PATH_PREFIXES = (
    "brain/",
    "docs/",
    "tmp_agent/state/",
    "tmp_agent/knowledge/",
    "tmp_agent/brain_v9/learning/",
    "tests/fixtures/",
    "github:",
    "https://github.com/",
    "manual:",
    "runtime:",
    "file:",
)

TERMINAL_STATES = {"blocked", "rejected", "deprecated"}

TRANSITIONS = {
    "discovered": {"extracted", "blocked", "rejected", "deprecated"},
    "extracted": {"normalized", "blocked", "rejected", "deprecated"},
    "normalized": {"curated_candidate", "blocked", "rejected", "deprecated"},
    "curated_candidate": {"validated_candidate", "blocked", "rejected", "deprecated"},
    "validated_candidate": {"promotion_plan_created", "blocked", "rejected", "deprecated"},
    "promotion_plan_created": {"approval_required", "blocked", "rejected", "deprecated"},
    "approval_required": {"approved_for_dry_run", "blocked", "rejected", "deprecated"},
    "approved_for_dry_run": {"dry_run_verified", "blocked", "rejected", "deprecated"},
    "dry_run_verified": {"ready_for_readonly_runtime_lookup", "blocked", "rejected", "deprecated"},
    "ready_for_readonly_runtime_lookup": {"deprecated", "blocked", "rejected"},
    "blocked": set(),
    "rejected": set(),
    "deprecated": set(),
}


@dataclass(frozen=True)
class FreshnessInfo:
    source_timestamp_utc: str
    evaluated_at_utc: str
    stale_after_days: int
    is_stale: bool = False


@dataclass(frozen=True)
class CheckResult:
    checked: bool
    method: str = ""
    passed: bool = True
    risk_level: str = "low"
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProvenanceBundle:
    source_id: str
    source_type: str
    source_uri_or_path: str
    content_hash: str
    extraction_method: str
    normalization_method: str
    operator_or_system: str
    timestamps: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRef:
    ref_id: str
    source_id: str
    path_or_uri: str
    quote_or_location: str
    hash: str


@dataclass(frozen=True)
class RollbackPlan:
    snapshot_required: bool
    affected_record_ids: tuple[str, ...] = ()
    inverse_operation: str = ""
    verification_steps: tuple[str, ...] = ()
    fixture_test_required: bool = True


@dataclass(frozen=True)
class PromotionCandidate:
    candidate_id: str
    source_id: str
    source_type: str
    source_uri_or_path: str
    content_hash: str
    extracted_text_hash: str
    normalized_text_hash: str
    curation_score: float
    validation_score: float
    confidence: float
    freshness: FreshnessInfo | None
    trust_score: float
    duplicate_check: CheckResult | None
    contradiction_check: CheckResult | None
    hallucination_risk_check: CheckResult | None
    provenance_bundle: ProvenanceBundle | None
    evidence_refs: tuple[EvidenceRef, ...]
    proposed_memory_payload: Mapping[str, Any]
    rollback_plan: RollbackPlan | None
    operator_approval_status: str
    dry_run_only: bool = True
    state: str = "validated_candidate"
    audit_event_created: bool = False
    observability_event_created: bool = False
    semantic_memory_unchanged: bool = False
    real_write_decision_gate_denied_write: bool = True
    dry_run_adapter_success: bool = False
    readonly_lookup_label: str = ""
    no_write_guarantee: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromotionGateDecision:
    allowed: bool
    blocked: bool
    reason_codes: tuple[str, ...] = ()
    next_state: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    version: str = PROMOTION_GATE_V1_VERSION
    real_write_allowed: bool = REAL_WRITE_ALLOWED
    dry_run_only_required: bool = DRY_RUN_ONLY_REQUIRED


def make_blocked_decision(
    reason_codes: list[str] | tuple[str, ...],
    details: Mapping[str, Any] | None = None,
) -> PromotionGateDecision:
    codes = tuple(dict.fromkeys(reason_codes))
    return PromotionGateDecision(
        allowed=False,
        blocked=True,
        reason_codes=codes,
        next_state="blocked",
        details=dict(details or {}),
    )


def make_allowed_decision(
    next_state: str,
    details: Mapping[str, Any] | None = None,
) -> PromotionGateDecision:
    return PromotionGateDecision(
        allowed=True,
        blocked=False,
        next_state=next_state,
        details=dict(details or {}),
    )


def validate_promotion_candidate(candidate: PromotionCandidate) -> PromotionGateDecision:
    reasons = evaluate_no_go_conditions(candidate)
    if reasons:
        return make_blocked_decision(reasons)
    return make_allowed_decision(candidate.state)


def validate_transition(
    from_state: str,
    to_state: str,
    candidate: PromotionCandidate,
) -> PromotionGateDecision:
    if from_state in FORBIDDEN_STATES_V1 or to_state in FORBIDDEN_STATES_V1:
        return make_blocked_decision(["forbidden_state_v1"])
    if from_state not in ALLOWED_STATES or to_state not in ALLOWED_STATES:
        return make_blocked_decision(["unknown_state"])
    if from_state in TERMINAL_STATES:
        return make_blocked_decision(["terminal_state_transition"])
    if to_state not in TRANSITIONS.get(from_state, set()):
        return make_blocked_decision(["invalid_transition"])

    reasons = evaluate_no_go_conditions(candidate)
    reasons.extend(_transition_specific_reasons(to_state, candidate))
    if reasons:
        return make_blocked_decision(reasons, {"from_state": from_state, "to_state": to_state})
    return make_allowed_decision(to_state, {"from_state": from_state, "to_state": to_state})


def evaluate_no_go_conditions(candidate: PromotionCandidate) -> list[str]:
    reasons: list[str] = []

    if not candidate.candidate_id:
        reasons.append("missing_candidate_id")
    if not candidate.source_id:
        reasons.append("missing_source_id")
    if candidate.source_type not in SOURCE_TYPES:
        reasons.append("unsupported_source_type")
    if not candidate.source_uri_or_path:
        reasons.append("missing_source_uri_or_path")
    elif _path_outside_allowed_roots(candidate.source_uri_or_path):
        reasons.append("path_outside_allowed_roots")

    if not candidate.content_hash:
        reasons.append("missing_content_hash")
    if not candidate.extracted_text_hash:
        reasons.append("missing_extracted_text_hash")
    if not candidate.normalized_text_hash:
        reasons.append("missing_normalized_text_hash")

    if candidate.state in FORBIDDEN_STATES_V1:
        reasons.append("forbidden_state_v1")
    elif candidate.state not in ALLOWED_STATES:
        reasons.append("unknown_state")

    if candidate.curation_score < CURATION_SCORE_THRESHOLD:
        reasons.append("curation_score_below_threshold")
    if candidate.validation_score < VALIDATION_SCORE_THRESHOLD:
        reasons.append("validation_score_below_threshold")
    if candidate.confidence < CONFIDENCE_THRESHOLD:
        reasons.append("confidence_below_threshold")
    if candidate.trust_score < TRUST_SCORE_THRESHOLD:
        reasons.append("trust_score_below_threshold")

    if candidate.freshness is None:
        reasons.append("missing_freshness")
    elif candidate.freshness.is_stale:
        reasons.append("stale_source")

    reasons.extend(_check_required("duplicate_check", candidate.duplicate_check))
    reasons.extend(_check_required("contradiction_check", candidate.contradiction_check))
    reasons.extend(_check_required("hallucination_risk_check", candidate.hallucination_risk_check))

    hallucination = candidate.hallucination_risk_check
    if hallucination and hallucination.risk_level.lower() in {"high", "critical"}:
        reasons.append("hallucination_risk_high")

    if candidate.provenance_bundle is None:
        reasons.append("missing_provenance")
    elif not _provenance_complete(candidate.provenance_bundle):
        reasons.append("incomplete_provenance")

    if not candidate.evidence_refs:
        reasons.append("missing_evidence_refs")
    if not candidate.proposed_memory_payload:
        reasons.append("missing_proposed_memory_payload")
    elif _payload_lacks_source_label(candidate.proposed_memory_payload):
        reasons.append("payload_lacks_source_label")

    if candidate.rollback_plan is None:
        reasons.append("missing_rollback_plan")
    elif not _rollback_plan_complete(candidate.rollback_plan):
        reasons.append("incomplete_rollback_plan")

    if candidate.operator_approval_status == "approved_for_real_write":
        reasons.append("operator_approval_real_write_forbidden")
    if candidate.operator_approval_status not in {
        "not_requested",
        "approval_required",
        "approved_for_dry_run",
        "rejected",
    }:
        reasons.append("invalid_operator_approval_status")

    if candidate.dry_run_only is not True:
        reasons.append("dry_run_only_required")
    if is_real_write_requested(candidate):
        reasons.append("real_write_requested")

    if candidate.no_write_guarantee is not True:
        reasons.append("missing_no_write_guarantee")

    return list(dict.fromkeys(reasons))


def is_real_write_requested(candidate: PromotionCandidate) -> bool:
    payload = {
        "candidate": {
            "dry_run_only": candidate.dry_run_only,
            "operator_approval_status": candidate.operator_approval_status,
            "state": candidate.state,
            "details": dict(candidate.details),
            "proposed_memory_payload": dict(candidate.proposed_memory_payload),
        }
    }
    return _contains_real_write_flag(payload)


def assert_v1_never_writes(candidate: PromotionCandidate) -> PromotionGateDecision:
    reasons: list[str] = []
    if REAL_WRITE_ALLOWED:
        reasons.append("real_write_constant_enabled")
    if not DRY_RUN_ONLY_REQUIRED:
        reasons.append("dry_run_constant_disabled")
    if is_real_write_requested(candidate):
        reasons.append("real_write_requested")
    if candidate.dry_run_only is not True:
        reasons.append("dry_run_only_required")
    if reasons:
        return make_blocked_decision(reasons)
    return make_allowed_decision(candidate.state)


def _transition_specific_reasons(to_state: str, candidate: PromotionCandidate) -> list[str]:
    reasons: list[str] = []
    if to_state in {"approval_required", "approved_for_dry_run", "dry_run_verified", "ready_for_readonly_runtime_lookup"}:
        if not candidate.audit_event_created:
            reasons.append("missing_audit_event")
        if not candidate.observability_event_created:
            reasons.append("missing_observability_event")
    if to_state == "approved_for_dry_run" and candidate.operator_approval_status != "approved_for_dry_run":
        reasons.append("operator_approval_missing")
    if to_state == "dry_run_verified":
        if not candidate.semantic_memory_unchanged:
            reasons.append("semantic_memory_unchanged_not_verified")
        if not candidate.real_write_decision_gate_denied_write:
            reasons.append("real_write_decision_gate_not_denied")
        if not candidate.dry_run_adapter_success:
            reasons.append("failed_dry_run")
    if to_state == "ready_for_readonly_runtime_lookup":
        if candidate.readonly_lookup_label not in {"curated_candidate", "verified_curated_readonly"}:
            reasons.append("missing_readonly_lookup_label")
        if not candidate.no_write_guarantee:
            reasons.append("missing_no_write_guarantee")
    return reasons


def _check_required(name: str, check: CheckResult | None) -> list[str]:
    if check is None:
        return [f"missing_{name}"]
    if check.checked is not True:
        return [f"{name}_not_checked"]
    if check.passed is not True:
        return [f"{name}_failed"]
    return []


def _contains_real_write_flag(value: Any) -> bool:
    forbidden_true_keys = {
        "allow_real_write",
        "real_write",
        "semantic_write_allowed",
        "can_execute_real_write",
        "promoted_real_write",
        "active_write",
    }
    forbidden_string_values = {
        "approved_for_real_write",
        "promoted_real_write",
        "active_write",
        "allow_real_write_true",
    }
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in forbidden_true_keys and item is True:
                return True
            if _contains_real_write_flag(item):
                return True
    elif isinstance(value, (list, tuple, set)):
        return any(_contains_real_write_flag(item) for item in value)
    elif isinstance(value, str):
        return value in forbidden_string_values
    return False


def _path_outside_allowed_roots(path: str) -> bool:
    normalized = path.replace("\\", "/").strip()
    if ".." in normalized.split("/"):
        return True
    return not any(normalized.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def _provenance_complete(provenance: ProvenanceBundle) -> bool:
    return all(
        [
            provenance.source_id,
            provenance.source_type,
            provenance.source_uri_or_path,
            provenance.content_hash,
            provenance.extraction_method,
            provenance.normalization_method,
            provenance.operator_or_system,
        ]
    )


def _payload_lacks_source_label(payload: Mapping[str, Any]) -> bool:
    source = payload.get("source")
    metadata = payload.get("metadata")
    tags = payload.get("tags")
    return not source or not isinstance(metadata, Mapping) or not tags


def _rollback_plan_complete(plan: RollbackPlan) -> bool:
    return bool(
        plan.snapshot_required
        and plan.inverse_operation
        and plan.verification_steps
        and plan.fixture_test_required
    )
