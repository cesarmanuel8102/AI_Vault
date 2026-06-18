#!/usr/bin/env python3
"""
Smoke test for conversation context assembler.
"""
import sys, json, tempfile
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, r"C:\AI_VAULT_CANONICAL\tmp_agent")

import brain_v9.core.agent_kernel_v2.context_assembler as ca
from brain_v9.core.agent_kernel_v2.context_assembler import assemble_recent_context, _is_follow_up, _has_generic_override


def test_follow_up_detection():
    assert _is_follow_up("y cómo lo solucionas?")
    assert _is_follow_up("continúa con eso")
    assert _is_follow_up("haz lo mismo")
    assert _is_follow_up("expand the search")
    assert not _is_follow_up("dame una receta")
    print("PASS: follow-up detection")


def test_generic_override():
    assert _has_generic_override("dame una receta de arroz con pollo")
    assert not _has_generic_override("y cómo lo solucionas?")
    print("PASS: generic override detection")


@contextmanager
def monkeypatch_runs_dir():
    old_root = ca.RUN_ROOT
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(3):
            d = Path(tmpdir) / f"agv2_fake_run_{i}"
            d.mkdir()
            (d / "run.json").write_text(json.dumps({
                "run_id": f"agv2_fake_run_{i}",
                "user_id": "test_user",
                "goal": f"question {i} about scheduler" if i == 0 else f"question {i}",
                "goal_preview": f"question {i} about scheduler" if i == 0 else f"question {i}",
                "intent_route": "brain_evidence",
                "classification": "brain_evidence",
                "evidence_sources": [{"type": "runtime_operations"}],
                "plan": [{"tool_name": "repo_status_read"}],
                "final_answer": f"answer {i}",
            }), encoding="utf-8")
        ca.RUN_ROOT = Path(tmpdir)
        try:
            yield Path(tmpdir)
        finally:
            ca.RUN_ROOT = old_root


def test_context_assembly_reads_runs():
    with monkeypatch_runs_dir():
        ctx = assemble_recent_context(
            user_id="test_user",
            current_goal="y cómo lo solucionas?",
            max_turns=3,
            max_chars=2000,
        )
        assert ctx["is_follow_up"] is True
        assert len(ctx["turns"]) <= 3
        assert any("scheduler" in t["goal"].lower() for t in ctx["turns"])
        print("PASS: context assembly reads runs")


def test_context_inheritance_routing():
    from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter
    adapter = AgentV2IntentAdapter()

    # Scenario 1: follow-up with prior brain_evidence context
    recent_ctx = {
        "is_follow_up": True,
        "prev_route": "brain_evidence",
        "prev_sources": ["runtime_operations", "tools_capabilities"],
        "prev_goal": "EL SCHEDULER ESTA ACTIVO O NO?",
    }
    route_info = adapter.select_route("y cómo lo solucionas?", recent_context=recent_ctx)
    assert route_info["route"] in {"brain_evidence", "mixed_brain_reasoning", "operational_agent"}
    assert route_info.get("context_inherited") is True
    print("PASS: context inheritance routing")

    # Scenario 2: follow-up with generic override should still be direct_assistant
    route_info = adapter.select_route("dame una receta de arroz con pollo", recent_context=recent_ctx)
    assert route_info["route"] == "direct_assistant"
    print("PASS: generic override preserved")

    # Scenario 3: no context, normal routing
    route_info = adapter.select_route("dame una receta de arroz con pollo", recent_context=None)
    assert route_info["route"] == "direct_assistant"
    print("PASS: normal routing without context")


def test_context_block_in_finalizer():
    from brain_v9.core.agent_kernel_v2.finalizer import build_finalizer_prompt
    run = {
        "goal": "y cómo lo solucionas?",
        "mode": "read_only",
        "classification": "brain_evidence",
    }
    recent_ctx = {
        "is_follow_up": True,
        "prev_route": "brain_evidence",
        "prev_sources": ["runtime_operations"],
        "prev_goal": "EL SCHEDULER ESTA ACTIVO O NO?",
        "prev_answer": "Scheduler found inactive...",
    }
    prompt = build_finalizer_prompt(run, [], [], recent_context=recent_ctx)
    assert "RECENT SESSION CONTEXT:" in prompt
    assert "brain_evidence" in prompt
    assert "Scheduler found inactive" in prompt
    assert "FOLLOW-UP" in prompt
    print("PASS: context block injected into finalizer prompt")


if __name__ == "__main__":
    test_follow_up_detection()
    test_generic_override()
    test_context_assembly_reads_runs()
    test_context_inheritance_routing()
    test_context_block_in_finalizer()
    print("\nALL CONTEXT ASSEMBLER TESTS PASSED")
