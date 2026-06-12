"""OpenAI-compatible transport adapter for Brain V9.

This adapter is intentionally protocol-only. It preserves the canonical Brain
router by delegating every chat completion request to
``brain_v9.core.router_entrypoint.handle_user_message``.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from brain_v9.core.router_entrypoint import handle_user_message

router = APIRouter(prefix="/v1", tags=["openai-compatible"])

MODEL_IDS = ("brain-v9-local", "brain", "ai-vault-brain")
DEFAULT_MODEL = "brain-v9-local"
FORBIDDEN_DIAGNOSTIC_KEYS = {"raw_chain_of_thought", "private_reasoning", "scratchpad"}


class OpenAIChatMessage(BaseModel):
    role: str
    content: Any

    class Config:
        extra = "allow"


class OpenAIChatCompletionRequest(BaseModel):
    model: str = DEFAULT_MODEL
    messages: List[OpenAIChatMessage] = Field(default_factory=list)
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    user: Optional[str] = None
    dry_run: bool = False
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


def _error(message: str, error_type: str = "invalid_request_error") -> Dict[str, Dict[str, str]]:
    return {"error": {"message": message, "type": error_type}}


def _message_content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _latest_user_message(messages: List[OpenAIChatMessage]) -> str:
    if not messages:
        raise HTTPException(status_code=400, detail=_error("messages is required"))
    for msg in reversed(messages):
        if str(msg.role).lower() == "user":
            text = _message_content_as_text(msg.content).strip()
            if text:
                return text
            raise HTTPException(status_code=400, detail=_error("latest user message is empty"))
    raise HTTPException(status_code=400, detail=_error("at least one user message is required"))


def _safe_brain_metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {
        "intent": result.get("intent"),
        "route": result.get("route"),
        "governance_applied": bool(result.get("governance_applied")),
        "no_cot_leak": bool(result.get("no_cot_leak")),
        "canonical_path": result.get("canonical_path"),
        "latency_ms": result.get("latency_ms"),
        "errors": result.get("errors") or [],
        "provider_chain": result.get("provider_chain"),
        "provider_selected": result.get("provider_selected"),
        "model_selected": result.get("model_selected"),
        "provider_status": result.get("provider_status"),
        "provider_latency_ms": result.get("provider_latency_ms"),
        "primary_provider_available": result.get("primary_provider_available"),
        "secondary_provider_available": result.get("secondary_provider_available"),
        "cloud_provider_available": result.get("cloud_provider_available"),
        "codex_provider_available": result.get("codex_provider_available"),
        "local_fallback_used": result.get("local_fallback_used"),
    }
    return {k: v for k, v in metadata.items() if k not in FORBIDDEN_DIAGNOSTIC_KEYS}


def _request_dry_run(payload: OpenAIChatCompletionRequest) -> bool:
    metadata = payload.metadata or {}
    return bool(
        payload.dry_run
        or metadata.get("dry_run")
        or metadata.get("read_only")
        or metadata.get("evaluation")
    )


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": 0, "owned_by": "local"}
            for model_id in MODEL_IDS
        ],
    }


@router.post("/chat/completions")
async def chat_completions(payload: OpenAIChatCompletionRequest) -> Dict[str, Any]:
    if payload.stream:
        raise HTTPException(status_code=501, detail=_error("streaming_not_supported_yet", "unsupported_feature"))
    if payload.model not in MODEL_IDS:
        # Open WebUI often sends custom model aliases. Keep transport tolerant but report the canonical model.
        model_id = DEFAULT_MODEL
    else:
        model_id = payload.model

    message = _latest_user_message(payload.messages)
    dry_run = _request_dry_run(payload)
    started = time.monotonic()
    try:
        result = await handle_user_message(
            message,
            room=payload.user or "openai_compat",
            dry_run=dry_run,
            context={
                "model_priority": "chat",
                "source": "openai_compat",
                "requested_model": payload.model,
                "dry_run": dry_run,
                "read_only": dry_run,
                "evaluation": dry_run,
            },
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail=_error("brain_adapter_error", "server_error"))

    content = str(result.get("content") or result.get("response") or "")
    if any(marker in content.lower() for marker in ("raw_chain_of_thought", "private_reasoning", "scratchpad")):
        content = "No puedo exponer razonamiento privado. Puedo responder con una sintesis visible y verificable."

    created = int(time.time())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "brain": {
            **_safe_brain_metadata(result),
            "adapter": "openai_compat",
            "adapter_latency_ms": round((time.monotonic() - started) * 1000, 3),
            "dry_run": dry_run,
            "read_only": dry_run,
            "fallback_used": bool(result.get("fallback_used") or result.get("llm_fallback_used")),
            "fallback_reason": result.get("fallback_reason"),
        },
    }
