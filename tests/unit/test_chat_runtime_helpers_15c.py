from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
for candidate in (ROOT, TMP_AGENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from brain_v9.core import chat_runtime_helpers as helpers


HELPER_SOURCE = (TMP_AGENT / "brain_v9" / "core" / "chat_runtime_helpers.py").read_text(encoding="utf-8")


def test_harmful_intrusion_predicate_blocks_offensive_access_language():
    assert helpers.looks_like_harmful_intrusion_request("hackea el wifi vecino")
    assert helpers.looks_like_harmful_intrusion_request("rompe la clave del router")
    assert not helpers.looks_like_harmful_intrusion_request("audita mi red local de forma defensiva")


def test_local_network_tool_predicate_requires_execution_and_not_code_inspection():
    assert helpers.should_attempt_local_network_tool("escanea mi red local y lista hosts activos")
    assert helpers.should_attempt_local_network_tool("dime que hosts conectados hay en el network")
    assert not helpers.should_attempt_local_network_tool("explica qué es una red local")
    assert not helpers.should_attempt_local_network_tool("revisa tests/agent/test_network.py y dime si usa nmap")


def test_pending_action_extraction_preserves_legacy_payload_shape():
    text = "Accion P2 requiere confirmacion\npending_id: confirm_20260402_205953_freeze_strategy"
    payload = helpers.extract_pending_action_from_text(text)
    assert payload == {
        "pending_id": "confirm_20260402_205953_freeze_strategy",
        "tool": "freeze_strategy",
        "risk": "P2",
        "description": "Accion P2 requiere confirmacion",
    }


def test_pending_action_signal_and_empty_extraction():
    assert helpers.has_pending_action_signal({"pending_id": "x"}, "Sin respuesta")
    assert helpers.has_pending_action_signal({}, "Accion P2 requiere confirmacion")
    assert helpers.extract_pending_action_from_text("requiere confirmacion sin id") is None


def test_helper_source_has_no_runtime_or_side_effect_dependencies():
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
        assert token not in HELPER_SOURCE


if __name__ == "__main__":
    test_harmful_intrusion_predicate_blocks_offensive_access_language()
    test_local_network_tool_predicate_requires_execution_and_not_code_inspection()
    test_pending_action_extraction_preserves_legacy_payload_shape()
    test_pending_action_signal_and_empty_extraction()
    test_helper_source_has_no_runtime_or_side_effect_dependencies()
    print("CHAT_RUNTIME_HELPERS_15C_OK")
