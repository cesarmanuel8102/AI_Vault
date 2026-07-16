"""Contract for dev/debug diagnostic route split 14E."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/dev_debug_routes.py"

MOVED = [
    "/brain/auto-surgeon/status",
    "/brain/auto-surgeon/diagnostics",
    "/self-diagnostic",
    "/brain/metacognition/status",
    "/brain/introspection/status",
    "/brain/introspection/gpu",
]
MOVED_POST_TO_REMAINING_CONTROL = [
    "/self-diagnostic/run",
]
DEFERRED_POST = []  # /brain/metacognition/audit moved to dev_pipeline_audit_routes.py in 16B


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_dev_debug_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "dev_debug_routes_router" in main
    assert "app.include_router(dev_debug_routes_router)" in main


def test_dev_debug_get_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED:
        assert f'@router.get("{endpoint}")' in router
        assert f'@app.get("{endpoint}")' not in main
    for endpoint in DEFERRED_POST:
        assert f'@app.post("{endpoint}")' in main
        assert endpoint not in router
    remaining = _read("tmp_agent/brain_v9/routes/main_remaining_control_routes.py")
    for endpoint in MOVED_POST_TO_REMAINING_CONTROL:
        assert f'@router.post("{endpoint}")' in remaining
        assert f'@app.post("{endpoint}")' not in main
        assert endpoint not in router


def test_dev_debug_router_no_runtime_launch_tokens():
    router = _read(ROUTER)
    forbidden = [
        "uv" + "icorn",
        "sub" + "process",
        "web" + "browser",
        "requ" + "ests.",
        "ht" + "tpx.",
        "Test" + "Client",
        "brain_v9." + "main",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"dev/debug router contains forbidden tokens: {hits}"


_TESTS = [
    test_dev_debug_router_exists_and_is_included,
    test_dev_debug_get_routes_moved,
    test_dev_debug_router_no_runtime_launch_tokens,
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
