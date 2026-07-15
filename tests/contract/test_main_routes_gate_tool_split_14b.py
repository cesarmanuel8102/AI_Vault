"""Contract for gate and Tool01 permission route split 14B.

Static checks only. No runtime imports, no HTTP clients, no server startup.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/gate_tool_routes.py"

MOVED = {
    "post": [
        "/gate/approve/{pending_id}",
        "/gate/reject/{pending_id}",
        "/tool01/permission/approve",
    ],
    "get": [
        "/tool01/permission/pending/{session_id}",
        "/tool01/permission/grants/{session_id}",
    ],
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_gate_tool_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "gate_tool_routes_router" in main
    assert "app.include_router(gate_tool_routes_router)" in main
    assert "configure_active_sessions_provider(lambda: active_sessions)" in main


def test_gate_tool_routes_moved_with_methods_preserved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoints in MOVED.items():
        for endpoint in endpoints:
            assert f'@router.{method}("{endpoint}")' in router
            assert f'@app.{method}("{endpoint}")' not in main


def test_strict_operator_access_preserved_for_control_routes():
    router = _read(ROUTER)
    assert "require_strict_operator_access" in router
    assert "StrictOperatorAccess" in router
    for fn in [
        "gate_approve",
        "gate_reject",
        "tool01_permission_approve",
    ]:
        assert fn in router
    assert "_operator: StrictAccess" in router


def test_no_auth_bypass_or_secret_leak_tokens():
    router = _read(ROUTER)
    forbidden = [
        "allow_" + "all",
        "disable_" + "auth",
        "by" + "pass_auth",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"gate/tool router contains forbidden auth tokens: {hits}"
    assert "item.pop(\"approval_token\", None)" in router
    assert "item.pop(\"approval_secret\", None)" in router


def test_gate_tool_router_no_forbidden_domains():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9." + "main",
        "semantic_mem" + "ory",
        "fai" + "ss",
        "tr" + "ading",
        "uv" + "icorn",
        "requ" + "ests.",
        "ht" + "tpx.",
        "Test" + "Client",
        "os.s" + "ystem",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"gate/tool router contains forbidden domain tokens: {hits}"


_TESTS = [
    test_gate_tool_router_exists_and_is_included,
    test_gate_tool_routes_moved_with_methods_preserved,
    test_strict_operator_access_preserved_for_control_routes,
    test_no_auth_bypass_or_secret_leak_tokens,
    test_gate_tool_router_no_forbidden_domains,
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
