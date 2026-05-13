"""R4.1: Lightweight global counters for R3/R3.1/R4 quality validators.

Both core.session and agent.loop import this so they can record validator
firings without circular dependencies. Counters merge into ChatMetrics
snapshot for visibility via /metrics or get_chat_metrics tool.
"""
from __future__ import annotations
from threading import Lock
from typing import Dict

_LOCK = Lock()
_COUNTERS: Dict[str, int] = {}


def record(name: str, count: int = 1) -> None:
    """Increment a named validator counter (thread-safe)."""
    if not name:
        return
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + int(count)


def snapshot() -> Dict[str, int]:
    """Return a copy of current counter state."""
    with _LOCK:
        return dict(_COUNTERS)


def reset() -> None:
    """Reset all counters (testing only)."""
    with _LOCK:
        _COUNTERS.clear()
