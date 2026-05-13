"""
Tests for brain_v9.core.session — BrainSession v5 (Token-Aware).

Covers:
  - Slash commands: /help, /status, /dev, /clear, /model, unknown
  - Agent routing: word-boundary regex matching (no false positives)
  - Developer mode: transparency block appended
  - Fastpath: utility, health
  - _normalize helper
  - Token-aware context truncation (_truncate_to_budget, _truncate_message)
  - Context budget computation (_context_budget)
"""
import json
import re
import asyncio
import pytest
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

from brain_v9.core.session import (
    BrainSession,
    _normalize,
    SLASH_COMMANDS,
    AGENT_KEYWORDS,
    _AGENT_PATTERNS,
    get_or_create_session,
)


# ── _normalize ────────────────────────────────────────────────────────────────

class TestNormalize:

    def test_both_fields_present(self):
        r = _normalize({"content": "a", "response": "b"})
        assert r["content"] == "a"
        assert r["response"] == "b"

    def test_content_only(self):
        r = _normalize({"content": "a"})
        assert r["content"] == "a"
        assert r["response"] == "a"

    def test_response_only(self):
        r = _normalize({"response": "b"})
        assert r["content"] == "b"
        assert r["response"] == "b"

    def test_neither_uses_fallback(self):
        r = _normalize({}, fallback_content="fallback")
        assert r["content"] == "fallback"
        assert r["response"] == "fallback"

    def test_empty_strings_use_fallback(self):
        r = _normalize({"content": "", "response": ""}, fallback_content="fb")
        assert r["content"] == "fb"
        assert r["response"] == "fb"


class TestChatSanitization:

    def test_sanitize_llm_chat_response_removes_fake_tool_lines(self):
        raw = (
            "Conclusion valida.\n\n"
            "Utilice la herramienta de inferencia para responder.\n"
            "La conclusion se sigue de las premisas."
        )
        cleaned = BrainSession._sanitize_llm_chat_response(raw)
        assert "herramienta" not in cleaned.lower()
        assert "Conclusion valida." in cleaned
        assert "La conclusion se sigue de las premisas." in cleaned


# ── Slash commands ────────────────────────────────────────────────────────────

