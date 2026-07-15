"""Contract for memory/semantic route split 14B."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/memory_semantic_routes.py"

MOVED = [
    ("get", "/brain/semantic-memory/search"),
    ("post", "/brain/semantic-memory/ingest"),
    ("post", "/brain/semantic-memory/ingest-session"),
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_memory_semantic_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "memory_semantic_routes_router" in main
    assert "app.include_router(memory_semantic_routes_router)" in main


def test_memory_semantic_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoint in MOVED:
        assert f'@router.{method}("{endpoint}")' in router
        assert f'@app.{method}("{endpoint}")' not in main


def test_memory_semantic_mutating_routes_keep_operator_access():
    router = _read(ROUTER)
    for endpoint in ["/brain/semantic-memory/ingest", "/brain/semantic-memory/ingest-session"]:
        decorator = f'@router.post("{endpoint}")'
        pos = router.index(decorator)
        next_decorator = router.find("\n@router.", pos + len(decorator))
        block = router[pos:] if next_decorator == -1 else router[pos:next_decorator]
        assert "_operator: OperatorAccess" in block


def test_memory_semantic_router_no_top_level_memory_execution():
    router = _read(ROUTER)
    first_route = router.index("@router.")
    top_level = router[:first_route]
    forbidden = [
        "get_semantic_memory",
        "ingest_text",
        "ingest_session_memory",
        "promote_record",
        "faiss.write_index",
        ".add(",
        "rebuild",
    ]
    hits = [t for t in forbidden if t in top_level]
    assert not hits, f"memory semantic router contains top-level execution tokens: {hits}"


def test_memory_semantic_router_no_dry_run_or_execution_bypass():
    router = _read(ROUTER)
    forbidden = [
        "dry_run_only=False",
        "allow_" + "all",
        "disable_" + "auth",
        "skip_" + "auth",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"memory semantic router contains forbidden bypass tokens: {hits}"


_TESTS = [
    test_memory_semantic_router_exists_and_is_included,
    test_memory_semantic_routes_moved,
    test_memory_semantic_mutating_routes_keep_operator_access,
    test_memory_semantic_router_no_top_level_memory_execution,
    test_memory_semantic_router_no_dry_run_or_execution_bypass,
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
