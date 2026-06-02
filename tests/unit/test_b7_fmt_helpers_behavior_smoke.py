"""B7-STRANGLER-06 behavior smoke: each fmt_<name> tolerates empty/partial
payloads, returns a string, and embeds essential keys for canonical inputs.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))


def test_fmt_check_port_libre():
    from brain_v9.core.session_fmt_helpers import fmt_check_port
    out = fmt_check_port({"port": 9000, "status": "libre"})
    assert "9000" in out and "libre" in out


def test_fmt_check_port_active_with_processes():
    from brain_v9.core.session_fmt_helpers import fmt_check_port
    out = fmt_check_port({
        "port": 8080, "status": "ocupado",
        "processes": [{"pid": 1234, "name": "python.exe", "state": "LISTENING"}],
    })
    assert "8080" in out and "python.exe" in out and "1234" in out


def test_fmt_check_port_kernel_only():
    from brain_v9.core.session_fmt_helpers import fmt_check_port
    out = fmt_check_port({"port": 80, "status": "ocupado", "processes": [{"pid": 0, "name": "Idle"}]})
    assert "kernel" in out


def test_fmt_check_http_service_200():
    from brain_v9.core.session_fmt_helpers import fmt_check_http_service
    out = fmt_check_http_service({"url": "http://localhost:8080/", "status_code": 200, "is_healthy": True})
    assert "200" in out


def test_fmt_check_http_service_error():
    from brain_v9.core.session_fmt_helpers import fmt_check_http_service
    out = fmt_check_http_service({"url": "http://x/", "error": "timeout"})
    assert "error" in out and "timeout" in out


def test_fmt_check_all_services():
    from brain_v9.core.session_fmt_helpers import fmt_check_all_services
    out = fmt_check_all_services({
        "overall_status": "healthy",
        "services": [{"name": "api", "port": 80, "running": True}],
    })
    assert "operativos" in out and "api" in out


def test_fmt_check_service_status_empty():
    from brain_v9.core.session_fmt_helpers import fmt_check_service_status
    out = fmt_check_service_status({"services_checked": 5, "services": []})
    assert "5" in out


def test_fmt_get_live_autonomy_status():
    from brain_v9.core.session_fmt_helpers import fmt_get_live_autonomy_status
    out = fmt_get_live_autonomy_status({
        "brain_health": {"status": "ok", "sessions": 3},
        "utility": {"u_score": 0.85, "verdict": "go"},
        "next_actions": {"top_action": "deploy", "blockers": ["b1"]},
    })
    assert "ok" in out and "0.85" in out and "deploy" in out and "b1" in out


def test_fmt_run_diagnostic():
    from brain_v9.core.session_fmt_helpers import fmt_run_diagnostic
    out = fmt_run_diagnostic({
        "summary": {"total_checks": 2, "successful": 2, "status": "ok"},
        "diagnostic": {"checks": [{"name": "c1", "result": {"success": True}}]},
    })
    assert "2/2" in out and "c1" in out


def test_fmt_get_system_info():
    from brain_v9.core.session_fmt_helpers import fmt_get_system_info
    out = fmt_get_system_info({
        "cpu_percent": 42, "memory": {"total_gb": 16, "available_gb": 8},
        "disk": {"free_gb": 100, "total_gb": 500},
    })
    assert "42" in out and "16" in out and "100" in out


def test_fmt_run_command_no_output():
    from brain_v9.core.session_fmt_helpers import fmt_run_command
    out = fmt_run_command({"stdout": "", "stderr": "", "return_code": 0})
    assert "sin salida" in out


def test_fmt_run_command_truncates_long():
    from brain_v9.core.session_fmt_helpers import fmt_run_command
    long = "x" * 1000
    out = fmt_run_command({"stdout": long, "return_code": 0})
    assert out.endswith("...") and len(out) <= 503


def test_fmt_read_file_short():
    from brain_v9.core.session_fmt_helpers import fmt_read_file
    out = fmt_read_file({"path": "C:/AI_VAULT/x.py", "content": "print(1)\n", "lines": 1})
    assert "x.py" in out and "1 lineas" in out


def test_fmt_read_file_truncated():
    from brain_v9.core.session_fmt_helpers import fmt_read_file
    out = fmt_read_file({"path": "x.py", "content": "a" * 600, "lines": 1})
    assert out.endswith("...") and "lineas" in out


def test_fmt_list_directory_list():
    from brain_v9.core.session_fmt_helpers import fmt_list_directory
    out = fmt_list_directory(["a", "b", "c"])
    assert "a" in out and "b" in out and "c" in out


def test_fmt_list_directory_dict_many():
    from brain_v9.core.session_fmt_helpers import fmt_list_directory
    out = fmt_list_directory({"path": "/x", "items": list(range(40))})
    assert "/x" in out and "40 elementos" in out


def test_fmt_search_files_empty():
    from brain_v9.core.session_fmt_helpers import fmt_search_files
    out = fmt_search_files({"matches": []})
    assert out == "Sin resultados"


def test_fmt_search_files_many():
    from brain_v9.core.session_fmt_helpers import fmt_search_files
    out = fmt_search_files({"matches": [{"file": f"f{i}.py"} for i in range(20)]})
    assert "20" in out and "12 mas" in out


def test_fmt_list_processes_truncates():
    from brain_v9.core.session_fmt_helpers import fmt_list_processes
    procs = [{"name": f"p{i}", "pid": i} for i in range(15)]
    out = fmt_list_processes({"processes": procs})
    assert "15 proceso" in out and "5 mas" in out


def test_fmt_grep_codebase_empty():
    from brain_v9.core.session_fmt_helpers import fmt_grep_codebase
    out = fmt_grep_codebase([])
    assert "Sin coincidencias" in out


def test_fmt_grep_codebase_error():
    from brain_v9.core.session_fmt_helpers import fmt_grep_codebase
    out = fmt_grep_codebase([{"error": "bad regex"}])
    assert "bad regex" in out


def test_fmt_grep_codebase_hits():
    from brain_v9.core.session_fmt_helpers import fmt_grep_codebase
    hits = [{"rel_path": f"a{i}.py", "line": i, "text": "match"} for i in range(12)]
    out = fmt_grep_codebase(hits)
    assert "12 coincidencia" in out and "4 mas" in out


def test_fmt_list_recent_brain_changes_empty():
    from brain_v9.core.session_fmt_helpers import fmt_list_recent_brain_changes
    out = fmt_list_recent_brain_changes({"days": 7, "ledger": [], "edited_files": []})
    assert "Sin cambios" in out and "7" in out


def test_fmt_list_recent_brain_changes_with_data():
    from brain_v9.core.session_fmt_helpers import fmt_list_recent_brain_changes
    out = fmt_list_recent_brain_changes({
        "days": 3,
        "ledger": [{"title": "T1", "date": "2026-06-01"}],
        "edited_files": [{"path": "x.py", "mtime": "now"}],
    })
    assert "T1" in out and "x.py" in out


def test_fmt_get_chat_metrics():
    from brain_v9.core.session_fmt_helpers import fmt_get_chat_metrics
    out = fmt_get_chat_metrics({
        "conversations": 100, "success_rate": 0.95,
        "routes": {"r1": 50, "r2": 30},
        "errors": {"e1": 2},
        "validators": {"v1": 5},
    })
    assert "100" in out and "95.0%" in out and "r1" in out


def test_fmt_get_chat_metrics_non_dict():
    from brain_v9.core.session_fmt_helpers import fmt_get_chat_metrics
    out = fmt_get_chat_metrics([])  # type: ignore[arg-type]
    assert isinstance(out, str)


def test_fmt_semantic_memory_search_empty():
    from brain_v9.core.session_fmt_helpers import fmt_semantic_memory_search
    out = fmt_semantic_memory_search({"query": "foo", "results": []})
    assert "foo" in out and "sin resultados" in out


def test_fmt_semantic_memory_search_hits():
    from brain_v9.core.session_fmt_helpers import fmt_semantic_memory_search
    out = fmt_semantic_memory_search({
        "query": "foo",
        "results": [{"score": 0.8, "text": "hello", "source": "s1"}],
    })
    assert "foo" in out and "0.80" in out and "hello" in out


def test_fmt_get_technical_introspection_full():
    from brain_v9.core.session_fmt_helpers import fmt_get_technical_introspection
    out = fmt_get_technical_introspection({
        "process": {"pid": 4242, "uptime": 100, "memory_mb": 512},
        "vram": {"used_mb": 1000, "total_mb": 8000},
        "code": {"python_files": 500, "lines_of_code": 50000},
        "capabilities": {"count": 30},
    })
    assert "4242" in out and "1000" in out and "500" in out and "30" in out


def test_fmt_get_technical_introspection_non_dict():
    from brain_v9.core.session_fmt_helpers import fmt_get_technical_introspection
    out = fmt_get_technical_introspection("garbage")  # type: ignore[arg-type]
    assert isinstance(out, str)


def test_all_fmt_tolerate_empty_input():
    """Each fmt_<n> must not raise on empty dict/list input."""
    from brain_v9.core import session_fmt_helpers as h
    list_input_names = {"fmt_list_directory", "fmt_grep_codebase"}
    for name in h.__all__:
        fn = getattr(h, name)
        empty = [] if name in list_input_names else {}
        result = fn(empty)
        assert isinstance(result, str), f"{name} did not return str"