class TestSlashCommands:

    @pytest.fixture
    def session(self, isolated_base_path):
        return BrainSession("test_cmd")

    def test_help_command(self, session):
        result = session._handle_command("/help")
        assert result["success"] is True
        assert result["model"] == "system"
        # All commands should be listed
        for cmd in SLASH_COMMANDS:
            assert cmd in result["content"]

    def test_status_command(self, session, isolated_base_path):
        """Status should work even with missing state files (returns N/A)."""
        result = session._handle_command("/status")
        assert result["success"] is True
        assert "Brain V9" in result["content"]
        assert session.session_id in result["content"]

    def test_status_with_real_state(self, session, isolated_base_path):
        """Status should read from real state files."""
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        utility_data = {"u_score": 0.73, "verdict": "no_promote", "promotion_gate": {"blockers": ["drawdown"]}}
        (state_dir / "utility_u_latest.json").write_text(json.dumps(utility_data))

        result = session._handle_command("/status")
        assert "0.73" in result["content"]
        assert "drawdown" in result["content"]

    def test_edge_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        edge_data = {"summary": {"validated_count": 1, "probation_count": 2, "blocked_count": 3}}
        (state_dir / "edge_validation_latest.json").write_text(json.dumps(edge_data))

        result = session._handle_command("/edge")
        assert result["success"] is True
        assert "validated" in result["content"]
        assert "1" in result["content"]

    def test_ranking_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        ranking_data = {
            "top_action": "run_probation_carefully",
            "ranked": [{"strategy_id": "s1", "edge_state": "probation", "execution_ready_now": False}],
            "probation_candidate": {"strategy_id": "s1"},
        }
        (state_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps(ranking_data))

        result = session._handle_command("/ranking")
        assert result["success"] is True
        assert "run_probation_carefully" in result["content"]
        assert "s1" in result["content"]

    def test_posttrade_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        analysis_data = {"summary": {"recent_resolved_trades": 7, "wins": 2, "losses": 5, "net_profit": -12.5, "duplicate_anomaly_count": 1, "next_focus": "audit_duplicate_execution"}}
        (state_dir / "post_trade_analysis_latest.json").write_text(json.dumps(analysis_data))

        result = session._handle_command("/posttrade")
        assert result["success"] is True
        assert "Post-Trade Analysis" in result["content"]
        assert "audit_duplicate_execution" in result["content"]

    def test_pipeline_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        pipeline_data = {
            "summary": {
                "status": "healthy",
                "pipeline_ok": True,
                "signals_count": 4,
                "stale_signal_count": 0,
                "stale_signal_without_marker_count": 0,
                "ledger_entries": 6,
                "resolved_entries": 5,
                "pending_entries": 1,
                "duplicate_trade_count": 0,
                "scorecard_resolved_match": True,
                "scorecard_open_match": True,
                "scorecards_fresh_after_resolution": True,
                "utility_fresh_after_scorecards": True,
                "decision_fresh_after_utility": True,
                "platform_isolation_ok": True,
                "last_resolved_utc": "2026-03-27T20:00:00Z",
                "top_action": "increase_resolved_sample",
            },
            "stages": {
                "utility": {"u_score": -0.2},
                "decision": {"top_action": "increase_resolved_sample"},
            },
            "anomalies": [],
        }
        (state_dir / "pipeline_integrity_latest.json").write_text(json.dumps(pipeline_data))

        result = session._handle_command("/pipeline")
        assert result["success"] is True
        assert "Trading Pipeline Integrity" in result["content"]
        assert "healthy" in result["content"]
        assert "increase_resolved_sample" in result["content"]

    def test_risk_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "risk"
        state_dir.mkdir(parents=True, exist_ok=True)
        risk_data = {
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
                "current_cash": 425.0,
                "committed_cash": 125.0,
                "base_capital": 500.0,
            },
            "control_layer": {"mode": "ACTIVE", "reason": "ok"},
            "utility": {"u_score": -0.2, "verdict": "no_promote"},
            "hard_violations": [],
            "warnings": ["total_exposure_near_limit"],
        }
        (state_dir / "risk_contract_status_latest.json").write_text(json.dumps(risk_data))

        result = session._handle_command("/risk")
        assert result["success"] is True
        assert "Risk Contract" in result["content"]
        assert "total_exposure_near_limit" in result["content"]

    def test_governance_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        governance = {
            "overall_status": "degraded",
            "current_operating_mode": "learning_active",
            "layers": {
                "V3": {"state": "active"},
                "V4": {"state": "active"},
                "V5": {"state": "partial"},
                "V6": {"state": "active"},
                "V7": {"state": "active"},
                "V8": {"state": "inactive"},
            },
            "change_validation": {"last_run_utc": "2026-03-27T20:00:00Z", "last_pipeline_state": "passed"},
            "rollbacks_last_7d": 1,
            "kill_switch": {"mode": "ACTIVE"},
            "improvement_summary": {"implemented_count": 3, "partial_count": 2, "pending_count": 6},
        }
        (state_dir / "governance_health_latest.json").write_text(json.dumps(governance), encoding="utf-8")

        result = session._handle_command("/governance")
        assert result["success"] is True
        assert "Governance Health" in result["content"]
        assert "learning_active" in result["content"]
        assert "implemented" in result["content"]

    def test_hypothesis_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        synth_data = {
            "summary": {"top_finding": "No validated edge is currently available", "finding_count": 2, "hypothesis_count": 2, "next_focus": "continue_probation"},
            "suggested_hypotheses": [{"statement": "Keep probation separate from exploitation."}],
            "llm_summary": {"available": True},
        }
        (state_dir / "post_trade_hypotheses_latest.json").write_text(json.dumps(synth_data))

        result = session._handle_command("/hypothesis")
        assert result["success"] is True
        assert "Post-Trade Hypotheses" in result["content"]
        assert "Keep probation separate" in result["content"]

    def test_security_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "security"
        state_dir.mkdir(parents=True, exist_ok=True)
        posture = {
            "env_runtime": {"dotenv_exists": True, "dotenv_example_exists": True, "gitignore_protects_dotenv": True, "gitignore_protects_secrets": True},
            "secrets_audit": {"raw_finding_count": 100, "unclassified_count": 90},
            "secrets_triage": {"actionable_candidate_count": 4, "likely_false_positive_count": 96, "stale_actionable_candidate_count": 2},
            "secret_source_audit": {"duplicate_source_count": 1, "mismatch_count": 1, "json_only_count": 2},
            "legacy_secret_files": {"mapped_json_fallback_count": 3, "loose_secret_file_count": 1},
            "legacy_runtime_refs": {"env_bat_reference_count": 0},
            "dependency_audit": {"vulnerability_count": 7, "patchable_vulnerability_count": 6, "upstream_blocked_vulnerability_count": 1, "affected_package_count": 5},
        }
        (state_dir / "security_posture_latest.json").write_text(json.dumps(posture))

        result = session._handle_command("/security")
        assert result["success"] is True
        assert "Security Posture" in result["content"]
        assert "100" in result["content"]
        assert "7" in result["content"]
        assert "3" in result["content"]

    def test_control_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        scorecard = {
            "summary": {
                "total_changes": 4,
                "promoted_count": 2,
                "reverted_count": 1,
                "pending_count": 1,
                "rollback_count": 1,
                "metric_degraded_count": 1,
                "frozen_recommended": False,
            },
            "entries": [{"change_id": "chg_123", "result": "promoted"}],
        }
        control = {"mode": "ACTIVE", "reason": "no_control_trigger"}
        (state_dir / "change_scorecard.json").write_text(json.dumps(scorecard))
        (state_dir / "control_layer_status.json").write_text(json.dumps(control))

        result = session._handle_command("/control")
        assert result["success"] is True
        assert "Change Control" in result["content"]
        assert "ACTIVE" in result["content"]
        assert "chg_123" in result["content"]

    def test_memory_command(self, session, isolated_base_path):
        payload = {
            "session_id": "test_cmd",
            "objective": "cerrar la fase actual",
            "important_vars": {
                "current_focus": "increase_resolved_sample",
                "top_action": "increase_resolved_sample",
                "message_count": 12,
                "recent_exchange_count": 6,
            },
            "key_files": ["C:\\AI_VAULT\\tmp_agent\\brain_v9\\main.py"],
            "decisions": [{"decision": "seguir con edge validation"}],
            "open_risks": ["sample_not_ready"],
        }
        with patch("brain_v9.core.session.get_session_memory_latest", return_value=payload):
            result = session._handle_command("/memory")
        assert result["success"] is True
        assert "Session Memory" in result["content"]
        assert "cerrar la fase actual" in result["content"]
        assert "increase_resolved_sample" in result["content"]

    def test_priority_command(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "top_action": "increase_resolved_sample",
            "current_focus": {
                "action": "increase_resolved_sample",
                "focus_lock_active": True,
                "focus_switch_allowed": False,
            },
            "top_priority": {
                "action": "increase_resolved_sample",
                "priority": "HIGH",
                "priority_score": 42.0,
            },
            "allocator": {
                "trading": 35,
                "stability_control": 25,
                "improvement_autobuild": 20,
                "observability": 15,
                "exploration": 5,
            },
            "discipline": {"optimization_allowed": False, "optimize_blockers": ["resolved_sample_below_15"]},
            "system_profile": {"consecutive_skips": 3, "validated_count": 0, "probation_count": 2},
        }
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps(meta))

        result = session._handle_command("/priority")
        assert result["success"] is True
        assert "Meta-Governance" in result["content"]
        assert "increase_resolved_sample" in result["content"]
        assert "42.0" in result["content"]

    def test_freeze_command(self, session, monkeypatch):
        import brain_v9.brain.control_layer as cl

        monkeypatch.setattr(cl, "freeze_control_layer", lambda reason, source="user": {
            "mode": "FROZEN",
            "reason": reason,
        })
        result = session._handle_command("/freeze test_reason")
        assert result["success"] is True
        assert "FROZEN" in result["content"]

    def test_unfreeze_command(self, session, monkeypatch):
        import brain_v9.brain.control_layer as cl

        monkeypatch.setattr(cl, "unfreeze_control_layer", lambda reason, source="user": {
            "mode": "ACTIVE",
            "reason": reason,
        })
        result = session._handle_command("/unfreeze resume_reason")
        assert result["success"] is True
        assert "ACTIVE" in result["content"]

    def test_dev_on(self, session):
        result = session._handle_command("/dev on")
        assert session.dev_mode is True
        assert "activado" in result["content"]

    def test_dev_off(self, session):
        session.dev_mode = True
        result = session._handle_command("/dev off")
        assert session.dev_mode is False
        assert "desactivado" in result["content"]

    def test_dev_no_arg_shows_status(self, session):
        result = session._handle_command("/dev")
        assert "off" in result["content"]
        session.dev_mode = True
        result = session._handle_command("/dev")
        assert "on" in result["content"]

    def test_clear_command(self, session):
        # Directly populate short_term (save() is async; this test is about /clear)
        session.memory.short_term.append({"role": "user", "content": "hello"})
        assert len(session.memory.short_term) > 0

        result = session._handle_command("/clear")
        assert result["success"] is True
        assert len(session.memory.short_term) == 0

    def test_model_change(self, session):
        result = session._handle_command("/model agent")
        assert session._model_priority == "agent"
        assert "agent" in result["content"]

    def test_model_invalid(self, session):
        old = session._model_priority
        result = session._handle_command("/model banana")
        assert session._model_priority == old  # unchanged
        assert "invalido" in result["content"]

    def test_model_no_arg_shows_current(self, session):
        result = session._handle_command("/model")
        assert session._model_priority in result["content"]

    def test_unknown_command(self, session):
        result = session._handle_command("/banana")
        assert result["success"] is True
        assert "desconocido" in result["content"]
        assert "/help" in result["content"]


