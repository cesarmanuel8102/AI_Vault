from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
ROUTER = ROOT / "tmp_agent" / "brain_v9" / "routes" / "chat_entrypoint_routes.py"
SERVICE = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_service.py"
REPORT = ROOT / "docs" / "audit" / "MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_chat_route_no_longer_in_main():
    assert '@app.post("/chat"' not in _read(MAIN)


def test_chat_route_lives_in_router():
    router = _read(ROUTER)
    assert '@router.post("/chat", response_model=ChatResponse)' in router


def test_main_includes_chat_entrypoint_router():
    main = _read(MAIN)
    assert "chat_entrypoint_router" in main
    assert "app.include_router(chat_entrypoint_router)" in main


def test_runtime_provider_registered():
    main = _read(MAIN)
    assert "configure_chat_entrypoint_runtime_provider" in main
    assert "configure_chat_service_runtime_provider" in main
    assert "_build_chat_entrypoint_runtime" in main
    assert "configure_chat_service_runtime_provider(_build_chat_entrypoint_runtime)" in main


def test_router_uses_service_boundary():
    router = _read(ROUTER)
    assert "handle_chat_entrypoint" in router
    assert "_chat_service_runtime()" in router
    assert "configure_chat_service_runtime_provider" in router


def test_router_does_not_import_main_or_forbidden_runtime():
    router = _read(ROUTER)
    forbidden = [
        "brain_v9." + "main",
        "brain_v9.core." + "session",
        "semantic_memory_faiss",
        "faiss",
        "trading",
        "requ" + "ests.",
        "ht" + "tpx.",
        "uv" + "icorn",
        "sub" + "process",
        "os." + "system",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in forbidden:
        assert token not in router


def test_service_contract_tokens_preserved():
    combined = _read(MAIN) + "\n" + _read(ROUTER) + "\n" + _read(SERVICE)
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


def test_endpoint_count_decreased_by_one():
    main = _read(MAIN)
    assert len(re.findall(r"@app\.(get|post|put|delete|patch)", main)) == 50


def test_models_not_from_main_in_router():
    router = _read(ROUTER)
    assert "from brain_v9.main" not in router
    assert "class ChatRequest" in router
    assert "class ChatResponse" in router


def test_no_runtime_data_mutation_tokens():
    combined = _read(MAIN) + "\n" + _read(ROUTER) + "\n" + _read(SERVICE)
    forbidden = [
        "dry_run_only=False",
        "promote_record",
        "faiss.write_index",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in forbidden:
        assert token not in combined


def test_report_records_final_move():
    report = _read(REPORT)
    assert "FULLY_COMPLETED_CHAT_ROUTE_MOVE" in report
    assert "service boundary reused" in report


if __name__ == "__main__":
    test_chat_route_no_longer_in_main()
    test_chat_route_lives_in_router()
    test_main_includes_chat_entrypoint_router()
    test_runtime_provider_registered()
    test_router_uses_service_boundary()
    test_router_does_not_import_main_or_forbidden_runtime()
    test_service_contract_tokens_preserved()
    test_endpoint_count_decreased_by_one()
    test_models_not_from_main_in_router()
    test_no_runtime_data_mutation_tokens()
    test_report_records_final_move()
    print("MAIN_ROUTES_CHAT_FINAL_ROUTE_MOVE_15F_OK")
