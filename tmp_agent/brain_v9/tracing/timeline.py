"""Pure projections of already-sanitized, correlation-bound trace events."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from ..core.agent_kernel_v2.schemas import TRACE_EVENT_TAXONOMY
from .trace_redactor import sanitize_event


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timeline_timestamp_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timeline_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("timeline_timestamp_invalid")
    return parsed


def _validate_event(event: Mapping[str, Any], seen_ids: set[str], prior: datetime | None) -> datetime:
    if not isinstance(event.get("run_id"), str) or not event["run_id"].strip():
        raise ValueError("timeline_run_id_required")
    if not isinstance(event.get("correlation_id"), str) or not event["correlation_id"].strip():
        raise ValueError("timeline_correlation_required")
    if not isinstance(event.get("event_id"), str) or not event["event_id"].strip() or event["event_id"] in seen_ids:
        raise ValueError("timeline_event_id_invalid")
    if event.get("event_type") not in TRACE_EVENT_TAXONOMY:
        raise ValueError("timeline_event_type_invalid")
    if not isinstance(event.get("data", {}), dict):
        raise ValueError("timeline_event_data_invalid")
    if sanitize_event(dict(event)) != dict(event):
        raise ValueError("timeline_event_not_sanitized")
    replay = event["data"].get("replay")
    if replay is not None and (
        not isinstance(replay, dict)
        or set(replay) != {"mode", "source", "sequence"}
        or replay["mode"] != "controlled"
        or not isinstance(replay["source"], str)
        or not replay["source"].strip()
        or not isinstance(replay["sequence"], int)
        or replay["sequence"] < 0
    ):
        raise ValueError("timeline_replay_metadata_invalid")
    current = _timestamp(event.get("timestamp_utc"))
    if prior is not None and current < prior:
        raise ValueError("timeline_non_monotonic")
    seen_ids.add(event["event_id"])
    return current


def project_run_timeline(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a stable, no-I/O timeline summary from safe supplied trace events."""
    runs: dict[tuple[str, str], dict[str, Any]] = {}
    seen_ids: set[str] = set()
    prior: datetime | None = None
    count = 0
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("timeline_event_invalid")
        current = _validate_event(event, seen_ids, prior)
        prior = current
        key = (event["run_id"], event["correlation_id"])
        record = runs.setdefault(
            key,
            {
                "run_id": event["run_id"],
                "correlation_id": event["correlation_id"],
                "event_ids": [],
                "event_types": [],
                "started_utc": event["timestamp_utc"],
                "ended_utc": event["timestamp_utc"],
            },
        )
        record["event_ids"].append(event["event_id"])
        record["event_types"].append(event["event_type"])
        record["ended_utc"] = event["timestamp_utc"]
        count += 1
    ordered = [runs[key] for key in sorted(runs)]
    return {"schema_version": 1, "run_count": len(ordered), "event_count": count, "runs": ordered}
