from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
ROUTER = ROOT / "tmp_agent" / "brain_v9" / "routes" / "chat_entrypoint_routes.py"
SERVICE = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_service.py"
REPORT = ROOT / "docs" / "audit" / "MAIN_ROUTER_CHAT_FINAL_MOVE_REPORT_15D.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_moved() -> bool:
    return '@app.post("/chat"' not in _read(MAIN) and '@router.post("/chat"' in _read(ROUTER)


def test_chat_route_moved_or_deferred_consistently():
    main = _read(MAIN)
    router = _read(ROUTER)
    report = _read(REPORT)
    final_report = _read(ROOT / "docs" / "audit" / "MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md")
    moved = _is_moved()
    if moved:
        assert '@app.post("/chat"' not in main
        assert '@router.post("/chat"' in router
        assert "PARTIALLY_COMPLETED_WITH_DEFERRED" in report
        assert "FULLY_COMPLETED_CHAT_ROUTE_MOVE" in final_report
    else:
        assert '@app.post("/chat"' in main
        assert '@router.post("/chat"' not in router
        assert "PARTIALLY_COMPLETED_WITH_DEFERRED" in report
        assert "dependency count still exceeds provider budget" in report


def test_provider_dependency_budget_or_deferred_reason_is_explicit():
    report = _read(REPORT)
    assert "Provider key count" in report
    assert "Dependency count before" in report
    assert "Dependency count after" in report
    if _is_moved():
        final_report = _read(ROOT / "docs" / "audit" / "MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md")
        assert "service boundary reused" in final_report
    else:
        assert "Provider key count: `not applicable`" in report
        assert "deferred to 15E" in report


def test_chat_response_contract_tokens_preserved():
    combined = _read(MAIN) + "\n" + _read(ROUTER) + "\n" + (_read(SERVICE) if SERVICE.exists() else "")
    for token in [
        "ChatResponse",
        "pending_action",
        "trace",
        "native",
        "timeout",
        "curated",
        "PAD",
        "GOD",
    ]:
        assert token in combined


def test_router_forbidden_imports_and_runtime_calls_absent():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core.session",
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
    for token in forbidden:
        assert token not in router


def test_no_endpoint_count_increase():
    main = _read(MAIN)
    endpoint_count = len(re.findall(r"@app\.(get|post|put|delete|patch)", main))
    if _is_moved():
        assert endpoint_count == 50
    else:
        assert endpoint_count == 51


def test_main_includes_chat_entrypoint_router():
    main = _read(MAIN)
    assert "chat_entrypoint_router" in main
    assert "app.include_router(chat_entrypoint_router)" in main
    assert "configure_chat_entrypoint_runtime_provider" in main


def test_no_runtime_data_mutation_tokens_introduced():
    combined = _read(MAIN) + "\n" + _read(ROUTER) + "\n" + (_read(SERVICE) if SERVICE.exists() else "")
    forbidden = [
        "dry_run_only=False",
        "promote_record",
        "faiss.write_index",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in forbidden:
        assert token not in combined


if __name__ == "__main__":
    test_chat_route_moved_or_deferred_consistently()
    test_provider_dependency_budget_or_deferred_reason_is_explicit()
    test_chat_response_contract_tokens_preserved()
    test_router_forbidden_imports_and_runtime_calls_absent()
    test_no_endpoint_count_increase()
    test_main_includes_chat_entrypoint_router()
    test_no_runtime_data_mutation_tokens_introduced()
    print("MAIN_ROUTES_CHAT_FINAL_MOVE_15D_OK")
