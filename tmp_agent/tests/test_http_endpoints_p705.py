"""P7-05: HTTP endpoint tests using FastAPI TestClient.

Covers critical routes from main.py, trading/router.py, and autonomy/router.py.
All heavy dependencies (Ollama, IBKR, PocketOption, etc.) are mocked.

Strategy:
 - Patch _startup_background to prevent real startup work.
 - Control _startup_done / _startup_error to test health states.
 - Mock read functions that hit state files.
 - Mock connector health checks for trading router.

Tests:
  1. GET /health — healthy (200)
  2. GET /health — initializing (503)
  3. GET /health — startup_failed (503)
  4. GET /status — returns sessions and ready flag
  5. GET /brain/utility — returns utility state
  6. POST /brain/utility/refresh — returns snapshot
  7. GET /brain/strategy-engine/features — returns feature snapshot
  8. GET /brain/strategy-engine/signals — returns signal snapshot
  9. GET /brain/strategy-engine/ranking — returns ranking
 10. GET /brain/strategy-engine/summary — returns summary
 11. GET /brain/autonomy/ibkr-ingester — returns ingester status
 12. POST /brain/autonomy/ibkr-snapshot — triggers snapshot
 13. GET /brain/research/summary — returns research summary
 14. GET /brain/roadmap/governance — returns governance status
 15. GET /brain/self-improvement/ledger — returns ledger
 16. POST /chat — mocked LLM response
 17. GET /trading/health — mocked connector health
 18. GET /trading/policy — returns policy (file missing → default)
 19. GET /trading/platforms/summary — mocked platform dashboard
 20. GET /autonomy/status — returns autonomy manager status
 21. GET /autonomy/reports — returns recent reports
 22. GET /brain/meta-improvement/status — returns status
 23. GET /brain/chat-product/status — returns status
 24. GET /brain/utility-governance/status — returns status
 25. GET /brain/post-bl-roadmap/status — returns status
 26. GET /self-diagnostic — returns diagnostic report
 27. GET /brain/strategy-engine/expectancy — returns expectancy
 28. GET /brain/strategy-engine/candidates — returns candidates
 29. GET /brain/strategy-engine/archive — returns archive state
 30. GET /brain/operations — combined operations endpoint
 31. GET /brain/strategy-engine/post-trade-analysis — returns canonical post-trade analysis
 32. GET /brain/strategy-engine/post-trade-hypotheses — returns canonical post-trade hypothesis synthesis
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# We need to prevent the real lifespan from doing startup work.
# Patch _startup_background before importing the app.

@pytest.fixture()
def client(monkeypatch):
    """Create a TestClient with startup disabled."""
    # Patch _startup_background to be a harmless coroutine
    async def _noop_startup():
        pass

    import brain_v9.main as main_mod
    monkeypatch.setattr(main_mod, "_startup_background", _noop_startup)
    # Default: startup done, no errors
    monkeypatch.setattr(main_mod, "_startup_done", True)
    monkeypatch.setattr(main_mod, "_startup_error", None)
    monkeypatch.setattr(main_mod, "active_sessions", {})

    from fastapi.testclient import TestClient
    with TestClient(main_mod.app) as c:
        yield c


@pytest.fixture()
def client_initializing(monkeypatch):
    """TestClient where startup is not yet done."""
    async def _noop_startup():
        pass

    import brain_v9.main as main_mod
    monkeypatch.setattr(main_mod, "_startup_background", _noop_startup)
    monkeypatch.setattr(main_mod, "_startup_done", False)
    monkeypatch.setattr(main_mod, "_startup_error", None)
    monkeypatch.setattr(main_mod, "active_sessions", {})

    from fastapi.testclient import TestClient
    with TestClient(main_mod.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def client_failed(monkeypatch):
    """TestClient where startup failed."""
    async def _noop_startup():
        pass

    import brain_v9.main as main_mod
    monkeypatch.setattr(main_mod, "_startup_background", _noop_startup)
    monkeypatch.setattr(main_mod, "_startup_done", False)
    monkeypatch.setattr(main_mod, "_startup_error", "Ollama unreachable")
    monkeypatch.setattr(main_mod, "active_sessions", {})

    from fastapi.testclient import TestClient
    with TestClient(main_mod.app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Fake return data
# ---------------------------------------------------------------------------

_FAKE_UTILITY_STATE = {
    "u_score": 0.42,
    "verdict": "hold",
    "blockers": [],
    "current_phase": "paper_exploration",
    "capital": {"paper": 10000},
    "components": {},
    "sample": {},
    "next_actions": {},
    "errors": [],
    "source": "test",
}

_FAKE_UTILITY_SNAPSHOTS = {
    "snapshot": {"updated_utc": "2026-03-26T12:00:00Z", "u_proxy_score": 0.42},
    "gate": {"verdict": "hold", "blockers": [], "required_next_actions": []},
    "next_actions": {"top_action": None},
}

_FAKE_FEATURE_SNAPSHOT = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "items": [{"venue": "ibkr", "symbol": "SPY", "last": 520.5}],
}

_FAKE_SIGNAL_SNAPSHOT = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "signals": [{"strategy": "momentum_spy", "direction": "long"}],
}

_FAKE_RANKING = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "ranking": [{"strategy_id": "momentum_spy", "score": 0.65}],
}

_FAKE_ENGINE_REFRESH = {
    "summary": {"strategies_total": 5, "active": 2},
    "scorecards": {},
    "hypotheses": [],
}

_FAKE_EDGE_VALIDATION = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "summary": {"promotable_count": 1, "validated_count": 1, "probation_count": 0},
    "items": [{"strategy_id": "momentum_spy", "edge_state": "validated"}],
}

_FAKE_CONTEXT_EDGE_VALIDATION = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "summary": {"validated_count": 1, "supportive_count": 1, "contradicted_count": 0},
    "items": [{"strategy_id": "momentum_spy", "current_context_edge_state": "validated"}],
}

_FAKE_ACTIVE_CATALOG = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "summary": {"operational_count": 1, "excluded_count": 2},
    "items": [{"strategy_id": "momentum_spy", "catalog_state": "probation"}],
}

_FAKE_PIPELINE_INTEGRITY = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "summary": {
        "status": "healthy",
        "pipeline_ok": True,
        "ledger_entries": 5,
        "resolved_entries": 4,
        "pending_entries": 1,
        "top_action": "increase_resolved_sample",
    },
    "stages": {
        "utility": {"u_score": -0.15},
        "decision": {"top_action": "increase_resolved_sample"},
    },
    "anomalies": [],
}

_FAKE_POST_TRADE_ANALYSIS = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "summary": {"recent_resolved_trades": 3, "duplicate_anomaly_count": 0, "next_focus": "continue_probation"},
    "by_strategy": [{"strategy_id": "momentum_spy", "resolved": 3}],
    "anomalies": [],
}

_FAKE_POST_TRADE_HYPOTHESES = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "summary": {"top_finding": "No validated edge is currently available", "finding_count": 2, "hypothesis_count": 2},
    "suggested_hypotheses": [{"hypothesis_id": "hyp_001", "statement": "Keep probation separate from exploitation."}],
    "llm_summary": {"available": True, "text": "Estado real: no hay edge validado."},
}

_FAKE_SECURITY_POSTURE = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "env_runtime": {"dotenv_exists": True, "dotenv_example_exists": True},
    "secrets_audit": {"raw_finding_count": 100, "unclassified_count": 90},
    "dependency_audit": {"vulnerability_count": 7, "affected_package_count": 5},
}

_FAKE_RISK_STATUS = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "status": "degraded",
    "execution_allowed": True,
    "paper_only": True,
    "limits": {
        "max_daily_loss_frac": 0.02,
        "max_weekly_drawdown_frac": 0.06,
        "max_total_exposure_frac": 0.70,
    },
    "measures": {
        "daily_loss_frac": 0.01,
        "weekly_drawdown_frac": 0.03,
        "total_exposure_frac": 0.55,
    },
    "hard_violations": [],
    "warnings": ["total_exposure_near_limit"],
}

_FAKE_GOVERNANCE_HEALTH = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "overall_status": "degraded",
    "current_operating_mode": "learning_active",
    "layer_composition": {"active_layers": ["V3", "V4", "V5", "V6", "V7"]},
    "layers": {
        "V3": {"state": "active", "name": "control_layer"},
        "V4": {"state": "active", "name": "change_validation"},
        "V5": {"state": "partial", "name": "risk_contract"},
        "V6": {"state": "active", "name": "meta_governance"},
        "V7": {"state": "active", "name": "learning_feedback"},
        "V8": {"state": "inactive", "name": "validated_edge_promotion"},
    },
    "change_validation": {"last_run_utc": "2026-03-26T12:00:00Z", "last_pipeline_state": "passed"},
    "rollbacks_last_7d": 1,
    "kill_switch": {"mode": "ACTIVE", "active": False},
    "improvement_summary": {"implemented_count": 3, "partial_count": 2, "pending_count": 6},
}

_FAKE_CHANGE_CONTROL = {
    "generated_utc": "2026-03-26T12:00:00Z",
    "summary": {
        "total_changes": 3,
        "promoted_count": 1,
        "reverted_count": 1,
        "pending_count": 1,
        "rollback_count": 1,
        "metric_degraded_count": 1,
        "frozen_recommended": False,
    },
    "entries": [{"change_id": "chg_001", "result": "promoted"}],
}

_FAKE_SESSION_MEMORY = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "session_id": "default",
    "objective": "cerrar la fase actual",
    "important_vars": {"current_focus": "increase_resolved_sample", "top_action": "increase_resolved_sample"},
    "key_files": ["C:\\AI_VAULT\\tmp_agent\\brain_v9\\main.py"],
    "decisions": [{"decision": "seguir con edge validation"}],
    "open_risks": ["sample_not_ready"],
}

_FAKE_RESEARCH_SUMMARY = {
    "updated_utc": "2026-03-26T12:00:00Z",
    "strategies_count": 3,
    "indicators_count": 12,
}

_FAKE_ROADMAP_GOVERNANCE = {
    "current_phase": "paper_exploration",
    "promotion": {},
    "development_status": {"phase": "7"},
}

_FAKE_LEDGER = {
    "entries": [
        {"change_id": "chg_001", "status": "promoted", "objective": "test fix"},
    ],
}

_FAKE_INGESTER_STATUS = {
    "running": True,
    "interval_seconds": 300,
    "consecutive_failures": 0,
    "last_checked_utc": "2026-03-26T12:00:00Z",
    "last_connected": True,
    "last_symbol_count": 5,
    "last_error_count": 0,
}

_FAKE_SNAPSHOT_RESULT = {
    "connected": True,
    "checked_utc": "2026-03-26T12:00:00Z",
    "symbols": {
        "SPY_ETF": {"has_any_tick": True, "last": 520.5},
    },
    "errors": [],
}


# ===========================================================================
# 1-3: Health endpoint
# ===========================================================================

class TestHealthEndpoint:
    def test_healthy(self, client):
        """1. GET /health → 200 when startup done."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "9.0.0"

    def test_initializing(self, client_initializing):
        """2. GET /health → 503 when still initializing."""
        resp = client_initializing.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "initializing"

    def test_startup_failed(self, client_failed):
        """3. GET /health → 503 when startup failed."""
        resp = client_failed.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "startup_failed"
        assert "Ollama" in data["error"]


