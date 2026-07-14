"""Contract for health-status deferred split 13C.

Front: FRONT-BRAIN-MAIN-ROUTES-HEALTH-STATUS-DEFERRED-SPLIT-13C

Static checks + pure adapter unit tests. No fastapi app imports,
no test harness, no runtime servers.
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


# -- 1. Router declares deferred routes --

def test_health_status_router_declares_deferred_routes():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_contains(p,
        '@router.get("/health")',
        '@router.get("/status")',
        '@router.get("/healthz")',
        '@router.get("/v1/agent/healthz")',
    )


# -- 2. Deferred routes no longer in main --

def test_deferred_routes_no_longer_defined_directly_in_main():
    p = "tmp_agent/brain_v9/main.py"
    _assert_not_contains(p,
        '@app.get("/health")',
        '@app.get("/status")',
        '@app.get("/healthz")',
        '@app.get("/v1/agent/healthz")',
    )


# -- 3. Brain validators remains deferred in main --

def test_brain_validators_remains_deferred_in_main():
    # /brain/validators moved to validators_observability.py in 13D
    _assert_not_contains("tmp_agent/brain_v9/main.py", '@app.get("/brain/validators")')
    _assert_not_contains("tmp_agent/brain_v9/routes/health_status.py",
        '@router.get("/brain/validators")')


# -- 4. Main configures startup state provider --

def test_main_configures_startup_state_provider():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "configure_startup_state_provider",
        "active_sessions_count",
        "active_session_keys",
        "startup_done",
        "startup_error",
        "safe_mode",
    )


# -- 5. Router uses adapter and provider --

def test_health_status_router_uses_adapter():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_contains(p,
        "build_health_response",
        "build_status_payload",
        "configure_startup_state_provider",
        "_startup_state_provider",
        "_startup_state",
    )


# -- 6. Adapter payload shapes unchanged --

def test_health_status_payload_shapes_unchanged():
    from brain_v9.routes.health_status_state import build_health_response, build_status_payload

    # startup_failed
    resp = build_health_response(
        startup_done=True, startup_error="boom",
        active_sessions_count=0, safe_mode=False,
    )
    assert resp["status_code"] == 503
    assert resp["content"] == {"status": "startup_failed", "error": "boom", "hint": "Revisa los logs"}

    # initializing
    resp = build_health_response(
        startup_done=False, startup_error=None,
        active_sessions_count=1, safe_mode=True,
    )
    assert resp["status_code"] == 503
    assert resp["content"] == {"status": "initializing", "sessions": 1}

    # healthy
    resp = build_health_response(
        startup_done=True, startup_error=None,
        active_sessions_count=3, safe_mode=False,
    )
    assert resp["status_code"] == 200
    assert resp["content"] == {"status": "healthy", "sessions": 3, "version": "9.0.0", "safe_mode": False}

    # status
    payload = build_status_payload(
        active_session_keys=["s1", "s2"],
        startup_done=True, safe_mode=False,
    )
    assert payload == {"sessions": ["s1", "s2"], "ready": True, "version": "9.0.0", "safe_mode": False}


# -- 7. Router has no forbidden imports --

def test_health_status_router_has_no_forbidden_imports():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _main = "brain_v9." + "main"
    _sess = "brain_v9.core.ses" + "sion"
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
    _assert_not_contains(p,
        f"from {_main}", f"import {_main}",
        f"from {_sess}", f"import {_sess}",
        _dash, _tr, _sm, _fa,
        _uv, _sub, _rq, _hx, _tc, _sys,
    )


# -- 8. Router has no mutating handlers --

def test_health_status_router_has_no_mutating_handlers():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_not_contains(p,
        "@router.post", "@router.delete",
        "@router.put", "@router.patch",
    )


# -- 9. Contract self-check --

def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_health_status_deferred_split_13c.py")
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
    test_health_status_router_declares_deferred_routes,
    test_deferred_routes_no_longer_defined_directly_in_main,
    test_brain_validators_remains_deferred_in_main,
    test_main_configures_startup_state_provider,
    test_health_status_router_uses_adapter,
    test_health_status_payload_shapes_unchanged,
    test_health_status_router_has_no_forbidden_imports,
    test_health_status_router_has_no_mutating_handlers,
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