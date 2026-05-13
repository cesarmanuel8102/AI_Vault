import os
import json
import time
import subprocess
import re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

# ==========================
# CONFIG
# ==========================
API_KEY = os.getenv("BRAIN_API_KEY")
ROUTER_PATH = r"C:\AI_VAULT\00_identity\brain_router.py"
TIMEOUT_SECONDS = int(os.getenv("BRAIN_TIMEOUT", "180"))

LOG_ENABLED = (os.getenv("BRAIN_LOG") or "").strip() == "1"
LOG_PATH = os.getenv("BRAIN_LOG_PATH") or r"C:\AI_VAULT\logs\brain_requests.ndjson"

MEM_ROOT = Path(os.getenv("BRAIN_MEM_ROOT") or r"C:\AI_VAULT\memory\rooms")
MEM_MAX_TURNS = int(os.getenv("BRAIN_MEM_MAX_TURNS", "40"))        # history guardado
CTX_LAST_TURNS = int(os.getenv("BRAIN_CTX_LAST_TURNS", "12"))      # últimos N turnos al prompt
FACTS_MAX = int(os.getenv("BRAIN_FACTS_MAX", "200"))               # cap facts por room
SUMMARY_MAX_LINES = int(os.getenv("BRAIN_SUMMARY_MAX_LINES", "20"))


class ChatRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    stream: Optional[bool] = False


# ==========================
# UTIL: AUTH
# ==========================
def _auth_or_401(authorization: Optional[str]) -> None:
    if API_KEY:
        if not authorization or authorization != f"Bearer {API_KEY}":
            raise HTTPException(status_code=401, detail="INVALID_API_KEY")


# ==========================
# UTIL: LOGGING
# ==========================
def _log_event(event: Dict[str, Any]) -> None:
    if not LOG_ENABLED:
        return
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ==========================
# UTIL: ROOM/MEM PATHS
# ==========================
def _safe_room_id(room_id: str) -> str:
    room_id = (room_id or "default").strip()
    room_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", room_id)
    return room_id[:80] if room_id else "default"


def _room_paths(room_id: str) -> Dict[str, Path]:
    rid = _safe_room_id(room_id)
    base = MEM_ROOT / rid
    return {
        "base": base,
        "history": base / "history.jsonl",
        "facts": base / "facts.jsonl",
        "summary": base / "summary.txt",
    }


def _ensure_room(room_id: str) -> Dict[str, Path]:
    paths = _room_paths(room_id)
    paths["base"].mkdir(parents=True, exist_ok=True)
    # crea summary vacío si no existe
    if not paths["summary"].exists():
        paths["summary"].write_text("", encoding="utf-8")
    return paths


