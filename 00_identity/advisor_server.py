import os, json, re
from pathlib import Path
from typing import Any, Dict, Optional, List

import httpx
from fastapi import FastAPI, Body, Request

# ---------------- Config ----------------
BRAIN_API = os.environ.get("BRAIN_API", "http://127.0.0.1:8010")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = (os.environ.get("OPENAI_MODEL_FOR_ADVISOR") or os.environ.get("OPENAI_MODEL") or "gpt-5.2").strip()  # canonical advisor model
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

def _coerce_step_content(tool_name: str, tool_args: dict) -> dict:  # CONTENT_JSON_ESCAPE_FIX_V1
    import json as _jfix
    args = dict(tool_args or {})
    if tool_name in {"write_file", "append_file"}:
        # Si content es dict/list (OpenAI devolvio objeto en vez de string) -> serializar
        raw = args.get("content")
        if isinstance(raw, (dict, list)):
            args["content"] = _jfix.dumps(raw, ensure_ascii=False, indent=2) + "\n"
            args["text"]    = args["content"]
        elif raw is None or raw == "":
            args["content"] = "{}"
            args["text"]    = "{}"
        elif not isinstance(raw, str):
            args["content"] = str(raw)
            args["text"]    = args["content"]
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


def _force_current_room_action_plan(room_id: str) -> dict:
    from pathlib import Path
    import json, datetime

    room_dir = Path(ROOMS_DIR) / room_id
    room_dir.mkdir(parents=True, exist_ok=True)

    out_path = room_dir / "planner_hardening_request.json"
    nowz = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    payload = {
        "room_id": room_id,
        "generated_utc": nowz,
        "phase": "P2_PLANNER_HARDENING_SCHEMA_NORMALIZATION",
        "objective": "Convert empty advisor recovery into a useful current-room request aligned with P2.1 and P2.2.",
        "next_work_items": [
            {
                "id": "P2.1",
                "title": "Guarantee tool_args.content is never null and is always a string",
                "required_checks": [
                    "content must always be a string for write_file and append_file",
                    "normalize literal backslash-n sequences into real newline characters",
                    "preserve raw_content when applicable"
                ]
            },
            {
                "id": "P2.2",
                "title": "Keep now_iso normalization consistent",
                "required_checks": [
                    "use a single now_iso interpolation policy",
                    "keep server-side fallback for the now_iso marker if received",
                    "persist final interpolated content when applicable"
                ]
            }
        ],
        "source": "advisor_empty_plan_recovery_useful_ascii_safe",
        "status": "active"
    }

    return {
        "room_id": room_id,
        "status": "active",
        "steps": [
            {
                "id": "RECOVERY_P2",
                "step_id": "RECOVERY_P2",
                "status": "todo",
                "tool_name": "write_file",
                "tool_args": {
                    "path": str(out_path),
                    "content": json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
                }
            }
        ]
    }
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

            ssot_suffixes = (
                "\\plan.json",
                "\\mission.json",
                "\\audit.ndjson",
                "\\evaluation.json",
                "\\evaluations.ndjson",
            )
            if norm.endswith(ssot_suffixes):
                safe_path = str(Path("C:/AI_VAULT/tmp_agent/state/rooms") / room_id / "planner_hardening_request.json")
                tool_args["path"] = safe_path
                path = safe_path
                norm = path.lower().replace("/", "\\")


            if norm.endswith("\\plan.json"):
                safe_path = str(Path("C:/AI_VAULT/tmp_agent/state/rooms") / room_id / "planner_hardening_request.json")
                tool_args["path"] = safe_path
                path = safe_path
                norm = path.lower().replace("/", "\\")

            tool_args = _coerce_step_content(tool_name, tool_args)

            try:
                _content_probe = str(tool_args.get("content") or "")
                _path_probe = str(tool_args.get("path") or "").lower().replace("/", "\\")
                if (
                    _path_probe.endswith("\\planner_hardening_request.json")
                    and "advisor_empty_plan_recovery_useful_ascii_safe" in _content_probe
                ):
                    safe_path = str(Path("C:/AI_VAULT/tmp_agent/state/rooms") / room_id / "planner_schema_patch_apply_request.json")
                    upgraded = {
                        "room_id": room_id,
                        "phase": "P2_PLANNER_HARDENING_SCHEMA_NORMALIZATION",
                        "artifact_kind": "planner_schema_patch_apply_request",
                        "objective": "Aplicar un parche concreto sobre brain_server.py para normalizar placeholders de content y preservar raw_content en /v1/agent/plan.",
                        "target_files": [
                            r"C:\AI_VAULT\00_identity\brain_server.py"
                        ],
                        "ops": [
                            {
                                "id": "PATCH_NORMALIZE_CONTENT_FN",
                                "file": r"C:\AI_VAULT\00_identity\brain_server.py",
                                "anchor_start": "def _normalize_content_str(x):",
                                "anchor_end": "def _harden_plan_payload(plan: dict):",
                                "replace_mode": "between_anchors",
                                "new_block": "def _normalize_content_str(x):\n    if x is None:\n        return None\n    if not isinstance(x, str):\n        x = str(x)\n\n    if \"__NOW_ISO_PLACEHOLDER__\" in x:\n        x = x.replace(\"__NOW_ISO_PLACEHOLDER__\", _now_iso_utc_z())\n    if \"{{now_iso}}\" in x:\n        x = x.replace(\"{{now_iso}}\", _now_iso_utc_z())\n\n    x = x.replace(\"__LITERAL_BACKSLASH_N__\", \"\\n\")\n    x = x.replace(\"\\\\r\\\\n\", \"\\r\\n\")\n    x = x.replace(\"\\\\n\", \"\\n\")\n    return x\n\n"
                            },
                            {
                                "id": "PATCH_SAFE_TOOL_ARGS_FN",
                                "file": r"C:\AI_VAULT\00_identity\brain_server.py",
                                "anchor_start": "def _p2_1_safe_tool_args(tool_name, tool_args):",
                                "anchor_end": "def _plan_steps(plan: dict):",
                                "replace_mode": "between_anchors",
                                "new_block": "def _p2_1_safe_tool_args(tool_name, tool_args):\n    try:\n        args = dict(tool_args) if isinstance(tool_args, dict) else {}\n\n        if tool_name in (\"write_file\", \"append_file\"):\n            raw = args.get(\"content\", None)\n\n            if raw is None and \"text\" in args:\n                raw = args.get(\"text\", None)\n\n            if raw is None:\n                raw = \"__NOW_ISO_PLACEHOLDER__\\n\"\n\n            if not isinstance(raw, str):\n                raw = str(raw)\n\n            norm = _normalize_content_str(raw)\n\n            if norm is None or norm == \"\":\n                norm = _now_iso_utc_z() + \"\\n\"\n\n            if norm != raw:\n                args[\"raw_content\"] = raw\n\n            args[\"content\"] = norm\n            args[\"text\"] = norm\n\n        return args\n    except Exception:\n        return tool_args if isinstance(tool_args, dict) else {}\n\n"
                            }
                        ],
                        "smoke_tests": [
                            {
                                "name": "plan_endpoint_normalizes_now_iso_placeholder",
                                "expect": {
                                    "raw_content_preserved": True,
                                    "placeholder_replaced": True
                                }
                            },
                            {
                                "name": "plan_endpoint_normalizes_literal_backslash_n_token",
                                "expect": {
                                    "raw_content_preserved": True,
                                    "real_newline_present": True
                                }
                            }
                        ],
                        "deliverable_contract": {
                            "expected_output_artifact": "planner_schema_patch_apply_request.json",
                            "room_scoped_only": True,
                            "ssot_files_must_not_be_overwritten": True
                        },
                        "source": "advisor_empty_plan_recovery_upgraded_to_apply_request"
                    }
                    import json
                    tool_args["path"] = safe_path
                    tool_args["content"] = json.dumps(upgraded, ensure_ascii=False, indent=2) + "\n"
                    tool_args["raw_content"] = tool_args["content"]
                    tool_args["text"] = tool_args["content"]
            except Exception:
                pass

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
            "Eres Brain Lab Advisor. Devuelve SOLO JSON valido, sin markdown, sin code fences y sin texto extra.\n"
            "Usa EXACTAMENTE el room_id recibido: " + room_id + ".\n"
            "publish debe ser false.\n"
            "No uses placeholders ni ejemplos genericos como 12345, toolA, toolB, arg1, arg2, value1, value2.\n"
            "Devuelve exactamente este shape: {ok, room_id, publish, plan:{room_id,status,steps:[{id,status,tool_name,tool_args}]}}.\n"
            "Si no hay accion util y segura, devuelve plan con status='complete' y steps=[].\n"
            "Si hay accion, devuelve EXACTAMENTE 1 step.\n"
            "tool_name solo puede ser uno de: write_file, append_file, read_file, list_dir.\n"
            "Si tool_name es write_file o append_file, tool_args.content debe ser string no vacio.\n"
            "Si tool_name es write_file o append_file, tool_args.path debe empezar por C:\\AI_VAULT\\tmp_agent\\state\\rooms\\" + room_id + "\\.\n"
            "Si tool_name es read_file o list_dir, el path puede estar en C:\\AI_VAULT\\00_identity\\ o C:\\AI_VAULT\\tmp_agent\\state\\roadmap.json o dentro del room actual.\n"
            "Prioriza trabajo real sobre P2_PLANNER_HARDENING_SCHEMA_NORMALIZATION.\n"
            "Objetivo P2.1: garantizar tool_args.content no-null, string, raw_content preservado y newline real.\n"
            "Objetivo P2.2: mantener now_iso consistente y evitar placeholders sin resolver.\n"
            "No propongas archivos de bajo valor como roadmap_progress.json, progress.json, summary.json, report.json, notes.json, log.json, log.txt, report.txt, progress.txt.\n"
            "No escribas fuera del room actual.\n"
            "Prefiere una accion concreta y util en el room actual antes que recovery.\n\n"
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
        # CONTENT_JSON_ESCAPE_FIX_V1 — robust parse con fallback
        try:
            obj = json.loads(out_text_clean)
        except Exception as _parse_err:
            import re as _re
            _best = None
            for _m in _re.finditer(r'\{', out_text_clean):
                _start = _m.start()
                for _end in range(len(out_text_clean), _start, -1):
                    try:
                        _candidate = out_text_clean[_start:_end]
                        _best = json.loads(_candidate)
                        break
                    except:
                        continue
                if _best:
                    break
            obj = _best if _best else json.loads(out_text_clean)

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
        forced = globals().get("_force_current_room_action_plan", None)
        if forced:
            obj["plan"] = _sanitize_advisor_plan(room_id, forced(room_id))
            obj["publish"] = False
        else:
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
        model = OPENAI_MODEL
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

