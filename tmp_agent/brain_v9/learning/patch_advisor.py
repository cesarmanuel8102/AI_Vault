from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_ROOT = BASE_PATH / "tmp_agent" / "state"
PROPOSAL_REGISTRY_PATH = STATE_ROOT / "capabilities" / "proposal_registry_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _target_files(capability: str) -> List[str]:
    root = BASE_PATH / "tmp_agent" / "brain_v9"
    mapping = {
        "planning_coherence": [
            str(root / "core" / "session.py"),
            str(root / "agent" / "loop.py"),
        ],
        "execution_reliability": [
            str(root / "agent" / "loop.py"),
            str(root / "core" / "llm.py"),
        ],
        "tool_use_accuracy": [
            str(root / "agent" / "tools.py"),
            str(root / "core" / "session.py"),
        ],
        "governance_quality": [
            str(root / "governance" / "execution_gate.py"),
            str(root / "brain" / "autonomous_governance_eval.py"),
        ],
    }
    return mapping.get(capability, [str(root / "core" / "session.py")])


PROPOSAL_STATES = [
    "pending_review",
    "approved_for_sandbox",
    "sandbox_running",
    "evaluation_pending",
    "candidate_promote",
    "rejected",
    "rolled_back",
]


def _semantic_key(hypothesis: Dict[str, Any]) -> str:
    return str(hypothesis.get("semantic_key") or f"{hypothesis.get('target_capability')}:{hypothesis.get('hypothesis_id')}")


def build_patch_proposals(hypothesis_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    existing_registry = read_json(PROPOSAL_REGISTRY_PATH, default={}) or {}
    existing_by_semantic = {
        str(item.get("semantic_key")): item
        for item in existing_registry.get("proposals", [])
        if item.get("semantic_key")
    }
    grouped: Dict[str, Dict[str, Any]] = {}
    for hypothesis in hypothesis_rows:
        target_capability = hypothesis.get("target_capability") or "planning_coherence"
        group_key = _semantic_key(hypothesis)
        bucket = grouped.setdefault(group_key, {
            "target_capability": target_capability,
            "hypothesis_ids": [],
            "linked_sources": [],
            "source_attributions": [],
            "semantic_key": group_key,
        })
        bucket["hypothesis_ids"].append(hypothesis.get("hypothesis_id"))
        bucket["linked_sources"].extend(hypothesis.get("linked_sources", []))
        bucket["source_attributions"].append(hypothesis.get("source_attribution"))

    proposals: List[Dict[str, Any]] = []
    created_proposal_ids: List[str] = []
    for idx, (_group_key, bucket) in enumerate(grouped.items(), start=1):
        target_capability = bucket["target_capability"]
        existing = existing_by_semantic.get(bucket["semantic_key"]) or {}
        proposal_id = str(existing.get("proposal_id") or f"PROP_{target_capability.upper()}_{idx:03d}")
        unique_sources = sorted({s for s in bucket["linked_sources"] if s})
        unique_attributions = []
        seen_attribution = set()
        for attribution in bucket["source_attributions"]:
            if not attribution:
                continue
            key = (
                attribution.get("source_id"),
                attribution.get("pattern_id"),
                attribution.get("semantic_family"),
            )
            if key in seen_attribution:
                continue
            seen_attribution.add(key)
            unique_attributions.append(attribution)
        state_history = existing.get("state_history") or [
            {
                "state": "pending_review",
                "ts_utc": _utc_now(),
                "actor": "system",
                "reason": "proposal_created_from_curated_external_hypotheses",
            }
        ]
        proposals.append({
            "proposal_id": proposal_id,
            "hypothesis_id": bucket["hypothesis_ids"][0],
            "hypothesis_ids": bucket["hypothesis_ids"],
            "semantic_key": bucket["semantic_key"],
            "files_to_modify": _target_files(target_capability),
            "change_type": "sandbox_patch",
            "expected_benefit": f"Improve {target_capability} via a small, governed change derived from external patterns.",
            "risk_level": "medium",
            "required_tests": [
                "py_compile",
                "brain_health",
                "targeted_regression",
                "no_production_write",
                "before_after_eval_later",
            ],
            "rollback_plan": "restore backup from sandbox snapshot",
            "current_state": existing.get("current_state", "pending_review"),
            "allowed_states": PROPOSAL_STATES,
            "state_history": state_history,
            "target_capability": target_capability,
            "linked_sources": unique_sources,
            "source_attribution": unique_attributions,
            "sandbox_runs": existing.get("sandbox_runs", []),
            "last_sandbox_run_id": existing.get("last_sandbox_run_id"),
            "evaluation_history": existing.get("evaluation_history", []),
            "last_evaluator_verdict": existing.get("last_evaluator_verdict"),
            "last_evaluation_report_path": existing.get("last_evaluation_report_path"),
        })
        if not existing:
            created_proposal_ids.append(proposal_id)

    registry = {
        "updated_utc": _utc_now(),
        "status": "proposal_only",
        "proposals": proposals,
        "created_proposal_ids": created_proposal_ids,
    }
    PROPOSAL_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(PROPOSAL_REGISTRY_PATH, registry)
    return registry
