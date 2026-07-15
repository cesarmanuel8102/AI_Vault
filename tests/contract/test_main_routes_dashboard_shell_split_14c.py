"""Contract for dashboard shell route split 14C.

Static checks only. No dashboard startup, browser, subprocess, HTTP client, or
FastAPI app import.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/dashboard_shell_routes.py"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_dashboard_shell_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "dashboard_shell_routes_router" in main
    assert "app.include_router(dashboard_shell_routes_router)" in main
    assert "configure_dashboard_html_path(lambda: _dashboard_html)" in main


def test_dashboard_shell_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in ["/dashboard", "/dashboard-v2"]:
        assert f'@router.get("{endpoint}"' in router
        assert f'@app.get("{endpoint}"' not in main


def test_dashboard_shell_no_runtime_start_or_browser():
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
    assert not hits, f"dashboard shell router contains forbidden tokens: {hits}"


_TESTS = [
    test_dashboard_shell_router_exists_and_is_included,
    test_dashboard_shell_routes_moved,
    test_dashboard_shell_no_runtime_start_or_browser,
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
