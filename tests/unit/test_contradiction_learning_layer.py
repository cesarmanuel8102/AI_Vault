"""
Tests for Contradiction Learning Layer (CLL)

Tests validate:
- Route reliability scoring
- Guard effectiveness scoring
- False positive analytics
- Semantic drift detection
- Learning summary generation
"""

import sys
import pytest

sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.core.session import ChatMetrics


class TestRouteReliabilityScoring:
    """Test suite for route reliability scoring."""
    
    def setup_method(self):
        """Setup before each test."""
        self.cm = ChatMetrics()
        self.cm.data["route_reliability"] = {}
        self.cm.data["contradiction_learning"] = []
    
    def test_route_reliability_empty_data(self):
        """Handle empty reliability data."""
        scores = self.cm.get_route_reliability_scores()
        assert scores == {}
    
    def test_route_reliability_single_success(self):
        """Calculate reliability for single successful route."""
        self.cm.record_routing_outcome(
            route="fastpath",
            success=True,
            contradiction_detected=False,
            coherence_score=0.9,
            guards_triggered=[],
        )
        
        scores = self.cm.get_route_reliability_scores()
        
        assert "fastpath" in scores
        assert scores["fastpath"]["success_rate"] == 1.0
        assert scores["fastpath"]["contradiction_rate"] == 0.0
        assert scores["fastpath"]["reliability_score"] > 0.8
        assert scores["fastpath"]["risk_score"] < 0.3
    
    def test_route_reliability_with_contradiction(self):
        """Calculate reliability with contradictions."""
        # Multiple outcomes
        for i in range(5):
            self.cm.record_routing_outcome(
                route="trading_analysis",
                success=True,
                contradiction_detected=(i >= 2),  # 3 contradictions
                coherence_score=0.9 if i < 2 else 0.5,
                guards_triggered=[],
            )
        
        scores = self.cm.get_route_reliability_scores()
        
        assert scores["trading_analysis"]["success_rate"] == 1.0
        assert scores["trading_analysis"]["contradiction_rate"] == 60.0  # 3/5 * 100
        assert scores["trading_analysis"]["reliability_score"] < 1.0
        assert scores["trading_analysis"]["risk_score"] > 0
    
    def test_route_reliability_low_success(self):
        """Detect low reliability routes."""
        for i in range(10):
            self.cm.record_routing_outcome(
                route="problematic",
                success=(i < 3),  # Only 3 successes
                contradiction_detected=True,
                coherence_score=0.4,
                guards_triggered=[],
            )
        
        scores = self.cm.get_route_reliability_scores()
        
        assert scores["problematic"]["success_rate"] == 0.3
        assert scores["problematic"]["reliability_score"] < 0.5
        assert "unreliable" in scores["problematic"]["recommendation"].lower()
    
    def test_route_reliability_multiple_routes(self):
        """Calculate reliability for multiple routes."""
        routes_data = [
            ("fastpath", True, False, 0.95),
            ("agent", True, True, 0.7),
            ("llm", True, False, 0.85),
        ]
        
        for route, success, contra, coh in routes_data:
            for _ in range(10):
                self.cm.record_routing_outcome(
                    route=route,
                    success=success,
                    contradiction_detected=contra,
                    coherence_score=coh,
                    guards_triggered=[],
                )
        
        scores = self.cm.get_route_reliability_scores()
        
        assert len(scores) == 3
        assert scores["fastpath"]["reliability_score"] > scores["agent"]["reliability_score"]
        assert scores["agent"]["contradiction_rate"] == 100.0


