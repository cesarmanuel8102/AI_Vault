from __future__ import annotations

import hashlib
import py_compile
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.learning.external_intel_ingestor import _append_event
from brain_v9.learning.proposal_governance import TRANSITIONS, load_registry, save_registry

STATE_ROOT = BASE_PATH / "tmp_agent" / "state" / "capabilities"
SANDBOX_ROOT = STATE_ROOT / "learning_sandboxes"
CAPABILITY_SCORECARD_PATH = STATE_ROOT / "capability_scorecard_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _proposal_lookup(registry: Dict[str, Any], proposal_id: str) -> Dict[str, Any] | None:
    return next((p for p in registry.get("proposals", []) if p.get("proposal_id") == proposal_id), None)


def _transition_inline(proposal: Dict[str, Any], target_state: str, *, actor: str, reason: str) -> Dict[str, Any]:
    current_state = proposal.get("current_state")
    allowed = TRANSITIONS.get(str(current_state), [])
    if target_state not in allowed:
        return {
            "success": False,
            "error": "invalid_transition",
            "proposal_id": proposal.get("proposal_id"),
            "current_state": current_state,
            "target_state": target_state,
            "allowed_next_states": allowed,
        }
    proposal["current_state"] = target_state
    proposal.setdefault("state_history", []).append({
        "state": target_state,
        "ts_utc": _utc_now(),
        "actor": actor,
        "reason": reason,
    })
    proposal["allowed_next_states"] = TRANSITIONS.get(target_state, [])
    return {"success": True}


def _copy_files(files_to_modify: List[str], workspace_root: Path) -> List[Dict[str, Any]]:
    copied: List[Dict[str, Any]] = []
    for file_path in files_to_modify:
        src = Path(file_path)
        try:
            src.relative_to(BASE_PATH / "tmp_agent" / "brain_v9")
            path_allowed = True
        except ValueError:
            path_allowed = False
        if not path_allowed:
            copied.append({
                "source_path": str(src),
                "status": "disallowed_path",
            })
            continue
        if not src.exists():
            copied.append({
                "source_path": str(src),
                "status": "missing",
            })
            continue
        try:
            rel = src.relative_to(BASE_PATH)
        except ValueError:
            rel = Path(src.name)
        dst = workspace_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy2(src, dst)
        copied.append({
            "source_path": str(src),
            "sandbox_path": str(dst),
            "status": "copied",
            "size_bytes": src.stat().st_size,
            "sha256": _sha256_file(src),
        })
    return copied


def _build_rollback_manifest(copied_files: List[Dict[str, Any]], run_id: str, proposal_id: str, workspace_root: Path) -> Dict[str, Any]:
    files = []
    for item in copied_files:
        if item.get("status") != "copied":
            continue
        files.append({
            "source_path": item.get("source_path"),
            "sandbox_path": item.get("sandbox_path"),
            "sha256": item.get("sha256"),
            "size_bytes": item.get("size_bytes"),
        })
    return {
        "proposal_id": proposal_id,
        "run_id": run_id,
        "created_at_utc": _utc_now(),
        "workspace_root": str(workspace_root),
        "files": files,
    }


