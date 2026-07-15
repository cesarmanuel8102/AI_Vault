"""Contract for chat entrypoint route split 15B."""
from __future__ import annotations

from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
ROUTER = "tmp_agent/brain_v9/routes/chat_entrypoint_routes.py"
REPORT = "docs/audit/MAIN_ROUTER_CHAT_ENTRYPOINT_REPORT_15B.md"

MOVED = [
    ("post", "/chat"),
    ("get", "/chat/introspectivo/debug"),
    ("post", "/chat/introspectivo"),
]

FORMERLY_DEFERRED = "/chat"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")


def test_chat_entrypoint_router_file_exists():
    router = _read(ROUTER)
    assert "APIRouter" in router
    assert "router = APIRouter" in router
    assert "def configure_chat_entrypoint_runtime_provider" in router
    assert "def _chat_runtime" in router


def test_main_includes_chat_entrypoint_router():
    main = _read("tmp_agent/brain_v9/main.py")
    assert "chat_entrypoint_router" in main
    assert "app.include_router(chat_entrypoint_router)" in main
    assert "configure_chat_entrypoint_runtime_provider" in main


def test_moved_chat_routes_live_in_router():
    router = _read(ROUTER)
    for method, endpoint in MOVED:
        assert f'@router.{method}("{endpoint}"' in router


def test_moved_chat_routes_no_longer_in_main():
    main = _read("tmp_agent/brain_v9/main.py")
    for method, endpoint in MOVED:
        assert f'@app.{method}("{endpoint}"' not in main


def test_deferred_chat_routes_documented():
    main = _read("tmp_agent/brain_v9/main.py")
    router = _read(ROUTER)
    assert f'@app.post("{FORMERLY_DEFERRED}"' not in main
    assert f'@router.post("{FORMERLY_DEFERRED}"' in router
    report = _read(REPORT)
    assert "POST /chat" in report
    assert "deferred" in report.lower()
    assert "dependency budget" in report.lower()
    final_report = _read("docs/audit/MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md")
    assert "FULLY_COMPLETED_CHAT_ROUTE_MOVE" in final_report


def test_router_provider_boundary_forbidden_imports():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core." + "session",
        "semantic_memory_faiss",
        "faiss.write_index",
        "faiss.add",
        "trading",
        "place" + "Order",
        "submit" + "_order",
        "requ" + "ests.",
        "ht" + "tpx.",
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
    ]
    hits = [token for token in forbidden if token in router]
    assert not hits, f"chat entrypoint router contains forbidden boundary tokens: {hits}"


def test_no_live_execution_tokens_in_contract_or_router():
    combined = _read(ROUTER) + "\n" + _read("tests/contract/test_main_routes_chat_entrypoint_split_15b.py")
    forbidden = [
        "Test" + "Client",
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "requ" + "ests.",
        "ht" + "tpx.",
        "place" + "Order",
        "submit" + "_order",
    ]
    hits = [token for token in forbidden if token in combined]
    assert not hits, f"contract/router contains forbidden live execution tokens: {hits}"


def test_provider_can_be_configured_with_fake_runtime():
    import builtins
    import importlib.util
    import sys

    class _FakeAPIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda func: func

        def post(self, *args, **kwargs):
            return lambda func: func

    class _FakeBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    fastapi_stub = ModuleType("fastapi")
    fastapi_stub.APIRouter = _FakeAPIRouter

    pydantic_stub = ModuleType("pydantic")
    pydantic_stub.BaseModel = _FakeBaseModel

    api_security_stub = ModuleType("brain_v9.api_security")
    api_security_stub.StrictOperatorAccess = object

    stub_modules = {
        "fastapi": fastapi_stub,
        "pydantic": pydantic_stub,
        "brain_v9.api_security": api_security_stub,
    }
    previous_modules = {name: sys.modules.get(name) for name in stub_modules}
    previous_import = builtins.__import__
    original_sys_path = list(sys.path)
    module_name = "chat_entrypoint_routes_contract_probe"

    def _contract_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in stub_modules:
            return stub_modules[name]
        return previous_import(name, globals, locals, fromlist, level)

    try:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "tmp_agent"))
        sys.modules.update(stub_modules)
        builtins.__import__ = _contract_import
        spec = importlib.util.spec_from_file_location(module_name, ROOT / ROUTER)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        fake_runtime = {"active_sessions": {}, "get_or_create_session": object(), "system_identity": "id"}
        module.configure_chat_entrypoint_runtime_provider(lambda: fake_runtime)
        assert module._chat_runtime() is fake_runtime
    finally:
        builtins.__import__ = previous_import
        sys.path[:] = original_sys_path
        sys.modules.pop(module_name, None)
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def test_dependency_budget_recorded():
    report = _read(REPORT)
    assert "POST /chat dependency count: 27" in report
    assert "provider dependency count for moved introspective routes: 3" in report
    assert "PARTIALLY_COMPLETED_WITH_DEFERRED" in report
    final_report = _read("docs/audit/MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md")
    assert "service boundary reused" in final_report


_TESTS = [
    test_chat_entrypoint_router_file_exists,
    test_main_includes_chat_entrypoint_router,
    test_moved_chat_routes_live_in_router,
    test_moved_chat_routes_no_longer_in_main,
    test_deferred_chat_routes_documented,
    test_router_provider_boundary_forbidden_imports,
    test_no_live_execution_tokens_in_contract_or_router,
    test_provider_can_be_configured_with_fake_runtime,
    test_dependency_budget_recorded,
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
