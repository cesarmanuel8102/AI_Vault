from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_ROOT = BASE_PATH / "tmp_agent" / "state"
EXTERNAL_SOURCE_SECURITY_POLICY_PATH = STATE_ROOT / "external_source_security_policy.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def curate_repo(source_manifest: Dict[str, Any], repo_metadata_path: Path, output_path: Path) -> Dict[str, Any]:
    metadata = read_json(repo_metadata_path, default={}) or {}
    root_index = read_json(source_manifest.get("root_index_path", ""), default=[]) or []
    repo_tree = read_json(source_manifest.get("repo_tree_index_path", ""), default=[]) or []
    priority_catalog = read_json(source_manifest.get("priority_file_catalog_path", ""), default=[]) or []
    dependency_hints = read_json(source_manifest.get("dependency_hints_path", ""), default={}) or {}
    security_policy = read_json(EXTERNAL_SOURCE_SECURITY_POLICY_PATH, default={}) or {}
    stargazers = int(metadata.get("stargazers_count") or 0)
    open_issues = int(metadata.get("open_issues_count") or 0)
    size_kb = int(metadata.get("size") or 0)
    archived = bool(metadata.get("archived"))
    disabled = bool(metadata.get("disabled"))
    has_wiki = bool(metadata.get("has_wiki"))
    has_issues = bool(metadata.get("has_issues"))
    default_branch = metadata.get("default_branch") or "main"
    updated_at = metadata.get("updated_at")
    license_name = ((metadata.get("license") or {}).get("spdx_id")) or "UNKNOWN"
    language = metadata.get("language") or "UNKNOWN"
    topics = metadata.get("topics") or []
    root_names = {str(item.get("name") or "").lower() for item in root_index}
    tests_present = any(
        name in root_names
        for name in ("tests", "test", "pytest.ini", "tox.ini", ".github")
    )
    docs_present = any(name in root_names for name in ("docs", "readme.md", "mkdocs.yml"))
    dependency_files = sorted(
        name for name in root_names
        if name in {"requirements.txt", "pyproject.toml", "package.json", "setup.py", "setup.cfg", "pipfile"}
    )
    suspicious_binaries = sorted(
        name for name in root_names
        if name.endswith((".exe", ".dll", ".so", ".bin"))
    )
    apparent_secrets = sorted(
        name for name in root_names
        if name in {".env", ".npmrc", "id_rsa", "id_dsa"} or name.endswith((".pem", ".key"))
    )
    dependency_risk_flags: List[str] = []
    for file_name, content in dependency_hints.items():
        raw = str(content).lower()
        if "subprocess" in raw or "os.system" in raw:
            dependency_risk_flags.append(f"{file_name}:unsafe_subprocess_pattern")
        if "eval(" in raw:
            dependency_risk_flags.append(f"{file_name}:eval_usage")

    reject_reasons: List[str] = []
    notes: List[str] = []
    risk = 0.0
    score = 5.0

    if archived or disabled:
        reject_reasons.append("repo_archived_or_disabled")
        risk += 3.0
    if stargazers >= 10000:
        score += 2.0
    elif stargazers >= 1000:
        score += 1.0
    else:
        notes.append("low_social_proof")
        risk += 0.5

    if has_issues:
        score += 0.5
    if has_wiki:
        score += 0.25
    if size_kb > 2_000_000:
        risk += 2.0
        notes.append("large_repo_review_required")
    elif size_kb > 200_000:
        risk += 0.75

    if open_issues > 500:
        notes.append("high_issue_volume")
        risk += 0.5

    if tests_present:
        score += 0.75
    else:
        notes.append("tests_not_obvious_at_root")
        risk += 0.5

    if docs_present:
        score += 0.5
    else:
        notes.append("docs_not_obvious_at_root")
        risk += 0.25

    if dependency_files:
        score += 0.35
    else:
        notes.append("dependency_manifest_not_detected")
        risk += 0.25

    if suspicious_binaries:
        notes.append("suspicious_binaries_present")
        risk += 1.5
    if apparent_secrets:
        reject_reasons.append("apparent_secrets_in_root")
        risk += 3.0
    if dependency_risk_flags:
        notes.append("dependency_risk_flags_detected")
        risk += 1.0

    allowlist_seed = set(((security_policy.get("domains_policy") or {}).get("allowlist_seed") or []))
    repo_host_allowed = "github.com" in allowlist_seed or not allowlist_seed
    if not repo_host_allowed:
        notes.append("source_host_not_in_allowlist_seed")
        risk += 0.5

    if license_name in {"MIT", "Apache-2.0", "BSD-3-Clause"}:
        license_status = "compatible"
        score += 1.0
    elif license_name == "UNKNOWN":
        license_status = "unknown_review_required"
        risk += 1.5
    else:
        license_status = "compatible_review_required"
        risk += 1.0

    if any(t in topics for t in ("multi-agent", "agents", "llm", "orchestration")):
        score += 1.0
    if language in {"Python", "Jupyter Notebook", "TypeScript"}:
        score += 0.5

    recommended_action = "analyze"
    if reject_reasons:
        recommended_action = "reject"
    elif risk >= 5.0:
        recommended_action = "quarantine"
    elif score < 6.0:
        recommended_action = "learn_only"

    report = {
        "source_id": source_manifest.get("source_id"),
        "curated_at_utc": _utc_now(),
        "repo": {
            "full_name": metadata.get("full_name"),
            "default_branch": default_branch,
            "updated_at": updated_at,
            "stargazers_count": stargazers,
            "open_issues_count": open_issues,
            "size_kb": size_kb,
            "language": language,
            "topics": topics,
            "tests_present": tests_present,
            "docs_present": docs_present,
            "dependency_files": dependency_files,
            "tree_entries": len(repo_tree),
            "priority_files_scanned": len(priority_catalog),
        },
        "curation_score": round(score, 2),
        "risk_score": round(risk, 2),
        "license_status": license_status,
        "recommended_action": recommended_action,
        "reject_reasons": reject_reasons,
        "notes": notes,
        "dependency_risk_flags": dependency_risk_flags,
        "suspicious_binaries": suspicious_binaries,
        "apparent_secrets": apparent_secrets,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, report)
    return report
