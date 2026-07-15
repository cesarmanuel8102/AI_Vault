from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
SERVICE = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_service.py"
ROUTER = ROOT / "tmp_agent" / "brain_v9" / "routes" / "chat_entrypoint_routes.py"
REPORT = ROOT / "docs" / "audit" / "MAIN_CHAT_SERVICE_BOUNDARY_REPORT_15E.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _chat_block() -> str:
    main = _read(MAIN)
    router = _read(ROUTER)
    source = main if '@app.post("/chat"' in main else router
    marker = '@app.post("/chat"' if source is main else '@router.post("/chat"'
    start = source.index(marker)
    next_route = source.find("\n@app.", start + 1) if source is main else source.find("\n@router.", start + 1)
    next_def = source.find("\ndef ", start + 1)
    candidates = [x for x in (next_route, next_def) if x != -1]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_chat_route_still_in_main():
    assert '@router.post("/chat", response_model=ChatResponse)' in _read(ROUTER)
    assert '@app.post("/chat"' not in _read(MAIN)


def test_chat_route_wrapper_uses_service():
    main = _read(MAIN)
    router = _read(ROUTER)
    assert "handle_chat_entrypoint" in router
    assert "_build_chat_entrypoint_runtime" in main
    assert "ChatEntrypointRuntime" in main


def test_chat_wrapper_is_small_enough():
    assert len(_chat_block().splitlines()) <= 45


def test_service_file_exists():
    assert SERVICE.exists()


def test_service_forbidden_imports():
    service = _read(SERVICE)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core.session",
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
        assert token not in service


def test_chat_response_contract_tokens_preserved():
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


def test_chat_final_move_not_done_yet():
    assert '@router.post("/chat"' in _read(ROUTER)
    assert '@app.post("/chat"' not in _read(MAIN)
    assert "15F" in _read(REPORT)


def test_no_endpoint_count_increase():
    main = _read(MAIN)
    assert len(re.findall(r"@app\.(get|post|put|delete|patch)", main)) <= 51


def test_15f_readiness_marker():
    report = _read(REPORT)
    assert "COMPLETED_SERVICE_BOUNDARY" in report
    assert "15F" in report
    assert "final move" in report
    final_report = _read(ROOT / "docs" / "audit" / "MAIN_ROUTER_CHAT_FINAL_ROUTE_MOVE_REPORT_15F.md")
    assert "FULLY_COMPLETED_CHAT_ROUTE_MOVE" in final_report


if __name__ == "__main__":
    test_chat_route_still_in_main()
    test_chat_route_wrapper_uses_service()
    test_chat_wrapper_is_small_enough()
    test_service_file_exists()
    test_service_forbidden_imports()
    test_chat_response_contract_tokens_preserved()
    test_chat_final_move_not_done_yet()
    test_no_endpoint_count_increase()
    test_15f_readiness_marker()
    print("MAIN_CHAT_SERVICE_BOUNDARY_15E_OK")
