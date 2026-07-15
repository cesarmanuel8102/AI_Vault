"""Contract for chat/session lifecycle route split 15A."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/chat_session_lifecycle_routes.py"

MOVED = [
    ("delete", "/sessions/{session_id}"),
    ("delete", "/sessions/{session_id}/memory"),
    ("post", "/agent"),
    ("post", "/dev"),
    ("get", "/godmode/status"),
    ("post", "/godmode"),
]

DEFERRED = {
    "/chat": "primary BrainSession route has large PAD/GOD/chat runtime dependency graph; defer to dedicated chat entrypoint front",
    "/chat/introspectivo": "introspective orchestrator route remains paired with ChatRequest/ChatResponse flow",
    "/chat/introspectivo/debug": "debug shell remains with introspective orchestrator helper",
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_chat_session_router_file_exists():
    router = _read(ROUTER)
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "def configure_active_sessions_provider" in router
    assert "def configure_chat_runtime_provider" in router


def test_main_includes_chat_session_router():
    main = _read("tmp_agent/brain_v9/main.py")
    assert "chat_session_lifecycle_routes_router" in main
    assert "app.include_router(chat_session_lifecycle_routes_router)" in main
    assert "configure_chat_active_sessions_provider(lambda: active_sessions)" in main
    assert "configure_chat_runtime_provider(_chat_session_runtime_payload)" in main


def test_moved_session_routes_live_in_router():
    router = _read(ROUTER)
    for method, endpoint in MOVED:
        assert f'@router.{method}("{endpoint}"' in router


def test_moved_session_routes_no_longer_in_main():
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoint in MOVED:
        assert f'@app.{method}("{endpoint}")' not in main


def test_session_routes_preserve_methods():
    router = _read(ROUTER)
    assert '@router.delete("/sessions/{session_id}")' in router
    assert '@router.delete("/sessions/{session_id}/memory")' in router
    assert '@router.post("/agent")' in router
    assert '@router.post("/dev", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.get("/godmode/status", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.post("/godmode", dependencies=[Depends(require_strict_operator_access)])' in router


def test_provider_boundary_does_not_import_main_or_session_in_router():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core.session",
        "_GLOBAL_CHAT_METRICS",
        "semantic_memory",
        "faiss",
        "trading",
        "placeOrder",
        "submit_order",
    ]
    hits = [t for t in forbidden if t in router]
    assert not hits, f"chat session router contains forbidden boundary tokens: {hits}"


def test_no_live_execution_tokens_in_contract_or_router():
    combined = _read(ROUTER) + "\n" + _read("tests/contract/test_main_routes_chat_session_lifecycle_split_15a.py")
    forbidden = [
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "requ" + "ests.",
        "ht" + "tpx.",
        "Test" + "Client",
        "place" + "_Order",
        "submit-" + "order",
    ]
    hits = [t for t in forbidden if t in combined]
    assert not hits, f"contract/router contains forbidden live execution tokens: {hits}"


def test_deferred_routes_are_documented_and_remain_in_main():
    main = _read("tmp_agent/brain_v9/main.py")
    router = _read(ROUTER)
    for endpoint, reason in DEFERRED.items():
        assert reason
        assert endpoint in main
        assert f'@router.post("{endpoint}"' not in router
        assert f'@router.get("{endpoint}"' not in router


def test_provider_can_be_configured_with_fake_sessions():
    import importlib.util
    import sys

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tmp_agent"))
    spec = importlib.util.spec_from_file_location(
        "chat_session_lifecycle_routes_contract_probe",
        ROOT / ROUTER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    fake_sessions = {"default": object()}
    fake_runtime = {"ok": True}
    module.configure_active_sessions_provider(lambda: fake_sessions)
    module.configure_chat_runtime_provider(lambda: fake_runtime)
    assert module._active_sessions() is fake_sessions
    assert module._chat_runtime() is fake_runtime


_TESTS = [
    test_chat_session_router_file_exists,
    test_main_includes_chat_session_router,
    test_moved_session_routes_live_in_router,
    test_moved_session_routes_no_longer_in_main,
    test_session_routes_preserve_methods,
    test_provider_boundary_does_not_import_main_or_session_in_router,
    test_no_live_execution_tokens_in_contract_or_router,
    test_deferred_routes_are_documented_and_remain_in_main,
    test_provider_can_be_configured_with_fake_sessions,
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
