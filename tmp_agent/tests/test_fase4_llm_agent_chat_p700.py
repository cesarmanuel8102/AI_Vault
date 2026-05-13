"""
Fase 4 Stage 2 — LLM / Agent / Chat como Capa Cognitiva Superior.

Tests for:
  4.1 — SYSTEM_IDENTITY updated with LLM role boundaries
  4.3 — 6 new analysis tools in build_standard_executor()
  4.4 — 3 new slash commands (/learning, /catalog, /context-edge)
       + fastpath detection
       + synthesize_edge_analysis tool logic
"""
import json
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


# ────────────────────────────────────────────────────────────────────────────
# 4.1 — SYSTEM_IDENTITY contains LLM role boundaries
# ────────────────────────────────────────────────────────────────────────────
class TestSystemIdentityLLMRole:
    """Verify SYSTEM_IDENTITY in config.py has the Fase 4 updates."""

    def test_has_analysis_category(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "ANÁLISIS AVANZADO" in SYSTEM_IDENTITY

    def test_has_llm_role_section(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "ROL DEL LLM EN EL SISTEMA" in SYSTEM_IDENTITY

    def test_llm_role_boundaries_yes(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "síntesis de datos canónicos" in SYSTEM_IDENTITY

    def test_llm_role_boundaries_no(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "inventar métricas" in SYSTEM_IDENTITY

    def test_canonical_data_references(self):
        from brain_v9.config import SYSTEM_IDENTITY
        for cmd in ["/learning", "/catalog", "/context-edge"]:
            assert cmd in SYSTEM_IDENTITY, f"Missing slash command reference: {cmd}"

    def test_synthesize_tool_referenced(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "synthesize_edge_analysis" in SYSTEM_IDENTITY

    def test_tool_count_at_least_41(self):
        from brain_v9.config import SYSTEM_IDENTITY
        assert "41 herramientas" in SYSTEM_IDENTITY


# ────────────────────────────────────────────────────────────────────────────
# 4.3 — build_standard_executor() registers 6 new tools
# ────────────────────────────────────────────────────────────────────────────
class TestBuildStandardExecutorFase4Tools:
    """Verify the 6 new Fase 4 Stage 2 tools are registered."""

    EXPECTED_TOOLS = [
        "get_context_edge_validation_live",
        "get_learning_loop_live",
        "get_active_catalog_live",
        "get_post_trade_context_live",
        "get_active_hypotheses_live",
        "synthesize_edge_analysis",
    ]

    def test_all_fase4_tools_registered(self):
        from brain_v9.agent.tools import build_standard_executor
        ex = build_standard_executor()
        tool_names = ex.list_tools()  # returns list of strings
        for expected in self.EXPECTED_TOOLS:
            assert expected in tool_names, f"Tool '{expected}' not registered"

    def test_minimum_total_tool_count(self):
        """Should have at least 61 tools (55 pre-Fase4 + 6 new)."""
        from brain_v9.agent.tools import build_standard_executor
        ex = build_standard_executor()
        count = len(ex.list_tools())
        assert count >= 61, f"Expected >=61 tools, got {count}"


# ────────────────────────────────────────────────────────────────────────────
# 4.3 — synthesize_edge_analysis logic
# ────────────────────────────────────────────────────────────────────────────
class TestSynthesizeEdgeAnalysis:
    """Test the consolidated analysis tool."""

    def _make_snapshots(self):
        context_edge = {
            "summary": {"ranked_count": 2, "validated_count": 1},
            "items": [],
        }
        learning = {
            "summary": {
                "top_learning_action": "continue_probation",
                "allow_variant_generation": False,
                "variant_generation_sources": ["strat_a"],
            },
            "items": [
                {
                    "strategy_id": "strat_a",
                    "catalog_state": "probation",
                    "learning_decision": "continue_probation",
                    "rationale": "sample_incomplete",
                    "entries_resolved": 5,
                    "expectancy": 0.5,
                },
                {
                    "strategy_id": "strat_b",
                    "catalog_state": "excluded",
                    "learning_decision": "historical_only",
                    "rationale": "refuted",
                    "entries_resolved": 40,
                    "expectancy": -8.0,
                },
            ],
        }
        post_trade = {
            "summary": {"recent_resolved_trades": 50},
            "by_setup_variant": [
                {"variant": "breakout", "avg_profit": -5.0},
                {"variant": "reversion", "avg_profit": 2.0},
            ],
            "by_duration": [
                {"bucket": "short", "avg_profit": -1.0},
                {"bucket": "ultra_short", "avg_profit": 0.5},
            ],
            "by_payout": [
                {"bucket": "good", "avg_profit": 1.0},
                {"bucket": "no_payout", "avg_profit": -3.0},
            ],
        }
        catalog = {
            "summary": {"total_count": 5, "operational_count": 1},
            "items": [],
        }
        return context_edge, learning, post_trade, catalog

    @pytest.mark.asyncio
    async def test_returns_success_with_valid_data(self):
        ce, ll, pt, cat = self._make_snapshots()
        with patch("brain_v9.trading.context_edge_validation.read_context_edge_validation_snapshot", return_value=ce), \
             patch("brain_v9.trading.learning_loop.read_learning_loop_snapshot", return_value=ll), \
             patch("brain_v9.trading.post_trade_analysis.read_post_trade_analysis_snapshot", return_value=pt), \
             patch("brain_v9.trading.active_strategy_catalog.read_active_strategy_catalog_snapshot", return_value=cat):
            from brain_v9.agent.tools import synthesize_edge_analysis
            result = await synthesize_edge_analysis()
        assert result["success"] is True
        assert result["synthesis_type"] == "edge_analysis_consolidated"

    @pytest.mark.asyncio
    async def test_filters_out_historical_only(self):
        ce, ll, pt, cat = self._make_snapshots()
        with patch("brain_v9.trading.context_edge_validation.read_context_edge_validation_snapshot", return_value=ce), \
             patch("brain_v9.trading.learning_loop.read_learning_loop_snapshot", return_value=ll), \
             patch("brain_v9.trading.post_trade_analysis.read_post_trade_analysis_snapshot", return_value=pt), \
             patch("brain_v9.trading.active_strategy_catalog.read_active_strategy_catalog_snapshot", return_value=cat):
            from brain_v9.agent.tools import synthesize_edge_analysis
            result = await synthesize_edge_analysis()
        actionable = result["actionable_learning_decisions"]
        ids = [item["strategy_id"] for item in actionable]
        assert "strat_a" in ids, "Probation strategy should be actionable"
        assert "strat_b" not in ids, "historical_only should be filtered"

    @pytest.mark.asyncio
    async def test_worst_variants_sorted(self):
        ce, ll, pt, cat = self._make_snapshots()
        with patch("brain_v9.trading.context_edge_validation.read_context_edge_validation_snapshot", return_value=ce), \
             patch("brain_v9.trading.learning_loop.read_learning_loop_snapshot", return_value=ll), \
             patch("brain_v9.trading.post_trade_analysis.read_post_trade_analysis_snapshot", return_value=pt), \
             patch("brain_v9.trading.active_strategy_catalog.read_active_strategy_catalog_snapshot", return_value=cat):
            from brain_v9.agent.tools import synthesize_edge_analysis
            result = await synthesize_edge_analysis()
        # breakout has -5.0 avg_profit, should be first (worst)
        assert result["worst_performing_variants"][0]["variant"] == "breakout"

    @pytest.mark.asyncio
    async def test_has_recommendation_context(self):
        ce, ll, pt, cat = self._make_snapshots()
        with patch("brain_v9.trading.context_edge_validation.read_context_edge_validation_snapshot", return_value=ce), \
             patch("brain_v9.trading.learning_loop.read_learning_loop_snapshot", return_value=ll), \
             patch("brain_v9.trading.post_trade_analysis.read_post_trade_analysis_snapshot", return_value=pt), \
             patch("brain_v9.trading.active_strategy_catalog.read_active_strategy_catalog_snapshot", return_value=cat):
            from brain_v9.agent.tools import synthesize_edge_analysis
            result = await synthesize_edge_analysis()
        assert "recommendation_context" in result
        assert "Do NOT invent statistics" in result["recommendation_context"]

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        with patch("brain_v9.trading.context_edge_validation.read_context_edge_validation_snapshot", side_effect=FileNotFoundError("missing")), \
             patch("brain_v9.trading.learning_loop.read_learning_loop_snapshot", return_value={}), \
             patch("brain_v9.trading.post_trade_analysis.read_post_trade_analysis_snapshot", return_value={}), \
             patch("brain_v9.trading.active_strategy_catalog.read_active_strategy_catalog_snapshot", return_value={}):
            from brain_v9.agent.tools import synthesize_edge_analysis
            result = await synthesize_edge_analysis()
        assert result["success"] is False
        assert "error" in result


# ────────────────────────────────────────────────────────────────────────────
# 4.4 — Slash commands: /learning, /catalog, /context-edge
# ────────────────────────────────────────────────────────────────────────────
class TestSlashCommandLearning:
    """Test /learning slash command."""

    def _write_learning_json(self, state_path: Path, data: dict):
        engine = state_path / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "learning_loop_latest.json").write_text(json.dumps(data), encoding="utf-8")

    def _build_session(self):
        from brain_v9.core.session import BrainSession
        return BrainSession(session_id="test")

    def test_learning_returns_formatted_output(self, isolated_base_path):
        data = {
            "summary": {
                "top_learning_action": "audit",
                "operational_count": 1,
                "audit_count": 1,
                "probation_continue_count": 0,
                "forward_validation_count": 0,
                "variant_generation_candidate_count": 2,
                "allow_variant_generation": True,
            },
            "items": [
                {
                    "strategy_id": "strat_x",
                    "catalog_state": "active",
                    "learning_decision": "audit",
                    "rationale": "anomaly_detected",
                    "entries_resolved": 20,
                    "expectancy": 1.5,
                    "allow_variant_generation": True,
                },
            ],
        }
        state_path = isolated_base_path / "tmp_agent" / "state"
        self._write_learning_json(state_path, data)
        session = self._build_session()
        result = session._cmd_learning()
        content = result.get("content") or result.get("response", "")
        assert "Learning Loop" in content
        assert "audit" in content
        assert "strat_x" in content

    def test_learning_empty_returns_error(self, isolated_base_path):
        session = self._build_session()
        result = session._cmd_learning()
        assert result.get("success") is False


class TestSlashCommandCatalog:
    """Test /catalog slash command."""

    def _write_catalog_json(self, state_path: Path, data: dict):
        engine = state_path / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "active_strategy_catalog_latest.json").write_text(json.dumps(data), encoding="utf-8")

    def _build_session(self):
        from brain_v9.core.session import BrainSession
        return BrainSession(session_id="test")

    def test_catalog_shows_strategies(self, isolated_base_path):
        data = {
            "summary": {"total": 3, "operational": 1, "excluded": 2},
            "items": [
                {"strategy_id": "s1", "catalog_state": "active", "venue": "ibkr", "entries_resolved": 10, "expectancy": 2.0},
                {"strategy_id": "s2", "catalog_state": "excluded", "venue": "pocket_option", "entries_resolved": 30, "expectancy": -5.0},
            ],
        }
        state_path = isolated_base_path / "tmp_agent" / "state"
        self._write_catalog_json(state_path, data)
        session = self._build_session()
        result = session._cmd_catalog()
        content = result.get("content") or result.get("response", "")
        assert "Active Strategy Catalog" in content
        assert "s1" in content
        assert "s2" in content

    def test_catalog_empty_returns_error(self, isolated_base_path):
        session = self._build_session()
        result = session._cmd_catalog()
        assert result.get("success") is False


class TestSlashCommandContextEdge:
    """Test /context-edge slash command."""

    def _write_ce_json(self, state_path: Path, data: dict):
        engine = state_path / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "context_edge_validation_latest.json").write_text(json.dumps(data), encoding="utf-8")

    def _build_session(self):
        from brain_v9.core.session import BrainSession
        return BrainSession(session_id="test")

    def test_context_edge_shows_summary(self, isolated_base_path):
        data = {
            "summary": {"total_contexts": 3, "validated": 1, "contradicted": 0, "unproven": 1, "insufficient": 1},
            "contexts": [
                {"strategy_id": "sx", "symbol": "SPY", "setup_variant": "breakout", "timeframe": "5m", "context_edge_state": "validated", "entries_resolved": 15, "expectancy": 3.0},
            ],
        }
        state_path = isolated_base_path / "tmp_agent" / "state"
        self._write_ce_json(state_path, data)
        session = self._build_session()
        result = session._cmd_context_edge()
        content = result.get("content") or result.get("response", "")
        assert "Context Edge Validation" in content
        assert "validated" in content.lower()

    def test_context_edge_empty_returns_error(self, isolated_base_path):
        session = self._build_session()
        result = session._cmd_context_edge()
        assert result.get("success") is False


# ────────────────────────────────────────────────────────────────────────────
# 4.4 — Fastpath detection for new domains
# ────────────────────────────────────────────────────────────────────────────
class TestFastpathDetection:
    """Verify _maybe_fastpath routes new Fase 4 domains."""

    def _build_session(self):
        from brain_v9.core.session import BrainSession
        return BrainSession(session_id="test")

    @pytest.mark.parametrize("msg", [
        "dame el learning loop",
        "quiero ver el loop de aprendizaje",
        "show me the learning decisions",
        "estado del learning",
    ])
    def test_learning_fastpath_triggers(self, msg, isolated_base_path):
        session = self._build_session()
        # Write dummy data so the handler doesn't fail
        engine = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "learning_loop_latest.json").write_text(
            json.dumps({"summary": {"top_learning_action": "test"}, "items": []}),
            encoding="utf-8",
        )
        result = session._maybe_fastpath(msg)
        assert result is not None, f"Fastpath should trigger for: {msg}"

    @pytest.mark.parametrize("msg", [
        "muestrame el catalogo activo",
        "quiero ver el catálogo activo",
        "active catalog please",
        "estrategias operativas",
    ])
    def test_catalog_fastpath_triggers(self, msg, isolated_base_path):
        session = self._build_session()
        engine = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "active_strategy_catalog_latest.json").write_text(
            json.dumps({"summary": {}, "items": []}),
            encoding="utf-8",
        )
        result = session._maybe_fastpath(msg)
        assert result is not None, f"Fastpath should trigger for: {msg}"

    @pytest.mark.parametrize("msg", [
        "show me the context edge",
        "quiero ver el edge por contexto",
        "validacion por contexto actual",
        "context-edge validation",
    ])
    def test_context_edge_fastpath_triggers(self, msg, isolated_base_path):
        session = self._build_session()
        engine = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "context_edge_validation_latest.json").write_text(
            json.dumps({"summary": {}, "contexts": []}),
            encoding="utf-8",
        )
        result = session._maybe_fastpath(msg)
        assert result is not None, f"Fastpath should trigger for: {msg}"
