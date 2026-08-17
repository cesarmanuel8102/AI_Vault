"""BRAIN-101-R3-2 Agent V2 evaluator contract tests.

Front: BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
Surface: C4 Evaluator contract

Deterministic contract tests for evaluator criteria and result schema.  The
only production evaluator implementation currently present is inside
LangGraphParityRuntimeV2._evaluator_node.  The tests therefore construct a
synthetic run state, invoke the evaluator directly, and verify the documented
evaluation criteria.  No server starts, no HTTP calls, no real writes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


# ---------------------------------------------------------------------------
# 1. Evaluator criteria key inventory
# ---------------------------------------------------------------------------

def test_evaluator_criteria_inventory():
    """The R3 C4 contract requires these evaluation criteria."""
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("inventory run", "brain_evidence")
    rt._evaluator_node(state)
    ev = state.get("evaluator_result", {})
    required = {
        "answered_user_intent",
        "route_correct",
        "classification_correct",
        "tool_use_adequate",
        "evidence_adequate",
        "memory_retrieval_adequate",
        "governance_compliant",
        "answer_complete",
        "finalizer_input_complete",
        "native_helper_parity_score",
        "full_parity_score",
    }
    assert required.issubset(set(ev.keys()))
    for key in required:
        assert isinstance(ev[key], (bool, int)), f"{key} has unexpected type {type(ev[key])}"


# ---------------------------------------------------------------------------
# 2. Evaluator on direct-assistant route
# ---------------------------------------------------------------------------

def test_evaluator_marks_direct_assistant_as_tool_adequate_without_tools():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("hi", "direct_assistant")
    rt._evaluator_node(state)
    ev = state["evaluator_result"]
    assert ev["route_correct"] is True
    assert ev["tool_use_adequate"] is True
    assert ev["evidence_adequate"] is True
    assert ev["answer_complete"] is True


# ---------------------------------------------------------------------------
# 3. Evaluator on brain-evidence route requires tools and evidence
# ---------------------------------------------------------------------------

def test_evaluator_requires_tools_for_brain_evidence_route():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("How is memory structured?", "brain_evidence")
    state["plan"] = []
    state["evidence_sources"] = []
    rt._evaluator_node(state)
    ev = state["evaluator_result"]
    assert ev["route_correct"] is True
    assert ev["tool_use_adequate"] is False
    assert ev["evidence_adequate"] is False


def test_evaluator_passes_brain_evidence_with_tools_and_sources():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("How is memory structured?", "brain_evidence")
    state["plan"] = [
        {
            "step_id": "ev_repo_status",
            "kind": "tool",
            "title": "Read repository status",
            "status": "completed",
            "tool_name": "repo_status_read",
            "input": {},
        },
    ]
    state["evidence_sources"] = [{"type": "front_brain", "tools": ["repo_status_read"]}]
    rt._evaluator_node(state)
    ev = state["evaluator_result"]
    assert ev["tool_use_adequate"] is True
    assert ev["evidence_adequate"] is True


# ---------------------------------------------------------------------------
# 4. Governance compliance contract
# ---------------------------------------------------------------------------

def test_evaluator_marks_governance_compliant_when_no_escalation():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("repo status", "brain_evidence")
    state["mode_escalation_required"] = False
    state["approval_required"] = False
    rt._evaluator_node(state)
    ev = state["evaluator_result"]
    assert ev["governance_compliant"] is True


def test_evaluator_marks_governance_noncompliant_for_unapproved_escalation():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("patch the code", "operational_agent")
    state["mode_escalation_required"] = True
    state["approval_required"] = False
    rt._evaluator_node(state)
    ev = state["evaluator_result"]
    assert ev["governance_compliant"] is False


# ---------------------------------------------------------------------------
# 5. Evaluator result sources
# ---------------------------------------------------------------------------

def test_evaluator_records_source_and_mode():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("repo status", "brain_evidence")
    rt._evaluator_node(state)
    assert state["evaluator_source"] == "deterministic_parity_evaluator"
    assert state["evaluator_parity_mode"] == "deterministic"


def test_injected_evaluator_is_used_when_supplied():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    def custom_eval(_state):
        return {"custom": True}

    rt = LangGraphParityRuntimeV2(
        run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval",
        evaluator_fn=custom_eval,
    )
    state = _minimal_completed_state("repo status", "brain_evidence")
    rt._evaluator_node(state)
    assert state["evaluator_source"] == "injected_evaluator"
    assert state["evaluator_parity_mode"] == "injected"
    assert state["evaluator_result"]["custom"] is True


# ---------------------------------------------------------------------------
# 6. Repair/replan node contract
# ---------------------------------------------------------------------------

def test_repair_or_replan_node_detects_failed_evaluation():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("How is memory structured?", "brain_evidence")
    state["plan"] = []
    state["evidence_sources"] = []
    rt._evaluator_node(state)
    rt._repair_or_replan_node(state)
    assert state["repair_needed"] is True
    assert state["node_path"][-1] == "repair_or_replan"


def test_repair_or_replan_node_marks_success_when_all_criteria_pass():
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=ROOT / "tmp_agent" / "agent_kernel_v2" / "runs_parity_test_eval")
    state = _minimal_completed_state("hi", "direct_assistant")
    # Ensure the evaluator_result is fully truthy; full_parity_score of 10 is
    # not enough because native_helper_parity_score is 0.  Supply a minimal
    # parity score and mark the run as deeply parity.
    state["native_helpers_used"] = [
        "context_assembler.isolated_run_root_equivalent",
        "NLIntentClassifierV2.classify_intent",
        "AgentV2IntentAdapter.get_evidence_sources",
        "planner.build_plan",
    ]
    state["context_assembler_full_parity"] = True
    state["tool_gateway_parity_improved"] = True
    state["memory_gateway_read_only"] = True
    state["finalizer_input_schema_complete"] = True
    state["evaluator_parity_mode"] = "deterministic_parity_evaluator"
    state["backend_flag_ready"] = True
    state["graph_stream_supported"] = True
    rt._evaluator_node(state)
    rt._repair_or_replan_node(state)
    assert state["repair_needed"] is False


# ---------------------------------------------------------------------------
# 7. Helpers
# ---------------------------------------------------------------------------

def _minimal_completed_state(message: str, route: str) -> dict:
    return {
        "run_id": f"eval_contract_{route}_{hash(message) & 0xFFFFFFFF}",
        "message": message,
        "goal": message,
        "mode_requested": "read_only",
        "mode_effective": "read_only",
        "user_id": "contract_test",
        "status": "completed",
        "final_answer": "Contract test answer.",
        "intent_route": route,
        "classification": route,
        "plan": [],
        "evidence_sources": [],
        "tool_results": [],
        "memory_hits": [],
        "blocked_tools": [],
        "mode_escalation_required": False,
        "approval_required": False,
        "finalizer_input_schema_complete": True,
        "native_helpers_used": [],
        "node_path": [],
    }


# ---------------------------------------------------------------------------
# 8. Safety: evaluator module does not contain forbidden runtime execution tokens
# ---------------------------------------------------------------------------

def test_evaluator_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem(", "requ" + "ests."]
    assert not any(token in src for token in forbidden)


# ---------------------------------------------------------------------------
# Runner for direct invocation
# ---------------------------------------------------------------------------

_TESTS = [
    test_evaluator_criteria_inventory,
    test_evaluator_marks_direct_assistant_as_tool_adequate_without_tools,
    test_evaluator_requires_tools_for_brain_evidence_route,
    test_evaluator_passes_brain_evidence_with_tools_and_sources,
    test_evaluator_marks_governance_compliant_when_no_escalation,
    test_evaluator_marks_governance_noncompliant_for_unapproved_escalation,
    test_evaluator_records_source_and_mode,
    test_injected_evaluator_is_used_when_supplied,
    test_repair_or_replan_node_detects_failed_evaluation,
    test_repair_or_replan_node_marks_success_when_all_criteria_pass,
    test_evaluator_source_does_not_import_server_starters,
]


if __name__ == "__main__":
    passed = failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
