from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.learning.capability_hypothesis_generator import TARGET_CAPABILITIES, generate_hypotheses
from brain_v9.learning.external_intel_ingestor import (
    EXTERNAL_INTEL_ROOT,
    KNOWLEDGE_EXTERNAL_ROOT,
    LEARNING_EVENTS_PATH,
    _append_event,
    ingest_github_repo,
)
from brain_v9.learning.patch_advisor import PROPOSAL_REGISTRY_PATH, build_patch_proposals
from brain_v9.learning.pattern_extractor import extract_patterns
from brain_v9.learning.proposal_governance import load_registry
from brain_v9.learning.sandbox_executor import SANDBOX_ROOT
from brain_v9.learning.repo_curator import curate_repo
from brain_v9.learning.source_registry import SOURCE_REGISTRY_PATH, active_sources, load_source_registry

STATE_ROOT = BASE_PATH / "tmp_agent" / "state"
CAPABILITY_STATE_ROOT = STATE_ROOT / "capabilities"
CAPABILITY_SCORECARD_PATH = CAPABILITY_STATE_ROOT / "capability_scorecard_latest.json"
LEARNING_STATUS_PATH = STATE_ROOT / "learning_status_latest.json"
LEARNING_REFRESH_STATE_PATH = STATE_ROOT / "learning_refresh_state.json"
LEARNING_CURVE_PATH = CAPABILITY_STATE_ROOT / "external_learning_curve_history.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_slug(owner: str, repo: str) -> str:
    return f"{owner}_{repo}".replace("-", "_")


def _knowledge_dir(owner: str, repo: str) -> Path:
    return KNOWLEDGE_EXTERNAL_ROOT / "github" / _source_slug(owner, repo)


def _build_attribution_map(source_manifest: Dict[str, Any], pattern_report: Dict[str, Any], hypothesis_report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_id": source_manifest.get("source_id"),
        "generated_at_utc": _utc_now(),
        "patterns": [
            {
                "pattern_id": p.get("pattern_id"),
                "semantic_family": p.get("semantic_family"),
                "source_id": source_manifest.get("source_id"),
                "evidence_refs": p.get("evidence_refs", []),
            }
            for p in pattern_report.get("patterns", [])
        ],
        "hypotheses": [
            {
                "hypothesis_id": h.get("hypothesis_id"),
                "semantic_key": h.get("semantic_key"),
                "source_id": source_manifest.get("source_id"),
                "pattern_id": (h.get("source_attribution") or {}).get("pattern_id"),
                "evidence_refs": (h.get("source_attribution") or {}).get("evidence_refs", []),
            }
            for h in hypothesis_report.get("hypotheses", [])
        ],
    }