# ==========================
# MEMORY: IO helpers
# ==========================
def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_last_jsonl(path: Path, max_lines: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = lines[-max_lines:] if max_lines > 0 else lines
        out = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _read_text(path: Path, max_chars: int = 4000) -> str:
    try:
        s = path.read_text(encoding="utf-8", errors="replace")
        s = s.strip()
        if max_chars and len(s) > max_chars:
            return s[-max_chars:]
        return s
    except Exception:
        return ""


def _write_text(path: Path, s: str) -> None:
    try:
        path.write_text(s, encoding="utf-8")
    except Exception:
        pass


# ==========================
# MEMORY: extraction (heurística + estable)
# ==========================
FACT_PATTERNS = [
    # "mi X es Y"
    re.compile(r"\bmi\s+(?P<k>[a-zA-Záéíóúñ0-9_\- ]{2,40})\s+es\s+(?P<v>.{1,120})", re.IGNORECASE),
    # "prefiero X"
    re.compile(r"\bprefiero\s+(?P<v>.{2,140})", re.IGNORECASE),
    # "mi objetivo es X"
    re.compile(r"\bmi\s+objetivo\s+es\s+(?P<v>.{2,180})", re.IGNORECASE),
]


def _extract_facts(text: str) -> List[Tuple[str, str]]:
    text = (text or "").strip()
    if not text:
        return []
    facts = []
    for pat in FACT_PATTERNS:
        for m in pat.finditer(text):
            if "k" in m.groupdict():
                k = m.group("k").strip()
                v = m.group("v").strip()
                facts.append((k, v))
            else:
                v = m.group("v").strip()
                facts.append(("preferencia", v))
    # dedupe simple
    seen = set()
    out = []
    for k, v in facts:
        key = (k.lower(), v.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((k, v))
    return out[:10]


def _update_summary(summary: str, user_text: str, assistant_text: str) -> str:
    """
    Resumen incremental ultra simple (sin LLM): guarda puntos clave del usuario + respuesta.
    Limitado a SUMMARY_MAX_LINES.
    """
    lines = [ln.strip() for ln in (summary or "").splitlines() if ln.strip()]
    # agrega 12 líneas por turno, recortadas
    u = (user_text or "").strip().replace("\n", " ")
    a = (assistant_text or "").strip().replace("\n", " ")
    if u:
        lines.append(f"U: {u[:160]}")
    if a:
        lines.append(f"A: {a[:160]}")
    # mantiene solo últimas N líneas
    lines = lines[-SUMMARY_MAX_LINES:]
    return "\n".join(lines).strip() + ("\n" if lines else "")


def _facts_relevant(facts: List[Dict[str, Any]], query: str, limit: int = 12) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    if not q:
        return facts[-limit:]
    scored = []
    for f in facts:
        k = str(f.get("k", "")).lower()
        v = str(f.get("v", "")).lower()
        score = 0
        for token in set(re.findall(r"[a-zA-Záéíóúñ0-9_]{3,}", q)):
            if token in k:
                score += 2
            if token in v:
                score += 1
        if score > 0:
            scored.append((score, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:limit]] if scored else facts[-limit:]


# ==========================
# PROMPT building
# ==========================
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


def _extract_last_system(messages: List[Dict[str, Any]]) -> str:
    sys_msg = ""
    for m in messages:
        if (m.get("role") or "").lower() == "system":
            sys_msg = (m.get("content") or "").strip()
    return sys_msg


def _extract_last_user(messages: List[Dict[str, Any]]) -> str:
    user_msg = ""
    for m in messages:
        if (m.get("role") or "").lower() == "user":
            user_msg = (m.get("content") or "").strip()
    return user_msg


def _wants_json(messages: List[Dict[str, Any]]) -> bool:
    sys_msg = _extract_last_system(messages).lower()
    user_msg = _extract_last_user(messages).strip().lower()

    if "solo json" in sys_msg or "only json" in sys_msg or "devuelve solo json" in sys_msg:
        return True
    if user_msg.startswith("json:"):
        return True
    return False


def _compose_context_pack(room_paths: Dict[str, Path], user_query: str) -> str:
    summary = _read_text(room_paths["summary"], max_chars=4000)

    facts = _read_last_jsonl(room_paths["facts"], FACTS_MAX)
    facts_rel = _facts_relevant(facts, user_query, limit=12)

    hist = _read_last_jsonl(room_paths["history"], MEM_MAX_TURNS)
    # últimos N turnos (user/assistant) para contexto corto
    hist_tail = hist[-CTX_LAST_TURNS:] if CTX_LAST_TURNS > 0 else hist

    parts = []
    if summary.strip():
        parts.append("### MEMORY_SUMMARY\n" + summary.strip())

    if facts_rel:
        # formatea facts
        fx = []
        for f in facts_rel:
            k = f.get("k")
            v = f.get("v")
            if k and v:
                fx.append(f"- {k}: {v}")
        if fx:
            parts.append("### MEMORY_FACTS\n" + "\n".join(fx))

    if hist_tail:
        hx = []
        for h in hist_tail:
            r = h.get("role")
            c = (h.get("content") or "").strip()
            if not c:
                continue
            tag = "USER" if r == "user" else "ASSISTANT"
            hx.append(f"[{tag}] {c[:220]}")
        if hx:
            parts.append("### MEMORY_RECENT\n" + "\n".join(hx))

    return "\n\n".join(parts).strip()


# ==========================
# ROUTER call
# ==========================
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


# ==========================
# ENDPOINTS
# ==========================
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "brain-router", "object": "model", "owned_by": "local"}]}


