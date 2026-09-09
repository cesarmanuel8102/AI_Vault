"""R7.2 contract: deterministic, sanitized run timelines and pure provider accounting."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _event(
    event_id: str,
    timestamp: str,
    event_type: str = "run_created",
    correlation_id: str = "corr-r7-2",
    **data,
):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "run_id": "run-r7-2",
        "correlation_id": correlation_id,
        "timestamp_utc": timestamp,
        "step_id": None,
        "message": "safe event",
        "data": data,
    }


def test_timeline_projects_sanitized_correlation_bound_events_stably():
    from tmp_agent.brain_v9.tracing.timeline import project_run_timeline

    events = [
        _event("event-1", "2026-09-09T00:00:00+00:00"),
        _event("event-2", "2026-09-09T00:00:01+00:00", "run_completed", replay={"mode": "controlled", "source": "fixture", "sequence": 1}),
    ]

    timeline = project_run_timeline(events)

    assert timeline == {
        "schema_version": 1,
        "run_count": 1,
        "event_count": 2,
        "runs": [
            {
                "run_id": "run-r7-2",
                "correlation_id": "corr-r7-2",
                "event_ids": ["event-1", "event-2"],
                "event_types": ["run_created", "run_completed"],
                "started_utc": "2026-09-09T00:00:00+00:00",
                "ended_utc": "2026-09-09T00:00:01+00:00",
            }
        ],
    }


@pytest.mark.parametrize(
    ("events", "reason"),
    [
        ([_event("event-1", "2026-09-09T00:00:00+00:00", correlation_id="")], "timeline_correlation_required"),
        ([_event("event-2", "2026-09-09T00:00:01+00:00"), _event("event-1", "2026-09-09T00:00:00+00:00")], "timeline_non_monotonic"),
        ([_event("event-1", "2026-09-09T00:00:00+00:00", token="secret-value")], "timeline_event_not_sanitized"),
        ([_event("event-1", "2026-09-09T00:00:00+00:00", replay={"mode": "uncontrolled"})], "timeline_replay_metadata_invalid"),
    ],
)
def test_timeline_rejects_unsafe_or_uncontrolled_inputs(events, reason):
    from tmp_agent.brain_v9.tracing.timeline import project_run_timeline

    with pytest.raises(ValueError, match=reason):
        project_run_timeline(events)


def test_provider_health_and_cost_accounting_is_pure_and_stable():
    from tmp_agent.brain_v9.provider_health.provider_health import derive_provider_health_and_accounting

    accounting = derive_provider_health_and_accounting(
        [
            {"provider_id": "provider-b", "model": "model-b", "outcome": "timeout", "input_tokens": 5, "output_tokens": 2, "cost_microusd": 7, "error_type": "TIMEOUT"},
            {"provider_id": "provider-a", "model": "model-a", "outcome": "success", "input_tokens": 3, "output_tokens": 4, "cost_microusd": 11},
            {"provider_id": "provider-b", "model": "model-b", "outcome": "error", "input_tokens": 1, "output_tokens": 0, "cost_microusd": 2, "error_type": "RATE_LIMIT"},
        ]
    )

    assert accounting == {
        "schema_version": 1,
        "provider_count": 2,
        "input_tokens": 9,
        "output_tokens": 6,
        "cost_microusd": 20,
        "providers": [
            {"provider_id": "provider-a", "model": "model-a", "success_count": 1, "error_count": 0, "timeout_count": 0, "input_tokens": 3, "output_tokens": 4, "cost_microusd": 11, "error_taxonomy": {}},
            {"provider_id": "provider-b", "model": "model-b", "success_count": 0, "error_count": 1, "timeout_count": 1, "input_tokens": 6, "output_tokens": 2, "cost_microusd": 9, "error_taxonomy": {"RATE_LIMIT": 1, "TIMEOUT": 1}},
        ],
    }


@pytest.mark.parametrize(
    "observation",
    [
        {"provider_id": "provider-a", "model": "model-a", "outcome": "success", "input_tokens": -1, "output_tokens": 0, "cost_microusd": 0},
        {"provider_id": "provider-a", "model": "model-a", "outcome": "error", "input_tokens": 0, "output_tokens": 0, "cost_microusd": 0},
        {"provider_id": "provider-a", "model": "model-a", "outcome": "success", "input_tokens": 0, "output_tokens": 0, "cost_microusd": 0, "token": "secret-value"},
    ],
)
def test_provider_accounting_rejects_unsafe_or_incomplete_metadata(observation):
    from tmp_agent.brain_v9.provider_health.provider_health import derive_provider_health_and_accounting

    with pytest.raises(ValueError):
        derive_provider_health_and_accounting([observation])


def test_r7_2_sources_are_no_provider_call_and_evidence_is_no_deploy():
    timeline_source = (ROOT / "tmp_agent/brain_v9/tracing/timeline.py").read_text(encoding="utf-8")
    health_source = (ROOT / "tmp_agent/brain_v9/provider_health/provider_health.py").read_text(encoding="utf-8")
    assert not any(token in timeline_source + health_source for token in ("requests", "httpx", "urllib", "subprocess", "socket", "open("))

    evidence = json.loads((ROOT / "docs/roadmap/evidence/BRAIN_101_R7_2_RUN_TIMELINE_PROVIDER_HEALTH_OPERATIONAL_ACCOUNTING.json").read_text(encoding="utf-8"))
    assert evidence["roadmap_item_id"] == "R7.2"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {"worker_install": False, "scheduler_activation": False, "provider_call": False, "canonical_local_sync": False}
