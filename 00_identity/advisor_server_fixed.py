import os, json, re
from pathlib import Path
from typing import Any, Dict, Optional, List

import httpx
from fastapi import FastAPI, Body, Request

# ---------------- Config ----------------
BRAIN_API = os.environ.get("BRAIN_API", "http://127.0.0.1:8010")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")  # ajustable
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

ROADMAP_PATH = os.environ.get("BRAIN_ROADMAP_PATH", r"C:\AI_VAULT\tmp_agent\state\roadmap.json")
ROOMS_DIR = os.environ.get("BRAIN_ROOMS_DIR", r"C:\AI_VAULT\tmp_agent\state\rooms")

# Low-risk allowlist (por defecto: solo rooms/<rid>/ y logs/evals/episodes)
ALLOW_TOOLS_DEFAULT = {"append_file", "write_file", "runtime_snapshot_set", "runtime_snapshot_get"}
ALLOW_PATH_PREFIX_DEFAULT = str(Path(ROOMS_DIR)).lower().replace("/", "\\") + "\\"

app = FastAPI(title="BrainLab Advisor", version="0.1.0")

# ---------------- Helpers ----------------
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

def _is_allowed_step(step: dict,
                     allow_tools: set,
                     allow_path_prefix: str) -> tuple[bool, str]:
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
    # robust parse: find first {...} block
    if not isinstance(text, str):
        return None
    text = text.strip()
    # direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # heuristic: find first JSON object
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

# PATCH_ADVISOR_PLAN_SANITIZE_V2
def _room_prefix(room_id: str) -> str:
    rid = _normalize_room_id(room_id)
    return str((Path(ROOMS_DIR) / rid)).lower().replace("/", "\\") + "\\"

def _coerce_step_content(tool_name: str, tool_args: dict) -> dict:
    args = dict(tool_args or {})
    if tool_name in {"write_file", "append_file"}:
        raw_content = args.get("content", args.get("text"))
        if raw_content is None:
            raw_content = ""
        txt = str(raw_content)
        txt = txt.replace("{{now_iso}}", _now_iso())
        txt = txt.replace("\\n", "\n")
        args["content"] = txt
        args["raw_content"] = str(raw_content)
        args["text"] = txt
    return args

def _sanitize_advisor_plan(room_id: str, plan_obj: dict) -> dict:
    room_id = _normalize_room_id(room_id)

    tool_map = {
        "low_risk.list_directory": "list_dir",
        "low_risk.read_file": "read_file",
        "low_risk.write_file": "write_file",
        "low_risk.append_file": "append_file",
        "list_directory": "list_dir",
        "readfile": "read_file",
        "writefile": "write_file",
        "appendfile": "append_file",
    }
    status_map = {
        "queued": "todo",
        "pending": "todo",
        "planned": "todo",
        "ready": "todo",
        "completed": "done",
        "failed": "error",
    }
    allowed_tools = {"list_dir", "read_file", "write_file", "append_file"}
    allowed_status = {"todo", "in_progress", "proposed", "done", "error"}
    allow_room_prefix = _room_prefix(room_id)
    allow_vault_prefix = str(Path("C:/AI_VAULT")).lower().replace("/", "\\")

    if not isinstance(plan_obj, dict):
        return {"room_id": room_id, "status": "complete", "steps": []}

    raw_steps = plan_obj.get("steps")
    if not isinstance(raw_steps, list):
        raw_steps = []

    out_steps = []
    i = 1
    for st in raw_steps:
        if not isinstance(st, dict):
            continue

        sid = str(st.get("id") or st.get("step_id") or i).strip() or str(i)

        st_status = str(st.get("status") or "todo").strip().lower()
        st_status = status_map.get(st_status, st_status)
        if st_status not in allowed_status:
            st_status = "todo"

        tool_name = str(st.get("tool_name") or st.get("action") or "").strip()
        tool_name = tool_map.get(tool_name, tool_name)
        if tool_name not in allowed_tools:
            continue

        tool_args = st.get("tool_args")
        if not isinstance(tool_args, dict):
            tool_args = st.get("args")
        if not isinstance(tool_args, dict):
            tool_args = {}

        path = str(tool_args.get("path") or "").strip()
        norm = path.lower().replace("/", "\\") if path else ""

        if tool_name in {"write_file", "append_file"}:
            if (not norm) or (not norm.startswith(allow_room_prefix)):
                continue
            tool_args = _coerce_step_content(tool_name, tool_args)
            if not str(tool_args.get("content") or ""):
                continue
        elif tool_name in {"read_file", "list_dir"}:
            if not norm:
                continue
            if not norm.startswith(allow_vault_prefix):
                continue

        out_steps.append({
            "id": sid,
            "status": st_status,
            "tool_name": tool_name,
            "tool_args": tool_args
        })
        i += 1

    return {
        "room_id": room_id,
        "status": "active" if out_steps else "complete",
        "steps": out_steps
    }

