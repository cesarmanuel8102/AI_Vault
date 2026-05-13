"""
Brain V9 — Auto Surgeon
========================
Closes the autonomous self-improvement loop:

  Trade Diagnostics (pattern detection)
      ↓ issue
  CodeGen (qwen3-coder:480b-cloud)
      ↓ patch
  Self-Improvement (stage → validate → promote → rollback)
      ↓ deployed fix (or safe rollback)

This module orchestrates the full cycle. It is called as an autonomy
action from the action_executor, running in the non_trading lane.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.brain.codegen import CodeGenClient
from brain_v9.brain.trade_diagnostics import (
    run_diagnostic_scan,
    get_next_actionable_issue,
    mark_issue_attempted,
)
from brain_v9.brain.self_improvement import (
    create_staged_change,
    validate_staged_change,
    promote_staged_change,
    ALLOWED_ROOTS,
)

log = logging.getLogger("AutoSurgeon")

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
SURGEON_PATH = STATE_PATH / "auto_surgeon"
SURGEON_PATH.mkdir(parents=True, exist_ok=True)

SURGEON_LEDGER = SURGEON_PATH / "surgeon_ledger.json"
SURGEON_STATUS = SURGEON_PATH / "surgeon_status_latest.json"

# Safety limits
MAX_PATCHES_PER_DAY = 10
MAX_ACTIVE_CHANGES = 3  # Don't stage more than 3 changes simultaneously
PATCH_COOLDOWN_SECONDS = 600  # 10 minutes between patches

# Singleton client (created lazily)
_codegen_client: Optional[CodeGenClient] = None


def _get_codegen_client() -> CodeGenClient:
    global _codegen_client
    if _codegen_client is None:
        _codegen_client = CodeGenClient()
    return _codegen_client


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_surgeon_ledger() -> Dict:
    return read_json(SURGEON_LEDGER, {
        "schema_version": "auto_surgeon_v1",
        "entries": [],
        "daily_count": 0,
        "daily_date": None,
    })


def _save_surgeon_ledger(ledger: Dict) -> None:
    ledger["updated_utc"] = _utc_now()
    write_json(SURGEON_LEDGER, ledger)


def _check_daily_limit() -> bool:
    """Check if we've exceeded the daily patch limit."""
    from datetime import datetime, timezone
    ledger = _read_surgeon_ledger()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ledger.get("daily_date") != today:
        ledger["daily_date"] = today
        ledger["daily_count"] = 0
        _save_surgeon_ledger(ledger)
    return ledger["daily_count"] < MAX_PATCHES_PER_DAY


def _increment_daily_count() -> None:
    from datetime import datetime, timezone
    ledger = _read_surgeon_ledger()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ledger.get("daily_date") != today:
        ledger["daily_date"] = today
        ledger["daily_count"] = 0
    ledger["daily_count"] += 1
    _save_surgeon_ledger(ledger)


def _check_patch_cooldown() -> bool:
    """Check if enough time has passed since the last patch."""
    from datetime import datetime, timezone
    status = read_json(SURGEON_STATUS, {})
    last_patch = status.get("last_patch_utc")
    if not last_patch:
        return True
    try:
        last_dt = datetime.fromisoformat(last_patch.replace("Z", "+00:00"))
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        return elapsed >= PATCH_COOLDOWN_SECONDS
    except Exception:
        return True


def _is_file_allowed(file_path: str) -> bool:
    """Check if a file is within ALLOWED_ROOTS for self-improvement."""
    resolved = Path(file_path).resolve()
    return any(str(resolved).startswith(str(root)) for root in ALLOWED_ROOTS)


def _read_file_safe(file_path: str, max_size: int = 50000) -> Optional[str]:
    """Read a file's contents, returning None if it doesn't exist or is too large."""
    try:
        p = Path(file_path)
        if not p.exists():
            return None
        content = p.read_text(encoding="utf-8")
        if len(content) > max_size:
            # Return truncated with note
            return content[:max_size] + f"\n\n[... truncated at {max_size} chars, total {len(content)} ...]"
        return content
    except Exception as e:
        log.warning("Could not read %s: %s", file_path, e)
        return None


