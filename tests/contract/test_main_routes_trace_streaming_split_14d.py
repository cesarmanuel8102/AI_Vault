"""Contract for agent trace/streaming route split 14D."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/trace_streaming_routes.py"

MOVED = [
    ("post", "/brain/agent-trace/event"),
    ("get", "/brain/agent-trace/latest"),
    ("get", "/brain/agent-trace/stream"),
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_trace_streaming_router_exists_and_is_included():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "trace_streaming_routes_router" in main
    assert "app.include_router(trace_streaming_routes_router)" in main
    assert "_emit_agent_trace_internal" in main


def test_trace_streaming_routes_moved():
    router = _read(ROUTER)
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoint in MOVED:
        assert f'@router.{method}("{endpoint}")' in router
        assert f'@app.{method}("{endpoint}")' not in main


def test_trace_streaming_guards_preserved():
    router = _read(ROUTER)
    assert "_operator: StrictOperatorAccess" in router
    assert "_operator: OperatorAccess" in router
    assert "raw_chain_of_thought" in router
    assert "private_reasoning" in router


def test_trace_streaming_no_runtime_launch_or_live_http_tokens():
    router = _read(ROUTER)
    forbidden = [
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "web" + "browser",
        "requ" + "ests.",
        "ht" + "tpx.",
        "place" + "Order",
        "submit_" + "order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"trace router contains forbidden runtime tokens: {hits}"


_TESTS = [
    test_trace_streaming_router_exists_and_is_included,
    test_trace_streaming_routes_moved,
    test_trace_streaming_guards_preserved,
    test_trace_streaming_no_runtime_launch_or_live_http_tokens,
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