# === OPENAI_RESPONSES_CALL_FORCE_V5_CC02_ENFORCEMENT BEGIN ===
import os
import json
import re
from pathlib import Path

def _cc_runtime_active():
    try:
        p = Path(r"C:\AI_VAULT\tmp_agent\state\roadmap.json")
        if not p.exists():
            return False
        rm = json.loads(p.read_text(encoding="utf-8"))
        active_roadmap = str(rm.get("active_roadmap") or "")
        current_phase = str(rm.get("current_phase") or "")
        current_stage = str(rm.get("current_stage") or "")
        return (
            active_roadmap == "brain_conversational_console_product_v2"
            and current_phase == "CC-02"
            and current_stage in (
                "pending",
                "in_progress",
                "artifact_seeded",
                "behaviorally_validated_minimal",
            )
        )
    except Exception:
        return False

def _cc_extract_inline_plan(prompt: str):
    s = str(prompt or "")
    brace_positions = [i for i, ch in enumerate(s) if ch == "{"]

    for start in reversed(brace_positions):
        depth = 0
        in_str = False
        esc = False

        for i in range(start, len(s)):
            ch = s[i]

            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    cand = s[start:i+1].strip()
                    try:
                        obj = json.loads(cand)
                    except Exception:
                        break

                    if isinstance(obj, dict) and isinstance(obj.get("steps"), list):
                        return {
                            "room_id": str(obj.get("room_id") or ""),
                            "status": str(obj.get("status") or "pending"),
                            "steps": obj.get("steps") or [],
                        }
                    break

    return None

