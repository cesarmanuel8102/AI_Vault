import os, json, re
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import httpx
from fastapi import FastAPI, Body, Request

# ---------------- Config ----------------
BRAIN_API = os.environ.get("BRAIN_API", "http://127.0.0.1:8010").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

ROADMAP_PATH = os.environ.get("BRAIN_ROADMAP_PATH", r"C:\AI_VAULT\tmp_agent\state\roadmap.json")
ROOMS_DIR = os.environ.get("BRAIN_ROOMS_DIR", r"C:\AI_VAULT\tmp_agent\state\rooms")

# Low-risk defaults
ALLOW_TOOLS_DEFAULT = {"append_file", "write_file"}  # snapshot handled out-of-plan by HTTP side-effect
ALLOW_PATH_PREFIX_DEFAULT = str(Path(ROOMS_DIR)).lower().replace("/", "\\") + "\\"

app = FastAPI(title="BrainLab Advisor (clean)", version="0.2.0")

# ---------------- Helpers ----------------
def _now_iso() -> str:
    # UTC ISO; brain_server usa Z en varios sitios
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _read_json(p: str) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None

def _tail_text(p: Path, max_bytes: int = 20000) -> str:
    try:
        b = p.read_bytes()
        if len(b) > max_bytes:
            b = b[-max_bytes:]
        return b.decode("utf-8", errors="replace")
    except Exception:
        return ""

def _normalize_room_id(room_id: str) -> str:
    v = (room_id or "").strip()
    if not v:
        return "default"
    v = "".join(ch for ch in v if ch.isalnum() or ch in ("-", "_"))[:64]
    return v or "default"

def _is_allowed_step(step: dict, allow_tools: set, allow_path_prefix: str) -> Tuple[bool, str]:
    if not isinstance(step, dict):
        return False, "step_not_object"

    tool = str(step.get("tool_name") or "").strip()
    if tool not in allow_tools:
        return False, f"tool_not_allowed:{tool}"

    args = step.get("tool_args")
    if not isinstance(args, dict):
        return False, "tool_args_missing_or_invalid"

    if tool in ("append_file", "write_file"):
        path = str(args.get("path") or "")
        norm = path.lower().replace("/", "\\")
        if not norm.startswith(allow_path_prefix):
            return False, f"path_not_allowed:{path}"

        content = args.get("content", args.get("text"))
        if content is None:
            return False, "content_null"
        b = str(content).encode("utf-8", errors="replace")
        if len(b) > 65536:
            return False, "content_too_large"

    return True, "ok"

def _extract_json_object(text: str) -> Optional[dict]:
    if not isinstance(text, str):
        return None
    s = text.strip()

    # direct parse
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # heuristic: first {...}
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

async def _brain_status(room_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{BRAIN_API}/v1/agent/status", params={"room_id": room_id}, headers={"x-room-id": room_id})
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": "brain_non_json", "status": r.status_code, "text": r.text[:2000]}

async def _brain_plan_publish(room_id: str, plan_obj: dict) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{BRAIN_API}/v1/agent/plan", json=plan_obj, headers={"x-room-id": room_id})
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": "brain_non_json", "status": r.status_code, "text": r.text[:2000]}

async def _brain_snapshot_set(room_id: str, path: str, value: Any) -> dict:
    payload = {"room_id": room_id, "path": path, "value": value}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{BRAIN_API}/v1/agent/runtime/snapshot/set", json=payload, headers={"x-room-id": room_id})
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": "brain_non_json", "status": r.status_code, "text": r.text[:2000]}

async def _openai_responses_call(prompt: str) -> dict:
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "missing_OPENAI_API_KEY"}

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": OPENAI_MODEL, "input": prompt}

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{OPENAI_BASE_URL}/responses", headers=headers, json=payload)
        try:
            data = r.json()
        except Exception:
            return {"ok": False, "error": "openai_non_json", "status": r.status_code, "text": r.text[:2000]}
        if r.status_code >= 400:
            return {"ok": False, "error": "openai_http_error", "status": r.status_code, "data": data}
        return {"ok": True, "data": data}

