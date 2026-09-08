"""R5.2 contract for durable Agent V2 run identity and lifecycle guards."""
from __future__ import annotations

import sys
import json

import pytest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R5_2_AGENT_V2_LIFECYCLE_CHECKPOINTS.json"
CLOSEOUT_EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R5_2_AGENT_V2_LIFECYCLE_CHECKPOINTS_CLOSEOUT.json"
MANIFEST = ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json"
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_r5_2_evidence_preserves_no_deploy_hard_limits():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["roadmap_item_id"] == "R5.2"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["hard_limits"] == {
        "human_final_authority": True,
        "auto_merge": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "persistent_agent_loop": "DEFERRED",
    }


def test_r5_2_closeout_binds_verified_implementation_and_activates_only_r5_3():
    closeout = json.loads(CLOSEOUT_EVIDENCE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert closeout["roadmap_item_id"] == "R5.2"
    assert closeout["parent_front_id"] == "BRAIN-101-R5-2-AGENT-V2-LIFECYCLE-CHECKPOINTS-01"
    assert closeout["parent_source_commit"] == "946f60c3ce799204d110388f6f7fe2f3b6f9a529"
    assert closeout["parent_merge_commit"] == "40e8724a5fae642c554b329ef964e2be5e653d15"
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["hard_limits"]["persistent_agent_loop"] == "DEFERRED"
    active = [item_id for item_id, item in manifest["roadmap_items"].items() if item["status"] == "AUTHORIZED_ACTIVE"]
    assert manifest["roadmap_items"]["R5.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert active == ["R5.3"]
    binding = manifest["roadmap_items"]["R5.3"]["automation"]
    assert binding["front_id"] == "BRAIN-101-R5-3-AGENT-V2-PLANNING-EVALUATION-PERSISTENCE-01"
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert set(manifest["roadmap_items"]["R5.2"]["automation"]["closeout"]["allowed_paths"]) >= {
        "tests/contract/test_r5_2_agent_v2_lifecycle_checkpoints.py",
        "tests/contract/test_brain_101_r5_r19_roadmap_decomposition.py",
        "tests/contract/operator_proxy/r4_1_roadmap_contract.test.ts",
    }


@pytest.mark.parametrize(
    "runtime_module,runtime_class",
    [
        ("brain_v9.core.agent_kernel_v2.native_runtime", "NativeAgentRuntimeV2"),
        ("brain_v9.core.agent_kernel_v2.langgraph_parity_runtime", "LangGraphParityRuntimeV2"),
    ],
)
def test_agent_v2_persists_explicit_mission_and_room_identity_in_checkpoints(
    tmp_path, runtime_module, runtime_class
):
    module = __import__(runtime_module, fromlist=[runtime_class])
    runtime = getattr(module, runtime_class)(run_root=tmp_path) if runtime_class.startswith("LangGraph") else getattr(module, runtime_class)()
    if runtime_class.startswith("Native"):
        from brain_v9.core.agent_kernel_v2 import native_runtime as native_module
        from brain_v9.core.agent_kernel_v2 import state as state_module

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(native_module, "RUN_ROOT", tmp_path)
        monkeypatch.setattr(state_module, "RUN_ROOT", tmp_path)
    else:
        monkeypatch = None
    try:
        run = runtime.create_run(
            "lifecycle identity", user_id="contract-user", mission_id="mission-r5-2", room_id="room-r5-2"
        )
        assert run["mission_id"] == "mission-r5-2"
        assert run["room_id"] == "room-r5-2"
        checkpoint = runtime.get_checkpoint(run["run_id"])
        assert checkpoint["data"]["mission_id"] == "mission-r5-2"
        assert checkpoint["data"]["room_id"] == "room-r5-2"
    finally:
        if monkeypatch:
            monkeypatch.undo()


@pytest.mark.parametrize(
    "runtime_module,runtime_class",
    [
        ("brain_v9.core.agent_kernel_v2.native_runtime", "NativeAgentRuntimeV2"),
        ("brain_v9.core.agent_kernel_v2.langgraph_parity_runtime", "LangGraphParityRuntimeV2"),
    ],
)
def test_agent_v2_rejects_resume_after_cancel_without_reopening_the_run(
    tmp_path, runtime_module, runtime_class
):
    module = __import__(runtime_module, fromlist=[runtime_class])
    runtime = getattr(module, runtime_class)(run_root=tmp_path) if runtime_class.startswith("LangGraph") else getattr(module, runtime_class)()
    if runtime_class.startswith("Native"):
        from brain_v9.core.agent_kernel_v2 import native_runtime as native_module
        from brain_v9.core.agent_kernel_v2 import state as state_module

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(native_module, "RUN_ROOT", tmp_path)
        monkeypatch.setattr(state_module, "RUN_ROOT", tmp_path)
    else:
        monkeypatch = None
    try:
        run = runtime.create_run("cancel lifecycle", user_id="contract-user")
        runtime.cancel_run(run["run_id"])
        resumed = runtime.resume_run(run["run_id"])
        assert resumed["status"] == "cancelled"
        assert "cannot transition terminal run" in resumed["error"]
    finally:
        if monkeypatch:
            monkeypatch.undo()


@pytest.mark.parametrize(
    "runtime_module,runtime_class",
    [
        ("brain_v9.core.agent_kernel_v2.native_runtime", "NativeAgentRuntimeV2"),
        ("brain_v9.core.agent_kernel_v2.langgraph_parity_runtime", "LangGraphParityRuntimeV2"),
    ],
)
def test_agent_v2_rejects_pause_after_cancel_without_reopening_the_run(
    tmp_path, runtime_module, runtime_class
):
    module = __import__(runtime_module, fromlist=[runtime_class])
    runtime = getattr(module, runtime_class)(run_root=tmp_path) if runtime_class.startswith("LangGraph") else getattr(module, runtime_class)()
    if runtime_class.startswith("Native"):
        from brain_v9.core.agent_kernel_v2 import native_runtime as native_module
        from brain_v9.core.agent_kernel_v2 import state as state_module

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(native_module, "RUN_ROOT", tmp_path)
        monkeypatch.setattr(state_module, "RUN_ROOT", tmp_path)
    else:
        monkeypatch = None
    try:
        run = runtime.create_run("cancel lifecycle", user_id="contract-user")
        runtime.cancel_run(run["run_id"])
        paused = runtime.pause_run(run["run_id"])
        assert paused["status"] == "cancelled"
        assert "cannot transition terminal run" in paused["error"]
    finally:
        if monkeypatch:
            monkeypatch.undo()