def _apply_patch_to_file(file_path: str, changes: list) -> Dict[str, Any]:
    """Apply a list of old→new replacements to a file.

    Returns {"success": bool, "error": str|None, "changes_applied": int}
    Does NOT write the file — returns the new content for staging.
    """
    try:
        p = Path(file_path)
        if not p.exists():
            return {"success": False, "error": f"File not found: {file_path}", "changes_applied": 0}

        content = p.read_text(encoding="utf-8")
        changes_applied = 0

        for change in changes:
            old = change.get("old", "")
            new = change.get("new", "")
            if not old:
                return {"success": False, "error": "Empty 'old' string in patch", "changes_applied": changes_applied}
            if old not in content:
                # Try with normalized line endings
                old_normalized = old.replace("\r\n", "\n")
                content_normalized = content.replace("\r\n", "\n")
                if old_normalized in content_normalized:
                    content = content_normalized
                    old = old_normalized
                    new = new.replace("\r\n", "\n")
                else:
                    return {
                        "success": False,
                        "error": f"'old' string not found in {file_path}. First 100 chars: {old[:100]}",
                        "changes_applied": changes_applied,
                    }
            content = content.replace(old, new, 1)
            changes_applied += 1

        return {"success": True, "new_content": content, "changes_applied": changes_applied}
    except Exception as e:
        return {"success": False, "error": str(e), "changes_applied": 0}