def _compile_copied_files(copied_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    ok = True
    for item in copied_files:
        if item.get("status") != "copied":
            ok = False
            results.append({
                "source_path": item.get("source_path"),
                "sandbox_path": item.get("sandbox_path"),
                "ok": False,
                "error": "source_missing",
            })
            continue
        sandbox_path = Path(str(item["sandbox_path"]))
        try:
            py_compile.compile(str(sandbox_path), doraise=True)
            results.append({
                "source_path": item.get("source_path"),
                "sandbox_path": str(sandbox_path),
                "ok": True,
            })
        except py_compile.PyCompileError as exc:
            ok = False
            results.append({
                "source_path": item.get("source_path"),
                "sandbox_path": str(sandbox_path),
                "ok": False,
                "error": str(exc),
            })
    return {"ok": ok, "results": results}


def _capture_production_integrity(copied_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in copied_files:
        source_path = item.get("source_path")
        if not source_path:
            continue
        src = Path(str(source_path))
        row = {
            "source_path": str(src),
            "exists": src.exists(),
        }
        if src.exists():
            row["sha256"] = _sha256_file(src)
            row["size_bytes"] = src.stat().st_size
        rows.append(row)
    return rows


def execute_sandbox_run(proposal_id: str, *, actor: str, reason: str) -> Dict[str, Any]:
    registry = load_registry()
    proposal = _proposal_lookup(registry, proposal_id)
    if proposal is None:
        return {"success": False, "error": "proposal_not_found", "proposal_id": proposal_id}

    transition = _transition_inline(
        proposal,
        "sandbox_running",
        actor=actor,
        reason=reason,
    )
    if not transition.get("success"):
        return transition

    run_id = f"{proposal_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    run_dir = SANDBOX_ROOT / proposal_id / run_id
    workspace_root = run_dir / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    copied_files = _copy_files(list(proposal.get("files_to_modify") or []), workspace_root)
    before_integrity = _capture_production_integrity(copied_files)
    rollback_manifest = _build_rollback_manifest(copied_files, run_id, proposal_id, workspace_root)
    manifest = {
        "run_id": run_id,
        "proposal_id": proposal_id,
        "created_at_utc": _utc_now(),
        "actor": actor,
        "reason": reason,
        "workspace_root": str(workspace_root),
        "copied_files": copied_files,
        "files_copied_ok": bool(copied_files) and all(item.get("status") == "copied" for item in copied_files),
        "files_requested_count": len(list(proposal.get("files_to_modify") or [])),
        "files_copied_count": sum(1 for item in copied_files if item.get("status") == "copied"),
    }
    write_json(run_dir / "sandbox_manifest.json", manifest)
    write_json(run_dir / "rollback_manifest.json", rollback_manifest)
    _append_event("sandbox_run_started", {"proposal_id": proposal_id, "run_id": run_id, "actor": actor})

    compile_result = _compile_copied_files(copied_files)
    after_integrity = _capture_production_integrity(copied_files)
    before_scorecard = read_json(CAPABILITY_SCORECARD_PATH, default={}) or {}
    evaluation_summary = {
        "proposal_id": proposal_id,
        "run_id": run_id,
        "completed_at_utc": _utc_now(),
        "validation": {
            "py_compile": compile_result,
        },
        "production_integrity": {
            "before": before_integrity,
            "after": after_integrity,
        },
        "before_capability_snapshot": (before_scorecard.get("capabilities", {}) or {}).get(str(proposal.get("target_capability") or ""), {}),
        "before_proposal_snapshot": {
            "proposal_id": proposal.get("proposal_id"),
            "current_state": proposal.get("current_state"),
            "proposal_priority_score": proposal.get("proposal_priority_score"),
            "evidence_strength_score": proposal.get("evidence_strength_score"),
            "risk_score": proposal.get("risk_score"),
        },
        "before_snapshot": copied_files,
        "after_snapshot": copied_files,
    }
    write_json(run_dir / "evaluation_summary.json", evaluation_summary)

    proposal.setdefault("sandbox_runs", []).append({
        "run_id": run_id,
        "created_at_utc": manifest["created_at_utc"],
        "completed_at_utc": evaluation_summary["completed_at_utc"],
        "actor": actor,
        "reason": reason,
        "status": "evaluation_pending" if compile_result["ok"] else "rolled_back",
        "workspace_root": str(workspace_root),
        "manifest_path": str(run_dir / "sandbox_manifest.json"),
        "rollback_manifest_path": str(run_dir / "rollback_manifest.json"),
        "evaluation_summary_path": str(run_dir / "evaluation_summary.json"),
        "validation": evaluation_summary["validation"],
        "files_copied_ok": manifest["files_copied_ok"],
    })
    proposal["last_sandbox_run_id"] = run_id

    final_state = "evaluation_pending" if compile_result["ok"] else "rolled_back"
    final_reason = "sandbox_py_compile_passed" if compile_result["ok"] else "sandbox_validation_failed"
    transition = _transition_inline(
        proposal,
        final_state,
        actor=actor,
        reason=final_reason,
    )
    if not transition.get("success"):
        return transition

    updated = save_registry(registry)
    _append_event(
        "sandbox_run_completed",
        {
            "proposal_id": proposal_id,
            "run_id": run_id,
            "actor": actor,
            "result_state": final_state,
            "py_compile_ok": compile_result["ok"],
        },
    )
    _append_event(
        "proposal_state_changed",
        {
            "proposal_id": proposal_id,
            "from_state": "approved_for_sandbox",
            "to_state": "sandbox_running",
            "actor": actor,
            "reason": reason,
        },
    )
    _append_event(
        "proposal_state_changed",
        {
            "proposal_id": proposal_id,
            "from_state": "sandbox_running",
            "to_state": final_state,
            "actor": actor,
            "reason": final_reason,
        },
    )
    fresh = _proposal_lookup(updated, proposal_id) or proposal
    return {
        "success": True,
        "proposal_id": proposal_id,
        "run_id": run_id,
        "result_state": final_state,
        "proposal": fresh,
        "validation": evaluation_summary["validation"],
        "workspace_root": str(workspace_root),
    }