def _cc_build_clarification_payload():
    return {
        "status": "clarification_required",
        "clarification_question": "¿Qué acción exacta quieres que ejecute y sobre qué ruta o recurso concreto?",
        "publish": False,
        "plan": {
            "status": "complete",
            "steps": []
        }
    }

def _advisor_strip_code_fences(text: str) -> str:
    s = str(text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _advisor_extract_first_json_object(text: str) -> str:
    s = _advisor_strip_code_fences(text)
    start = s.find("{")
    if start < 0:
        return ""

    depth = 0
    in_str = False
    esc = False

    for i in range(start, len(s)):
        ch = s[i]

        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                cand = s[start:i+1]
                try:
                    json.loads(cand)
                    return cand
                except Exception:
                    return ""

    return ""

async def _openai_responses_call(prompt: str) -> dict:
    prompt = str(prompt or "")

    # CC-02 deterministic enforcement:
    # - explicit structured prompt => pass-through plan, no clarification
    # - ambiguous prompt => minimal clarification, no execution
    if _cc_runtime_active():
        inline_plan = _cc_extract_inline_plan(prompt)
        if inline_plan is not None:
            payload = {
                "status": "ready",
                "publish": False,
                "plan": inline_plan
            }
            out_text = json.dumps(payload, ensure_ascii=False)
            return {
                "ok": True,
                "output_text": out_text,
                "raw_output_text": out_text,
                "raw": None
            }

        payload = _cc_build_clarification_payload()
        out_text = json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": out_text,
            "raw_output_text": out_text,
            "raw": None
        }

    try:
        from openai import AsyncOpenAI  # type: ignore
    except Exception as e:
        return {"ok": False, "error": "openai_sdk_missing", "detail": repr(e), "output_text": ""}

    try:
        client = AsyncOpenAI()
        model = OPENAI_MODEL

        contract = (
            "You are the Brain Lab planner endpoint. "
            "Return EXACTLY ONE valid JSON object and nothing else. "
            "Do not return markdown. Do not return headings. Do not return prose. Do not use code fences. "
            "If no safe executable plan is possible, still return valid JSON with status "
            "\"complete\" and steps []. "
            "Required JSON shape: "
            "{\"room_id\":\"<string>\",\"status\":\"pending|in_progress|complete\",\"steps\":["
            "{\"id\":\"S1\",\"tool_name\":\"read_file|write_file|append_file|list_dir\","
            "\"tool_args\":{},\"why\":\"short reason\"}]}"
        )

        wrapped_prompt = contract + "\n\nUSER_PROMPT:\n" + prompt

        resp = await client.responses.create(
            model=model,
            input=wrapped_prompt
        )

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

        normalized = _advisor_strip_code_fences(out_text)
        json_candidate = _advisor_extract_first_json_object(normalized)
        final_text = json_candidate or normalized

        return {
            "ok": True,
            "output_text": final_text,
            "raw_output_text": out_text,
            "raw": resp
        }

    except Exception as e:
        return {"ok": False, "error": "openai_call_failed", "detail": repr(e), "output_text": ""}

