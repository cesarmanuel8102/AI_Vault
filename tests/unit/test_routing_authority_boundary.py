"""Tests for Routing Authority Boundary Guards.

Tests for FASE 1: Routing Authority Stabilization.
Covers conflict detection, authority tracing, and fallback markers.
"""

import pytest
from typing import Dict, Tuple

import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tmp_agent" / "brain_v9" / "core" / "routing"))

from guards import (
    detect_routing_authority_conflict,
    get_route_confidence,
    build_authority_trace,
    get_fallback_marker,
    V9_ROUTING_MARKERS,
    BRAINSESSION_ROUTING_MARKERS,
)


class TestRoutingAuthorityConflict:
    """Test detection of routing authority conflicts."""

    def test_detects_no_tool_override_conflict(self):
        """Test detection when V9.1 says 'agent_task' but BrainSession says 'llm'."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="agent_task",
            brainsession_route="llm",
            v9_confidence=0.8,
            brainsession_confidence=0.9,
        )
        
        assert conflict is True
        assert winner == "BrainSession"
        assert "no_tool_preference" in reason

    def test_detects_explicit_target_conflict(self):
        """Test detection when V9.1 says 'general_conversation' but BrainSession says 'agent'."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="general_conversation",
            brainsession_route="agent",
            v9_confidence=0.7,
            brainsession_confidence=0.85,
        )
        
        assert conflict is True
        assert winner == "BrainSession"
        assert "explicit_tool_target" in reason

    def test_detects_fastpath_dashboard_conflict(self):
        """Test detection when V9.1 says 'dashboard_analysis' but BrainSession says 'fastpath'."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="dashboard_analysis",
            brainsession_route="fastpath",
            v9_confidence=0.75,
            brainsession_confidence=0.9,
        )
        
        assert conflict is True
        assert winner == "BrainSession"
        assert "fastpath_has_real_data" in reason

    def test_detects_informational_learning_conflict(self):
        """Test detection when V9.1 says 'learning_request' but BrainSession says 'llm'."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="learning_request",
            brainsession_route="llm",
            v9_confidence=0.6,
            brainsession_confidence=0.8,
        )
        
        assert conflict is True
        assert winner == "BrainSession"
        assert "informational_not_operational" in reason

    def test_v9_wins_high_confidence_agent(self):
        """Test that V9.1 wins when it has high confidence operational request."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="agent_task",
            brainsession_route="llm",
            v9_confidence=0.95,
            brainsession_confidence=0.6,
        )
        
        assert conflict is True
        assert winner == "V9.1"
        assert "high_confidence" in reason

    def test_no_conflict_when_aligned(self):
        """Test that no conflict is detected when routes align."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="agent_task",
            brainsession_route="agent",
            v9_confidence=0.8,
            brainsession_confidence=0.85,
        )
        
        assert conflict is False
        assert winner == "none"
        assert "aligned" in reason

    def test_no_conflict_with_empty_data(self):
        """Test that no conflict is detected with insufficient data."""
        conflict, winner, reason = detect_routing_authority_conflict(
            v9_category="",
            brainsession_route="agent",
            v9_confidence=0.0,
            brainsession_confidence=0.8,
        )
        
        assert conflict is False
        assert "insufficient_data" in reason

    def test_case_insensitive_matching(self):
        """Test that category matching is case insensitive."""
        conflict, winner, _ = detect_routing_authority_conflict(
            v9_category="AGENT_TASK",
            brainsession_route="LLM",
            v9_confidence=0.8,
            brainsession_confidence=0.9,
        )
        
        assert conflict is True
        assert winner == "BrainSession"


class TestRouteConfidence:
    """Test confidence calculation for routing decisions."""

    def test_base_confidence_with_no_data(self):
        """Test base confidence with no supporting data."""
        confidence, source = get_route_confidence()
        
        assert 0.4 <= confidence <= 0.6  # Should be near base 0.5
        assert source == "default"

    def test_confidence_boost_for_patterns(self):
        """Test confidence increases with pattern matches."""
        confidence1, _ = get_route_confidence(
            intent="ANALYSIS",
            matched_patterns=1,
            total_patterns=10,
        )
        
        confidence2, _ = get_route_confidence(
            intent="ANALYSIS",
            matched_patterns=5,
            total_patterns=10,
        )
        
        assert confidence2 > confidence1

    def test_confidence_boost_for_explicit_target(self):
        """Test confidence increases with explicit tool target."""
        confidence_with, _ = get_route_confidence(
            has_explicit_target=True,
        )
        
        confidence_without, _ = get_route_confidence(
            has_explicit_target=False,
        )
        
        assert confidence_with > confidence_without
        assert confidence_with - confidence_without >= 0.1

    def test_confidence_adjustment_for_verification(self):
        """Test confidence adjustment for verification priority."""
        conf_high, _ = get_route_confidence(verification_priority=3)
        conf_none, _ = get_route_confidence(verification_priority=0)
        
        assert conf_high > conf_none

    def test_confidence_source_strong_intent(self):
        """Test confidence source when strong intent + target detected."""
        _, source = get_route_confidence(
            matched_patterns=3,
            total_patterns=5,
            has_explicit_target=True,
        )
        
        assert "strong_intent" in source

    def test_confidence_source_explicit_only(self):
        """Test confidence source when only explicit target present."""
        _, source = get_route_confidence(
            has_explicit_target=True,
        )
        
        assert source == "explicit_target_only"


