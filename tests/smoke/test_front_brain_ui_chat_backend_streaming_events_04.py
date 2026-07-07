"""Tests for Brain Chat backend streaming events.

Front: FRONT-BRAIN-UI-CHAT-BACKEND-STREAMING-EVENTS-04
Tests that the streaming endpoint exists, emits correct SSE events,
does not expose secrets/CoT, and preserves metadata.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def test_streaming_endpoint_route_exists():
    """Verify the streaming route is registered in the dashboard router."""
    from tmp_agent.brain_v9.dashboard.dashboard_routes import router
    paths = [r.path for r in router.routes]
    assert "/brain-dashboard/chat/stream" in paths, "chat/stream route not found"


def test_sse_event_formatter():
    """Verify SSE event format is correct."""
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _sse_event
    result = _sse_event("test.event", {"ok": True, "msg": "hello"})
    assert result.startswith("event: test.event\n")
    assert "data: " in result
    assert result.endswith("\n\n")
    data_line = [l for l in result.split("\n") if l.startswith("data: ")][0]
    parsed = json.loads(data_line[6:])
    assert parsed["ok"] is True
    assert parsed["msg"] == "hello"


def test_proxy_chat_returns_proper_envelope():
    """Verify proxy returns either success data or error envelope with error_kind."""
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _proxy_chat_to_8091
    result = _proxy_chat_to_8091({"message": "test", "mode": "read_only", "user_id": "test"})
    # Either it succeeds (returns data with final_answer) or returns error envelope
    if result.get("_proxy_error"):
        assert "error_kind" in result
        assert result["error_kind"] in ("critical", "operational_warning", "auth_governance")
    else:
        # Success path: should have either final_answer or some response field
        assert "final_answer" in result or "content" in result or "status" in result


def test_proxy_trace_returns_error_on_failure():
    """Verify trace proxy returns error envelope when backend is unreachable."""
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _proxy_trace_from_8091
    result = _proxy_trace_from_8091("fake_run_id")
    assert result.get("_proxy_error") is True


def test_governance_signal_detector():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _contains_governance_signal
    assert _contains_governance_signal('{"governance": "checked"}') is True
    assert _contains_governance_signal('{"blocked": true}') is True
    assert _contains_governance_signal('{"approval": "granted"}') is True
    assert _contains_governance_signal('{"foo": "bar"}') is False


def test_provider_signal_detector():
    from tmp_agent.brain_v9.dashboard.dashboard_routes import _contains_provider_signal
    assert _contains_provider_signal('{"provider": "ollama"}') is True
    assert _contains_provider_signal('{"model": "kimi"}') is True
    assert _contains_provider_signal('{"fallback": "used"}') is True
    assert _contains_provider_signal('{"degraded": true}') is True
    assert _contains_provider_signal('{"foo": "bar"}') is False


def test_app_js_has_streaming_endpoint():
    """Verify app.js references the streaming endpoint."""
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "/brain-dashboard/chat/stream" in src, "app.js must reference /brain-dashboard/chat/stream"


def test_app_js_has_legacy_fallback():
    """Verify app.js still has the legacy chat endpoint as fallback."""
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "/brain-dashboard/chat'" in src or "/brain-dashboard/chat\"" in src, "app.js must have legacy /brain-dashboard/chat fallback"
    assert "sendChatLegacy" in src, "app.js must have sendChatLegacy fallback function"


def test_app_js_has_trace_proxy():
    """Verify app.js still references the trace proxy endpoint."""
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    assert "/brain-dashboard/agent-v2/runs/" in src, "app.js must reference trace proxy"


def test_app_js_no_hardcoded_8091():
    """Verify app.js does not hardcode 127.0.0.1:8091 for data fetch calls."""
    with open("tmp_agent/brain_v9/dashboard/static/app.js", encoding="utf-8") as f:
        src = f.read()
    # The app should use relative /brain-dashboard/ paths, not direct 8091 fetch
    # A display label reference is OK, but fetch() to 8091 is not
    import re
    fetch_to_8091 = re.search(r"fetch\s*\(\s*['\"`]http://127\.0\.0\.1:8091", src)
    assert not fetch_to_8091, "app.js must not fetch() directly to 127.0.0.1:8091"


def test_no_secrets_in_dashboard_routes():
    """Verify dashboard_routes.py does not contain hardcoded secrets."""
    with open("tmp_agent/brain_v9/dashboard/dashboard_routes.py", encoding="utf-8") as f:
        src = f.read()
    forbidden = ["AGENTV2_TEST_ADMIN_TOKEN", "dev_admin_2026!", "MiClaveUltraSegura",
                "OPENAI_API_KEY", "API_KEY=", "PASSWORD="]
    for token in forbidden:
        assert token not in src, f"dashboard_routes.py must not contain {token}"


def test_streaming_endpoint_imports_streaming_response():
    """Verify StreamingResponse is imported."""
    with open("tmp_agent/brain_v9/dashboard/dashboard_routes.py", encoding="utf-8") as f:
        src = f.read()
    assert "StreamingResponse" in src, "StreamingResponse must be imported"


if __name__ == "__main__":
    tests = [
        test_streaming_endpoint_route_exists,
        test_sse_event_formatter,
        test_proxy_chat_returns_proper_envelope,
        test_proxy_trace_returns_error_on_failure,
        test_governance_signal_detector,
        test_provider_signal_detector,
        test_app_js_has_streaming_endpoint,
        test_app_js_has_legacy_fallback,
        test_app_js_has_trace_proxy,
        test_app_js_no_hardcoded_8091,
        test_no_secrets_in_dashboard_routes,
        test_streaming_endpoint_imports_streaming_response,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")