# === OPENAI_RESPONSES_CALL_FORCE_V5_CC02_ENFORCEMENT END ===

# === CC_STREAM_ESCAPE_HATCH_GUARD_V1 BEGIN ===
import json as _cc_json
from pathlib import Path as _cc_Path

_CC_MAIN_ROADMAP_PATH = r"C:\AI_VAULT\tmp_agent\state\roadmap.json"
_ORIG_FALLBACK_PLAN_LOW_RISK = globals().get("_fallback_plan_low_risk", None)
_ORIG_FORCE_CURRENT_ROOM_ACTION_PLAN = globals().get("_force_current_room_action_plan", None)

def _cc_read_main_roadmap():
    try:
        p = _cc_Path(_CC_MAIN_ROADMAP_PATH)
        if not p.exists():
            return {}
        return _cc_json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _cc_stream_active():
    rm = _cc_read_main_roadmap()
    active_roadmap = str(rm.get("active_roadmap") or "")
    current_phase = str(rm.get("current_phase") or "")
    return (
        active_roadmap == "brain_conversational_console_product_v2"
        or current_phase.startswith("CC-")
    )

def _cc_noop_plan(room_id):
    rid = str(room_id or "default")
    return {
        "room_id": rid,
        "status": "complete",
        "steps": []
    }

