"""R7.1 contract: governed correlation-bound trace schema and event writer."""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_trace_store_persists_only_governed_correlation_bound_redacted_events(tmp_path):
    from brain_v9.core.agent_kernel_v2.schemas import AgentTraceEvent
    from brain_v9.core.agent_kernel_v2.trace import TraceStore

    store = TraceStore(tmp_path)
    store.append(
        AgentTraceEvent(
            event_type="run_created",
            run_id="run-r7-1",
            event_id="event-r7-1",
            correlation_id="corr-r7-1",
            data={
                "summary": "governed trace",
                "reasoning": "private reasoning must not persist",
                "token": "secret-value",
            },
        )
    )

    persisted = store.read()

    assert persisted == [
        {
            "correlation_id": "corr-r7-1",
            "data": {"summary": "governed trace"},
            "event_id": "event-r7-1",
            "event_type": "run_created",
            "message": "",
            "run_id": "run-r7-1",
            "schema_version": 1,
            "step_id": None,
            "timestamp_utc": persisted[0]["timestamp_utc"],
        }
    ]


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        ({"event_type": "run_created", "correlation_id": ""}, "trace_correlation_id_required"),
        ({"event_type": "not_in_governed_taxonomy"}, "trace_event_type_not_allowed"),
    ],
)
def test_trace_store_rejects_missing_correlation_or_unknown_taxonomy_before_write(
    tmp_path, event, reason
):
    from brain_v9.core.agent_kernel_v2.schemas import AgentTraceEvent
    from brain_v9.core.agent_kernel_v2.trace import TraceStore

    store = TraceStore(tmp_path)
    candidate = AgentTraceEvent(run_id="run-r7-1", **event)

    with pytest.raises(ValueError, match=reason):
        store.append(candidate)
    assert store.read() == []


def test_trace_event_defaults_bind_identity_to_its_run():
    from brain_v9.core.agent_kernel_v2.schemas import AgentTraceEvent

    event = AgentTraceEvent(event_type="run_completed", run_id="run-r7-1")

    assert event.schema_version == 1
    assert event.event_id
    assert event.correlation_id == "run-r7-1"


def test_trace_store_redacts_private_reasoning_markers_before_persistence(tmp_path):
    from brain_v9.core.agent_kernel_v2.schemas import AgentTraceEvent
    from brain_v9.core.agent_kernel_v2.trace import TraceStore

    store = TraceStore(tmp_path)
    store.append(
        AgentTraceEvent(
            event_type="plan_created",
            run_id="run-r7-1",
            data={"summary": "private reasoning must not be retained"},
        )
    )

    assert store.read()[0]["data"] == {
        "redacted": True,
        "reason": "private_reasoning_marker_blocked",
    }


def test_all_static_runtime_trace_types_are_in_the_governed_taxonomy():
    from brain_v9.core.agent_kernel_v2.schemas import TRACE_EVENT_TAXONOMY

    runtime_paths = (
        ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py",
        ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py",
    )
    used_types = set()
    for path in runtime_paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_trace"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                used_types.add(node.args[1].value)

    assert used_types <= TRACE_EVENT_TAXONOMY


def test_r7_1_evidence_records_no_deploy_trace_baseline_contract():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R7_1_GOVERNED_TRACE_SCHEMA_EVENT_WRITER_BASELINE.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item_id"] == "R7.1"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "provider_call": False,
        "canonical_local_sync": False,
    }
