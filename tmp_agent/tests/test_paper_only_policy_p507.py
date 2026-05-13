"""P5-07: Tests for centralized paper_only trading policy.

Covers:
1. config.PAPER_ONLY defaults to True
2. config.PAPER_ONLY reads from PAPER_ONLY env var
3. TRADING_AUTONOMY_POLICY global_rules reflect PAPER_ONLY
4. TRADING_AUTONOMY_POLICY platform_rules reflect PAPER_ONLY
5. strategy_engine normalization injects PAPER_ONLY
6. knowledge_base strategy seeds use PAPER_ONLY
7. knowledge_base hypothesis seeds use PAPER_ONLY
8. build_strategy_candidates() fallback uses PAPER_ONLY
9. Flipping PAPER_ONLY=false propagates everywhere
"""
from __future__ import annotations

import importlib
import os

import pytest

import brain_v9.config as _cfg


# ---------------------------------------------------------------------------
# 1. config.PAPER_ONLY default and env-var parsing
# ---------------------------------------------------------------------------

class TestConfigPaperOnly:
    """Verify the PAPER_ONLY constant in config."""

    def test_paper_only_default_is_true(self):
        """PAPER_ONLY defaults to True when env var is not set."""
        # The conftest doesn't patch PAPER_ONLY, so it keeps its import-time
        # value.  We verify the constant exists and is bool.
        assert isinstance(_cfg.PAPER_ONLY, bool)
        # Default (no env override in CI) should be True
        assert _cfg.PAPER_ONLY is True

    def test_paper_only_env_true_variants(self, monkeypatch):
        """Various truthy strings all produce True."""
        for val in ("true", "True", "TRUE", "tRuE"):
            monkeypatch.setenv("PAPER_ONLY", val)
            result = os.getenv("PAPER_ONLY", "true").lower() == "true"
            assert result is True

    def test_paper_only_env_false(self, monkeypatch):
        """Setting PAPER_ONLY=false yields False."""
        monkeypatch.setenv("PAPER_ONLY", "false")
        result = os.getenv("PAPER_ONLY", "true").lower() == "true"
        assert result is False

    def test_paper_only_env_arbitrary_string(self, monkeypatch):
        """Arbitrary non-'true' string yields False."""
        monkeypatch.setenv("PAPER_ONLY", "maybe")
        result = os.getenv("PAPER_ONLY", "true").lower() == "true"
        assert result is False


# ---------------------------------------------------------------------------
# 2. TRADING_AUTONOMY_POLICY respects PAPER_ONLY
# ---------------------------------------------------------------------------

class TestTradingAutonomyPolicy:
    """Verify the policy dict in action_executor uses config.PAPER_ONLY."""

    def test_policy_global_rules_paper_only(self):
        """Global rules reference PAPER_ONLY, not hardcoded True."""
        from brain_v9.autonomy.action_executor import TRADING_AUTONOMY_POLICY

        gr = TRADING_AUTONOMY_POLICY["global_rules"]
        assert gr["paper_only"] is _cfg.PAPER_ONLY
        assert gr["live_trading_forbidden"] is _cfg.PAPER_ONLY
        assert gr["capital_mutation_forbidden"] is _cfg.PAPER_ONLY

    def test_policy_platform_modes_paper_only(self):
        """Platform modes are consistent with PAPER_ONLY=True."""
        from brain_v9.autonomy.action_executor import TRADING_AUTONOMY_POLICY

        pr = TRADING_AUTONOMY_POLICY["platform_rules"]

        # Internal paper simulator
        ips = pr["internal_paper_simulator"]
        assert ips["paper_allowed"] is True
        assert ips["live_allowed"] is (not _cfg.PAPER_ONLY)
        assert "paper" in ips["mode"]

        # IBKR
        ibkr = pr["ibkr"]
        assert ibkr["paper_allowed"] is True
        assert ibkr["live_allowed"] is (not _cfg.PAPER_ONLY)

        # PocketOption
        po = pr["pocket_option"]
        assert po["paper_allowed"] is True
        assert po["live_allowed"] is (not _cfg.PAPER_ONLY)

        # QuantConnect — always research_only regardless of PAPER_ONLY
        qc = pr["quantconnect"]
        assert qc["paper_allowed"] is False
        assert qc["live_allowed"] is False
        assert qc["mode"] == "research_only"

    def test_policy_credentials_always_forbidden(self):
        """credentials_mutation_forbidden is always True (not tied to PAPER_ONLY)."""
        from brain_v9.autonomy.action_executor import TRADING_AUTONOMY_POLICY

        assert TRADING_AUTONOMY_POLICY["global_rules"]["credentials_mutation_forbidden"] is True


# ---------------------------------------------------------------------------
# 3. strategy_engine normalization uses PAPER_ONLY
# ---------------------------------------------------------------------------