async def run_auto_surgeon_cycle() -> Dict[str, Any]:
    """Execute one full auto-surgeon cycle:
    1. Run diagnostic scan
    2. Pick the highest-priority actionable issue
    3. Generate a code patch via CodeGen
    4. Stage, validate, and optionally promote the patch

    Returns a structured result for the autonomy action ledger.
    """
    cycle_start = time.time()
    result = {
        "action_name": "auto_surgeon_cycle",
        "started_utc": _utc_now(),
        "success": False,
        "phase": "init",
    }

    # ── Phase 1: Diagnostic Scan ──────────────────────────────────────────
    result["phase"] = "diagnostics"
    scan_result = run_diagnostic_scan()
    result["diagnostics"] = scan_result

    if not scan_result.get("scanned"):
        result["status"] = "diagnostics_cooldown"
        result["success"] = True  # Not a failure, just nothing to do
        _save_status(result)
        return result

    # ── Phase 2: Pick Issue ──────────────────────────────────────────────
    result["phase"] = "issue_selection"
    issue = get_next_actionable_issue()

    if not issue:
        result["status"] = "no_actionable_issues"
        result["success"] = True
        _save_status(result)
        return result

    result["issue"] = {
        "issue_id": issue["issue_id"],
        "title": issue["title"],
        "severity": issue["severity"],
        "category": issue.get("category"),
        "attempts": issue.get("attempts", 0),
    }

    # ── Safety Checks ────────────────────────────────────────────────────
    if not _check_daily_limit():
        result["status"] = "daily_limit_reached"
        result["success"] = True
        _save_status(result)
        return result

    if not _check_patch_cooldown():
        result["status"] = "patch_cooldown"
        result["success"] = True
        _save_status(result)
        return result

    affected_file = issue.get("affected_file")
    if not affected_file:
        result["status"] = "no_affected_file"
        mark_issue_attempted(issue["issue_id"], {"success": False, "error": "no_affected_file"})
        _save_status(result)
        return result

    if not _is_file_allowed(affected_file):
        log.warning(
            "AutoSurgeon: file %s is outside ALLOWED_ROOTS, skipping issue %s",
            affected_file, issue["issue_id"],
        )
        result["status"] = "file_outside_allowed_roots"
        result["skipped_file"] = affected_file
        mark_issue_attempted(issue["issue_id"], {"success": False, "error": "file_outside_allowed_roots"})
        _save_status(result)
        return result

    # ── Phase 3: Read File Contents ──────────────────────────────────────
    result["phase"] = "read_files"
    file_contents = {}
    content = _read_file_safe(affected_file)
    if content:
        file_contents[affected_file] = content
    else:
        result["status"] = "cannot_read_affected_file"
        mark_issue_attempted(issue["issue_id"], {"success": False, "error": "cannot_read_file"})
        _save_status(result)
        return result

    # ── Phase 4: Generate Patch ──────────────────────────────────────────
    result["phase"] = "codegen"
    client = _get_codegen_client()

    try:
        codegen_result = await client.generate_patch(issue, file_contents)
    except Exception as e:
        log.error("AutoSurgeon codegen exception: %s", e)
        codegen_result = {"success": False, "error": str(e)}

    result["codegen"] = {
        "success": codegen_result.get("success"),
        "model_used": codegen_result.get("model_used"),
        "latency_s": codegen_result.get("latency_s"),
        "retries": codegen_result.get("retries"),
        "reasoning": (codegen_result.get("reasoning") or "")[:500],
    }

    if not codegen_result.get("success"):
        result["status"] = "codegen_failed"
        result["error"] = codegen_result.get("error")
        mark_issue_attempted(issue["issue_id"], codegen_result)
        _save_status(result)
        return result

    # ── Phase 5: Apply Patch to Local Copy ───────────────────────────────
    result["phase"] = "apply_patch"
    patch = codegen_result["patch"]
    patched_files = {}

    for fpath, changes in patch.items():
        # Resolve the file path — model might return relative or different separators
        resolved_fpath = _resolve_patch_filepath(fpath, affected_file)
        if not resolved_fpath:
            result["status"] = "patch_file_not_found"
            result["error"] = f"Cannot resolve patch file: {fpath}"
            mark_issue_attempted(issue["issue_id"], {"success": False, "error": result["error"]})
            _save_status(result)
            return result

        if not _is_file_allowed(resolved_fpath):
            result["status"] = "patch_file_outside_roots"
            result["error"] = f"Patch targets file outside allowed roots: {resolved_fpath}"
            mark_issue_attempted(issue["issue_id"], {"success": False, "error": result["error"]})
            _save_status(result)
            return result

        apply_result = _apply_patch_to_file(resolved_fpath, changes)
        if not apply_result["success"]:
            result["status"] = "patch_apply_failed"
            result["error"] = apply_result["error"]
            mark_issue_attempted(issue["issue_id"], {"success": False, "error": result["error"]})
            _save_status(result)
            return result

        patched_files[resolved_fpath] = apply_result["new_content"]

    # ── Phase 6: Stage via Self-Improvement ──────────────────────────────
    result["phase"] = "staging"
    try:
        # Write patched content to the files (self_improvement will backup originals)
        file_paths = list(patched_files.keys())
        # First, create the staged change (this makes backups)
        staged = create_staged_change(
            files=file_paths,
            objective=f"AutoSurgeon fix for {issue['issue_id']}: {issue['title']}",
            change_type="auto_surgeon_patch",
        )
        change_id = staged["change_id"]
        result["change_id"] = change_id

        # Now write the patched content to the staged copies
        for fpath, new_content in patched_files.items():
            for file_entry in staged["files"]:
                if file_entry["target"] == fpath:
                    Path(file_entry["staged"]).write_text(new_content, encoding="utf-8")
                    break
    except Exception as e:
        result["status"] = "staging_failed"
        result["error"] = str(e)
        mark_issue_attempted(issue["issue_id"], {"success": False, "error": str(e)})
        _save_status(result)
        return result

    # ── Phase 7: Validate ────────────────────────────────────────────────
    result["phase"] = "validation"
    try:
        validation = validate_staged_change(change_id)
        result["validation"] = {
            "passed": validation.get("passed"),
            "errors": validation.get("errors", [])[:3],
            "checks": {k: v.get("passed") for k, v in validation.get("checks", {}).items()},
        }
    except Exception as e:
        result["status"] = "validation_exception"
        result["error"] = str(e)
        mark_issue_attempted(issue["issue_id"], {"success": False, "error": str(e), "change_id": change_id})
        _save_status(result)
        return result

    if not validation.get("passed"):
        result["status"] = "validation_failed"
        mark_issue_attempted(issue["issue_id"], {
            "success": False,
            "error": "validation_failed",
            "change_id": change_id,
            "validation_errors": validation.get("errors", []),
        })
        _save_status(result)
        return result

    # ── Phase 8: Promote ─────────────────────────────────────────────────
    result["phase"] = "promotion"
    try:
        promotion = promote_staged_change(change_id)
        result["promotion"] = {
            "status": promotion.get("status"),
            "job_id": promotion.get("job_id"),
            "success": promotion.get("success"),
        }
    except Exception as e:
        result["status"] = "promotion_exception"
        result["error"] = str(e)
        mark_issue_attempted(issue["issue_id"], {
            "success": False,
            "error": str(e),
            "change_id": change_id,
        })
        _save_status(result)
        return result

    # ── Finalize ─────────────────────────────────────────────────────────
    _increment_daily_count()
    result["phase"] = "completed"
    result["status"] = "patch_promoted" if promotion.get("success") else "promotion_scheduled"
    result["success"] = True
    result["duration_s"] = round(time.time() - cycle_start, 2)
    result["finished_utc"] = _utc_now()

    mark_issue_attempted(issue["issue_id"], {
        "success": True,
        "promoted": promotion.get("success"),
        "change_id": change_id,
        "model_used": codegen_result.get("model_used"),
    })

    # Append to surgeon ledger
    ledger = _read_surgeon_ledger()
    ledger["entries"].append({
        "timestamp": _utc_now(),
        "issue_id": issue["issue_id"],
        "title": issue["title"],
        "change_id": change_id,
        "model_used": codegen_result.get("model_used"),
        "status": result["status"],
        "duration_s": result["duration_s"],
    })
    # Keep last 100 entries
    if len(ledger["entries"]) > 100:
        ledger["entries"] = ledger["entries"][-100:]
    _save_surgeon_ledger(ledger)

    _save_status(result)
    log.info(
        "AutoSurgeon completed: issue=%s change=%s status=%s model=%s %.1fs",
        issue["issue_id"], change_id, result["status"],
        codegen_result.get("model_used"), result["duration_s"],
    )
    return result


