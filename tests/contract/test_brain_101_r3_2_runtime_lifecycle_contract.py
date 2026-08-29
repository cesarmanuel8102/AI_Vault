"""BRAIN-101-R3-2 Agent V2 runtime lifecycle contract tests.

Front: BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
Surface: C1 Runtime contract (mission/run identity, checkpoint/resume,
status transition, backend selection)

Deterministic contract tests that exercise the runtime selector and the
NativeAgentRuntimeV2 / LangGraphParityRuntimeV2 lifecycle methods without
starting servers or making network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


@pytest.fixture
def temp_run_root(tmp_path):
    return tmp_path / "runs"


@pytest.fixture
def parity_run_root(tmp_path):
    return tmp_path / "runs_parity_test_lifecycle"


# ---------------------------------------------------------------------------
# 1. Runtime backend selector contract
# ---------------------------------------------------------------------------

def test_resolve_agent_v2_backend_defaults_to_langgraph_parity():
    from brain_v9.core.agent_kernel_v2.runtime import resolve_agent_v2_backend_choice

    assert resolve_agent_v2_backend_choice(None) == "langgraph_parity"
    assert resolve_agent_v2_backend_choice("langgraph_parity") == "langgraph_parity"
    assert resolve_agent_v2_backend_choice("langgraph") == "langgraph_parity"


def test_resolve_agent_v2_backend_native_values_rollback():
    from brain_v9.core.agent_kernel_v2.runtime import resolve_agent_v2_backend_choice

    assert resolve_agent_v2_backend_choice("native") == "native_runtime"
    assert resolve_agent_v2_backend_choice("") == "native_runtime"
    assert resolve_agent_v2_backend_choice("invalid_backend") == "native_runtime"


def test_is_langgraph_backend_requested():
    from brain_v9.core.agent_kernel_v2.runtime import is_langgraph_backend_requested

    assert is_langgraph_backend_requested(None) is True
    assert is_langgraph_backend_requested("langgraph_parity") is True
    assert is_langgraph_backend_requested("native") is False


# ---------------------------------------------------------------------------
# 2. Production runtime interface contract
# ---------------------------------------------------------------------------

def test_native_runtime_implements_required_interface():
    from brain_v9.core.agent_kernel_v2.runtime import is_agent_v2_production_runtime_compatible
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

    rt = NativeAgentRuntimeV2()
    compatible, missing = is_agent_v2_production_runtime_compatible(rt)
    assert compatible is True
    assert not missing
    required_methods = ("create_run", "execute_run", "plan_run", "pause_run", "resume_run", "cancel_run")
    for method in required_methods:
        assert hasattr(rt, method) and callable(getattr(rt, method))


def test_langgraph_parity_runtime_implements_required_interface(parity_run_root):
    from brain_v9.core.agent_kernel_v2.runtime import is_agent_v2_production_runtime_compatible
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=parity_run_root)
    compatible, missing = is_agent_v2_production_runtime_compatible(rt)
    assert compatible is True
    assert not missing


# ---------------------------------------------------------------------------
# 3. Native runtime lifecycle contract
# ---------------------------------------------------------------------------

def test_native_create_run_sets_required_identity_fields(temp_run_root, monkeypatch):
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    from brain_v9.core.agent_kernel_v2 import state as state_mod
    from brain_v9.core.agent_kernel_v2 import native_runtime as native_runtime_mod

    monkeypatch.setattr(state_mod, "RUN_ROOT", temp_run_root)
    monkeypatch.setattr(native_runtime_mod, "RUN_ROOT", temp_run_root)
    rt = NativeAgentRuntimeV2()
    run = rt.create_run("Test goal", mode="read_only", user_id="contract_user")
    assert run["goal"] == "Test goal"
    assert run["mode"] == "read_only"
    assert run["mode_requested"] == "read_only"
    assert run["mode_effective"] == "read_only"
    assert run["user_id"] == "contract_user"
    assert run["status"] == "created"
    assert run["run_id"].startswith("agv2_")
    assert "agent_version" in run
    assert run["canonical_agent"] is True


def test_native_plan_run_persists_plan_and_status(temp_run_root, monkeypatch):
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    from brain_v9.core.agent_kernel_v2 import state as state_mod
    from brain_v9.core.agent_kernel_v2 import native_runtime as native_runtime_mod

    monkeypatch.setattr(state_mod, "RUN_ROOT", temp_run_root)
    monkeypatch.setattr(native_runtime_mod, "RUN_ROOT", temp_run_root)
    rt = NativeAgentRuntimeV2()
    run = rt.create_run("repo status", mode="read_only")
    planned = rt.plan_run(run["run_id"])
    assert planned["status"] == "planned"
    assert "plan" in planned
    assert "metadata" in planned
    assert isinstance(planned["plan"], list)


def test_native_pause_resume_cancel_transitions(temp_run_root, monkeypatch):
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    from brain_v9.core.agent_kernel_v2 import state as state_mod
    from brain_v9.core.agent_kernel_v2 import native_runtime as native_runtime_mod

    monkeypatch.setattr(state_mod, "RUN_ROOT", temp_run_root)
    monkeypatch.setattr(native_runtime_mod, "RUN_ROOT", temp_run_root)
    rt = NativeAgentRuntimeV2()
    run = rt.create_run("lifecycle test", mode="read_only")
    rt.pause_run(run["run_id"])
    run = rt.get_run(run["run_id"])
    assert run["status"] == "paused"
    rt.resume_run(run["run_id"])
    run = rt.get_run(run["run_id"])
    assert run["status"] == "running"
    rt.cancel_run(run["run_id"])
    run = rt.get_run(run["run_id"])
    assert run["status"] == "cancelled"


def test_native_checkpoint_is_persisted(temp_run_root, monkeypatch):
    from brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2
    from brain_v9.core.agent_kernel_v2 import state as state_mod
    from brain_v9.core.agent_kernel_v2 import native_runtime as native_runtime_mod

    monkeypatch.setattr(state_mod, "RUN_ROOT", temp_run_root)
    monkeypatch.setattr(native_runtime_mod, "RUN_ROOT", temp_run_root)
    rt = NativeAgentRuntimeV2()
    run = rt.create_run("checkpoint test", mode="read_only")
    rt._save_run(run)
    cp_path = rt._run_dir(run["run_id"]) / "checkpoint.json"
    assert cp_path.exists()


# ---------------------------------------------------------------------------
# 4. LangGraph parity runtime lifecycle contract
# ---------------------------------------------------------------------------

def test_langgraph_parity_create_run_sets_required_fields(parity_run_root):
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=parity_run_root)
    run = rt.create_run("parity lifecycle", mode="read_only", user_id="contract_user")
    assert run["goal"] == "parity lifecycle"
    assert run["mode"] == "read_only"
    assert run["mode_requested"] == "read_only"
    assert run["mode_effective"] == "read_only"
    assert run["user_id"] == "contract_user"
    assert run["status"] == "created"
    assert run["run_id"].startswith("agv2_")
    assert run["backend_selected"] == "langgraph_parity"
    assert run["canonical_agent"] is True


def test_langgraph_parity_plan_run_transitions_and_schedules_tools(parity_run_root):
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=parity_run_root)
    run = rt.create_run("repo status", mode="read_only")
    planned = rt.plan_run(run["run_id"])
    assert planned["status"] == "planned"
    assert "plan" in planned
    assert planned.get("planner_used") is True
    assert isinstance(planned["plan"], list)


def test_langgraph_parity_status_transition_rules(parity_run_root):
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=parity_run_root)
    run = rt.create_run("transition test", mode="read_only")
    rt.pause_run(run["run_id"])
    assert rt.get_run(run["run_id"])["status"] == "paused"
    rt.resume_run(run["run_id"])
    assert rt.get_run(run["run_id"])["status"] == "resumed"
    rt.cancel_run(run["run_id"])
    assert rt.get_run(run["run_id"])["status"] == "cancelled"


def test_langgraph_parity_resume_survives_runtime_recreation(parity_run_root):
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    first_runtime = LangGraphParityRuntimeV2(run_root=parity_run_root)
    run = first_runtime.create_run("restartable lifecycle", mode="read_only")
    first_runtime.plan_run(run["run_id"])
    first_runtime.pause_run(run["run_id"])

    recreated_runtime = LangGraphParityRuntimeV2(run_root=parity_run_root)
    resumed = recreated_runtime.resume_run(run["run_id"])

    assert resumed["status"] == "resumed"
    assert resumed["previous_status"] == "paused"
    assert resumed["resumed_to_status"] == "planned"
    assert recreated_runtime.get_checkpoint(run["run_id"])["status"] == "resumed"


def test_langgraph_parity_invalid_transition_is_rejected(parity_run_root):
    from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import LangGraphParityRuntimeV2

    rt = LangGraphParityRuntimeV2(run_root=parity_run_root)
    run = rt.create_run("invalid transition", mode="read_only")
    rt.cancel_run(run["run_id"])
    result = rt.pause_run(run["run_id"])
    assert result["status"] == "cancelled"
    assert "cannot transition terminal run" in result.get("error", "")


# ---------------------------------------------------------------------------
# 5. Runtime status constants contract
# ---------------------------------------------------------------------------

def test_runtime_status_constants_are_complete():
    from brain_v9.core.agent_kernel_v2.schemas import STATUSES

    required = {"created", "planned", "running", "waiting_approval", "paused", "failed", "completed", "cancelled"}
    assert required.issubset(STATUSES)


def test_runtime_modes_are_restricted():
    from brain_v9.core.agent_kernel_v2.schemas import MODES

    assert MODES == {"read_only", "build", "auto"}


# ---------------------------------------------------------------------------
# 6. Backend metadata contract
# ---------------------------------------------------------------------------

def test_get_agent_runtime_v2_falls_back_to_native_when_langgraph_unavailable(monkeypatch):
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2

    monkeypatch.setenv("AGENT_V2_BACKEND", "this_backend_does_not_exist")
    rt = get_agent_runtime_v2()
    assert rt.backend_selected == "native_runtime"
    assert rt.backend_fallback_used is True
    assert "this_backend_does_not_exist" in (rt.backend_fallback_reason or "")


# ---------------------------------------------------------------------------
# 7. Safety: runtime modules do not contain forbidden server execution tokens
# ---------------------------------------------------------------------------

def test_runtime_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/runtime.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem("]
    assert not any(token in src for token in forbidden)


def test_native_runtime_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem("]
    assert not any(token in src for token in forbidden)


# ---------------------------------------------------------------------------
# Runner for direct invocation
# ---------------------------------------------------------------------------

_TESTS = [
    test_resolve_agent_v2_backend_defaults_to_langgraph_parity,
    test_resolve_agent_v2_backend_native_values_rollback,
    test_is_langgraph_backend_requested,
    test_native_runtime_implements_required_interface,
    test_langgraph_parity_runtime_implements_required_interface,
    test_native_create_run_sets_required_identity_fields,
    test_native_plan_run_persists_plan_and_status,
    test_native_pause_resume_cancel_transitions,
    test_native_checkpoint_is_persisted,
    test_langgraph_parity_create_run_sets_required_fields,
    test_langgraph_parity_plan_run_transitions_and_schedules_tools,
    test_langgraph_parity_status_transition_rules,
    test_langgraph_parity_invalid_transition_is_rejected,
    test_runtime_status_constants_are_complete,
    test_runtime_modes_are_restricted,
    test_get_agent_runtime_v2_falls_back_to_native_when_langgraph_unavailable,
    test_runtime_source_does_not_import_server_starters,
    test_native_runtime_source_does_not_import_server_starters,
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
