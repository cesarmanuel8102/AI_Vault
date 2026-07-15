"""Contract for strategy read-only route split 14F."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/strategy_readonly_routes.py"

MOVED_GET = [
    "/brain/strategy-engine/summary",
    "/brain/strategy-engine/candidates",
    "/brain/strategy-engine/scorecards",
    "/brain/strategy-engine/ranking",
    "/brain/strategy-engine/ranking-v2",
    "/brain/strategy-engine/features",
    "/brain/strategy-engine/history",
    "/brain/strategy-engine/signals",
    "/brain/strategy-engine/archive",
    "/brain/strategy-engine/expectancy",
    "/brain/strategy-engine/expectancy/by-strategy",
    "/brain/strategy-engine/expectancy/by-venue",
    "/brain/strategy-engine/expectancy/by-symbol",
    "/brain/strategy-engine/expectancy/by-context",
    "/brain/strategy-engine/edge-validation",
    "/brain/strategy-engine/context-edge-validation",
    "/brain/strategy-engine/active-catalog",
    "/brain/strategy-engine/pipeline-integrity",
    "/brain/strategy-engine/post-trade-analysis",
    "/brain/strategy-engine/post-trade-hypotheses",
    "/brain/strategy-engine/learning-loop",
    "/brain/strategy-engine/hypotheses",
    "/brain/strategy-engine/execution-audit",
    "/brain/strategy-engine/adaptation-state",
    "/brain/strategy-engine/session-performance",
]

DEFERRED_POST = [
    "/brain/strategy-engine/simulation-gate/{strategy_id}",
    "/brain/strategy-engine/refresh",
    "/brain/strategy-engine/execute-top-candidate",
    "/brain/strategy-engine/execute-candidate/{strategy_id}",
    "/brain/strategy-engine/execute-batch/{strategy_id}",
    "/brain/strategy-engine/execute-comparison-cycle",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_strategy_readonly_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "strategy_readonly_routes_router" in main
    assert "app.include_router(strategy_readonly_routes_router)" in main


def test_strategy_readonly_get_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for endpoint in MOVED_GET:
        assert f'@router.get("{endpoint}")' in router
        assert f'@app.get("{endpoint}")' not in main


def test_strategy_mutating_posts_deferred_in_main():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "@router.post(" not in router
    for endpoint in DEFERRED_POST:
        assert f'@app.post("{endpoint}")' in main
        assert endpoint not in router


def test_strategy_readonly_router_no_order_execution_tokens():
    router = _read(ROUTER)
    forbidden = [
        "place" + "Order",
        "submit_" + "order",
        "dry_run_only=False",
        "Interactive" + "Brokers",
        "IB" + "KR",
        "live_" + "trading",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"strategy read-only router contains forbidden execution tokens: {hits}"


_TESTS = [
    test_strategy_readonly_router_exists_and_is_included,
    test_strategy_readonly_get_routes_moved,
    test_strategy_mutating_posts_deferred_in_main,
    test_strategy_readonly_router_no_order_execution_tokens,
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