def _response_text(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    out = data.get("output")
    if isinstance(out, list):
        chunks = []
        for item in out:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") in ("output_text", "text"):
                            t = c.get("text") or c.get("content") or ""
                            if isinstance(t, str) and t:
                                chunks.append(t)
        return "\n".join(chunks)
    return ""

def _fallback_plan_low_risk(room_id: str) -> dict:
    # 2-step deterministic plan: write episode.json + append evaluations.ndjson
    room_dir = Path(ROOMS_DIR) / room_id
    ep = str(room_dir / "episode.json")
    ev = str(room_dir / "evaluations.ndjson")

    episode_obj = {
        "ts": _now_iso(),
        "room_id": room_id,
        "phase": "P3",
        "note": "fallback advisor (clean) - create episode/eval artifacts"
    }

    eval_line = json.dumps({
        "ts": _now_iso(),
        "room_id": room_id,
        "plan_status": "active",
        "pass": True,
        "notes": ["fallback advisor wrote episode + evaluation"],
        "artifacts": {"files": ["episode.json", "evaluations.ndjson"]}
    }, ensure_ascii=False)

    return {
        "room_id": room_id,
        "status": "active",
        "steps": [
            {
                "id": "EPI1",
                "step_id": "EPI1",
                "status": "todo",
                "tool_name": "write_file",
                "tool_args": {"path": ep, "content": json.dumps(episode_obj, ensure_ascii=False, indent=2)}
            },
            {
                "id": "EV1",
                "step_id": "EV1",
                "status": "todo",
                "tool_name": "append_file",
                "tool_args": {"path": ev, "content": eval_line + "\n"}
            }
        ]
    }

# ---------------- API ----------------
@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "brain_api": BRAIN_API,
        "openai_key_present": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "roadmap_path": ROADMAP_PATH,
        "rooms_dir": ROOMS_DIR,
        "allow_tools_default": sorted(list(ALLOW_TOOLS_DEFAULT)),
        "allow_path_prefix_default": ALLOW_PATH_PREFIX_DEFAULT,
        "impl": "advisor_clean_v0_2"
    }

