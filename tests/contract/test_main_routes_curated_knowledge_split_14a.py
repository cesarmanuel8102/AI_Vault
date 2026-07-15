"""Contract for curated knowledge route split 14A.

Static checks only. No main.py import, no FastAPI app import, no HTTP client,
no server startup, no runtime execution.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/curated_knowledge_routes.py"

MOVED = {
    "get": ["/brain/curated-knowledge/status"],
    "post": [
        "/brain/curated-knowledge/search",
        "/brain/curated-knowledge/demo-search",
    ],
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_curated_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "curated_knowledge_routes_router" in main
    assert "app.include_router(curated_knowledge_routes_router)" in main


def test_curated_routes_moved_with_methods_preserved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoints in MOVED.items():
        for endpoint in endpoints:
            assert f'@router.{method}("{endpoint}")' in router
            assert f'@app.{method}("{endpoint}")' not in main


def test_curated_router_preserves_operator_and_policy_tokens():
    router = _read(ROUTER)
    for token in [
        "require_operator_access",
        "OperatorAccess",
        "verified_curated_readonly",
        "verified_curated_readonly_demo",
        "real_write_allowed",
        "faiss_write_allowed",
        "global_config_mutated",
        "automatic_context_injection",
        "search_curated_candidates",
        "load_curated_lookup_index",
        "demo_index_path",
    ]:
        assert token in router, f"missing curated policy token: {token}"


def test_curated_router_has_no_forbidden_runtime_imports():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9." + "main",
        "brain_v9.core.ses" + "sion",
        "_GLOBAL_CHAT" + "_METRICS",
        "dash" + "board",
        "tr" + "ading",
        "uv" + "icorn",
        "sub" + "process",
        "requ" + "ests.",
        "ht" + "tpx.",
        "Test" + "Client",
        "os.s" + "ystem",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"curated router contains forbidden tokens: {hits}"


def test_contract_self_check_no_runtime_imports():
    self_src = _read("tests/contract/test_main_routes_curated_knowledge_split_14a.py")
    forbidden = [
        "from brain_v9." + "main import",
        "import brain_v9." + "main",
        "Test" + "Client",
        "uv" + "icorn",
        "requ" + "ests.",
        "ht" + "tpx.",
        "sub" + "process",
        "os.s" + "ystem",
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import runtime: {hits}"


_TESTS = [
    test_curated_router_exists_and_is_included,
    test_curated_routes_moved_with_methods_preserved,
    test_curated_router_preserves_operator_and_policy_tokens,
    test_curated_router_has_no_forbidden_runtime_imports,
    test_contract_self_check_no_runtime_imports,
]


if __name__ == "__main__":
    failed = 0
    for test in _TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {test.__name__}: {exc}")
    print(f"\n{len(_TESTS) - failed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