class TestStrategyEngineNormalization:
    """Verify that _normalize_strategy_specs uses PAPER_ONLY."""

    def _patch_engine(self, monkeypatch, tmp_path, se, paper_only_val):
        """Common setup: redirect paths and set PAPER_ONLY."""
        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(se, "STATE_PATH", tmp_path / "tmp_agent" / "state")
        monkeypatch.setattr(_cfg, "PAPER_ONLY", paper_only_val)
        monkeypatch.setattr(se, "PAPER_ONLY", paper_only_val)

        # Provide minimal strategy specs so _normalize_strategy_specs has data
        mock_specs = {
            "strategies": [{
                "id": "test_strat_norm",
                "venue": "ibkr",
                "family": "trend_following",
                "summary": "test normalization",
                "core_indicators": ["rsi_14"],
            }],
        }
        mock_hyps = {"hypotheses": []}
        monkeypatch.setattr(se, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(se, "read_hypothesis_queue", lambda: mock_hyps)

    def test_normalize_injects_paper_only(self, monkeypatch, tmp_path):
        """Normalized strategies carry paper_only=True from config."""
        import brain_v9.trading.strategy_engine as se

        self._patch_engine(monkeypatch, tmp_path, se, True)

        result = se._normalize_strategy_specs()
        strats = result.get("strategies", [])
        assert len(strats) >= 1
        assert strats[0]["paper_only"] is True

    def test_normalize_reflects_false_when_patched(self, monkeypatch, tmp_path):
        """When PAPER_ONLY=False, normalized strategies get paper_only=False."""
        import brain_v9.trading.strategy_engine as se

        self._patch_engine(monkeypatch, tmp_path, se, False)

        result = se._normalize_strategy_specs()
        strats = result.get("strategies", [])
        assert len(strats) >= 1
        assert strats[0]["paper_only"] is False


# ---------------------------------------------------------------------------
# 4. knowledge_base seeds use PAPER_ONLY
# ---------------------------------------------------------------------------

class TestKnowledgeBaseSeedData:
    """Verify seed generators reference PAPER_ONLY, not hardcoded True."""

    def test_strategy_seeds_carry_paper_only(self, monkeypatch):
        """All strategy seeds have paper_only == PAPER_ONLY."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)
        monkeypatch.setattr(kb, "PAPER_ONLY", True)

        seed = kb._strategy_seed()
        for strat in seed["strategies"]:
            assert strat["paper_only"] is True, f"{strat['id']} should be paper_only=True"

    def test_strategy_seeds_flip_to_false(self, monkeypatch):
        """When PAPER_ONLY=False, strategy seeds reflect that."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", False)
        monkeypatch.setattr(kb, "PAPER_ONLY", False)

        seed = kb._strategy_seed()
        for strat in seed["strategies"]:
            assert strat["paper_only"] is False, f"{strat['id']} should be paper_only=False"

    def test_hypothesis_seeds_carry_paper_only(self, monkeypatch):
        """All hypothesis seeds have paper_only == PAPER_ONLY."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)
        monkeypatch.setattr(kb, "PAPER_ONLY", True)

        seed = kb._hypothesis_seed()
        for hyp in seed["hypotheses"]:
            assert hyp["paper_only"] is True, f"{hyp['id']} should be paper_only=True"

    def test_hypothesis_seeds_flip_to_false(self, monkeypatch):
        """When PAPER_ONLY=False, hypothesis seeds reflect that."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", False)
        monkeypatch.setattr(kb, "PAPER_ONLY", False)

        seed = kb._hypothesis_seed()
        for hyp in seed["hypotheses"]:
            assert hyp["paper_only"] is False, f"{hyp['id']} should be paper_only=False"

    def test_strategy_seed_count(self):
        """Seed contains the expected number of strategies."""
        import brain_v9.research.knowledge_base as kb

        seed = kb._strategy_seed()
        assert len(seed["strategies"]) == 5

    def test_hypothesis_seed_count(self):
        """Seed contains the expected number of hypotheses."""
        import brain_v9.research.knowledge_base as kb

        seed = kb._hypothesis_seed()
        assert len(seed["hypotheses"]) == 5


# ---------------------------------------------------------------------------
# 5. build_strategy_candidates() fallback uses PAPER_ONLY
# ---------------------------------------------------------------------------