@app.post("/v1/advisor/next")
async def advisor_next(request: Request, req: dict = Body(...)) -> Dict[str, Any]:
    room_id = _normalize_room_id(str((req.get("room_id") or request.headers.get("x-room-id") or "default")))

    mode = str(req.get("mode") or "planner").strip().lower()
    publish = bool(req.get("publish", True))
    objective = str(req.get("objective") or "").strip()

    allow_tools = set(req.get("allow_tools") or []) or set(ALLOW_TOOLS_DEFAULT)
    allow_path_prefix = str(req.get("allow_path_prefix") or ALLOW_PATH_PREFIX_DEFAULT).lower().replace("/", "\\")

    force_fallback = bool(req.get("force_fallback", False))

    # Gather context (lightweight; safe)
    roadmap = _read_json(ROADMAP_PATH) or {}
    status = await _brain_status(room_id)

    room_dir = Path(ROOMS_DIR) / room_id
    plan_path = room_dir / "plan.json"
    audit_path = room_dir / "audit.ndjson"
    plan_txt = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    audit_tail = _tail_text(audit_path) if audit_path.exists() else ""

    # ---- Forced fallback path ----
    if force_fallback:
        plan_obj = _fallback_plan_low_risk(room_id)

        # Validate allowlist
        errs: List[str] = []
        for i, st in enumerate(plan_obj.get("steps") or [], start=1):
            ok, reason = _is_allowed_step(st, allow_tools, allow_path_prefix)
            if not ok:
                errs.append(f"step_{i}:{reason}")
        if errs:
            return {"ok": False, "room_id": room_id, "error": "fallback_policy_reject", "details": errs, "plan": plan_obj}

        published = None
        if publish:
            published = await _brain_plan_publish(room_id, plan_obj)

        snapshot_set = await _brain_snapshot_set(
            room_id=room_id,
            path="mission_state.json",
            value={"ts": _now_iso(), "room_id": room_id, "stage": "P3_forced"}
        )

        return {
            "ok": True,
            "room_id": room_id,
            "publish": publish,
            "plan": plan_obj,
            "published": published,
            "snapshot_set": snapshot_set,
            "model": "fallback_forced",
            "impl_trace": "advisor_clean_force_fallback"
        }

    # ---- OpenAI path (fallback on any error) ----
    prompt = f"""
You are the Advisor for a local supervised agent called Brain Lab.
You MUST output ONLY valid JSON (no markdown) matching this schema:

{{
  "room_id": "{room_id}",
  "status": "active",
  "steps": [
    {{
      "id": "S1",
      "step_id": "S1",
      "status": "todo",
      "tool_name": "append_file|write_file",
      "tool_args": {{
        "path": "ABSOLUTE_WINDOWS_PATH_IF_FILE",
        "content": "STRING_IF_WRITE"
      }}
    }}
  ]
}}

Rules:
- Do NOT propose any tool_name outside: {sorted(list(allow_tools))}
- For write_file/append_file, path MUST start with: {allow_path_prefix}
- Keep each write content <= 64KB.
- Prefer append-only ndjson logs. Avoid rewriting existing files unless necessary.
- Focus on progressing the roadmap toward autonomy with supervision.

Context:
mode={mode}
objective={objective if objective else "(use roadmap next actionable item)"}

Roadmap JSON (abridged):
{json.dumps(roadmap, ensure_ascii=False)[:12000]}

Current room status (/v1/agent/status):
{json.dumps(status, ensure_ascii=False)[:8000]}

Current plan.json (if any):
{plan_txt[:8000]}

Recent audit.ndjson tail (if any):
{audit_tail[:8000]}

Task:
Propose the NEXT minimal low-risk plan that advances the roadmap.
""".strip()

    oc = await _openai_responses_call(prompt)
    if not oc.get("ok"):
        # Clean fallback on OpenAI failure
        plan_obj = _fallback_plan_low_risk(room_id)

        errs: List[str] = []
        for i, st in enumerate(plan_obj.get("steps") or [], start=1):
            ok, reason = _is_allowed_step(st, allow_tools, allow_path_prefix)
            if not ok:
                errs.append(f"step_{i}:{reason}")
        if errs:
            return {"ok": False, "room_id": room_id, "error": "fallback_policy_reject", "details": errs, "plan": plan_obj, "openai_error": oc}

        published = None
        if publish:
            published = await _brain_plan_publish(room_id, plan_obj)

        snapshot_set = await _brain_snapshot_set(
            room_id=room_id,
            path="mission_state.json",
            value={"ts": _now_iso(), "room_id": room_id, "stage": "P3_openai_failed"}
        )

        return {
            "ok": True,
            "room_id": room_id,
            "publish": publish,
            "plan": plan_obj,
            "published": published,
            "snapshot_set": snapshot_set,
            "model": "fallback_no_openai",
            "openai_error": oc,
            "impl_trace": "advisor_clean_openai_failed"
        }

    raw_text = _response_text(oc.get("data") or {})
    plan_obj = _extract_json_object(raw_text)
    if not isinstance(plan_obj, dict):
        # Fallback if model output isn't parseable JSON
        plan_obj = _fallback_plan_low_risk(room_id)

    plan_obj["room_id"] = room_id
    plan_obj.setdefault("status", "active")

    steps = plan_obj.get("steps")
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "room_id": room_id, "error": "advisor_steps_empty_or_invalid", "raw": raw_text[:2000]}

    errs: List[str] = []
    for i, st in enumerate(steps, start=1):
        ok, reason = _is_allowed_step(st, allow_tools, allow_path_prefix)
        if not ok:
            errs.append(f"step_{i}:{reason}")
        st.setdefault("id", st.get("step_id") or f"S{i}")
        st.setdefault("step_id", st.get("id") or f"S{i}")
        st.setdefault("status", "todo")

    if errs:
        return {"ok": False, "room_id": room_id, "error": "advisor_policy_reject", "details": errs, "plan": plan_obj}

    published = None
    if publish:
        published = await _brain_plan_publish(room_id, plan_obj)

    # Snapshot side-effect: mark advisor progress
    snapshot_set = await _brain_snapshot_set(
        room_id=room_id,
        path="mission_state.json",
        value={"ts": _now_iso(), "room_id": room_id, "stage": "P3_advised"}
    )

    return {
        "ok": True,
        "room_id": room_id,
        "publish": publish,
        "plan": plan_obj,
        "published": published,
        "snapshot_set": snapshot_set,
        "model": OPENAI_MODEL,
        "impl_trace": "advisor_clean_openai_ok"
    }
