from __future__ import annotations

import json

import brain_v9.brain.control_layer as cl
from brain_v9.core.state_io import read_json


def test_build_control_layer_status_active(monkeypatch, tmp_path):
    status_path = tmp_path / "control_layer_status.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(cl, "CONTROL_LAYER_STATUS_PATH", status_path)
    monkeypatch.setattr(cl, "AGENT_EVENTS_LOG_PATH", events_path)
    monkeypatch.setattr(
        cl,
        "get_change_scorecard_latest",
        lambda: {"summary": {"critical_recent_failures": 0}},
    )
    monkeypatch.setattr(cl, "read_utility_state", lambda: {"u_score": -0.2, "verdict": "no_promote", "blockers": []})

    payload = cl.build_control_layer_status()

    assert payload["mode"] == "ACTIVE"
    assert payload["execution_allowed"] is True
    stored = read_json(status_path, {})
    assert stored["mode"] == "ACTIVE"


def test_freeze_and_unfreeze_control_layer(monkeypatch, tmp_path):
    status_path = tmp_path / "control_layer_status.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(cl, "CONTROL_LAYER_STATUS_PATH", status_path)
    monkeypatch.setattr(cl, "AGENT_EVENTS_LOG_PATH", events_path)
    monkeypatch.setattr(
        cl,
        "build_change_scorecard",
        lambda: {"summary": {"critical_recent_failures": 0}},
    )
    monkeypatch.setattr(
        cl,
        "get_change_scorecard_latest",
        lambda: {"summary": {"critical_recent_failures": 0}},
    )
    monkeypatch.setattr(cl, "read_utility_state", lambda: {"u_score": -0.2, "verdict": "no_promote", "blockers": []})

    frozen = cl.freeze_control_layer("manual_test", source="test")
    assert frozen["mode"] == "FROZEN"
    assert frozen["reason"] == "manual_test"

    unfrozen = cl.unfreeze_control_layer("resume_test", source="test")
    assert unfrozen["mode"] == "ACTIVE"

    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["event"] == "control_layer_frozen"
    assert second["event"] == "control_layer_unfrozen"


def test_build_control_layer_status_freezes_on_critical_failures(monkeypatch, tmp_path):
    status_path = tmp_path / "control_layer_status.json"
    events_path = tmp_path / "agent_events.ndjson"
    monkeypatch.setattr(cl, "CONTROL_LAYER_STATUS_PATH", status_path)
    monkeypatch.setattr(cl, "AGENT_EVENTS_LOG_PATH", events_path)
    monkeypatch.setattr(
        cl,
        "get_change_scorecard_latest",
        lambda: {"summary": {"critical_recent_failures": 3}},
    )
    monkeypatch.setattr(cl, "read_utility_state", lambda: {"u_score": -0.2, "verdict": "no_promote", "blockers": []})

    payload = cl.build_control_layer_status()

    assert payload["mode"] == "FROZEN"
    assert payload["reason"] == "critical_recent_change_failures"