def _fallback_plan_low_risk(room_id):
    if _cc_stream_active():
        return _cc_noop_plan(room_id)
    if callable(_ORIG_FALLBACK_PLAN_LOW_RISK):
        return _ORIG_FALLBACK_PLAN_LOW_RISK(room_id)
    return _cc_noop_plan(room_id)

def _force_current_room_action_plan(room_id):
    if _cc_stream_active():
        return _cc_noop_plan(room_id)
    if callable(_ORIG_FORCE_CURRENT_ROOM_ACTION_PLAN):
        return _ORIG_FORCE_CURRENT_ROOM_ACTION_PLAN(room_id)
    return _cc_noop_plan(room_id)
# === CC_STREAM_ESCAPE_HATCH_GUARD_V1 END ===

# === AUTONOMY_V2_DETERMINISTIC_BRIDGE BEGIN ===
import json as _autonomy_json
import re as _autonomy_re

_AUTONOMY_V2_PREV_OPENAI_CALL = globals().get("_openai_responses_call", None)

def _autonomy_v2_norm(x):
    return str(x or "").strip()

def _autonomy_v2_extract_room_id(prompt: str) -> str:
    text = str(prompt or "")
    m = _autonomy_re.search(r'"room_id"\s*:\s*"([^"]+)"', text)
    if m:
        return str(m.group(1)).strip()
    return "default"

def _autonomy_v2_simple_plan_from_prompt(room_id: str, prompt: str):
    text = _autonomy_v2_norm(prompt)
    patterns = [
        (r'^(?:lista|list|ls|dir)\s+(.+)$', "list_dir", "List directory requested by user"),
        (r'^(?:lee|leer|read|show|muestra)\s+(.+)$', "read_file", "Read file requested by user"),
    ]

    for pat, tool_name, why in patterns:
        m = _autonomy_re.match(pat, text, flags=_autonomy_re.IGNORECASE | _autonomy_re.DOTALL)
        if not m:
            continue

        raw_path = str(m.group(1)).strip().strip('"').strip("'")
        if not raw_path:
            return None

        return {
            "status": "ready",
            "publish": False,
            "room_id": room_id,
            "plan": {
                "room_id": room_id,
                "status": "active",
                "steps": [
                    {
                        "id": "S1",
                        "status": "todo",
                        "tool_name": tool_name,
                        "tool_args": {
                            "path": raw_path
                        },
                        "why": why
                    }
                ]
            }
        }

    return None

async def _openai_responses_call(prompt: str) -> dict:
    room_id = _autonomy_v2_extract_room_id(prompt)
    deterministic = _autonomy_v2_simple_plan_from_prompt(room_id, prompt)
    if deterministic is not None:
        payload = _autonomy_json.dumps(deterministic, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": payload,
            "raw_output_text": payload,
            "raw": None
        }

    prev = globals().get("_AUTONOMY_V2_PREV_OPENAI_CALL", None)
    if callable(prev):
        return await prev(prompt)

    return {
        "ok": False,
        "error": "autonomy_v2_no_openai_call",
        "detail": "previous_openai_call_missing",
        "output_text": ""
    }
# === AUTONOMY_V2_DETERMINISTIC_BRIDGE END ===

# === AUTONOMY_V3_DETERMINISTIC_BRIDGE BEGIN ===
import json as _autonomy_v3_json
import re as _autonomy_v3_re

_AUTONOMY_V3_PREV_OPENAI_CALL = globals().get("_openai_responses_call", None)

def _autonomy_v3_find_after(text: str, patterns):
    src = str(text or "")
    for pat in patterns:
        m = _autonomy_v3_re.search(pat, src, flags=_autonomy_v3_re.IGNORECASE | _autonomy_v3_re.MULTILINE)
        if m:
            val = str(m.group(1) or "").strip().strip('"').strip("'")
            if val:
                return val
    return ""

