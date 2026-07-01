"""Smoke test: LangGraph parity runtime documentation matches promoted default status."""
from pathlib import Path


def test_langgraph_parity_docstring_does_not_claim_test_only_or_unwired():
    path = Path("tmp_agent/brain_v9/core/agent_kernel_v2/langgraph_parity_runtime.py")
    text = path.read_text(encoding="utf-8")
    header = text.split('"""', 2)[1]

    assert "NOT wired" not in header
    assert "test-only" not in header
    assert "default" in header
    assert "runtime selector" in header
    assert "strict governance" in header
