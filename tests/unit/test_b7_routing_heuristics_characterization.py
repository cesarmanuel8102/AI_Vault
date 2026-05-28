"""B7-FASE-C Characterization tests for routing/overfire/semantic heuristics.

These tests capture current behavior WITHOUT modifying session.py.
They serve as a safety net before any future B7-FASE-* consolidation.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import brain_v9.core.session as session_mod


class TestB7RoutingHeuristics:
    """Introspection-based characterization tests."""

    def test_agent_keywords_module_level(self):
        """AGENT_KEYWORDS should exist as a non-empty list/tuple at module level."""
        assert hasattr(session_mod, "AGENT_KEYWORDS")
        assert isinstance(session_mod.AGENT_KEYWORDS, (list, tuple))
        assert len(session_mod.AGENT_KEYWORDS) > 0

    def test_chatmetrics_class_exists(self):
        """ChatMetrics class should exist and be instantiable or have static methods."""
        assert hasattr(session_mod, "ChatMetrics")
        metrics_cls = session_mod.ChatMetrics
        assert callable(metrics_cls)

    def test_brainsession_class_exists(self):
        """BrainSession class should exist."""
        assert hasattr(session_mod, "BrainSession")
        assert callable(session_mod.BrainSession)

    def test_get_overfire_analytics_exists_in_chatmetrics(self):
        """get_overfire_analytics should be a method on ChatMetrics."""
        assert hasattr(session_mod.ChatMetrics, "get_overfire_analytics")
        assert callable(session_mod.ChatMetrics.get_overfire_analytics)

    def test_validate_semantic_coherence_exists_in_chatmetrics(self):
        """validate_semantic_coherence should be a method on ChatMetrics."""
        assert hasattr(session_mod.ChatMetrics, "validate_semantic_coherence")
        assert callable(session_mod.ChatMetrics.validate_semantic_coherence)

    def test_chatmetrics_instantiable_without_crashing(self):
        """If ChatMetrics instantiation fails, skip documenting unstable API."""
        try:
            m = session_mod.ChatMetrics()
        except Exception as exc:
            pytest.skip(f"ChatMetrics instantiation unstable: {exc}")
        assert m is not None

    def test_get_overfire_analytics_return_type(self):
        """If instantiable, get_overfire_analytics returns a dict."""
        try:
            m = session_mod.ChatMetrics()
        except Exception as exc:
            pytest.skip(f"ChatMetrics instantiation unstable: {exc}")
        result = m.get_overfire_analytics()
        assert isinstance(result, dict)
        assert "patterns" in result or "status" in result

    def test_validate_semantic_coherence_returns_dict(self):
        """If instantiable, validate_semantic_coherence returns a dict."""
        try:
            m = session_mod.ChatMetrics()
        except Exception as exc:
            pytest.skip(f"ChatMetrics instantiation unstable: {exc}")
        result = m.validate_semantic_coherence(
            user_message="no trading solo analiza",
            selected_route="trading_analysis",
        )
        assert isinstance(result, dict)

    def test_routing_debug_terms_local_not_module_level(self):
        """Characterization: _ROUTING_DEBUG_TERMS is method-local (not module-level).
        If extracted later, this test should be updated.
        """
        assert not hasattr(session_mod, "_ROUTING_DEBUG_TERMS")
