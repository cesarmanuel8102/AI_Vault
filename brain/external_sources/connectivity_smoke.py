"""External source connectivity smoke tests.

Read-only. No memory/FAISS/real writes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class ExternalSourceStatus:
    ok: bool
    source_id: str
    source_type: str
    provider: str
    url: str
    http_status: int
    credential_status: str
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    license_or_terms: Optional[str] = None
    title: Optional[str] = None
    text_excerpt: Optional[str] = None
    raw_saved: bool = False
    raw_path: Optional[str] = None
    content_hash: Optional[str] = None
    rate_limit: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=lambda: {"method": "", "headers_redacted": True, "token_redacted": True})
    readme_tested: bool = False
    readme_status: Optional[int] = None
    readme_content_hash: Optional[str] = None


def _redact_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _env_exists(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _get_rate_limit_rps() -> int:
    try:
        return int(os.getenv("BRAIN_EXTERNAL_RATE_LIMIT_RPS", "2").strip())
    except Exception:
        return 2


def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> tuple:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            encoding = resp.headers.get("Content-Encoding", "").lower()
            if encoding == "gzip":
                body = gzip.decompress(body)
            status = resp.status
            rate_headers = {
                "limit": resp.headers.get("X-RateLimit-Limit"),
                "remaining": resp.headers.get("X-RateLimit-Remaining"),
                "reset": resp.headers.get("X-RateLimit-Reset"),
            }
            return body, status, rate_headers
    except urllib.error.HTTPError as e:
        return b"", e.code, {}
    except Exception:
        return b"", 0, {}


def _http_get_text(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> tuple:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            encoding = resp.headers.get("Content-Encoding", "").lower()
            if encoding == "gzip":
                body = gzip.decompress(body)
            status = resp.status
            return body, status
    except urllib.error.HTTPError as e:
        return b"", e.code
    except Exception:
        return b"", 0


def smoke_sec_edgar() -> ExternalSourceStatus:
    sec_user_agent = os.getenv("SEC_USER_AGENT", "").strip()
    if not sec_user_agent:
        return ExternalSourceStatus(
            ok=False,
            source_id="sec_submissions_CIK0000320193",
            source_type="sec_filing",
            provider="sec",
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            http_status=0,
            credential_status="credential_missing",
            error="SEC_USER_AGENT not set",
        )
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    headers = {
        "User-Agent": sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    body, status, rate_headers = _http_get_json(url, headers, timeout=15)
    time.sleep(1 / _get_rate_limit_rps())
    content_hash = hashlib.sha256(body).hexdigest()
    data = json.loads(body) if body else {}
    ok = status == 200 and bool(data.get("cik")) and bool(data.get("name"))
    return ExternalSourceStatus(
        ok=ok,
        source_id="sec_submissions_CIK0000320193",
        source_type="sec_filing",
        provider="sec",
        url=url,
        http_status=status,
        credential_status="not_required_user_agent_present",
        title=data.get("name"),
        content_hash=content_hash,
        rate_limit={"limit": rate_headers.get("limit"), "remaining": rate_headers.get("remaining"), "reset": rate_headers.get("reset")},
        provenance={"method": "api", "headers_redacted": True, "token_redacted": True},
    )


def smoke_github() -> ExternalSourceStatus:
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    url = "https://api.github.com/repos/OpenBB-finance/OpenBB"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
        cred_status = "authenticated"
    else:
        cred_status = "unauthenticated"
    body, status, rate_headers = _http_get_json(url, headers, timeout=15)
    time.sleep(1 / _get_rate_limit_rps())
    repo_hash = hashlib.sha256(body).hexdigest()
    data = json.loads(body) if body else {}
    repo_ok = status == 200 and bool(data.get("full_name"))
    license_info = data.get("license") or {}

    # README endpoint
    readme_url = "https://api.github.com/repos/OpenBB-finance/OpenBB/readme"
    readme_body, readme_status, _ = _http_get_json(readme_url, headers, timeout=15)
    readme_hash = hashlib.sha256(readme_body).hexdigest() if readme_body else None
    time.sleep(1 / _get_rate_limit_rps())

    ok = repo_ok
    if github_token:
        if status in (401, 403):
            cred_status = "authenticated_failed"
            ok = False
        else:
            cred_status = "authenticated" if ok else "authenticated_failed"
    else:
        if ok:
            cred_status = "unauthenticated"

    return ExternalSourceStatus(
        ok=ok,
        source_id="github_repo_openbb",
        source_type="github_repo",
        provider="github",
        url=url,
        http_status=status,
        credential_status=cred_status,
        title=data.get("full_name"),
        license_or_terms=license_info.get("spdx_id"),
        content_hash=repo_hash,
        rate_limit={"limit": rate_headers.get("limit"), "remaining": rate_headers.get("remaining"), "reset": rate_headers.get("reset")},
        provenance={"method": "api", "headers_redacted": True, "token_redacted": True},
        readme_tested=True,
        readme_status=readme_status,
        readme_content_hash=readme_hash,
    )


def smoke_fred() -> ExternalSourceStatus:
    fred_key = os.getenv("FRED_API_KEY", "").strip()
    if not fred_key:
        return ExternalSourceStatus(
            ok=False,
            source_id="fred_series_FEDFUNDS",
            source_type="fred_series",
            provider="fred",
            url="https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key=REDACTED&file_type=json&limit=5",
            http_status=0,
            credential_status="credential_missing",
            error="FRED_API_KEY not set",
        )
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={fred_key}&file_type=json&limit=5"
    body, status, rate_headers = _http_get_json(url, timeout=15)
    time.sleep(1 / _get_rate_limit_rps())
    content_hash = hashlib.sha256(body).hexdigest()
    data = json.loads(body) if body else {}
    observations = data.get("observations") or []
    ok = status == 200 and len(observations) > 0
    return ExternalSourceStatus(
        ok=ok,
        source_id="fred_series_FEDFUNDS",
        source_type="fred_series",
        provider="fred",
        url="https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key=REDACTED&file_type=json&limit=5",
        http_status=status,
        credential_status="authenticated",
        content_hash=content_hash,
        rate_limit={"limit": rate_headers.get("limit"), "remaining": rate_headers.get("remaining"), "reset": rate_headers.get("reset")},
        provenance={"method": "api", "headers_redacted": True, "token_redacted": True},
    )


def smoke_official_docs() -> ExternalSourceStatus:
    user_agent = os.getenv("BRAIN_EXTERNAL_USER_AGENT", "").strip()
    if not user_agent:
        user_agent = "AI_Vault_BrainLab external-source-smoke"
    url = "https://docs.github.com/en/rest"
    headers = {"User-Agent": user_agent}
    body, status = _http_get_text(url, headers, timeout=15)
    time.sleep(1 / _get_rate_limit_rps())
    content_hash = hashlib.sha256(body).hexdigest()
    text = body.decode("utf-8", errors="replace")[:300]
    return ExternalSourceStatus(
        ok=status == 200,
        source_id="docs_github_rest",
        source_type="official_doc",
        provider="docs",
        url=url,
        http_status=status,
        credential_status="not_required",
        title="GitHub REST API Docs" if status == 200 else None,
        text_excerpt=text,
        content_hash=content_hash,
        provenance={"method": "http_get", "headers_redacted": True, "token_redacted": True},
    )


def run_all_smokes() -> Dict[str, Any]:
    sec = smoke_sec_edgar()
    github = smoke_github()
    fred = smoke_fred()
    docs = smoke_official_docs()
    openbb = ExternalSourceStatus(
        ok=True,
        source_id="openbb_planned",
        source_type="openbb_provider",
        provider="openbb",
        url="",
        http_status=0,
        credential_status="planned",
        title="OpenBB planned",
    )
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    fred_key = os.getenv("FRED_API_KEY", "").strip()
    sec_ua = os.getenv("SEC_USER_AGENT", "").strip()
    brain_ua = os.getenv("BRAIN_EXTERNAL_USER_AGENT", "").strip()
    tokens = {
        "GITHUB_TOKEN": {"exists": bool(github_token), "redacted": _redact_secret(github_token) if github_token else None},
        "FRED_API_KEY": {"exists": bool(fred_key), "redacted": _redact_secret(fred_key) if fred_key else None},
        "SEC_USER_AGENT": {"exists": bool(sec_ua), "redacted": "present" if sec_ua else "not_present"},
        "BRAIN_EXTERNAL_USER_AGENT": {"exists": bool(brain_ua), "redacted": "present" if brain_ua else "not_present"},
    }

    missing_credentials = []
    if not github_token:
        missing_credentials.append("GITHUB_TOKEN")
    if not sec_ua:
        missing_credentials.append("SEC_USER_AGENT")
    if not fred_key:
        missing_credentials.append("FRED_API_KEY")
    if not brain_ua:
        missing_credentials.append("BRAIN_EXTERNAL_USER_AGENT")

    # Compute status flags
    ok = True  # overall ok unless uncaught exception
    complete = True
    partial = False

    # GitHub evaluation
    github_expected_logged_in = bool(github_token)
    if github_expected_logged_in:
        if not github.ok or github.credential_status == "authenticated_failed":
            complete = False
            partial = True
    else:
        # Token missing; still ok but not complete
        complete = False
        partial = True

    # SEC evaluation
    sec_expected = bool(sec_ua)
    if sec_expected:
        if not sec.ok:
            complete = False
            partial = True
    else:
        complete = False
        partial = True

    # FRED evaluation
    fred_expected = bool(fred_key)
    if fred_expected:
        if not fred.ok:
            complete = False
            partial = True
    else:
        complete = False
        partial = True

    # Docs must pass
    if not docs.ok:
        complete = False
        partial = True  # or False? docs failure is real failure
        ok = False

    return {
        "ok": ok,
        "complete": complete,
        "partial": partial,
        "missing_credentials": missing_credentials,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "sec_edgar": asdict(sec),
            "github": asdict(github),
            "fred": asdict(fred),
            "official_docs": asdict(docs),
            "openbb": asdict(openbb),
        },
        "tokens": tokens,
        "real_write_performed": False,
        "faiss_write_performed": False,
        "memory_write_performed": False,
    }
