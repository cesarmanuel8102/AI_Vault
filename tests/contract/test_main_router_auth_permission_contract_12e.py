"""Static read-only contract for auth/permission surface mapping.

Front: FRONT-BRAIN-MAIN-ROUTERS-AUTH-PERMISSION-CONTRACT-12E

100% static: reads source files as text. No runtime imports,
no servers, no HTTP calls.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _assert_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{path} missing expected auth/permission tokens: {missing}"


# -- 1. Main.py auth/permission surfaces --

def test_main_auth_permission_surfaces_visible():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "StrictOperatorAccess",
        "require_strict_operator_access",
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
        "/tool01/permission/pending",
        "/tool01/permission/grants",
    )


# -- 2. Agent V2 API auth surfaces --

def test_agent_v2_auth_surfaces_visible():
    p = "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py"
    _assert_contains(p,
        "require_strict_operator_access",
        "operator",
        "/execute",
        "/runs",
        "/trace",
        "/agent",
    )


# -- 3. OpenAI compat auth surfaces --

def test_openai_compat_auth_surfaces_visible():
    p = "tmp_agent/brain_v9/api/openai_compat.py"
    _assert_contains(p,
        "require_strict_operator_access",
        "/chat/completions",
        "/models",
    )


# -- 4. Dashboard control surfaces --

def test_dashboard_control_surfaces_visible():
    p = "tmp_agent/brain_v9/dashboard/dashboard_routes.py"
    _assert_contains(p,
        "/run-once",
        "/pause",
        "/resume",
        "/stop",
        "/chat/stream",
        "/agent-v2",
    )


# -- 5. UI proxy mutation surfaces --

def test_ui_proxy_mutation_surfaces_visible():
    p = "tmp_agent/ui_proxy_server.py"
    _assert_contains(p,
        "/ui/api/apply",
        "/ui/api/reject",
        "/proxy/",
    )


# -- 6. Trading blocked and not imported --

def test_trading_blocked_and_not_imported():
    p = "tmp_agent/brain_v9/trading/router.py"
    _assert_contains(p,
        'prefix="/trading"',
        "/trade",
        "/policy",
        "/health",
    )
    self_src = _read("tests/contract/test_main_router_auth_permission_contract_12e.py")
    _tr = "tr" + "ading"
    forbidden = [
        "import" + " tmp_agent.brain_v9." + _tr,
        "from" + " tmp_agent.brain_v9." + _tr,
        "import" + " brain_v9." + _tr,
        "from" + " brain_v9." + _tr,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import trading: {hits}"


# -- 7. Self-check: no runtime imports --

def test_contract_no_runtime_imports():
    self_src = _read("tests/contract/test_main_router_auth_permission_contract_12e.py")
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
        _tc, _uv, _rq, _hx, _sub, _sys,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import runtime: {hits}"


# -- 8. Self-check: no runtime execution tokens --

def test_contract_no_runtime_execution_tokens():
    self_src = _read("tests/contract/test_main_router_auth_permission_contract_12e.py")
    _run = "uv" + "icorn.run("
    _tc = "Test" + "Client("
    _rq = "requ" + "ests."
    _hx = "ht" + "tpx."
    _sub = "sub" + "process.run("
    _sys = "os.s" + "ystem("
    forbidden = [_run, _tc, _rq, _hx, _sub, _sys]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not contain execution tokens: {hits}"


# -- 9. Self-check: no security-disabling tokens --

def test_contract_no_security_disabling_tokens():
    self_src = _read("tests/contract/test_main_router_auth_permission_contract_12e.py")
    _dry = "dry_run" + "_only=False"
    _dry2 = "dry_run" + "_only = False"
    _po = "place" + "Order"
    _so = "submit_" + "order"
    _aa = "allow_" + "all"
    _da = "disable_" + "auth"
    _bp = "by" + "pass"
    _gt = "GITHUB" + "_TOKEN"
    _ag = "api.git" + "hub.com"
    forbidden = [_dry, _dry2, _po, _so, _aa, _da, _bp, _gt, _ag]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not contain security-disabling tokens: {hits}"


_TESTS = [
    test_main_auth_permission_surfaces_visible,
    test_agent_v2_auth_surfaces_visible,
    test_openai_compat_auth_surfaces_visible,
    test_dashboard_control_surfaces_visible,
    test_ui_proxy_mutation_surfaces_visible,
    test_trading_blocked_and_not_imported,
    test_contract_no_runtime_imports,
    test_contract_no_runtime_execution_tokens,
    test_contract_no_security_disabling_tokens,
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