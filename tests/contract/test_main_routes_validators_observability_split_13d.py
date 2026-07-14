"""Contract for validators observability split 13D.

Front: FRONT-BRAIN-MAIN-ROUTES-VALIDATORS-OBSERVABILITY-SPLIT-13D

Static checks + provider unit test. No fastapi app imports,
no test harness, no runtime servers.
"""
from __future__ import annotations

import asyncio
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


# -- 1. Router file exists --

def test_validators_router_file_exists():
    p = "tmp_agent/brain_v9/routes/validators_observability.py"
    _assert_contains(p, "APIRouter", "router = APIRouter")


# -- 2. Route moved to router --

def test_validators_route_moved_to_router():
    _assert_contains("tmp_agent/brain_v9/routes/validators_observability.py",
        '@router.get("/brain/validators")')
    _assert_not_contains("tmp_agent/brain_v9/main.py",
        '@app.get("/brain/validators")')


# -- 3. Main includes validators router --

def test_main_includes_validators_observability_router():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "validators_observability_router",
        "app.include_router(validators_observability_router)",
        "configure_validators_metrics_provider",
    )


# -- 4. Provider boundary exists --

def test_validators_provider_boundary_exists():
    p = "tmp_agent/brain_v9/routes/validators_observability.py"
    _assert_contains(p,
        "configure_validators_metrics_provider",
        "_validators_metrics_provider",
        "_validators_metrics",
        "validators_metrics_provider_not_configured",
    )


# -- 5. Router does not import session or runtime --

def test_router_does_not_import_session_or_runtime():
    p = "tmp_agent/brain_v9/routes/validators_observability.py"
    _sess = "brain_v9.core.ses" + "sion"
    _gcm = "_GLOBAL_CHAT" + "_METRICS"
    _main = "brain_v9." + "main"
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
    # Direct token forbidden (not just import forms)
    _direct_sess = "brain_v9.core." + "session"
    _direct_gcm = "_GLOBAL_CHAT" + "_METRICS"
    _assert_not_contains(p,
        f"from {_sess}", f"import {_sess}",
        _gcm,
        f"from {_main}", f"import {_main}",
        _dash, _tr, _sm, _fa,
        _uv, _sub, _rq, _hx, _tc, _sys,
        _direct_sess,
        _direct_gcm,
    )


# -- 6. Main provider is the only session boundary --

def test_main_provider_is_the_only_session_boundary():
    _gcm = "_GLOBAL_CHAT" + "_METRICS"
    _assert_contains("tmp_agent/brain_v9/main.py", _gcm)
    _assert_not_contains("tmp_agent/brain_v9/routes/validators_observability.py",
        "_GLOBAL_CHAT" + "_METRICS",
        "brain_v9.core." + "session",
    )


# -- 7. No mutating handlers --

def test_validators_route_has_no_mutating_handlers():
    p = "tmp_agent/brain_v9/routes/validators_observability.py"
    _assert_not_contains(p,
        "@router.post", "@router.delete",
        "@router.put", "@router.patch",
    )


# -- 8. Contract self-check --

def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_validators_observability_split_13d.py")
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


# -- 9. Provider can be configured with fake payload --

def test_provider_can_be_configured_with_fake_payload():
    from brain_v9.routes import validators_observability as vo

    vo.configure_validators_metrics_provider(lambda: {"ok": True, "validators": {}})
    payload = vo._validators_metrics()
    assert payload["ok"] is True

    result = asyncio.run(vo.brain_validators())
    assert result == {"ok": True, "validators": {}}


_TESTS = [
    test_validators_router_file_exists,
    test_validators_route_moved_to_router,
    test_main_includes_validators_observability_router,
    test_validators_provider_boundary_exists,
    test_router_does_not_import_session_or_runtime,
    test_main_provider_is_the_only_session_boundary,
    test_validators_route_has_no_mutating_handlers,
    test_contract_self_check_no_runtime_imports,
    test_provider_can_be_configured_with_fake_payload,
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