def _build_initial_scorecard(hypothesis_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    existing_payload = read_json(CAPABILITY_SCORECARD_PATH, default={}) or {}
    existing_caps = existing_payload.get("capabilities", {})
    evidence_by_capability: Dict[str, List[str]] = {name: [] for name in TARGET_CAPABILITIES}
    for report in hypothesis_reports:
        for hyp in report.get("hypotheses", []):
            cap = hyp.get("target_capability")
            if cap in evidence_by_capability:
                evidence_by_capability[cap].append(hyp.get("hypothesis_id"))

    capabilities = {}
    for cap in TARGET_CAPABILITIES:
        evidence = evidence_by_capability.get(cap, [])
        seed_score = round(min(0.55 + (0.07 * len(evidence)), 0.79), 2)
        existing = existing_caps.get(cap, {})
        current_score = max(seed_score, float(existing.get("current_score", seed_score) or seed_score))
        confidence = max(round(min(0.45 + (0.1 * len(evidence)), 0.8), 2), float(existing.get("confidence", 0.0) or 0.0))
        capabilities[cap] = {
            "current_score": round(current_score, 2),
            "previous_score": float(existing.get("previous_score", current_score) or current_score),
            "delta": float(existing.get("delta", 0.0) or 0.0),
            "confidence": round(confidence, 2),
            "evidence": sorted(set((existing.get("evidence") or []) + evidence)),
            "status": str(existing.get("status") or "hypothesis_only"),
            "last_evaluation": existing.get("last_evaluation"),
        }
    return {
        "updated_utc": _utc_now(),
        "capabilities": capabilities,
    }


def _read_learning_events(limit: int = 20) -> List[Dict[str, Any]]:
    if not LEARNING_EVENTS_PATH.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(LEARNING_EVENTS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    rows.sort(key=lambda row: row.get("ts_utc", ""), reverse=True)
    return rows[:limit]


def _ingestion_summary(registry: Dict[str, Any], sources: List[Dict[str, Any]], failures: List[Dict[str, Any]], *, refresh: bool, max_sources: int | None) -> Dict[str, Any]:
    catalog = registry.get("sources", [])
    active = [row for row in catalog if row.get("enabled")]
    categories: Dict[str, int] = {}
    for row in active:
        category = str(row.get("category") or "general")
        categories[category] = categories.get(category, 0) + 1
    return {
        "registry_path": str(SOURCE_REGISTRY_PATH),
        "catalog_size": len(catalog),
        "active_sources": len(active),
        "ingested_sources": len(sources),
        "failed_sources": len(failures),
        "categories": categories,
        "mode": "full_catalog" if max_sources is None else f"bounded:{max_sources}",
        "refresh_requested": refresh,
        "last_run_utc": _utc_now(),
    }


def _load_cached_source_artifacts(owner: str, repo: str) -> Dict[str, Any] | None:
    source_dir = _knowledge_dir(owner, repo)
    paths = {
        "manifest": source_dir / "source_manifest.json",
        "curation": source_dir / "curation_report.json",
        "patterns": source_dir / "pattern_report.json",
        "hypotheses": source_dir / "capability_hypotheses.json",
    }
    if not all(path.exists() for path in paths.values()):
        return None
    return {
        "manifest": read_json(paths["manifest"], default={}) or {},
        "curation": read_json(paths["curation"], default={}) or {},
        "patterns": read_json(paths["patterns"], default={}) or {},
        "hypotheses": read_json(paths["hypotheses"], default={}) or {},
        "source_dir": source_dir,
    }


def _semantic_dedup_summary(hypothesis_rows: List[Dict[str, Any]], proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clusters: Dict[str, Dict[str, Any]] = {}
    for row in hypothesis_rows:
        key = str(row.get("semantic_key") or row.get("hypothesis_id"))
        cluster = clusters.setdefault(key, {
            "semantic_key": key,
            "target_capability": row.get("target_capability"),
            "hypothesis_ids": [],
            "linked_sources": set(),
            "evidence_refs": [],
        })
        cluster["hypothesis_ids"].append(row.get("hypothesis_id"))
        for src in row.get("linked_sources", []):
            if src:
                cluster["linked_sources"].add(src)
        attribution = row.get("source_attribution") or {}
        for ref in attribution.get("evidence_refs", []):
            if ref not in cluster["evidence_refs"]:
                cluster["evidence_refs"].append(ref)
    proposal_map = {p.get("semantic_key"): p.get("proposal_id") for p in proposals}
    rows = []
    for key, cluster in clusters.items():
        rows.append({
            "semantic_key": key,
            "target_capability": cluster["target_capability"],
            "hypothesis_count": len(cluster["hypothesis_ids"]),
            "proposal_id": proposal_map.get(key),
            "linked_sources": sorted(cluster["linked_sources"]),
            "evidence_refs": cluster["evidence_refs"],
        })
    return rows


def _overlay_proposal_outcomes(scorecard: Dict[str, Any], proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    caps = scorecard.setdefault("capabilities", {})
    for proposal in proposals:
        cap = str(proposal.get("target_capability") or "")
        if cap not in caps:
            continue
        row = caps[cap]
        state = str(proposal.get("current_state") or "")
        verdict = str(proposal.get("last_evaluator_verdict") or "")
        if state == "candidate_promote" or verdict == "evaluation_passed_candidate":
            row["status"] = "candidate_ready"
            row["current_score"] = round(max(float(row.get("current_score", 0.0) or 0.0), 0.81), 2)
        elif verdict == "needs_more_tests" and row.get("status") == "hypothesis_only":
            row["status"] = "needs_more_tests"
        if verdict:
            row["last_evaluation"] = {
                "proposal_id": proposal.get("proposal_id"),
                "verdict": verdict,
                "updated_utc": _utc_now(),
            }
    return scorecard


def _sandbox_summary(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    runs = []
    by_state: Dict[str, int] = {}
    for proposal in proposals:
        for run in proposal.get("sandbox_runs", []) or []:
            runs.append(run)
            state = str(run.get("status") or "unknown")
            by_state[state] = by_state.get(state, 0) + 1
    latest = sorted(runs, key=lambda item: item.get("completed_at_utc", ""), reverse=True)[:5]
    return {
        "sandbox_root": str(SANDBOX_ROOT),
        "total_runs": len(runs),
        "by_status": by_state,
        "latest_runs": latest,
    }


def _evaluation_summary(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = []
    by_verdict: Dict[str, int] = {}
    for proposal in proposals:
        history = list(proposal.get("evaluation_history", []) or [])
        if not history:
            for run in proposal.get("sandbox_runs", []) or []:
                verdict = run.get("evaluator_verdict")
                if not verdict:
                    continue
                history.append({
                    "run_id": run.get("run_id"),
                    "evaluated_at_utc": run.get("evaluation_completed_at_utc"),
                    "verdict": verdict,
                    "report_path": run.get("evaluation_report_path"),
                })
        for entry in history:
            items.append({
                "proposal_id": proposal.get("proposal_id"),
                "target_capability": proposal.get("target_capability"),
                "current_state": proposal.get("current_state"),
                "verdict": entry.get("verdict"),
                "run_id": entry.get("run_id"),
                "evaluated_at_utc": entry.get("evaluated_at_utc"),
                "report_path": entry.get("report_path"),
            })
            verdict = str(entry.get("verdict") or "unknown")
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
    items.sort(key=lambda row: row.get("evaluated_at_utc", ""), reverse=True)
    return {
        "total_evaluations": len(items),
        "by_verdict": by_verdict,
        "latest": items[:5],
    }


def _learning_activation(scorecard: Dict[str, Any], evaluation_summary: Dict[str, Any]) -> Dict[str, Any]:
    caps = scorecard.get("capabilities", {})
    evidence_backed_caps = [
        cap for cap, row in caps.items()
        if row.get("last_evaluation") or str(row.get("status") or "") in {"candidate_ready", "needs_more_tests", "evaluation_failed", "insufficient_evidence"}
    ]
    total_evals = int(evaluation_summary.get("total_evaluations", 0) or 0)
    candidate_count = int((evaluation_summary.get("by_verdict") or {}).get("evaluation_passed_candidate", 0) or 0)
    active = total_evals > 0 and bool(evidence_backed_caps)
    stage = "research_only"
    if active:
        stage = "externally_informed_learning_active"
    elif total_evals > 0:
        stage = "sandbox_evaluation_active"
    return {
        "externally_informed_learning_active": active,
        "activation_stage": stage,
        "trigger_condition": "At least one external-derived proposal has been evaluated and changed capability evidence/state.",
        "evidence_backed_capabilities": evidence_backed_caps,
        "total_evaluations": total_evals,
        "candidate_verdicts": candidate_count,
    }


def _load_learning_curve() -> Dict[str, Any]:
    payload = read_json(LEARNING_CURVE_PATH, default={}) or {"updated_utc": _utc_now(), "points": []}
    payload.setdefault("points", [])
    payload["capability_curves"] = _capability_curves(payload["points"])
    return payload


def _capability_curves(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    curves: Dict[str, List[Dict[str, Any]]] = {}
    for point in points:
        for cap, score in (point.get("capability_scores") or {}).items():
            curves.setdefault(cap, []).append({
                "ts_utc": point.get("ts_utc"),
                "score": score,
                "status": (point.get("capability_status") or {}).get(cap),
                "activation_stage": point.get("activation_stage"),
            })
    return curves


def _update_learning_curve(status: Dict[str, Any], scorecard: Dict[str, Any], evaluation_summary: Dict[str, Any]) -> Dict[str, Any]:
    payload = _load_learning_curve()
    points = list(payload.get("points", []))
    activation = status.get("activation", {})
    point = {
        "ts_utc": _utc_now(),
        "milestone": status.get("milestone"),
        "sources": len(status.get("panels", {}).get("sources", [])),
        "patterns": len(status.get("panels", {}).get("patterns", [])),
        "hypotheses": len(status.get("panels", {}).get("hypotheses", [])),
        "proposals": len(status.get("panels", {}).get("proposals", [])),
        "evaluations": int(evaluation_summary.get("total_evaluations", 0) or 0),
        "candidate_verdicts": int((evaluation_summary.get("by_verdict") or {}).get("evaluation_passed_candidate", 0) or 0),
        "needs_more_tests": int((evaluation_summary.get("by_verdict") or {}).get("needs_more_tests", 0) or 0),
        "active": bool(activation.get("externally_informed_learning_active")),
        "activation_stage": activation.get("activation_stage"),
        "capability_status": {cap: row.get("status") for cap, row in (scorecard.get("capabilities", {}) or {}).items()},
        "capability_scores": {cap: row.get("current_score") for cap, row in (scorecard.get("capabilities", {}) or {}).items()},
    }
    if not points or any(point.get(k) != points[-1].get(k) for k in ("sources", "patterns", "hypotheses", "proposals", "evaluations", "candidate_verdicts", "needs_more_tests", "activation_stage")):
        points.append(point)
    payload["updated_utc"] = _utc_now()
    payload["points"] = points[-120:]
    payload["capability_curves"] = _capability_curves(payload["points"])
    write_json(LEARNING_CURVE_PATH, payload)
    return payload


def build_learning_status(*, refresh: bool = False, max_sources: int | None = None) -> Dict[str, Any]:
    EXTERNAL_INTEL_ROOT.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_EXTERNAL_ROOT.mkdir(parents=True, exist_ok=True)
    CAPABILITY_STATE_ROOT.mkdir(parents=True, exist_ok=True)

    source_registry = load_source_registry()
    selected_sources = active_sources(max_sources=max_sources)
    refresh_state = {
        "started_at_utc": _utc_now(),
        "refresh_requested": refresh,
        "max_sources": max_sources,
        "status": "running",
        "catalog_size": len(source_registry.get("sources", [])),
        "selected_sources": len(selected_sources),
    }
    write_json(LEARNING_REFRESH_STATE_PATH, refresh_state)
    _append_event("learning_refresh_started", {
        "refresh": refresh,
        "max_sources": max_sources,
        "selected_sources": len(selected_sources),
    })

    sources: List[Dict[str, Any]] = []
    pattern_rows: List[Dict[str, Any]] = []
    hypothesis_rows: List[Dict[str, Any]] = []
    proposals: List[Dict[str, Any]] = []
    per_source_hypothesis_reports: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for source_spec in selected_sources:
        owner = str(source_spec.get("owner") or "")
        repo = str(source_spec.get("repo") or "")
        try:
            manifest = ingest_github_repo(owner, repo, force_refresh=refresh)
            local_dir = Path(manifest["local_path"])
            repo_metadata_path = local_dir / "repo_metadata.json"
            readme_path = local_dir / "README.snapshot.md"

            source_dir = _knowledge_dir(owner, repo)
            source_dir.mkdir(parents=True, exist_ok=True)

            source_manifest_path = source_dir / "source_manifest.json"
            curation_report_path = source_dir / "curation_report.json"
            pattern_report_path = source_dir / "pattern_report.json"
            hypothesis_report_path = source_dir / "capability_hypotheses.json"
            attribution_map_path = source_dir / "attribution_map.json"
            risk_report_path = source_dir / "risk_report.json"

            write_json(source_manifest_path, manifest)
            curation = curate_repo(manifest, repo_metadata_path, curation_report_path)
            _append_event("source_curated", {"source_id": manifest["source_id"], "recommended_action": curation["recommended_action"]})

            patterns = extract_patterns(manifest, curation, repo_metadata_path, readme_path, pattern_report_path)
            _append_event("pattern_extracted", {"source_id": manifest["source_id"], "pattern_count": len(patterns.get("patterns", []))})

            hypotheses = generate_hypotheses(manifest, patterns, hypothesis_report_path)
            _append_event("hypothesis_created", {"source_id": manifest["source_id"], "hypothesis_count": len(hypotheses.get("hypotheses", []))})

            attribution = _build_attribution_map(manifest, patterns, hypotheses)
            write_json(attribution_map_path, attribution)
            write_json(risk_report_path, {
                "source_id": manifest["source_id"],
                "generated_at_utc": _utc_now(),
                "source_risk_score": curation.get("risk_score"),
                "pattern_risks": [
                    {"pattern_id": p.get("pattern_id"), "risk": p.get("risk")}
                    for p in patterns.get("patterns", [])
                ],
            })

            sources.append({
                "source_id": manifest["source_id"],
                "type": manifest["source_type"],
                "url": manifest["url"],
                "status": manifest["status"],
                "owner": owner,
                "repo": repo,
                "category": source_spec.get("category"),
                "priority": source_spec.get("priority"),
                "rationale": source_spec.get("rationale"),
                "curation_score": curation["curation_score"],
                "risk_score": curation["risk_score"],
                "recommended_action": curation["recommended_action"],
                "knowledge_path": str(source_dir),
                "repo_signals": {
                    "tests_present": curation.get("repo", {}).get("tests_present"),
                    "docs_present": curation.get("repo", {}).get("docs_present"),
                    "dependency_files": curation.get("repo", {}).get("dependency_files", []),
                    "tree_entries": curation.get("repo", {}).get("tree_entries"),
                    "priority_files_scanned": curation.get("repo", {}).get("priority_files_scanned"),
                },
            })

            for p in patterns.get("patterns", []):
                target_for_pattern = next(
                    (
                        h.get("target_capability")
                        for h in hypotheses.get("hypotheses", [])
                        if (h.get("source_attribution") or {}).get("pattern_id") == p.get("pattern_id")
                    ),
                    "planning_coherence",
                )
                pattern_rows.append({
                    "pattern_id": p.get("pattern_id"),
                    "semantic_family": p.get("semantic_family"),
                    "source_id": manifest["source_id"],
                    "capability_target": target_for_pattern,
                    "relevance_score": p.get("relevance_to_brain"),
                    "risk_score": p.get("risk"),
                    "evidence_refs": p.get("evidence_refs", []),
                    "status": "extracted",
                })
            for h in hypotheses.get("hypotheses", []):
                hypothesis_rows.append({
                    "hypothesis_id": h.get("hypothesis_id"),
                    "semantic_key": h.get("semantic_key"),
                    "target_capability": h.get("target_capability"),
                    "expected_lift": h.get("expected_metric_lift"),
                    "status": "created",
                    "linked_sources": h.get("inspired_by_sources", []),
                    "source_attribution": h.get("source_attribution"),
                })
            per_source_hypothesis_reports.append(hypotheses)
        except Exception as exc:
            cached = _load_cached_source_artifacts(owner, repo)
            if cached:
                manifest = cached["manifest"]
                curation = cached["curation"]
                patterns = cached["patterns"]
                hypotheses = cached["hypotheses"]
                source_dir = cached["source_dir"]
                sources.append({
                    "source_id": manifest.get("source_id"),
                    "type": manifest.get("source_type"),
                    "url": manifest.get("url"),
                    "status": "cached_fallback",
                    "owner": owner,
                    "repo": repo,
                    "category": source_spec.get("category"),
                    "priority": source_spec.get("priority"),
                    "rationale": source_spec.get("rationale"),
                    "curation_score": curation.get("curation_score"),
                    "risk_score": curation.get("risk_score"),
                    "recommended_action": curation.get("recommended_action"),
                    "knowledge_path": str(source_dir),
                    "repo_signals": {
                        "tests_present": curation.get("repo", {}).get("tests_present"),
                        "docs_present": curation.get("repo", {}).get("docs_present"),
                        "dependency_files": curation.get("repo", {}).get("dependency_files", []),
                        "tree_entries": curation.get("repo", {}).get("tree_entries"),
                        "priority_files_scanned": curation.get("repo", {}).get("priority_files_scanned"),
                    },
                })
                for p in patterns.get("patterns", []):
                    target_for_pattern = next(
                        (
                            h.get("target_capability")
                            for h in hypotheses.get("hypotheses", [])
                            if (h.get("source_attribution") or {}).get("pattern_id") == p.get("pattern_id")
                        ),
                        "planning_coherence",
                    )
                    pattern_rows.append({
                        "pattern_id": p.get("pattern_id"),
                        "semantic_family": p.get("semantic_family"),
                        "source_id": manifest.get("source_id"),
                        "capability_target": target_for_pattern,
                        "relevance_score": p.get("relevance_to_brain"),
                        "risk_score": p.get("risk"),
                        "evidence_refs": p.get("evidence_refs", []),
                        "status": "cached",
                    })
                for h in hypotheses.get("hypotheses", []):
                    hypothesis_rows.append({
                        "hypothesis_id": h.get("hypothesis_id"),
                        "semantic_key": h.get("semantic_key"),
                        "target_capability": h.get("target_capability"),
                        "expected_lift": h.get("expected_metric_lift"),
                        "status": "cached",
                        "linked_sources": h.get("inspired_by_sources", []),
                        "source_attribution": h.get("source_attribution"),
                    })
                per_source_hypothesis_reports.append(hypotheses)
                _append_event("source_ingest_cached_fallback", {
                    "owner": owner,
                    "repo": repo,
                    "error": str(exc),
                    "source_id": manifest.get("source_id"),
                })
                continue
            failure = {
                "owner": owner,
                "repo": repo,
                "category": source_spec.get("category"),
                "error": str(exc),
                "failed_at_utc": _utc_now(),
            }
            failures.append(failure)
            _append_event("source_ingest_failed", failure)

    scorecard = _build_initial_scorecard(per_source_hypothesis_reports)
    proposal_registry = build_patch_proposals(hypothesis_rows)
    proposals = proposal_registry.get("proposals", [])
    scorecard = _overlay_proposal_outcomes(scorecard, proposals)
    write_json(CAPABILITY_SCORECARD_PATH, scorecard)
    created_proposal_ids = set((read_json(PROPOSAL_REGISTRY_PATH, default={}) or {}).get("created_proposal_ids", []))
    for proposal in proposals:
        if proposal.get("proposal_id") not in created_proposal_ids:
            continue
        _append_event("proposal_created", {
            "proposal_id": proposal.get("proposal_id"),
            "hypothesis_id": proposal.get("hypothesis_id"),
            "target_capability": proposal.get("target_capability"),
        })
    semantic_clusters = _semantic_dedup_summary(hypothesis_rows, proposals)
    refresh_state.update({
        "completed_at_utc": _utc_now(),
        "status": "ok",
        "ingested_sources": len(sources),
        "failed_sources": len(failures),
        "patterns": len(pattern_rows),
        "hypotheses": len(hypothesis_rows),
        "proposals": len(proposals),
    })
    write_json(LEARNING_REFRESH_STATE_PATH, refresh_state)
    _append_event("learning_refresh_completed", {
        "refresh": refresh,
        "max_sources": max_sources,
        "ingested_sources": len(sources),
        "failed_sources": len(failures),
        "patterns": len(pattern_rows),
        "hypotheses": len(hypothesis_rows),
        "proposals": len(proposals),
    })

    evaluation_summary = _evaluation_summary(proposals)
    status = {
        "updated_utc": _utc_now(),
        "milestone": "learning_phase_1_5",
        "status": "ok",
        "rules": {
            "external_source_cannot_modify_production_directly": True,
            "patching_active": False,
            "sandbox_execution_active": True,
            "promotion_active": False,
            "proposal_generation_active": True,
        },
        "paths": {
            "external_intel_root": str(EXTERNAL_INTEL_ROOT),
            "knowledge_external_root": str(KNOWLEDGE_EXTERNAL_ROOT),
            "learning_events_path": str(LEARNING_EVENTS_PATH),
            "capability_scorecard_path": str(CAPABILITY_SCORECARD_PATH),
            "proposal_registry_path": str(PROPOSAL_REGISTRY_PATH),
            "source_registry_path": str(SOURCE_REGISTRY_PATH),
            "learning_refresh_state_path": str(LEARNING_REFRESH_STATE_PATH),
            "learning_curve_path": str(LEARNING_CURVE_PATH),
        },
        "panels": {
            "ingestion": _ingestion_summary(source_registry, sources, failures, refresh=refresh, max_sources=max_sources),
            "source_registry": source_registry,
            "sources": sources,
            "source_failures": failures,
            "patterns": pattern_rows,
            "hypotheses": hypothesis_rows,
            "semantic_dedup": semantic_clusters,
            "proposals": proposals,
            "sandbox": _sandbox_summary(proposals),
            "evaluation": evaluation_summary,
            "capability_evolution": scorecard.get("capabilities", {}),
            "promotion_history": [],
            "recent_events": _read_learning_events(25),
        },
    }
    status["activation"] = _learning_activation(scorecard, evaluation_summary)
    status["panels"]["learning_curve"] = _update_learning_curve(status, scorecard, evaluation_summary)
    write_json(LEARNING_STATUS_PATH, status)
    return status


def run_learning_refresh(*, actor: str, reason: str, force_refresh: bool = True, max_sources: int | None = None) -> Dict[str, Any]:
    _append_event("learning_refresh_requested", {
        "actor": actor,
        "reason": reason,
        "force_refresh": force_refresh,
        "max_sources": max_sources,
    })
    status = build_learning_status(refresh=force_refresh, max_sources=max_sources)
    payload = dict(status)
    payload["refresh_request"] = {
        "actor": actor,
        "reason": reason,
        "force_refresh": force_refresh,
        "max_sources": max_sources,
        "completed_at_utc": _utc_now(),
    }
    write_json(LEARNING_STATUS_PATH, payload)
    return payload


def read_learning_status() -> Dict[str, Any]:
    if not LEARNING_STATUS_PATH.exists():
        return build_learning_status(refresh=False)
    payload = read_json(LEARNING_STATUS_PATH, default={}) or {}
    if not payload:
        return build_learning_status(refresh=False)
    proposals = load_registry().get("proposals", [])
    payload.setdefault("panels", {})
    payload["panels"]["proposals"] = proposals
    payload["panels"]["sandbox"] = _sandbox_summary(proposals)
    payload["panels"]["evaluation"] = _evaluation_summary(proposals)
    payload["panels"]["recent_events"] = _read_learning_events(25)
    payload["panels"]["source_registry"] = load_source_registry()
    scorecard = read_json(CAPABILITY_SCORECARD_PATH, default={}) or {"capabilities": {}}
    payload["panels"]["capability_evolution"] = scorecard.get("capabilities", {})
    payload["activation"] = _learning_activation(scorecard, payload["panels"]["evaluation"])
    payload["panels"]["learning_curve"] = _load_learning_curve()
    payload["milestone"] = "learning_phase_1_5"
    payload.setdefault("rules", {})
    payload["rules"]["sandbox_execution_active"] = True
    write_json(LEARNING_STATUS_PATH, payload)
    return payload