# ── Agent routing (word-boundary regex) ───────────────────────────────────────

class TestAgentRouting:

    @pytest.fixture
    def session(self, isolated_base_path):
        return BrainSession("test_route")

    def test_exact_keyword_matches(self, session):
        """Known agent keywords should trigger agent route."""
        assert session._should_use_agent("revisa el sistema", "CONVERSATION") is True
        assert session._should_use_agent("diagnostica el puerto 8090", "CONVERSATION") is True
        assert session._should_use_agent("que esta corriendo en el dashboard", "CONVERSATION") is True

    def test_no_false_positives_on_substrings(self, session):
        """Words that contain agent keywords as substrings should NOT match."""
        # "log" should not match in "lograr" or "logica"
        assert session._should_use_agent("voy a lograr mis metas", "CONVERSATION") is False
        assert session._should_use_agent("la logica es simple", "CONVERSATION") is False

    def test_intent_triggers_agent(self, session):
        """SYSTEM, CODE and COMMAND intents should trigger agent."""
        assert session._should_use_agent("anything", "SYSTEM") is True
        assert session._should_use_agent("anything", "CODE") is True
        assert session._should_use_agent("anything", "COMMAND") is True

    def test_abstract_analysis_intent_stays_llm(self, session):
        assert session._should_use_agent("deduce this syllogism", "ANALYSIS") is False

    def test_abstract_reasoning_query_detection(self, session):
        assert session._is_abstract_reasoning_query("si todos los mamiferos son animales, puedes concluir algo?") is True
        assert session._is_abstract_reasoning_query("revisa el dashboard") is False

    def test_conversation_intent_no_keywords_stays_llm(self, session):
        """CONVERSATION intent without keywords should NOT trigger agent."""
        assert session._should_use_agent("hola como estas", "CONVERSATION") is False
        assert session._should_use_agent("hoy hace buen dia", "CONVERSATION") is False

    def test_trading_intent_routes_to_agent(self, session):
        """TRADING intent should trigger agent (P3-08 fix)."""
        assert session._should_use_agent("que piensas del mercado", "TRADING") is True
        assert session._should_use_agent("how is the market", "TRADING") is True

    def test_regex_patterns_are_compiled(self):
        """All patterns should be compiled regex objects."""
        for p in _AGENT_PATTERNS:
            assert isinstance(p, re.Pattern)


# ── Developer mode ────────────────────────────────────────────────────────────

class TestDevMode:

    @pytest.fixture
    def session(self, isolated_base_path):
        return BrainSession("test_dev")

    def test_dev_block_not_added_when_off(self, session):
        result = {"content": "hello", "response": "hello", "route": "llm", "intent": "CONVERSATION"}
        out = session._maybe_dev_block(result)
        assert "[DEV]" not in out["content"]

    def test_dev_block_added_when_on(self, session):
        session.dev_mode = True
        result = {
            "content": "hello", "response": "hello",
            "route": "llm", "intent": "CONVERSATION",
            "model_used": "llama8b", "success": True,
        }
        out = session._maybe_dev_block(result)
        assert "[DEV]" in out["content"]
        assert "route=`llm`" in out["content"]
        assert "intent=`CONVERSATION`" in out["content"]

    def test_dev_block_includes_agent_steps(self, session):
        session.dev_mode = True
        result = {
            "content": "done", "response": "done",
            "route": "agent", "intent": "SYSTEM",
            "model_used": "agent_orav", "success": True,
            "agent_steps": 3, "agent_status": "completed",
        }
        out = session._maybe_dev_block(result)
        assert "steps=`3`" in out["content"]
        assert "status=`completed`" in out["content"]


