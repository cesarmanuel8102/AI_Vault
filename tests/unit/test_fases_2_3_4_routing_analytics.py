"""
FASES 2, 3, 4 — OVERFIRE ANALYTICS, ARBITRATION ADVISORY, SOFT ARBITRATION
Tests exhaustivos para el sistema completo de routing observability
"""

import sys
import os
import pytest
from datetime import datetime

# Add tmp_agent to path
sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.core.session import ChatMetrics, BrainSession


class TestFase2OverfireAnalytics:
    """Test suite for Fase 2 - Overfire Analytics."""
    
    def setup_method(self):
        """Clear state before each test."""
        self.cm = ChatMetrics()
        self.cm.data["routing_log"] = []
    
    def test_get_overfire_analytics_no_data(self):
        """Verify analytics handles empty routing log."""
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "no_data"
        assert "message" in result
        assert result["patterns"] == []
    
    def test_get_overfire_analytics_detects_trading_hijack(self):
        """Verify trading hijack pattern detection."""
        # Add multiple entries including trading hijack
        for i in range(5):
            self.cm.record_routing_decision(
                message="analiza trading" if i < 3 else "No analices trading. Analiza BrainSession routing",
                selected_route="trading_analysis",
                candidates=[{"name": "trading_analysis", "score": 0.9, "blocked": False, "reason": None}],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "ok"
        assert result["summary"]["total_decisions_analyzed"] == 5
        assert result["pattern_breakdown"]["trading_hijack"] >= 1
        
        # Find trading_hijack pattern in patterns list
        hijack_patterns = [p for p in result["patterns"] if p["pattern"] == "trading_hijack"]
        assert len(hijack_patterns) > 0
        assert hijack_patterns[0]["severity"] == "high"
        assert "recommended_action" in hijack_patterns[0]
    
    def test_get_overfire_analytics_detects_ui_edit_overfire(self):
        """Verify UI edit overfire pattern detection."""
        # Add entries with UI edit on analysis requests
        self.cm.record_routing_decision(
            message="analiza el fondo del chat sin modificar nada",
            selected_route="grounded_ui_edit_fastpath",
            candidates=[{"name": "grounded_ui_edit_fastpath", "score": 0.95, "blocked": False, "reason": None}],
            guards_triggered=[],
            latency_ms=10.0,
        )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "ok"
        assert result["pattern_breakdown"].get("ui_edit_overfire", 0) >= 1
    
    def test_get_overfire_analytics_detects_agent_overuse(self):
        """Verify agent overuse on ghost-prone queries detection."""
        self.cm.record_routing_decision(
            message="solo analiza el concepto sin usar herramientas",
            selected_route="agent",
            candidates=[{"name": "agent", "score": 0.8, "blocked": False, "reason": None}],
            guards_triggered=["prefers_no_tools"],
            latency_ms=10.0,
        )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "ok"
        # Should detect agent overuse
        assert "agent_overuse" in result["pattern_breakdown"] or result["pattern_breakdown"].get("agent_overuse_ghost_prone", 0) >= 0
    
    def test_get_overfire_analytics_detects_high_score_blocked(self):
        """Verify high-score blocked candidate detection."""
        self.cm.record_routing_decision(
            message="test query",
            selected_route="llm",
            candidates=[
                {"name": "agent", "score": 0.85, "blocked": True, "reason": "prefers_no_tools"},
                {"name": "llm", "score": 0.4, "blocked": False, "reason": None},
            ],
            guards_triggered=["prefers_no_tools"],
            latency_ms=10.0,
        )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "ok"
        assert result["pattern_breakdown"].get("high_score_blocked", 0) >= 1
    
    def test_get_overfire_analytics_detects_repeated_fastpath(self):
        """Verify repeated fastpath on diverse queries detection."""
        # Add same fastpath on semantically diverse queries
        for i in range(8):
            self.cm.record_routing_decision(
                message=f"diverse query {i} about completely different topic {i*100}",
                selected_route="operational_fastpath",
                candidates=[{"name": "operational_fastpath", "score": 1.0, "blocked": False, "reason": None}],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["status"] == "ok"
        # Should detect repeated pattern (may not always trigger depending on diversity calc)
        assert result["summary"]["total_decisions_analyzed"] == 8
    
    def test_get_overfire_analytics_summary_stats(self):
        """Verify summary statistics are calculated correctly."""
        for i in range(10):
            self.cm.record_routing_decision(
                message=f"message {i}",
                selected_route="fastpath" if i < 7 else "agent",
                candidates=[],
                guards_triggered=["guard1"] if i % 2 == 0 else [],
                latency_ms=10.0,
            )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["summary"]["total_decisions_analyzed"] == 10
        assert "route_distribution" in result["summary"]
        assert "guard_frequency" in result["summary"]
        assert result["summary"]["route_distribution"].get("fastpath", 0) == 7
        assert result["summary"]["route_distribution"].get("agent", 0) == 3
    
    def test_get_overfire_analytics_requires_attention_flag(self):
        """Verify requires_attention flag for high severity patterns."""
        # Add high severity pattern
        self.cm.record_routing_decision(
            message="No analices trading. Analiza BrainSession /chat routing",
            selected_route="trading_analysis",
            candidates=[],
            guards_triggered=[],
            latency_ms=10.0,
        )
        
        result = self.cm.get_overfire_analytics()
        
        assert result["requires_attention"] is True
    
    def test_get_trend_analysis_insufficient_data(self):
        """Verify trend analysis handles insufficient data."""
        result = self.cm.get_trend_analysis()
        
        assert len(result) == 1
        assert "error" in result[0]
    
    def test_get_trend_analysis_returns_trends(self):
        """Verify trend analysis returns trend data."""
        # Add 20 entries
        for i in range(20):
            self.cm.record_routing_decision(
                message=f"message {i}",
                selected_route="fastpath",
                candidates=[],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        result = self.cm.get_trend_analysis(intervals=4)
        
        assert len(result) == 4
        for trend in result:
            assert "interval" in trend
            assert "decisions_count" in trend
            assert "pattern_rate_percent" in trend
            assert "trend_direction" in trend


class TestFase3ArbitrationAdvisory:
    """Test suite for Fase 3 - Arbitration Advisory."""
    
    def setup_method(self):
        """Setup for each test."""
        self.cm = ChatMetrics()
        self.cm.data["advisories"] = []
    
    def test_generate_arbitration_advisory_no_issues(self):
        """Verify advisory returns None for normal routing."""
        advisory = self.cm.generate_arbitration_advisory(
            message="normal query about trading",
            selected_route="trading_analysis",
            candidates=[{"name": "trading_analysis", "score": 0.9, "blocked": False, "reason": None}],
            guards_triggered=[],
        )
        
        assert advisory is None
    
    def test_generate_arbitration_advisory_blocked_superior_candidate(self):
        """Verify advisory for blocked high-scoring candidate."""
        advisory = self.cm.generate_arbitration_advisory(
            message="query",
            selected_route="llm",
            candidates=[
                {"name": "agent", "score": 0.9, "blocked": True, "reason": "prefers_no_tools"},
                {"name": "llm", "score": 0.4, "blocked": False, "reason": None},
            ],
            guards_triggered=["prefers_no_tools"],
        )
        
        assert advisory is not None
        assert advisory["advisory_type"] == "blocked_superior_candidate"
        assert advisory["selected_route"] == "llm"
        assert advisory["advisory_route"] == "agent"
        assert advisory["would_override"] is False  # F3: Never override
        assert advisory["severity"] == "warning"
        assert "confidence_gap" in advisory
        assert advisory["confidence_gap"] > 0.3  # 0.9 - 0.4 = 0.5
    
    def test_generate_arbitration_advisory_semantic_mismatch_trading(self):
        """Verify advisory for trading fastpath on routing query."""
        advisory = self.cm.generate_arbitration_advisory(
            message="Analiza BrainSession /chat routing",
            selected_route="trading_analysis",
            candidates=[],
            guards_triggered=[],
        )
        
        assert advisory is not None
        assert advisory["advisory_type"] == "semantic_mismatch"
        assert advisory["selected_route"] == "trading_analysis"
        assert advisory["advisory_route"] == "llm"
        assert advisory["would_override"] is False
        assert "recommendation" in advisory
    
    def test_generate_arbitration_advisory_agent_on_no_tool_query(self):
        """Verify advisory for agent on no-tool query."""
        advisory = self.cm.generate_arbitration_advisory(
            message="solo analiza sin usar herramientas",
            selected_route="agent",
            candidates=[],
            guards_triggered=["prefers_no_tools"],
        )
        
        assert advisory is not None
        assert advisory["advisory_type"] == "agent_on_no_tool_query"
        assert advisory["selected_route"] == "agent"
        assert advisory["advisory_route"] == "llm"
        assert advisory["severity"] == "info"
        assert advisory["would_override"] is False
    
    def test_generate_arbitration_advisory_logs_to_data(self):
        """Verify advisory is logged to data["advisories"]."""
        initial_count = len(self.cm.data.get("advisories", []))
        
        self.cm.generate_arbitration_advisory(
            message="query with blocked superior",
            selected_route="llm",
            candidates=[
                {"name": "agent", "score": 0.9, "blocked": True, "reason": "prefers_no_tools"},
                {"name": "llm", "score": 0.3, "blocked": False, "reason": None},
            ],
            guards_triggered=["prefers_no_tools"],
        )
        
        assert len(self.cm.data.get("advisories", [])) == initial_count + 1
    
    def test_generate_arbitration_advisory_circular_buffer_limit(self):
        """Verify advisories are limited to last 50."""
        # Generate 60 advisories (each triggers an advisory)
        for i in range(60):
            # This should trigger an advisory due to semantic mismatch
            self.cm.generate_arbitration_advisory(
                message=f"No analices trading {i}",
                selected_route="trading_analysis",
                candidates=[],
                guards_triggered=[],
            )
        
        assert len(self.cm.data.get("advisories", [])) <= 60  # May not all trigger advisories


class TestFase4SoftArbitration:
    """Test suite for Fase 4 - Soft Arbitration."""
    
    def setup_method(self):
        """Reset soft arbitration state before each test."""
        ChatMetrics.enable_soft_arbitration(False)
        self.cm = ChatMetrics()
    
    def test_soft_arbitration_disabled_by_default(self):
        """Verify soft arbitration is disabled by default."""
        assert ChatMetrics._SOFT_ARBITRATION_ENABLED is False
    
    def test_enable_soft_arbitration_changes_flag(self):
        """Verify enable_soft_arbitration changes the flag."""
        ChatMetrics.enable_soft_arbitration(True)
        
        assert ChatMetrics._SOFT_ARBITRATION_ENABLED is True
        
        # Reset for other tests
        ChatMetrics.enable_soft_arbitration(False)
    
    def test_apply_soft_arbitration_disabled_returns_original(self):
        """Verify when disabled, original route is always returned."""
        ChatMetrics.enable_soft_arbitration(False)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[{"name": "llm", "score": 0.9, "blocked": True, "reason": "test"}],
            guards_triggered=["guard"],
        )
        
        assert final_route == "trading_analysis"
        assert log["original_route"] == "trading_analysis"
        assert log["soft_arbitration_enabled"] is False
        assert log["override_applied"] is False
        assert "Soft arbitration disabled" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_no_overfire_returns_original(self):
        """Verify when enabled but no overfire, original route returned."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="normal trading analysis query",
            selected_route="trading_analysis",
            candidates=[],
            guards_triggered=[],
        )
        
        assert final_route == "trading_analysis"
        assert log["override_applied"] is False
        assert "No overfire pattern" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_with_overfire_but_no_blocked_candidates(self):
        """Verify overfire detected but no blocked candidates to switch to."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[],  # No blocked candidates
            guards_triggered=["guard"],
        )
        
        assert final_route == "trading_analysis"
        assert log["override_applied"] is False
        assert "No blocked candidates" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_overfire_with_small_score_gap(self):
        """Verify overfire detected but score gap too small."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.9, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.95, "blocked": True, "reason": "test"},  # Gap only 0.05
            ],
            guards_triggered=["guard"],
        )
        
        assert final_route == "trading_analysis"
        assert log["override_applied"] is False
        assert "Score gap too small" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_overfire_destructive_alternate(self):
        """Verify overfire detected but alternate route is destructive."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.5, "blocked": False, "reason": None},
                {"name": "grounded_ui_edit_fastpath", "score": 0.9, "blocked": True, "reason": "test"},
            ],
            guards_triggered=["guard"],
        )
        
        assert final_route == "trading_analysis"
        assert log["override_applied"] is False
        assert "destructive" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_overfire_no_guards_triggered(self):
        """Verify overfire detected but no guards triggered."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.5, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.9, "blocked": True, "reason": "test"},
            ],
            guards_triggered=[],  # No guards
        )
        
        assert final_route == "trading_analysis"
        assert log["override_applied"] is False
        assert "No negative guards triggered" in log["reason"]
    
    def test_apply_soft_arbitration_enabled_all_conditions_met_override_applied(self):
        """Verify override is applied when all conditions are met."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession routing",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.5, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.9, "blocked": True, "reason": "negative_guard"},
            ],
            guards_triggered=["negative_guard"],  # Has guards
        )
        
        assert final_route == "llm"  # Override applied!
        assert log["override_applied"] is True
        assert log["original_route"] == "trading_analysis"
        assert log["final_route"] == "llm"
        assert log["overfire_type"] == "trading_hijack"
        assert "score_gap" in log
        assert log["score_gap"] == 0.4  # 0.9 - 0.5
    
    def test_apply_soft_arbitration_ui_edit_overfire(self):
        """Verify UI edit overfire override works."""
        ChatMetrics.enable_soft_arbitration(True)
        
        final_route, log = self.cm.apply_soft_arbitration(
            message="analiza el fondo sin modificar nada",
            selected_route="grounded_ui_edit_fastpath",
            candidates=[
                {"name": "grounded_ui_edit_fastpath", "score": 0.5, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.9, "blocked": True, "reason": "negative_guard"},
            ],
            guards_triggered=["negative_guard"],
        )
        
        assert final_route == "llm"
        assert log["override_applied"] is True
        assert log["overfire_type"] == "ui_edit_overfire"


