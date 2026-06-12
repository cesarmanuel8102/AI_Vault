"""Direct local client for Codex/Kimi/GLM-to-Brain dialogue via OpenAI-compatible API."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List

DEFAULT_BASE_URL = "http://127.0.0.1:8090/v1"
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)\s*[:=]\s*[^\s,'\"]+")


def redact_sensitive(text: str) -> str:
    return SECRET_RE.sub(r"\1=<REDACTED>", text or "")


def _request_json(url: str, payload: Dict[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if payload is None else "POST")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe_models(base_url: str = DEFAULT_BASE_URL) -> Dict[str, Any]:
    return _request_json(f"{base_url.rstrip('/')}/models")


def chat_completion(
    message: str,
    model: str = "brain-v9-local",
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 30,
) -> Dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": message}], "stream": False}
    return _request_json(f"{base_url.rstrip('/')}/chat/completions", payload, timeout=timeout)


def chat_batch(messages: Iterable[str], model: str = "brain-v9-local", base_url: str = DEFAULT_BASE_URL, timeout: int = 30) -> List[Dict[str, Any]]:
    return [chat_completion(message, model=model, base_url=base_url, timeout=timeout) for message in messages]


def validate_openai_response(response: Dict[str, Any]) -> bool:
    try:
        return (
            response.get("object") == "chat.completion"
            and bool(response.get("choices"))
            and bool(response["choices"][0]["message"].get("content"))
            and isinstance(response.get("brain"), dict)
        )
    except Exception:
        return False


def extract_brain_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    brain = response.get("brain") or {}
    return {
        "intent": brain.get("intent"),
        "route": brain.get("route"),
        "governance_applied": brain.get("governance_applied"),
        "no_cot_leak": brain.get("no_cot_leak"),
        "canonical_path": brain.get("canonical_path"),
    }
