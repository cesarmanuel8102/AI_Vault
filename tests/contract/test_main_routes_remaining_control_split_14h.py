"""Contract for remaining controlled diagnostics/ops route split 14H."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/main_remaining_control_routes.py"

MOVED_GET = [
    "/brain/ops/log-status",
    "/brain/ops/adn-quality",
    "/brain/ops/upgrade-check",
    "/brain/ops/pre-upgrade",
    "/brain/ops/post-upgrade",
    "/brain/ops/ethics",
]

MOVED_POST = [
    "/brain/ops/log-cleanup",
    "/self-diagnostic/run",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_remaining_control_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "main_remaining_control_routes_router" in main
    assert "app.include_router(main_remaining_control_routes_router)" in main


def test_remaining_control_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_GET:
        assert f'@router.get("{endpoint}")' in router
        assert f'@app.get("{endpoint}")' not in main
    for endpoint in MOVED_POST:
        assert f'@router.post("{endpoint}")' in router
        assert f'@app.post("{endpoint}")' not in main


def test_remaining_control_posts_keep_operator_access():
    router = _read(ROUTER)
    for endpoint in MOVED_POST:
        decorator = f'@router.post("{endpoint}")'
        pos = router.index(decorator)
        next_decorator = router.find("\n@router.", pos + len(decorator))
        block = router[pos:] if next_decorator == -1 else router[pos:next_decorator]
        assert "_operator: OperatorAccess" in block


def test_remaining_control_no_server_or_live_external_tokens():
    router = _read(ROUTER)
    forbidden = [
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "web" + "browser",
        "requ" + "ests.",
        "ht" + "tpx.",
        "place" + "Order",
        "submit_" + "order",
        "dry_run_only=False",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"remaining control router contains forbidden runtime tokens: {hits}"


_TESTS = [
    test_remaining_control_router_exists_and_is_included,
    test_remaining_control_routes_moved,
    test_remaining_control_posts_keep_operator_access,
    test_remaining_control_no_server_or_live_external_tokens,
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
