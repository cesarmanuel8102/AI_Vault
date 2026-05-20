"""Tests for Fallback Visibility - FASE 5

Tests for detecting silent degradation and minimal telemetry.
"""

import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tmp_agent"))

from brain_v9.core.routing.fallback_visibility import (
    FallbackVisibility,
    DegradationEvent,
    get_fallback_visibility,
    record_degradation,
    check_system_health,
)


class TestDegradationEvent:
    """Test degradation event data structure."""
    
    def test_can_create_event(self):
        """Should be able to create degradation event."""
        event = DegradationEvent(
            timestamp=time.time(),
            component="metacore",
            severity="critical",
            message="MetaCore is None",
        )
        
        assert event.component == "metacore"
        assert event.severity == "critical"
        assert not event.recovered


class TestFallbackVisibility:
    """Test FallbackVisibility class."""
    
    def test_can_create_instance(self):
        """Should be able to create instance."""
        fb = FallbackVisibility()
        assert fb is not None
    
    def test_records_degradation(self):
        """Should record degradation events."""
        fb = FallbackVisibility()
        
        fb.record_degradation("metacore", "critical", "MetaCore is None")
        
        summary = fb.get_degradation_summary()
        assert summary["critical_count"] == 1
        assert summary["total_events"] == 1
    
    def test_records_recovery(self):
        """Should mark events as recovered."""
        fb = FallbackVisibility()
        
        fb.record_degradation("metacore", "critical", "MetaCore is None")
        fb.record_recovery("metacore")
        
        summary = fb.get_degradation_summary()
        assert summary["critical_count"] == 0  # Recovered
    
    def test_limits_event_count(self):
        """Should limit number of stored events."""
        fb = FallbackVisibility(max_events=5)
        
        for i in range(10):
            fb.record_degradation("test", "info", f"Event {i}")
        
        summary = fb.get_degradation_summary()
        assert summary["total_events"] <= 5
    
    def test_tracks_counters(self):
        """Should track counters by component and severity."""
        fb = FallbackVisibility()
        
        fb.record_degradation("metacore", "critical", "Test")
        fb.record_degradation("metacore", "critical", "Test 2")
        fb.record_degradation("memory", "warning", "Test")
        
        summary = fb.get_degradation_summary()
        assert "counters" in summary
        assert summary["counters"].get("metacore_critical", 0) == 2


class TestHealthStatus:
    """Test health status reporting."""
    
    def test_healthy_when_no_degradations(self):
        """Should report healthy when no degradations."""
        fb = FallbackVisibility()
        
        summary = fb.get_degradation_summary()
        assert summary["health_status"] == "healthy"
    
    def test_warning_status(self):
        """Should report warning when warnings present."""
        fb = FallbackVisibility()
        
        fb.record_degradation("test", "warning", "Test warning")
        
        summary = fb.get_degradation_summary()
        assert summary["health_status"] == "warning"
    
    def test_degraded_status(self):
        """Should report degraded when critical present."""
        fb = FallbackVisibility()
        
        fb.record_degradation("test", "warning", "Test warning")
        fb.record_degradation("test", "critical", "Test critical")
        
        summary = fb.get_degradation_summary()
        assert summary["health_status"] == "degraded"


class TestCommonDegradations:
    """Test detection of common degradation conditions."""
    
    def test_detects_metacore_none(self):
        """Should detect MetaCore=None."""
        fb = FallbackVisibility()
        
        degradations = fb.check_common_degradations(
            metacore=None,
            orchestrator_set=True,
            semantic_memory_available=True,
        )
        
        assert len(degradations) == 1
        assert degradations[0][0] == "metacore"
        assert degradations[0][1] == "critical"
    
    def test_detects_orchestrator_not_set(self):
        """Should detect orchestrator not set."""
        fb = FallbackVisibility()
        
        degradations = fb.check_common_degradations(
            metacore={"ok": True},
            orchestrator_set=False,
            semantic_memory_available=True,
        )
        
        assert any(d[0] == "orchestrator" for d in degradations)
    
    def test_detects_memory_unavailable(self):
        """Should detect semantic memory unavailable."""
        fb = FallbackVisibility()
        
        degradations = fb.check_common_degradations(
            metacore={"ok": True},
            orchestrator_set=True,
            semantic_memory_available=False,
        )
        
        assert any(d[0] == "semantic_memory" for d in degradations)


class TestRateLimiting:
    """Test rate limiting of reports."""
    
    def test_rate_limits_reports(self):
        """Should rate limit report emission."""
        fb = FallbackVisibility()
        
        # First call should report
        assert fb.should_report(min_interval_seconds=1) is True
        
        # Immediate second call should not
        assert fb.should_report(min_interval_seconds=1) is False
        
        # Wait and try again
        time.sleep(0.1)
        assert fb.should_report(min_interval_seconds=0.05) is True


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    def test_get_fallback_visibility_returns_instance(self):
        """Should return singleton instance."""
        fb1 = get_fallback_visibility()
        fb2 = get_fallback_visibility()
        
        assert fb1 is fb2
    
    def test_record_degradation_function(self):
        """Should be able to record via convenience function."""
        record_degradation("test", "warning", "Test message")
        
        fb = get_fallback_visibility()
        summary = fb.get_degradation_summary()
        
        # Should have at least 1 event (might have more from other tests)
        assert summary["total_events"] >= 1
    
    def test_check_system_health(self):
        """Should check system health."""
        result = check_system_health(
            metacore=None,
            orchestrator_set=False,
            semantic_memory_available=False,
        )
        
        assert "health_status" in result
        assert result["critical_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