# ===========================================================================
# 4: Status endpoint
# ===========================================================================

class TestStatusEndpoint:
    def test_status(self, client, monkeypatch):
        """4. GET /status → returns sessions and ready flag."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "active_sessions", {"default": MagicMock(), "user_123": MagicMock()})

        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "default" in data["sessions"]
        assert "user_123" in data["sessions"]
        assert data["ready"] is True
        assert data["version"] == "9.0.0"


# ===========================================================================
# 5-6: Brain utility
# ===========================================================================

class TestBrainUtility:
    def test_brain_utility(self, client, monkeypatch):
        """5. GET /brain/utility → returns utility state."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_utility_state", lambda: _FAKE_UTILITY_STATE)
        monkeypatch.setattr(main_mod, "is_promotion_safe", lambda: (False, "blockers remain"))

        resp = client.get("/brain/utility")
        assert resp.status_code == 200
        data = resp.json()
        assert data["u_score"] == 0.42
        assert data["verdict"] == "hold"
        assert data["can_promote"] is False
        assert data["promotion_reason"] == "blockers remain"

    def test_brain_utility_refresh(self, client, monkeypatch):
        """6. POST /brain/utility/refresh → returns snapshot."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "write_utility_snapshots", lambda: _FAKE_UTILITY_SNAPSHOTS)
        monkeypatch.setattr(main_mod, "refresh_utility_governance_status", lambda: {"ok": True})
        monkeypatch.setattr(main_mod, "promote_roadmap_if_ready", lambda: {"promotion": {}})

        resp = client.post("/brain/utility/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["u_score"] == 0.42


# ===========================================================================
# 7-10: Strategy engine
# ===========================================================================

class TestStrategyEngine:
    def test_features(self, client, monkeypatch):
        """7. GET /brain/strategy-engine/features → returns features."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_strategy_feature_snapshot", lambda: _FAKE_FEATURE_SNAPSHOT)

        resp = client.get("/brain/strategy-engine/features")
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_utc"] == "2026-03-26T12:00:00Z"
        assert len(data["items"]) == 1

    def test_signals(self, client, monkeypatch):
        """8. GET /brain/strategy-engine/signals → returns signals."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_strategy_signal_snapshot", lambda: _FAKE_SIGNAL_SNAPSHOT)

        resp = client.get("/brain/strategy-engine/signals")
        assert resp.status_code == 200
        data = resp.json()
        assert "signals" in data

    def test_ranking(self, client, monkeypatch):
        """9. GET /brain/strategy-engine/ranking → returns ranking."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_strategy_ranking", lambda: _FAKE_RANKING)

        resp = client.get("/brain/strategy-engine/ranking")
        assert resp.status_code == 200
        data = resp.json()
        assert "ranking" in data

    def test_summary(self, client, monkeypatch):
        """10. GET /brain/strategy-engine/summary → returns summary."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)

        resp = client.get("/brain/strategy-engine/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategies_total"] == 5


# ===========================================================================
# 11-12: IBKR ingester endpoints
# ===========================================================================

class TestIBKRIngesterEndpoints:
    def test_ingester_status(self, client, monkeypatch):
        """11. GET /brain/autonomy/ibkr-ingester → returns ingester status."""
        mock_ingester = MagicMock()
        mock_ingester.get_status.return_value = _FAKE_INGESTER_STATUS

        with patch("brain_v9.trading.ibkr_data_ingester.get_ibkr_data_ingester",
                    return_value=mock_ingester):
            resp = client.get("/brain/autonomy/ibkr-ingester")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["running"] is True
        assert data["interval_seconds"] == 300

    def test_trigger_snapshot(self, client, monkeypatch):
        """12. POST /brain/autonomy/ibkr-snapshot → triggers snapshot."""
        with patch("brain_v9.trading.ibkr_data_ingester.run_ibkr_snapshot_async",
                    new_callable=AsyncMock, return_value=_FAKE_SNAPSHOT_RESULT):
            resp = client.post("/brain/autonomy/ibkr-snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["connected"] is True
        assert data["symbols_with_data"] == 1


# ===========================================================================
# 13-15: Research, roadmap, self-improvement
# ===========================================================================

class TestResearchAndGovernance:
    def test_research_summary(self, client, monkeypatch):
        """13. GET /brain/research/summary → returns research summary."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "get_research_summary", lambda: _FAKE_RESEARCH_SUMMARY)

        resp = client.get("/brain/research/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategies_count"] == 3

    def test_roadmap_governance(self, client, monkeypatch):
        """14. GET /brain/roadmap/governance → returns governance status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_roadmap_governance_status", lambda: _FAKE_ROADMAP_GOVERNANCE)

        resp = client.get("/brain/roadmap/governance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_phase"] == "paper_exploration"

    def test_self_improvement_ledger(self, client, monkeypatch):
        """15. GET /brain/self-improvement/ledger → returns ledger."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "get_self_improvement_ledger", lambda: _FAKE_LEDGER)

        resp = client.get("/brain/self-improvement/ledger")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["change_id"] == "chg_001"