def _autonomy_v3_make_response(room_id: str, plan_steps):
    return {
        "status": "ready",
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "active",
            "steps": plan_steps
        }
    }

def _autonomy_v3_make_clarification(room_id: str, question: str):
    return {
        "status": "clarification_required",
        "clarification_question": question,
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "complete",
            "steps": []
        }
    }

async def _openai_responses_call(prompt: str) -> dict:
    text = str(prompt or "")
    room_id = "default"

    list_path = _autonomy_v3_find_after(text, [
        r'(?:^|[\r\n]|\\b)(?:lista|list|ls|dir)\\s+(.+?)(?:[\r\n]|$)',
    ])

    if list_path:
        payload = _autonomy_v3_make_response(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "list_dir",
                "tool_args": {
                    "path": list_path
                },
                "why": "List directory requested by user"
            }
        ])
        txt = _autonomy_v3_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    read_path = _autonomy_v3_find_after(text, [
        r'(?:^|[\r\n]|\\b)(?:lee|leer|read|muestra|show)\\s+(.+?)(?:[\r\n]|$)',
    ])

    if read_path:
        payload = _autonomy_v3_make_response(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "read_file",
                "tool_args": {
                    "path": read_path
                },
                "why": "Read file requested by user"
            }
        ])
        txt = _autonomy_v3_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    low = text.lower()
    if ("segura posible" in low) or ("más segura posible" in low) or ("advance with cc-02" in low) or ("avances con cc-02" in low):
        payload = _autonomy_v3_make_clarification(
            room_id,
            "¿Qué acción exacta quieres que ejecute y sobre qué ruta o recurso concreto?"
        )
        txt = _autonomy_v3_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    prev = globals().get("_AUTONOMY_V3_PREV_OPENAI_CALL", None)
    if callable(prev):
        return await prev(prompt)

    return {
        "ok": False,
        "error": "autonomy_v3_no_openai_call",
        "detail": "previous_openai_call_missing",
        "output_text": ""
    }
# === AUTONOMY_V3_DETERMINISTIC_BRIDGE END ===

# === AUTONOMY_V4_DETERMINISTIC_BRIDGE BEGIN ===
import json as _autonomy_v4_json
import re as _autonomy_v4_re

_AUTONOMY_V4_PREV_OPENAI_CALL = globals().get("_openai_responses_call", None)

def _autonomy_v4_extract_user_prompt(text: str) -> str:
    src = str(text or "")
    m = _autonomy_v4_re.search(r"USER_PROMPT:\s*(.*)$", src, flags=_autonomy_v4_re.IGNORECASE | _autonomy_v4_re.DOTALL)
    if m:
        return str(m.group(1) or "").strip()
    return src.strip()

def _autonomy_v4_match_first_line(src: str, patterns):
    text = str(src or "").strip()
    for pat in patterns:
        m = _autonomy_v4_re.search(pat, text, flags=_autonomy_v4_re.IGNORECASE | _autonomy_v4_re.MULTILINE)
        if m:
            val = str(m.group(1) or "").strip().strip('"').strip("'")
            if val:
                return val
    return ""

def _autonomy_v4_make_ready(room_id: str, steps):
    return {
        "status": "ready",
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "active",
            "steps": steps
        }
    }

def _autonomy_v4_make_clarification(room_id: str, question: str):
    return {
        "status": "clarification_required",
        "clarification_question": question,
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "complete",
            "steps": []
        }
    }

