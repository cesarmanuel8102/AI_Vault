"""Static read-only contract for main router topology.

Front: FRONT-BRAIN-MAIN-ROUTERS-READONLY-CONTRACT-12B

This test is 100% static: it reads source files as text and checks for
expected topology tokens. It does NOT import runtime modules, start
servers, or make HTTP calls.

Purpose: lock the router/entrypoint inventory documented in
docs/audit/MAIN_ROUTER_TOPOLOGY_AUDIT_12A.md so accidental drift is
caught by CI.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _assert_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    missing = [t for t in tokens if t not in text]
    assert not missing, f"{path} missing expected tokens: {missing}"


def _assert_not_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    hits = [t for t in tokens if t in text]
    assert not hits, f"{path} contains forbidden tokens: {hits}"


# -- 1. Canonical main server entrypoint exists --

def test_canonical_main_server_entrypoint_exists():
    p = "tmp_agent/brain_v9/main.py"
    _uv_run = "uv" + "icorn.run"
    _assert_contains(p,
        "FastAPI(",
        "app = FastAPI",
        _uv_run,
        "include_router",
        "trading_router",
        "autonomy_router",
        "openai_compat_router",
        "agent_v2_router",
        "agent_v2_chat_router",
    )


# -- 2. Main router includes expected router surfaces --

def test_main_router_includes_expected_router_surfaces():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "app.include_router(trading_router)",
        "app.include_router(autonomy_router)",
        "app.include_router(openai_compat_router)",
        "app.include_router(agent_v2_router)",
        "app.include_router(agent_v2_chat_router)",
        "app.include_router(canary_lookup_read_only_router)",
        "app.include_router(knowledge_read_api_router)",
        "app.include_router(health_status_router)",
    )


# -- 3. Core HTTP surfaces are visible --

def test_core_http_surfaces_are_visible():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        '@app.post("/chat"',
        '@app.get("/health"',
        '@app.get("/status"',
        '@app.get("/healthz"',
        '@app.get("/dashboard"',
        '@app.get("/dashboard-v2"',
    )


# -- 4. High-risk mutation surfaces are explicit --

def test_high_risk_mutation_surfaces_are_explicit():
    p = "tmp_agent/brain_v9/main.py"
    _assert_contains(p,
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
        "/brain/mutations",
        "/rollback",
        "@app.delete(",
        "/sessions/{session_id}/memory",
    )


# -- 5. Agent V2 API surface contract --

def test_agent_v2_api_surface_contract():
    p = "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py"
    _assert_contains(p,
        "APIRouter",
        "/v2/agent",
        "/v2/chat",
        "require_strict_operator_access",
        "/capabilities",
        "/status",
        "/runs",
        "/execute",
        "/trace",
        "/agent",
    )


# -- 6. OpenAI compat surface contract --

def test_openai_compat_surface_contract():
    p = "tmp_agent/brain_v9/api/openai_compat.py"
    _assert_contains(p,
        "APIRouter",
        'prefix="/v1"',
        "/models",
        "/chat/completions",
        "require_strict_operator_access",
    )


# -- 7. Dashboard surface contract --

def test_dashboard_surface_contract():
    _assert_contains("tmp_agent/brain_v9/dashboard/dashboard_app.py",
        "FastAPI(",
        "include_router",
    )
    _assert_contains("tmp_agent/brain_v9/dashboard/dashboard_routes.py",
        "APIRouter",
        "/status",
        "/chat",
        "/chat/stream",
        "/agent-v2/status",
    )


# -- 8. UI proxy surface contract --

def test_ui_proxy_surface_contract():
    p = "tmp_agent/ui_proxy_server.py"
    _assert_contains(p,
        "FastAPI(",
        "/ui",
        "/healthz",
        "/proxy/{",
        "/ui/ollama_plan",
    )


# -- 9. Health and read-only routes contract --

def test_health_and_readonly_routes_contract():
    canary = "tmp_agent/brain_v9/routes/canary_lookup_read_only.py"
    knowledge = "tmp_agent/brain_v9/routes/knowledge_read_api.py"
    _assert_contains(canary, "APIRouter", "read-only", "/brain")
    _assert_contains(knowledge, "APIRouter", "/brain")
    # read-only routes must not have POST or DELETE handlers
    _assert_not_contains(canary, "@router.post(", "@router.delete(")
    _assert_not_contains(knowledge, "@router.post(", "@router.delete(")


# -- 10. Autonomy surface is explicitly controlled --

def test_autonomy_surface_is_explicitly_controlled():
    p = "tmp_agent/brain_v9/autonomy/router.py"
    _assert_contains(p,
        "APIRouter",
        "/status",
        "/cycle",
        "/reports",
        "/start",
        "/stop",
    )
    text = _read(p)
    assert "/start" in text, "autonomy /start control surface must be visible"
    assert "/stop" in text, "autonomy /stop control surface must be visible"


# -- 11. Trading surface remains blocked and separate --

def test_trading_surface_remains_blocked_and_separate():
    p = "tmp_agent/brain_v9/trading/router.py"
    _assert_contains(p,
        "APIRouter",
        'prefix="/trading"',
        "/health",
        "/policy",
        "/trade",
    )


# -- 12. Contract does not import runtime modules --

def test_contract_does_not_import_runtime_modules():
    self_src = _read("tests/contract/test_main_router_topology_contract_12b.py")
    # Build forbidden import tokens via concatenation to avoid self-match
    _m = "main" + " import"
    _tc = "Test" + "Client"
    _uv = "uv" + "icorn"
    _rq = "requ" + "ests"
    _hx = "ht" + "tpx"
    forbidden = [
        "from tmp_agent.brain_v9." + _m,
        "import tmp_agent.brain_v9." + _m,
        "from brain_v9." + _m,
        "import brain_v9." + _m,
        _tc,
        _uv,
        _rq,
        _hx,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract test must not import runtime: {hits}"


# -- 13. Forbidden runtime execution tokens absent from contract --

def test_forbidden_runtime_execution_tokens_absent_from_contract():
    self_src = _read("tests/contract/test_main_router_topology_contract_12b.py")
    # Build via concatenation to avoid self-match on the assertion strings
    _run = "uv" + "icorn.run("
    _sub = "sub" + "process.run("
    _sys = "os.s" + "ystem("
    _req = "requ" + "ests."
    _http = "ht" + "tpx."
    _tc = "Test" + "Client("
    forbidden = [_run, _sub, _sys, _req, _http, _tc]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract test must not contain runtime execution tokens: {hits}"


# -- Runner --

_TESTS = [
    test_canonical_main_server_entrypoint_exists,
    test_main_router_includes_expected_router_surfaces,
    test_core_http_surfaces_are_visible,
    test_high_risk_mutation_surfaces_are_explicit,
    test_agent_v2_api_surface_contract,
    test_openai_compat_surface_contract,
    test_dashboard_surface_contract,
    test_ui_proxy_surface_contract,
    test_health_and_readonly_routes_contract,
    test_autonomy_surface_is_explicitly_controlled,
    test_trading_surface_remains_blocked_and_separate,
    test_contract_does_not_import_runtime_modules,
    test_forbidden_runtime_execution_tokens_absent_from_contract,
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