def _strip_json_fences(txt: str) -> str:
    s = str(txt or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _looks_like_placeholder_plan(obj: dict, room_id: str) -> bool:
    if not isinstance(obj, dict):
        return True

    bad_tokens = {"12345", "toola", "toolb", "arg1", "arg2", "value1", "value2", "room_ui_write_smoke_x"}
    root_room = str(obj.get("room_id") or "").strip().lower()
    plan = obj.get("plan") if isinstance(obj.get("plan"), dict) else {}
    plan_room = str(plan.get("room_id") or "").strip().lower()

    if root_room and root_room != str(room_id).strip().lower():
        return True
    if plan_room and plan_room != str(room_id).strip().lower():
        return True

    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    for st in steps:
        if not isinstance(st, dict):
            return True
        tool_name = str(st.get("tool_name") or "").strip().lower()
        if tool_name in bad_tokens:
            return True
        args = st.get("tool_args") if isinstance(st.get("tool_args"), dict) else {}
        path = str(args.get("path") or "").strip().lower()
        content = str(args.get("content") or args.get("text") or "").strip().lower()

        if any(tok in path for tok in bad_tokens):
            return True
        if any(tok in content for tok in bad_tokens):
            return True

    return False

def _finalize_no_action(room_id: str, *, ok: bool = True, model: str = "no_action", detail: str = "") -> dict:
    return {
        "ok": ok,
        "room_id": room_id,
        "publish": False,
        "plan": {
            "room_id": room_id,
            "status": "complete",
            "steps": []
        },
        "model": model,
        "detail": detail
    }

def _fallback_plan_low_risk(room_id: str):
    """
    HARDENING_V6_DISABLE_EXECUTABLE_FALLBACK
    Cuando el advisor cae en fallback, NO debe fabricar un step ejecutable.
    Debe devolver una respuesta explícita de no-acción para que el loop/policy
    detengan el avance y no confundan fallback con progreso real.
    """
    room_id = _normalize_room_id(room_id)
    return {
        "ok": True,
        "room_id": room_id,
        "publish": False,
        "model": "fallback_no_action",
        "note": "advisor fallback disabled for executable plans",
        "plan": {
            "room_id": room_id,
            "status": "complete",
            "steps": []
        }
    }

async def _brain_plan_publish(room_id: str, plan_obj: dict) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{BRAIN_API}/v1/agent/plan", json=plan_obj, headers={"x-room-id": room_id})
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": "brain_non_json", "status": r.status_code, "text": r.text[:2000]}

def _persist_advisor_raw(room_id: str, out_text: str, meta: Optional[dict] = None) -> dict:
    """
    Guarda output crudo del modelo por room para diagnóstico cuando falle el parse.
    """
    try:
        room_id = str(room_id or "").strip() or "default"
        room_dir = Path(ROOMS_DIR) / room_id
        room_dir.mkdir(parents=True, exist_ok=True)

        raw_path = room_dir / "raw_model_output.txt"
        meta_path = room_dir / "raw_model_meta.json"

        txt = str(out_text or "")
        raw_path.write_text(txt, encoding="utf-8", errors="ignore")

        payload = {
            "room_id": room_id,
            "chars": len(txt),
            "preview": txt[:1000],
        }
        if isinstance(meta, dict):
            payload.update(meta)

        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "raw_output_path": str(raw_path),
            "raw_meta_path": str(meta_path)
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"persist_raw_failed: {e}"
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
    }

