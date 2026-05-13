from __future__ import annotations

from typing import Any, Dict, List, Optional
import httpx

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5-coder:14b"


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        temperature: float = 0.2,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            },
        }
        if options:
            payload["options"].update(options)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()

    def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.2,
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        data = self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            stream=False,
        )
        return data.get("message", {}).get("content", "").strip()