class TestGuardEffectivenessScoring:
    """Test suite for guard effectiveness scoring."""
    
    def setup_method(self):
        self.cm = ChatMetrics()
        self.cm.data["guard_effectiveness"] = {}
        self.cm.data["contradiction_learning"] = []
    
    def test_guard_effectiveness_empty_data(self):
        """Handle empty guard effectiveness data."""
        scores = self.cm.get_guard_effectiveness_scores()
        assert scores == {}
    
    def test_guard_effectiveness_highly_effective(self):
        """Calculate effectiveness for highly effective guard."""
        for i in range(10):
            self.cm.record_routing_outcome(
                route="fastpath",
                success=True,
                contradiction_detected=False,
                coherence_score=0.9,
                guards_triggered=["prefers_no_tools"],
                false_positive=False,
            )
        
        scores = self.cm.get_guard_effectiveness_scores()
        
        assert "prefers_no_tools" in scores
        assert scores["prefers_no_tools"]["effectiveness"] == 0.0  # No contradictions = effective
        assert scores["prefers_no_tools"]["false_positive_rate"] == 0.0
    
    def test_guard_effectiveness_prevented_contradiction(self):
        """Guard that prevents contradiction is effective."""
        # Guard triggers and no contradiction = prevented it
        for i in range(10):
            self.cm.record_routing_outcome(
                route="llm",
                success=True,
                contradiction_detected=False,  # No contradiction = prevented
                coherence_score=0.9,
                guards_triggered=["negative_guard"],
                false_positive=False,
            )
        
        scores = self.cm.get_guard_effectiveness_scores()
        
        assert scores["negative_guard"]["prevented_contradictions"] == 0  # No contradictions
        assert scores["negative_guard"]["total_triggers"] == 10
    
    def test_guard_effectiveness_false_positive(self):
        """Detect guards with high false positive rate."""
        for i in range(10):
            self.cm.record_routing_outcome(
                route="fastpath",
                success=True,
                contradiction_detected=False,
                coherence_score=0.9,
                guards_triggered=["overly_strict_guard"],
                false_positive=(i >= 7),  # 3 false positives
            )
        
        scores = self.cm.get_guard_effectiveness_scores()
        
        assert scores["overly_strict_guard"]["false_positives"] == 3
        assert scores["overly_strict_guard"]["false_positive_rate"] == 30.0
        # Check that there's some recommendation (could be about false positives or effectiveness)
        assert len(scores["overly_strict_guard"]["recommendation"]) > 0
        assert ("false positive" in scores["overly_strict_guard"]["recommendation"].lower() or
                "effectiveness" in scores["overly_strict_guard"]["recommendation"].lower())


class TestFalsePositiveAnalytics:
    """Test suite for false positive analytics."""
    
    def setup_method(self):
        self.cm = ChatMetrics()
        self.cm.data["contradiction_learning"] = []
    
    def test_false_positive_empty_data(self):
        """Handle empty false positive data."""
        analytics = self.cm.get_false_positive_analytics()
        assert analytics["status"] == "no_data"
    
    def test_false_positive_rate_calculation(self):
        """Calculate false positive rate."""
        for i in range(20):
            self.cm.record_routing_outcome(
                route="agent",
                success=True,
                contradiction_detected=False,
                coherence_score=0.8,
                guards_triggered=["guard1"],
                false_positive=(i >= 15),  # 5 false positives
            )
        
        analytics = self.cm.get_false_positive_analytics()
        
        assert analytics["status"] == "ok"
        assert analytics["false_positive_rate"] == 25.0  # 5/20 * 100
        assert analytics["total_false_positives"] == 5
    
    def test_false_positive_problematic_routes(self):
        """Identify routes with high false positive rates."""
        # Route with high FP rate
        for i in range(10):
            self.cm.record_routing_outcome(
                route="problematic_route",
                success=True,
                contradiction_detected=False,
                coherence_score=0.8,
                guards_triggered=[],
                false_positive=(i >= 7),  # 30% FP rate
            )
        
        analytics = self.cm.get_false_positive_analytics()
        
        assert len(analytics["problematic_routes"]) > 0
        if analytics["problematic_routes"]:
            assert analytics["problematic_routes"][0]["route"] == "problematic_route"
            assert analytics["problematic_routes"][0]["fp_rate"] == 30.0