# ===========================================================================
# 16: Chat endpoint
# ===========================================================================

class TestChatEndpoint:
    def test_chat_mocked(self, client, monkeypatch):
        """16. POST /chat → returns mocked LLM response."""
        mock_session = MagicMock()
        mock_session.chat = AsyncMock(return_value={
            "content": "Test response from Brain V9",
            "model": "llama3.1:8b",
            "success": True,
        })

        def _fake_get_or_create(sid, sessions):
            sessions[sid] = mock_session
            return mock_session

        # get_or_create_session is lazy-imported inside the /chat handler,
        # so we patch at the source module.
        with patch("brain_v9.core.session.get_or_create_session", side_effect=_fake_get_or_create):
            resp = client.post("/chat", json={
                "message": "Hello",
                "session_id": "test_session",
                "model_priority": "ollama",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] == "Test response from Brain V9"
        assert data["session_id"] == "test_session"
        assert data["model_used"] == "llama3.1:8b"

    def test_agent_uses_model_priority_and_returns_string_result(self, client, monkeypatch):
        import brain_v9.main as main_mod

        mock_session = MagicMock()
        mock_session.llm = MagicMock()

        def _fake_get_or_create(sid, sessions):
            sessions[sid] = mock_session
            return mock_session

        captured = {}

        class _FakeLoop:
            def __init__(self, llm, executor):
                self.llm = llm
                self.executor = executor
                self.history = [{"step": 0, "verified": True}]
                self.MAX_STEPS = 0

            async def run(self, task, context=None):
                captured["task"] = task
                captured["context"] = context
                return {
                    "success": True,
                    "result": [{"status": "ok", "detail": "raw"}],
                    "steps": 1,
                    "summary": "Agent summary",
                    "status": "completed",
                }

            def get_history(self):
                return self.history

        monkeypatch.setattr(main_mod, "_agent_executor", MagicMock())
        monkeypatch.setattr(main_mod, "AgentLoop", _FakeLoop)

        with patch("brain_v9.core.session.get_or_create_session", side_effect=_fake_get_or_create):
            resp = client.post("/agent", json={
                "task": "check brain",
                "session_id": "agent_session",
                "model_priority": "gpt4",
                "max_steps": 2,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"] == "Agent summary"
        assert data["raw_result"] == [{"status": "ok", "detail": "raw"}]
        assert captured["context"] == {"model_priority": "gpt4"}

    def test_agent_uses_canonical_brain_audit_fastpath(self, client, monkeypatch):
        import brain_v9.main as main_mod

        class _FakeSession:
            llm = object()

            @staticmethod
            def _is_deep_brain_analysis_query(message):
                return "analiza profundamente" in message

            @staticmethod
            def _deep_brain_analysis_fastpath():
                return {"content": "**Analisis profundo del brain**\n  grounded"}

            @staticmethod
            def _is_self_build_query(message):
                return False

            @staticmethod
            def _is_consciousness_query(message):
                return False

            @staticmethod
            def _is_brain_status_query(message):
                return False

        def _boom(*args, **kwargs):
            raise AssertionError("AgentLoop should not be called for canonical audits")

        monkeypatch.setattr(main_mod, "_agent_executor", MagicMock())
        monkeypatch.setattr(main_mod, "AgentLoop", _boom)

        with patch("brain_v9.core.session.get_or_create_session", return_value=_FakeSession()):
            resp = client.post("/agent", json={
                "task": "Analiza profundamente el estado del brain y sus implicaciones actuales.",
                "session_id": "audit_fastpath",
                "model_priority": "chat",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "canonical_audit"
        assert data["steps"] == 0
        assert "Analisis profundo del brain" in data["result"]

    def test_agent_uses_canonical_self_build_fastpath(self, client, monkeypatch):
        import brain_v9.main as main_mod

        class _FakeSession:
            llm = object()

            @staticmethod
            def _is_deep_brain_analysis_query(message):
                return False

            @staticmethod
            def _is_self_build_query(message):
                return "autoconstruccion" in message

            @staticmethod
            def _self_build_fastpath():
                return {"content": "**Autoconstruccion**\n  lista para promover cambios autonomos: `NO`"}

            @staticmethod
            def _is_consciousness_query(message):
                return False

            @staticmethod
            def _is_brain_status_query(message):
                return False

        def _boom(*args, **kwargs):
            raise AssertionError("AgentLoop should not be called for canonical audits")

        monkeypatch.setattr(main_mod, "_agent_executor", MagicMock())
        monkeypatch.setattr(main_mod, "AgentLoop", _boom)

        with patch("brain_v9.core.session.get_or_create_session", return_value=_FakeSession()):
            resp = client.post("/agent", json={
                "task": "Evalua la autoconstruccion actual del sistema.",
                "session_id": "self_build_fastpath",
                "model_priority": "chat",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "canonical_audit"
        assert data["steps"] == 0
        assert "Autoconstruccion" in data["result"]

    def test_agent_uses_canonical_risk_fastpath(self, client, monkeypatch):
        import brain_v9.main as main_mod

        class _FakeSession:
            llm = object()

            @staticmethod
            def _is_deep_brain_analysis_query(message): return False
            @staticmethod
            def _is_deep_risk_analysis_query(message): return "riesgo" in message
            @staticmethod
            def _deep_risk_analysis_fastpath(): return {"content": "**Analisis profundo de riesgo**\n  grounded"}
            @staticmethod
            def _is_deep_edge_analysis_query(message): return False
            @staticmethod
            def _is_deep_strategy_analysis_query(message): return False
            @staticmethod
            def _is_deep_pipeline_analysis_query(message): return False
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
                "task": "Analiza profundamente el riesgo actual del sistema.",
                "session_id": "risk_fastpath",
                "model_priority": "chat",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "canonical_audit"
        assert "Analisis profundo de riesgo" in data["result"]

    def test_agent_uses_canonical_strategy_fastpath(self, client, monkeypatch):
        import brain_v9.main as main_mod

        class _FakeSession:
            llm = object()

            @staticmethod
            def _is_deep_brain_analysis_query(message): return False
            @staticmethod
            def _is_deep_risk_analysis_query(message): return False
            @staticmethod
            def _is_deep_edge_analysis_query(message): return False
            @staticmethod
            def _is_deep_strategy_analysis_query(message): return "strategy engine" in message
            @staticmethod
            def _deep_strategy_analysis_fastpath(): return {"content": "**Analisis profundo del strategy engine**\n  grounded"}
            @staticmethod
            def _is_deep_pipeline_analysis_query(message): return False
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
                "task": "Audita profundamente el strategy engine.",
                "session_id": "strategy_fastpath",
                "model_priority": "chat",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"] == "canonical_audit"
        assert "Analisis profundo del strategy engine" in data["result"]


# ===========================================================================
# 17-19: Trading router
# ===========================================================================

class TestTradingRouter:
    def test_trading_health(self, client, monkeypatch):
        """17. GET /trading/health → returns mocked health per connector."""
        import brain_v9.trading.router as tr

        async def _fake_health():
            return {"status": "ok", "connected": True}

        mock_tiingo = MagicMock(); mock_tiingo.check_health = _fake_health
        mock_qc = MagicMock(); mock_qc.check_health = _fake_health
        mock_ibkr = MagicMock(); mock_ibkr.check_health = _fake_health
        mock_po = MagicMock(); mock_po.check_health = _fake_health

        monkeypatch.setattr(tr, "_get_tiingo", lambda: mock_tiingo)
        monkeypatch.setattr(tr, "_get_qc", lambda: mock_qc)
        monkeypatch.setattr(tr, "_get_ibkr", lambda: mock_ibkr)
        monkeypatch.setattr(tr, "_get_po", lambda: mock_po)

        resp = client.get("/trading/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "tiingo" in data
        assert "ibkr" in data
        assert data["tiingo"]["status"] == "ok"

    def test_trading_policy_default(self, client, monkeypatch):
        """18. GET /trading/policy → returns default when file missing."""
        import brain_v9.trading.router as tr

        # Force policy file to not exist
        monkeypatch.setattr(tr, "TRADING_POLICY_PATH", MagicMock(exists=MagicMock(return_value=False)))

        resp = client.get("/trading/policy")
        assert resp.status_code == 200
        data = resp.json()
        assert data["global_rules"]["paper_only"] is True
        assert data["global_rules"]["live_trading_forbidden"] is True

    def test_platforms_summary(self, client, monkeypatch):
        """19. GET /trading/platforms/summary → mocked dashboard."""
        import brain_v9.trading.router as tr

        mock_dashboard = MagicMock()
        mock_dashboard.get_all_platforms_summary.return_value = {
            "platforms": ["ibkr", "pocket_option", "internal"],
            "updated_utc": "2026-03-26T12:00:00Z",
        }
        monkeypatch.setattr(tr, "_get_dashboard", lambda: mock_dashboard)

        resp = client.get("/trading/platforms/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "platforms" in data
        assert len(data["platforms"]) == 3


# ===========================================================================
# 20-21: Autonomy router
# ===========================================================================

class TestAutonomyRouter:
    def test_autonomy_status(self, client, monkeypatch):
        """20. GET /autonomy/status → returns autonomy manager status."""
        from brain_v9.autonomy import router as auto_router

        mock_manager = MagicMock()
        mock_manager.get_status.return_value = {
            "running": True,
            "cycle_count": 42,
            "last_cycle_utc": "2026-03-26T12:00:00Z",
        }
        monkeypatch.setattr(auto_router, "get_manager", lambda: mock_manager)

        resp = client.get("/autonomy/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["running"] is True
        assert data["cycle_count"] == 42

    def test_autonomy_cycle(self, client, monkeypatch):
        """21. GET /autonomy/cycle → returns latest autonomy cycle snapshot."""
        from brain_v9.autonomy import router as auto_router

        mock_manager = MagicMock()
        mock_manager.get_cycle_snapshot.return_value = {
            "schema_version": "autonomy_cycle_v1",
            "cycle_id": "autocycle_000042",
            "cycle_count": 42,
            "current_stage": "done",
            "result": "success",
        }
        monkeypatch.setattr(auto_router, "get_manager", lambda: mock_manager)

        resp = client.get("/autonomy/cycle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cycle_id"] == "autocycle_000042"
        assert data["result"] == "success"

    def test_autonomy_reports(self, client, monkeypatch):
        """22. GET /autonomy/reports → returns recent reports."""
        from brain_v9.autonomy import router as auto_router

        mock_manager = MagicMock()
        mock_manager.get_recent_reports.return_value = [
            {"cycle": 40, "actions": 2},
            {"cycle": 41, "actions": 1},
        ]
        monkeypatch.setattr(auto_router, "get_manager", lambda: mock_manager)

        resp = client.get("/autonomy/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


# ===========================================================================
# 22-25: Governance status endpoints
# ===========================================================================

class TestGovernanceEndpoints:
    def test_meta_improvement_status(self, client, monkeypatch):
        """22. GET /brain/meta-improvement/status → returns status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_meta_improvement_status",
                            lambda: {"status": "active", "improvements": 3})

        resp = client.get("/brain/meta-improvement/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"

    def test_chat_product_status(self, client, monkeypatch):
        """23. GET /brain/chat-product/status → returns status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_chat_product_status",
                            lambda: {"product": "brain_chat", "quality_score": 0.7})

        resp = client.get("/brain/chat-product/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "brain_chat"

    def test_utility_governance_status(self, client, monkeypatch):
        """24. GET /brain/utility-governance/status → returns status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_utility_governance_status",
                            lambda: {"governance": "active", "violations": 0})

        resp = client.get("/brain/utility-governance/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["governance"] == "active"

    def test_meta_governance_status(self, client, monkeypatch):
        """24b. GET /brain/meta-governance/status → returns status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "get_meta_governance_status_latest",
                            lambda: {"top_action": "increase_resolved_sample", "current_focus": {"action": "increase_resolved_sample"}})

        resp = client.get("/brain/meta-governance/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_action"] == "increase_resolved_sample"

    def test_session_memory(self, client, monkeypatch):
        """24c. GET /brain/session-memory → returns canonical session memory."""
        import brain_v9.core.session_memory_state as sms

        monkeypatch.setattr(sms, "build_session_memory", lambda session_id="default": _FAKE_SESSION_MEMORY)
        monkeypatch.setattr(sms, "get_session_memory_latest", lambda session_id="default": _FAKE_SESSION_MEMORY)

        resp = client.get("/brain/session-memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "default"
        assert data["important_vars"]["top_action"] == "increase_resolved_sample"

    def test_post_bl_roadmap_status(self, client, monkeypatch):
        """25. GET /brain/post-bl-roadmap/status → returns status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "read_post_bl_roadmap_status",
                            lambda: {"phase": "post_baseline", "items_done": 5})

        resp = client.get("/brain/post-bl-roadmap/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "post_baseline"


# ===========================================================================
# 26: Self-diagnostic
# ===========================================================================

class TestSelfDiagnostic:
    def test_self_diagnostic_get(self, client, monkeypatch):
        """26. GET /self-diagnostic → returns diagnostic report."""
        mock_diag = MagicMock()
        mock_diag.get_status_report.return_value = {
            "healthy": True,
            "checks": 5,
            "failures": 0,
        }

        with patch("brain_v9.core.self_diagnostic.get_self_diagnostic",
                    return_value=mock_diag):
            resp = client.get("/self-diagnostic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["failures"] == 0


# ===========================================================================
# 27-29: Strategy engine additional
# ===========================================================================

class TestStrategyEngineAdditional:
    def test_expectancy(self, client, monkeypatch):
        """27. GET /brain/strategy-engine/expectancy → returns expectancy."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_expectancy_snapshot", lambda: None)
        monkeypatch.setattr(main_mod, "read_expectancy_snapshot",
                            lambda: {"strategies": [], "updated_utc": "2026-03-26T12:00:00Z"})

        resp = client.get("/brain/strategy-engine/expectancy")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data

    def test_candidates(self, client, monkeypatch):
        """28. GET /brain/strategy-engine/candidates → returns candidates."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_strategy_candidates",
                            lambda: [{"id": "strat_001", "state": "paper_candidate"}])

        resp = client.get("/brain/strategy-engine/candidates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_archive(self, client, monkeypatch):
        """29. GET /brain/strategy-engine/archive → returns archive state."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_strategy_archive_state",
                            lambda: {"archived": 2, "refuted": 1})

        resp = client.get("/brain/strategy-engine/archive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["archived"] == 2

    def test_edge_validation(self, client, monkeypatch):
        """GET /brain/strategy-engine/edge-validation → returns edge validation snapshot."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_edge_validation_state", lambda: _FAKE_EDGE_VALIDATION)

        resp = client.get("/brain/strategy-engine/edge-validation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["validated_count"] == 1
        assert data["items"][0]["edge_state"] == "validated"

    def test_context_edge_validation(self, client, monkeypatch):
        """GET /brain/strategy-engine/context-edge-validation → returns current context edge snapshot."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_context_edge_validation_state", lambda: _FAKE_CONTEXT_EDGE_VALIDATION)

        resp = client.get("/brain/strategy-engine/context-edge-validation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["validated_count"] == 1
        assert data["items"][0]["current_context_edge_state"] == "validated"

    def test_pipeline_integrity(self, client, monkeypatch):
        """GET /brain/strategy-engine/pipeline-integrity → returns pipeline integrity snapshot."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_pipeline_integrity_state", lambda: _FAKE_PIPELINE_INTEGRITY)

        resp = client.get("/brain/strategy-engine/pipeline-integrity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["status"] == "healthy"
        assert data["stages"]["decision"]["top_action"] == "increase_resolved_sample"

    def test_active_catalog(self, client, monkeypatch):
        """GET /brain/strategy-engine/active-catalog → returns operational catalog snapshot."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "read_active_strategy_catalog_state", lambda: _FAKE_ACTIVE_CATALOG)

        resp = client.get("/brain/strategy-engine/active-catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["operational_count"] == 1
        assert data["items"][0]["catalog_state"] == "probation"

    def test_post_trade_analysis(self, client, monkeypatch):
        """31. GET /brain/strategy-engine/post-trade-analysis → returns canonical post-trade analysis."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_post_trade_analysis_snapshot", lambda: _FAKE_POST_TRADE_ANALYSIS)

        resp = client.get("/brain/strategy-engine/post-trade-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["recent_resolved_trades"] == 3
        assert data["summary"]["next_focus"] == "continue_probation"

    def test_post_trade_hypotheses(self, client, monkeypatch):
        """32. GET /brain/strategy-engine/post-trade-hypotheses → returns canonical post-trade hypothesis synthesis."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_post_trade_hypothesis_snapshot", AsyncMock(return_value=_FAKE_POST_TRADE_HYPOTHESES))

        resp = client.get("/brain/strategy-engine/post-trade-hypotheses")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["finding_count"] == 2
        assert data["llm_summary"]["available"] is True

    def test_security_posture(self, client, monkeypatch):
        """GET /brain/security/posture → returns canonical security posture."""
        import brain_v9.brain.security_posture as sp
        monkeypatch.setattr(sp, "build_security_posture", lambda refresh_dependency_audit=True: _FAKE_SECURITY_POSTURE)
        monkeypatch.setattr(sp, "get_security_posture_latest", lambda: _FAKE_SECURITY_POSTURE)

        resp = client.get("/brain/security/posture")
        assert resp.status_code == 200
        data = resp.json()
        assert data["secrets_audit"]["raw_finding_count"] == 100
        assert data["dependency_audit"]["vulnerability_count"] == 7

    def test_risk_status(self, client, monkeypatch):
        """GET /brain/risk/status → returns canonical risk-contract status."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_risk_contract_status", lambda refresh=True: _FAKE_RISK_STATUS)
        monkeypatch.setattr(main_mod, "read_risk_contract_status", lambda: _FAKE_RISK_STATUS)

        resp = client.get("/brain/risk/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["warnings"] == ["total_exposure_near_limit"]

    def test_governance_health(self, client, monkeypatch):
        """GET /brain/governance/health → returns canonical governance health."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_governance_health", lambda refresh=True: _FAKE_GOVERNANCE_HEALTH)
        monkeypatch.setattr(main_mod, "read_governance_health", lambda: _FAKE_GOVERNANCE_HEALTH)

        resp = client.get("/brain/governance/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "degraded"
        assert data["current_operating_mode"] == "learning_active"
        assert data["kill_switch"]["mode"] == "ACTIVE"

    def test_change_control_scorecard(self, client, monkeypatch):
        """GET /brain/change-control/scorecard → returns canonical change-control scorecard."""
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "build_change_scorecard", lambda: _FAKE_CHANGE_CONTROL)
        monkeypatch.setattr(main_mod, "get_change_scorecard_latest", lambda: _FAKE_CHANGE_CONTROL)

        resp = client.get("/brain/change-control/scorecard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_changes"] == 3
        assert data["entries"][0]["change_id"] == "chg_001"

    def test_control_layer_status(self, client, monkeypatch):
        import brain_v9.main as main_mod
        payload = {
            "mode": "ACTIVE",
            "reason": "no_control_trigger",
            "execution_allowed": True,
        }
        monkeypatch.setattr(main_mod, "build_control_layer_status", lambda refresh_change_scorecard=True: payload)
        monkeypatch.setattr(main_mod, "get_control_layer_status_latest", lambda: payload)

        resp = client.get("/brain/control-layer/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "ACTIVE"

    def test_control_layer_freeze(self, client, monkeypatch):
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "freeze_control_layer", lambda reason, source="api": {
            "mode": "FROZEN",
            "reason": reason,
            "execution_allowed": False,
        })

        resp = client.post("/brain/control-layer/freeze?reason=test_freeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "FROZEN"
        assert data["reason"] == "test_freeze"

    def test_control_layer_unfreeze(self, client, monkeypatch):
        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "unfreeze_control_layer", lambda reason, source="api": {
            "mode": "ACTIVE",
            "reason": reason,
            "execution_allowed": True,
        })

        resp = client.post("/brain/control-layer/unfreeze?reason=test_unfreeze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "ACTIVE"
        assert data["reason"] == "test_unfreeze"

    def test_control_layer_freeze_denied_for_non_local_without_token(self, monkeypatch):
        async def _noop_startup():
            pass

        import brain_v9.main as main_mod
        monkeypatch.setattr(main_mod, "_startup_background", _noop_startup)
        monkeypatch.setattr(main_mod, "_startup_done", True)
        monkeypatch.setattr(main_mod, "_startup_error", None)
        monkeypatch.setattr(main_mod, "active_sessions", {})
        monkeypatch.delenv("BRAIN_ADMIN_TOKEN", raising=False)

        from fastapi.testclient import TestClient
        with TestClient(main_mod.app, client=("203.0.113.10", 50000)) as remote_client:
            resp = remote_client.post("/brain/control-layer/freeze?reason=remote_test")

        assert resp.status_code == 403


# ===========================================================================
# 30: Operations (combined) endpoint
# ===========================================================================

class TestOperationsEndpoint:
    def test_operations(self, client, monkeypatch):
        """30. GET /brain/operations → combined operations endpoint."""
        import brain_v9.main as main_mod

        monkeypatch.setattr(main_mod, "read_utility_state", lambda: _FAKE_UTILITY_STATE)
        monkeypatch.setattr(main_mod, "is_promotion_safe", lambda: (False, "blockers"))
        monkeypatch.setattr(main_mod, "get_research_summary", lambda: _FAKE_RESEARCH_SUMMARY)
        monkeypatch.setattr(main_mod, "refresh_strategy_engine", lambda: _FAKE_ENGINE_REFRESH)
        monkeypatch.setattr(main_mod, "get_self_improvement_ledger", lambda: _FAKE_LEDGER)
        monkeypatch.setattr(main_mod, "read_roadmap_governance_status", lambda: _FAKE_ROADMAP_GOVERNANCE)
        monkeypatch.setattr(main_mod, "read_meta_improvement_status", lambda: {"status": "ok"})
        monkeypatch.setattr(main_mod, "read_chat_product_status", lambda: {"product": "ok"})
        monkeypatch.setattr(main_mod, "read_utility_governance_status", lambda: {"gov": "ok"})
        monkeypatch.setattr(main_mod, "read_post_bl_roadmap_status", lambda: {"post": "ok"})

        # Mock the trading router functions imported inside brain_operations
        import brain_v9.trading.router as tr

        async def _fake_health():
            return {"status": "ok", "connected": True}

        mock_tiingo = MagicMock(); mock_tiingo.check_health = _fake_health
        mock_qc = MagicMock(); mock_qc.check_health = _fake_health
        mock_ibkr = MagicMock(); mock_ibkr.check_health = _fake_health
        mock_po = MagicMock(); mock_po.check_health = _fake_health

        monkeypatch.setattr(tr, "_get_tiingo", lambda: mock_tiingo)
        monkeypatch.setattr(tr, "_get_qc", lambda: mock_qc)
        monkeypatch.setattr(tr, "_get_ibkr", lambda: mock_ibkr)
        monkeypatch.setattr(tr, "_get_po", lambda: mock_po)

        resp = client.get("/brain/operations")
        assert resp.status_code == 200
        data = resp.json()
        assert "utility" in data
        assert "research" in data
        assert "strategy_engine" in data
        assert "trading" in data
        assert "self_improvement" in data
        assert data["utility"]["u_score"] == 0.42
