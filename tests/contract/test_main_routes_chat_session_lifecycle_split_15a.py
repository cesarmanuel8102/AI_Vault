"""Contract for chat/session lifecycle route split 15A."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

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
    assert '@router.delete("/sessions/{session_id}", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.delete("/sessions/{session_id}/memory", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.post("/agent")' in router
    assert '@router.post("/dev", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.get("/godmode/status", dependencies=[Depends(require_strict_operator_access)])' in router
    assert '@router.post("/godmode", dependencies=[Depends(require_strict_operator_access)])' in router


def test_provider_boundary_does_not_import_main_or_session_in_router():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core." + "session",
        "_GLOBAL_CHAT" + "_METRICS",
        "semantic_memory",
        "faiss",
        "trading",
        "place" + "Order",
        "submit" + "_order",
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
    import builtins
    import importlib.util
    import sys

    class _FakeAPIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def delete(self, *args, **kwargs):
            return lambda func: func

        def get(self, *args, **kwargs):
            return lambda func: func

        def post(self, *args, **kwargs):
            return lambda func: func

    class _FakeHTTPException(Exception):
        def __init__(self, status_code=500, detail=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _FakeBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    fastapi_stub = ModuleType("fastapi")
    fastapi_stub.APIRouter = _FakeAPIRouter
    fastapi_stub.Depends = lambda dependency=None, *args, **kwargs: dependency
    fastapi_stub.HTTPException = _FakeHTTPException

    pydantic_stub = ModuleType("pydantic")
    pydantic_stub.BaseModel = _FakeBaseModel
    pydantic_stub.ConfigDict = lambda **kwargs: dict(kwargs)

    agent_loop_stub = ModuleType("brain_v9.agent.loop")
    agent_loop_stub.AgentLoop = type("AgentLoop", (), {})

    agent_tools_stub = ModuleType("brain_v9.agent.tools")
    agent_tools_stub.build_standard_executor = lambda: object()

    api_security_stub = ModuleType("brain_v9.api_security")
    api_security_stub.StrictOperatorAccess = object
    api_security_stub.require_strict_operator_access = lambda: None

    stub_modules = {
        "fastapi": fastapi_stub,
        "pydantic": pydantic_stub,
        "brain_v9.agent.loop": agent_loop_stub,
        "brain_v9.agent.tools": agent_tools_stub,
        "brain_v9.api_security": api_security_stub,
    }
    previous_modules = {name: sys.modules.get(name) for name in stub_modules}
    previous_import = builtins.__import__

    def _contract_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in stub_modules:
            return stub_modules[name]
        return previous_import(name, globals, locals, fromlist, level)

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "tmp_agent"))
    try:
        sys.modules.update(stub_modules)
        builtins.__import__ = _contract_import
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
    finally:
        builtins.__import__ = previous_import
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


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
