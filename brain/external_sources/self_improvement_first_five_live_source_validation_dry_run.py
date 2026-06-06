"""Live-source validation dry-run for first-five self-improvement candidates.

This module validates only metadata for candidates that passed the utility
evaluation gate. It never stores raw response bodies, writes memory, writes
FAISS, promotes knowledge, or integrates with runtime/chat.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from brain.external_sources.self_improvement_first_five_utility_evaluation_dry_run import (
    run_first_five_utility_evaluation_dry_run,
)


TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "GITHUB_TOKEN",
)

KNOWN_TARGETS = {
    "EVALUATION_BENCHMARKS_QUALITY_GATES": {
        "official_docs": ["https://www.swebench.com/"],
        "github": ["SWE-bench/SWE-bench"],
        "paper_index": ["https://arxiv.org/abs/2310.06770"],
        "terms": ["SWE-bench", "software engineering benchmark", "real-world GitHub issues"],
    },
    "AUTO_CODING_AGENTS_PATCH_GENERATION": {
        "official_docs": ["https://swe-agent.com/"],
        "github": ["SWE-agent/SWE-agent"],
        "paper_index": ["https://arxiv.org/abs/2405.15793"],
        "terms": ["SWE-agent", "agent-computer interfaces", "automated software engineering"],
    },
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def _safe_hash(payload: Dict[str, Any]) -> str:
    safe_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(safe_payload.encode("utf-8")).hexdigest()


def _redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _contains_token_marker(text: str) -> bool:
    return any(marker in text for marker in TOKEN_MARKERS)


def load_utility_evaluation_artifacts(output_dir: str) -> Dict[str, Any]:
    out = Path(output_dir)
    return {
        "evaluations": _read_json(out / "first_five_utility_evaluations.json", []),
        "actionability_matrix": _read_json(out / "first_five_actionability_matrix.json", []),
        "summary": _read_json(out / "first_five_utility_summary.json", {}),
        "output_dir": str(out),
    }


def select_candidates_for_live_validation(evaluations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected = [
        item
        for item in evaluations
        if item.get("decision") == "ready_for_live_source_validation"
        and item.get("requires_live_source_validation") is True
        and float(item.get("utility_score", 0.0)) >= 0.80
    ]
    if selected:
        return selected
    return [
        item
        for item in evaluations
        if item.get("decision") == "useful_but_needs_live_evidence"
        and float(item.get("utility_score", 0.0)) >= 0.70
    ]


def build_live_validation_query(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    front_id = evaluation.get("front_id", "")
    known = KNOWN_TARGETS.get(front_id, {})
    title_terms = [part for part in str(evaluation.get("title", "")).replace(":", " ").split() if len(part) > 3]
    search_terms = list(dict.fromkeys((known.get("terms") or []) + title_terms[:5]))
    return {
        "validation_query_id": _stable_id("live_query", evaluation.get("candidate_id", ""), front_id),
        "candidate_id": evaluation.get("candidate_id", ""),
        "front_id": front_id,
        "title": evaluation.get("title", ""),
        "provider_targets": ["github", "official_docs", "paper_index"],
        "search_terms": search_terms,
        "expected_evidence_types": [
            "official_doc",
            "github_repo",
            "paper",
            "benchmark",
            "security_guideline",
        ],
        "known_targets": {
            "github": known.get("github", []),
            "official_docs": known.get("official_docs", []),
            "paper_index": known.get("paper_index", []),
        },
        "network_allowed": True,
        "raw_body_storage_allowed": False,
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "promotion_allowed": False,
    }


def _head_url_metadata(url: str, timeout: float = 5.0) -> Tuple[Dict[str, Any] | None, str | None]:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "AI-Vault-live-source-validation-dry-run"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            metadata = {
                "provider": "official_docs",
                "source_id": _redact_url(url),
                "source_type": "official_doc",
                "url_redacted": _redact_url(url),
                "http_status": int(getattr(response, "status", 0) or response.getcode()),
                "content_hash": _safe_hash(
                    {
                        "url": _redact_url(url),
                        "status": int(getattr(response, "status", 0) or response.getcode()),
                        "content_type": response.headers.get("Content-Type", ""),
                    }
                ),
                "retrieved_at": now_utc(),
            }
            return metadata, None
    except urllib.error.HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308, 403, 405}:
            metadata = {
                "provider": "official_docs",
                "source_id": _redact_url(url),
                "source_type": "official_doc",
                "url_redacted": _redact_url(url),
                "http_status": int(exc.code),
                "content_hash": _safe_hash({"url": _redact_url(url), "status": int(exc.code)}),
                "retrieved_at": now_utc(),
            }
            return metadata, None
        return None, "failed_safely"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "deferred_no_network"


def _paper_index_metadata(url: str, timeout: float = 5.0) -> Tuple[Dict[str, Any] | None, str | None]:
    metadata, status = _head_url_metadata(url, timeout=timeout)
    if metadata:
        metadata["provider"] = "paper_index"
        metadata["source_type"] = "paper"
    return metadata, status


def _github_repo_metadata(repo: str, timeout: float = 5.0) -> Tuple[Dict[str, Any] | None, str | None]:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None, "deferred_missing_credentials"
    url = f"https://api.github.com/repos/{repo}"
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "AI-Vault-live-source-validation-dry-run",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            limited = response.read(4096)
            body = json.loads(limited.decode("utf-8"))
            safe_subset = {
                "full_name": body.get("full_name", repo),
                "html_url": body.get("html_url", f"https://github.com/{repo}"),
                "default_branch": body.get("default_branch", ""),
                "archived": body.get("archived", False),
                "fork": body.get("fork", False),
            }
            metadata = {
                "provider": "github",
                "source_id": repo,
                "source_type": "github_repo",
                "url_redacted": _redact_url(str(safe_subset["html_url"])),
                "http_status": int(getattr(response, "status", 0) or response.getcode()),
                "content_hash": _safe_hash(safe_subset),
                "retrieved_at": now_utc(),
            }
            return metadata, None
    except urllib.error.HTTPError as exc:
        return None, "not_found" if exc.code == 404 else "failed_safely"
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "deferred_no_network"


def _check_provider(query: Dict[str, Any], provider: str) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    evidence: List[Dict[str, Any]] = []
    deferred: List[str] = []
    failures: List[str] = []
    targets = query.get("known_targets", {}).get(provider, [])
    if provider == "github":
        for repo in targets:
            item, status = _github_repo_metadata(repo)
            if item:
                evidence.append(item)
            elif status:
                deferred.append(provider) if status.startswith("deferred") else failures.append(status)
    elif provider == "official_docs":
        for url in targets:
            item, status = _head_url_metadata(url)
            if item:
                evidence.append(item)
            elif status:
                deferred.append(provider) if status.startswith("deferred") else failures.append(status)
    elif provider == "paper_index":
        for url in targets:
            item, status = _paper_index_metadata(url)
            if item:
                evidence.append(item)
            elif status:
                deferred.append(provider) if status.startswith("deferred") else failures.append(status)
    return evidence, list(dict.fromkeys(deferred)), failures


def validate_candidate_source_live_dry_run(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    query = build_live_validation_query(evaluation)
    providers_checked: List[str] = []
    providers_deferred: List[str] = []
    failures: List[str] = []
    evidence_refs: List[Dict[str, Any]] = []

    for provider in query["provider_targets"]:
        providers_checked.append(provider)
        evidence, deferred, provider_failures = _check_provider(query, provider)
        evidence_refs.extend(evidence)
        providers_deferred.extend(deferred)
        failures.extend(provider_failures)

    providers_deferred = list(dict.fromkeys(providers_deferred))
    evidence_count = len(evidence_refs)
    if evidence_count >= 2:
        validation_status = "validated_live_source"
    elif evidence_count == 1:
        validation_status = "partially_validated"
    elif providers_deferred == ["github"] and not failures:
        validation_status = "deferred_missing_credentials"
    elif providers_deferred:
        validation_status = "deferred_no_network"
    elif "not_found" in failures:
        validation_status = "not_found"
    else:
        validation_status = "failed_safely"

    base_confidence = float(evaluation.get("utility_score", 0.0))
    confidence = min(1.0, base_confidence + evidence_count * 0.04)
    if evidence_count == 0:
        confidence = max(0.0, base_confidence - 0.10)

    return {
        "live_validation_id": _stable_id("live_validation", evaluation.get("candidate_id", ""), validation_status),
        "candidate_id": evaluation.get("candidate_id", ""),
        "front_id": evaluation.get("front_id", ""),
        "title": evaluation.get("title", ""),
        "validation_status": validation_status,
        "live_evidence_found": evidence_count > 0,
        "evidence_count": evidence_count,
        "providers_checked": providers_checked,
        "providers_deferred": providers_deferred,
        "evidence_refs": evidence_refs,
        "confidence_after_live_validation": round(confidence, 4),
        "recommended_next_step": "benchmark_design_dry_run" if evidence_count else "retry_live_source_validation_dry_run",
        "memory_write_allowed": False,
        "faiss_write_allowed": False,
        "real_write_allowed": False,
        "promotion_allowed": False,
        "raw_body_saved": False,
        "validated_at": now_utc(),
    }


def validate_all_live_sources_dry_run(evaluations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [validate_candidate_source_live_dry_run(item) for item in select_candidates_for_live_validation(evaluations)]


def summarize_live_source_validation(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    statuses: Dict[str, int] = {}
    providers_deferred: Dict[str, int] = {}
    for result in results:
        status = result.get("validation_status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        for provider in result.get("providers_deferred", []):
            providers_deferred[provider] = providers_deferred.get(provider, 0) + 1
    return {
        "safe_completion": True,
        "candidates_selected": len(results),
        "validation_results": len(results),
        "validated_live_source": statuses.get("validated_live_source", 0),
        "partially_validated": statuses.get("partially_validated", 0),
        "deferred_missing_credentials": statuses.get("deferred_missing_credentials", 0),
        "deferred_no_network": statuses.get("deferred_no_network", 0),
        "not_found": statuses.get("not_found", 0),
        "failed_safely": statuses.get("failed_safely", 0),
        "providers_deferred": providers_deferred,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "raw_body_saved": False,
        "timestamp": now_utc(),
    }


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _render_report(queries: List[Dict[str, Any]], results: List[Dict[str, Any]], summary: Dict[str, Any]) -> str:
    lines = [
        "# Validacion contra fuentes vivas - Dry Run",
        "",
        "## 1. Candidatos intentados",
        f"- Total seleccionados: {summary['candidates_selected']}",
    ]
    for query in queries:
        lines.append(f"- {query['front_id']}: {query['title']}")
    lines.extend(["", "## 2. Fuentes y proveedores revisados"])
    for query in queries:
        lines.append(f"- {query['candidate_id']}: {', '.join(query['provider_targets'])}")
    lines.extend(["", "## 3. Resultados validados"])
    for result in results:
        lines.append(
            f"- {result['front_id']}: {result['validation_status']} "
            f"evidence_count={result['evidence_count']} confidence={result['confidence_after_live_validation']}"
        )
    lines.extend(["", "## 4. Deferred y motivos"])
    if summary["providers_deferred"]:
        for provider, count in summary["providers_deferred"].items():
            lines.append(f"- {provider}: {count}")
    else:
        lines.append("- Ningun provider deferred.")
    lines.extend(["", "## 5. Evidencia metadata obtenida"])
    for result in results:
        for ref in result.get("evidence_refs", []):
            lines.append(
                f"- {result['candidate_id']} {ref['provider']} {ref['source_type']} "
                f"status={ref['http_status']} url={ref['url_redacted']}"
            )
    lines.extend(
        [
            "",
            "## 6. Confianza despues de live validation",
            f"- validated_live_source: {summary['validated_live_source']}",
            f"- partially_validated: {summary['partially_validated']}",
            f"- deferred_missing_credentials: {summary['deferred_missing_credentials']}",
            f"- deferred_no_network: {summary['deferred_no_network']}",
            f"- failed_safely: {summary['failed_safely']}",
            "",
            "## 7. Que NO se escribio todavia",
            "- No memory/semantic.",
            "- No FAISS.",
            "- No real write.",
            "- No promotion.",
            "- No runtime/chat integration.",
            "- No raw API bodies completos.",
            "",
            "## 8. Siguiente paso recomendado",
            "SELF-IMPROVEMENT-FIRST-FIVE-BENCHMARK-DESIGN-DRY-RUN-01",
        ]
    )
    return "\n".join(lines) + "\n"


def _output_has_token_marker(output_dir: Path) -> bool:
    for path in output_dir.glob("live_validation*"):
        if path.is_file() and _contains_token_marker(path.read_text(encoding="utf-8", errors="ignore")):
            return True
    return False


def run_first_five_live_source_validation_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    out = Path(output_dir or "tmp_agent/self_improvement_first_five_live_source_validation_dry_run_output")
    out.mkdir(parents=True, exist_ok=True)
    utility_dir = out / "run_utility_evaluation"
    utility_result = run_first_five_utility_evaluation_dry_run(str(utility_dir))
    artifacts = load_utility_evaluation_artifacts(str(utility_dir))
    evaluations = artifacts.get("evaluations", [])
    selected = select_candidates_for_live_validation(evaluations)
    queries = [build_live_validation_query(item) for item in selected]
    results = [validate_candidate_source_live_dry_run(item) for item in selected]
    summary = summarize_live_source_validation(results)
    summary.update(
        {
            "utility_result": utility_result,
            "queries": len(queries),
            "output_dir": str(out),
        }
    )

    (out / "live_validation_queries.json").write_text(json.dumps(queries, indent=2), encoding="utf-8")
    (out / "live_validation_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_jsonl(out / "live_validation_results.jsonl", results)
    (out / "live_validation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "live_validation_report.md").write_text(_render_report(queries, results, summary), encoding="utf-8")

    token_leak = _output_has_token_marker(out)
    return {
        "ok": not token_leak,
        "safe_completion": True,
        "candidates_selected": len(selected),
        "validation_results": len(results),
        "validated_live_source": summary["validated_live_source"],
        "partially_validated": summary["partially_validated"],
        "deferred_missing_credentials": summary["deferred_missing_credentials"],
        "deferred_no_network": summary["deferred_no_network"],
        "not_found": summary["not_found"],
        "failed_safely": summary["failed_safely"],
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "runtime_chat_integration": False,
        "trading_used": False,
        "b8_touched": False,
        "raw_body_saved": False,
        "token_leak_detected": token_leak,
        "output_dir": str(out),
    }
