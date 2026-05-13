"""
Smoke tests para la integracion del Brain upgrade stack.

Estas pruebas validan el punto de acople real:
- `main.py` debe importar sin romper el bootstrap legacy.
- El router `/upgrade/*` debe quedar montado en FastAPI.
- El orchestrator debe responder `status()` y `tick()`.
"""

import asyncio

import pytest


@pytest.mark.unit
def test_main_imports_and_mounts_upgrade_routes():
    import main

    paths = {route.path for route in main.app.router.routes}

    assert "/upgrade/status" in paths
    assert "/upgrade/tick" in paths
    assert "/upgrade/aos/status" in paths
    assert "/upgrade/l2/report" in paths
    assert "/upgrade/sandbox/status" in paths
    assert "/upgrade/events/replay" in paths
    assert "/upgrade/settings" in paths
    assert "/upgrade/capabilities/status" in paths
    assert "/upgrade/capabilities/diagnose" in paths


@pytest.mark.unit
def test_upgrade_status_smoke():
    from brain.upgrade_router import upgrade_status

    result = asyncio.run(upgrade_status())

    assert isinstance(result, dict)
    assert "last_tick" in result
    assert "subsystems" in result
    assert isinstance(result["subsystems"], dict)


@pytest.mark.unit
def test_upgrade_tick_smoke():
    from brain.upgrade_router import upgrade_tick

    result = asyncio.run(upgrade_tick())

    assert isinstance(result, dict)
    assert "signals" in result
    assert "new_goals" in result
    assert "executions" in result
    assert "biases_detected" in result
    assert isinstance(result["signals"], dict)


@pytest.mark.unit
def test_upgrade_status_http(api_client):
    response = api_client.get("/upgrade/status")

    assert response.status_code == 200
    payload = response.json()
    assert "last_tick" in payload
    assert "subsystems" in payload
