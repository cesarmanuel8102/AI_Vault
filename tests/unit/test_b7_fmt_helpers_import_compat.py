"""B7-STRANGLER-06 import-compat: BrainSession._fmt_* shim integrity + dispatcher.

Verifies:
* The 17 module-level fmt_<name> functions exist and are callable.
* Each BrainSession._fmt_<name> classmethod still resolves via getattr(cls, name).
* The shim and the standalone helper produce identical output for sample payloads.
* _TOOL_FORMATTERS dispatch (incl. the ``check_url`` alias) still works through
  ``BrainSession._format_tool_result``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))


_FMT_NAMES = (
    "check_port", "check_http_service", "check_all_services",
    "check_service_status", "get_live_autonomy_status", "run_diagnostic",
    "get_system_info", "run_command", "read_file", "list_directory",
    "search_files", "list_processes", "grep_codebase",
    "list_recent_brain_changes", "get_chat_metrics", "semantic_memory_search",
    "get_technical_introspection",
)


def test_helpers_module_exposes_17_functions():
    from brain_v9.core import session_fmt_helpers as h
    for n in _FMT_NAMES:
        fn = getattr(h, f"fmt_{n}", None)
        assert callable(fn), f"missing/uncallable fmt_{n}"
    assert sorted(h.__all__) == sorted(f"fmt_{n}" for n in _FMT_NAMES)


def test_brain_session_classmethods_present_and_callable():
    from brain_v9.core.session import BrainSession
    for n in _FMT_NAMES:
        method_name = f"_fmt_{n}"
        bound = getattr(BrainSession, method_name, None)
        assert callable(bound), f"BrainSession.{method_name} not callable"


def test_shim_and_standalone_produce_same_output():
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_fmt_helpers as h
    samples = {
        "check_port": {"port": 8080, "status": "libre"},
        "check_http_service": {"url": "http://localhost:8080/", "status_code": 200, "is_healthy": True},
        "check_all_services": {"overall_status": "healthy", "services": [{"name": "api", "port": 80, "running": True}]},
        "check_service_status": {"services_checked": 2, "services": [{"name": "x", "running": True}]},
        "get_live_autonomy_status": {"brain_health": {"status": "ok", "sessions": 1}, "utility": {"u_score": 0.9, "verdict": "go"}},
        "run_diagnostic": {"summary": {"total_checks": 3, "successful": 3, "status": "ok"}, "diagnostic": {"checks": []}},
        "get_system_info": {"cpu_percent": 12, "memory": {"total_gb": 16, "available_gb": 8}, "disk": {"free_gb": 100, "total_gb": 500}},
        "run_command": {"stdout": "hola", "stderr": "", "return_code": 0},
        "read_file": {"path": "x.py", "content": "print(1)\n", "lines": 1},
        "list_directory": {"path": ".", "items": ["a", "b"]},
        "search_files": {"matches": [{"file": "a.py"}]},
        "list_processes": {"processes": [{"name": "p", "pid": 1}]},
        "grep_codebase": [{"rel_path": "a.py", "line": 1, "text": "x"}],
        "list_recent_brain_changes": {"days": 7, "ledger": [], "edited_files": [{"path": "a.py", "mtime": "now"}]},
        "get_chat_metrics": {"conversations": 10, "success_rate": 0.9, "routes": {"r1": 5}},
        "semantic_memory_search": {"query": "q", "results": [{"score": 0.8, "text": "hi"}]},
        "get_technical_introspection": {"process": {"pid": 1, "uptime": 10, "memory_mb": 100}},
    }
    for n, payload in samples.items():
        shim_out = getattr(BrainSession, f"_fmt_{n}")(payload)
        helper_out = getattr(h, f"fmt_{n}")(payload)
        assert shim_out == helper_out, f"divergence for {n}: shim={shim_out!r} helper={helper_out!r}"


def test_TOOL_FORMATTERS_registry_intact():
    from brain_v9.core.session import BrainSession
    reg = BrainSession._TOOL_FORMATTERS
    # All 17 helpers + the check_url alias = 18 entries
    assert len(reg) == 18
    assert reg["check_url"] == "_fmt_check_http_service"
    for tool_name, method_name in reg.items():
        assert callable(getattr(BrainSession, method_name)), \
            f"{tool_name} -> {method_name} not callable on BrainSession"


def test_format_tool_result_dispatch_via_alias():
    """check_url aliases to _fmt_check_http_service through the dispatcher."""
    from brain_v9.core.session import BrainSession
    payload = {"url": "http://localhost:8080/health", "status_code": 200, "is_healthy": True}
    direct = BrainSession._fmt_check_http_service(payload)
    via_alias = BrainSession._format_tool_result("check_url", True, payload)
    via_canonical = BrainSession._format_tool_result("check_http_service", True, payload)
    assert direct == via_alias == via_canonical
    assert isinstance(direct, str) and direct


def test_format_tool_result_dispatch_smoke_all():
    from brain_v9.core.session import BrainSession
    # Minimal payloads keyed by tool name
    payloads = {
        "check_port": {"port": 22, "status": "libre"},
        "check_http_service": {"url": "x", "status_code": 200, "is_healthy": True},
        "check_all_services": {"overall_status": "healthy", "services": []},
        "check_service_status": {"services_checked": 0, "services": []},
        "get_live_autonomy_status": {},
        "run_diagnostic": {"summary": {}, "diagnostic": {"checks": []}},
        "get_system_info": {"cpu_percent": 1, "memory": {}, "disk": {}},
        "run_command": {"stdout": "", "stderr": "", "return_code": 0},
        "read_file": {"path": "p", "content": "", "lines": 0},
        "list_directory": {"path": ".", "items": []},
        "search_files": {"matches": []},
        "list_processes": {"processes": []},
        "grep_codebase": [],
        "list_recent_brain_changes": {"days": 1, "ledger": [], "edited_files": []},
        "get_chat_metrics": {"conversations": 0, "success_rate": 0},
        "semantic_memory_search": {"query": "q", "results": []},
        "get_technical_introspection": {},
    }
    for tool, payload in payloads.items():
        out = BrainSession._format_tool_result(tool, True, payload)
        assert isinstance(out, str)
