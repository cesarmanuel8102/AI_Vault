from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def client(monkeypatch):
    async def _noop_startup():
        pass

    import brain_v9.main as main_mod
    monkeypatch.setattr(main_mod, "_startup_background", _noop_startup)
    monkeypatch.setattr(main_mod, "_startup_done", True)
    monkeypatch.setattr(main_mod, "_startup_error", None)
    monkeypatch.setattr(main_mod, "active_sessions", {})

    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c


def test_agent_uses_canonical_self_build_resolution_fastpath(client, monkeypatch):
    import brain_v9.main as main_mod

    class _FakeSession:
        llm = object()

        @staticmethod
        def _is_self_build_resolution_query(message):
            return "resuelvelo" in message

        @staticmethod
        def _self_build_resolution_fastpath():
            return {"content": "**Resolucion de autoconstruccion**\n  criterio de salida: apply_gate_ready=true"}

        @staticmethod
        def _is_deep_risk_analysis_query(message): return False

        @staticmethod
        def _is_deep_edge_analysis_query(message): return False

        @staticmethod
        def _is_deep_strategy_analysis_query(message): return False

        @staticmethod
        def _is_deep_pipeline_analysis_query(message): return False

        @staticmethod
        def _is_deep_brain_analysis_query(message): return False

        @staticmethod
        def _is_self_build_query(message): return False

        @staticmethod
        def _is_consciousness_query(message): return False

        @staticmethod
        def _is_brain_status_query(message): return False

    def _boom(*args, **kwargs):
        raise AssertionError("AgentLoop should not be called for canonical audits")

    monkeypatch.setattr(main_mod, "_agent_executor", MagicMock())
    monkeypatch.setattr(main_mod, "AgentLoop", _boom)

    with patch("brain_v9.core.session.get_or_create_session", return_value=_FakeSession()):
        resp = client.post("/agent", json={
            "task": "Por que esta detenida la autoconstruccion y resuelvelo.",
            "session_id": "self_build_resolution_fastpath",
            "model_priority": "chat",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "canonical_audit"
    assert data["steps"] == 0
    assert "Resolucion de autoconstruccion" in data["result"]
