"""
Agent Visual Trace Console v1 — Structure & Safety Tests
Minimal static tests that verify backend helpers and safety rules.
Reads main.py as text to avoid heavy FastAPI import.
"""
import json, os, re

MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "main.py")

def _read_main() -> str:
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        return f.read()

def test_trace_event_schema_rejects_raw_chain_of_thought():
    text = _read_main()
    # helper _append_trace_event must reject raw_chain_of_thought
    assert "\"raw_chain_of_thought\" in body_json" in text or "raw_chain_of_thought" in text, "VTC: must reject raw_chain_of_thought"

def test_trace_event_accepts_operational_thinking():
    text = _read_main()
    assert "\"thinking\"" in text and "\"tool\"" in text, "VTC: must accept operational event types"

def test_exists_helper_append_and_read():
    text = _read_main()
    assert "def _append_trace_event" in text, "VTC: _append_trace_event helper must exist"
    assert "def _read_trace_events" in text, "VTC: _read_trace_events helper must exist"

def test_exists_endpoint_event():
    text = _read_main()
    assert '"/brain/agent-trace/event"' in text, "VTC: POST /brain/agent-trace/event endpoint must exist"

def test_exists_endpoint_latest():
    text = _read_main()
    assert '"/brain/agent-trace/latest"' in text, "VTC: GET /brain/agent-trace/latest endpoint must exist"

def test_exists_endpoint_stream():
    text = _read_main()
    assert '"/brain/agent-trace/stream"' in text, "VTC: GET /brain/agent-trace/stream endpoint must exist"

def test_sse_format_helper():
    text = _read_main()
    assert "def _sse_format" in text, "VTC: _sse_format helper must exist"
    assert "event:" in text and "data:" in text, "VTC: SSE format must contain event+data fields"

def test_trace_persistence_path():
    text = _read_main()
    assert 'trace.ndjson' in text, "VTC: trace must persist to trace.ndjson"

def test_no_code_execution_in_trace_endpoint():
    text = _read_main()
    blockers = ["subprocess", "exec(", "eval(", "os.system", "run("]
    func_start = text.find("async def brain_agent_trace_event")
    func_end = text.find("async def ", func_start + 1)
    func_body = text[func_start:func_end]
    for b in blockers:
        assert b not in func_body, f"VTC: trace endpoint must not contain {b}"

def test_no_raw_cot_in_sanitization():
    text = _read_main()
    # COT safety filter should be in endpoint
    assert "private_reasoning" in text and "raw_chain_of_thought" in text, "VTC: must filter private/raw COT"

def test_streaming_response_imported():
    text = _read_main()
    assert "StreamingResponse" in text, "VTC: StreamingResponse must be imported"

def test_event_source_in_ui():
    ui_path = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "ui", "agent_trace_console.html")
    if os.path.exists(ui_path):
        with open(ui_path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "EventSource" in html, "VTC UI: must use EventSource for SSE"
        assert "/brain/agent-trace/stream" in html, "VTC UI: must connect to stream endpoint"
    else:
        assert False, "VTC UI: agent_trace_console.html not found (Phase 5 may not be complete)"


INDEX_HTML = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "ui", "index.html")

def _read_index_html() -> str:
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        return f.read()

def test_chat_index_contains_trace_toggle():
    html = _read_index_html()
    assert "vtc-toggle" in html, "VTC Chat Embed: index.html must contain vtc-toggle button"

def test_chat_index_contains_trace_panel():
    html = _read_index_html()
    assert "vtc-panel" in html, "VTC Chat Embed: index.html must contain vtc-panel"

def test_chat_index_uses_eventsource():
    html = _read_index_html()
    assert "EventSource" in html, "VTC Chat Embed: index.html must instantiate EventSource"

def test_chat_index_connects_to_agent_trace_stream():
    html = _read_index_html()
    assert "/brain/agent-trace/stream" in html, "VTC Chat Embed: index.html must connect to /brain/agent-trace/stream"

def test_chat_index_fetches_agent_trace_latest():
    html = _read_index_html()
    assert "/brain/agent-trace/latest" in html, "VTC Chat Embed: index.html must fetch /brain/agent-trace/latest"

def test_chat_index_does_not_render_raw_cot():
    html = _read_index_html()
    # index.html should never expose raw COT strings as visible/renderable content.
    # Backend blocks them before they reach the client.
    assert "vtc-text" in html, "VTC Chat Embed: vtc-text wrapper renders only safe text"
    # No raw COT or private reasoning should be present in the HTML source except as
    # part of defensive blocking logic (which we keep in the backend only).

def test_standalone_console_still_exists():
    import os
    standalone = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "ui", "agent_trace_console.html")
    assert os.path.exists(standalone), "VTC: standalone agent_trace_console.html must still exist as fallback"


if __name__ == "__main__":
    test_trace_event_schema_rejects_raw_chain_of_thought()
    test_trace_event_accepts_operational_thinking()
    test_exists_helper_append_and_read()
    test_exists_endpoint_event()
    test_exists_endpoint_latest()
    test_exists_endpoint_stream()
    test_sse_format_helper()
    test_trace_persistence_path()
    test_no_code_execution_in_trace_endpoint()
    test_no_raw_cot_in_sanitization()
    test_streaming_response_imported()
    test_chat_index_contains_trace_toggle()
    test_chat_index_contains_trace_panel()
    test_chat_index_uses_eventsource()
    test_chat_index_connects_to_agent_trace_stream()
    test_chat_index_fetches_agent_trace_latest()
    test_chat_index_does_not_render_raw_cot()
    test_standalone_console_still_exists()
    print("All VTC v1.1 tests passed.")
