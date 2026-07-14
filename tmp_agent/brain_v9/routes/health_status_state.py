"""Pure state adapter for health/status endpoint payloads.

B7-STRANGLER-13B: Isolates the payload construction logic for
/health and /status so the endpoints can later be moved to
health_status.py without carrying main.py global dependencies.

This module is intentionally framework-free:
  - No web framework, no router decorator.
  - No main.py / session.py / dash / trade imports.
  - No process spawning, no HTTP clients, no server startup.
  - Only pure functions receiving state as arguments.

Payload shapes are copied verbatim from main.py as of commit 694a62d.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_health_response(
    *,
    startup_done: bool,
    startup_error: Optional[str],
    active_sessions_count: int,
    safe_mode: bool,
) -> Dict[str, Any]:
    """Build the /health payload + status code.

    Returns a dict with keys:
      - content: the response body dict
      - status_code: HTTP status code (503 or 200)

    Three branches matching main.py exactly:
      1. startup_error set → 503 startup_failed
      2. not startup_done → 503 initializing
      3. healthy → 200
    """
    if startup_error:
        return {
            "content": {
                "status": "startup_failed",
                "error": startup_error,
                "hint": "Revisa los logs",
            },
            "status_code": 503,
        }
    if not startup_done:
        return {
            "content": {
                "status": "initializing",
                "sessions": active_sessions_count,
            },
            "status_code": 503,
        }
    return {
        "content": {
            "status": "healthy",
            "sessions": active_sessions_count,
            "version": "9.0.0",
            "safe_mode": safe_mode,
        },
        "status_code": 200,
    }


def build_health_payload(
    *,
    startup_done: bool,
    startup_error: Optional[str],
    active_sessions_count: int,
    safe_mode: bool,
) -> Dict[str, Any]:
    """Build the /health response body dict (without status code wrapper).

    Caller is responsible for applying the status code if needed.
    For the common case where the endpoint returns the dict directly,
    this returns just the body.
    """
    resp = build_health_response(
        startup_done=startup_done,
        startup_error=startup_error,
        active_sessions_count=active_sessions_count,
        safe_mode=safe_mode,
    )
    return resp["content"]


def build_status_payload(
    *,
    active_session_keys: List[str],
    startup_done: bool,
    safe_mode: bool,
) -> Dict[str, Any]:
    """Build the /status payload.

    Matches main.py exactly:
      - sessions: list of session keys
      - ready: startup_done
      - version: "9.0.0"
      - safe_mode: safe_mode
    """
    return {
        "sessions": active_session_keys,
        "ready": startup_done,
        "version": "9.0.0",
        "safe_mode": safe_mode,
    }