"""Static contract for health-status route split 13A.

Front: FRONT-BRAIN-MAIN-ROUTES-HEALTH-STATUS-SPLIT-13A

100% static: reads source files as text. No runtime imports,
no servers, no HTTP calls.
"""
from __future__ import annotations

from pathlib import Path

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


MOVED_ENDPOINTS = [
    '/v1/agent/status',
    '/brain/health',
    '/brain/security/posture',
    '/brain/risk/status',
    '/brain/governance/health',
    '/brain/metrics',
    '/tools/coverage',
]


# -- 1. Router file exists --

def test_health_status_router_file_exists():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_contains(p, "APIRouter", "router = APIRouter")


# -- 2. Main includes health_status_router --

def test_main_includes_health_status_router():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p, "health_status_router", "app.include_router(health_status_router)")


# -- 3. Moved routes live in new router --

def test_moved_health_status_routes_live_in_new_router():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_contains(p, "@router.get")
    for ep in MOVED_ENDPOINTS:
        _assert_contains(p, ep)


# -- 4. Moved routes no longer in main --

def test_moved_routes_no_longer_defined_directly_in_main():
    p = "tmp_agent/brain_v9/main.py"
    for ep in MOVED_ENDPOINTS:
        _assert_not_contains(p, f'@app.get("{ep}"')


# -- 5. New router has no forbidden runtime imports --

def test_new_router_has_no_forbidden_runtime_imports():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _sess = "brain_v9.core.ses" + "sion"
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
    _assert_not_contains(p,
        f"from {_sess}",
        f"import {_sess}",
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
    )


# -- 6. New router has no mutating handlers --

def test_new_router_has_no_mutating_handlers():
    p = "tmp_agent/brain_v9/routes/health_status.py"
    _assert_not_contains(p,
        "@router.post",
        "@router.delete",
        "@router.put",
        "@router.patch",
    )


# -- 7. Contract self-check no runtime imports --

def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_health_status_split_13a.py")
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


# -- 8. Existing contracts reference health_status_split --

def test_existing_router_contracts_reference_health_status_split():
    b12 = _read("tests/contract/test_main_router_topology_contract_12b.py")
    assert "health_status_router" in b12, "12B must reference health_status_router"
    d12 = _read("tests/contract/test_main_router_surface_matrix_12d.py")
    assert "health_status.py" in d12, "12D must reference health_status.py"


_TESTS = [
    test_health_status_router_file_exists,
    test_main_includes_health_status_router,
    test_moved_health_status_routes_live_in_new_router,
    test_moved_routes_no_longer_defined_directly_in_main,
    test_new_router_has_no_forbidden_runtime_imports,
    test_new_router_has_no_mutating_handlers,
    test_contract_self_check_no_runtime_imports,
    test_existing_router_contracts_reference_health_status_split,
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