"""Contract + unit test for startup state adapter 13B.

Front: FRONT-BRAIN-MAIN-ROUTES-STARTUP-STATE-ADAPTER-13B

Static checks + pure function unit tests. No FastAPI imports,
no fastapi test harness, no runtime servers.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))

ROOT = Path(__file__).resolve().parents[2]


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


# -- 1. Adapter file exists --

def test_startup_state_adapter_file_exists():
    p = "tmp_agent/brain_v9/routes/health_status_state.py"
    _assert_contains(p,
        "build_health_payload",
        "build_status_payload",
        "build_health_response",
    )
    _assert_not_contains(p, "APIRouter", "FastAPI")


# -- 2. Main uses adapter --

def test_main_uses_startup_state_adapter():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "build_health_response",
        "build_status_payload",
        "from brain_v9.routes.health_status_state import",
    )


# -- 3. Deferred endpoints remain in main --

def test_deferred_endpoints_remain_in_main():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        '@app.get("/health")',
        '@app.get("/status")',
        '@app.get("/healthz")',
        '@app.get("/v1/agent/healthz")',
        '@app.get("/brain/validators")',
    )


# -- 4. Adapter payload shape: healthy --

def test_health_status_adapter_payload_shape_healthy():
    from brain_v9.routes.health_status_state import build_health_response, build_status_payload

    resp = build_health_response(
        startup_done=True,
        startup_error=None,
        active_sessions_count=3,
        safe_mode=False,
    )
    assert resp["status_code"] == 200
    assert resp["content"] == {
        "status": "healthy",
        "sessions": 3,
        "version": "9.0.0",
        "safe_mode": False,
    }


# -- 5. Adapter payload shape: startup_failed --

def test_health_status_adapter_payload_shape_startup_failed():
    from brain_v9.routes.health_status_state import build_health_response

    resp = build_health_response(
        startup_done=True,
        startup_error="boom",
        active_sessions_count=0,
        safe_mode=False,
    )
    assert resp["status_code"] == 503
    assert resp["content"] == {
        "status": "startup_failed",
        "error": "boom",
        "hint": "Revisa los logs",
    }


# -- 6. Adapter payload shape: initializing --

def test_health_status_adapter_payload_shape_initializing():
    from brain_v9.routes.health_status_state import build_health_response

    resp = build_health_response(
        startup_done=False,
        startup_error=None,
        active_sessions_count=1,
        safe_mode=True,
    )
    assert resp["status_code"] == 503
    assert resp["content"] == {
        "status": "initializing",
        "sessions": 1,
    }


# -- 7. Adapter status payload shape --

def test_health_status_adapter_status_payload_shape():
    from brain_v9.routes.health_status_state import build_status_payload

    payload = build_status_payload(
        active_session_keys=["s1", "s2"],
        startup_done=True,
        safe_mode=False,
    )
    assert payload == {
        "sessions": ["s1", "s2"],
        "ready": True,
        "version": "9.0.0",
        "safe_mode": False,
    }


# -- 8. Adapter has no forbidden runtime imports --

def test_adapter_has_no_forbidden_runtime_imports():
    p = "tmp_agent/brain_v9/routes/health_status_state.py"
    _sess = "brain_v9.core.ses" + "sion"
    _main = "brain_v9." + "main"
    _dash = "dashboard"
    _tr = "tr" + "ading"
    _sm = "semantic_memory"
    _fa = "faiss"
    _uv = "uv" + "icorn"
    _sub = "sub" + "process"
    _rq = "requ" + "ests"
    _hx = "ht" + "tpx"
    _tc = "Test" + "Client"
    _sys = "os.s" + "ystem"
    _fast = "Fast" + "API"
    _router = "API" + "Router"
    _assert_not_contains(p,
        f"from {_sess}",
        f"import {_sess}",
        f"from {_main}",
        f"import {_main}",
        _dash, _tr, _sm, _fa,
        _uv, _sub, _rq, _hx, _tc, _sys,
        _fast, _router,
    )


# -- 9. Adapter has no mutating/server tokens --

def test_adapter_has_no_mutating_or_server_tokens():
    p = "tmp_agent/brain_v9/routes/health_status_state.py"
    _run = "uv" + "icorn.run"
    _sub = "sub" + "process.run"
    _sys = "os.s" + "ystem"
    _dry = "dry_run" + "_only=False"
    _po = "place" + "Order"
    _so = "submit_" + "order"
    _assert_not_contains(p, _run, _sub, _sys, _dry, _po, _so)


# -- 10. Contract self-check no runtime imports --

def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_startup_state_adapter_13b.py")
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
        _tc, _uv, _rq, _hx, _sub, _sys,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import runtime: {hits}"


_TESTS = [
    test_startup_state_adapter_file_exists,
    test_main_uses_startup_state_adapter,
    test_deferred_endpoints_remain_in_main,
    test_health_status_adapter_payload_shape_healthy,
    test_health_status_adapter_payload_shape_startup_failed,
    test_health_status_adapter_payload_shape_initializing,
    test_health_status_adapter_status_payload_shape,
    test_adapter_has_no_forbidden_runtime_imports,
    test_adapter_has_no_mutating_or_server_tokens,
    test_contract_self_check_no_runtime_imports,
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