from pathlib import Path
import asyncio
import sys


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
for candidate in (ROOT, TMP_AGENT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from brain_v9.core.chat_entrypoint_service import (
    ChatEntrypointRuntime,
    chat_entrypoint_runtime_field_count,
    handle_chat_entrypoint,
)
from brain_v9.core.chat_runtime_helpers import extract_pending_action_from_text


SERVICE_SOURCE = (TMP_AGENT / "brain_v9" / "core" / "chat_entrypoint_service.py").read_text(encoding="utf-8")


class FakeRequest:
    def __init__(self, message: str, session_id: str = "s1", model_priority: str = "auto"):
        self.message = message
        self.session_id = session_id
        self.model_priority = model_priority


class FakeResponse:
    def __init__(self, **kwargs):
        self.payload = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeGate:
    def disable_god_mode(self, _session_id):
        return None

    def enable_god_mode(self, _session_id):
        return None


def _runtime(**overrides):
    async def _handle_user_message(_message, room=None, context=None):
        return {"content": "native ok", "success": True, "model": "fake-native"}

    async def _detect_local_network():
        return {"success": True, "primary_cidr": "127.0.0.1/32", "primary_ip": "127.0.0.1", "interfaces": []}

    async def _scan_local_network(**_kwargs):
        return {"success": True, "cidr": "127.0.0.1/32", "live_count": 0, "live_hosts": []}

    payload = {
        "active_sessions": {},
        "chat_response_cls": FakeResponse,
        "trivial_chat_fastpath": lambda _message: None,
        "looks_like_curated_learning_probe": lambda _message: False,
        "answer_chat_probe": lambda **_kwargs: {"decision": "ok"},
        "format_curated_probe_response": lambda _result: "curated ok",
        "pad_authenticated_sessions": {},
        "brain_enable_unsafe_dev_endpoints": False,
        "get_gate": lambda: FakeGate(),
        "execute_god_chat_task": lambda *_args, **_kwargs: {"success": True},
        "pad_audit": lambda *_args, **_kwargs: None,
        "emit_agent_trace": lambda *_args, **_kwargs: None,
        "handle_user_message": _handle_user_message,
        "detect_local_network": _detect_local_network,
        "scan_local_network": _scan_local_network,
        "logger": type("FakeLogger", (), {"debug": lambda *a, **k: None, "warning": lambda *a, **k: None, "exception": lambda *a, **k: None})(),
    }
    payload.update(overrides)
    return ChatEntrypointRuntime(**payload)


def test_service_module_imports_without_runtime():
    assert ChatEntrypointRuntime is not None
    assert handle_chat_entrypoint is not None


def test_runtime_dataclass_exists_and_budget_is_controlled():
    assert chat_entrypoint_runtime_field_count() <= 24
    assert chat_entrypoint_runtime_field_count() == len(ChatEntrypointRuntime.__dataclass_fields__)


def test_service_does_not_import_forbidden_runtime():
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
        assert token not in SERVICE_SOURCE


def test_harmful_intrusion_path_with_fake_runtime():
    response = asyncio.run(handle_chat_entrypoint(FakeRequest("hackea el wifi vecino"), _runtime()))
    assert response.success is False
    assert response.model_used == "brain_safety_guard"
    assert "No puedo ayudar" in response.response


def test_curated_fastpath_path_with_fake_runtime():
    runtime = _runtime(
        looks_like_curated_learning_probe=lambda _message: True,
        answer_chat_probe=lambda **_kwargs: {"decision": "demo"},
        format_curated_probe_response=lambda result: f"Decision: {result['decision']}",
    )
    response = asyncio.run(handle_chat_entrypoint(FakeRequest("q01 dominios"), runtime))
    assert response.success is True
    assert response.model_used == "curated_helper"
    assert response.response == "Decision: demo"


def test_native_pending_action_shape_with_fake_runtime():
    async def _handle_user_message(_message, room=None, context=None):
        return {
            "content": "Accion P2 requiere confirmacion\npending_id: confirm_20260402_205953_freeze_strategy",
            "success": False,
            "model": "fake-native",
            "permission_required": True,
        }

    response = asyncio.run(handle_chat_entrypoint(FakeRequest("haz cambio"), _runtime(handle_user_message=_handle_user_message)))
    assert response.pending_action["pending_id"] == "confirm_20260402_205953_freeze_strategy"
    assert response.pending_action["tool"] == "freeze_strategy"
    assert response.permission_required is True


def test_pending_action_parser_still_available():
    payload = extract_pending_action_from_text("Accion P2\nconfirm_20260402_205953_freeze_strategy")
    assert payload["tool"] == "freeze_strategy"


def test_wrapper_readiness_contract_with_fake_runtime():
    response = asyncio.run(handle_chat_entrypoint(FakeRequest("hola normal"), _runtime()))
    assert response.success is True
    assert response.response == "native ok"
    assert response.model_used == "fake-native"


if __name__ == "__main__":
    test_service_module_imports_without_runtime()
    test_runtime_dataclass_exists_and_budget_is_controlled()
    test_service_does_not_import_forbidden_runtime()
    test_harmful_intrusion_path_with_fake_runtime()
    test_curated_fastpath_path_with_fake_runtime()
    test_native_pending_action_shape_with_fake_runtime()
    test_pending_action_parser_still_available()
    test_wrapper_readiness_contract_with_fake_runtime()
    print("CHAT_ENTRYPOINT_SERVICE_15E_OK")