# ── Fastpath ──────────────────────────────────────────────────────────────────

class TestFastpath:

    @pytest.fixture
    def session(self, isolated_base_path):
        return BrainSession("test_fp")

    def test_health_fastpath(self, session):
        result = session._maybe_fastpath("estas operativo")
        assert result is not None
        assert "operativo" in result["content"]
        assert result["success"] is True

    def test_greeting_fastpath(self, session):
        result = session._maybe_fastpath("hola")
        assert result is not None
        assert result["success"] is True
        assert "Brain V9 esta operativo" in result["content"]

    def test_capabilities_fastpath(self, session):
        result = session._maybe_fastpath("que puedes hacer?")
        assert result is not None
        assert result["success"] is True
        assert "Puedo revisar estado del brain" in result["content"]

    def test_dashboard_query_does_not_match_ui_substring_inside_words(self, session):
        assert session._is_dashboard_query("puedes concluir que ana es disciplinada") is False

    def test_brain_status_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "overall_status": "healthy",
            "current_operating_mode": "learning_active",
            "change_validation": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({
            "mode": "ACTIVE",
            "execution_allowed": True,
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
            "system_profile": {"blockers": ["no_validated_edge"]},
        }))
        result = session._maybe_fastpath("dame el estado del brain")
        assert result is not None
        assert "Estado actual del brain" in result["content"]
        assert "increase_resolved_sample" in result["content"]

    def test_deep_brain_analysis_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        strategy_dir = state_dir / "strategy_engine"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        risk_dir = state_dir / "risk"
        risk_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "overall_status": "healthy",
            "current_operating_mode": "learning_active",
            "layers": {"V8": {"state": "inactive"}},
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({
            "mode": "ACTIVE",
        }))
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({
            "status": "healthy",
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
            "system_profile": {"validated_count": 0, "blockers": ["no_validated_edge", "sample_not_ready"]},
        }))
        (state_dir / "brain_self_model_latest.json").write_text(json.dumps({
            "identity": {"current_mode": "continual_self_improvement"},
            "overall_score": 0.75,
            "domains": [{"domain_id": "utility_governance", "status": "needs_work"}],
        }))
        (state_dir / "change_validation_status_latest.json").write_text(json.dumps({
            "summary": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (strategy_dir / "edge_validation_latest.json").write_text(json.dumps({
            "summary": {"promotable_count": 0},
        }))
        (strategy_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps({
            "ranked": [{"strategy_id": "po_mean_reversion_v2_auto", "execution_ready_now": False}],
        }))
        result = session._maybe_fastpath("analiza profundamente el estado del brain y sus implicaciones actuales")
        assert result is not None
        assert "Analisis profundo del brain" in result["content"]
        assert "implicacion 1" in result["content"]
        assert "po_mean_reversion_v2_auto" in result["content"]

    def test_deep_risk_analysis_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        risk_dir = state_dir / "risk"
        state_dir.mkdir(parents=True, exist_ok=True)
        risk_dir.mkdir(parents=True, exist_ok=True)
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({
            "status": "healthy",
            "execution_allowed": True,
            "limits": {"max_daily_loss_frac": 0.15, "max_weekly_drawdown_frac": 0.5, "max_total_exposure_frac": 0.7},
            "measures": {"daily_loss_frac": 0.1, "weekly_drawdown_frac": 0.11, "total_exposure_frac": 0.22},
            "warnings": [],
            "hard_violations": [],
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({"mode": "ACTIVE"}))
        result = session._maybe_fastpath("analiza profundamente el riesgo actual del sistema")
        assert result is not None
        assert "Analisis profundo de riesgo" in result["content"]
        assert "execution_allowed=`True`" in result["content"]

    def test_deep_strategy_analysis_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
            "ranked": [{"strategy_id": "po_mean_reversion_v2_auto", "edge_state": "probation", "execution_ready_now": False}],
            "exploit_candidate": None,
            "explore_candidate": {"strategy_id": "po_breakout_v3_auto"},
            "probation_candidate": {"strategy_id": "po_mean_reversion_v2_auto"},
        }))
        result = session._maybe_fastpath("audita profundamente el strategy engine")
        assert result is not None
        assert "Analisis profundo del strategy engine" in result["content"]
        assert "po_mean_reversion_v2_auto" in result["content"]

    def test_deep_pipeline_analysis_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "pipeline_integrity_latest.json").write_text(json.dumps({
            "summary": {
                "status": "degraded",
                "pipeline_ok": True,
                "signals_count": 2,
                "ledger_entries": 74,
                "decision_fresh_after_utility": True,
                "anomaly_count": 1,
            },
            "anomalies": [{"orphaned_resolved_total": 14}],
        }))
        result = session._maybe_fastpath("analiza profundamente la integridad del pipeline")
        assert result is not None
        assert "Analisis profundo del pipeline" in result["content"]
        assert "orphaned_resolved_total=`14`" in result["content"]

    def test_self_build_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "layers": {"V8": {"state": "inactive"}},
        }))
        (state_dir / "change_validation_status_latest.json").write_text(json.dumps({
            "summary": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "system_profile": {"validated_count": 0, "promotable_count": 0, "blockers": ["no_validated_edge"]},
        }))
        result = session._maybe_fastpath("evalua la autoconstruccion actual")
        assert result is not None
        assert result["success"] is False
        assert "lista para promover cambios autonomos: `NO`" in result["content"]

    def test_self_build_resolution_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        risk_dir = state_dir / "risk"
        risk_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "layers": {"V8": {"state": "inactive"}},
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({
            "mode": "ACTIVE",
        }))
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({
            "execution_allowed": True,
        }))
        (state_dir / "change_validation_status_latest.json").write_text(json.dumps({
            "summary": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "system_profile": {"validated_count": 0, "promotable_count": 0, "blockers": ["no_validated_edge"]},
        }))
        result = session._maybe_fastpath("por que esta detenida la autoconstruccion y como lo resuelvo?")
        assert result is not None
        assert result["success"] is False
        assert "Resolucion de autoconstruccion" in result["content"]
        assert "apply_gate_ready=`False`" in result["content"]
        assert "criterio de salida" in result["content"]

    def test_consciousness_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "brain_self_model_latest.json").write_text(json.dumps({
            "identity": {"current_mode": "continual_self_improvement"},
            "overall_score": 0.75,
            "domains": [{"domain_id": "utility_governance", "status": "needs_work"}],
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
        }))
        result = session._maybe_fastpath("eres autoconsciente?")
        assert result is not None
        assert "autodescripcion operativa" in result["content"]

    def test_consciousness_query_takes_priority_over_brain_status(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "brain_self_model_latest.json").write_text(json.dumps({
            "identity": {"current_mode": "continual_self_improvement"},
            "overall_score": 0.75,
            "domains": [{"domain_id": "utility_governance", "status": "needs_work"}],
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
            "system_profile": {"blockers": ["no_validated_edge"]},
        }))
        result = session._maybe_fastpath("eres autoconsciente? responde basandote en el estado actual del brain")
        assert result is not None
        assert "autodescripcion operativa" in result["content"]

    def test_dashboard_fastpath_reports_local_ui(self, session):
        result = session._maybe_fastpath("verifica el estado del dashboard")
        assert result is not None
        assert result["success"] is True
        assert "ui_url" in result["content"]
        assert "dashboard_url" in result["content"]

    def test_utility_fastpath_no_data(self, session, isolated_base_path):
        result = session._maybe_fastpath("utility u score")
        assert result is not None
        # No state file = should indicate missing data
        assert result["success"] is False

    def test_utility_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        utility_data = {
            "u_score": 0.55,
            "verdict": "no_promote",
            "promotion_gate": {"verdict": "no_promote", "blockers": ["min_trades"]},
        }
        (state_dir / "utility_u_latest.json").write_text(json.dumps(utility_data))

        result = session._maybe_fastpath("utility u score")
        assert result is not None
        assert "0.55" in result["content"]
        assert "min_trades" in result["content"]

    def test_edge_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        edge_data = {"summary": {"validated_count": 0, "probation_count": 2, "blocked_count": 1}}
        (state_dir / "edge_validation_latest.json").write_text(json.dumps(edge_data))

        result = session._maybe_fastpath("revisa el edge validation del sistema")
        assert result is not None
        assert "Edge Validation" in result["content"]
        assert "probation" in result["content"]

    def test_autonomy_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        utility_data = {"u_score": -0.2, "verdict": "no_promote", "promotion_gate": {"required_next_actions": ["run_probation_carefully"]}}
        (state_dir / "utility_u_latest.json").write_text(json.dumps(utility_data))
        (state_dir / "autonomy_next_actions.json").write_text(json.dumps({"top_action": "run_probation_carefully"}))

        result = session._maybe_fastpath("dame el estado de autonomia actual")
        assert result is not None
        assert "Autonomy" in result["content"]
        assert "run_probation_carefully" in result["content"]

    def test_status_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "utility_u_latest.json").write_text(json.dumps({"u_score": -0.4, "verdict": "no_promote"}))
        strategy_dir = state_dir / "strategy_engine"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        (strategy_dir / "edge_validation_latest.json").write_text(json.dumps({"summary": {"validated_count": 0, "probation_count": 2}}))

        result = session._maybe_fastpath("dame un resumen del sistema")
        assert result is not None
        assert "Estado Brain V9" in result["content"]
        assert "probation" in result["content"]

    def test_hypothesis_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        state_dir.mkdir(parents=True, exist_ok=True)
        synth_data = {
            "summary": {"top_finding": "Possible duplicate execution bursts detected", "finding_count": 3, "hypothesis_count": 2, "next_focus": "audit_duplicate_execution"},
            "suggested_hypotheses": [{"statement": "Audit duplicate clusters before trusting expectancy."}],
            "llm_summary": {"available": False},
        }
        (state_dir / "post_trade_hypotheses_latest.json").write_text(json.dumps(synth_data))

        result = session._maybe_fastpath("revisa las hipotesis post-trade")
        assert result is not None
        assert "Post-Trade Hypotheses" in result["content"]

    def test_security_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state" / "security"
        state_dir.mkdir(parents=True, exist_ok=True)
        posture = {
            "env_runtime": {"dotenv_exists": True, "dotenv_example_exists": True, "gitignore_protects_dotenv": True, "gitignore_protects_secrets": True},
            "secrets_audit": {"raw_finding_count": 100, "unclassified_count": 90},
            "secrets_triage": {"actionable_candidate_count": 4, "likely_false_positive_count": 96},
            "secret_source_audit": {"duplicate_source_count": 1, "mismatch_count": 1, "json_only_count": 2},
            "legacy_runtime_refs": {"env_bat_reference_count": 0},
            "dependency_audit": {"vulnerability_count": 7, "patchable_vulnerability_count": 6, "upstream_blocked_vulnerability_count": 1, "affected_package_count": 5},
        }
        (state_dir / "security_posture_latest.json").write_text(json.dumps(posture))

        result = session._maybe_fastpath("dame la postura de seguridad del sistema")
        assert result is not None
        assert "Security Posture" in result["content"]
        assert "100" in result["content"]

    def test_priority_fastpath_with_data(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "top_action": "increase_resolved_sample",
            "current_focus": {"action": "increase_resolved_sample", "focus_lock_active": True, "focus_switch_allowed": False},
            "top_priority": {"action": "increase_resolved_sample", "priority": "HIGH", "priority_score": 42.0},
            "allocator": {"trading": 35, "stability_control": 25, "improvement_autobuild": 20, "observability": 15, "exploration": 5},
            "discipline": {"optimization_allowed": False, "optimize_blockers": ["resolved_sample_below_15"]},
            "system_profile": {"consecutive_skips": 3, "validated_count": 0, "probation_count": 2},
        }
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps(meta))

        result = session._maybe_fastpath("dame la prioridad del sistema")
        assert result is not None
        assert "Meta-Governance" in result["content"]

    def test_no_fastpath_for_general_messages(self, session):
        assert session._maybe_fastpath("hola como estas") is None
        assert session._maybe_fastpath("que es machine learning") is None