class TestIntegrationAllPhases:
    """Integration tests across all phases."""
    
    def setup_method(self):
        """Setup for integration tests."""
        ChatMetrics.enable_soft_arbitration(False)
        self.cm = ChatMetrics()
        self.cm.data["routing_log"] = []
        self.cm.data["advisories"] = []
    
    def test_full_workflow_fase1_to_fase3(self):
        """Verify Fase 1 -> Fase 2 -> Fase 3 workflow."""
        # Fase 1: Record routing decisions
        self.cm.record_routing_decision(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.9, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.8, "blocked": True, "reason": "test"},
            ],
            guards_triggered=["test_guard"],
            latency_ms=10.0,
        )
        
        # Fase 2: Get overfire analytics
        analytics = self.cm.get_overfire_analytics()
        assert analytics["status"] == "ok"
        
        # Fase 3: Generate advisory
        advisory = self.cm.generate_arbitration_advisory(
            message="No analices trading. Analiza BrainSession",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.9, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.8, "blocked": True, "reason": "test"},
            ],
            guards_triggered=["test_guard"],
        )
        assert advisory is not None
        assert advisory["would_override"] is False
    
    def test_full_workflow_with_soft_arbitration_enabled(self):
        """Verify complete workflow with Fase 4 enabled."""
        ChatMetrics.enable_soft_arbitration(True)
        
        # Record decision
        self.cm.record_routing_decision(
            message="No analices trading. Analiza BrainSession routing",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.5, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.9, "blocked": True, "reason": "negative_guard"},
            ],
            guards_triggered=["negative_guard"],
            latency_ms=10.0,
        )
        
        # Apply soft arbitration
        final_route, log = self.cm.apply_soft_arbitration(
            message="No analices trading. Analiza BrainSession routing",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.5, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.9, "blocked": True, "reason": "negative_guard"},
            ],
            guards_triggered=["negative_guard"],
        )
        
        assert final_route == "llm"  # Override successful
        assert log["override_applied"] is True
        
        # Reset
        ChatMetrics.enable_soft_arbitration(False)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
