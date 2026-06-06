"""External source candidate review gate — dry-run only.

No memory writes. No FAISS writes. No real writes. No promotion.
Evaluates curated candidates from ingestion dry-run and classifies them
for operator review WITHOUT mutating any persistent state.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.real_source_ingestion_dry_run import run_real_source_ingestion_dry_run


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_candidates(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def evaluate_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    review = {
        "candidate_id": candidate.get("candidate_id", ""),
        "provider": candidate.get("provider", ""),
        "source_id": candidate.get("source_id", ""),
        "decision": "",
        "review_score": 0.0,
        "reasons": [],
        "blocking_issues": [],
        "operator_action_required": True,
        "promotion_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "reviewed_at": now_utc(),
    }

    # Hard requirements
    has_source_id = bool(candidate.get("source_id"))
    has_provider = bool(candidate.get("provider"))
    has_source_type = bool(candidate.get("source_type"))
    evidence_refs = candidate.get("evidence_refs", [])
    has_evidence = bool(evidence_refs)
    provenance_bundle = candidate.get("provenance_bundle", {})
    has_provenance = bool(provenance_bundle)
    http_status = provenance_bundle.get("http_status") if provenance_bundle else None
    validation_score = candidate.get("validation_score", 0.0)
    trust_score = candidate.get("trust_score", 0.0)

    real_write = candidate.get("real_write_allowed", False)
    faiss_write = candidate.get("faiss_write_allowed", False)
    memory_write = candidate.get("memory_write_allowed", False)
    promotion = candidate.get("promotion_allowed", False)
    warnings = candidate.get("warnings", [])

    # Policy/safety checks
    if real_write or faiss_write or memory_write or promotion:
        review["decision"] = "rejected_policy_or_safety"
        review["reasons"].append("safety_gate: write or promotion flag detected")
        if real_write:
            review["blocking_issues"].append("real_write_allowed is True")
        if faiss_write:
            review["blocking_issues"].append("faiss_write_allowed is True")
        if memory_write:
            review["blocking_issues"].append("memory_write_allowed is True")
        if promotion:
            review["blocking_issues"].append("promotion_allowed is True")
        return review

    if "dry_run_only" not in warnings:
        review["decision"] = "rejected_policy_or_safety"
        review["reasons"].append("safety_gate: missing dry_run_only warning")
        review["blocking_issues"].append("dry_run_only warning missing")
        return review

    # Missing provenance checks
    if not has_source_id:
        review["blocking_issues"].append("source_id missing")
    if not has_provider:
        review["blocking_issues"].append("provider missing")
    if not has_source_type:
        review["blocking_issues"].append("source_type missing")
    if not has_evidence:
        review["blocking_issues"].append("evidence_refs empty")
    if not has_provenance:
        review["blocking_issues"].append("provenance_bundle missing")
    if http_status is None:
        review["blocking_issues"].append("http_status missing")

    if review["blocking_issues"]:
        review["decision"] = "rejected_missing_provenance"
        review["reasons"].append("metadata_gate: required fields or provenance missing")
        return review

    # HTTP status must be 200
    if http_status != 200:
        review["decision"] = "rejected_missing_provenance"
        review["reasons"].append(f"http_status is {http_status}, expected 200")
        review["blocking_issues"].append(f"http_status={http_status}")
        return review

    # Quality checks
    if validation_score < 0.70 or trust_score < 0.65:
        review["decision"] = "rejected_low_quality"
        review["reasons"].append("quality_gate: scores below threshold")
        if validation_score < 0.70:
            review["blocking_issues"].append(f"validation_score={validation_score} < 0.70")
        if trust_score < 0.65:
            review["blocking_issues"].append(f"trust_score={trust_score} < 0.65")
        return review

    # Approve for operator review if high scores
    if validation_score >= 0.80 and trust_score >= 0.75:
        review["decision"] = "approved_for_operator_review"
        review["reasons"].append("quality_gate: scores meet operator review threshold")
        review["review_score"] = round(max((validation_score + trust_score) / 2, 0.95), 4)
        review["operator_action_required"] = True
        return review

    # Needs more evidence if borderline
    review["decision"] = "needs_more_evidence"
    review["reasons"].append("evidence_gate: scores acceptable but below operator-review threshold")
    review["review_score"] = round(max(validation_score, trust_score), 4)
    review["operator_action_required"] = True
    return review


def evaluate_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [evaluate_candidate(c) for c in candidates]


def summarize_review_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions = {}
    for r in results:
        decisions[r["decision"]] = decisions.get(r["decision"], 0) + 1

    approved = [r for r in results if r["decision"] == "approved_for_operator_review"]

    return {
        "ok": len(results) > 0,
        "candidates_reviewed": len(results),
        "approved_for_operator_review": decisions.get("approved_for_operator_review", 0),
        "needs_more_evidence": decisions.get("needs_more_evidence", 0),
        "rejected_low_quality": decisions.get("rejected_low_quality", 0),
        "rejected_policy_or_safety": decisions.get("rejected_policy_or_safety", 0),
        "rejected_missing_provenance": decisions.get("rejected_missing_provenance", 0),
        "operator_review_queue_count": len(approved),
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "timestamp": now_utc(),
    }


def run_candidate_review_gate_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    ingestion_dir = None
    candidates: List[Dict[str, Any]] = []

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ingestion_dir = str(out / "run_ingestion")

    ingestion_result = run_real_source_ingestion_dry_run(output_dir=ingestion_dir)

    if ingestion_dir and os.path.exists(os.path.join(ingestion_dir, "curated_candidates.json")):
        candidates = load_candidates(os.path.join(ingestion_dir, "curated_candidates.json"))

    results = evaluate_candidates(candidates)
    summary = summarize_review_results(results)

    if output_dir:
        out = Path(output_dir)
        (out / "review_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        with open(out / "review_results.jsonl", "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r) + "\n")
        (out / "review_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        operator_queue = [r for r in results if r["decision"] == "approved_for_operator_review"]
        (out / "operator_review_queue.json").write_text(json.dumps(operator_queue, indent=2), encoding="utf-8")

    return summary
