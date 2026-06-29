"""Smoke test for metadata-only capability exposure in /v2/chat/agent.

Read-only and deterministic. No live LLM, no server, no memory/FAISS mutation.

Tests parse and statically evaluate the _build_capability_metadata helper in
api_adapter.py without importing the module (which uses relative imports).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_api_adapter_path = Path("C:/AI_VAULT_CANONICAL/tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py")


def _extract_build_capability_metadata_node():
    content = _api_adapter_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_capability_metadata":
            return node
    raise AssertionError("_build_capability_metadata not found in api_adapter.py")


def _run_helper(run: dict) -> dict:
    """Execute the helper source in a clean namespace with the provided run."""
    node = _extract_build_capability_metadata_node()
    code = compile(ast.unparse(node), "<api_adapter_helper>", "exec")
    namespace = {"run": run, "Dict": dict, "Any": object}
    exec(code, namespace)
    return namespace["_build_capability_metadata"](run)


@pytest.fixture(scope="module")
def helper_node():
    return _extract_build_capability_metadata_node()


def test_build_capability_metadata_exists(helper_node):
    assert helper_node is not None
    assert helper_node.name == "_build_capability_metadata"


def test_build_capability_metadata_retrieval_attempted():
    run = {
        "intent_route": "brain_evidence",
        "plan": [
            {
                "tool_name": "semantic_retrieve",
                "status": "completed",
                "output": {"result": {"hits": [{"id": "1"}]}},
            }
        ],
    }
    meta = _run_helper(run)
    assert meta["retrieval_attempted"] is True
    assert meta["memory_used"] is True
    assert meta["retrieval_no_results"] is False
    assert meta["retrieval_skipped"] is False


def test_build_capability_metadata_retrieval_no_results():
    run = {
        "intent_route": "brain_evidence",
        "plan": [
            {
                "tool_name": "semantic_retrieve",
                "status": "completed",
                "output": {"result": {"hits": []}},
            }
        ],
    }
    meta = _run_helper(run)
    assert meta["retrieval_attempted"] is True
    assert meta["retrieval_no_results"] is True
    assert meta["retrieval_skipped"] is False


def test_build_capability_metadata_retrieval_skipped():
    run = {
        "intent_route": "mixed_brain_reasoning",
        "plan": [{"tool_name": "grep_search", "status": "completed"}],
    }
    meta = _run_helper(run)
    assert meta["retrieval_attempted"] is False
    assert meta["retrieval_skipped"] is True


def test_build_capability_metadata_direct_assistant_not_skipped():
    run = {
        "intent_route": "direct_assistant",
        "plan": [],
    }
    meta = _run_helper(run)
    assert meta["retrieval_attempted"] is False
    assert meta["retrieval_skipped"] is False


def test_build_capability_metadata_evidence_routed():
    run = {
        "intent_route": "brain_evidence",
        "evidence_sources": [{"type": "code", "tools": ["grep_search"]}],
        "plan": [{"tool_name": "grep_search", "status": "completed"}],
    }
    meta = _run_helper(run)
    assert meta["evidence_routed"] is True
    assert meta["evidence_sources_count"] == 1
    assert meta["planner_used"] is True


def test_build_capability_metadata_governance_checked():
    run = {
        "intent_route": "operational_agent",
        "mode_escalation_required": True,
        "blocked_tools": ["write_file"],
        "plan": [{"tool_name": "write_file", "status": "blocked"}],
    }
    meta = _run_helper(run)
    assert meta["governance_checked"] is True
    assert meta["tools_blocked"] == 1


def test_build_capability_metadata_tool_counts():
    run = {
        "intent_route": "operational_agent",
        "plan": [
            {"tool_name": "grep_search", "status": "completed"},
            {"tool_name": "file_read", "status": "completed"},
            {"tool_name": "write_file", "status": "blocked"},
            {"tool_name": None, "status": "completed"},
        ],
    }
    meta = _run_helper(run)
    assert meta["tools_considered"] == 3
    assert meta["tools_executed"] == 3


def test_build_capability_metadata_required_keys():
    meta = _run_helper({"intent_route": "direct_assistant", "plan": []})
    expected_keys = {
        "memory_used",
        "retrieval_attempted",
        "retrieval_no_results",
        "retrieval_skipped",
        "planner_used",
        "evidence_routed",
        "evidence_sources_count",
        "tools_considered",
        "tools_executed",
        "tools_blocked",
        "governance_checked",
        "intent_route",
        "classification",
    }
    assert expected_keys.issubset(set(meta.keys()))


def test_no_live_mutation_in_helpers(helper_node):
    """Static smoke: helper does not write to files or call external services."""
    src = ast.unparse(helper_node)
    assert "write_text" not in src
    assert "open(" not in src
    assert "requests" not in src
    assert "call(" not in src


def test_native_runtime_not_modified_in_this_patch():
    """Confirm we are only testing api_adapter changes."""
    # Static check: native_runtime.py should not mention capability_metadata construction.
    nr_path = Path("C:/AI_VAULT_CANONICAL/tmp_agent/brain_v9/core/agent_kernel_v2/native_runtime.py")
    content = nr_path.read_text(encoding="utf-8")
    # Runtime behavior unchanged: no capability_metadata keyword added there
    assert "capability_metadata" not in content


def test_api_adapter_response_includes_capability_metadata_key():
    """Static check that chat_agent returns 'capability_metadata' in its response dict."""
    content = _api_adapter_path.read_text(encoding="utf-8")
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "chat_agent":
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Dict):
                    keys = {ast.unparse(k) for k in ret.value.keys if isinstance(k, ast.Constant)}
                    assert "'capability_metadata'" in keys
                    return
    raise AssertionError("chat_agent does not return capability_metadata")
