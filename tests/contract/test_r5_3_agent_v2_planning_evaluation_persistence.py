"""R5.3 contract for durable, safe Agent V2 execution evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R5_3_AGENT_V2_PLANNING_EVALUATION_PERSISTENCE.json"
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_r5_3_evidence_declares_the_persistent_projection_and_no_deploy_limits():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["roadmap_item_id"] == "R5.3"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_contract"]["execution_evidence_checkpointed"] is True
    assert evidence["runtime_contract"]["sensitive_fields_excluded"] == [
        "goal",
        "final_answer",
        "tool_inputs",
        "tool_outputs",
    ]
    assert evidence["hard_limits"] == {
        "human_final_authority": True,
        "auto_merge": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "persistent_agent_loop": "DEFERRED",
    }


@pytest.mark.parametrize(
    "runtime_module,runtime_class",
    [
        ("brain_v9.core.agent_kernel_v2.native_runtime", "NativeAgentRuntimeV2"),
        ("brain_v9.core.agent_kernel_v2.langgraph_parity_runtime", "LangGraphParityRuntimeV2"),
    ],
)
def test_r5_3_persists_a_normalized_execution_evidence_projection(
    tmp_path, runtime_module, runtime_class
):
    module = __import__(runtime_module, fromlist=[runtime_class])
    runtime = (
        getattr(module, runtime_class)(run_root=tmp_path)
        if runtime_class.startswith("LangGraph")
        else getattr(module, runtime_class)()
    )
    monkeypatch = pytest.MonkeyPatch()
    if runtime_class.startswith("Native"):
        from brain_v9.core.agent_kernel_v2 import native_runtime as native_module
        from brain_v9.core.agent_kernel_v2 import state as state_module

        monkeypatch.setattr(native_module, "RUN_ROOT", tmp_path)
        monkeypatch.setattr(state_module, "RUN_ROOT", tmp_path)
    try:
        run = runtime.create_run(
            "sensitive goal must not enter execution evidence",
            user_id="contract-user",
            mission_id="mission-r5-3",
            room_id="room-r5-3",
        )
        run["plan"] = [
            {
                "step_id": "safe-read",
                "tool_name": "repo_status_read",
                "status": "completed",
                "input": {"secret": "must-not-persist"},
                "output": {"raw": "must-not-persist"},
            }
        ]
        run["tool_results"] = [{"tool_name": "repo_status_read", "ok": True, "result": {"raw": "must-not-persist"}}]
        run["evaluator_source"] = "deterministic_parity_evaluator"
        run["evaluator_parity_mode"] = "deterministic"
        run["evaluator_result"] = {"answered_user_intent": True, "governance_compliant": True}
        run["provider_metadata"] = {"provider_used": "structured", "model_used": "test-model", "provider_degraded": False}
        run["final_answer"] = "must-not-persist"
        run["status"] = "completed"
        if runtime_class.startswith("LangGraph"):
            runtime._save_run_json(run)
        else:
            runtime._save_run(run)

        evidence = runtime.get_checkpoint(run["run_id"])["data"]["execution_evidence"]
        assert evidence == {
            "schema_version": 1,
            "mission_id": "mission-r5-3",
            "run_id": run["run_id"],
            "room_id": "room-r5-3",
            "plan": {"step_count": 1, "tool_names": ["repo_status_read"]},
            "tools": {"result_count": 1, "completed": 1, "failed": 0, "blocked": 0, "tool_names": ["repo_status_read"]},
            "evaluator": {"source": "deterministic_parity_evaluator", "mode": "deterministic", "passed": True},
            "finalizer": {"provider": "structured", "model": "test-model", "degraded": False},
        }
        assert "must-not-persist" not in str(evidence)
    finally:
        monkeypatch.undo()
