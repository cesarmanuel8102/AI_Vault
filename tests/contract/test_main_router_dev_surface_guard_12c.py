"""Static read-only contract guarding dev/debug/control surfaces.

Front: FRONT-BRAIN-MAIN-ROUTERS-DEV-SURFACE-GUARD-12C

This test is 100% static: it reads source files as text and checks for
expected high-risk surface tokens. It does NOT import runtime modules,
start servers, or make HTTP calls.

Purpose: ensure dev/debug/mutation/control endpoints remain explicit
and detectable, preventing accidental camouflage or silent removal.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _assert_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{path} missing expected dev/control surface tokens: {missing}"


def _assert_not_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    hits = [t for t in tokens if t in text]
    assert not hits, f"{path} contains forbidden tokens: {hits}"


# -- 1. Main dev/debug surfaces remain explicit --

def test_main_dev_debug_surfaces_remain_explicit():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "/brain/maintenance/action",
        "/brain/mutations",
        "/brain/mutations/test_apply",
        "/brain/mutations/{",
        "/rollback",
    )
    _assert_contains(
        "tmp_agent/brain_v9/routes/chat_entrypoint_routes.py",
        "/chat/introspectivo/debug",
    )
    _assert_contains(
        "tmp_agent/brain_v9/routes/provider_readonly_routes.py",
        "/brain/maintenance/status",
    )


# -- 2. Gate and permission surfaces remain explicit --

def test_gate_and_permission_surfaces_remain_explicit():
    p = "tmp_agent/brain_v9/routes/gate_tool_routes.py"
    _assert_contains(p,
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
        "/tool01/permission/pending",
        "/tool01/permission/grants",
    )
    # GAK render functions live in governed_action_kernel, not main.py;
    # verify they exist there so the permission surface stays traceable.
    _assert_contains("tmp_agent/brain_v9/core/governed_action_kernel.py",
        "render_permission_request",
        "render_policy_block",
    )


# -- 3. Memory mutation surfaces remain explicit --

def test_memory_mutation_surfaces_remain_explicit():
    p = "tmp_agent/brain_v9/routes/chat_session_lifecycle_routes.py"
    _assert_contains(p,
        "@router.delete",
        "/sessions/{session_id}",
        "/sessions/{session_id}/memory",
    )


# -- 4. Agent execute surface remains operator-controlled --

def test_agent_execute_surface_remains_operator_controlled():
    p = "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py"
    _assert_contains(p,
        "/execute",
        "/runs",
        "/trace",
        "require_strict_operator_access",
        "operator",
    )


# -- 5. Autonomy control surfaces are visible --

def test_autonomy_control_surfaces_are_visible():
    p = "tmp_agent/brain_v9/autonomy/router.py"
    _assert_contains(p,
        "/start",
        "/stop",
        "/reports",
        "/cycle",
        "@router.post",
        "@router.get",
    )


# -- 6. Dashboard control surfaces are visible --

def test_dashboard_control_surfaces_are_visible():
    p = "tmp_agent/brain_v9/dashboard/dashboard_routes.py"
    _assert_contains(p,
        "/chat",
        "/chat/stream",
        "/agent-v2",
        "/run-once",
        "/pause",
        "/resume",
        "/stop",
    )


# -- 7. UI proxy mutation surfaces are visible --

def test_ui_proxy_mutation_surfaces_are_visible():
    p = "tmp_agent/ui_proxy_server.py"
    _assert_contains(p,
        "/ui/api/apply",
        "/ui/api/reject",
        "/proxy/",
        "/ui/ollama_plan",
    )


# -- 8. Trading surface is blocked and not part of nontrading contract --

def test_trading_surface_is_blocked_and_not_part_of_nontrading_contract():
    p = "tmp_agent/brain_v9/trading/router.py"
    _assert_contains(p,
        'prefix="/trading"',
        "/trade",
        "/health",
        "/policy",
    )
    # Contract must not import or execute trading
    self_src = _read("tests/contract/test_main_router_dev_surface_guard_12c.py")
    _tr = "tr" + "ading"
    _imp = "import" + " tmp_agent.brain_v9." + _tr
    _from = "from" + " tmp_agent.brain_v9." + _tr
    _imp2 = "import" + " brain_v9." + _tr
    _from2 = "from" + " brain_v9." + _tr
    forbidden = [_imp, _from, _imp2, _from2]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import trading: {hits}"


# -- 9. No runtime imports in contract --

def test_no_runtime_imports_in_contract():
    self_src = _read("tests/contract/test_main_router_dev_surface_guard_12c.py")
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


# -- 10. No runtime execution tokens in contract --

def test_no_runtime_execution_tokens_in_contract():
    self_src = _read("tests/contract/test_main_router_dev_surface_guard_12c.py")
    _run = "uv" + "icorn.run("
    _tc = "Test" + "Client("
    _rq = "requ" + "ests."
    _hx = "ht" + "tpx."
    _sub = "sub" + "process.run("
    _sys = "os.s" + "ystem("
    forbidden = [_run, _tc, _rq, _hx, _sub, _sys]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not contain runtime execution tokens: {hits}"


# -- 11. Contract does not expand allowed runtime --

def test_dev_surface_contract_does_not_expand_allowed_runtime():
    self_src = _read("tests/contract/test_main_router_dev_surface_guard_12c.py")
    _dry = "dry_run" + "_only=False"
    _dry2 = "dry_run" + "_only = False"
    _po = "place" + "Order"
    _so = "submit_" + "order"
    _aa = "allow_" + "all"
    _da = "disable_" + "auth"
    _bp = "by" + "pass"
    forbidden = [_dry, _dry2, _po, _so, _aa, _da, _bp]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not contain security-disabling tokens: {hits}"


# -- Runner --

_TESTS = [
    test_main_dev_debug_surfaces_remain_explicit,
    test_gate_and_permission_surfaces_remain_explicit,
    test_memory_mutation_surfaces_remain_explicit,
    test_agent_execute_surface_remains_operator_controlled,
    test_autonomy_control_surfaces_are_visible,
    test_dashboard_control_surfaces_are_visible,
    test_ui_proxy_mutation_surfaces_are_visible,
    test_trading_surface_is_blocked_and_not_part_of_nontrading_contract,
    test_no_runtime_imports_in_contract,
    test_no_runtime_execution_tokens_in_contract,
    test_dev_surface_contract_does_not_expand_allowed_runtime,
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
