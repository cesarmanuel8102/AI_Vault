import asyncio

import pytest


@pytest.mark.unit
def test_capability_governor_resolves_legacy_aliases():
    from brain.capability_governor import get_capability_governor

    governor = get_capability_governor()
    governor.register_runtime_tools(["run_command", "analyze_python", "request_clarification"])

    resolved = governor.resolve_tool_name("execute_command")
    clarify = governor.resolve_tool_name("ask_user_for_objective")

    assert resolved["ok"] is True
    assert resolved["tool"] == "run_command"
    assert clarify["ok"] is True
    assert clarify["tool"] == "request_clarification"


@pytest.mark.unit
def test_tool_executor_returns_structured_missing_capability():
    from brain_v9.agent.loop import ToolExecutor

    async def _dummy() -> dict:
        return {"success": True}

    executor = ToolExecutor()
    executor.register("run_command", _dummy, "dummy")

    result = asyncio.run(executor.execute("nonexistent_tool"))

    assert result["success"] is False
    assert result["status"] == "missing_capability"
    assert result["requested_tool"] == "nonexistent_tool"


@pytest.mark.unit
def test_upgrade_routes_expose_capability_governor(api_client):
    response = api_client.get("/upgrade/capabilities/status")

    assert response.status_code == 200
    payload = response.json()
    assert "tool_inventory_count" in payload
    assert "known_aliases" in payload


@pytest.mark.unit
def test_capability_diagnose_includes_memory_health(api_client):
    response = api_client.get("/upgrade/capabilities/diagnose")

    assert response.status_code == 200
    payload = response.json()
    assert "memory_health" in payload
    assert "episodic" in payload["memory_health"]


@pytest.mark.unit
def test_upgrade_routes_expose_memory_maintenance(api_client):
    status = api_client.get("/upgrade/memory/status")
    compact = api_client.post("/upgrade/memory/compact", json={"dry_run": True})

    assert status.status_code == 200
    assert "episodic" in status.json()
    assert compact.status_code == 200
    compact_payload = compact.json()
    assert compact_payload["dry_run"] is True
    assert "episodic" in compact_payload
    assert "semantic" in compact_payload


@pytest.mark.unit
def test_chat_product_governance_tracks_episodic_memory_hygiene():
    import sys

    sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")
    from brain_v9.brain.chat_product_governance import refresh_chat_product_status

    status = refresh_chat_product_status()
    quality_ids = {item["check_id"] for item in status["quality_checks"]}
    operational = status.get("quality_score")

    assert "episodic_memory_has_no_exact_duplicates" in quality_ids
    assert operational is not None
