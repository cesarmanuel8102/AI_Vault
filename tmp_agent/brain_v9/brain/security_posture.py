"""
Brain V9 — Canonical security posture summary.

Safe by design:
- Never returns secret values
- Summarizes env/gitignore posture, raw secrets audit volume, and dependency audit
- Can refresh dependency audit on demand using pip-audit
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import brain_v9.config as _cfg

log = logging.getLogger("brain.security_posture")

STATE_DIR = _cfg.STATE_PATH / "security"
SECURITY_POSTURE_ARTIFACT = STATE_DIR / "security_posture_latest.json"
SECRETS_REPORT_PATH = _cfg.BASE_PATH / "audit_reports" / "secrets_report.json"
DOTENV_PATH = _cfg.BASE_PATH / ".env"
DOTENV_EXAMPLE_PATH = _cfg.BASE_PATH / ".env.example"
GITIGNORE_PATH = _cfg.BASE_PATH / ".gitignore"
LEGACY_SECURITY_FILES = [
    _cfg.BRAIN_V9_PATH / "brain_v9" / "agent" / "tools.py",
    _cfg.BRAIN_V9_PATH / "brain_v9" / "brain" / "self_improvement.py",
    _cfg.BRAIN_V9_PATH / "brain_v9" / "ops" / "restart_brain_v9_safe.ps1",
]
SECRET_SOURCE_MAP = {
    "openai": ("OPENAI_API_KEY", _cfg.BASE_PATH / "tmp_agent" / "Secrets" / "openai_access.json"),
    "anthropic": ("ANTHROPIC_API_KEY", _cfg.BASE_PATH / "tmp_agent" / "Secrets" / "anthropic_access.json"),
    "gemini": ("GEMINI_API_KEY", _cfg.BASE_PATH / "tmp_agent" / "Secrets" / "gemini_access.json"),
}
LEGACY_LOOSE_SECRET_FILES = [
    _cfg.BASE_PATH / ".secrets" / "openai_api_key.txt",
    _cfg.BASE_PATH / "tmp_agent" / "Secrets" / "OPENI_ACCESS.json",
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Failed to read json %s: %s", path, exc)
        return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_text(path: Path) -> str:
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.debug("Failed to read text %s: %s", path, exc)
        return ""


def _read_env_key(path: Path, key: str) -> str:
    content = _read_text(path)
    if not content:
        return ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def _read_json_secret_value(path: Path) -> str:
    try:
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("token") or data.get("api_key") or data.get("password") or "")
    except Exception as exc:
        log.debug("Failed to read json secret %s: %s", path, exc)
        return ""


def _digest_secret(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _summarize_env_runtime() -> Dict[str, Any]:
    gitignore = _read_text(GITIGNORE_PATH)
    return {
        "dotenv_exists": DOTENV_PATH.exists(),
        "dotenv_example_exists": DOTENV_EXAMPLE_PATH.exists(),
        "gitignore_protects_dotenv": ".env" in gitignore,
        "gitignore_protects_secrets": ".secrets" in gitignore or "*secret*" in gitignore,
        "config_env_first": True,
    }


def _summarize_secrets_report() -> Dict[str, Any]:
    report = _read_json(SECRETS_REPORT_PATH, default={})
    findings: List[Dict[str, Any]]
    if isinstance(report, dict):
        findings = report.get("findings") or report.get("results") or report.get("items") or []
    elif isinstance(report, list):
        findings = report
    else:
        findings = []

    real_secret = 0
    false_positive = 0
    unclassified = 0
    for item in findings:
        classification = str(
            item.get("classification") or item.get("status") or ""
        ).lower()
        if classification == "real_secret":
            real_secret += 1
        elif classification == "false_positive":
            false_positive += 1
        else:
            unclassified += 1

    return {
        "report_exists": SECRETS_REPORT_PATH.exists(),
        "raw_finding_count": len(findings),
        "classified_real_secret": real_secret,
        "classified_false_positive": false_positive,
        "unclassified_count": unclassified,
    }


def _triage_secrets_report() -> Dict[str, Any]:
    report = _read_json(SECRETS_REPORT_PATH, default={})
    findings: List[Dict[str, Any]]
    if isinstance(report, dict):
        findings = report.get("findings") or report.get("results") or report.get("items") or []
    elif isinstance(report, list):
        findings = report
    else:
        findings = []

    categories: Dict[str, int] = {
        "potential_runtime_secret": 0,
        "config_reference": 0,
        "documentation_example": 0,
        "generated_or_cache": 0,
        "review_required": 0,
    }
    actionable_candidates: List[Dict[str, Any]] = []

    for item in findings:
        file_path = str(item.get("abs_path") or item.get("file") or "")
        suffix = Path(file_path).suffix.lower()
        line_text = str(item.get("line_text") or "")
        match_text = str(item.get("match") or "")
        pattern = str(item.get("pattern") or "").lower()
        path_lower = file_path.lower()
        line_lower = line_text.lower()
        match_lower = match_text.lower()
        match_value = match_text.split("=", 1)[1].strip() if "=" in match_text else match_text
        env_name_like = bool(match_value) and match_value.upper() == match_value and any(
            token in match_value for token in ["KEY", "TOKEN", "SECRET", "PASSWORD"]
        )
        secret_literal_like = ("sk-" in line_text and "..." not in line_text) or (
            "api_key=" in line_lower and not env_name_like and "your_" not in line_lower
        )

        category = "review_required"

        if (
            "__pycache__" in path_lower
            or suffix in {".pyc", ".pyo", ".csv", ".xml", ".log"}
            or "\\logs\\" in path_lower
            or "/logs/" in path_lower
            or "\\tmp_agent\\state\\reports\\" in path_lower
            or "/tmp_agent/state/reports/" in path_lower
            or "\\tmp_agent\\state\\rooms\\" in path_lower
            or "/tmp_agent/state/rooms/" in path_lower
            or "\\tmp_agent\\workspace\\receipts\\" in path_lower
            or "/tmp_agent/workspace/receipts/" in path_lower
            or "apply_request_backups" in path_lower
            or path_lower.endswith("brain_audit_report.txt")
            or "repomix-output.xml" in path_lower
            or path_lower.endswith("audit_reports\\secrets_report.json")
            or path_lower.endswith("audit_reports/secrets_report.json")
            or any(x in path_lower for x in [".pre_", ".broken", "baseline_", ".backup", ".old"])
        ):
            category = "generated_or_cache"
        elif "\\autogen_test\\" in path_lower or "/autogen_test/" in path_lower:
            category = "documentation_example"
        elif "\\workspace\\brainlab\\docs\\diagnostics\\" in path_lower or "/workspace/brainlab/docs/diagnostics/" in path_lower:
            category = "generated_or_cache"
        elif "\\workspace\\brainlab\\docs\\backups\\" in path_lower or "/workspace/brainlab/docs/backups/" in path_lower:
            category = "generated_or_cache"
        elif "\\workspace\\brainlab\\docs\\" in path_lower or "/workspace/brainlab/docs/" in path_lower:
            category = "documentation_example"
        elif suffix == ".md" or any(x in path_lower for x in ["migracion", "estado_", "readme", "auditoria"]):
            category = "documentation_example"
        elif (
            any(x in path_lower for x in ["20_infrastructure\\security\\", "20_infrastructure/security/"])
            and pattern == "password_assignment"
        ):
            category = "config_reference"
        elif suffix == ".py" and (
            ("os.getenv(" in line_text or "os.environ" in line_text or "environ.get(" in line_text)
            and env_name_like
        ):
            category = "config_reference"
        elif suffix == ".py" and env_name_like and not secret_literal_like:
            category = "config_reference"
        elif (suffix == ".py" or ".py." in path_lower) and (
            line_lower.strip().startswith("token =")
            or match_lower.startswith("token =")
            or match_lower.startswith("token=")
            or match_lower.startswith("token:")
            or line_lower.strip().startswith("api_key =")
            or match_lower.startswith("api_key =")
            or match_lower.startswith("api_key=")
            or line_lower.strip().startswith("key =")
            or match_lower.startswith("key =")
            or "token = getattr" in line_lower
            or "token = getattr" in match_lower
        ) and not secret_literal_like:
            category = "config_reference"
        elif (
            suffix == ".py"
            and "api_key=" in line_lower
            and env_name_like
            and "your_" not in line_lower
            and not secret_literal_like
        ):
            category = "config_reference"
        elif suffix == ".py" and (
            match_lower.replace(" ", "") in {"token=token", "token=none", "token=getattr", 'api_key="ollama"', "api_key='ollama'"}
            or line_lower.strip() in {"token = token", "token = none"}
            or ('api_key="ollama"' in line_lower or "api_key='ollama'" in line_lower)
        ):
            category = "config_reference"
        elif (
            any(x in path_lower for x in ["\\.env", "/.env", "\\tmp_agent\\secrets\\", "/tmp_agent/secrets/"])
            or ("sk-" in line_text and "..." not in line_text)
            or ("api_key=" in line_lower and "your_" not in line_lower and not env_name_like)
        ):
            category = "potential_runtime_secret"

        categories[category] += 1

        if category in {"potential_runtime_secret", "review_required"} and len(actionable_candidates) < 20:
            actionable_candidates.append(
                {
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "pattern": item.get("pattern"),
                    "match": item.get("match"),
                    "category": category,
                }
            )

    return {
        "categories": categories,
        "likely_false_positive_count": categories["config_reference"] + categories["documentation_example"] + categories["generated_or_cache"],
        "actionable_candidate_count": categories["potential_runtime_secret"] + categories["review_required"],
        "actionable_candidates": actionable_candidates,
    }


def _scan_legacy_security_refs() -> Dict[str, Any]:
    env_bat_refs = []
    for path in LEGACY_SECURITY_FILES:
        content = _read_text(path)
        if ".env.bat" in content:
            env_bat_refs.append(str(path))
    return {
        "env_bat_reference_count": len(env_bat_refs),
        "env_bat_reference_files": env_bat_refs,
    }


def _audit_secret_sources() -> Dict[str, Any]:
    providers: Dict[str, Dict[str, Any]] = {}
    duplicates = 0
    mismatches = 0
    env_only = 0
    json_only = 0
    fully_missing = 0

    for provider, (env_key, json_path) in SECRET_SOURCE_MAP.items():
        env_value = _read_env_key(DOTENV_PATH, env_key)
        json_value = _read_json_secret_value(json_path)
        env_present = bool(env_value)
        json_present = bool(json_value)
        same_value = bool(env_value and json_value and env_value == json_value)

        if env_present and json_present:
            duplicates += 1
            if not same_value:
                mismatches += 1
        elif env_present:
            env_only += 1
        elif json_present:
            json_only += 1
        else:
            fully_missing += 1

        providers[provider] = {
            "env_present": env_present,
            "json_present": json_present,
            "same_value": same_value,
            "env_digest": _digest_secret(env_value),
            "json_digest": _digest_secret(json_value),
        }

    return {
        "providers": providers,
        "duplicate_source_count": duplicates,
        "mismatch_count": mismatches,
        "env_only_count": env_only,
        "json_only_count": json_only,
        "fully_missing_count": fully_missing,
    }


def _scan_legacy_secret_files() -> Dict[str, Any]:
    existing = [str(path) for path in LEGACY_LOOSE_SECRET_FILES if path.exists()]
    mapped_json_existing = [str(path) for _, path in SECRET_SOURCE_MAP.values() if path.exists()]
    return {
        "loose_secret_file_count": len(existing),
        "loose_secret_files": existing,
        "mapped_json_fallback_count": len(mapped_json_existing),
        "mapped_json_fallback_files": mapped_json_existing,
        "runtime_json_fallback_active": False,
    }


def _count_stale_actionable_candidates(candidates: List[Dict[str, Any]]) -> int:
    count = 0
    for item in candidates:
        raw = item.get("file")
        if not raw:
            continue
        try:
            path = Path(str(raw))
            if not path.is_absolute():
                path = _cfg.BASE_PATH / str(raw)
            if not path.exists():
                count += 1
        except Exception as exc:
            log.debug("Failed to evaluate actionable candidate path %s: %s", raw, exc)
    return count


def _filter_existing_actionable_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing: List[Dict[str, Any]] = []
    for item in candidates:
        raw = item.get("file")
        if not raw:
            continue
        try:
            path = Path(str(raw))
            if not path.is_absolute():
                path = _cfg.BASE_PATH / str(raw)
            if path.exists():
                existing.append(item)
        except Exception as exc:
            log.debug("Failed to evaluate actionable candidate path %s: %s", raw, exc)
    return existing


def _refresh_dependency_audit() -> Dict[str, Any]:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
            temp_path = Path(tmp.name)
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-f", "json", "-o", str(temp_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        report = _read_json(temp_path, default={})
        dependencies = report.get("dependencies") if isinstance(report, dict) else []
        vulnerabilities: List[Dict[str, Any]] = []
        affected_packages: List[Dict[str, Any]] = []
        if isinstance(dependencies, list):
            for dep in dependencies:
                vulns = dep.get("vulns") or []
                if vulns:
                    affected_packages.append(
                        {
                            "name": dep.get("name"),
                            "version": dep.get("version"),
                            "vuln_count": len(vulns),
                        }
                    )
                    for vuln in vulns:
                        vulnerabilities.append(
                            {
                                "package": dep.get("name"),
                                "version": dep.get("version"),
                                "id": vuln.get("id"),
                                "aliases": vuln.get("aliases") or [],
                                "fix_versions": vuln.get("fix_versions") or [],
                            }
                        )
        patchable = 0
        upstream_blocked = 0
        for vuln in vulnerabilities:
            if vuln.get("fix_versions"):
                patchable += 1
            else:
                upstream_blocked += 1
        return {
            "available": True,
            "returncode": proc.returncode,
            "affected_package_count": len(affected_packages),
            "vulnerability_count": len(vulnerabilities),
            "patchable_vulnerability_count": patchable,
            "upstream_blocked_vulnerability_count": upstream_blocked,
            "affected_packages": affected_packages[:10],
            "vulnerabilities": vulnerabilities[:20],
            "stderr": (proc.stderr or "").strip()[:400],
        }
    except subprocess.TimeoutExpired:
        return {
            "available": False,
            "error": "timeout",
        }
    except Exception as exc:
        log.debug("Dependency audit failed: %s", exc)
        return {
            "available": False,
            "error": type(exc).__name__,
        }
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError as exc:
                log.debug("Could not delete temp pip-audit report %s: %s", temp_path, exc)


def build_security_posture(refresh_dependency_audit: bool = True) -> Dict[str, Any]:
    dependency_audit = _refresh_dependency_audit() if refresh_dependency_audit else {}
    triage = _triage_secrets_report()
    triage["stale_actionable_candidate_count"] = _count_stale_actionable_candidates(
        triage.get("actionable_candidates", [])
    )
    triage["current_actionable_candidates"] = _filter_existing_actionable_candidates(
        triage.get("actionable_candidates", [])
    )
    triage["current_actionable_candidate_count"] = len(
        triage["current_actionable_candidates"]
    )
    payload = {
        "generated_utc": _now_utc_iso(),
        "env_runtime": _summarize_env_runtime(),
        "secrets_audit": _summarize_secrets_report(),
        "secrets_triage": triage,
        "secret_source_audit": _audit_secret_sources(),
        "legacy_secret_files": _scan_legacy_secret_files(),
        "legacy_runtime_refs": _scan_legacy_security_refs(),
        "dependency_audit": dependency_audit,
    }
    _write_json(SECURITY_POSTURE_ARTIFACT, payload)
    return payload


def get_security_posture_latest() -> Dict[str, Any]:
    payload = _read_json(SECURITY_POSTURE_ARTIFACT, default={})
    if isinstance(payload, dict) and payload:
        return payload
    return build_security_posture(refresh_dependency_audit=True)