@app.post("/v1/chat/completions")
def chat(
    req: ChatRequest,
    authorization: str = Header(default=None),
    x_room_id: str = Header(default="default")
):
    _auth_or_401(authorization)

    room_paths = _ensure_room(x_room_id)

    # usuario actual
    user_last = _extract_last_user(req.messages)
    system_last = _extract_last_system(req.messages)

    # contexto: memoria persistente + prompt
    base_prompt = _build_prompt(req.messages, keep_last=10)
    if not base_prompt:
        raise HTTPException(status_code=400, detail="EMPTY_PROMPT")

    context_pack = _compose_context_pack(room_paths, user_last)

    # prompt final que ve el router/modelo
    final_prompt = base_prompt
    if context_pack:
        final_prompt = f"{context_pack}\n\n---\n\n{base_prompt}"

    wants_json = _wants_json(req.messages)

    # call router
    t0 = time.time()
    routed = _call_router(final_prompt)
    server_dt_ms = int((time.time() - t0) * 1000)

    domain = routed.get("domain") or "GENERAL"
    answer = (routed.get("answer") or "").strip()

    model_used = routed.get("model_used")
    model_source = routed.get("model_source")
    mode = routed.get("mode")
    latency_ms = routed.get("latency_ms")
    router_error = routed.get("error")

    if not answer:
        _log_event({
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event": "chat_error",
            "code": "EMPTY_ANSWER_FROM_MODEL",
            "router_error": router_error,
            "domain": domain,
            "model_used": model_used,
            "model_source": model_source,
            "mode": mode,
            "latency_ms": latency_ms,
            "server_dt_ms": server_dt_ms,
            "prompt_len": len(final_prompt),
            "wants_json": wants_json,
            "room_id": _safe_room_id(x_room_id),
        })
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

    # ==========================
    # MEMORY: persist after success
    # ==========================
    now_s = time.strftime("%Y-%m-%d %H:%M:%S")
    # guarda el último turno user + assistant en history
    if user_last.strip():
        _append_jsonl(room_paths["history"], {"ts": now_s, "role": "user", "content": user_last.strip(), "domain": domain})
    _append_jsonl(room_paths["history"], {"ts": now_s, "role": "assistant", "content": answer, "domain": domain})

    # extrae facts del user y los guarda
    for k, v in _extract_facts(user_last):
        _append_jsonl(room_paths["facts"], {"ts": now_s, "k": k, "v": v, "source": "heuristic"})

    # actualiza summary incremental
    summary_old = _read_text(room_paths["summary"], max_chars=4000)
    summary_new = _update_summary(summary_old, user_last, answer)
    _write_text(room_paths["summary"], summary_new)

    # meta.json (opción 2)
    meta_json_obj = None
    if wants_json:
        meta_json_obj = {"domain": domain, "message": answer}

    # log ok
    _log_event({
        "ts": now_s,
        "event": "chat_ok",
        "domain": domain,
        "model_used": model_used,
        "model_source": model_source,
        "mode": mode,
        "latency_ms": latency_ms,
        "server_dt_ms": server_dt_ms,
        "prompt_len": len(final_prompt),
        "wants_json": wants_json,
        "room_id": _safe_room_id(x_room_id),
    })

    # response
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
            "server_dt_ms": server_dt_ms,
            "env_BRAIN_OLLAMA_MODEL": os.getenv("BRAIN_OLLAMA_MODEL"),
            "json": meta_json_obj,
            "log_enabled": LOG_ENABLED,
            "log_path": LOG_PATH if LOG_ENABLED else None,
            "room_id": _safe_room_id(x_room_id),
            "mem_base": str(room_paths["base"]),
        },
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
    }