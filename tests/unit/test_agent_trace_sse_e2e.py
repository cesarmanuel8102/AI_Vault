"""
VTC-F2 SSE E2E Automated Test — End-to-end trace redaction verification.

Strategy: functional test without server startup.
- Import _emit_agent_trace_internal (bypasses auth) to emit event
- Import _read_trace_events to read back persisted sanitized events
- Also verify SSE queue receives sanitized message
- No tokens, no uvicorn, no FastAPI client needed
"""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

from brain_v9.main import (
    _agent_trace_queues,
    _emit_agent_trace_internal,
    _read_trace_events,
)

ROOM_ID = "vtc_f2_sse_test"
RUN_ID = "sse_redaction_e2e"


class TestTraceSSEEndToEndRedaction:
    """End-to-end test: emit → sanitize → persist / broadcast."""

    @classmethod
    def setup_class(cls):
        """Clean leftover test artifacts before class."""
        root = Path("C:/AI_VAULT/tmp_agent/state/rooms") / ROOM_ID / "agent_runs" / RUN_ID
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    def teardown_method(self):
        """Remove test artifacts after each method."""
        root = Path("C:/AI_VAULT/tmp_agent/state/rooms") / ROOM_ID / "agent_runs" / RUN_ID
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        # Remove queues registered during test
        key = f"{ROOM_ID}::{RUN_ID}"
        if key in _agent_trace_queues:
            del _agent_trace_queues[key]

    def test_emit_and_read_trace_sanitized(self):
        """Emit sensitive event, read back from trace file, verify redaction."""
        _emit_agent_trace_internal(
            room_id=ROOM_ID,
            run_id=RUN_ID,
            type_="tool",
            title="Sensitive event",
            text="Testing password=supersecret123 token=ghp_1234567890abcdef1234567890abcdef1234 path memory/semantic/state.json",
            severity="warning",
            data={
                "chain_of_thought": "raw hidden reasoning should not appear",
                "api_key": "sk-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "password": "supersecret123",
                "detail": "Operational detail with bearer abcdefghijklmnopqrstuvwxyz123456",
                "path2": "tmp_agent/strategies/mean_reversion_eq/config.json",
            },
        )

        events = _read_trace_events(ROOM_ID, RUN_ID, limit=10)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"

        event = events[0]
        serialized = json.dumps(event, ensure_ascii=False)

        # Leak checks
        assert "supersecret123" not in serialized, "password value leaked"
        assert "ghp_" not in serialized, "token prefix leaked"
        assert "sk-" not in serialized, "api_key prefix leaked"
        assert "abcdefghijklmnopqrstuvwxyz123456" not in serialized, "bearer value leaked"
        assert "chain_of_thought" not in serialized, "blocked field leaked as key"
        assert "raw hidden reasoning" not in serialized, "blocked field content leaked"
        assert "memory/semantic" not in serialized, "protected path leaked"
        assert "tmp_agent/strategies" not in serialized, "protected strategy path leaked"

        # Redaction presence
        assert "[REDACTED_SECRET]" in serialized, "REDACTED_SECRET marker absent"
        assert "[REDACTED_PATH]" in serialized, "REDACTED_PATH marker absent"

        # Structural checks
        assert event["room_id"] == ROOM_ID
        assert event["run_id"] == RUN_ID
        assert event["title"] == "Sensitive event"
        assert "data" in event
        assert "chain_of_thought" not in event["data"]  # blocked field removed
        assert "api_key" not in event["data"]  # blocked field removed
        assert "password" not in event["data"]  # blocked field removed

    def test_sse_queue_receives_sanitized_event(self):
        """Verify SSE queue gets sanitized message (no raw secrets)."""
        key = (ROOM_ID, RUN_ID)  # broadcast uses tuple key
        q = asyncio.Queue()
        _agent_trace_queues.setdefault(key, []).append(q)

        _emit_agent_trace_internal(
            room_id=ROOM_ID,
            run_id=RUN_ID,
            type_="tool",
            title="Queue test event",
            text="password=queue_secret123",
            severity="info",
            data={},
        )

        msg = q.get_nowait()
        assert "password=queue_secret123" not in msg, "raw secret leaked into SSE queue"
        assert "[REDACTED_SECRET]" in msg, "REDACTED_SECRET marker absent in SSE message"

        # Clean up queue registration
        if key in _agent_trace_queues and q in _agent_trace_queues[key]:
            _agent_trace_queues[key].remove(q)
            if not _agent_trace_queues[key]:
                del _agent_trace_queues[key]

    def test_emit_safe_event_idempotent(self):
        """Safe events should not be mutated unexpectedly."""
        _emit_agent_trace_internal(
            room_id=ROOM_ID,
            run_id=RUN_ID,
            type_="tool",
            title="Safe event",
            text="This is clean. Operational detail.",
            severity="info",
            data={"tool": "smoke_test", "status": "ok"},
        )

        events = _read_trace_events(ROOM_ID, RUN_ID, limit=10)
        assert len(events) == 1
        event = events[0]
        assert event["text"] == "This is clean. Operational detail."
        assert "[REDACTED_SECRET]" not in event["text"]
        assert "[REDACTED_PATH]" not in event["text"]
        assert event["data"]["tool"] == "smoke_test"
        assert event["data"]["status"] == "ok"
