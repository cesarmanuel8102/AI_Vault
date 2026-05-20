"""
FASE 1 - OBSERVABILIDAD: Tests exhaustivos para ChatMetrics extended

Tests para verificar:
1. routing_log functionality
2. record_routing_decision
3. get_routing_stats
4. _detect_overfire_candidates
"""

import sys
import json
import pytest
from pathlib import Path
from datetime import datetime

# Add tmp_agent to path
sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.core.session import ChatMetrics, get_chat_metrics


class TestChatMetricsExtended:
    """Test suite for Fase 1 - Observabilidad extensions."""
    
    def setup_method(self):
        """Clear routing_log before each test to ensure isolation."""
        cm = ChatMetrics()
        cm.data["routing_log"] = []
    
    def test_routing_log_exists_and_is_list(self):
        """Verify routing_log exists and is a list (may have data from previous tests)."""
        cm = ChatMetrics()
        assert "routing_log" in cm.data
        assert isinstance(cm.data["routing_log"], list)
        # Note: May have data from singleton, that's OK

    def test_record_routing_decision_creates_valid_entry(self):
        """Verify routing decision creates entry with all required fields."""
        cm = ChatMetrics()
        initial_count = len(cm.data["routing_log"])
        
        candidates = [
            {"name": "fastpath", "score": 0.9, "blocked": False, "reason": None},
            {"name": "agent", "score": 0.7, "blocked": True, "reason": "prefers_no_tools"},
        ]
        
        cm.record_routing_decision(
            message="Test message",
            selected_route="fastpath",
            candidates=candidates,
            guards_triggered=["prefers_no_tools"],
            latency_ms=15.5,
        )
        
        # Verify entry was added
        assert len(cm.data["routing_log"]) == initial_count + 1
        entry = cm.data["routing_log"][-1]
        
        assert "timestamp" in entry
        assert entry["message_preview"] == "Test message"
        assert entry["selected_route"] == "fastpath"
        assert len(entry["candidates"]) == 2
        assert entry["guards_triggered"] == ["prefers_no_tools"]
        assert entry["decision_latency_ms"] == 15.5
    
    def test_record_routing_decision_truncates_message(self):
        """Verify message preview is truncated to 200 chars."""
        cm = ChatMetrics()
        long_message = "x" * 500
        
        cm.record_routing_decision(
            message=long_message,
            selected_route="llm",
            candidates=[],
            guards_triggered=[],
            latency_ms=10.0,
        )
        
        entry = cm.data["routing_log"][0]
        assert len(entry["message_preview"]) <= 200
    
    def test_routing_log_circular_buffer_limits_to_100(self):
        """Verify only last 100 decisions are kept."""
        cm = ChatMetrics()
        
        # Add 150 entries
        for i in range(150):
            cm.record_routing_decision(
                message=f"Message {i}",
                selected_route="llm",
                candidates=[],
                guards_triggered=[],
                latency_ms=10.0,
            )
        
        assert len(cm.data["routing_log"]) == 100
        # Verify it kept the LAST 100 (messages 50-149)
        assert cm.data["routing_log"][0]["message_preview"] == "Message 50"
        assert cm.data["routing_log"][-1]["message_preview"] == "Message 149"
    
    def test_get_routing_stats_empty_log(self):
        """Verify stats handles empty routing log."""
        cm = ChatMetrics()
        stats = cm.get_routing_stats()
        
        assert "error" in stats
        assert stats["error"] == "No routing data available"
    
    def test_get_routing_stats_with_data(self):
        """Verify stats calculation with sample data."""
        cm = ChatMetrics()
        
        # Add diverse routing decisions
        for i in range(10):
            cm.record_routing_decision(
                message=f"Test {i}",
                selected_route="fastpath" if i < 7 else "agent",
                candidates=[
                    {"name": "fastpath", "score": 0.9, "blocked": False, "reason": None},
                    {"name": "agent", "score": 0.6, "blocked": i >= 7, "reason": "prefers_no_tools"},
                ],
                guards_triggered=["prefers_no_tools"] if i >= 7 else [],
                latency_ms=10.0 + i,
            )
        
        stats = cm.get_routing_stats()
        
        assert stats["total_decisions"] == 10
        assert stats["route_distribution"]["fastpath"] == 7
        assert stats["route_distribution"]["agent"] == 3
        assert "prefers_no_tools" in stats["guard_frequency"]
        assert stats["avg_candidates_evaluated"] == 2.0
    
    def test_detect_overfire_finds_trading_hijack(self):
        """Verify trading hijack pattern detection."""
        cm = ChatMetrics()
        
        # Add suspicious trading routing
        cm.record_routing_decision(
            message="No analices trading. Analiza BrainSession /chat routing",
            selected_route="trading_analysis",
            candidates=[
                {"name": "trading_analysis", "score": 0.95, "blocked": False, "reason": None},
                {"name": "llm", "score": 0.3, "blocked": False, "reason": None},
            ],
            guards_triggered=[],
            latency_ms=10.0,
        )
        
        suspicious = cm._detect_overfire_candidates()
        
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "trading_hijack"
        assert "brainsession" in suspicious[0]["risk"].lower() or "trading_hijack" in suspicious[0]["pattern"]
    
    def test_detect_overfire_finds_ui_edit_overfire(self):
        """Verify UI edit overfire pattern detection."""
        cm = ChatMetrics()
        
        cm.record_routing_decision(
            message="analiza el fondo sin modificar nada",
            selected_route="grounded_ui_edit_fastpath",
            candidates=[],
            guards_triggered=[],
            latency_ms=10.0,
        )
        
        suspicious = cm._detect_overfire_candidates()
        
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "ui_edit_overfire"
    
    def test_detect_overfire_finds_high_score_blocked(self):
        """Verify high-score blocked candidate detection."""
        cm = ChatMetrics()
        
        cm.record_routing_decision(
            message="Test query",
            selected_route="llm",
            candidates=[
                {"name": "agent", "score": 0.95, "blocked": True, "reason": "prefers_no_tools"},
                {"name": "llm", "score": 0.4, "blocked": False, "reason": None},
            ],
            guards_triggered=["prefers_no_tools"],
            latency_ms=10.0,
        )
        
        suspicious = cm._detect_overfire_candidates()
        
        assert len(suspicious) == 1
        assert suspicious[0]["pattern"] == "high_score_blocked"
    
    def test_persist_load_routing_log(self):
        """Verify routing_log survives persist/load cycle."""
        cm1 = ChatMetrics()
        
        cm1.record_routing_decision(
            message="Test persist",
            selected_route="fastpath",
            candidates=[{"name": "fastpath", "score": 1.0, "blocked": False, "reason": None}],
            guards_triggered=[],
            latency_ms=5.0,
        )
        
        # Force persist
        cm1.force_persist()
        
        # Create new instance (should load persisted data)
        cm2 = ChatMetrics()
        
        assert len(cm2.data["routing_log"]) >= 1
        # Note: May have previous entries from other tests


class TestRoutingIntegration:
    """Integration tests for routing observability."""
    
    def test_global_chat_metrics_has_routing_log(self):
        """Verify global singleton has routing_log."""
        cm = get_chat_metrics()
        assert "routing_log" in cm.data
    
    def test_routing_log_shares_global_singleton(self):
        """Verify routing_log shares global singleton (by design).
        
        Note: ChatMetrics uses a process-wide singleton via get_chat_metrics().
        Multiple ChatMetrics() instances share the same underlying data.
        This is intentional for observability across sessions.
        """
        # Get current log size before adding
        cm1 = ChatMetrics()
        initial_size = len(cm1.data["routing_log"])
        
        cm1.record_routing_decision(
            message="Instance 1",
            selected_route="llm",
            candidates=[],
            guards_triggered=[],
            latency_ms=1.0,
        )
        
        # Create new instance - shares same data
        cm2 = ChatMetrics()
        
        # Both instances see the same data (singleton pattern)
        assert len(cm2.data["routing_log"]) == initial_size + 1
        assert cm2.data["routing_log"][-1]["message_preview"] == "Instance 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