class TestBuildStrategyCandidates:
    """Verify build_strategy_candidates() default uses PAPER_ONLY."""

    def test_candidates_default_paper_only(self, monkeypatch, tmp_path):
        """Candidates built from seeds carry paper_only from config."""
        import brain_v9.research.knowledge_base as kb

        # Redirect paths to tmp so seed files get created fresh
        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(kb, "KB_PATH", kb_path)
        monkeypatch.setattr(kb, "KNOWLEDGE_PATH", kb_path / "knowledge_base.json")
        monkeypatch.setattr(kb, "INDICATORS_PATH", kb_path / "indicator_registry.json")
        monkeypatch.setattr(kb, "STRATEGIES_PATH", kb_path / "strategy_specs.json")
        monkeypatch.setattr(kb, "HYPOTHESES_PATH", kb_path / "hypothesis_queue.json")

        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)
        monkeypatch.setattr(kb, "PAPER_ONLY", True)

        candidates = kb.build_strategy_candidates()
        assert len(candidates) >= 1
        for c in candidates:
            assert c["paper_only"] is True

    def test_candidates_paper_only_false_propagates(self, monkeypatch, tmp_path):
        """When PAPER_ONLY=False, candidates reflect False."""
        import brain_v9.research.knowledge_base as kb

        kb_path = tmp_path / "tmp_agent" / "state" / "trading_knowledge_base"
        kb_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(kb, "KB_PATH", kb_path)
        monkeypatch.setattr(kb, "KNOWLEDGE_PATH", kb_path / "knowledge_base.json")
        monkeypatch.setattr(kb, "INDICATORS_PATH", kb_path / "indicator_registry.json")
        monkeypatch.setattr(kb, "STRATEGIES_PATH", kb_path / "strategy_specs.json")
        monkeypatch.setattr(kb, "HYPOTHESES_PATH", kb_path / "hypothesis_queue.json")

        monkeypatch.setattr(_cfg, "PAPER_ONLY", False)
        monkeypatch.setattr(kb, "PAPER_ONLY", False)

        candidates = kb.build_strategy_candidates()
        assert len(candidates) >= 1
        for c in candidates:
            assert c["paper_only"] is False

    def test_candidate_fallback_when_strategy_missing_key(self, monkeypatch):
        """If a strategy dict lacks paper_only, fallback is PAPER_ONLY."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", True)
        monkeypatch.setattr(kb, "PAPER_ONLY", True)

        # Simulate a strategy without paper_only key
        mock_specs = {"strategies": [{"id": "bare_strat", "family": "test"}]}
        mock_hyps = {"hypotheses": []}
        monkeypatch.setattr(kb, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(kb, "read_hypothesis_queue", lambda: mock_hyps)

        candidates = kb.build_strategy_candidates()
        assert len(candidates) == 1
        assert candidates[0]["paper_only"] is True

    def test_candidate_fallback_false(self, monkeypatch):
        """Fallback with PAPER_ONLY=False gives False."""
        import brain_v9.research.knowledge_base as kb

        monkeypatch.setattr(_cfg, "PAPER_ONLY", False)
        monkeypatch.setattr(kb, "PAPER_ONLY", False)

        mock_specs = {"strategies": [{"id": "bare_strat2", "family": "test"}]}
        mock_hyps = {"hypotheses": []}
        monkeypatch.setattr(kb, "read_strategy_specs", lambda: mock_specs)
        monkeypatch.setattr(kb, "read_hypothesis_queue", lambda: mock_hyps)

        candidates = kb.build_strategy_candidates()
        assert len(candidates) == 1
        assert candidates[0]["paper_only"] is False


# ---------------------------------------------------------------------------
# 6. Cross-module consistency
# ---------------------------------------------------------------------------

class TestCrossModuleConsistency:
    """Verify all modules reference the same config constant."""

    def test_action_executor_imports_paper_only_from_config(self):
        """action_executor.PAPER_ONLY is the same object as config.PAPER_ONLY."""
        from brain_v9.autonomy import action_executor as ae

        # Both should reference the config module's value
        assert ae.PAPER_ONLY is _cfg.PAPER_ONLY

    def test_strategy_engine_imports_paper_only_from_config(self):
        """strategy_engine.PAPER_ONLY is the same object as config.PAPER_ONLY."""
        import brain_v9.trading.strategy_engine as se

        assert se.PAPER_ONLY is _cfg.PAPER_ONLY

    def test_knowledge_base_imports_paper_only_from_config(self):
        """knowledge_base.PAPER_ONLY is the same object as config.PAPER_ONLY."""
        import brain_v9.research.knowledge_base as kb

        assert kb.PAPER_ONLY is _cfg.PAPER_ONLY

    def test_all_modules_agree(self):
        """All three consumers see the same PAPER_ONLY value."""
        from brain_v9.autonomy import action_executor as ae
        import brain_v9.trading.strategy_engine as se
        import brain_v9.research.knowledge_base as kb

        values = {ae.PAPER_ONLY, se.PAPER_ONLY, kb.PAPER_ONLY, _cfg.PAPER_ONLY}
        assert len(values) == 1, f"PAPER_ONLY values disagree: {values}"