def _resolve_patch_filepath(model_path: str, original_affected: str) -> Optional[str]:
    """Resolve a file path from the model's patch to an actual file.

    The model might return:
    - The exact path we gave it
    - A path with different separators
    - A relative path
    """
    # Direct match
    p = Path(model_path)
    if p.exists():
        return str(p.resolve())

    # Try with forward slashes converted
    p2 = Path(model_path.replace("/", "\\"))
    if p2.exists():
        return str(p2.resolve())

    # If the basename matches the affected file, use the affected file's path
    if Path(model_path).name == Path(original_affected).name:
        return str(Path(original_affected).resolve())

    return None


def _save_status(result: Dict) -> None:
    """Save latest surgeon status for monitoring."""
    try:
        write_json(SURGEON_STATUS, {
            "last_patch_utc": _utc_now() if result.get("change_id") else None,
            "last_cycle_utc": _utc_now(),
            "last_status": result.get("status"),
            "last_phase": result.get("phase"),
            "last_error": result.get("error"),
            "last_issue": result.get("issue", {}).get("issue_id"),
            "last_change_id": result.get("change_id"),
            "last_codegen": result.get("codegen"),
            "codegen_metrics": _get_codegen_client().metrics if _codegen_client else {},
        })
    except Exception as e:
        log.debug("Could not save surgeon status: %s", e)


def get_surgeon_status() -> Dict:
    """Get the current auto-surgeon status for API/dashboard."""
    status = read_json(SURGEON_STATUS, {})
    ledger = _read_surgeon_ledger()
    status["daily_count"] = ledger.get("daily_count", 0)
    status["daily_limit"] = MAX_PATCHES_PER_DAY
    status["total_entries"] = len(ledger.get("entries", []))
    status["recent_entries"] = ledger.get("entries", [])[-5:]
    return status
