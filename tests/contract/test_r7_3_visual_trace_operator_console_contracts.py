"""R7.3 contract: read-only, sanitized visual trace and operator console."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _event(**overrides: object) -> dict:
    event = {
        "schema_version": 1,
        "run_id": "run-r7-3",
        "event_id": "event-r7-3",
        "correlation_id": "corr-r7-3",
        "event_type": "run_created",
        "timestamp_utc": "2026-09-09T00:00:00+00:00",
        "message": "safe trace",
        "data": {"summary": "safe"},
    }
    event.update(overrides)
    return event


def test_console_projection_accepts_only_sanitized_correlation_bound_events():
    from tmp_agent.brain_v9.routes.trace_streaming_routes import project_trace_console_event

    assert project_trace_console_event(_event()) == _event()


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        (_event(correlation_id=""), "trace_console_correlation_id_required"),
        (_event(event_id=""), "trace_console_event_id_required"),
        (_event(data={"token": "secret-value"}), "trace_console_event_not_sanitized"),
        (_event(data={"reasoning": "private reasoning"}), "trace_console_event_not_sanitized"),
    ],
)
def test_console_projection_rejects_unsafe_or_unbound_events(event, reason):
    from tmp_agent.brain_v9.routes.trace_streaming_routes import project_trace_console_event

    with pytest.raises(ValueError, match=reason):
        project_trace_console_event(event)


def test_console_sources_have_no_sanitizer_fallback_and_existing_ingest_stays_operator_gated():
    source = (ROOT / "tmp_agent/brain_v9/routes/trace_streaming_routes.py").read_text(encoding="utf-8")
    assert "from ..tracing.trace_redactor import sanitize_event as _sanitize_event" in source
    assert "def _sanitize_event" not in source
    assert "def project_trace_console_event" in source
    assert "async def brain_agent_trace_event(" in source
    assert "_operator: StrictOperatorAccess" in source


def test_console_escapes_trace_content_and_encodes_query_identifiers():
    source = (ROOT / "tmp_agent/brain_v9/ui/agent_trace_console.html").read_text(encoding="utf-8")
    assert "innerHTML" not in source
    assert "textContent" in source
    assert "encodeURIComponent(roomId)" in source
    assert "encodeURIComponent(runId)" in source


def test_r7_3_evidence_is_no_deploy_and_preserves_privacy_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R7_3_VISUAL_TRACE_OPERATOR_CONSOLE_CONTRACTS.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item_id"] == "R7.3"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "provider_call": False,
        "canonical_local_sync": False,
    }
    assert evidence["controls"] == [
        "Read-only trace projection",
        "Correlation-bound sanitized events only",
        "No private reasoning or secret display",
        "No unaudited operator action",
    ]
