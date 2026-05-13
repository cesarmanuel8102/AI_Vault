"""
Brain V9 — Canonical Change Control Layer

Builds a before/after comparator summary over the governed self-improvement
pipeline and persists it as the canonical artifact required by the master doc.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.brain.self_improvement import (
    CHANGES_ROOT,
    get_self_improvement_ledger,
    _is_metric_degraded,
)
from brain_v9.config import STATE_PATH
from brain_v9.core.state_io import read_json, write_json


CHANGE_SCORECARD_PATH = STATE_PATH / "change_scorecard.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_change_metadata(change_id: str) -> Dict[str, Any]:
    meta_path = CHANGES_ROOT / change_id / "metadata.json"
    return read_json(meta_path, {}) if meta_path.exists() else {}


def _read_change_result(change_id: str) -> Dict[str, Any]:
    result_path = CHANGES_ROOT / change_id / "promotion_result.json"
    return read_json(result_path, {}) if result_path.exists() else {}


def _static_stage(metadata: Dict[str, Any]) -> Dict[str, Any]:
    validation = metadata.get("validation") or {}
    checks = validation.get("checks") or {}
    syntax = checks.get("syntax") or {}
    imports = checks.get("imports") or {}
    if not validation:
        return {"state": "pending"}
    if syntax.get("passed") is False or imports.get("passed") is False:
        return {"state": "failed"}
    if syntax.get("passed") or imports.get("passed"):
        return {"state": "passed"}
    return {"state": "pending"}


def _unit_stage(metadata: Dict[str, Any]) -> Dict[str, Any]:
    validation = metadata.get("validation") or {}
    checks = validation.get("checks") or {}
    unit = checks.get("unit_tests") or {}
    if unit:
        if unit.get("passed") is False:
            return {"state": "failed", "targets": unit.get("targets", [])}
        if unit.get("passed") is True:
            return {"state": "passed", "targets": unit.get("targets", [])}
    return {"state": "not_implemented"}


def _runtime_stage(result: Dict[str, Any]) -> Dict[str, Any]:
    endpoints = result.get("endpoint_results") or []
    if not result:
        return {"state": "pending", "failed_endpoints": []}
    failed = [row.get("endpoint") for row in endpoints if isinstance(row, dict) and not row.get("ok")]
    if failed:
        return {"state": "failed", "failed_endpoints": failed}
    if result.get("health_status") == "healthy":
        return {"state": "passed", "failed_endpoints": []}
    return {"state": "pending", "failed_endpoints": []}


def _metric_stage(metadata: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    before = metadata.get("impact_before")
    after = metadata.get("impact_after") or result.get("impact_after")
    if not before or not after:
        return {"state": "pending", "degraded": False}
    degraded = _is_metric_degraded(before, after)
    return {
        "state": "failed" if degraded else "passed",
        "degraded": degraded,
        "delta": metadata.get("impact_delta") or {},
    }


def _result_state(entry: Dict[str, Any], metadata: Dict[str, Any], result: Dict[str, Any]) -> str:
    status = (entry.get("status") or metadata.get("status") or "").lower()
    if status in {"promoted", "stable"}:
        return "promoted"
    if status in {"rolled_back", "promotion_failed"}:
        return "reverted"
    if status in {"promotion_scheduled", "validated", "staged"}:
        return "pending"
    return status or "pending"


def _score_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    change_id = entry.get("change_id", "")
    metadata = _read_change_metadata(change_id)
    result = _read_change_result(change_id)
    static_check = _static_stage(metadata)
    unit_check = _unit_stage(metadata)
    runtime_check = _runtime_stage(result)
    metric_check = _metric_stage(metadata, result)
    return {
        "change_id": change_id,
        "timestamp": entry.get("timestamp"),
        "objective": entry.get("objective"),
        "files": entry.get("files", []),
        "status": entry.get("status"),
        "result": _result_state(entry, metadata, result),
        "rollback_executed": bool(entry.get("rollback") or metadata.get("rollback")),
        "metrics_before": metadata.get("impact_before") or entry.get("impact_before") or {},
        "metrics_after": metadata.get("impact_after") or entry.get("impact_after") or result.get("impact_after") or {},
        "stages": {
            "static_check": static_check,
            "unit_test": unit_check,
            "runtime_check": runtime_check,
            "metric_check": metric_check,
        },
    }


def build_change_scorecard() -> Dict[str, Any]:
    ledger = get_self_improvement_ledger()
    entries = [_score_entry(entry) for entry in ledger.get("entries", [])]
    promoted = sum(1 for entry in entries if entry.get("result") == "promoted")
    reverted = sum(1 for entry in entries if entry.get("result") == "reverted")
    pending = sum(1 for entry in entries if entry.get("result") == "pending")
    rollback_count = sum(1 for entry in entries if entry.get("rollback_executed"))
    metric_degraded_count = sum(
        1 for entry in entries
        if ((entry.get("stages") or {}).get("metric_check") or {}).get("degraded")
    )
    recent = entries[-3:]
    critical_recent_failures = sum(
        1 for entry in recent if entry.get("result") == "reverted"
    )
    payload = {
        "schema_version": "change_scorecard_v1",
        "generated_utc": _utc_now(),
        "summary": {
            "total_changes": len(entries),
            "promoted_count": promoted,
            "reverted_count": reverted,
            "pending_count": pending,
            "rollback_count": rollback_count,
            "metric_degraded_count": metric_degraded_count,
            "critical_recent_failures": critical_recent_failures,
            "frozen_recommended": critical_recent_failures >= 3,
        },
        "entries": entries[-50:],
    }
    write_json(CHANGE_SCORECARD_PATH, payload)
    return payload


def get_change_scorecard_latest() -> Dict[str, Any]:
    payload = read_json(CHANGE_SCORECARD_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_change_scorecard()
