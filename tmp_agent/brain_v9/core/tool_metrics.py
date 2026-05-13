"""R14: Per-tool coverage observability.

Tracks invocations, schema violations, errors (by type), truncations and
duration for every registered tool. Exposed via GET /tools/coverage so the
operator can spot tools that fail/truncate often and prioritize fixes.

Thread-safe; zero deps.
"""
from __future__ import annotations
from threading import Lock
from time import time
from typing import Any, Dict, Optional


class ToolStats:
    """Mutable per-tool stats container. Access only under _LOCK."""

    __slots__ = (
        "invocations",
        "successes",
        "failures",
        "schema_violations",
        "truncations",
        "vendored_skips",
        "total_duration_ms",
        "max_duration_ms",
        "error_types",
        "last_error",
        "last_invoked_ts",
    )

    def __init__(self) -> None:
        self.invocations = 0
        self.successes = 0
        self.failures = 0
        self.schema_violations = 0
        self.truncations = 0
        self.vendored_skips = 0
        self.total_duration_ms = 0.0
        self.max_duration_ms = 0.0
        self.error_types: Dict[str, int] = {}
        self.last_error: Optional[str] = None
        self.last_invoked_ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        avg_ms = (self.total_duration_ms / self.invocations) if self.invocations else 0.0
        success_rate = (self.successes / self.invocations) if self.invocations else None
        return {
            "invocations": self.invocations,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(success_rate, 4) if success_rate is not None else None,
            "schema_violations": self.schema_violations,
            "truncations": self.truncations,
            "vendored_skips": self.vendored_skips,
            "avg_duration_ms": round(avg_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "error_types": dict(self.error_types),
            "last_error": self.last_error,
            "last_invoked_ts": self.last_invoked_ts,
        }


_LOCK = Lock()
_STATS: Dict[str, ToolStats] = {}


def _get(name: str) -> ToolStats:
    s = _STATS.get(name)
    if s is None:
        s = ToolStats()
        _STATS[name] = s
    return s


def record_schema_violation(tool: str) -> None:
    """Tool was rejected at the schema gate before invocation."""
    if not tool:
        return
    with _LOCK:
        s = _get(tool)
        s.invocations += 1
        s.failures += 1
        s.schema_violations += 1
        s.error_types["missing_args"] = s.error_types.get("missing_args", 0) + 1
        s.last_error = "schema_violation"
        s.last_invoked_ts = time()


def record_invocation(
    tool: str,
    duration_ms: float,
    *,
    success: bool,
    error_type: Optional[str] = None,
    truncated: bool = False,
    vendored_skipped: int = 0,
    error_message: Optional[str] = None,
) -> None:
    """Tool actually ran (post-schema-gate). Capture outcome metrics."""
    if not tool:
        return
    with _LOCK:
        s = _get(tool)
        s.invocations += 1
        s.total_duration_ms += duration_ms
        if duration_ms > s.max_duration_ms:
            s.max_duration_ms = duration_ms
        s.last_invoked_ts = time()
        if success:
            s.successes += 1
        else:
            s.failures += 1
            etype = error_type or "unknown"
            s.error_types[etype] = s.error_types.get(etype, 0) + 1
            if error_message:
                s.last_error = error_message[:200]
        if truncated:
            s.truncations += 1
        if vendored_skipped:
            s.vendored_skips += vendored_skipped


def snapshot() -> Dict[str, Any]:
    """Return a deep copy of all per-tool stats plus aggregates."""
    with _LOCK:
        per_tool = {name: s.to_dict() for name, s in _STATS.items()}
    total_invocations = sum(t["invocations"] for t in per_tool.values())
    total_failures = sum(t["failures"] for t in per_tool.values())
    total_schema = sum(t["schema_violations"] for t in per_tool.values())
    total_trunc = sum(t["truncations"] for t in per_tool.values())
    # Top problematic tools (by failure count, then schema_violations)
    ranked = sorted(
        per_tool.items(),
        key=lambda kv: (kv[1]["failures"], kv[1]["schema_violations"]),
        reverse=True,
    )
    top_failing = [
        {"tool": name, **stats}
        for name, stats in ranked[:5]
        if stats["failures"] > 0
    ]
    return {
        "tools": per_tool,
        "totals": {
            "invocations": total_invocations,
            "failures": total_failures,
            "schema_violations": total_schema,
            "truncations": total_trunc,
            "registered_tools": len(per_tool),
            "tools_ever_failed": sum(1 for t in per_tool.values() if t["failures"] > 0),
        },
        "top_failing": top_failing,
    }


def reset() -> None:
    """Test helper."""
    with _LOCK:
        _STATS.clear()
