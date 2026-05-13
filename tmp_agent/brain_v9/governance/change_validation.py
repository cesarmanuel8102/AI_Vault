"""
Brain V9 — Canonical change-validation runtime summary.

Operationalizes the 4-stage pipeline from the master document so it exists as
real code and a canonical artifact, not only as narrative guidance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.brain.change_control import build_change_scorecard, get_change_scorecard_latest
from brain_v9.config import STATE_PATH
from brain_v9.core.state_io import read_json, write_json


CHANGE_VALIDATION_STATUS_PATH = STATE_PATH / "change_validation_status_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stage_state(entry: Dict[str, Any], name: str) -> str:
    return str((((entry.get("stages") or {}).get(name) or {}).get("state")) or "pending").lower()


def _pipeline_state(entry: Dict[str, Any]) -> str:
    states = [
        _stage_state(entry, "static_check"),
        _stage_state(entry, "unit_test"),
        _stage_state(entry, "runtime_check"),
        _stage_state(entry, "metric_check"),
    ]
    if any(state == "failed" for state in states):
        return "failed"
    if all(state == "passed" for state in states):
        return "passed"
    if any(state in {"pending", "not_implemented"} for state in states):
        return "pending"
    return "pending"


def _compact_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "change_id": entry.get("change_id"),
        "timestamp": entry.get("timestamp"),
        "result": entry.get("result"),
        "rollback_executed": bool(entry.get("rollback_executed")),
        "stages": entry.get("stages") or {},
        "pipeline_state": _pipeline_state(entry),
    }


def build_change_validation_status(refresh_scorecard: bool = False) -> Dict[str, Any]:
    scorecard = build_change_scorecard() if refresh_scorecard else get_change_scorecard_latest()
    entries = [_compact_entry(entry) for entry in (scorecard.get("entries") or [])]
    last_entry = entries[-1] if entries else {}
    passed_count = sum(1 for entry in entries if entry.get("pipeline_state") == "passed")
    failed_count = sum(1 for entry in entries if entry.get("pipeline_state") == "failed")
    pending_count = sum(1 for entry in entries if entry.get("pipeline_state") == "pending")
    payload = {
        "schema_version": "change_validation_status_v1",
        "generated_utc": _utc_now(),
        "summary": {
            "total_validations": len(entries),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "last_run_utc": last_entry.get("timestamp"),
            "last_pipeline_state": last_entry.get("pipeline_state", "pending"),
            "apply_gate_ready": last_entry.get("pipeline_state") == "passed",
        },
        "last_validation": last_entry,
        "recent_validations": entries[-10:],
    }
    write_json(CHANGE_VALIDATION_STATUS_PATH, payload)
    return payload


def read_change_validation_status() -> Dict[str, Any]:
    payload = read_json(CHANGE_VALIDATION_STATUS_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_change_validation_status()
