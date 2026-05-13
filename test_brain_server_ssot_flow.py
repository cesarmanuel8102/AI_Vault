import importlib.util
import pytest
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(r"C:\AI_VAULT")
BRAIN_SERVER_PATH = ROOT / "00_identity" / "brain_server.py"
TMP_ROOMS_ROOT = ROOT / "tmp_agent" / "state" / "rooms"


def _load_brain_server_module():
    sys.path.insert(0, str(BRAIN_SERVER_PATH.parent))
    spec = importlib.util.spec_from_file_location("brain_server_test_mod", str(BRAIN_SERVER_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DummyReq:
    def __init__(self, room_id: str):
        self.headers = {"x-room-id": room_id}


def test_plan_run_once_write_apply_runtime_snapshot_complete():
    mod = _load_brain_server_module()
    room_id = f"pytest_ssot_{uuid.uuid4().hex[:10]}"
    room_dir = TMP_ROOMS_ROOT / room_id
    plan_path = room_dir / "plan.json"
    snapshot_path = room_dir / "runtime_snapshot.json"

    if plan_path.exists():
        plan_path.unlink()
    if snapshot_path.exists():
        snapshot_path.unlink()

    req = DummyReq(room_id)
    payload = {
        "room_id": room_id,
        "steps": [
            {
                "id": "W1",
                "status": "todo",
                "tool_name": "append_file",
                "tool_args": {"path": "smoke.txt", "content": "hello\n"},
            },
            {
                "id": "R1",
                "status": "todo",
                "tool_name": "runtime_snapshot_set",
                "tool_args": {"path": "state.json", "value": {"ok": True}},
            },
        ],
    }

    created = mod.agent_plan_create_ssot(req, payload)
    assert created["ok"] is True
    assert plan_path.exists()

    first = mod.agent_run_once_ssot(req, mod.AgentRunOnceRequest(room_id=room_id))
    assert first["action"] == "propose_write_step"
    approve = first["approve_token"]
    assert isinstance(approve, str) and approve.startswith("APPLY_")

    second = mod.agent_run_once_ssot(req, mod.AgentRunOnceRequest(room_id=room_id, approve_token=approve))
    assert second["action"] == "apply_step"

    third = mod.agent_run_once_ssot(req, mod.AgentRunOnceRequest(room_id=room_id))
    assert third["action"] == "propose_step"

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "complete"

    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["W1"]["status"] == "done"
    assert "proposal_id" not in steps["W1"]
    assert "required_approve" not in steps["W1"]
    assert steps["R1"]["status"] == "done"
    assert steps["R1"]["result"]["ok"] is True

    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["room_id"] == room_id
    assert snapshot["kv"]["state.json"]["ok"] is True
    assert snapshot["kv"]["state.json"]["room_id"] == room_id
    assert isinstance(snapshot["kv"]["state.json"]["ts"], str)


def test_run_once_invalid_approve_token_keeps_proposed_step():
    mod = _load_brain_server_module()
    room_id = f"pytest_ssot_invalid_{uuid.uuid4().hex[:10]}"
    room_dir = TMP_ROOMS_ROOT / room_id
    plan_path = room_dir / "plan.json"

    if plan_path.exists():
        plan_path.unlink()

    req = DummyReq(room_id)
    payload = {
        "room_id": room_id,
        "steps": [
            {
                "id": "W1",
                "status": "todo",
                "tool_name": "append_file",
                "tool_args": {"path": "smoke.txt", "content": "hello\n"},
            },
        ],
    }

    created = mod.agent_plan_create_ssot(req, payload)
    assert created["ok"] is True

    proposed = mod.agent_run_once_ssot(req, mod.AgentRunOnceRequest(room_id=room_id))
    assert proposed["action"] == "propose_write_step"

    invalid = mod.agent_run_once_ssot(
        req,
        mod.AgentRunOnceRequest(room_id=room_id, approve_token="APPLY_not_the_real_pid"),
    )
    assert invalid["action"] == "noop_no_matching_proposed_step"

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "active"
    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["W1"]["status"] == "proposed"
    assert steps["W1"]["required_approve"] == proposed["approve_token"]
    assert steps["W1"]["proposal_id"] == proposed["approve_token"].replace("APPLY_", "", 1)


def test_run_once_malformed_approve_token_raises_400():
    mod = _load_brain_server_module()
    room_id = f"pytest_ssot_badtoken_{uuid.uuid4().hex[:10]}"
    room_dir = TMP_ROOMS_ROOT / room_id
    plan_path = room_dir / "plan.json"

    if plan_path.exists():
        plan_path.unlink()

    req = DummyReq(room_id)
    payload = {
        "room_id": room_id,
        "steps": [
            {
                "id": "W1",
                "status": "todo",
                "tool_name": "append_file",
                "tool_args": {"path": "smoke.txt", "content": "hello\n"},
            },
        ],
    }

    created = mod.agent_plan_create_ssot(req, payload)
    assert created["ok"] is True

    proposed = mod.agent_run_once_ssot(req, mod.AgentRunOnceRequest(room_id=room_id))
    assert proposed["action"] == "propose_write_step"

    before = json.loads(plan_path.read_text(encoding="utf-8"))
    with pytest.raises(mod.HTTPException) as exc:
        mod.agent_run_once_ssot(
            req,
            mod.AgentRunOnceRequest(room_id=room_id, approve_token="bad_token"),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "approve_token must be APPLY_<proposal_id>"

    after = json.loads(plan_path.read_text(encoding="utf-8"))
    assert after == before
    steps = {step["id"]: step for step in after["steps"]}
    assert steps["W1"]["status"] == "proposed"
    assert steps["W1"]["required_approve"] == proposed["approve_token"]
