"""Static read-only contract for side-effect boundary mapping.

Front: FRONT-BRAIN-MAIN-ROUTERS-SIDE-EFFECT-BOUNDARY-CONTRACT-12F

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
    assert not missing, f"{path} missing expected side-effect boundary tokens: {missing}"


def _assert_not_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    hits = [t for t in tokens if t in text]
    assert not hits, f"{path} contains forbidden mutating handler tokens: {hits}"


# -- 1. Main mutation/side-effect tokens --

def test_main_mutation_side_effects_explicit():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "@app.post",
        "@app.delete",
        "/brain/mutations",
        "/brain/mutations/test_apply",
        "/rollback",
        "/sessions/{session_id}/memory",
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
    )


# -- 2. Autonomy side-effect/control --

def test_autonomy_side_effects_explicit():
    p = "tmp_agent/brain_v9/autonomy/router.py"
    _assert_contains(p,
        "/start",
        "/stop",
        "@router.post",
    )


# -- 3. Agent execution side-effect --

def test_agent_execution_side_effects_explicit():
    p = "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py"
    _assert_contains(p,
        "/execute",
        "/runs",
        "@router.post",
    )


# -- 4. Dashboard control side-effects --

def test_dashboard_control_side_effects_explicit():
    p = "tmp_agent/brain_v9/dashboard/dashboard_routes.py"
    _assert_contains(p,
        "/run-once",
        "/pause",
        "/resume",
        "/stop",
        "/chat",
        "/chat/stream",
    )


# -- 5. UI proxy mutation --

def test_ui_proxy_mutation_side_effects_explicit():
    p = "tmp_agent/ui_proxy_server.py"
    _assert_contains(p,
        "/ui/api/apply",
        "/ui/api/reject",
        "@app.post",
    )


# -- 6. Read-only routes must not have mutating handlers --

def test_read_only_routes_no_mutating_handlers():
    for path in [
        "tmp_agent/brain_v9/routes/canary_lookup_read_only.py",
        "tmp_agent/brain_v9/routes/knowledge_read_api.py",
    ]:
        _assert_not_contains(path,
            "@router.post(",
            "@router.delete(",
            "@router.put(",
            "@router.patch(",
        )


# -- 7. Self-check: no runtime imports --

def test_contract_no_runtime_imports():
    self_src = _read("tests/contract/test_main_router_side_effect_boundary_12f.py")
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
    self_src = _read("tests/contract/test_main_router_side_effect_boundary_12f.py")
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
    self_src = _read("tests/contract/test_main_router_side_effect_boundary_12f.py")
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


_TESTS = [
    test_main_mutation_side_effects_explicit,
    test_autonomy_side_effects_explicit,
    test_agent_execution_side_effects_explicit,
    test_dashboard_control_side_effects_explicit,
    test_ui_proxy_mutation_side_effects_explicit,
    test_read_only_routes_no_mutating_handlers,
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