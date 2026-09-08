"""R4.3 contract for the pure chat entrypoint runtime boundary."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_service.py"
CONTRACTS = ROOT / "tmp_agent" / "brain_v9" / "core" / "chat_entrypoint_contracts.py"

EXPECTED_FIELDS = (
    "active_sessions",
    "chat_response_cls",
    "trivial_chat_fastpath",
    "looks_like_curated_learning_probe",
    "answer_chat_probe",
    "format_curated_probe_response",
    "pad_authenticated_sessions",
    "brain_enable_unsafe_dev_endpoints",
    "get_gate",
    "execute_god_chat_task",
    "pad_audit",
    "emit_agent_trace",
    "handle_user_message",
    "detect_local_network",
    "scan_local_network",
    "logger",
)


def _load_contracts_module():
    spec = importlib.util.spec_from_file_location("r4_3_contracts", CONTRACTS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_contract_module_exists_and_preserves_the_frozen_field_shape():
    assert CONTRACTS.exists()
    module = _load_contracts_module()
    assert tuple(module.ChatEntrypointRuntime.__dataclass_fields__) == EXPECTED_FIELDS
    assert module.chat_entrypoint_runtime_field_count() == len(EXPECTED_FIELDS)


def test_service_reexports_the_runtime_contract_without_moving_the_entrypoint():
    service = SERVICE.read_text(encoding="utf-8")
    assert "from brain_v9.core.chat_entrypoint_contracts import" in service
    assert "ChatEntrypointRuntime" in service
    assert "chat_entrypoint_runtime_field_count" in service
    assert "async def handle_chat_entrypoint" in service


def test_runtime_contract_module_stays_internal_and_dependency_free():
    source = CONTRACTS.read_text(encoding="utf-8")
    forbidden = (
        "fastapi",
        "brain_v9.main",
        "brain_v9.core.session",
        "semantic_memory_faiss",
        "faiss",
        "trading",
        "provider",
        "tool",
        "subprocess",
        "os.system",
        "scheduler",
        "deployment",
    )
    for token in forbidden:
        assert token not in source.lower()
