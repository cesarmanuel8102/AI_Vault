from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
from typing import Any, Dict

from brain_v9.core.state_io import read_json, write_json
from brain_v9.learning.external_intel_ingestor import _append_event
from brain_v9.learning.proposal_governance import load_registry, save_registry, transition_proposal_state
from brain_v9.learning.sandbox_executor import _proposal_lookup
from brain_v9.learning.status import CAPABILITY_SCORECARD_PATH

VALID_VERDICTS = {
    "insufficient_evidence",
    "evaluation_passed_candidate",
    "evaluation_failed",
    "needs_more_tests",
}

TARGETED_TESTS = {
    "governance_quality": [
        r"C:\AI_VAULT\tests\unit\test_learning_pipeline.py",
        r"C:\AI_VAULT\tests\unit\test_autonomous_governance_eval.py",
    ],
    "tool_use_accuracy": [
        r"C:\AI_VAULT\tests\unit\test_brain_chat_hygiene.py",
        r"C:\AI_VAULT\tests\unit\test_network_scan_regressions.py",
        r"C:\AI_VAULT\tests\unit\test_grounded_code_fastpath.py",
    ],
    "planning_coherence": [
        r"C:\AI_VAULT\tests\unit\test_brain_chat_hygiene.py",
        r"C:\AI_VAULT\tests\unit\test_llm_codex_integration.py",
    ],
    "execution_reliability": [
        r"C:\AI_VAULT\tests\unit\test_learning_pipeline.py",
        r"C:\AI_VAULT\tests\unit\test_llm_codex_integration.py",
    ],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _latest_sandbox_run(proposal: Dict[str, Any], run_id: str | None = None) -> Dict[str, Any] | None:
    runs = proposal.get("sandbox_runs", []) or []
    if run_id:
        return next((r for r in runs if r.get("run_id") == run_id), None)
    if not runs:
        return None
    return sorted(runs, key=lambda item: item.get("completed_at_utc", ""), reverse=True)[0]


def _safe_read(path_value: str | None) -> Dict[str, Any]:
    if not path_value:
        return {}
    return read_json(Path(path_value), default={}) or {}


def _no_production_write(evaluation_summary: Dict[str, Any]) -> bool:
    integrity = evaluation_summary.get("production_integrity") or {}
    before = {row.get("source_path"): row for row in integrity.get("before", []) or []}
    after = {row.get("source_path"): row for row in integrity.get("after", []) or []}
    if not before or not after:
        return False
    for path, row_before in before.items():
        row_after = after.get(path) or {}
        if row_before.get("exists") != row_after.get("exists"):
            return False
        if row_before.get("sha256") != row_after.get("sha256"):
            return False
        if row_before.get("size_bytes") != row_after.get("size_bytes"):
            return False
    return True


def _targeted_regression(target_capability: str) -> Dict[str, Any]:
    tests = TARGETED_TESTS.get(target_capability, [r"C:\AI_VAULT\tests\unit\test_learning_pipeline.py"])
    cmd = [
        "python",
        "-m",
        "pytest",
        *tests,
        "-q",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = r"C:\AI_VAULT\tmp_agent;C:\AI_VAULT"
    result = subprocess.run(
        cmd,
        cwd=r"C:\AI_VAULT",
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "tests": tests,
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
    }


def _evidence_refs_present(proposal: Dict[str, Any]) -> bool:
    for attr in proposal.get("source_attribution", []) or []:
        if attr.get("evidence_refs"):
            return True
    return False


def _evidence_ref_count(proposal: Dict[str, Any]) -> int:
    count = 0
    for attr in proposal.get("source_attribution", []) or []:
        count += len(attr.get("evidence_refs", []) or [])
    return count


def _readiness_score(metrics: Dict[str, Any], base_score: float) -> float:
    score = float(base_score)
    score += 0.05 if metrics.get("py_compile_ok") else -0.08
    score += 0.05 if metrics.get("files_copied_ok") else -0.05
    score += 0.05 if metrics.get("proposal_has_evidence_refs") else -0.08
    score += 0.05 if metrics.get("source_attribution_present") else -0.05
    score += 0.04 if metrics.get("rollback_manifest_present") else -0.05
    score += 0.04 if metrics.get("lifecycle_integrity_ok") else -0.05
    score += 0.04 if metrics.get("targeted_regression", {}).get("ok") else -0.07
    score += 0.03 if metrics.get("implementation_size_ok") else -0.04
    score += min(0.08, 0.02 * int(metrics.get("evidence_ref_count", 0) or 0))
    score -= min(0.10, 0.08 * float(metrics.get("risk_score", 0.0) or 0.0))
    return round(max(0.0, min(1.0, score)), 4)


def _projected_capability_after(before_capability_score: float, metrics: Dict[str, Any]) -> float:
    projected = float(before_capability_score)
    if metrics.get("targeted_regression", {}).get("ok"):
        projected += 0.015
    if float(metrics.get("evidence_strength_score", 0.0) or 0.0) >= 0.7:
        projected += 0.01
    if int(metrics.get("evidence_ref_count", 0) or 0) >= 3:
        projected += 0.005
    if not metrics.get("implementation_size_ok"):
        projected -= 0.01
    if float(metrics.get("risk_score", 0.0) or 0.0) > 0.6:
        projected -= 0.01
    return round(max(0.0, min(1.0, projected)), 4)


def _update_scorecard(proposal: Dict[str, Any], verdict: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    payload = read_json(CAPABILITY_SCORECARD_PATH, default={}) or {}
    caps = payload.setdefault("capabilities", {})
    target = str(proposal.get("target_capability") or "planning_coherence")
    row = caps.setdefault(target, {
        "current_score": 0.6,
        "previous_score": 0.6,
        "delta": 0.0,
        "confidence": 0.5,
        "evidence": [],
        "status": "hypothesis_only",
    })
    current = float(row.get("current_score", 0.6) or 0.6)
    delta = 0.0
    status = row.get("status") or "hypothesis_only"
    if verdict == "evaluation_passed_candidate":
        delta = 0.02
        status = "candidate_ready"
    elif verdict == "evaluation_failed":
        delta = -0.01
        status = "evaluation_failed"
    elif verdict == "needs_more_tests":
        status = "needs_more_tests"
    elif verdict == "insufficient_evidence":
        status = "insufficient_evidence"
    new_score = round(max(0.0, min(1.0, current + delta)), 2)
    row["previous_score"] = current
    row["current_score"] = new_score
    row["delta"] = round(new_score - current, 2)
    row["status"] = status
    row["last_evaluation"] = {
        "proposal_id": proposal.get("proposal_id"),
        "verdict": verdict,
        "updated_utc": _utc_now(),
        "metrics": {
            "evidence_strength_score": metrics.get("evidence_strength_score"),
            "risk_score": metrics.get("risk_score"),
            "implementation_size_ok": metrics.get("implementation_size_ok"),
        },
    }
    payload["updated_utc"] = _utc_now()
    write_json(CAPABILITY_SCORECARD_PATH, payload)
    return payload


def evaluate_proposal(proposal_id: str, *, actor: str, reason: str, run_id: str | None = None) -> Dict[str, Any]:
    registry = load_registry()
    proposal = _proposal_lookup(registry, proposal_id)
    if proposal is None:
        return {"success": False, "error": "proposal_not_found", "proposal_id": proposal_id}

    if proposal.get("current_state") != "evaluation_pending":
        return {
            "success": False,
            "error": "invalid_state",
            "proposal_id": proposal_id,
            "current_state": proposal.get("current_state"),
        }

    sandbox_run = _latest_sandbox_run(proposal, run_id=run_id)
    if sandbox_run is None:
        return {"success": False, "error": "sandbox_run_not_found", "proposal_id": proposal_id}

    manifest = _safe_read(sandbox_run.get("manifest_path"))
    rollback_manifest = _safe_read(sandbox_run.get("rollback_manifest_path"))
    evaluation_summary = _safe_read(sandbox_run.get("evaluation_summary_path"))

    copied = manifest.get("copied_files", []) or []
    copied_ok = bool(copied) and all(item.get("status") == "copied" for item in copied)
    source_attr_present = bool(proposal.get("source_attribution"))
    evidence_refs_present = _evidence_refs_present(proposal)
    lifecycle_integrity_ok = bool(proposal.get("state_history")) and proposal.get("current_state") == "evaluation_pending"
    implementation_size_ok = len(proposal.get("files_to_modify", []) or []) <= 4
    py_compile_ok = bool((((evaluation_summary.get("validation") or {}).get("py_compile") or {}).get("ok")))
    rollback_manifest_present = bool(rollback_manifest) and bool(rollback_manifest.get("files"))
    sandbox_manifest_present = bool(manifest) and bool(manifest.get("copied_files"))
    evaluation_summary_present = bool(evaluation_summary) and bool(evaluation_summary.get("validation"))
    no_production_write = _no_production_write(evaluation_summary)
    risk_score = float(proposal.get("risk_score", 0.5) or 0.5)
    evidence_strength_score = float(proposal.get("evidence_strength_score", 0.0) or 0.0)
    evidence_ref_count = _evidence_ref_count(proposal)
    targeted_regression = _targeted_regression(str(proposal.get("target_capability") or "planning_coherence"))
    before_capability = (evaluation_summary.get("before_capability_snapshot") or {})
    before_capability_score = float(before_capability.get("current_score", 0.6) or 0.6)
    before_capability_status = str(before_capability.get("status") or "hypothesis_only")

    metrics = {
        "py_compile_ok": py_compile_ok,
        "files_copied_ok": copied_ok,
        "source_attribution_present": source_attr_present,
        "proposal_has_evidence_refs": evidence_refs_present,
        "sandbox_manifest_present": sandbox_manifest_present,
        "evaluation_summary_present": evaluation_summary_present,
        "rollback_manifest_present": rollback_manifest_present,
        "lifecycle_integrity_ok": lifecycle_integrity_ok,
        "implementation_size_ok": implementation_size_ok,
        "no_production_write": no_production_write,
        "risk_score": risk_score,
        "evidence_strength_score": evidence_strength_score,
        "evidence_ref_count": evidence_ref_count,
        "targeted_regression": targeted_regression,
    }
    readiness_before = _readiness_score(metrics, before_capability_score)
    projected_after_seed = _projected_capability_after(before_capability_score, metrics)
    readiness_after = _readiness_score(metrics, projected_after_seed)
    readiness_delta = round(readiness_after - readiness_before, 4)
    metrics["before_after"] = {
        "capability_score_before": before_capability_score,
        "capability_status_before": before_capability_status,
        "capability_score_projected_after": projected_after_seed,
        "readiness_score_before": readiness_before,
        "readiness_score_after": readiness_after,
        "readiness_delta": readiness_delta,
    }

    verdict = "needs_more_tests"
    next_state = None
    if not py_compile_ok or not rollback_manifest_present or not sandbox_manifest_present or not evaluation_summary_present or not no_production_write:
        verdict = "evaluation_failed"
        next_state = "rolled_back"
    elif not source_attr_present or not evidence_refs_present:
        verdict = "insufficient_evidence"
        next_state = "rejected"
    elif risk_score >= 0.8 and evidence_strength_score < 0.6:
        verdict = "needs_more_tests"
    elif not targeted_regression.get("ok"):
        verdict = "needs_more_tests"
    elif evidence_ref_count < 2:
        verdict = "insufficient_evidence"
        next_state = "rejected"
    elif (
        copied_ok
        and lifecycle_integrity_ok
        and implementation_size_ok
        and evidence_strength_score >= 0.7
        and risk_score <= 0.6
        and projected_after_seed > before_capability_score
        and readiness_after >= max(readiness_before, 0.85)
    ):
        verdict = "evaluation_passed_candidate"
        next_state = "candidate_promote"

    report = {
        "proposal_id": proposal_id,
        "run_id": sandbox_run.get("run_id"),
        "evaluated_at_utc": _utc_now(),
        "actor": actor,
        "reason": reason,
        "metrics": metrics,
        "evaluator_verdict": verdict,
        "next_state": next_state,
    }
    if verdict not in VALID_VERDICTS:
        return {"success": False, "error": "invalid_verdict_computed", "proposal_id": proposal_id, "verdict": verdict}

    report_path = Path(str(sandbox_run.get("evaluation_summary_path"))).with_name("evaluation_report.json")
    write_json(report_path, report)

    sandbox_run["evaluation_report_path"] = str(report_path)
    sandbox_run["evaluator_verdict"] = verdict
    sandbox_run["evaluation_completed_at_utc"] = report["evaluated_at_utc"]
    proposal["last_evaluator_verdict"] = verdict
    proposal["last_evaluation_report_path"] = str(report_path)
    proposal.setdefault("evaluation_history", []).append({
        "run_id": sandbox_run.get("run_id"),
        "evaluated_at_utc": report["evaluated_at_utc"],
        "actor": actor,
        "verdict": verdict,
        "report_path": str(report_path),
    })

    scorecard = _update_scorecard(proposal, verdict, metrics)
    save_registry(registry)

    transition_result = None
    if next_state:
        transition_result = transition_proposal_state(proposal_id, next_state, actor=actor, reason=f"evaluator:{verdict}")
        registry = load_registry()
        proposal = _proposal_lookup(registry, proposal_id) or proposal

    _append_event("evaluation_completed", {
        "proposal_id": proposal_id,
        "run_id": sandbox_run.get("run_id"),
        "actor": actor,
        "verdict": verdict,
        "next_state": next_state,
    })
    return {
        "success": True,
        "proposal_id": proposal_id,
        "run_id": sandbox_run.get("run_id"),
        "evaluator_verdict": verdict,
        "next_state": next_state,
        "metrics": metrics,
        "proposal": proposal,
        "scorecard": scorecard,
        "transition": transition_result,
        "evaluation_report_path": str(report_path),
    }
