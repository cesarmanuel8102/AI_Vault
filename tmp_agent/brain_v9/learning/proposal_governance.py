from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.core.state_io import read_json, write_json
from brain_v9.learning.external_intel_ingestor import _append_event
from brain_v9.learning.patch_advisor import PROPOSAL_REGISTRY_PATH, PROPOSAL_STATES

TRANSITIONS = {
    "pending_review": ["approved_for_sandbox", "rejected"],
    "approved_for_sandbox": ["sandbox_running", "rejected"],
    "sandbox_running": ["evaluation_pending", "rolled_back"],
    "evaluation_pending": ["candidate_promote", "rejected", "rolled_back"],
    "candidate_promote": [],
    "rejected": [],
    "rolled_back": [],
}

IMPACT_BY_CAPABILITY = {
    "planning_coherence": 0.85,
    "execution_reliability": 0.82,
    "tool_use_accuracy": 0.80,
    "governance_quality": 0.78,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _evidence_strength_score(proposal: Dict[str, Any]) -> float:
    attributions = proposal.get("source_attribution") or []
    evidence_refs = []
    for attr in attributions:
        evidence_refs.extend(attr.get("evidence_refs", []))
    sources = {attr.get("source_id") for attr in attributions if attr.get("source_id")}
    score = 0.35 + min(0.25, 0.08 * len(evidence_refs)) + min(0.2, 0.1 * len(sources))
    return round(min(score, 1.0), 2)


def _implementation_size_score(proposal: Dict[str, Any]) -> float:
    files = proposal.get("files_to_modify") or []
    return round(min(0.15 * len(files), 1.0), 2)


def _confidence_score(proposal: Dict[str, Any]) -> float:
    sources = proposal.get("linked_sources") or []
    evidence = proposal.get("source_attribution") or []
    score = 0.4 + min(0.3, 0.1 * len(sources)) + min(0.2, 0.05 * len(evidence))
    return round(min(score, 1.0), 2)


def _risk_score(proposal: Dict[str, Any]) -> float:
    risk_level = str(proposal.get("risk_level") or "medium").lower()
    return {"low": 0.25, "medium": 0.5, "high": 0.8}.get(risk_level, 0.5)


def _impact_score(proposal: Dict[str, Any]) -> float:
    return IMPACT_BY_CAPABILITY.get(proposal.get("target_capability"), 0.7)


def score_proposal(proposal: Dict[str, Any]) -> Dict[str, Any]:
    proposal.pop("_is_new", None)
    impact_score = _impact_score(proposal)
    confidence_score = _confidence_score(proposal)
    evidence_strength_score = _evidence_strength_score(proposal)
    implementation_size_score = _implementation_size_score(proposal)
    risk_score = _risk_score(proposal)
    priority = (
        impact_score * 0.35
        + confidence_score * 0.20
        + evidence_strength_score * 0.20
        - risk_score * 0.15
        - implementation_size_score * 0.10
    )
    proposal["impact_score"] = round(impact_score, 2)
    proposal["confidence_score"] = round(confidence_score, 2)
    proposal["evidence_strength_score"] = round(evidence_strength_score, 2)
    proposal["implementation_size_score"] = round(implementation_size_score, 2)
    proposal["risk_score"] = round(risk_score, 2)
    proposal["proposal_priority_score"] = round(priority, 4)
    proposal["allowed_next_states"] = TRANSITIONS.get(proposal.get("current_state"), [])
    proposal.setdefault("allowed_states", PROPOSAL_STATES)
    return proposal


def rank_proposals(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scored = [score_proposal(dict(p)) for p in proposals]
    scored.sort(key=lambda p: (p.get("proposal_priority_score", 0.0), p.get("evidence_strength_score", 0.0)), reverse=True)
    return scored


def load_registry() -> Dict[str, Any]:
    payload = read_json(PROPOSAL_REGISTRY_PATH, default={}) or {}
    if not payload:
        return {"updated_utc": _utc_now(), "status": "proposal_only", "proposals": []}
    payload["proposals"] = rank_proposals(payload.get("proposals", []))
    return payload


def save_registry(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(payload)
    payload["updated_utc"] = _utc_now()
    payload["proposals"] = rank_proposals(payload.get("proposals", []))
    write_json(PROPOSAL_REGISTRY_PATH, payload)
    return payload


def transition_proposal_state(proposal_id: str, target_state: str, *, actor: str, reason: str) -> Dict[str, Any]:
    registry = load_registry()
    proposals = registry.get("proposals", [])
    proposal = next((p for p in proposals if p.get("proposal_id") == proposal_id), None)
    if proposal is None:
        return {"success": False, "error": "proposal_not_found", "proposal_id": proposal_id}
    current_state = proposal.get("current_state")
    allowed = TRANSITIONS.get(current_state, [])
    if target_state not in allowed:
        return {
            "success": False,
            "error": "invalid_transition",
            "proposal_id": proposal_id,
            "current_state": current_state,
            "target_state": target_state,
            "allowed_next_states": allowed,
        }
    proposal["current_state"] = target_state
    proposal.setdefault("state_history", []).append({
        "state": target_state,
        "ts_utc": _utc_now(),
        "actor": actor,
        "reason": reason,
    })
    updated = save_registry(registry)
    _append_event("proposal_state_changed", {
        "proposal_id": proposal_id,
        "from_state": current_state,
        "to_state": target_state,
        "actor": actor,
        "reason": reason,
    })
    fresh = next((p for p in updated.get("proposals", []) if p.get("proposal_id") == proposal_id), proposal)
    return {
        "success": True,
        "proposal_id": proposal_id,
        "from_state": current_state,
        "to_state": target_state,
        "proposal": fresh,
    }
