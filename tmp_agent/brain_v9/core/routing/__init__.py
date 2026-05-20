"""Routing submodule for BrainSession.

This module provides semantic guards and heuristics for routing decisions.
Extracted from session.py as part of architectural hardening.

Available exports:
- prefers_no_tool_analysis: Check if user wants analysis without tools
- has_explicit_tool_target: Check if user named a specific target
- is_confirmation: Detect confirmation phrases
- is_code_change_request: Detect file modification requests
- is_tool_confirmation_request_response: Detect tool confirmation requests
- should_route_to_llm_instead_of_agent: Composite routing decision
- requires_grounded_verification: Detect grounded verification needs
- get_verification_priority: Get verification priority level
- should_degrade_fastpath: Check if fastpath should be bypassed
- detect_routing_authority_conflict: Detect V9.1 vs BrainSession conflicts
- get_route_confidence: Calculate routing confidence with explanation
- build_authority_trace: Build complete routing authority trace
- get_fallback_marker: Generate fallback marker for traceability
- Constants: NO_TOOL_MARKERS, CODE_ANALYSIS_PATH_RE, etc.

Usage:
    from tmp_agent.brain_v9.core.routing import guards
    
    if guards.prefers_no_tool_analysis(message):
        route = "llm"
    
    # Check for routing conflicts
    conflict, winner, reason = guards.detect_routing_authority_conflict(
        v9_category="agent_task",
        brainsession_route="llm",
        v9_confidence=0.8,
        brainsession_confidence=0.9,
    )

Notes:
    - All functions are pure (no side effects)
    - No dependencies on BrainSession state
    - Testable independently
    - Reusable across routing layers
"""

from .guards import (
    NO_TOOL_MARKERS,
    CODE_ANALYSIS_PATH_RE,
    TOOL_TARGET_PATTERNS,
    TOOL_TARGET_TOKENS,
    GROUNDED_VERIFICATION_MARKERS,
    REJECTS_TEMPLATE_MARKERS,
    V9_ROUTING_MARKERS,
    BRAINSESSION_ROUTING_MARKERS,
    prefers_no_tool_analysis,
    has_explicit_tool_target,
    is_confirmation,
    is_code_change_request,
    is_tool_confirmation_request_response,
    should_route_to_llm_instead_of_agent,
    requires_grounded_verification,
    get_verification_priority,
    should_degrade_fastpath,
    detect_routing_authority_conflict,
    get_route_confidence,
    build_authority_trace,
    get_fallback_marker,
)

__all__ = [
    "NO_TOOL_MARKERS",
    "CODE_ANALYSIS_PATH_RE",
    "TOOL_TARGET_PATTERNS",
    "TOOL_TARGET_TOKENS",
    "GROUNDED_VERIFICATION_MARKERS",
    "REJECTS_TEMPLATE_MARKERS",
    "V9_ROUTING_MARKERS",
    "BRAINSESSION_ROUTING_MARKERS",
    "prefers_no_tool_analysis",
    "has_explicit_tool_target",
    "is_confirmation",
    "is_code_change_request",
    "is_tool_confirmation_request_response",
    "should_route_to_llm_instead_of_agent",
    "requires_grounded_verification",
    "get_verification_priority",
    "should_degrade_fastpath",
    "detect_routing_authority_conflict",
    "get_route_confidence",
    "build_authority_trace",
    "get_fallback_marker",
]