@app.post("/v1/advisor/next", response_model=dict)
async def advisor_next(req: dict):
    """ADVISOR_NEXT_CANON_BODY_V2: saneamiento server-side y publish=false por defecto."""
    try:
        import os, json
        from pathlib import Path
        from fastapi import HTTPException
    except Exception:
        raise

    req = req or {}
    room_id = _normalize_room_id(str(req.get("room_id") or ""))
    if not room_id:
        raise HTTPException(status_code=400, detail="missing room_id")

    mode = str(req.get("mode") or "planner").strip().lower()
    publish = bool(req.get("publish", False))
    prompt = str(req.get("prompt") or "").strip()

    if not prompt:
        roadmap_path = os.environ.get("ROADMAP_PATH") or ROADMAP_PATH
        brain_api = os.environ.get("BRAIN_API") or BRAIN_API
        roadmap_txt = ""
        try:
            roadmap_txt = Path(roadmap_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as _e:
            roadmap_txt = json.dumps({"ok": False, "error": "roadmap_read_failed", "detail": repr(_e), "path": roadmap_path})

        status_obj = {}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(f"{brain_api}/v1/agent/status", params={"room_id": room_id}, headers={"x-room-id": room_id})
                status_obj = r.json() if r.status_code == 200 else {"ok": False, "http_status": r.status_code, "text": r.text}
        except Exception as _e:
            status_obj = {"ok": False, "error": "status_fetch_failed", "detail": repr(_e)}

        prompt = (
            "Eres Brain Lab Advisor. Devuelve SOLO JSON válido, sin markdown, sin code fences y sin texto extra.\n"
            f"Usa EXACTAMENTE room_id='{room_id}'.\n"
            "publish debe ser false.\n"
            "Shape exacto: {ok, room_id, publish, plan:{room_id,status,steps:[{id,status,tool_name,tool_args}]}}.\n"
            "tool_name solo puede ser list_dir, read_file, write_file o append_file.\n"
            "Para write_file o append_file, tool_args.path debe estar dentro de C:\\AI_VAULT\\tmp_agent\\state\\rooms\\<room_id>\\ y content debe ser string no vacío.\n"
            "No uses placeholders ni ejemplos como 12345, toolA, toolB, arg1, arg2, value1, value2 ni room_ui_write_smoke_X.\n"
            "Si no existe una acción segura, útil y room-coherent, devuelve plan.steps=[] y status='complete'.\n"
            "No propongas roadmap_progress.json, progress.json, summary.json, report.json, notes.json, log.json, log.txt, report.txt, progress.txt ni next_action.json.\n\n"
            "ROADMAP_JSON:\n" + roadmap_txt + "\n\n"
            "ROOM_STATUS_JSON:\n" + json.dumps(status_obj, ensure_ascii=False) + "\n"
        )

    fn = globals().get("_openai_responses_call", None)
    if not fn:
        fb = globals().get("_fallback_plan_low_risk", None)
        if fb:
            plan_obj = fb(room_id)
            return {"ok": True, "room_id": room_id, "publish": False, "plan": plan_obj, "model": "fallback_helper_missing"}
        return _finalize_no_action(room_id, ok=False, model="openai_helper_missing", detail="openai_helper_missing")

    oc = await fn(prompt)
    out_text = str((oc or {}).get("output_text") or "").strip()
    if not out_text:
        fb = globals().get("_fallback_plan_low_risk", None)
        if fb:
            plan_obj = fb(room_id)
            return {"ok": True, "room_id": room_id, "publish": False, "plan": plan_obj, "model": "fallback_empty_output"}
        return _finalize_no_action(room_id, ok=False, model="empty_model_output", detail="empty_model_output")

    out_text_clean = _strip_json_fences(out_text)

    try:
        obj = json.loads(out_text_clean)

        if _looks_like_placeholder_plan(obj, room_id):
            persist = _persist_advisor_raw(
                room_id,
                out_text_clean,
                {
                    "error": "placeholder_plan_detected",
                    "detail": "generic room_id/tool names/content",
                    "model_name": (globals().get("OPENAI_MODEL", None) or os.environ.get("OPENAI_MODEL") or ""),
                    "mode": mode,
                    "publish_requested": bool(publish)
                }
            )
            fb = globals().get("_fallback_plan_low_risk", None)
            if fb:
                plan_obj = fb(room_id)
                return {
                    "ok": True,
                    "room_id": room_id,
                    "publish": False,
                    "plan": plan_obj,
                    "model": "fallback_placeholder_plan",
                    "detail": "placeholder_plan_detected",
                    "raw_output_path": (persist.get("raw_output_path") if isinstance(persist, dict) else None),
                    "raw_meta_path": (persist.get("raw_meta_path") if isinstance(persist, dict) else None)
                }
            return _finalize_no_action(room_id, ok=False, model="placeholder_plan_detected", detail="placeholder_plan_detected")

    except Exception as _e:
        persist = _persist_advisor_raw(
            room_id,
            out_text_clean,
            {
                "error": "json_parse_failed",
                "detail": repr(_e),
                "model_name": (globals().get("OPENAI_MODEL", None) or os.environ.get("OPENAI_MODEL") or ""),
                "mode": mode,
                "publish_requested": bool(publish)
            }
        )
        fb = globals().get("_fallback_plan_low_risk", None)
        if fb:
            plan_obj = fb(room_id)
            return {
                "ok": True,
                "room_id": room_id,
                "publish": False,
                "plan": plan_obj,
                "model": "fallback_parse_fail",
                "detail": repr(_e),
                "raw_output_path": (persist.get("raw_output_path") if isinstance(persist, dict) else None),
                "raw_meta_path": (persist.get("raw_meta_path") if isinstance(persist, dict) else None)
            }
        return {
            "ok": False,
            "room_id": room_id,
            "publish": False,
            "plan": {"room_id": room_id, "status": "complete", "steps": []},
            "error": "json_parse_failed",
            "detail": repr(_e),
            "raw_output_path": (persist.get("raw_output_path") if isinstance(persist, dict) else None),
            "raw_meta_path": (persist.get("raw_meta_path") if isinstance(persist, dict) else None)
        }

    if not isinstance(obj, dict):
        return _finalize_no_action(room_id, ok=False, model="invalid_root_object", detail="invalid_root_object")

    obj["room_id"] = room_id
    obj["publish"] = False

    _plan_in = obj.get("plan")
    if isinstance(_plan_in, dict):
        if isinstance(_plan_in.get("plan"), dict):
            obj["plan"] = _sanitize_advisor_plan(room_id, _plan_in.get("plan"))
            if _plan_in.get("note") and not obj.get("note"):
                obj["note"] = _plan_in.get("note")
            if _plan_in.get("model") and not obj.get("model"):
                obj["model"] = _plan_in.get("model")
        else:
            obj["plan"] = _sanitize_advisor_plan(room_id, _plan_in)
    else:
        obj["plan"] = {"room_id": room_id, "status": "complete", "steps": []}

    if not isinstance(obj.get("plan"), dict):
        obj["plan"] = {"room_id": room_id, "status": "complete", "steps": []}

    obj["plan"]["room_id"] = room_id
    _steps = obj["plan"].get("steps") if isinstance(obj["plan"].get("steps"), list) else []
    if len(_steps) == 0:
        obj["plan"] = {"room_id": room_id, "status": "complete", "steps": []}

    return obj

async def _openai_responses_call(prompt: str) -> dict:
    """
    Minimal OpenAI Responses API wrapper used by advisor_next.
    Returns a dict with best-effort keys: ok, output_text, raw.
    """
    prompt = str(prompt or "")
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        # No SDK installed -> explicit failure (handled by caller fallback if any)
        return {"ok": False, "error": "openai_sdk_missing", "detail": repr(e), "output_text": ""}

    try:
        client = AsyncOpenAI()
        # Keep it simple; model comes from env OPENAI_MODEL in this service.
        model = (os.environ.get("OPENAI_MODEL") or "").strip() or "gpt-5"
        resp = await client.responses.create(
            model=model,
            input=prompt
        )
        # best-effort extract text
        out_text = ""
        try:
            out_text = getattr(resp, "output_text", "") or ""
        except Exception:
            out_text = ""
        if not out_text:
            # fallback: try to walk output items
            try:
                # resp.output is a list of items; each may have content blocks
                for item in (getattr(resp, "output", None) or []):
                    for c in (getattr(item, "content", None) or []):
                        t = getattr(c, "text", None)
                        if t:
                            out_text += str(t)
            except Exception:
                pass
        return {"ok": True, "output_text": out_text, "raw": resp}
    except Exception as e:
        return {"ok": False, "error": "openai_call_failed", "detail": repr(e), "output_text": ""}
# === OPENAI_RESPONSES_CALL_V1 END ===

# === OPENAI_RESPONSES_CALL_FORCE_V3 BEGIN ===
import os

async def _openai_responses_call(prompt: str) -> dict:
    prompt = str(prompt or "")
    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        return {"ok": False, "error": "openai_sdk_missing", "detail": repr(e), "output_text": ""}

    try:
        client = AsyncOpenAI()
        model = (os.environ.get("OPENAI_MODEL") or "").strip() or "gpt-5"
        resp = await client.responses.create(model=model, input=prompt)

        out_text = ""
        try:
            out_text = getattr(resp, "output_text", "") or ""
        except Exception:
            out_text = ""

        if not out_text:
            try:
                for item in (getattr(resp, "output", None) or []):
                    for c in (getattr(item, "content", None) or []):
                        t = getattr(c, "text", None)
                        if t:
                            out_text += str(t)
            except Exception:
                pass

        return {"ok": True, "output_text": out_text, "raw": resp}
    except Exception as e:
        return {"ok": False, "error": "openai_call_failed", "detail": repr(e), "output_text": ""}
# === OPENAI_RESPONSES_CALL_FORCE_V3 END ===



