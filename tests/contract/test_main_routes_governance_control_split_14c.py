"""Contract for governance/control route split 14C."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/governance_control_routes.py"

MOVED_GET = [
    "/brain/meta-governance/status",
    "/brain/change-control/scorecard",
    "/brain/control-layer/status",
    "/brain/purpose/status",
    "/brain/consciousness/status",
]

MOVED_POST = [
    "/brain/purpose/refresh",
    "/brain/control-layer/freeze",
    "/brain/control-layer/unfreeze",
    "/brain/self-improvement/change",
    "/brain/self-improvement/change/{change_id}/validate",
    "/brain/self-improvement/change/{change_id}/promote",
    "/brain/self-improvement/change/{change_id}/rollback",
    "/brain/validate",
]

DEFERRED = [
    "/godmode/status",
    "/godmode",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_governance_control_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "governance_control_routes_router" in main
    assert "app.include_router(governance_control_routes_router)" in main


def test_governance_control_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_GET:
        assert f'@router.get("{endpoint}")' in router
        assert f'@app.get("{endpoint}")' not in main
    for endpoint in MOVED_POST:
        assert f'@router.post("{endpoint}")' in router
        assert f'@app.post("{endpoint}")' not in main


def test_governance_control_posts_preserve_operator_access():
    router = _read(ROUTER)
    for endpoint in MOVED_POST:
        decorator = f'@router.post("{endpoint}")'
        pos = router.index(decorator)
        next_decorator = router.find("\n@router.", pos + len(decorator))
        block = router[pos:] if next_decorator == -1 else router[pos:next_decorator]
        assert "_operator: OperatorAccess" in block


def test_godmode_deferred_in_main():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in DEFERRED:
        assert endpoint not in router
    assert '@app.get("/godmode/status", dependencies=[Depends(require_strict_operator_access)])' in main
    assert '@app.post("/godmode", dependencies=[Depends(require_strict_operator_access)])' in main


def test_governance_control_router_no_auth_bypass_tokens():
    router = _read(ROUTER)
    forbidden = [
        "allow_" + "all",
        "disable_" + "auth",
        "skip_" + "auth",
        "always_" + "allow",
        "dry_run_only=False",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"governance router contains forbidden tokens: {hits}"


_TESTS = [
    test_governance_control_router_exists_and_is_included,
    test_governance_control_routes_moved,
    test_governance_control_posts_preserve_operator_access,
    test_godmode_deferred_in_main,
    test_governance_control_router_no_auth_bypass_tokens,
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