# ── get_or_create_session ─────────────────────────────────────────────────────

class TestGetOrCreateSession:

    def test_creates_new_session(self, isolated_base_path):
        sessions = {}
        s = get_or_create_session("new_one", sessions)
        assert isinstance(s, BrainSession)
        assert "new_one" in sessions

    def test_returns_existing_session(self, isolated_base_path):
        sessions = {}
        s1 = get_or_create_session("reuse", sessions)
        s2 = get_or_create_session("reuse", sessions)
        assert s1 is s2


# ── Full chat flow (mocked LLM) ──────────────────────────────────────────────

class TestChatFlow:

    @pytest.fixture
    def session(self, isolated_base_path):
        s = BrainSession("test_chat_flow")
        # Mock the LLM to avoid real Ollama calls
        s.llm.query = AsyncMock(return_value={
            "success": True,
            "content": "Mocked LLM response",
            "response": "Mocked LLM response",
            "model": "mock",
            "model_used": "mock",
        })
        return s

    @pytest.mark.asyncio
    async def test_chat_routes_to_llm(self, session):
        result = await session.chat("hola como estas")
        assert result["success"] is True
        assert "Mocked LLM response" in result["content"]
        # Should have saved the turn to memory
        ctx = session.memory.get_context()
        assert len(ctx) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_chat_slash_command_bypasses_llm(self, session):
        result = await session.chat("/help")
        assert result["model"] == "system"
        # LLM should NOT have been called
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_fastpath_bypasses_llm(self, session):
        result = await session.chat("estas operativo")
        assert "operativo" in result["content"]
        assert result["route"] == "fastpath"
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_greeting_fastpath_bypasses_llm(self, session):
        result = await session.chat("hola")
        assert result["success"] is True
        assert result["route"] == "fastpath"
        assert "Brain V9 esta operativo" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_capabilities_fastpath_bypasses_llm(self, session):
        result = await session.chat("que puedes hacer?")
        assert result["success"] is True
        assert result["route"] == "fastpath"
        assert "Puedo revisar estado del brain" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_reasoning_query_no_longer_hits_dashboard_fastpath(self, session):
        result = await session.chat(
            "Si todos los mamiferos son animales y todos los perros son mamiferos, puedes concluir que los perros son animales?"
        )
        assert result["success"] is True
        assert "Mocked LLM response" in result["content"]
        assert result["route"] == "llm"

    @pytest.mark.asyncio
    async def test_chat_deep_brain_analysis_uses_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        strategy_dir = state_dir / "strategy_engine"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        risk_dir = state_dir / "risk"
        risk_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "overall_status": "healthy",
            "current_operating_mode": "learning_active",
            "layers": {"V8": {"state": "inactive"}},
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({"mode": "ACTIVE"}))
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({"status": "healthy"}))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "top_action": "increase_resolved_sample",
            "system_profile": {"validated_count": 0, "blockers": ["no_validated_edge"]},
        }))
        (state_dir / "brain_self_model_latest.json").write_text(json.dumps({
            "identity": {"current_mode": "continual_self_improvement"},
            "overall_score": 0.75,
            "domains": [{"domain_id": "utility_governance", "status": "needs_work"}],
        }))
        (state_dir / "change_validation_status_latest.json").write_text(json.dumps({
            "summary": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (strategy_dir / "edge_validation_latest.json").write_text(json.dumps({"summary": {"promotable_count": 0}}))
        (strategy_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps({
            "ranked": [{"strategy_id": "po_mean_reversion_v2_auto", "execution_ready_now": False}],
        }))
        result = await session.chat("Analiza profundamente el estado del brain y sus implicaciones actuales.")
        assert result["success"] is True
        assert result["route"] == "fastpath"
        assert "Analisis profundo del brain" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_self_build_resolution_uses_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        risk_dir = state_dir / "risk"
        risk_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "governance_health_latest.json").write_text(json.dumps({
            "layers": {"V8": {"state": "inactive"}},
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({
            "mode": "ACTIVE",
        }))
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({
            "execution_allowed": True,
        }))
        (state_dir / "change_validation_status_latest.json").write_text(json.dumps({
            "summary": {"apply_gate_ready": False, "passed_count": 0, "pending_count": 8},
        }))
        (state_dir / "meta_governance_status_latest.json").write_text(json.dumps({
            "system_profile": {"validated_count": 0, "promotable_count": 0, "blockers": ["no_validated_edge"]},
        }))
        result = await session.chat("por que esta detenida la autoconstruccion y resuelvelo")
        assert result["success"] is False
        assert result["route"] == "fastpath"
        assert "Resolucion de autoconstruccion" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_deep_risk_analysis_uses_fastpath(self, session, isolated_base_path):
        state_dir = isolated_base_path / "tmp_agent" / "state"
        risk_dir = state_dir / "risk"
        state_dir.mkdir(parents=True, exist_ok=True)
        risk_dir.mkdir(parents=True, exist_ok=True)
        (risk_dir / "risk_contract_status_latest.json").write_text(json.dumps({
            "status": "healthy",
            "execution_allowed": True,
            "limits": {"max_daily_loss_frac": 0.15, "max_weekly_drawdown_frac": 0.5, "max_total_exposure_frac": 0.7},
            "measures": {"daily_loss_frac": 0.1, "weekly_drawdown_frac": 0.11, "total_exposure_frac": 0.22},
            "warnings": [],
            "hard_violations": [],
        }))
        (state_dir / "control_layer_status.json").write_text(json.dumps({"mode": "ACTIVE"}))
        result = await session.chat("analiza profundamente el riesgo actual del sistema")
        assert result["success"] is True
        assert result["route"] == "fastpath"
        assert "Analisis profundo de riesgo" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_chat_normalizes_legacy_ui_model_alias(self, session):
        result = await session.chat("hola como estas", model_priority="llama3.1:8b")
        assert result["success"] is True
        assert "Mocked LLM response" in result["content"]
        session.llm.query.assert_awaited_once()
        _, kwargs = session.llm.query.await_args
        assert kwargs["model_priority"] == "llama8b"

    @pytest.mark.asyncio
    async def test_chat_strips_fake_tool_claims_from_llm_route(self, session):
        session.llm.query = AsyncMock(return_value={
            "success": True,
            "content": "Respuesta correcta.\n\nUtilicé la herramienta de inferencia.\nSigue la conclusión.",
            "response": "Respuesta correcta.\n\nUtilicé la herramienta de inferencia.\nSigue la conclusión.",
            "model": "mock",
            "model_used": "mock",
        })
        result = await session.chat("explica esta deduccion", model_priority="chat")
        assert result["success"] is True
        assert "herramienta" not in result["content"].lower()
        assert "Sigue la conclusión." in result["content"]

    @pytest.mark.asyncio
    async def test_chat_dashboard_fastpath_bypasses_llm(self, session):
        result = await session.chat("Verifica el estado del dashboard")
        assert result["success"] is True
        assert result["route"] == "fastpath"
        assert "dashboard_url" in result["content"]
        session.llm.query.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_to_agent_timeout_returns_partial_results(self, session, monkeypatch):
        class FakeExecutor:
            def list_tools(self):
                return ["fake_tool"]

        class FakeLoop:
            def __init__(self, llm, tools):
                self.history = [{
                    "actions": [{"tool": "fake_tool", "success": True, "output": {"status": "partial"}}]
                }]
                self.MAX_STEPS = 0
                self.WALL_CLOCK_TIMEOUT = 0

            async def run(self, task, context=None):
                await asyncio.sleep(70)
                return {"success": False, "status": "timeout", "steps": 1}

            def get_history(self):
                return self.history

        monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: FakeExecutor())
        monkeypatch.setattr("brain_v9.agent.loop.AgentLoop", FakeLoop)

        result = await session._route_to_agent("haz un diagnostico complejo", "agent")
        assert result["success"] is True
        assert "resultados parciales" in result["content"]
        assert "fake_tool" in result["content"]

    @pytest.mark.asyncio
    async def test_route_to_agent_passes_requested_model_priority(self, session, monkeypatch):
        class FakeExecutor:
            def list_tools(self):
                return ["fake_tool"]

        captured = {}

        class FakeLoop:
            def __init__(self, llm, tools):
                self.history = []
                self.MAX_STEPS = 0
                self.WALL_CLOCK_TIMEOUT = 0

            async def run(self, task, context=None):
                captured["task"] = task
                captured["context"] = context or {}
                return {"success": True, "status": "completed", "steps": 1, "result": "ok"}

            def get_history(self):
                return self.history

        monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: FakeExecutor())
        monkeypatch.setattr("brain_v9.agent.loop.AgentLoop", FakeLoop)

        result = await session._route_to_agent("haz una revision operativa", "gpt4")
        assert result["success"] is True
        assert captured["task"] == "haz una revision operativa"
        assert captured["context"]["model_priority"] == "gpt4"
        assert "Agente ORAV" in result["content"]

    @pytest.mark.asyncio
    async def test_route_to_agent_operational_summary_is_deterministic(self, session, monkeypatch):
        class FakeExecutor:
            def list_tools(self):
                return ["check_http_service", "get_autonomy_phase"]

        class FakeLoop:
            def __init__(self, llm, tools):
                self.history = [{
                    "actions": [
                        {
                            "tool": "check_http_service",
                            "success": True,
                            "output": {
                                "service": "Brain Chat V9",
                                "url": "http://127.0.0.1:8090/health",
                                "status_code": 200,
                                "is_healthy": True,
                            },
                        },
                        {
                            "tool": "get_autonomy_phase",
                            "success": True,
                            "output": {
                                "running": True,
                                "phase": "observe",
                            },
                        },
                    ]
                }]
                self.MAX_STEPS = 0
                self.WALL_CLOCK_TIMEOUT = 0

            async def run(self, task, context=None):
                return {"success": True, "status": "completed", "steps": 1, "result": None}

            def get_history(self):
                return self.history

        monkeypatch.setattr("brain_v9.agent.tools.build_standard_executor", lambda: FakeExecutor())
        monkeypatch.setattr("brain_v9.agent.loop.AgentLoop", FakeLoop)

        result = await session._route_to_agent("Revisa el estado del brain", "gpt4")
        assert result["success"] is True
        assert "Resumen basado en herramientas reales." in result["content"]
        assert "check_http_service" in result["content"]
        assert "status_code=200" in result["content"]
        assert "phase=observe" in result["content"]
        session.llm.query.assert_not_called()


# ── Token-Aware Context Truncation ────────────────────────────────────────────

class TestTruncateMessage:

    def test_short_message_unchanged(self):
        msg = {"role": "user", "content": "hola"}
        result = BrainSession._truncate_message(msg, 6000)
        assert result["content"] == "hola"

    def test_long_message_truncated(self):
        msg = {"role": "user", "content": "x" * 10000}
        result = BrainSession._truncate_message(msg, 6000)
        assert len(result["content"]) < 10000
        assert "truncado" in result["content"]
        assert result["content"].startswith("x" * 6000)

    def test_exact_boundary_not_truncated(self):
        msg = {"role": "user", "content": "x" * 6000}
        result = BrainSession._truncate_message(msg, 6000)
        assert "truncado" not in result["content"]

    def test_preserves_other_fields(self):
        msg = {"role": "assistant", "content": "x" * 10000, "timestamp": "2026-01-01"}
        result = BrainSession._truncate_message(msg, 100)
        assert result["role"] == "assistant"
        assert result["timestamp"] == "2026-01-01"
        assert "truncado" in result["content"]


class TestTruncateToBudget:

    def _msg(self, content: str, role: str = "user") -> Dict:
        return {"role": role, "content": content}

    def test_empty_history_returns_empty(self):
        result = BrainSession._truncate_to_budget([], budget_tokens=1000)
        assert result == []

    def test_small_history_fits(self):
        """Short messages that fit easily within budget should all be kept."""
        history = [
            self._msg("hola"),
            self._msg("todo bien", role="assistant"),
            self._msg("genial"),
        ]
        result = BrainSession._truncate_to_budget(history, budget_tokens=5000)
        assert len(result) == 3

    def test_drops_oldest_when_over_budget(self):
        """When history exceeds budget, oldest messages are dropped first."""
        # Each message ~100 chars = ~34 tokens + 4 overhead = ~38 tokens
        history = [self._msg("a" * 100) for _ in range(20)]
        # Budget for ~5 messages: 5 * 38 = 190 tokens
        result = BrainSession._truncate_to_budget(history, budget_tokens=190)
        assert len(result) < 20
        assert len(result) >= 4  # should keep at least a few

    def test_preserves_most_recent(self):
        """The most recent messages should be the ones kept."""
        history = [self._msg(f"msg_{i}") for i in range(50)]
        result = BrainSession._truncate_to_budget(history, budget_tokens=100)
        # Should be the tail of the history
        assert len(result) < 50
        assert result[-1]["content"] == "msg_49"

    def test_zero_budget_returns_empty(self):
        history = [self._msg("anything")]
        result = BrainSession._truncate_to_budget(history, budget_tokens=0)
        assert result == []

    def test_oversized_message_gets_trimmed(self):
        """A single huge message should be tail-truncated before budgeting."""
        history = [self._msg("x" * 50000)]
        # With max_msg_chars=6000, the message becomes ~6030 chars
        # = ~2010 tokens + 4 overhead = ~2014 tokens
        result = BrainSession._truncate_to_budget(
            history, budget_tokens=3000, max_msg_chars=6000
        )
        assert len(result) == 1
        assert "truncado" in result[0]["content"]
        assert len(result[0]["content"]) < 50000

    def test_oversized_message_dropped_if_still_too_big(self):
        """If even truncated message exceeds budget, it's dropped."""
        history = [self._msg("x" * 50000)]
        result = BrainSession._truncate_to_budget(
            history, budget_tokens=10, max_msg_chars=6000
        )
        assert result == []

    def test_mixed_sizes(self):
        """Mix of short and long messages; long ones trimmed, oldest dropped."""
        history = [
            self._msg("short"),                      # ~6 tokens
            self._msg("y" * 10000, role="assistant"), # will be trimmed to ~2000 tokens
            self._msg("also short"),                  # ~8 tokens
        ]
        # Budget only for ~100 tokens — should drop the long one and maybe keep shorts
        result = BrainSession._truncate_to_budget(
            history, budget_tokens=100
        )
        # At minimum, the last short message should fit
        assert any("also short" in m["content"] for m in result)


class TestContextBudget:

    @pytest.fixture
    def session(self, isolated_base_path):
        return BrainSession("test_budget")

    def test_returns_positive_for_default_chain(self, session):
        budget = session._context_budget("System prompt", "Hello", "ollama")
        assert budget > 0
        assert isinstance(budget, int)

    def test_larger_system_prompt_reduces_budget(self, session):
        small_budget = session._context_budget("Short", "Hi", "ollama")
        large_budget = session._context_budget("x" * 5000, "Hi", "ollama")
        assert large_budget < small_budget

    def test_agent_and_chat_chains_same_budget_after_reorder(self, session):
        """After chain reorder (llama8b first everywhere), both chains use same model limits."""
        chat_budget = session._context_budget("sys", "msg", "chat")
        agent_budget = session._context_budget("sys", "msg", "agent")
        # Both chains now start with llama8b (max_num_ctx=16384)
        assert chat_budget == agent_budget
        assert chat_budget > 0

    def test_huge_prompt_returns_zero(self, session):
        """If system + user + num_predict exceed max_ctx, budget should be 0."""
        # max_num_ctx for llama8b is 16384, num_predict is 4096
        # so ~12288 tokens of system+user should leave 0 budget
        huge_system = "x" * 50000  # ~16667 tokens
        budget = session._context_budget(huge_system, "msg", "ollama")
        assert budget == 0

    def test_unknown_chain_uses_default_limits(self, session):
        """Unknown chain falls back to CHAINS['ollama'], should still work."""
        budget = session._context_budget("sys", "msg", "nonexistent_chain")
        assert budget > 0
