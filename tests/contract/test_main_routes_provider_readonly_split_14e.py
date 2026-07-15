"""Contract for provider-backed read-only route split 14E."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/provider_readonly_routes.py"

MOVED_GET = [
    "/brain-dashboard/agent-v2/status",
    "/brain/operating-context",
    "/brain/maintenance/status",
]

DEFERRED_POST = [
    "/brain/maintenance/action",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_provider_readonly_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "provider_readonly_routes_router" in main
    assert "app.include_router(provider_readonly_routes_router)" in main


def test_provider_readonly_provider_configured_from_main():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "def configure_provider_readonly" in router
    assert "configure_provider_readonly(_build_brain_operating_context, _build_brain_maintenance_status)" in main
    assert "brain_v9.main" not in router


def test_provider_readonly_get_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_GET:
        assert f'@router.get("{endpoint}")' in router
        assert f'@app.get("{endpoint}")' not in main


def test_provider_readonly_mutating_maintenance_action_deferred():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in DEFERRED_POST:
        assert f'@app.post("{endpoint}")' in main
        assert endpoint not in router


def test_provider_readonly_no_mutating_handlers_or_bypass_tokens():
    router = _read(ROUTER)
    forbidden = [
        "@router.post(",
        "@router.delete(",
        "disable_" + "auth",
        "skip_" + "auth",
        "allow_" + "all",
        "dry_run_only=False",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"provider read-only router contains forbidden tokens: {hits}"


_TESTS = [
    test_provider_readonly_router_exists_and_is_included,
    test_provider_readonly_provider_configured_from_main,
    test_provider_readonly_get_routes_moved,
    test_provider_readonly_mutating_maintenance_action_deferred,
    test_provider_readonly_no_mutating_handlers_or_bypass_tokens,
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
