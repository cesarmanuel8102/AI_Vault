"""Contract for read-only diagnostics route split 13E.

Front: FRONT-BRAIN-MAIN-ROUTES-READONLY-DIAGNOSTICS-SPLIT-13E

Static checks only. No main.py import, no FastAPI app import, no HTTP client,
no server startup, no runtime execution.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MOVED_ENDPOINTS = [
    "/brain/rsi",
    "/brain/learned/patterns",
    "/brain/learned/patterns/{pattern_id}",
    "/brain/health_gate/status",
    "/brain/reasoning/history",
    "/brain/proactive/status",
    "/brain/llm/circuit_breaker",
]

BLOCKED_ENDPOINTS = [
    "/chat/introspectivo/debug",
    "/brain/mutations",
    "/brain/maintenance/action",
    "/rollback",
    "/gate/approve",
    "/gate/reject",
    "/tool01/permission/approve",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _assert_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{path} missing expected tokens: {missing}"


def _assert_not_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    hits = [t for t in tokens if t in text]
    assert not hits, f"{path} contains forbidden tokens: {hits}"


def test_read_only_diagnostics_router_file_exists():
    p = "tmp_agent/brain_v9/routes/read_only_diagnostics.py"
    _assert_contains(p, "APIRouter", "router = APIRouter")


def test_main_includes_read_only_diagnostics_router():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(
        p,
        "read_only_diagnostics_router",
        "app.include_router(read_only_diagnostics_router)",
    )


def test_moved_diagnostics_routes_live_in_router():
    text = _read("tmp_agent/brain_v9/routes/read_only_diagnostics.py")
    for endpoint in MOVED_ENDPOINTS:
        assert f'@router.get("{endpoint}")' in text, (
            f"read_only_diagnostics.py must declare @router.get for {endpoint}"
        )


def test_moved_diagnostics_routes_no_longer_defined_in_main():
    text = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_ENDPOINTS:
        assert f'@app.get("{endpoint}")' not in text, (
            f"main.py must not still declare @app.get for moved endpoint {endpoint}"
        )


def test_router_has_no_forbidden_runtime_imports():
    p = "tmp_agent/brain_v9/routes/read_only_diagnostics.py"
    _sess = "brain_v9.core.ses" + "sion"
    _gcm = "_GLOBAL_CHAT" + "_METRICS"
    _dash = "dash" + "board"
    _tr = "tr" + "ading"
    _sm = "semantic_mem" + "ory"
    _fa = "fai" + "ss"
    _uv = "uv" + "icorn"
    _sub = "sub" + "process"
    _rq = "requ" + "ests"
    _hx = "ht" + "tpx"
    _tc = "Test" + "Client"
    _sys = "os.s" + "ystem"
    _po = "place" + "Order"
    _so = "submit_" + "order"
    _assert_not_contains(
        p,
        "brain_v9." + "main",
        _sess,
        _gcm,
        _dash,
        _tr,
        _sm,
        _fa,
        _uv,
        _sub,
        _rq,
        _hx,
        _tc,
        _sys,
        _po,
        _so,
    )


def test_router_has_no_mutating_handlers():
    p = "tmp_agent/brain_v9/routes/read_only_diagnostics.py"
    _assert_not_contains(p, "@router.post", "@router.delete", "@router.put", "@router.patch")


def test_moved_routes_are_read_only_by_name():
    forbidden_segments = [
        "approve",
        "reject",
        "apply",
        "rollback",
        "mutation",
        "mutate",
        "delete",
        "start",
        "stop",
        "execute",
        "trade",
        "order",
    ]
    for endpoint in MOVED_ENDPOINTS:
        lowered = endpoint.lower()
        hits = [seg for seg in forbidden_segments if seg in lowered]
        assert not hits, f"moved endpoint {endpoint} has non-read-only path segments: {hits}"


def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_readonly_diagnostics_split_13e.py")
    _m = "main" + " import"
    _tc = "Test" + "Client"
    _uv = "uv" + "icorn"
    _rq = "requ" + "ests"
    _hx = "ht" + "tpx"
    _sub = "sub" + "process"
    _sys = "os.s" + "ystem"
    forbidden = [
        "from tmp_agent.brain_v9." + _m,
        "import tmp_agent.brain_v9." + _m,
        "from brain_v9." + _m,
        "import brain_v9." + _m,
        _tc,
        _uv,
        _rq,
        _hx,
        _sub,
        _sys,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import runtime: {hits}"


def test_deferred_or_blocked_candidates_not_moved():
    text = _read("tmp_agent/brain_v9/routes/read_only_diagnostics.py")
    for endpoint in BLOCKED_ENDPOINTS:
        assert endpoint not in text, f"blocked endpoint must not be moved to read-only diagnostics: {endpoint}"


_TESTS = [
    test_read_only_diagnostics_router_file_exists,
    test_main_includes_read_only_diagnostics_router,
    test_moved_diagnostics_routes_live_in_router,
    test_moved_diagnostics_routes_no_longer_defined_in_main,
    test_router_has_no_forbidden_runtime_imports,
    test_router_has_no_mutating_handlers,
    test_moved_routes_are_read_only_by_name,
    test_contract_self_check_no_runtime_imports,
    test_deferred_or_blocked_candidates_not_moved,
]


if __name__ == "__main__":
    passed = 0
    failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
