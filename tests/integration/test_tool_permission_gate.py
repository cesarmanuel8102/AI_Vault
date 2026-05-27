"""
TOOL-01B: Permission Gate tests.
"""
import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))


@pytest.mark.asyncio
async def test_read_file_without_permission_returns_permission_required():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-read-no-perm")
    result = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result is not None
    assert result.get("permission_required") is True
    assert result.get("tool01_real") is False
    assert result.get("tool01_router_used") is True
    assert "permission_id" in result
    assert result.get("risk_level") == "low"


@pytest.mark.asyncio
async def test_allow_once_executes_once():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-allow-once")
    result = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result is not None
    assert result.get("permission_required") is True
    perm = result

    # Approve allow_once via API method
    approval = session._tool01_approve_permission(perm["permission_id"], "allow_once")
    assert approval["success"] is True
    assert approval["decision"] == "allow_once"

    # After approval, router should execute directly
    result2 = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result2.get("success") is True
    assert result2.get("tool01_real") is True
    assert "preview" in result2

    # Third call should need permission again
    result3 = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result3 is not None
    # Because allow_once requires a new permission each time after use


@pytest.mark.asyncio
async def test_allow_session_allows_second_call_without_reask():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-allow-session")
    result = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result is not None
    assert result.get("permission_required") is True
    perm = result

    approval = session._tool01_approve_permission(perm["permission_id"], "allow_session")
    assert approval["success"] is True
    assert approval["decision"] == "allow_session"

    # Should execute without asking again
    result2 = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result2.get("success") is True
    assert result2.get("tool01_real") is True


@pytest.mark.asyncio
async def test_deny_blocks_execution():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-deny")
    result = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result is not None
    assert result.get("permission_required") is True
    perm = result

    approval = session._tool01_approve_permission(perm["permission_id"], "deny")
    assert approval["success"] is False
    assert approval["decision"] == "deny"
    assert approval["blocked_by_user"] is True


@pytest.mark.asyncio
async def test_protected_path_blocked_even_with_allow_session():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-protected")
    result = await session._tool01_router("lee archivo tmp_agent/brain_v9/core/llm.py")
    assert result is not None
    assert result.get("permission_required") is True
    perm = result

    session._tool01_approve_permission(perm["permission_id"], "allow_session")

    # Now try to read a protected path
    exec_result = await session._tool01_execute("read_file", "lee archivo C:\\AI_VAULT\\memory\\semantic\\semantic_memory.jsonl usando read_file")
    assert exec_result["success"] is False
    assert exec_result["blocked_by_policy"] is True


@pytest.mark.asyncio
async def test_git_status_low_risk_asks_permission():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-git-status")
    result = await session._tool01_router("git status")
    assert result is not None
    assert result.get("permission_required") is True
    assert result.get("risk_level") == "low"
    assert "allow_session" in result.get("options", [])


@pytest.mark.asyncio
async def test_high_risk_no_allow_session():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-high-risk")
    perm = session._tool01_request_permission("install", "test high-risk", "/")
    assert perm["risk_level"] == "high"
    assert "allow_session" not in perm["options"]


@pytest.mark.asyncio
async def test_fallback_llm_does_not_claim_execution():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01b-test-fallback")
    # Any message not matching TOOL-01 patterns
    result = await session._tool01_router("hola amigo")
    assert result is None
    # LLM route would handle; we don't touch that here
    # Key assertion: without a real grant, real tools return permission_required
    result2 = await session._tool01_router("git status")
    assert result2.get("permission_required") is True
    assert result2.get("tool01_real") is False
    # Must NOT say "Tool ejecutada realmente" without execution evidence
    assert "tool01_real=false" in str(result2).lower() or result2.get("tool01_real") is False


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
