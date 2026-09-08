"""R5.4 contract: Agent V2 route selection has one canonical runtime owner."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R5_4_AGENT_V2_COGNITIVE_ROUTE_CONVERGENCE.json"
CLOSEOUT_EVIDENCE = (
    ROOT
    / "docs/roadmap/evidence/BRAIN_101_R5_4_AGENT_V2_COGNITIVE_ROUTE_CONVERGENCE_CLOSEOUT.json"
)
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_chat_endpoint_does_not_select_a_parallel_route_before_runtime(monkeypatch):
    """The runtime owns route selection; HTTP only validates and renders its result."""
    from brain_v9.core.agent_kernel_v2 import api_adapter, intent_adapter

    class RuntimeStub:
        backend = "langgraph_parity"
        backend_selected = "langgraph_parity"
        backend_default = "langgraph_parity"
        backend_fallback_used = False
        backend_fallback_reason = None
        runtime_type = "RuntimeStub"
        rollback_backend = "native_runtime"

        def create_run(self, goal, mode, user_id):
            assert goal == "show Brain evidence"
            assert mode == "read_only"
            assert user_id == "contract-user"
            return {"run_id": "r5-4-run"}

        def execute_run(self, run_id):
            assert run_id == "r5-4-run"
            return {
                "run_id": run_id,
                "status": "completed",
                "final_answer": "runtime-owned route",
                "intent_route": "brain_evidence",
                "classification": "brain_evidence",
                "intent_detected": "QUERY",
                "intent_confidence": 0.95,
                "mode_requested": "read_only",
                "mode_effective": "read_only",
                "provider_metadata": {},
                "plan": [],
                "evidence_sources": [],
                "tool_results": [],
                "executed_tools": [],
                "blocked_tools": [],
            }

        def get_trace(self, run_id):
            assert run_id == "r5-4-run"
            return []

    monkeypatch.setattr(api_adapter, "get_agent_runtime_v2", lambda: RuntimeStub())

    def parallel_selector(*_args, **_kwargs):
        raise AssertionError("HTTP adapter must not select a route")

    monkeypatch.setattr(intent_adapter.AgentV2IntentAdapter, "select_route", parallel_selector)

    response = api_adapter.chat_agent(
        api_adapter.AgentChatRequest(
            message="show Brain evidence",
            mode="read_only",
            user_id="contract-user",
        )
    )

    assert response["intent_route"] == "brain_evidence"
    assert response["capability_metadata"]["intent_route"] == "brain_evidence"


def test_r5_4_evidence_binds_single_runtime_route_selection_and_no_deploy_limits():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["roadmap_item_id"] == "R5.4"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_contract"] == {
        "route_selection_owner": "agent_v2_runtime",
        "http_preplanner_route_selection": False,
        "parallel_cognitive_runtime": False,
        "governance_fastpath": False,
    }
    assert evidence["hard_limits"] == {
        "human_final_authority": True,
        "auto_merge": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "persistent_agent_loop": "DEFERRED",
    }


def test_native_runtime_uses_canonical_financial_diagnosis_route(tmp_path, monkeypatch):
    """Financial diagnostics must retain evidence/governance routing in Native V2."""
    from brain_v9.core.agent_kernel_v2 import native_runtime, state

    monkeypatch.setattr(native_runtime, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(state, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(
        native_runtime,
        "finalize_agent_run",
        lambda *_args, **_kwargs: ("safe final", {"provider_used": "test", "model_used": "test", "provider_degraded": False}),
    )
    monkeypatch.setattr(native_runtime.NativeAgentRuntimeV2, "_build_evidence_plan", lambda *_args: [])
    monkeypatch.setattr(native_runtime.NativeAgentRuntimeV2, "_run_adaptive_expansion", lambda _self, _run, plan, *_args: (plan, []))

    runtime = native_runtime.NativeAgentRuntimeV2()
    run = runtime.create_run("diagnose financial autonomy dry run safety flags")
    completed = runtime.execute_run(run["run_id"])

    assert completed["intent_route"] == "brain_evidence"
    assert completed["classification"] == "brain_evidence"


def test_native_runtime_marks_classifier_failure_as_explicit_route_fallback(tmp_path, monkeypatch):
    from brain_v9.core.agent_kernel_v2 import native_runtime, state

    monkeypatch.setattr(native_runtime, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(state, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(native_runtime, "_classify_canonical_intent", lambda _goal: (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(
        native_runtime.AgentV2IntentAdapter,
        "select_route",
        lambda *_args, **_kwargs: {"route": "brain_evidence", "intent": "QUERY", "confidence": 0.1},
    )
    monkeypatch.setattr(
        native_runtime,
        "finalize_agent_run",
        lambda *_args, **_kwargs: ("safe final", {"provider_used": "test", "model_used": "test", "provider_degraded": True}),
    )
    monkeypatch.setattr(native_runtime.NativeAgentRuntimeV2, "_build_evidence_plan", lambda *_args: [])
    monkeypatch.setattr(native_runtime.NativeAgentRuntimeV2, "_run_adaptive_expansion", lambda _self, _run, plan, *_args: (plan, []))

    runtime = native_runtime.NativeAgentRuntimeV2()
    run = runtime.create_run("explain the Brain route fallback")
    completed = runtime.execute_run(run["run_id"])

    assert completed["intent_route"] == "brain_evidence"
    assert completed["intent_route_source"] == "AgentV2IntentAdapter.degraded_fallback"
    assert completed["intent_route_fallback_used"] is True


def test_sanitizer_namespace_import_does_not_eagerly_load_the_route_classifier():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from tmp_agent.brain_v9.core.agent_kernel_v2.response_normalizer import sanitize_user_facing_content; print(bool(sanitize_user_facing_content))",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_r5_4_closeout_binds_verified_evidence_and_preserves_its_r6_1_successor():
    """R5.4's immutable closeout must remain valid after later roadmap transitions."""
    closeout = json.loads(CLOSEOUT_EVIDENCE.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))

    assert closeout["roadmap_item_id"] == "R5.4"
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["parent_merge_commit"] == "5acb2363420a5e62ca77eeadf2dea91c85993e66"
    assert closeout["next_item"] == {
        "roadmap_item_id": "R6.1",
        "front_id": "BRAIN-101-R6-1-MEMORY-SERVICE-OWNERSHIP-INTEGRITY-BASELINE-01",
        "executor": "codex_control_plane",
        "deployment_mode": "NO_DEPLOY",
        "expected_base_sha_source": (
            "sequenceRoadmap resolves the exact live canonical integration-branch head "
            "at governed dispatch"
        ),
        "jit_binding_completed": True,
    }
    assert manifest["roadmap_items"]["R5.4"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    automation = manifest["roadmap_items"]["R6.1"]["automation"]
    assert automation["jit_binding_completed"] is True
    assert automation["dispatchable"] is True
    assert automation["front_id"] == closeout["next_item"]["front_id"]
    assert automation["expected_base_sha_source"] == closeout["next_item"]["expected_base_sha_source"]
    assert manifest["roadmap_items"]["R6.1"]["hard_limits"] == closeout["hard_limits"]
