"""
Integration text tests for VTC-B trace redactor endpoint integration.
These tests verify by file inspection that main.py has been properly patched.
No runtime FastAPI required.
"""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))


MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "main.py")


def _read_main():
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        return f.read()


class TestMainTraceRedactorIntegration:
    def test_main_imports_trace_redactor(self):
        txt = _read_main()
        assert "from brain_v9.tracing.trace_redactor import sanitize_event as _sanitize_event" in txt

    def test_append_trace_event_uses_sanitize_event(self):
        txt = _read_main()
        idx = txt.find("def _append_trace_event(event: dict)")
        assert idx > 0, "_append_trace_event not found"
        block = txt[idx:idx+500]
        assert "_sanitize_event(event)" in block

    def test_broadcast_trace_event_uses_sanitize_event(self):
        txt = _read_main()
        idx = txt.find("def _broadcast_trace_event(room_id: str, run_id: str, event: dict)")
        assert idx > 0, "_broadcast_trace_event not found"
        block = txt[idx:idx+300]
        assert "_sanitize_event(dict(event))" in block

    def test_latest_endpoint_sanitizes_returned_events(self):
        txt = _read_main()
        idx = txt.find("async def brain_agent_trace_latest(")
        assert idx > 0, "brain_agent_trace_latest not found"
        block = txt[idx:idx+300]
        assert "_sanitize_event" in block

    def test_stream_endpoint_exists_unmodified(self):
        txt = _read_main()
        assert "async def brain_agent_trace_stream(" in txt

    def test_no_ui_files_modified_by_vtc_b(self):
        uv = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "ui")
        assert os.path.isdir(uv)
        for f in os.listdir(uv):
            if f.endswith(".html"):
                with open(os.path.join(uv, f), encoding="utf-8") as fh:
                    assert "Modified for trace_redactor" not in fh.read(), f"{f} should not be modified for trace redactor"


class TestTraceRedactorIdempotent:
    def test_idempotent_for_safe_event(self):
        from brain_v9.tracing.trace_redactor import sanitize_event
        event = {"title": "Safe", "type": "test"}
        s1 = sanitize_event(event)
        s2 = sanitize_event(s1.copy())
        assert s1 == s2

    def test_blocked_fields_removed_in_data_field(self):
        from brain_v9.tracing.trace_redactor import sanitize_event
        event = {"type": "thinking", "data": {"chain_of_thought": "secret reasoning"}}
        safe = sanitize_event(event)
        assert "chain_of_thought" not in safe.get("data", {})

    def test_secrets_scrubbed_in_data_field(self):
        from brain_v9.tracing.trace_redactor import sanitize_event
        long_key = "sk-" + "a" * 48
        event = {"type": "tool", "data": {"text": f"Calling API with key={long_key}"}}
        safe = sanitize_event(event)
        assert "[REDACTED_SECRET]" in safe["data"]["text"]
        assert long_key not in safe["data"]["text"]
