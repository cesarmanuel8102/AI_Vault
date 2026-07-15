from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
HELPERS = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_runtime_helpers.py"
SERVICE = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_service.py"
CHAT_ENTRYPOINT_ROUTES = ROOT / "tmp_agent" / "brain_v9" / "routes" / "chat_entrypoint_routes.py"
REPORT = ROOT / "docs" / "audit" / "MAIN_CHAT_RUNTIME_DECOMPOSITION_REPORT_15C.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_chat_route_decomposition_is_preserved_after_final_move():
    main = _read(MAIN)
    router = _read(CHAT_ENTRYPOINT_ROUTES)
    assert '@app.post("/chat"' not in main
    assert '@router.post("/chat", response_model=ChatResponse)' in router


def test_runtime_helper_file_exists_and_main_uses_it():
    helper = _read(HELPERS)
    main_or_service = _read(MAIN) + "\n" + (_read(SERVICE) if SERVICE.exists() else "")
    names = [
        "looks_like_harmful_intrusion_request",
        "should_attempt_local_network_tool",
        "has_pending_action_signal",
        "extract_pending_action_from_text",
    ]
    for name in names:
        assert f"def {name}" in helper
        assert name in main_or_service
    assert "from brain_v9.core.chat_runtime_helpers import" in main_or_service


def test_helper_file_has_no_forbidden_runtime_dependencies():
    helper = _read(HELPERS)
    forbidden = [
        "brain_v9.main",
        "brain_v9.core.session",
        "semantic_memory_faiss",
        "faiss",
        "trading",
        "requests.",
        "httpx.",
        "uvicorn",
        "subprocess",
        "os.system",
        "placeOrder",
        "submit_order",
    ]
    for token in forbidden:
        assert token not in helper


def test_chat_response_contract_tokens_still_present():
    combined = _read(MAIN) + "\n" + _read(HELPERS) + "\n" + (_read(SERVICE) if SERVICE.exists() else "")
    for token in [
        "pending_action",
        "trace",
        "native",
        "ChatResponse",
        "timeout",
        "curated",
        "PAD",
        "GOD",
    ]:
        assert token in combined


def test_main_endpoint_count_is_unchanged_after_helper_extraction():
    main = _read(MAIN)
    assert len(re.findall(r"@app\.(get|post|put|delete|patch)", main)) == 50


def test_report_documents_15d_target():
    report = _read(REPORT)
    assert "15D" in report
    assert "POST /chat" in report
    assert "COMPLETED_HELPER_EXTRACTION" in report


if __name__ == "__main__":
    test_legacy_chat_route_decomposition_is_preserved_after_final_move()
    test_runtime_helper_file_exists_and_main_uses_it()
    test_helper_file_has_no_forbidden_runtime_dependencies()
    test_chat_response_contract_tokens_still_present()
    test_main_endpoint_count_is_unchanged_after_helper_extraction()
    test_report_documents_15d_target()
    print("MAIN_CHAT_RUNTIME_DECOMPOSITION_15C_OK")