class TestAuthorityTrace:
    """Test authority trace building."""

    def test_builds_complete_trace(self):
        """Test that complete authority trace is built."""
        trace = build_authority_trace(
            v9_category="agent_task",
            v9_confidence=0.8,
            brainsession_route="llm",
            brainsession_confidence=0.9,
            conflict_detected=True,
            winner="BrainSession",
            reason="user_no_tool_preference_overrides_agent",
            fallback_marker="authority_conflict_resolved|verification_degraded_fastpath",
        )
        
        assert "v9_router" in trace
        assert "brainsession_router" in trace
        assert "conflict_resolution" in trace
        assert "fallback_marker" in trace
        assert "semantic_origin" in trace
        
        assert trace["v9_router"]["category"] == "agent_task"
        assert trace["v9_router"]["advisory"] is True
        assert trace["brainsession_router"]["operational"] is True
        assert trace["conflict_resolution"]["detected"] is True
        assert trace["conflict_resolution"]["winner"] == "BrainSession"
        assert "timestamp" in trace["conflict_resolution"]

    def test_trace_no_conflict(self):
        """Test trace when no conflict detected."""
        trace = build_authority_trace(
            v9_category="agent_task",
            v9_confidence=0.8,
            brainsession_route="agent",
            brainsession_confidence=0.85,
            conflict_detected=False,
            winner="",
            reason="",
        )
        
        assert trace["conflict_resolution"]["winner"] == "none"
        assert trace["conflict_resolution"]["reason"] == "no_conflict"

    def test_trace_with_empty_fallback(self):
        """Test trace handles empty fallback marker."""
        trace = build_authority_trace(fallback_marker="")
        
        assert trace["fallback_marker"] == "none"


class TestFallbackMarker:
    """Test fallback marker generation."""

    def test_marker_for_fastpath(self):
        """Test marker when fastpath is used."""
        marker = get_fallback_marker(fastpath_used=True)
        
        assert "fastpath" in marker

    def test_marker_for_agent(self):
        """Test marker when agent is used."""
        marker = get_fallback_marker(agent_used=True)
        
        assert "agent_orchestration" in marker

    def test_marker_for_llm(self):
        """Test marker when LLM is used."""
        marker = get_fallback_marker(llm_used=True)
        
        assert "llm_direct" in marker

    def test_marker_for_conflict(self):
        """Test marker includes conflict info."""
        marker = get_fallback_marker(
            conflict_detected=True,
            fastpath_used=True,
        )
        
        assert "authority_conflict_resolved" in marker
        assert "fastpath" in marker

    def test_marker_for_verification_degradation(self):
        """Test marker includes verification degradation."""
        marker = get_fallback_marker(
            verification_required=True,
            verification_priority=3,
            fastpath_used=True,
        )
        
        assert "verification_degraded_fastpath" in marker

    def test_marker_multiple_conditions(self):
        """Test marker combines multiple conditions."""
        marker = get_fallback_marker(
            verification_required=True,
            verification_priority=2,
            conflict_detected=True,
            agent_used=True,
        )
        
        assert "authority_conflict_resolved" in marker
        assert "verification_bypassed_template" in marker
        assert "agent_orchestration" in marker

    def test_marker_no_conditions(self):
        """Test marker when no conditions provided."""
        marker = get_fallback_marker()
        
        assert marker == "no_route"


class TestRoutingMarkers:
    """Test that routing marker constants are defined."""

    def test_v9_markers_defined(self):
        """Test V9 routing markers are defined."""
        assert "self_awareness" in V9_ROUTING_MARKERS
        assert "dashboard_analysis" in V9_ROUTING_MARKERS
        assert "agent_task" in V9_ROUTING_MARKERS

    def test_brainsession_markers_defined(self):
        """Test BrainSession routing markers are defined."""
        assert "fastpath" in BRAINSESSION_ROUTING_MARKERS
        assert "agent" in BRAINSESSION_ROUTING_MARKERS
        assert "llm" in BRAINSESSION_ROUTING_MARKERS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
