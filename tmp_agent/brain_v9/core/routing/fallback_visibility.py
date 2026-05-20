"""Fallback Visibility Module

FASE 5: Detect silent degradation and provide minimal telemetry.
NO spam logs - only meaningful degradation signals.

NOTE: This module exists as INFRASTRUCTURE for future integration.
The FallbackVisibility class and its methods provide the capability
to track degradation events, but they are NOT yet wired into the
main chat() flow or other degradation points in the system.

To integrate: call record_degradation() from points where silent
degradation is detected (e.g., MetaCore=None, orchestrator not set,
semantic memory unavailable, etc.).
"""

import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

log = logging.getLogger("fallback_visibility")


@dataclass
class DegradationEvent:
    """Record of a degradation event."""
    timestamp: float
    component: str
    severity: str  # "critical", "warning", "info"
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    recovered: bool = False


class FallbackVisibility:
    """Minimal visibility into silent degradation.
    
    Tracks:
    - MetaCore=None
    - Orchestrator not set
    - Semantic memory unavailable
    - Routing conflicts
    - Verification failures
    - Ghost completions
    
    No spam logs - only meaningful signals.
    """
    
    def __init__(self, max_events: int = 100):
        self.max_events = max_events
        self._events: List[DegradationEvent] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._last_report_time: float = 0
    
    def record_degradation(
        self,
        component: str,
        severity: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a degradation event.
        
        Args:
            component: Component that degraded (e.g., "metacore", "semantic_memory")
            severity: "critical", "warning", "info"
            message: Description of degradation
            context: Additional context
        """
        event = DegradationEvent(
            timestamp=time.time(),
            component=component,
            severity=severity,
            message=message,
            context=context or {},
        )
        
        self._events.append(event)
        self._counters[f"{component}_{severity}"] += 1
        
        # Keep only recent events
        if len(self._events) > self.max_events:
            self._events.pop(0)
        
        # Log only critical and warning
        if severity in ("critical", "warning"):
            log.warning(f"[{severity.upper()}] {component}: {message}")
    
    def record_recovery(self, component: str) -> None:
        """Mark component as recovered."""
        for event in reversed(self._events):
            if event.component == component and not event.recovered:
                event.recovered = True
                break
    
    def get_degradation_summary(self) -> Dict[str, Any]:
        """Get summary of degradation state.
        
        Returns:
            Dict with counts, recent events, and health status
        """
        now = time.time()
        
        # Count unrecovered events by severity
        critical_count = sum(
            1 for e in self._events
            if e.severity == "critical" and not e.recovered
        )
        warning_count = sum(
            1 for e in self._events
            if e.severity == "warning" and not e.recovered
        )
        
        # Recent events (last hour)
        recent_events = [
            e for e in self._events
            if now - e.timestamp < 3600
        ]
        
        return {
            "health_status": "degraded" if critical_count > 0 else "warning" if warning_count > 0 else "healthy",
            "critical_count": critical_count,
            "warning_count": warning_count,
            "total_events": len(self._events),
            "counters": dict(self._counters),
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "component": e.component,
                    "severity": e.severity,
                    "message": e.message,
                    "recovered": e.recovered,
                }
                for e in recent_events[-10:]  # Last 10 recent
            ],
        }
    
    def should_report(self, min_interval_seconds: float = 300) -> bool:
        """Check if should emit report (to avoid spam).
        
        Args:
            min_interval_seconds: Minimum seconds between reports
            
        Returns:
            True if enough time has passed
        """
        now = time.time()
        if now - self._last_report_time >= min_interval_seconds:
            self._last_report_time = now
            return True
        return False
    
    def check_common_degradations(
        self,
        metacore: Any = None,
        orchestrator_set: bool = False,
        semantic_memory_available: bool = False,
    ) -> List[Tuple[str, str, str]]:
        """Check common degradation conditions.
        
        Returns:
            List of (component, severity, message) tuples
        """
        degradations = []
        
        if metacore is None:
            degradations.append(("metacore", "critical", "MetaCore is None"))
        
        if not orchestrator_set:
            degradations.append(("orchestrator", "warning", "Orchestrator not set"))
        
        if not semantic_memory_available:
            degradations.append(("semantic_memory", "warning", "Semantic memory unavailable"))
        
        return degradations
    
    def emit_if_needed(self) -> Optional[Dict[str, Any]]:
        """Emit degradation report if conditions warrant.
        
        Returns:
            Report dict if emitted, None otherwise
        """
        if not self.should_report():
            return None
        
        summary = self.get_degradation_summary()
        
        # Only emit if there are actual issues
        if summary["health_status"] == "healthy":
            return None
        
        log.info(f"Degradation report: {summary['critical_count']} critical, {summary['warning_count']} warnings")
        
        return summary


# Global instance for system-wide use
_fallback_visibility: Optional[FallbackVisibility] = None


def get_fallback_visibility() -> FallbackVisibility:
    """Get global fallback visibility instance."""
    global _fallback_visibility
    if _fallback_visibility is None:
        _fallback_visibility = FallbackVisibility()
    return _fallback_visibility


def record_degradation(
    component: str,
    severity: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Convenience function to record degradation."""
    get_fallback_visibility().record_degradation(component, severity, message, context)


def check_system_health(
    metacore: Any = None,
    orchestrator_set: bool = False,
    semantic_memory_available: bool = False,
) -> Dict[str, Any]:
    """Check system health and record degradations.
    
    Returns:
        Health status dict
    """
    fb = get_fallback_visibility()
    
    degradations = fb.check_common_degradations(
        metacore=metacore,
        orchestrator_set=orchestrator_set,
        semantic_memory_available=semantic_memory_available,
    )
    
    for component, severity, message in degradations:
        fb.record_degradation(component, severity, message)
    
    return fb.get_degradation_summary()
