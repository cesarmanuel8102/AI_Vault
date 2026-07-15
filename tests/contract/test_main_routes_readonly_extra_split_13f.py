"""Contract for extra read-only route split 13F.

Front: FRONT-BRAIN-MAIN-ROUTER-FULL-MIGRATION-SWEEP-13F-TO-CLOSE

Static checks only. No main.py import, no FastAPI app import, no HTTP client,
no server startup, no runtime execution.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ROUTER = "tmp_agent/brain_v9/routes/read_only_diagnostics_extra.py"

MOVED_ENDPOINTS = [
    "/brain/utility",
    "/brain/utility/v2",
    "/brain/utility/status",
    "/brain/roadmap/governance",
    "/brain/roadmap/development-status",
    "/brain/post-bl-roadmap/status",
    "/brain/meta-improvement/status",
    "/brain/chat-product/status",
    "/brain/autonomous-governance-eval/status",
    "/brain/utility-governance/status",
    "/brain/research/summary",
    "/brain/research/knowledge",
    "/brain/research/indicators",
    "/brain/research/strategies",
    "/brain/research/hypotheses",
    "/brain/research/candidates",
    "/brain/learning/status",
    "/brain/self-improvement/ledger",
    "/brain/self-improvement/change/{change_id}/status",
]

DEFERRED_ENDPOINTS = [
    "/brain/meta-governance/status",
    "/brain/autonomy/next-actions",
    "/brain/session-memory",
    "/brain/pipeline-health",
    "/brain/operations",
    "/brain/strategy-engine/summary",
    "/brain/semantic-memory/status",
    "/brain/autonomy/ibkr-ingester",
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


def test_read_only_extra_router_file_exists():
    _assert_contains(ROUTER, "APIRouter", "router = APIRouter")


def test_main_includes_read_only_extra_router():
    _assert_contains(
        "tmp_agent/brain_v9/main.py",
        "read_only_diagnostics_extra_router",
        "app.include_router(read_only_diagnostics_extra_router)",
    )


def test_moved_extra_routes_live_in_router():
    text = _read(ROUTER)
    for endpoint in MOVED_ENDPOINTS:
        assert f'@router.get("{endpoint}")' in text, (
            f"read_only_diagnostics_extra.py must declare @router.get for {endpoint}"
        )


def test_moved_extra_routes_no_longer_defined_in_main():
    text = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_ENDPOINTS:
        assert f'@app.get("{endpoint}")' not in text, (
            f"main.py must not still declare @app.get for moved endpoint {endpoint}"
        )


def test_router_has_no_forbidden_runtime_imports():
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
        ROUTER,
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
    _assert_not_contains(ROUTER, "@router.post", "@router.delete", "@router.put", "@router.patch")


def test_deferred_or_blocked_candidates_not_moved():
    text = _read(ROUTER)
    for endpoint in DEFERRED_ENDPOINTS:
        assert endpoint not in text, f"deferred endpoint must not be moved to read-only extra: {endpoint}"


def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_readonly_extra_split_13f.py")
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


_TESTS = [
    test_read_only_extra_router_file_exists,
    test_main_includes_read_only_extra_router,
    test_moved_extra_routes_live_in_router,
    test_moved_extra_routes_no_longer_defined_in_main,
    test_router_has_no_forbidden_runtime_imports,
    test_router_has_no_mutating_handlers,
    test_deferred_or_blocked_candidates_not_moved,
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