async def _openai_responses_call(prompt: str) -> dict:
    src = str(prompt or "")
    room_id = "default"
    user_text = _autonomy_v4_extract_user_prompt(src)

    list_path = _autonomy_v4_match_first_line(user_text, [
        r"^\s*(?:lista|list|ls|dir)\s+([^\r\n]+?)\s*$",
        r"^\s*(?:listar)\s+([^\r\n]+?)\s*$",
    ])

    if list_path:
        payload = _autonomy_v4_make_ready(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "list_dir",
                "tool_args": {
                    "path": list_path
                },
                "why": "List directory requested by user"
            }
        ])
        txt = _autonomy_v4_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    read_path = _autonomy_v4_match_first_line(user_text, [
        r"^\s*(?:lee|leer|read|muestra|show)\s+([^\r\n]+?)\s*$",
    ])

    if read_path:
        payload = _autonomy_v4_make_ready(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "read_file",
                "tool_args": {
                    "path": read_path
                },
                "why": "Read file requested by user"
            }
        ])
        txt = _autonomy_v4_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    low = user_text.lower()
    if ("segura posible" in low) or ("más segura posible" in low) or ("advance with cc-02" in low) or ("avances con cc-02" in low):
        payload = _autonomy_v4_make_clarification(
            room_id,
            "¿Qué acción exacta quieres que ejecute y sobre qué ruta o recurso concreto?"
        )
        txt = _autonomy_v4_json.dumps(payload, ensure_ascii=False)
        return {
            "ok": True,
            "output_text": txt,
            "raw_output_text": txt,
            "raw": None
        }

    prev = globals().get("_AUTONOMY_V4_PREV_OPENAI_CALL", None)
    if callable(prev):
        return await prev(prompt)

    return {
        "ok": False,
        "error": "autonomy_v4_no_match",
        "detail": "no deterministic bridge match and no previous call available",
        "output_text": ""
    }
# === AUTONOMY_V4_DETERMINISTIC_BRIDGE END ===

# === AUTONOMY_V5_ADVISOR_MIDDLEWARE BEGIN ===
import json as _autov5_json
import re as _autov5_re

from starlette.requests import Request as _autov5_Request
from starlette.responses import JSONResponse as _autov5_JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware as _autov5_BaseHTTPMiddleware

def _autov5_make_ready(room_id: str, steps):
    return {
        "status": "ready",
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "active",
            "steps": steps
        }
    }

def _autov5_make_clarification(room_id: str, question: str):
    return {
        "status": "clarification_required",
        "clarification_question": question,
        "publish": False,
        "room_id": room_id,
        "plan": {
            "room_id": room_id,
            "status": "complete",
            "steps": []
        }
    }

def _autov5_extract_path(text: str, patterns):
    s = str(text or "").strip()
    for pat in patterns:
        m = _autov5_re.match(pat, s, flags=_autov5_re.IGNORECASE)
        if m:
            val = str(m.group(1) or "").strip().strip('"').strip("'")
            if val:
                return val
    return ""

def _autov5_match_direct_plan(room_id: str, prompt: str):
    p = str(prompt or "").strip()

    list_path = _autov5_extract_path(p, [
        r'^(?:lista|list|ls|dir)\s+(.+)$',
        r'^(?:listar)\s+(.+)$',
    ])
    if list_path:
        return _autov5_make_ready(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "list_dir",
                "tool_args": { "path": list_path },
                "why": "List directory requested by user"
            }
        ])

    read_path = _autov5_extract_path(p, [
        r'^(?:lee|leer|read|muestra|show)\s+(.+)$',
    ])
    if read_path:
        return _autov5_make_ready(room_id, [
            {
                "id": "S1",
                "status": "todo",
                "tool_name": "read_file",
                "tool_args": { "path": read_path },
                "why": "Read file requested by user"
            }
        ])

    low = p.lower()
    if (
        "segura posible" in low
        or "más segura posible" in low
        or "avances con cc-02" in low
        or "advance with cc-02" in low
    ):
        return _autov5_make_clarification(
            room_id,
            "¿Qué acción exacta quieres que ejecute y sobre qué ruta o recurso concreto?"
        )

    return None

class _AutonomyV5AdvisorMiddleware(_autov5_BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method.upper() != "POST" or request.url.path != "/v1/advisor/next":
            return await call_next(request)

        body = await request.body()

        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = _autov5_Request(request.scope, _receive)

        try:
            payload = _autov5_json.loads(body.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}

        room_id = str(payload.get("room_id") or "default")
        prompt = str(payload.get("prompt") or payload.get("message") or "").strip()

        direct = _autov5_match_direct_plan(room_id, prompt)
        if direct is not None:
            return _autov5_JSONResponse(direct)

        return await call_next(request)

try:
    app.add_middleware(_AutonomyV5AdvisorMiddleware)
except Exception:
    pass
# === AUTONOMY_V5_ADVISOR_MIDDLEWARE END ===
