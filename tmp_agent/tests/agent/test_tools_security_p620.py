from __future__ import annotations

import pytest

import brain_v9.agent.tools as tools


@pytest.mark.asyncio
async def test_run_command_blocks_python_execution():
    result = await tools.run_command("python -m http.server 9001")
    assert result["success"] is False
    assert "bloqueado" in result["error"].lower() or "no permitida" in result["error"].lower()


@pytest.mark.asyncio
async def test_write_file_denies_protected_root(monkeypatch, tmp_path):
    protected = tmp_path / "00_identity"
    protected.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools, "_deny_roots", lambda: [protected.resolve()])

    with pytest.raises(PermissionError):
        await tools.write_file(str(protected / "blocked.txt"), "secret")


@pytest.mark.asyncio
async def test_start_brain_v7_requires_escalation():
    result = await tools.start_brain_v7()
    assert result["success"] is False
    assert result["status"] == "escalation_required"
    assert result["permission_level"] == "P3"


@pytest.mark.asyncio
async def test_start_brain_server_legacy_requires_escalation():
    result = await tools.start_brain_server_legacy()
    assert result["success"] is False
    assert result["status"] == "escalation_required"
    assert result["permission_level"] == "P3"


@pytest.mark.asyncio
async def test_stop_service_requires_escalation():
    result = await tools.stop_service("brain_v9")
    assert result["success"] is False
    assert result["status"] == "escalation_required"
    assert result["permission_level"] == "P3"


@pytest.mark.asyncio
async def test_restart_service_requires_escalation():
    result = await tools.restart_service("brain_v9")
    assert result["success"] is False
    assert result["status"] == "escalation_required"
    assert result["permission_level"] == "P3"
