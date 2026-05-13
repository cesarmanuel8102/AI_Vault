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
MEM_MAX_TURNS = int(os.getenv("BRAIN_MEM_MAX_TURNS", "40"))
CTX_LAST_TURNS = int(os.getenv("BRAIN_CTX_LAST_TURNS", "12"))
FACTS_MAX = int(os.getenv("BRAIN_FACTS_MAX", "200"))
SUMMARY_MAX_LINES = int(os.getenv("BRAIN_SUMMARY_MAX_LINES", "20"))

POLICY_PATH = Path(os.getenv("BRAIN_POLICY_PATH") or r"C:\AI_VAULT\policy\permissions.json")

# Tool loop
MAX_TOOL_ROUNDS = int(os.getenv("BRAIN_MAX_TOOL_ROUNDS", "2"))  # 0/1/2...
TOOL_TIMEOUT_S = int(os.getenv("BRAIN_TOOL_TIMEOUT", "60"))


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
    if not paths["summary"].exists():
        paths["summary"].write_text("", encoding="utf-8")
    return paths


# ==========================
# MEMORY: IO
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
# MEMORY: extraction
# ==========================
FACT_PATTERNS = [
    re.compile(r"\bmi\s+(?P<k>[a-zA-Záéíóúñ0-9_\- ]{2,40})\s+es\s+(?P<v>.{1,120})", re.IGNORECASE),
    re.compile(r"\bprefiero\s+(?P<v>.{2,140})", re.IGNORECASE),
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
    lines = [ln.strip() for ln in (summary or "").splitlines() if ln.strip()]
    u = (user_text or "").strip().replace("\n", " ")
    a = (assistant_text or "").strip().replace("\n", " ")
    if u:
        lines.append(f"U: {u[:160]}")
    if a:
        lines.append(f"A: {a[:160]}")
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
    hist_tail = hist[-CTX_LAST_TURNS:] if CTX_LAST_TURNS > 0 else hist

    parts = []
    if summary.strip():
        parts.append("### MEMORY_SUMMARY\n" + summary.strip())

    if facts_rel:
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
# POLICY (permissions)
# ==========================
def _default_policy() -> Dict[str, Any]:
    return {
        "allow_write_paths": [r"C:\AI_VAULT\\"],
        "allow_read_paths": [r"C:\AI_VAULT\\"],
        "allow_exec": False,
        "allow_net": ["127.0.0.1", "localhost"],
        "blocked_commands": ["rm", "del", "erase", "format", "diskpart", "cipher", "bcdedit", "reg", "takeown", "icacls"],
        "max_read_bytes": 200000,
        "max_write_bytes": 400000,
        "workspace_root": r"C:\AI_VAULT\workspace\\",
    }


def _load_policy() -> Dict[str, Any]:
    try:
        if POLICY_PATH.exists():
            obj = json.loads(POLICY_PATH.read_text(encoding="utf-8", errors="replace"))
            base = _default_policy()
            base.update(obj if isinstance(obj, dict) else {})
            return base
    except Exception:
        pass
    return _default_policy()


def _norm_path(p: str) -> str:
    try:
        return str(Path(p).resolve())
    except Exception:
        return p


def _path_allowed(p: str, allowed_roots: List[str]) -> bool:
    p2 = _norm_path(p).lower()
    for root in allowed_roots:
        r2 = _norm_path(root).lower()
        if not r2.endswith("\\") and not r2.endswith("/"):
            r2 += "\\"
        if p2.startswith(r2):
            return True
    return False


# ==========================
# TOOLS
# ==========================
def tool_list_dir(args: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    path = (args.get("path") or policy.get("workspace_root") or r"C:\AI_VAULT\workspace\\")
    path = _norm_path(path)

    if not _path_allowed(path, policy.get("allow_read_paths", [])):
        return {"ok": False, "error": "PATH_NOT_ALLOWED", "path": path}

    try:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return {"ok": False, "error": "NOT_A_DIRECTORY", "path": path}
        items = []
        for x in p.iterdir():
            items.append({
                "name": x.name,
                "is_dir": x.is_dir(),
                "size": x.stat().st_size if x.is_file() else None,
            })
        return {"ok": True, "path": path, "items": items[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


def tool_read_file(args: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    path = _norm_path(args.get("path") or "")
    if not path:
        return {"ok": False, "error": "MISSING_PATH"}

    if not _path_allowed(path, policy.get("allow_read_paths", [])):
        return {"ok": False, "error": "PATH_NOT_ALLOWED", "path": path}

    max_bytes = int(policy.get("max_read_bytes", 200000))
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return {"ok": False, "error": "NOT_A_FILE", "path": path}
        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[:max_bytes]
            truncated = True
        else:
            truncated = False
        text = data.decode("utf-8", errors="replace")
        return {"ok": True, "path": path, "truncated": truncated, "content": text}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


def tool_write_file(args: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    path = _norm_path(args.get("path") or "")
    content = args.get("content")
    if not path or content is None:
        return {"ok": False, "error": "MISSING_PATH_OR_CONTENT"}

    if not _path_allowed(path, policy.get("allow_write_paths", [])):
        return {"ok": False, "error": "PATH_NOT_ALLOWED", "path": path}

    max_bytes = int(policy.get("max_write_bytes", 400000))
    data = str(content).encode("utf-8", errors="replace")
    if len(data) > max_bytes:
        return {"ok": False, "error": "CONTENT_TOO_LARGE", "bytes": len(data), "max_bytes": max_bytes}

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return {"ok": True, "path": path, "bytes": len(data)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


def tool_append_file(args: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    path = _norm_path(args.get("path") or "")
    content = args.get("content")
    if not path or content is None:
        return {"ok": False, "error": "MISSING_PATH_OR_CONTENT"}

    if not _path_allowed(path, policy.get("allow_write_paths", [])):
        return {"ok": False, "error": "PATH_NOT_ALLOWED", "path": path}

    max_bytes = int(policy.get("max_write_bytes", 400000))
    data = (str(content) + "\n").encode("utf-8", errors="replace")
    if len(data) > max_bytes:
        return {"ok": False, "error": "CONTENT_TOO_LARGE", "bytes": len(data), "max_bytes": max_bytes}

    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "ab") as f:
            f.write(data)
        return {"ok": True, "path": path, "bytes": len(data)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": path}


def tool_run_ps(args: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    if not bool(policy.get("allow_exec", False)):
        return {"ok": False, "error": "EXEC_DISABLED_BY_POLICY"}

    cmd = (args.get("command") or "").strip()
    if not cmd:
        return {"ok": False, "error": "MISSING_COMMAND"}

    blocked = [str(x).lower() for x in policy.get("blocked_commands", [])]
    cmd_low = cmd.lower()
    for b in blocked:
        if b and re.search(r"\b" + re.escape(b) + r"\b", cmd_low):
            return {"ok": False, "error": "COMMAND_BLOCKED", "blocked": b}

    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TOOL_TIMEOUT_S
        )
        return {
            "ok": True,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[:20000],
            "stderr": (proc.stderr or "")[:20000],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


TOOLS = {
    "list_dir": tool_list_dir,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "append_file": tool_append_file,
    "run_ps": tool_run_ps,
}


# ==========================
# TOOL CALL PROTOCOL
# ==========================
def _try_parse_tool_calls(text: str) -> Optional[Dict[str, Any]]:
    """
    Esperamos JSON tipo:
    {
      "tool_calls":[{"name":"read_file","args":{"path":"..."}}]
    }
    """
    if not text:
        return None
    s = text.strip()

    # limpia code fences
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
            return obj
    except Exception:
        return None
    return None


def _tools_system_instruction(policy: Dict[str, Any]) -> str:
    tool_list = []
    for name in TOOLS.keys():
        tool_list.append(name)

    workspace = policy.get("workspace_root", r"C:\AI_VAULT\workspace\\")
    return (
        "Eres Brain Lab con herramientas controladas.\n"
        "Si necesitas usar herramientas, responde SOLO JSON con este esquema:\n"
        "{\n"
        '  "tool_calls": [\n'
        '    {"name": "list_dir|read_file|write_file|append_file|run_ps", "args": {...}}\n'
        "  ]\n"
        "}\n"
        "Reglas:\n"
        f"- Solo leer/escribir dentro de rutas permitidas. Usa workspace por defecto: {workspace}\n"
        "- No inventes resultados de herramientas.\n"
        "- Si no necesitas herramientas, responde normal.\n"
    )


def _execute_tool_calls(tool_calls: List[Dict[str, Any]], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = []
    for i, tc in enumerate(tool_calls[:8]):  # límite duro
        name = (tc.get("name") or "").strip()
        args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
        fn = TOOLS.get(name)
        if not fn:
            results.append({"index": i, "name": name, "ok": False, "error": "UNKNOWN_TOOL"})
            continue
        res = fn(args, policy)
        results.append({"index": i, "name": name, "args": args, "result": res})
    return results


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
    policy = _load_policy()

    room_paths = _ensure_room(x_room_id)
    now_s = time.strftime("%Y-%m-%d %H:%M:%S")

    user_last = _extract_last_user(req.messages)
    base_prompt = _build_prompt(req.messages, keep_last=10)
    if not base_prompt:
        raise HTTPException(status_code=400, detail="EMPTY_PROMPT")

    context_pack = _compose_context_pack(room_paths, user_last)
    final_prompt = base_prompt if not context_pack else f"{context_pack}\n\n---\n\n{base_prompt}"

    wants_json = _wants_json(req.messages)

    # TOOL LOOP: máximo MAX_TOOL_ROUNDS
    tool_round = 0
    answer = ""
    domain = "GENERAL"
    meta = {}

    # inyecta instrucción de tools al system para que el modelo sepa el protocolo
    tools_sys = _tools_system_instruction(policy)
    final_prompt_with_tools = f"[SYSTEM]\n{tools_sys}\n\n{final_prompt}"

    prompt_for_round = final_prompt_with_tools

    while True:
        t0 = time.time()
        routed = _call_router(prompt_for_round)
        server_dt_ms = int((time.time() - t0) * 1000)

        domain = routed.get("domain") or "GENERAL"
        answer = (routed.get("answer") or "").strip()

        meta = {
            "model_used": routed.get("model_used"),
            "model_source": routed.get("model_source"),
            "mode": routed.get("mode"),
            "latency_ms": routed.get("latency_ms"),
            "server_dt_ms": server_dt_ms,
            "env_BRAIN_OLLAMA_MODEL": os.getenv("BRAIN_OLLAMA_MODEL"),
            "room_id": _safe_room_id(x_room_id),
            "mem_base": str(room_paths["base"]),
        }

        if not answer:
            _log_event({
                "ts": now_s,
                "event": "chat_error",
                "code": "EMPTY_ANSWER_FROM_MODEL",
                "router_error": routed.get("error"),
                "domain": domain,
                "model_used": meta["model_used"],
                "model_source": meta["model_source"],
                "mode": meta["mode"],
                "latency_ms": meta["latency_ms"],
                "server_dt_ms": meta["server_dt_ms"],
                "prompt_len": len(prompt_for_round),
                "wants_json": wants_json,
                "room_id": meta["room_id"],
                "tool_round": tool_round,
            })
            raise HTTPException(status_code=500, detail={
                "code": "EMPTY_ANSWER_FROM_MODEL",
                "router_error": routed.get("error"),
                "domain": domain,
                "mode": meta["mode"],
                "model_used": meta["model_used"],
                "model_source": meta["model_source"],
                "latency_ms": meta["latency_ms"],
            })

        parsed_tools = _try_parse_tool_calls(answer)
        if parsed_tools and tool_round < MAX_TOOL_ROUNDS:
            tool_calls = parsed_tools.get("tool_calls", [])
            tool_results = _execute_tool_calls(tool_calls, policy)

            # log tool usage
            _log_event({
                "ts": now_s,
                "event": "tools_used",
                "room_id": meta["room_id"],
                "tool_round": tool_round,
                "domain": domain,
                "model_used": meta["model_used"],
                "tool_calls": tool_calls,
                "tool_results": tool_results,
            })

            # re-prompt con resultados (2 pasos)
            tool_round += 1
            prompt_for_round = (
                f"{final_prompt_with_tools}\n\n"
                f"[TOOLS_RESULTS]\n{json.dumps(tool_results, ensure_ascii=False)}\n\n"
                "Ahora, usando SOLO esos resultados, responde al usuario."
            )
            continue

        # si no hay tools o se acabaron rondas, salimos
        break

    # ==========================
    # MEMORY: persist after success
    # ==========================
    if user_last.strip():
        _append_jsonl(room_paths["history"], {"ts": now_s, "role": "user", "content": user_last.strip(), "domain": domain})
    _append_jsonl(room_paths["history"], {"ts": now_s, "role": "assistant", "content": answer, "domain": domain})

    for k, v in _extract_facts(user_last):
        _append_jsonl(room_paths["facts"], {"ts": now_s, "k": k, "v": v, "source": "heuristic"})

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
        "model_used": meta.get("model_used"),
        "model_source": meta.get("model_source"),
        "mode": meta.get("mode"),
        "latency_ms": meta.get("latency_ms"),
        "server_dt_ms": meta.get("server_dt_ms"),
        "prompt_len": len(prompt_for_round),
        "wants_json": wants_json,
        "room_id": meta.get("room_id"),
        "tool_rounds_used": tool_round,
    })

    now = int(time.time())
    return {
        "id": f"chatcmpl-{now}",
        "object": "chat.completion",
        "created": now,
        "model": "brain-router",
        "domain": domain,
        "meta": {
            **meta,
            "json": meta_json_obj,
            "log_enabled": LOG_ENABLED,
            "log_path": LOG_PATH if LOG_ENABLED else None,
            "policy_path": str(POLICY_PATH),
            "allow_exec": bool(policy.get("allow_exec", False)),
            "max_tool_rounds": MAX_TOOL_ROUNDS,
            "tool_rounds_used": tool_round,
        },
        "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}],
    }