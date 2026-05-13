import os
import json
import time
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

# ==========================
# CONFIG
# ==========================
API_KEY = os.getenv("BRAIN_API_KEY")
ROUTER_PATH = r"C:\AI_VAULT\00_identity\brain_router.py"
TIMEOUT_SECONDS = 180


class ChatRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    stream: Optional[bool] = False


def _auth_or_401(authorization: Optional[str]) -> None:
    if API_KEY:
        if not authorization or authorization != f"Bearer {API_KEY}":
            raise HTTPException(status_code=401, detail="INVALID_API_KEY")


def _build_prompt(messages: List[Dict[str, Any]], keep_last: int = 10) -> str:
    system_msg = ""
    ua: List[tuple] = []

    for m in messages:
        role = (m.get("role") or "").lower()
        content = (m.get("content") or "").strip()
        if role == "system" and content:
            system_msg = content
        elif role in ("user", "assistant") and content:
            ua.append((role, content))

    if keep_last and len(ua) > keep_last:
        ua = ua[-keep_last:]

    parts: List[str] = []
    if system_msg:
        parts.append(f"[SYSTEM]\n{system_msg}\n")

    for role, content in ua:
        tag = "USER" if role == "user" else "ASSISTANT"
        parts.append(f"[{tag}]\n{content}\n")

    return "\n".join(parts).strip()


def _call_router(raw_text: str) -> Dict[str, Any]:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return {"domain": "GENERAL", "model_used": None, "answer": "", "error": "EMPTY_PROMPT"}

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        ["python", ROUTER_PATH],
        input=raw_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=env,
        timeout=TIMEOUT_SECONDS,
    )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if not out:
        raise HTTPException(status_code=500, detail=f"ROUTER_EMPTY_OUTPUT: {err[:500]}")

    try:
        return json.loads(out)
    except Exception:
        return {
            "domain": "GENERAL",
            "model_used": None,
            "answer": out,
            "router_raw": out,
            "router_err": err,
            "error": "ROUTER_NON_JSON_OUTPUT",
        }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "brain-router", "object": "model", "owned_by": "local"}]}


@app.post("/v1/chat/completions")
def chat(req: ChatRequest, authorization: str = Header(default=None)):
    _auth_or_401(authorization)

    prompt = _build_prompt(req.messages, keep_last=10)
    if not prompt:
        raise HTTPException(status_code=400, detail="EMPTY_PROMPT")

    routed = _call_router(prompt)

    domain = routed.get("domain") or "GENERAL"
    answer = (routed.get("answer") or "").strip()

    model_used = routed.get("model_used")
    model_source = routed.get("model_source")
    mode = routed.get("mode")
    latency_ms = routed.get("latency_ms")
    router_error = routed.get("error")

    if not answer:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "EMPTY_ANSWER_FROM_MODEL",
                "router_error": router_error,
                "domain": domain,
                "mode": mode,
                "model_used": model_used,
                "model_source": model_source,
                "latency_ms": latency_ms,
            },
        )

    now = int(time.time())
    return {
        "id": f"chatcmpl-{now}",
        "object": "chat.completion",
        "created": now,
        "model": "brain-router",
        "domain": domain,
        "meta": {
            "model_used": model_used,
            "model_source": model_source,
            "mode": mode,
            "latency_ms": latency_ms,
            "env_BRAIN_OLLAMA_MODEL": os.getenv("BRAIN_OLLAMA_MODEL"),
        },
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
    }