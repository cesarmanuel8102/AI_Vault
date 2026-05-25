"""Tests for BOR-2 — Clean Agent Failure Fallback.

Static assertions: checks that the fallback helpers exist in session.py
and that the fallback branch appears inside _route_to_agent.
No runtime needed.
"""
import pytest
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def get_session_source():
    return (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")


def _find_function(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in AST")


class TestPatchPresence:
    """Verify that the BOR-2 fallback helpers are present in session.py."""

    def test_is_agent_execution_failure_present(self):
        src = get_session_source()
        assert "def _is_agent_execution_failure(self" in src
        assert '"ghost_completion"' in src
        assert '"max_steps_reached"' in src
        assert '"retry_exhausted"' in src
        assert '"timeout"' in src

    def test_agent_failure_notice_present(self):
        src = get_session_source()
        assert "def _agent_failure_notice(self" in src
        assert "agent_status=" in src

    def test_agent_fallback_llm_route_present(self):
        src = get_session_source()
        assert '"route": "agent_fallback_llm"' in src
        assert '"original_route": "agent"' in src


class TestRouteToAgentFallbackBranch:
    """AST-level check that the new fallback branch appears inside _route_to_agent."""

    def test_fallback_branch_inside_route_to_agent(self):
        tree = ast.parse(get_session_source())
        node = _find_function(tree, "_route_to_agent")
        body = ast.unparse(node)
        assert "_is_agent_execution_failure" in body
        assert "_agent_failure_notice" in body
        assert "agent_fallback_llm" in body
        assert "fallback_success" in body
        assert "original_route" in body

    def test_fallback_statuses(self):
        tree = ast.parse(get_session_source())
        node = _find_function(tree, "_route_to_agent")
        body = ast.unparse(node)
        for status in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
            assert status in body, f"Expected status {status} inside _route_to_agent body"

    def test_helper_detection(self):
        tree = ast.parse(get_session_source())
        for name in ("_is_agent_execution_failure", "_agent_failure_notice"):
            node = _find_function(tree, name)
            body = ast.unparse(node)
            if name == "_is_agent_execution_failure":
                assert "ghost_completion" in body
                assert "max_steps_reached" in body
            else:
                assert "agent_status=" in body


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
