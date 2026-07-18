#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("agent_worker_v157_state_event", MODULE)
assert spec and spec.loader
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

FRONT = "PILOT-KIMI-CODEX-20260716-091529"


def test_state_schema_version_injected() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "state" / "issue-5.json"
        original = {
            "issue_number": 5,
            "front": FRONT,
            "spec": {"front_id": FRONT},
            "status": "WAITING_GITHUB",
            "updated_utc": worker.utc(),
        }
        worker.save_json(path, original)
        loaded = worker.load_json(path)
        assert loaded.get("state_schema_version") == worker.STATE_SCHEMA_VERSION
        assert loaded.get("worker_version") == worker.WORKER_VERSION
        assert worker.validate_state_json(loaded) == []


def test_state_validation_rejects_unknown_and_missing() -> None:
    missing_status = {"issue_number": 5, "updated_utc": worker.utc()}
    assert any("missing" in e.lower() for e in worker.validate_state_json(missing_status))
    unknown = {
        "issue_number": 5,
        "status": "WAITING_GITHUB",
        "updated_utc": worker.utc(),
        "extra_field": True,
    }
    assert any("unknown" in e.lower() for e in worker.validate_state_json(unknown))


def test_event_contract_enforces_required_fields() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = {"install_root": td}
        worker.event(cfg, "executor_started", front=FRONT, cycle=1, command_identity="opencode", model="m")
        try:
            worker.event(cfg, "executor_started", front=FRONT, cycle=1)
        except RuntimeError as exc:
            assert "EVENT_CONTRACT_VIOLATION" in str(exc)
        else:
            raise AssertionError("expected event contract violation")
        lines = (Path(td) / "reports" / "worker-events.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        evt = json.loads(lines[0])
        assert evt["kind"] == "executor_started"
        assert {"front", "cycle", "command_identity", "model"}.issubset(evt)


def test_worker_started_event_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = {"install_root": td}
        worker.event(cfg, "worker_started", once=True, worker_version=worker.WORKER_VERSION, worker_sha256="abc")
        lines = (Path(td) / "reports" / "worker-events.jsonl").read_text(encoding="utf-8").splitlines()
        evt = json.loads(lines[0])
        assert evt["kind"] == "worker_started"
        assert evt["worker_version"] == worker.WORKER_VERSION


print(json.dumps({"status": "PASS", "tests": ["state_schema_version_injected", "state_validation", "event_contract", "worker_started_event"]}, indent=2))
