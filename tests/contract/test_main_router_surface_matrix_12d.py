"""Static read-only surface matrix contract for main router topology.

Front: FRONT-BRAIN-MAIN-ROUTERS-READONLY-SURFACE-MATRIX-12D

This test is 100% static: it reads source files as text and validates
that endpoint surfaces remain classified in their expected categories.
It does NOT import runtime modules, start servers, or make HTTP calls.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def _flatten(matrix: dict[str, list[str]]) -> set[str]:
    out: set[str] = set()
    for tokens in matrix.values():
        out.update(tokens)
    return out


def _assert_matrix_present(matrix: dict[str, list[str]]) -> None:
    for path, tokens in matrix.items():
        text = _read(path)
        missing = [t for t in tokens if t not in text]
        assert not missing, f"{path} missing matrix tokens: {missing}"


def _assert_not_contains(path: str, *tokens: str) -> None:
    text = _read(path)
    hits = [t for t in tokens if t in text]
    assert not hits, f"{path} contains forbidden tokens: {hits}"


# ── Surface matrices ──────────────────────────────────────────────

READ_ONLY_SURFACES: dict[str, list[str]] = {
    "tmp_agent/brain_v9/main.py": [
        "/health",
        "/status",
        "/healthz",
        "/brain/health",
        "/brain/security/posture",
        "/brain/risk/status",
        "/brain/governance/health",
        "/brain/metrics",
        "/brain/validators",
        "/tools/coverage",
    ],
    "tmp_agent/brain_v9/routes/canary_lookup_read_only.py": [
        "APIRouter",
    ],
    "tmp_agent/brain_v9/routes/knowledge_read_api.py": [
        "APIRouter",
    ],
}

CONTROL_SURFACES: dict[str, list[str]] = {
    "tmp_agent/brain_v9/main.py": [
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
        "/tool01/permission/pending",
        "/tool01/permission/grants",
    ],
    "tmp_agent/brain_v9/autonomy/router.py": [
        "/start",
        "/stop",
    ],
    "tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py": [
        "/execute",
        "/runs",
        "/trace",
    ],
    "tmp_agent/brain_v9/dashboard/dashboard_routes.py": [
        "/run-once",
        "/pause",
        "/resume",
        "/stop",
    ],
}

MUTATION_SURFACES: dict[str, list[str]] = {
    "tmp_agent/brain_v9/main.py": [
        "@app.delete",
        "/sessions/{session_id}/memory",
        "/brain/mutations",
        "/brain/mutations/test_apply",
        "/rollback",
    ],
    "tmp_agent/ui_proxy_server.py": [
        "/ui/api/apply",
        "/ui/api/reject",
    ],
}

DEV_DEBUG_SURFACES: dict[str, list[str]] = {
    "tmp_agent/brain_v9/main.py": [
        "/chat/introspectivo/debug",
        "/brain/maintenance/status",
        "/brain/maintenance/action",
    ],
}

BLOCKED_TRADING_SURFACES: dict[str, list[str]] = {
    "tmp_agent/brain_v9/trading/router.py": [
        'prefix="/trading"',
        "/trade",
        "/policy",
        "/health",
    ],
}

# Tokens that must NEVER appear in READ_ONLY
_MUTATION_INDICATORS = [
    "/approve", "/reject", "/delete", "/rollback",
    "/test_apply", "/trade", "/start", "/stop",
]


# ── Tests ────────────────────────────────────────────────────────

def test_read_only_surface_matrix_is_present():
    _assert_matrix_present(READ_ONLY_SURFACES)


def test_control_surface_matrix_is_present():
    _assert_matrix_present(CONTROL_SURFACES)


def test_mutation_surface_matrix_is_present():
    _assert_matrix_present(MUTATION_SURFACES)


def test_dev_debug_surface_matrix_is_present():
    _assert_matrix_present(DEV_DEBUG_SURFACES)


def test_blocked_trading_surface_matrix_is_present_but_not_executed():
    _assert_matrix_present(BLOCKED_TRADING_SURFACES)
    self_src = _read("tests/contract/test_main_router_surface_matrix_12d.py")
    _tr = "tr" + "ading"
    forbidden = [
        "import" + " tmp_agent.brain_v9." + _tr,
        "from" + " tmp_agent.brain_v9." + _tr,
        "import" + " brain_v9." + _tr,
        "from" + " brain_v9." + _tr,
    ]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not import trading: {hits}"


def test_read_only_route_files_do_not_define_mutating_handlers():
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


def test_surface_categories_are_disjoint_by_intent():
    ro_tokens = _flatten(READ_ONLY_SURFACES)
    for indicator in _MUTATION_INDICATORS:
        assert indicator not in ro_tokens, (
            f"READ_ONLY must not contain mutation indicator: {indicator}"
        )


def test_high_risk_surfaces_have_explicit_category():
    high_risk = [
        "/gate/approve",
        "/gate/reject",
        "/tool01/permission/approve",
        "/brain/mutations",
        "/rollback",
        "/chat/introspectivo/debug",
        "/start",
        "/stop",
        "/execute",
        "/trade",
    ]
    control = _flatten(CONTROL_SURFACES)
    mutation = _flatten(MUTATION_SURFACES)
    dev_debug = _flatten(DEV_DEBUG_SURFACES)
    trading = _flatten(BLOCKED_TRADING_SURFACES)
    non_readonly = control | mutation | dev_debug | trading
    for token in high_risk:
        assert token in non_readonly, (
            f"high-risk token {token} must be in CONTROL, MUTATION, DEV_DEBUG, or BLOCKED_TRADING"
        )
    ro = _flatten(READ_ONLY_SURFACES)
    for token in high_risk:
        assert token not in ro, (
            f"high-risk token {token} must NOT be in READ_ONLY"
        )


def test_contract_does_not_import_runtime_modules():
    self_src = _read("tests/contract/test_main_router_surface_matrix_12d.py")
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


def test_contract_has_no_runtime_execution_tokens():
    self_src = _read("tests/contract/test_main_router_surface_matrix_12d.py")
    _run = "uv" + "icorn.run("
    _tc = "Test" + "Client("
    _rq = "requ" + "ests."
    _hx = "ht" + "tpx."
    _sub = "sub" + "process.run("
    _sys = "os.s" + "ystem("
    forbidden = [_run, _tc, _rq, _hx, _sub, _sys]
    hits = [t for t in forbidden if t in self_src]
    assert not hits, f"contract must not contain runtime execution tokens: {hits}"


def test_contract_does_not_expand_runtime_authority():
    self_src = _read("tests/contract/test_main_router_surface_matrix_12d.py")
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


# ── Runner ───────────────────────────────────────────────────────

_TESTS = [
    test_read_only_surface_matrix_is_present,
    test_control_surface_matrix_is_present,
    test_mutation_surface_matrix_is_present,
    test_dev_debug_surface_matrix_is_present,
    test_blocked_trading_surface_matrix_is_present_but_not_executed,
    test_read_only_route_files_do_not_define_mutating_handlers,
    test_surface_categories_are_disjoint_by_intent,
    test_high_risk_surfaces_have_explicit_category,
    test_contract_does_not_import_runtime_modules,
    test_contract_has_no_runtime_execution_tokens,
    test_contract_does_not_expand_runtime_authority,
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