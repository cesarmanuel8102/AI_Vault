"""Tests for session_fmt_helpers pure formatters.

Front: FRONT-B7-SESSION-STRANGLER-FORMATTERS-01A
Verifies that extracted formatters produce correct output without BrainSession.
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.session_fmt_helpers import (
    format_action_value,
    fmt_check_port,
    fmt_check_http_service,
    fmt_check_all_services,
    fmt_check_service_status,
    fmt_get_live_autonomy_status,
    fmt_run_diagnostic,
    fmt_get_system_info,
)


def test_format_action_value_bool():
    assert format_action_value(True) == "si"
    assert format_action_value(False) == "no"


def test_format_action_value_numbers():
    assert format_action_value(42) == "42"
    assert format_action_value(3.14) == "3.14"


def test_format_action_value_string():
    assert format_action_value("hello") == "hello"


def test_format_action_value_list_short():
    assert format_action_value([1, 2, 3]) == "1, 2, 3"


def test_format_action_value_list_long():
    result = format_action_value([1, 2, 3, 4, 5, 6])
    assert "1, 2, 3, 4" in result
    assert "+2 mas" in result


def test_format_action_value_empty_list():
    assert format_action_value([]) == "(vacio)"


def test_format_action_value_dict_simple():
    result = format_action_value({"a": 1, "b": "hi"})
    assert "a=1" in result
    assert "b=hi" in result


def test_format_action_value_dict_bool():
    result = format_action_value({"ok": True})
    assert "ok=si" in result


def test_format_action_value_dict_empty():
    result = format_action_value({})
    assert "null" in result.lower() or "{}" in result


def test_format_action_value_none():
    assert format_action_value(None) == "None"


def test_fmt_check_port_free():
    result = fmt_check_port({"port": 8091, "status": "libre"})
    assert "8091" in result
    assert "libre" in result


def test_fmt_check_port_active():
    result = fmt_check_port({"port": 8091, "status": "ocupado", "processes": [{"pid": 123, "name": "python", "state": "LISTENING"}]})
    assert "8091" in result
    assert "python" in result
    assert "123" in result


def test_fmt_check_http_service_healthy():
    result = fmt_check_http_service({"url": "http://127.0.0.1:8091/health", "status_code": 200, "is_healthy": True})
    assert "200" in result
    assert "saludable" in result


def test_fmt_check_http_service_error():
    result = fmt_check_http_service({"url": "http://127.0.0.1:8091/health", "status_code": 500, "is_healthy": False, "error": "timeout"})
    assert "error" in result.lower()
    assert "timeout" in result


def test_fmt_check_all_services_healthy():
    result = fmt_check_all_services({"overall_status": "healthy", "services": [{"name": "brain", "port": 8091, "running": True}]})
    assert "operativos" in result
    assert "brain" in result
    assert "OK" in result


def test_fmt_check_all_services_down():
    result = fmt_check_all_services({"overall_status": "degraded", "services": [{"name": "brain", "port": 8091, "running": False}]})
    assert "CAIDO" in result
    assert "brain" in result


def test_fmt_check_service_status():
    result = fmt_check_service_status({"services_checked": 2, "services": [{"name": "brain", "running": True}, {"name": "dash", "running": False}]})
    assert "brain: OK" in result
    assert "dash: CAIDO" in result


def test_fmt_get_live_autonomy_status():
    result = fmt_get_live_autonomy_status({"brain_health": {"status": "healthy", "sessions": 2}, "utility": {"u_score": 0.85, "verdict": "good"}})
    assert "Brain: healthy" in result
    assert "U=0.85" in result


def test_fmt_run_diagnostic():
    result = fmt_run_diagnostic({"summary": {"total_checks": 3, "successful": 2, "status": "partial"}, "diagnostic": {"checks": [{"name": "cpu", "result": {"success": True}}, {"name": "mem", "result": {"success": False}}]}})
    assert "2/3" in result
    assert "partial" in result


def test_fmt_get_system_info():
    result = fmt_get_system_info({"cpu_percent": 45.2, "memory": {"total_gb": 16, "available_gb": 8}, "disk": {"free_gb": 100, "total_gb": 500}})
    assert "45.2" in result
    assert "8GB" in result
    assert "100GB" in result


def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_fmt_helpers as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session" not in line, f"session_fmt_helpers must NOT import session.py, found: {line.strip()}"


if __name__ == "__main__":
    tests = [
        test_format_action_value_bool,
        test_format_action_value_numbers,
        test_format_action_value_string,
        test_format_action_value_list_short,
        test_format_action_value_list_long,
        test_format_action_value_empty_list,
        test_format_action_value_dict_simple,
        test_format_action_value_dict_bool,
        test_format_action_value_dict_empty,
        test_format_action_value_none,
        test_fmt_check_port_free,
        test_fmt_check_port_active,
        test_fmt_check_http_service_healthy,
        test_fmt_check_http_service_error,
        test_fmt_check_all_services_healthy,
        test_fmt_check_all_services_down,
        test_fmt_check_service_status,
        test_fmt_get_live_autonomy_status,
        test_fmt_run_diagnostic,
        test_fmt_get_system_info,
        test_module_does_not_import_session,
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