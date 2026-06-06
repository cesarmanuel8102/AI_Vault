"""Real source ingestion dry-run.

Read-only. No memory/FAISS/real writes.
Reuses brain.external_sources.connectivity_smoke.run_all_smokes().
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.external_sources.connectivity_smoke import run_all_smokes


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def redact_url(url: str) -> str:
    if not url:
        return ""
    # Redact API keys or tokens if present in query string
    # Simple redaction for fred api_key
    if "api_key=" in url:
        parts = url.split("api_key=")
        before = parts[0]
        after = parts[1]
        # Find next & or end
        next_amp = after.find("&")
        if next_amp >= 0:
            after_redacted = after[next_amp:]
        else:
            after_redacted = ""
        return f"{before}api_key=REDACTED{after_redacted}"
    return url


def safe_excerpt(text: Optional[str], max_chars: int = 800) -> str:
    if not text:
        return ""
    return text[:max_chars].replace("\r", " ").replace("\n", " ")


def build_normalized_source_records(smoke_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    records = []
    sources = smoke_result.get("sources", {})
    for key, src in sources.items():
        record = {
            "source_id": src.get("source_id", key),
            "source_type": src.get("source_type", "unknown"),
            "provider": src.get("provider", "unknown"),
            "url": redact_url(src.get("url", "")),
            "retrieved_at": src.get("timestamp", now_utc()),
            "http_status": src.get("http_status", 0),
            "credential_status": src.get("credential_status", "unknown"),
            "license_or_terms": src.get("license_or_terms"),
            "content_hash": src.get("content_hash"),
            "title": src.get("title"),
            "text_excerpt": safe_excerpt(src.get("text_excerpt")),
            "rate_limit": src.get("rate_limit", {"limit": None, "remaining": None, "reset": None}),
            "provenance": {
                "method": src.get("provenance", {}).get("method", ""),
                "headers_redacted": True,
                "token_redacted": True,
                "raw_body_saved": False,
            },
            "dry_run": True,
            "real_write_allowed": False,
            "faiss_write_allowed": False,
            "memory_write_allowed": False,
        }
        records.append(record)
    return records


def _base_candidate(record: Dict[str, Any], topic: str, scores: Dict[str, float]) -> Dict[str, Any]:
    candidate_id = f"{record['provider']}_{record['source_id']}_dry_run_{sha256_text(record.get('source_id',''))[:8]}"
    return {
        "candidate_id": candidate_id,
        "state": "candidate_from_external_source",
        "label": "unverified_external_candidate",
        "topic": topic,
        "claim": f"External source retrieved from {record['provider']}: {record.get('title') or record['source_id']}",
        "text": record.get("text_excerpt", ""),
        "source_id": record["source_id"],
        "source_type": record.get("source_type", "unknown"),
        "provider": record["provider"],
        "evidence_refs": [record["source_id"]],
        "provenance": record.get("provenance", {}),
        "provenance_bundle": {
            "retrieved_at": record.get("retrieved_at"),
            "url_redacted": record.get("url"),
            "http_status": record.get("http_status"),
            "credential_status": record.get("credential_status"),
            "license_or_terms": record.get("license_or_terms"),
            "content_hash": record.get("content_hash"),
        },
        "validation_score": scores.get("validation_score", 0.0),
        "curation_score": scores.get("curation_score", 0.0),
        "trust_score": scores.get("trust_score", 0.0),
        "warnings": [
            "dry_run_only",
            "not_promoted_to_memory",
            "external_source_unverified_candidate",
            "requires_operator_review_before_promotion",
        ],
        "real_write_allowed": False,
        "faiss_write_allowed": False,
        "memory_write_allowed": False,
        "promotion_allowed": False,
    }


def github_record_to_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    scores = {"validation_score": 0.82, "curation_score": 0.75, "trust_score": 0.78}
    candidate = _base_candidate(record, "external_source_connectivity/github_repository_metadata", scores)
    if record.get("provider") == "github" and record.get("http_status") == 200:
        candidate["warnings"].append("github_authenticated" if record.get("credential_status") == "authenticated" else "github_unauthenticated_or_authenticated_failed")
    return candidate


def sec_record_to_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    scores = {"validation_score": 0.90, "curation_score": 0.82, "trust_score": 0.88}
    candidate = _base_candidate(record, "external_source_connectivity/sec_company_submissions", scores)
    candidate["warnings"].append("not_financial_advice")
    return candidate


def docs_record_to_candidate(record: Dict[str, Any]) -> Dict[str, Any]:
    scores = {"validation_score": 0.80, "curation_score": 0.74, "trust_score": 0.76}
    candidate = _base_candidate(record, "external_source_connectivity/official_documentation", scores)
    return candidate


def _to_candidate(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    provider = record.get("provider", "")
    http_status = record.get("http_status", 0)
    # Only generate candidates when http_status == 200 and sufficient metadata exists
    if http_status != 200:
        return None
    if provider == "fred":
        # FRED is intentionally deferred, skip candidate generation
        return None
    if provider == "openbb":
        # OpenBB is planned/deferred
        return None
    if provider not in {"github", "sec", "docs"}:
        return None
    if provider == "github":
        return github_record_to_candidate(record)
    if provider == "sec":
        return sec_record_to_candidate(record)
    if provider == "docs":
        return docs_record_to_candidate(record)
    return None


def run_real_source_ingestion_dry_run(output_dir: str | None = None) -> Dict[str, Any]:
    smoke = run_all_smokes()
    normalized_records = build_normalized_source_records(smoke)

    # Build candidates only for supported providers
    candidates = []
    for rec in normalized_records:
        cand = _to_candidate(rec)
        if cand is not None:
            candidates.append(cand)

    # Determine providers
    providers_seen = list({r["provider"] for r in normalized_records})
    providers_passed = list({r["provider"] for r in normalized_records if r.get("http_status") == 200})
    providers_deferred = list({r["provider"] for r in normalized_records if r.get("http_status") == 0})

    # Determine ok/complete/partial
    github_ok = any(r["provider"] == "github" and r.get("http_status") == 200 for r in normalized_records)
    sec_ok = any(r["provider"] == "sec" and r.get("http_status") == 200 for r in normalized_records)
    docs_ok = any(r["provider"] == "docs" and r.get("http_status") == 200 for r in normalized_records)

    ok = github_ok or sec_ok or docs_ok
    complete = github_ok and sec_ok and docs_ok
    partial = (not complete) or any(p == "fred" for p in providers_deferred)

    # Candidate counts per provider
    github_candidates_count = sum(1 for c in candidates if c.get("provider") == "github")
    sec_candidates_count = sum(1 for c in candidates if c.get("provider") == "sec")
    docs_candidates_count = sum(1 for c in candidates if c.get("provider") == "docs")
    fred_candidates_count = sum(1 for c in candidates if c.get("provider") == "fred")
    openbb_candidates_count = sum(1 for c in candidates if c.get("provider") == "openbb")

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "normalized_source_records.json").write_text(json.dumps(normalized_records, indent=2), encoding="utf-8")
        (out / "curated_candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
        with open(out / "curated_candidates.jsonl", "w", encoding="utf-8") as fh:
            for c in candidates:
                fh.write(json.dumps(c) + "\n")
        summary = {
            "ok": ok,
            "complete": complete,
            "partial": partial,
            "normalized_records_count": len(normalized_records),
            "curated_candidates_count": len(candidates),
            "providers_seen": providers_seen,
            "providers_passed": providers_passed,
            "providers_deferred": providers_deferred,
            "real_write_performed": False,
            "faiss_write_performed": False,
            "memory_write_performed": False,
            "promotion_performed": False,
            "output_dir": str(out),
            "timestamp": now_utc(),
        }
        (out / "ingestion_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    else:
        out = None

    return {
        "ok": ok,
        "complete": complete,
        "partial": partial,
        "normalized_records_count": len(normalized_records),
        "curated_candidates_count": len(candidates),
        "providers_seen": providers_seen,
        "providers_passed": providers_passed,
        "providers_deferred": providers_deferred,
        "github_candidates_count": github_candidates_count,
        "sec_candidates_count": sec_candidates_count,
        "docs_candidates_count": docs_candidates_count,
        "fred_candidates_count": fred_candidates_count,
        "openbb_candidates_count": openbb_candidates_count,
        "real_write_performed": False,
        "faiss_write_performed": False,
        "memory_write_performed": False,
        "promotion_performed": False,
        "output_dir": str(out) if out else None,
    }
