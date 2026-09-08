"""Pure runtime contract for the legacy chat entrypoint service."""
from __future__ import annotations

import logging
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, fields
from typing import Any


log = logging.getLogger("brain_v9")


@dataclass(frozen=True)
class ChatEntrypointRuntime:
    active_sessions: MutableMapping[str, Any]
    chat_response_cls: type
    trivial_chat_fastpath: Callable[..., Any]
    looks_like_curated_learning_probe: Callable[..., bool]
    answer_chat_probe: Callable[..., Any]
    format_curated_probe_response: Callable[..., str]
    pad_authenticated_sessions: MutableMapping[str, Any]
    brain_enable_unsafe_dev_endpoints: bool
    get_gate: Callable[..., Any]
    execute_god_chat_task: Callable[..., Any]
    pad_audit: Callable[..., Any]
    emit_agent_trace: Callable[..., Any]
    handle_user_message: Callable[..., Any]
    detect_local_network: Callable[..., Any]
    scan_local_network: Callable[..., Any]
    logger: Any = log


def chat_entrypoint_runtime_field_count() -> int:
    return len(fields(ChatEntrypointRuntime))