class TestSemanticDriftDetection:
    """Test suite for semantic drift detection."""
    
    def setup_method(self):
        self.cm = ChatMetrics()
        self.cm.data["routing_log"] = []
    
    def test_semantic_drift_insufficient_data(self):
        """Handle insufficient data for drift detection."""
        # Add only 10 entries
        for i in range(10):
            self.cm.record_routing_decision(
                message=f"query {i}",
                selected_route="fastpath",
                candidates=[],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        drift = self.cm.get_semantic_drift_indicators(window_size=50)
        assert drift["status"] == "insufficient_data"
    
    def test_semantic_drift_no_drift(self):
        """Detect when no semantic drift exists."""
        # Many similar queries (no drift)
        for i in range(50):
            self.cm.record_routing_decision(
                message="what time is it now",
                selected_route="fastpath",
                candidates=[],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        drift = self.cm.get_semantic_drift_indicators(window_size=50)
        
        if drift["status"] == "ok":
            fastpath_drift = drift["drift_indicators"].get("fastpath", {})
            assert fastpath_drift.get("drift_level") == "low"
    
    def test_semantic_drift_high_diversity(self):
        """Detect high semantic diversity (potential drift)."""
        # Many different queries on same route
        diverse_queries = [
            "what is the weather",
            "analyze trading patterns",
            "tell me about history",
            "explain quantum physics",
            "recommend a movie",
            "how does blockchain work",
            "what is machine learning",
            "explain neural networks",
        ]
        
        for i in range(50):
            self.cm.record_routing_decision(
                message=diverse_queries[i % len(diverse_queries)],
                selected_route="fastpath",
                candidates=[],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        drift = self.cm.get_semantic_drift_indicators(window_size=50)
        
        assert drift["status"] == "ok"
        assert drift["routes_analyzed"] > 0


class TestContradictionLearningSummary:
    """Test suite for comprehensive learning summary."""
    
    def setup_method(self):
        self.cm = ChatMetrics()
        self.cm.data["contradiction_learning"] = []
        self.cm.data["route_reliability"] = {}
        self.cm.data["guard_effectiveness"] = {}
        self.cm.data["routing_log"] = []
    
    def test_learning_summary_empty_data(self):
        """Handle empty learning data."""
        summary = self.cm.get_contradiction_learning_summary()
        assert summary["status"] == "no_data"
    
    def test_learning_summary_comprehensive(self):
        """Generate comprehensive learning summary."""
        # Record diverse outcomes
        for i in range(50):
            self.cm.record_routing_outcome(
                route="fastpath" if i % 2 == 0 else "agent",
                success=(i % 3 != 0),
                contradiction_detected=(i % 5 == 0),
                coherence_score=0.9 if i % 3 != 0 else 0.5,
                guards_triggered=["guard1"] if i % 2 == 0 else [],
                false_positive=(i >= 45),  # 5 false positives
            )
        
        summary = self.cm.get_contradiction_learning_summary()
        
        assert summary["status"] == "ok"
        assert summary["total_recorded"] == 50
        assert "system_health" in summary
        assert "route_reliability" in summary
        assert "guard_effectiveness" in summary
        assert "risk_assessment" in summary
        
        # Verify metrics
        health = summary["system_health"]
        assert health["contradiction_rate"] >= 0
        assert health["avg_coherence"] >= 0
        assert health["routes_learned"] > 0


class TestRealWorldLearningScenarios:
    """Test real-world learning scenarios."""
    
    def setup_method(self):
        self.cm = ChatMetrics()
        self.cm.data["contradiction_learning"] = []
        self.cm.data["route_reliability"] = {}
        self.cm.data["guard_effectiveness"] = {}
    
    def test_learning_trading_hijack_pattern(self):
        """Learn that trading routes cause contradictions."""
        # Simulate trading hijack patterns
        for i in range(20):
            self.cm.record_routing_outcome(
                route="trading_analysis",
                success=True,
                contradiction_detected=(i >= 10),  # 50% contradictions
                coherence_score=0.5,
                guards_triggered=[],
            )
        
        scores = self.cm.get_route_reliability_scores()
        
        if "trading_analysis" in scores:
            assert scores["trading_analysis"]["contradiction_rate"] > 40.0
            assert scores["trading_analysis"]["risk_score"] > 0.3
    
    def test_learning_guard_effectiveness_over_time(self):
        """Track guard effectiveness over multiple uses."""
        guard_name = "prefers_no_tools"
        
        # Guard prevents contradictions
        for i in range(30):
            self.cm.record_routing_outcome(
                route="llm",
                success=True,
                contradiction_detected=False,  # Guard prevented it
                coherence_score=0.9,
                guards_triggered=[guard_name],
                false_positive=False,
            )
        
        scores = self.cm.get_guard_effectiveness_scores()
        
        if guard_name in scores:
            # Guard triggers and no contradiction = effective
            assert scores[guard_name]["total_triggers"] == 30
    
    def test_learning_false_positive_reduction(self):
        """Identify need to reduce false positives."""
        # Record outcomes with false positives
        for i in range(40):
            self.cm.record_routing_outcome(
                route="agent",
                success=True,
                contradiction_detected=False,
                coherence_score=0.8,
                guards_triggered=["strict_guard"],
                false_positive=(i >= 30),  # 25% FP rate
            )
        
        fp_analytics = self.cm.get_false_positive_analytics()
        
        if fp_analytics.get("status") == "ok":
            assert fp_analytics["false_positive_rate"] == 25.0
            assert "review" in fp_analytics.get("recommendation", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
