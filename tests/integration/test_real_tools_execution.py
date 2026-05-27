"""
TOOL-01A: deterministic real-tool router tests.

These tests verify the router contract without relying on LLM tool_calls or
AgentLoop. Runtime /chat smoke is still required for final acceptance.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))


@pytest.mark.asyncio
async def test_tool01_router_health(monkeypatch):
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-health")

    async def fake_execute(tool_name, message):
        return {
            "route": "tool01_router",
            "tool01_router_used": True,
            "tool01_real": True,
            "tools_executed_count": 1,
            "tool_name": "runtime.health_check",
            "success": True,
            "blocked_by_policy": False,
        }

    monkeypatch.setattr(session, "_tool01_execute", fake_execute)
    # Pre-grant permission so router skips the permission gate
    session._tool01_permission_grants["health_check"] = {
        "granted": True, "grant_type": "allow_session", "scope": "C:/AI_VAULT"
    }
    result = await session._tool01_router("Comprueba el health de Brain. Usa herramienta real.")
    assert result["tool01_router_used"] is True
    assert result["tool01_real"] is True
    assert result["tools_executed_count"] == 1
    assert result["tool_name"] == "runtime.health_check"


@pytest.mark.asyncio
async def test_tool01_router_git_status():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-git")
    result = await session._tool01_execute("git_status", "Ejecuta git status --short en C:\\AI_VAULT")
    assert result["tool01_router_used"] is True
    assert result["tool01_real"] is True
    assert result["tools_executed_count"] >= 1
    assert result["tool_name"] == "git.status"
    assert result["success"] is True
    assert "stdout" in result
    assert result["blocked_by_policy"] is False


@pytest.mark.asyncio
async def test_tool01_router_list_dir():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-list")
    result = await session._tool01_execute(
        "list_directory",
        "Lista los archivos de C:\\AI_VAULT\\tmp_agent\\brain_v9\\core. Usa herramienta real.",
    )
    assert result["tool_name"] == "filesystem.list_dir"
    assert result["tool01_router_used"] is True
    assert result["success"] is True
    assert result["tools_executed_count"] >= 1
    assert any("llm.py" in entry for entry in result.get("entries", []))


@pytest.mark.asyncio
async def test_tool01_router_read_file():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-read")
    result = await session._tool01_execute(
        "read_file",
        "Lee las primeras 10 líneas de C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\llm.py. Usa herramienta real.",
    )
    assert result["tool_name"] == "filesystem.read_file"
    assert result["tool01_router_used"] is True
    assert result["success"] is True
    assert result["tools_executed_count"] >= 1
    assert "preview" in result
    assert len(result["preview"].splitlines()) <= 10


@pytest.mark.asyncio
async def test_tool01_blocks_protected_read():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-block-read")
    result = await session._tool01_execute(
        "read_file",
        "Lee C:\\AI_VAULT\\memory\\semantic\\semantic_memory.jsonl con herramienta real.",
    )
    assert result["tool_name"] == "filesystem.read_file"
    assert result["success"] is False
    assert result["blocked_by_policy"] is True
    assert "bloqueada" in result["error"].lower() or "bloqueado" in result["error"].lower()


@pytest.mark.asyncio
async def test_tool01_blocks_arbitrary_shell():
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-shell")
    result = await session._tool01_router("Ejecuta del /F /Q tmp_agent con shell real")
    assert result is None


@pytest.mark.asyncio
async def test_tool01_does_not_use_agentloop_timeout_for_simple_tools(monkeypatch):
    from brain_v9.core.session import BrainSession

    session = BrainSession("tool01-test-fastpath")

    async def fake_router(message):
        return {
            "route": "tool01_router",
            "tool01_router_used": True,
            "tool01_real": True,
            "tools_executed_count": 1,
            "tool_name": "git.status",
            "success": True,
            "blocked_by_policy": False,
            "fallback": False,
            "agent_status_timeout": False,
            "stdout": "",
        }

    monkeypatch.setattr(session, "_tool01_router", fake_router)
    response = await session._route_to_agent("git status --short", "auto")
    assert response["route"] == "tool01_router"
    assert response["tool01_router_used"] is True
    assert response["tools_executed_count"] == 1
    assert response["tool_name"] == "git.status"
    assert response["fallback"] is False
    assert response["agent_status"] == "tool01_real"
    assert response["tool_result"]["agent_status_timeout"] is False
