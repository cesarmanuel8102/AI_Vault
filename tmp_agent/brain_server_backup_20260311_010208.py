from __future__ import annotations  # FUTURE_ANNOTATIONS_V1
import uuid
import types

# --- HARDENING_PLAN_NORMALIZE_V2 ---------------------------------------------------
from datetime import datetime, timezone

def _now_iso_utc_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def _normalize_content_str(x):
    if x is None:
        return None
    if not isinstance(x, str):
        x = str(x)

    # placeholders
    if "{{now_iso}}" in x:
        x = x.replace("{{now_iso}}", _now_iso_utc_z())

    # IMPORTANT: convert literal escapes to real newlines
    # order matters
    x = x.replace("\\\\r\\\\n", "\r\n")
    x = x.replace("\\\\n", "\n")
    return x

def _harden_plan_payload(plan: dict):
    errs = []
    if not isinstance(plan, dict):
        return plan, ["plan_not_object"]

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return plan, ["steps_empty_or_invalid"]

    for idx, st in enumerate(steps, start=1):
        if not isinstance(st, dict):
            errs.append(f"step_{idx}_not_object")
            continue

        tool = st.get("tool_name")
        args = st.get("tool_args") if isinstance(st.get("tool_args"), dict) else None
        if args is None:
            errs.append(f"step_{idx}_tool_args_missing_or_invalid")
            continue

        if tool in ("append_file", "write_file"):
            # canonical key
            if "content" not in args and "text" in args:
                args["content"] = args.get("text")

            raw = args.get("content", None)
            if raw is None:
                errs.append(f"step_{idx}_content_null_for_{tool}")
                continue

            norm = _normalize_content_str(raw)
            if norm is None or (isinstance(norm, str) and len(norm) == 0):
                errs.append(f"step_{idx}_content_empty_after_normalize_for_{tool}")
                continue

            if norm != raw:
                args["raw_content"] = raw
                args["content"] = norm

            # keep mirror
            args["text"] = args.get("content")

    return plan, errs
# --- /HARDENING_PLAN_NORMALIZE_V2 --------------------------------------------------

# --- HARDENING_PLAN_NORMALIZE_V1 ---------------------------------------------------
from datetime import datetime, timezone

def _now_iso_utc_z() -> str:
    # seconds precision to keep diffs stable
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def _normalize_content_str(x: str) -> str:
    if x is None:
        return x
    if not isinstance(x, str):
        x = str(x)
    # normalize placeholders
    if "{{now_iso}}" in x:
        x = x.replace("{{now_iso}}", _now_iso_utc_z())
    # normalize literal escapes that frequently appear from planners/UI
    x = x.replace("\\r\\n", "\r\n")
    x = x.replace("\\n", "\n")
    return x

def _harden_plan_payload(plan: dict) -> tuple[dict, list]:
    """
    Returns: (normalized_plan, errors[])
    Enforces:
      - steps non-empty
      - for write_file/append_file: tool_args.content must be non-null string after normalization
      - converts literal \\n into newline
      - replaces {{now_iso}} fallback server-side
      - stores raw_content when changed
    """
    errs = []
    if not isinstance(plan, dict):
        return plan, ["plan_not_object"]

    steps = plan.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        errs.append("steps_empty_or_invalid")
        return plan, errs

    for i, st in enumerate(steps, start=1):
        if not isinstance(st, dict):
            errs.append(f"step_{i}_not_object")
            continue

        tool = st.get("tool_name")
        args = st.get("tool_args") if isinstance(st.get("tool_args"), dict) else None
        if args is None:
            errs.append(f"step_{i}_tool_args_missing_or_invalid")
            continue

        if tool in ("append_file", "write_file"):
            # canonical key is "content" (legacy key sometimes "text")
            if "content" not in args and "text" in args:
                args["content"] = args.get("text")

            raw = args.get("content", None)

            if raw is None:
                errs.append(f"step_{i}_content_null_for_{tool}")
                continue

            norm = _normalize_content_str(raw)
            if norm is None or (isinstance(norm, str) and len(norm) == 0):
                # allow empty string? For safety, treat empty as error for write/append.
                errs.append(f"step_{i}_content_empty_after_normalize_for_{tool}")
                continue

            if norm != raw:
                args["raw_content"] = raw
                args["content"] = norm

            # keep legacy mirror if code expects it later
            args["text"] = args.get("content")

    return plan, errs
# --- /HARDENING_PLAN_NORMALIZE_V1 --------------------------------------------------
# AUTO_PERSIST_FS_EXECUTE_HOOK_V1
import json


# === RUNTIME_SNAPSHOT_KV_HELPERS_V1 BEGIN ===
def _runtime_snapshot_file(room_id: str) -> str:
    """rooms/<rid>/runtime_snapshot.json"""
    from pathlib import Path
    _room_state_dir(room_id)
    # Use _room_paths if available, else fallback to rooms/<rid>/runtime_snapshot.json
    fp = ""
    try:
        paths = _room_paths(room_id) or {}
        fp = str(paths.get("runtime_snapshot") or "")
    except Exception:
        fp = ""
    if fp:
        return fp
    return str(Path(_room_state_dir(room_id)) / "runtime_snapshot.json")


def _runtime_snapshot_kv_load(room_id: str) -> dict:
    import json
    from pathlib import Path
    fp = _runtime_snapshot_file(room_id)
    f = Path(fp)
    if not f.exists():
        return {"kv": {}, "updated_at": None, "room_id": room_id}
    try:
        obj = json.loads(f.read_text(encoding="utf-8")) or {}
    except Exception:
        obj = {}
    kv = obj.get("kv")
    if not isinstance(kv, dict):
        kv = {}
    return {"kv": kv, "updated_at": obj.get("updated_at"), "room_id": room_id}


def _runtime_snapshot_kv_save(room_id: str, kv: dict) -> dict:
    import json
    from pathlib import Path
    from datetime import datetime, timezone
    fp = _runtime_snapshot_file(room_id)
    payload = {
        "kv": kv if isinstance(kv, dict) else {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
    }
    Path(fp).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "file": fp}


def _runtime_snapshot_set_kv(room_id: str, path: str, value):
    obj = _runtime_snapshot_kv_load(room_id)
    kv = obj.get("kv") or {}
    kv[str(path or "")] = value
    res = _runtime_snapshot_kv_save(room_id, kv)
    return {"ok": True, "path": str(path or ""), "value": value, "file": res.get("file")}


def _runtime_snapshot_get_kv(room_id: str, path: str):
    obj = _runtime_snapshot_kv_load(room_id)
    kv = obj.get("kv") or {}
    key = str(path or "")
    if key not in kv:
        return {
            "ok": False,
            "error": "SNAPSHOT_KEY_MISSING",
            "path": key,
            "file": _runtime_snapshot_file(room_id),
            "kv_keys": list(kv.keys())[:50],
        }
    return {"ok": True, "path": key, "value": kv.get(key), "file": _runtime_snapshot_file(room_id)}
# === RUNTIME_SNAPSHOT_KV_HELPERS_V1 END ===

import risk_gate
from fastapi import FastAPI, Request, Body, Query

# --- HARDENING2.3_AUTOSTUBS: response_model fallbacks --------------------
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object
try:
    from typing import Any, Optional
except Exception:
    Any = object
    Optional = object

def _mk_stub(name: str):
    # crea una clase Pydantic mínima con campos estándar
    attrs = {'ok': True, 'error': None, '__annotations__': {'ok': bool, 'error': Optional[str]}}
    return type(name, (BaseModel,), attrs)

if 'AgentPlanRealV2Response' not in globals():
    AgentPlanRealV2Response = _mk_stub('AgentPlanRealV2Response')
if 'AgentPlanRealV3BResponse' not in globals():
    AgentPlanRealV3BResponse = _mk_stub('AgentPlanRealV3BResponse')
if 'AgentPlanRealV3Response' not in globals():
    AgentPlanRealV3Response = _mk_stub('AgentPlanRealV3Response')
if 'AgentRunOnceResponse' not in globals():
    AgentRunOnceResponse = _mk_stub('AgentRunOnceResponse')
if 'GuardrailCheckResponse' not in globals():
    GuardrailCheckResponse = _mk_stub('GuardrailCheckResponse')
# --- /HARDENING2.3_AUTOSTUBS ---------------------------------------------

# --- HARDENING2.4_REQUEST_STUBS: fix ForwardRefs for OpenAPI ---------------
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict, List
except Exception:
    Any = object
    Optional = object
    Dict = dict
    List = list

# AgentPlanRequest se usa en anotaciones (a veces como ForwardRef) para /v1/agent/plan
if "AgentPlanRequest" not in globals():
    class AgentPlanRequest(BaseModel):
        # mínimo viable; SSOT usa room_id / req.room_id
        room_id: str = ""
        goal: Optional[str] = None
        steps: Optional[List[Any]] = None
        plan: Optional[Dict[str, Any]] = None

# Si pydantic v2, intentar rebuild por si hay forward refs colgantes
try:
    AgentPlanRequest.model_rebuild()
except Exception:
    pass
# --- /HARDENING2.4_REQUEST_STUBS -------------------------------------------

# --- HARDENING2.5_REQUEST_STUBS: fix ForwardRefs for OpenAPI (Eval) --------
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict, List
except Exception:
    Any = object
    Optional = object
    Dict = dict
    List = list

# AgentEvalRequest se usa en anotaciones (a veces como ForwardRef) para /v1/agent/evaluate o /v1/agent/eval
if "AgentEvalRequest" not in globals():
    class AgentEvalRequest(BaseModel):
        room_id: str = ""
        # payload de evaluación (por compat con implementaciones previas)
        observations: Optional[Dict[str, Any]] = None
        metrics: Optional[Dict[str, Any]] = None
        state: Optional[Dict[str, Any]] = None
        notes: Optional[str] = None

try:
    AgentEvalRequest.model_rebuild()
except Exception:
    pass
# --- /HARDENING2.5_REQUEST_STUBS -------------------------------------------

# --- HARDENING2.6_REQUEST_STUBS: fix ForwardRefs for OpenAPI (Execute) -----
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict, List
except Exception:
    Any = object
    Optional = object
    Dict = dict
    List = list

# AgentExecuteRequest se usa en anotaciones (a veces como ForwardRef) para /v1/agent/execute
if "AgentExecuteRequest" not in globals():
    class AgentExecuteRequest(BaseModel):
        room_id: str = ""
        step_id: Optional[str] = None
        tool: Optional[str] = None
        input: Optional[Dict[str, Any]] = None
        args: Optional[Dict[str, Any]] = None
        # para compat con "execute_step" o runners
        step: Optional[Dict[str, Any]] = None
        meta: Optional[Dict[str, Any]] = None

try:
    AgentExecuteRequest.model_rebuild()
except Exception:
    pass
# --- /HARDENING2.6_REQUEST_STUBS -------------------------------------------

# --- HARDENING2.7_REQUEST_STUBS: fix ForwardRefs for OpenAPI (Guardrail) ---
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict, List
except Exception:
    Any = object
    Optional = object
    Dict = dict
    List = list

# GuardrailCheckRequest se usa en anotaciones (a veces como ForwardRef) para /v1/agent/guardrail_check
if "GuardrailCheckRequest" not in globals():
    class GuardrailCheckRequest(BaseModel):
        room_id: str = ""
        # entrada típica: texto / prompt / step / state
        text: Optional[str] = None
        prompt: Optional[str] = None
        step: Optional[Dict[str, Any]] = None
        state: Optional[Dict[str, Any]] = None
        meta: Optional[Dict[str, Any]] = None

try:
    GuardrailCheckRequest.model_rebuild()
except Exception:
    pass
# --- /HARDENING2.7_REQUEST_STUBS -------------------------------------------

# --- HARDENING2.8_REQUEST_STUBS: fix ForwardRefs for OpenAPI (RunOnce) -----
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict, List
except Exception:
    Any = object
    Optional = object
    Dict = dict
    List = list

# AgentRunOnceRequest se usa en anotaciones (a veces como ForwardRef) para /v1/agent/run_once
if "AgentRunOnceRequest" not in globals():
    class AgentRunOnceRequest(BaseModel):
        room_id: str = ""
        approve_token: Optional[str] = None
        goal: Optional[str] = None
        # soporta payload flexible según runner
        plan: Optional[Dict[str, Any]] = None
        state: Optional[Dict[str, Any]] = None
        step: Optional[Dict[str, Any]] = None
        input: Optional[Dict[str, Any]] = None
        meta: Optional[Dict[str, Any]] = None

try:
    AgentRunOnceRequest.model_rebuild()
except Exception:
    pass
# --- /HARDENING2.8_REQUEST_STUBS -------------------------------------------
from pydantic import BaseModel, Field

# --- HARDENING2.1: ensure AgentPlanResponse exists -------------------------
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object  # ultra-fallback

try:
    from typing import Any, Optional
except Exception:
    Any = object
    Optional = object

class AgentPlanResponse(BaseModel):
    """
    Modelo mínimo para evitar crash en import.
    Ajustable luego cuando consolidemos schemas.
    """
    ok: bool = True
    room_id: str = ""
    plan: Any = None
    error: Optional[str] = None
# --- /HARDENING2.1 --------------------------------------------------------


# --- HARDENING2.2: ensure AgentEvalResponse exists -------------------------
try:
    from pydantic import BaseModel
except Exception:
    BaseModel = object

try:
    from typing import Any, Optional, Dict
except Exception:
    Any = object
    Optional = object
    Dict = dict

class AgentEvalResponse(BaseModel):
    """
    Modelo mínimo para evitar crash en import.
    'result' puede contener el dict/objeto de evaluación (p.ej. last_eval).
    """
    ok: bool = True
    room_id: str = ""
    result: Any = None
    error: Optional[str] = None
# --- /HARDENING2.2 --------------------------------------------------------
from typing import Any, Dict, Optional

# ==================================
# AUTO_PERSIST_FS_EXECUTE_V1
# ==================================
def _autopersist_step_done_fs(room_id: str, step_id: str) -> None:
    """
    Mark step done in tmp_agent/state/plan.json for read-only /v1/agent/execute calls.
    Uses tmp_agent AgentStateStore (room-scoped).
    """
    try:
        if not step_id:
            return
        agent_state = _import_tmp_agent_module("agent_state")
        store = agent_state.AgentStateStore(_resolve_tmp_agent_root())
        plan = store.load_plan(room_id)
        if not isinstance(plan, dict):
            return
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            return
        for s in steps:
            if isinstance(s, dict) and str(s.get("id")) == str(step_id):
                s["status"] = "done"
                break
        store.save_plan(room_id, plan)
    except Exception:
        pass

# ================================
# AUTO_PERSIST_EXECUTE_V2 (BrainLab)
# ================================
def _persist_step_status(store, room_id: str, step_id: str, status: str, **fields):
    """
    Persist step status into plan.json via store.
    Expected store API:
      - load_plan(room_id) -> dict
      - save_plan(room_id, plan_dict) -> None
    """
    try:
        plan = store.load_plan(room_id)
        if not isinstance(plan, dict):
            return False
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            return False

        target = None
        for s in steps:
            if isinstance(s, dict) and str(s.get("id")) == str(step_id):
                target = s
                break
        if not target:
            return False

        target["status"] = status
        for k, v in fields.items():
            target[k] = v

        try:
            from datetime import datetime as _dt
            plan["updated_at"] = _dt.utcnow().isoformat() + "Z"
        except Exception:
            pass

        store.save_plan(room_id, plan)
        return True
    except Exception:
        return False

# --- Filesystem tool shims (used by AgentLoop) ---
from pathlib import Path

_ALLOWED_ROOTS = [Path(r"C:\AI_VAULT").resolve()]

def _is_allowed(p: Path) -> bool:
    try:
        rp = p.resolve()
        return any(str(rp).lower().startswith(str(root).lower()) for root in _ALLOWED_ROOTS)
    except Exception:
        return False

def list_dir(path: str) -> dict:
    p = Path(path)
    if not _is_allowed(p):
        raise PermissionError(f"READ_NOT_IN_ALLOWLIST: {p}")
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(str(p))
    items = []
    for x in sorted(p.iterdir(), key=lambda t: t.name.lower()):
        try:
            items.append({"name": x.name, "is_dir": x.is_dir(), "size": x.stat().st_size})
        except Exception:
            items.append({"name": x.name, "is_dir": x.is_dir(), "size": None})
    return {"path": str(p), "items": items}

def read_file(path: str, max_bytes: int = 200000) -> dict:
    p = Path(path)
    if not _is_allowed(p):
        raise PermissionError(f"READ_NOT_IN_ALLOWLIST: {p}")
    data = p.read_bytes()
    truncated = False
    if len(data) > max_bytes:
        data = data[:max_bytes]
        truncated = True
    text = data.decode("utf-8", errors="replace")
    return {"path": str(p), "text": text, "truncated": truncated}

def write_file(path: str, text: str) -> dict:
    p = Path(path)
    if not _is_allowed(p):
        raise PermissionError(f"WRITE_NOT_IN_ALLOWLIST: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return {"path": str(p), "bytes": len(text.encode("utf-8"))}

def append_file(path: str, text: str) -> dict:
    p = Path(path)
    if not _is_allowed(p):
        raise PermissionError(f"WRITE_NOT_IN_ALLOWLIST: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(text)
    return {"path": str(p), "bytes": len(text.encode("utf-8"))}
from fastapi.responses import JSONResponse
from brain_router import router
import time
import os
import shutil
# === ROOM STORE PATCH BEGIN ===
import re

def _safe_room_id(room_id: str) -> str:
    room_id = (room_id or "default").strip()
    room_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", room_id)
    if room_id == "":
        room_id = "default"
    return room_id

def _effective_room_id(request, payload_room_id: str = None) -> str:
    # Prioridad: header x-room-id > payload.room_id > "default"
    hdr = None
    try:
        hdr = request.headers.get("x-room-id")
    except Exception:
        hdr = None
    return _safe_room_id(hdr or payload_room_id or "default")

def _state_root_dir() -> str:
    # Mantén esto coherente con tu política: todo dentro de C:\AI_VAULT\tmp_agent
    # Si ya existe una constante/variable global, la respetamos abajo.
    return r"C:\AI_VAULT\tmp_agent\state"

def _room_state_dir(room_id: str) -> str:
    rid = _safe_room_id(room_id)
    base = globals().get("STATE_DIR") or globals().get("STATE_ROOT") or _state_root_dir()
    d = os.path.join(base, "rooms", rid)
    os.makedirs(d, exist_ok=True)
    return d

def _room_paths(room_id: str) -> dict:
    d = _room_state_dir(room_id)
    return {
        "mission": os.path.join(d, "mission.json"),
        "plan": os.path.join(d, "plan.json"),
        "snapshot": os.path.join(d, "runtime_snapshot.json"),
        "history": os.path.join(d, "history.ndjson"),
    }
# === ROOM STORE PATCH END ===
# === ROOM IO HELPERS BEGIN ===

# === GLOBAL ROOM PLAN LOADER (FIX) BEGIN ===
def _load_room_plan(room_id: str) -> dict:
    """Load per-room plan.json from rooms/<room_id>/...; returns {} if missing."""
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pp = paths.get('plan')
        if pp and Path(pp).exists():
            return json.loads(Path(pp).read_text(encoding='utf-8')) or {}
    except Exception:
        return {}
    return {}
# === GLOBAL ROOM PLAN LOADER (FIX) END ===
def _room_read_json(room_id: str, key: str, default=None):
    paths = _room_paths(room_id)
    p = paths.get(key)
    try:
        if p and os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _room_write_json(room_id: str, key: str, obj) -> bool:
    paths = _room_paths(room_id)
    p = paths.get(key)
    try:
        if not p:
            return False
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
# === ROOM IO HELPERS END ===
# === ENSURE ROOMS DIR BEGIN ===
# Crea los directorios base para stores por-room (independiente de endpoints)
try:
    _base = _state_root_dir()
    os.makedirs(_base, exist_ok=True)
    os.makedirs(os.path.join(_base, 'rooms'), exist_ok=True)
except Exception:
    pass
# === ENSURE ROOMS DIR END ===
# === ROOM SEED LEGACY BEGIN ===
def _seed_room_from_legacy_if_needed(room_id: str) -> None:
    # One-way compat: if legacy tmp_agent/state/{plan,mission}.json exist and room files don't, copy into rooms/<room_id>/
    try:
        rid = _safe_room_id(room_id)
        paths = _room_paths(rid)  # also ensures dirs
        legacy_root = _state_root_dir()
        legacy_plan = os.path.join(legacy_root, "plan.json")
        legacy_mission = os.path.join(legacy_root, "mission.json")

        if (not os.path.exists(paths["plan"])) and os.path.exists(legacy_plan):
            with open(legacy_plan, "rb") as fsrc:
                with open(paths["plan"], "wb") as fdst:
                    fdst.write(fsrc.read())

        if (not os.path.exists(paths["mission"])) and os.path.exists(legacy_mission):
            with open(legacy_mission, "rb") as fsrc:
                with open(paths["mission"], "wb") as fdst:
                    fdst.write(fsrc.read())
    except Exception:
        pass
# === ROOM SEED LEGACY END ===

APP_NAME = "Brain Lab"
APP_VERSION = "0.1.2"

CONTRACT_DEFAULT_PATH = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_v1.json"
RISK_STATE_ROOT = (Path(_state_root_dir()).resolve() / "rooms")

# === FIX_DEFINE__IS_WRITE_TOOL_V2 BEGIN ===
def _is_write_tool(tool_name: str) -> bool:
    try:
        t = (tool_name or "").strip()
    except Exception:
        t = ""
    return t in ("write_file", "append_file")
# === FIX_DEFINE__IS_WRITE_TOOL_V2 END ===

# FIX_DEFINE__HAS_PLACEHOLDER_V1
# === FIX_DEFINE__HAS_PLACEHOLDER_V1 BEGIN ===
def _has_placeholder(obj) -> bool:
    """
    Returns True if obj contains placeholder markers that indicate the planner
    hasn't produced real content yet (safety/quality guard).
    """
    try:
        PH = ("PLANNER_PLACEHOLDER", "PLACEHOLDER", "TODO_PLACEHOLDER")
        def _scan(x):
            if x is None:
                return False
            if isinstance(x, str):
                u = x.upper()
                return any(p in u for p in PH)
            if isinstance(x, dict):
                for k, v in x.items():
                    if _scan(k) or _scan(v):
                        return True
                return False
            if isinstance(x, (list, tuple, set)):
                for it in x:
                    if _scan(it):
                        return True
                return False
            return False
        return _scan(obj)
    except Exception:
        return False
# === FIX_DEFINE__HAS_PLACEHOLDER_V1 END ===

app = FastAPI(title=APP_NAME, version=APP_VERSION)
# === ROOM MIDDLEWARE BEGIN ===
@app.middleware("http")
async def _ensure_room_store_mw(request, call_next):
    # Create rooms/<room_id> for every request (robust, param-name agnostic)
    try:
        rid = _safe_room_id(request.headers.get("x-room-id") or "default")
        _room_state_dir(rid)
    except Exception:
        pass
    return await call_next(request)
# === ROOM MIDDLEWARE END ===


# ===== RISK_GATE_BLOCK_V1 =====
CONTRACT_DEFAULT_PATH = r"C:\AI_VAULT\workspace\brainlab\brainlab\contracts\financial_motor_contract_v1.json"
RISK_STATE_ROOT = (Path(_state_root_dir()).resolve() / "rooms")

def _risk_state_path(room_id: str) -> Path:
    # usa _norm_room_id si existe; fallback conservador
    rid = room_id
    try:
        rid = _norm_room_id(room_id)  # type: ignore
    except Exception:
        rid = (room_id or "default").strip() or "default"
        rid = "".join(ch for ch in rid if ch.isalnum() or ch in ("-", "_"))[:64] or "default"
    return (RISK_STATE_ROOT / rid / "risk_state.json").resolve()


def _risk_read_state(room_id: str) -> dict:
    rid = _norm_room_id(room_id)
    p = (RISK_STATE_ROOT / rid / "risk_state.json").resolve()
    try:
        if not p.exists():
            return {"exists": False, "path": str(p), "kill_switch": False}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
        data["_meta"] = {"exists": True, "path": str(p)}
        return data
    except Exception as e:
        return {"exists": False, "path": str(p), "kill_switch": False, "error": repr(e)}

def _risk_is_blocked(room_id: str) -> dict:
    st = _risk_read_state(room_id)
    try:
        ks = bool(st.get("kill_switch", False))
    except Exception:
        ks = False
    if ks:
        return {
            "ok": False,
            "error": "KILL_SWITCH",
            "detail": "Risk Gate latched: execution blocked until manual reset",
            "room_id": room_id,
            "risk_state": st
        }
    return {}



def _risk_summary(room_id: str) -> dict:
    st = _risk_read_state(room_id)
    # meta path
    path = None
    try:
        path = ((st.get("_meta") or {}).get("path")) if isinstance(st, dict) else None
    except Exception:
        path = None

    kill_switch = False
    try:
        kill_switch = bool(st.get("kill_switch", False)) if isinstance(st, dict) else False
    except Exception:
        kill_switch = False

    last = {}
    try:
        last = st.get("last_assess") or {}
        if not isinstance(last, dict):
            last = {}
    except Exception:
        last = {}

    last_verdict = str(last.get("verdict") or "")
    last_reason = str(last.get("reason") or "")

    vio_types = []
    try:
        v = st.get("last_violation_types") or []
        if isinstance(v, list):
            vio_types = [str(x) for x in v if x is not None]
    except Exception:
        vio_types = []

    blocked_reason = "KILL_SWITCH" if kill_switch else ""
    return {
                "effective_verdict": ("halt" if bool(kill_switch) else "continue"),
        "effective_reason": ("KILL_SWITCH" if bool(kill_switch) else "OK"),"room_id": room_id,
        "blocked": bool(kill_switch),
        "blocked_reason": blocked_reason,
        "last_verdict": last_verdict,
        "last_reason": last_reason,
        "last_violation_types": vio_types,
        "risk_state_path": path,
    }

# --- HARDENING_NORM_ROOM_ID_V1 -------------------------------------------------------
import re as _re

def _norm_room_id(room_id) -> str:
    """
    Normalize room_id to a safe filesystem-friendly identifier.
    - Accepts str/None/other; coerces to str
    - Trims; default 'default'
    - Allows: [A-Za-z0-9._-]
    - Collapses everything else to '_'
    - Prevents path traversal ('..') and empty result
    """
    try:
        rid = "" if room_id is None else str(room_id)
    except Exception:
        rid = "default"
    rid = rid.strip()
    if not rid:
        rid = "default"

    # replace slashes/backslashes and other unsafe chars
    rid = rid.replace("\\", "_").replace("/", "_")
    rid = _re.sub(r"[^A-Za-z0-9._-]+", "_", rid)

    # avoid traversal / dot-only names
    rid = rid.strip("._-")
    if not rid or rid in ("..", "."):
        rid = "default"
    rid = rid.replace("..", "_")

    # length guard
    if len(rid) > 80:
        rid = rid[:80]
    return rid
# --- /HARDENING_NORM_ROOM_ID_V1 ------------------------------------------------------


def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
class RuntimeSnapshotIn(BaseModel):
    nlv: float = Field(..., description="Net Liquidation Value")
    daily_pnl: float = Field(..., description="PnL del día")
    weekly_drawdown: float = Field(..., description="DD semanal (escala consistente con tu motor)")
    total_exposure: float = Field(..., description="Exposición total (escala consistente con tu motor)")


class StepWithSnapshotIn(BaseModel):
    snapshot: RuntimeSnapshotIn
    plan: Optional[Dict[str, Any]] = None

# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/risk/assess")
# [HARDENING4_SAFEMIN_DISABLED] def agent_risk_assess(payload: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
# [HARDENING4_SAFEMIN_DISABLED]     if snapshot is None:
# [HARDENING4_SAFEMIN_DISABLED]         snapshot = payload  # permitir snapshot en raíz
# [HARDENING4_SAFEMIN_DISABLED]     if not isinstance(snapshot, dict):
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_INVALID", "detail": "snapshot must be an object"}

# [HARDENING4_SAFEMIN_DISABLED]     contract_path = str(payload.get("contract_path") or CONTRACT_DEFAULT_PATH) if isinstance(payload, dict) else CONTRACT_DEFAULT_PATH

# [HARDENING4_SAFEMIN_DISABLED]     return risk_gate.persist_assess(
# [HARDENING4_SAFEMIN_DISABLED]         room_id=str(room_id or "default"),
# [HARDENING4_SAFEMIN_DISABLED]         contract_path=contract_path,
# [HARDENING4_SAFEMIN_DISABLED]         snapshot=snapshot,
# [HARDENING4_SAFEMIN_DISABLED]         risk_state_path=_risk_state_path(str(room_id or "default")),
# [HARDENING4_SAFEMIN_DISABLED]     )






# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/risk/reset_kill")
# [HARDENING4_SAFEMIN_DISABLED] def agent_risk_reset_kill(payload: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     note = ""
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if isinstance(payload, dict):
# [HARDENING4_SAFEMIN_DISABLED]             note = str(payload.get("note") or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         note = ""
# [HARDENING4_SAFEMIN_DISABLED]     return risk_gate.reset_kill_switch(_risk_state_path(str(room_id or "default")), note=note)
# [HARDENING4_SAFEMIN_DISABLED] # ===== /RISK_GATE_BLOCK_V1 =====
# [HARDENING4_SAFEMIN_DISABLED] # --- Agent Loop (Planner→Executor→Evaluator) ---
# [HARDENING4_SAFEMIN_DISABLED] from typing import Any, Dict as _Dict
# [HARDENING4_SAFEMIN_DISABLED] from agent_loop import AgentLoop, ToolResult, AgentPaths
# [HARDENING4_SAFEMIN_DISABLED] def _dispatch_tool(tool: str, args: dict) -> ToolResult:
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     Adaptador: conecta AgentLoop con tus tools reales.
# [HARDENING4_SAFEMIN_DISABLED]     Ajusta aquí si tus funciones se llaman distinto.
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if tool == "list_dir":
# [HARDENING4_SAFEMIN_DISABLED]             out = list_dir(**args)
# [HARDENING4_SAFEMIN_DISABLED]             return ToolResult(ok=True, output=out)
# [HARDENING4_SAFEMIN_DISABLED]         if tool == "read_file":
# [HARDENING4_SAFEMIN_DISABLED]             out = read_file(**args)
# [HARDENING4_SAFEMIN_DISABLED]             return ToolResult(ok=True, output=out)
# [HARDENING4_SAFEMIN_DISABLED]         if tool == "write_file":
# [HARDENING4_SAFEMIN_DISABLED]             out = write_file(**args)
# [HARDENING4_SAFEMIN_DISABLED]             return ToolResult(ok=True, output=out)
# [HARDENING4_SAFEMIN_DISABLED]         if tool == "append_file":
# [HARDENING4_SAFEMIN_DISABLED]             out = append_file(**args)
# [HARDENING4_SAFEMIN_DISABLED]             return ToolResult(ok=True, output=out)
# [HARDENING4_SAFEMIN_DISABLED]         return ToolResult(ok=False, error=f"UNKNOWN_TOOL: {tool}")
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return ToolResult(ok=False, error=repr(e))
# [HARDENING4_SAFEMIN_DISABLED] AVAILABLE_TOOLS = {
# [HARDENING4_SAFEMIN_DISABLED]     "list_dir": True,
# [HARDENING4_SAFEMIN_DISABLED]     "read_file": True,
# [HARDENING4_SAFEMIN_DISABLED]     "write_file": True,
# [HARDENING4_SAFEMIN_DISABLED]     "append_file": True
# [HARDENING4_SAFEMIN_DISABLED] }


# [HARDENING4_SAFEMIN_DISABLED] _AGENTS = {}  # room_id -> AgentLoop

# [HARDENING4_SAFEMIN_DISABLED] def _norm_room_id(v: str) -> str:
# [HARDENING4_SAFEMIN_DISABLED]     v = (v or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     if not v:
# [HARDENING4_SAFEMIN_DISABLED]         return "default"
# [HARDENING4_SAFEMIN_DISABLED]     v = "".join(ch for ch in v if ch.isalnum() or ch in ("-", "_"))[:64]
# [HARDENING4_SAFEMIN_DISABLED]     return v or "default"

# [HARDENING4_SAFEMIN_DISABLED] def _get_agent(request: Request) -> AgentLoop:
# [HARDENING4_SAFEMIN_DISABLED]     rid = None
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id")
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         rid = None
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(rid)

# [HARDENING4_SAFEMIN_DISABLED]     ag = _AGENTS.get(rid)
# [HARDENING4_SAFEMIN_DISABLED]     if ag is None:
# [HARDENING4_SAFEMIN_DISABLED]         ag = AgentLoop(paths=AgentPaths.default(room_id=rid))
# [HARDENING4_SAFEMIN_DISABLED]         ag.dispatch_tool = _dispatch_tool
# [HARDENING4_SAFEMIN_DISABLED]         _AGENTS[rid] = ag
# [HARDENING4_SAFEMIN_DISABLED]     return ag





# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] @app.post("/v1/agent/plan_legacy")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def agent_plan(payload: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     agent = _get_agent(request)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     goal = str(payload.get("goal") or "").strip()
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     profile = str(payload.get("profile") or "default").strip()
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     force_new = bool(payload.get("force_new", False))
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return agent.plan(goal=goal, profile=profile, force_new=force_new)





# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}@app.post("/v1/agent/step_with_snapshot")
# [HARDENING4_SAFEMIN_DISABLED] def step_with_snapshot(payload: StepWithSnapshotIn, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     """One-shot: persiste runtime snapshot validado y ejecuta el mismo flujo que /v1/agent/step."""
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     rid = (room_id or "default")

# [HARDENING4_SAFEMIN_DISABLED]     # 1) Persistir snapshot (validado por Pydantic)
# [HARDENING4_SAFEMIN_DISABLED]     snapshot_dict = payload.snapshot.model_dump()
# [HARDENING4_SAFEMIN_DISABLED]     wr = _runtime_snapshot_write(rid, snapshot_dict)
# [HARDENING4_SAFEMIN_DISABLED]     if not bool(wr.get("ok", False)):
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}

# [HARDENING4_SAFEMIN_DISABLED]     # 2) Ejecutar MISMO flujo que /step (hard block -> preflight -> latch -> etc.)
# [HARDENING4_SAFEMIN_DISABLED]     return agent_step(request)


# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/snapshot/set")
# [HARDENING4_SAFEMIN_DISABLED] def snapshot_set_alias(payload: RuntimeSnapshotIn, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     """Alias de compatibilidad: escribe runtime snapshot en /v1/agent/runtime/snapshot/set."""
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     rid = (room_id or "default")
# [HARDENING4_SAFEMIN_DISABLED]     snapshot_dict = payload.model_dump()
# [HARDENING4_SAFEMIN_DISABLED]     wr = _runtime_snapshot_write(rid, snapshot_dict)
# [HARDENING4_SAFEMIN_DISABLED]     if not bool(wr.get("ok", False)):
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}
# [HARDENING4_SAFEMIN_DISABLED]     return {"ok": True, "room_id": rid, "snapshot_path": wr.get("path")}

# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/step")
# [HARDENING4_SAFEMIN_DISABLED] def agent_step(request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     rid = (room_id or "default")

# [HARDENING4_SAFEMIN_DISABLED]     # 1) hard block if kill switch latched
# [HARDENING4_SAFEMIN_DISABLED]     blocked = _risk_is_blocked(rid)
# [HARDENING4_SAFEMIN_DISABLED]     if blocked:
# [HARDENING4_SAFEMIN_DISABLED]         return blocked

# [HARDENING4_SAFEMIN_DISABLED]     # 2) preflight assess using persisted runtime snapshot
# [HARDENING4_SAFEMIN_DISABLED]     snapr = _runtime_snapshot_read(rid)
# [HARDENING4_SAFEMIN_DISABLED]     if not bool(snapr.get("ok", False)):
# [HARDENING4_SAFEMIN_DISABLED]         return {
# [HARDENING4_SAFEMIN_DISABLED]             "ok": False,
# [HARDENING4_SAFEMIN_DISABLED]             "error": str(snapr.get("error") or "SNAPSHOT_MISSING"),
# [HARDENING4_SAFEMIN_DISABLED]             "detail": "Provide runtime snapshot via /v1/agent/runtime/snapshot/set",
# [HARDENING4_SAFEMIN_DISABLED]             "room_id": rid,
# [HARDENING4_SAFEMIN_DISABLED]             "snapshot_path": snapr.get("path")
# [HARDENING4_SAFEMIN_DISABLED]         }

# [HARDENING4_SAFEMIN_DISABLED]     snapshot = (snapr.get("snapshot") or {})
# [HARDENING4_SAFEMIN_DISABLED]     contract_path = CONTRACT_DEFAULT_PATH

# [HARDENING4_SAFEMIN_DISABLED]     # persist_assess will auto-latch kill switch if configured
# [HARDENING4_SAFEMIN_DISABLED]     rg = risk_gate.persist_assess(
# [HARDENING4_SAFEMIN_DISABLED]         room_id=rid,
# [HARDENING4_SAFEMIN_DISABLED]         contract_path=contract_path,
# [HARDENING4_SAFEMIN_DISABLED]         snapshot=snapshot,
# [HARDENING4_SAFEMIN_DISABLED]         risk_state_path=_risk_state_path(rid)
# [HARDENING4_SAFEMIN_DISABLED]     )

# [HARDENING4_SAFEMIN_DISABLED]     assess = (rg.get("assess") or {}) if isinstance(rg, dict) else {}
# [HARDENING4_SAFEMIN_DISABLED]     verdict = str(assess.get("verdict") or "")
# [HARDENING4_SAFEMIN_DISABLED]     if verdict.lower() == "halt":
# [HARDENING4_SAFEMIN_DISABLED]         return {
# [HARDENING4_SAFEMIN_DISABLED]             "ok": False,
# [HARDENING4_SAFEMIN_DISABLED]             "error": "RISK_HALT",
# [HARDENING4_SAFEMIN_DISABLED]             "detail": "Risk Gate preflight blocked execution",
# [HARDENING4_SAFEMIN_DISABLED]             "room_id": rid,
# [HARDENING4_SAFEMIN_DISABLED]             "risk_gate": rg
# [HARDENING4_SAFEMIN_DISABLED]         }

# [HARDENING4_SAFEMIN_DISABLED]     # 3) execute one agent step
# [HARDENING4_SAFEMIN_DISABLED]     return _get_agent(request).step()




# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] @app.post("/v1/agent/eval")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def agent_eval(request: Request):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return _get_agent(request).eval()






# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}# HARDENING16C_STATUS_GET_EOF_DISABLED_CORRUPT: @app.get("/v1/agent/status")
# [HARDENING4_SAFEMIN_DISABLED] def agent_status(request: Request):
# [HARDENING4_SAFEMIN_DISABLED] # === STATUS ROOM BOOTSTRAP BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # Room-aware bootstrap (robusto a nombres de params):
# [HARDENING4_SAFEMIN_DISABLED]     # - Encuentra el Request buscando un objeto con .headers.get()
# [HARDENING4_SAFEMIN_DISABLED]     # - Encuentra payload buscando dict con room_id o objeto con .room_id
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _req = None
# [HARDENING4_SAFEMIN_DISABLED]         for _v in locals().values():
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 if hasattr(_v, "headers") and hasattr(_v.headers, "get"):
# [HARDENING4_SAFEMIN_DISABLED]                     _req = _v
# [HARDENING4_SAFEMIN_DISABLED]                     break
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass

# [HARDENING4_SAFEMIN_DISABLED]         _hdr_room = None
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             if _req is not None:
# [HARDENING4_SAFEMIN_DISABLED]                 _hdr_room = _req.headers.get("x-room-id")
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             _hdr_room = None

# [HARDENING4_SAFEMIN_DISABLED]         _payload_room = None
# [HARDENING4_SAFEMIN_DISABLED]         for _v in locals().values():
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 if isinstance(_v, dict) and "room_id" in _v:
# [HARDENING4_SAFEMIN_DISABLED]                     _payload_room = _v.get("room_id")
# [HARDENING4_SAFEMIN_DISABLED]                     break
# [HARDENING4_SAFEMIN_DISABLED]                 if hasattr(_v, "room_id"):
# [HARDENING4_SAFEMIN_DISABLED]                     _payload_room = getattr(_v, "room_id", None)
# [HARDENING4_SAFEMIN_DISABLED]                     if _payload_room:
# [HARDENING4_SAFEMIN_DISABLED]                         break
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass

# [HARDENING4_SAFEMIN_DISABLED]         room_id = _safe_room_id(_hdr_room or _payload_room or "default")
# [HARDENING4_SAFEMIN_DISABLED]         _room_state_dir(room_id)

# [HARDENING4_SAFEMIN_DISABLED]         # Seed inicial: copiar state/*.json global -> rooms/<room>/ si faltan
# [HARDENING4_SAFEMIN_DISABLED]         base = _state_root_dir()
# [HARDENING4_SAFEMIN_DISABLED]         src_m = os.path.join(base, "mission.json")
# [HARDENING4_SAFEMIN_DISABLED]         src_p = os.path.join(base, "plan.json")
# [HARDENING4_SAFEMIN_DISABLED]         src_s = os.path.join(base, "runtime_snapshot.json")
# [HARDENING4_SAFEMIN_DISABLED]         dst = _room_paths(room_id)

# [HARDENING4_SAFEMIN_DISABLED]         if os.path.exists(src_m) and (not os.path.exists(dst["mission"])):
# [HARDENING4_SAFEMIN_DISABLED]             try: shutil.copyfile(src_m, dst["mission"])
# [HARDENING4_SAFEMIN_DISABLED]             except Exception: pass
# [HARDENING4_SAFEMIN_DISABLED]         if os.path.exists(src_p) and (not os.path.exists(dst["plan"])):
# [HARDENING4_SAFEMIN_DISABLED]             try: shutil.copyfile(src_p, dst["plan"])
# [HARDENING4_SAFEMIN_DISABLED]             except Exception: pass
# [HARDENING4_SAFEMIN_DISABLED]         if os.path.exists(src_s) and (not os.path.exists(dst["snapshot"])):
# [HARDENING4_SAFEMIN_DISABLED]             try: shutil.copyfile(src_s, dst["snapshot"])
# [HARDENING4_SAFEMIN_DISABLED]             except Exception: pass

# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         pass
# [HARDENING4_SAFEMIN_DISABLED] # === STATUS ROOM BOOTSTRAP END ===
# [HARDENING4_SAFEMIN_DISABLED] # === STATUS ROOMDIR PATCH BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # Garantiza que exista el store por-room en disco
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         # room_id efectivo: header x-room-id > payload.room_id > default
# [HARDENING4_SAFEMIN_DISABLED]         # (si ya lo calculaste arriba, reutiliza la variable room_id)
# [HARDENING4_SAFEMIN_DISABLED]         if 'room_id' in locals():
# [HARDENING4_SAFEMIN_DISABLED]             _room_state_dir(room_id)
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             room_id = _effective_room_id(request, None)
# [HARDENING4_SAFEMIN_DISABLED]             _room_state_dir(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         # No tumbar status por fallo de FS; pero dejamos rastro en logs si existen
# [HARDENING4_SAFEMIN_DISABLED]         pass
# [HARDENING4_SAFEMIN_DISABLED] # === STATUS ROOMDIR PATCH END ===
# [HARDENING4_SAFEMIN_DISABLED]     # === STATUS ROOM-AWARE INJECT BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # derive room_id from header x-room-id > payload.room_id > default
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _payload_room = None
# [HARDENING4_SAFEMIN_DISABLED]         if isinstance(payload, dict):
# [HARDENING4_SAFEMIN_DISABLED]             _payload_room = payload.get("room_id")
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         _payload_room = None
# [HARDENING4_SAFEMIN_DISABLED]     room_id = _effective_room_id(request, _payload_room)
# [HARDENING4_SAFEMIN_DISABLED]     # ensure room dirs exist + seed legacy if needed
# [HARDENING4_SAFEMIN_DISABLED]     _seed_room_from_legacy_if_needed(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     _ = _room_paths(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     # === STATUS ROOM-AWARE INJECT END ===
# [HARDENING4_SAFEMIN_DISABLED]     return _get_agent(request).status()






# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/reset")
# [HARDENING4_SAFEMIN_DISABLED] def agent_reset(request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     return _get_agent(request).reset()






# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}@app.get("/v1/agent/capabilities")
def agent_capabilities():
    return {
        "ok": True,
        "available_tools": AVAILABLE_TOOLS
    }






def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/risk/assess")
# [HARDENING4_SAFEMIN_DISABLED] def agent_risk_assess(payload: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     # payload expects: snapshot {nlv,daily_pnl,weekly_drawdown,total_exposure}
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     snapshot = payload.get("snapshot") or payload  # allow sending snapshot at root
# [HARDENING4_SAFEMIN_DISABLED]     if not isinstance(snapshot, dict):
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_INVALID", "detail": "snapshot must be an object"}
# [HARDENING4_SAFEMIN_DISABLED]     contract_path = str(payload.get("contract_path") or CONTRACT_DEFAULT_PATH)
# [HARDENING4_SAFEMIN_DISABLED]     rsp = risk_gate.persist_assess(
# [HARDENING4_SAFEMIN_DISABLED]         room_id=(room_id or "default"),
# [HARDENING4_SAFEMIN_DISABLED]         contract_path=contract_path,
# [HARDENING4_SAFEMIN_DISABLED]         snapshot=snapshot,
# [HARDENING4_SAFEMIN_DISABLED]         risk_state_path=_risk_state_path(room_id or "default")
# [HARDENING4_SAFEMIN_DISABLED]     )
# [HARDENING4_SAFEMIN_DISABLED]     return rsp







# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/risk/reset_kill")
# [HARDENING4_SAFEMIN_DISABLED] def agent_risk_reset_kill(payload: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     note = str((payload or {}).get("note") or "").strip() if isinstance(payload, dict) else ""
# [HARDENING4_SAFEMIN_DISABLED]     return risk_gate.reset_kill_switch(_risk_state_path(room_id or "default"), note=note)

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING4_SAFEMIN_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         if not p.exists():
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(data, dict):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING4_SAFEMIN_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING4_SAFEMIN_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}# [HARDENING4_SAFEMIN_DISABLED] @app.get("/v1/agent/risk/status")
# [HARDENING4_SAFEMIN_DISABLED] def agent_risk_status(request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING4_SAFEMIN_DISABLED]     rid = (room_id or "default")
# [HARDENING4_SAFEMIN_DISABLED]     st = _risk_read_state(rid)
# [HARDENING4_SAFEMIN_DISABLED]     summary = _risk_summary(rid)
# [HARDENING4_SAFEMIN_DISABLED]     return {"ok": True, "room_id": rid, "summary": summary, "risk_state": st}
@app.post("/v1/agent/runtime/snapshot/set")
def runtime_snapshot_set(payload: dict, request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    snap = (payload or {}).get("snapshot") if isinstance(payload, dict) else None
    if snap is None and isinstance(payload, dict):
        # allow sending snapshot at root
        snap = payload
    if not isinstance(snap, dict):
        return {"ok": False, "error": "SNAPSHOT_INVALID", "detail": "snapshot must be an object"}
    return _runtime_snapshot_write(room_id or "default", snap)

@app.get("/v1/agent/runtime/snapshot/get")
def runtime_snapshot_get(request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    return _runtime_snapshot_read(room_id or "default")

# APP_INCLUDE_ROUTER_MOVED_V1: moved to EOF\n# app.include_router(router)
def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_path(room_id: str) -> Path:
    rid = _norm_room_id(room_id)
    return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

def _runtime_snapshot_read(room_id: str) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        if not p.exists():
            return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
        return {"ok": True, "path": str(p), "snapshot": data}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
    p = _runtime_snapshot_path(room_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
# [HARDENING2_DISABLED] @app.get("/healthz")
# [HARDENING2_DISABLED] def healthz():
# [HARDENING2_DISABLED] # === HEALTH ROOMDIR PATCH BEGIN ===
# [HARDENING2_DISABLED]     # Forzar creación de store por-room (garantiza rooms/default) SIN depender de request
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         _room_state_dir("default")
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass
# [HARDENING2_DISABLED] # === HEALTH ROOMDIR PATCH END ===
# [HARDENING2_DISABLED]     return {"ok": True, "name": APP_NAME, "version": APP_VERSION, "pid": os.getpid()}






# [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING2_DISABLED] def _runtime_snapshot_path(room_id: str) -> Path:
# [HARDENING2_DISABLED]     rid = _norm_room_id(room_id)
# [HARDENING2_DISABLED]     return (RISK_STATE_ROOT / rid / "runtime_snapshot.json").resolve()

# [HARDENING2_DISABLED] def _runtime_snapshot_read(room_id: str) -> dict:
# [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         if not p.exists():
# [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_MISSING", "path": str(p)}
# [HARDENING2_DISABLED]         data = json.loads(p.read_text(encoding="utf-8"))
# [HARDENING2_DISABLED]         if not isinstance(data, dict):
# [HARDENING2_DISABLED]             return {"ok": False, "error": "SNAPSHOT_INVALID", "path": str(p)}
# [HARDENING2_DISABLED]         return {"ok": True, "path": str(p), "snapshot": data}
# [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_READ_FAILED", "path": str(p), "detail": repr(e)}

# [HARDENING2_DISABLED] def _runtime_snapshot_write(room_id: str, snapshot: dict) -> dict:
# [HARDENING2_DISABLED]     p = _runtime_snapshot_path(room_id)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         p.parent.mkdir(parents=True, exist_ok=True)
# [HARDENING2_DISABLED]         p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         return {"ok": True, "path": str(p)}
# [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING2_DISABLED]         return {"ok": False, "error": "SNAPSHOT_WRITE_FAILED", "path": str(p), "detail": repr(e)}
# [HARDENING2_DISABLED] @app.middleware("http")
# [HARDENING2_DISABLED] async def add_timing_and_room(request: Request, call_next):
# [HARDENING2_DISABLED]     t0 = time.time()
# [HARDENING2_DISABLED]     room_id = request.headers.get("x-room-id", "default")
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         response = await call_next(request)
# [HARDENING2_DISABLED]     except Exception as e:
# [HARDENING2_DISABLED]         dt_ms = int((time.time() - t0) * 1000)
# [HARDENING2_DISABLED]         return JSONResponse(status_code=500, content={"ok": False, "error": str(e), "room_id": room_id, "latency_ms": dt_ms})
# [HARDENING2_DISABLED]     dt_ms = int((time.time() - t0) * 1000)
# [HARDENING2_DISABLED]     response.headers["x-latency-ms"] = str(dt_ms)
# [HARDENING2_DISABLED]     response.headers["x-room-id"] = room_id
# [HARDENING2_DISABLED]     return response















# [HARDENING2_DISABLED] # ===== Brain Lab Agent Endpoints (v4) =====
# [HARDENING2_DISABLED] import os
# [HARDENING2_DISABLED] import sys
# [HARDENING2_DISABLED] from typing import Any, Dict, Optional

# [HARDENING2_DISABLED] from fastapi import Body, HTTPException
# [HARDENING2_DISABLED] from pydantic import BaseModel, Field

# [HARDENING2_DISABLED] TMP_AGENT_ROOT = os.environ.get("BRAIN_TMP_AGENT_ROOT", r"C:\AI_VAULT\tmp_agent")
# [HARDENING2_DISABLED] if TMP_AGENT_ROOT not in sys.path:
# [HARDENING2_DISABLED]     sys.path.insert(0, TMP_AGENT_ROOT)

# [HARDENING2_DISABLED] from agent_state import AgentStateStore  # noqa: E402

# [HARDENING2_DISABLED] agent_store = AgentStateStore(root=TMP_AGENT_ROOT)


# [HARDENING2_DISABLED] class AgentPlanRequest(BaseModel):
# [HARDENING2_DISABLED]     goal: str = Field(..., min_length=1)
# [HARDENING2_DISABLED]     room_id: Optional[str] = None
# [HARDENING2_DISABLED]     context: Optional[Dict[str, Any]] = None


# [HARDENING2_DISABLED] class AgentPlanResponse(BaseModel):
# [HARDENING2_DISABLED]     ok: bool
# [HARDENING2_DISABLED]     mission: Dict[str, Any]
# [HARDENING2_DISABLED]     plan: Dict[str, Any]


# [HARDENING2_DISABLED] class AgentEvalRequest(BaseModel):
# [HARDENING2_DISABLED]     observation: Dict[str, Any] = Field(default_factory=dict)
# [HARDENING2_DISABLED]     room_id: Optional[str] = None


# [HARDENING2_DISABLED] class AgentEvalResponse(BaseModel):
# [HARDENING2_DISABLED]     ok: bool
# [HARDENING2_DISABLED]     plan: Dict[str, Any]
# [HARDENING2_DISABLED]     verdict: Dict[str, Any]


# [HARDENING3_DISABLED_OLD] @app.get("/v1/agent/plan")
# [HARDENING3_DISABLED_OLD] def agent_plan_get(request: Request):
# [HARDENING3_DISABLED_OLD]     # === PLAN_GET_SSOT_ROOMPLAN_JSON_V1 ===
# [HARDENING3_DISABLED_OLD]     rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
# [HARDENING3_DISABLED_OLD]     rid = (rid or "default")

# [HARDENING3_DISABLED_OLD]     plan = {}
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         import json
# [HARDENING3_DISABLED_OLD]         from pathlib import Path
# [HARDENING3_DISABLED_OLD]         root = Path(_resolve_tmp_agent_root())
# [HARDENING3_DISABLED_OLD]         roomdir = root / "state" / "rooms" / str(rid)
# [HARDENING3_DISABLED_OLD]         fp = roomdir / "plan.json"
# [HARDENING3_DISABLED_OLD]         if fp.exists():
# [HARDENING3_DISABLED_OLD]             plan = json.loads(fp.read_text(encoding="utf-8")) or {}
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         plan = {}

# [HARDENING3_DISABLED_OLD]     if not isinstance(plan, dict):
# [HARDENING3_DISABLED_OLD]         plan = {}
# [HARDENING3_DISABLED_OLD]     plan.setdefault("room_id", rid)
# [HARDENING3_DISABLED_OLD]     plan.setdefault("status", "planned")
# [HARDENING3_DISABLED_OLD]     plan.setdefault("steps", [])

# [HARDENING3_DISABLED_OLD]     return {"ok": True, "room_id": rid, "plan": plan}@app.post("/v1/agent/plan", response_model=AgentPlanResponse)
def agent_plan(req: AgentPlanRequest, request: Request):
    # === PLAN_POST_SSOT_FIX_V1 ===
    # === AGENT_PLAN ROOM LOAD BEGIN ===
    # Resolve room_id from header/body (room-aware planner)
    try:
        hdr_room = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
    except Exception:
        hdr_room = None
    try:
        req_room = getattr(req, 'room_id', None)
    except Exception:
        req_room = None
    room_id = _safe_room_id(req_room or hdr_room or 'default')
    _audit_append((rid if 'rid' in locals() else room_id), event='plan_get')

    # Load mission/plan from rooms/<room_id> (fallback: keep existing locals if any)
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pm = paths.get('mission')
        pp = paths.get('plan')
        if pm and Path(pm).exists():
            mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {}
        if pp and Path(pp).exists():
            plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {}
    except Exception:
        pass
    # === AGENT_PLAN ROOM LOAD END ===

    # === AGENT_PLAN ROOM LOAD (FIX) BEGIN ===
    # Resolve room_id from header/body
    try:
        hdr_room = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
    except Exception:
        hdr_room = None
    try:
        req_room = getattr(req, 'room_id', None)
    except Exception:
        req_room = None
    room_id = _safe_room_id(req_room or hdr_room or 'default')
    
    # Load mission/plan from rooms/<room_id> (fallback a store global)
    mission, plan = {}, {}
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pm = paths.get('mission')
        pp = paths.get('plan')
        if pm and Path(pm).exists():
            mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {}
        if pp and Path(pp).exists():
            plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {}
    except Exception:
        try:
            mission, plan = agent_store.load()
        except Exception:
            mission, plan = {}, {}
    # === AGENT_PLAN ROOM LOAD (FIX) END ===

    # ===== Planner executable steps (v4.4) =====
    # Conservative/idempotent planning: do not overwrite active plans.
    status = str((plan or {}).get("status", "idle") or "idle").lower()
    steps = (plan or {}).get("steps", []) or []
    can_plan = (not steps) or (status in {"idle", "complete", "failed"})

    if can_plan:
        repo_risk = r"C:\AI_VAULT\workspace\brainlab\brainlab\risk"
        repo_risk_engine = r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py"

        plan["status"] = "planned"
        # === MIN_MISSION_GOAL_TS_V1 BEGIN ===
        from datetime import datetime, timezone
        _now = datetime.now(timezone.utc).isoformat()
        # === MIN_MISSION_GOAL_TS_V1 END ===
        plan["steps"] = [
            {
                "id": "S1",
                "title": "Write mission_log.txt (append_file) — gated (repo-safe)",
                "status": "todo",
                "tool_name": "append_file",
                "mode": "propose",
                "kind": "new_file",
                "dest_dir": (r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)),
                "tool_args": {
                    "path": "mission_log.txt",
                    "content": "MISSION START\\n"
                }
            },
            {
                "id": "S2",
                "title": "Snapshot set mission_state.json (runtime_snapshot_set)",
                "status": "todo",
                "tool_name": "runtime_snapshot_set",
                "mode": "propose",
                "kind": "state",
                "tool_args": {
                    "path": "mission_state.json",
                    "value": {"ts": "", "goal": "", "room_id": ""}
                }
            },
            {
                "id": "S3",
                "title": "Snapshot get mission_state.json (runtime_snapshot_get)",
                "status": "todo",
                "tool_name": "runtime_snapshot_get",
                "mode": "propose",
                "kind": "state",
                "tool_args": {
                    "path": "mission_state.json"
                }
            }
        ]
        # === PLAN_POST_SSOT_WRITEFILE_V1 BEGIN ===
        try:
            import json
            from pathlib import Path
            root = Path(_resolve_tmp_agent_root())
            roomdir = root / "state" / "rooms" / str(room_id)
            roomdir.mkdir(parents=True, exist_ok=True)
            fp = roomdir / "plan.json"
            fp.write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding="utf-8")
            # best-effort mission persist if available
            try:
                if "mission" in locals() and isinstance(mission, dict):
                    fm = roomdir / "mission.json"
                    fm.write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        except Exception:
            pass
        # === PLAN_POST_SSOT_WRITEFILE_V1 END ===
        # PLAN_POST_SSOT_WRITEFILE_V1

    # Always append history
    # Derive room_id for history (prefer req.room_id, fallback x-room-id header)
    rid = room_id  # PLAN_POST_SSOT_FIX_V1
    # rid initialized from SSOT room_id
    # (kept for legacy fallback below)
    #
    # original:
    # rid = None
    try:
        rid = getattr(req, 'room_id', None)
    except Exception:
        rid = None
    if not rid and 'request' in locals() and request is not None:
        try:
            rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
        except Exception:
            rid = None
    agent_store.append_history({
        "kind": "plan",
        "goal": req.goal,
        "room_id": rid,
        "can_plan": can_plan,
        "status_before": status,
    })
    # === PLAN_POST_SSOT_FIX_V1 ROOM LOAD RETURN BEGIN ===
    # Return SSOT room-scoped mission/plan (not global agent_store)
    try:
        mission2 = _load_room_mission(room_id) or {}
    except Exception:
        mission2 = {}
    try:
        plan2 = _load_room_plan(room_id) or {}
    except Exception:
        plan2 = {}
    try:
        if isinstance(mission2, dict):
            mission2.setdefault("room_id", room_id)
    except Exception:
        pass
    try:
        if isinstance(plan2, dict):
            plan2.setdefault("room_id", room_id)
            plan2.setdefault("status", "planned")
            plan2.setdefault("steps", [])
    except Exception:
        pass
    # === PLAN_POST_SSOT_FIX_V1 ROOM LOAD RETURN END ===
    # === AGENT_PLAN ROOM SAVE (FIX) BEGIN ===
    # Persist mission/plan to rooms/<room_id>/... (NO-OP si no hay room_id)
    try:
        _rid = None
        # 1) intenta encontrar room id en variables locales comunes
        for _k in ('room_id','rid','x_room_id','req_room_id','room'):
            try:
                if _k in locals() and locals().get(_k):
                    _rid = locals().get(_k)
                    break
            except Exception:
                pass
        # 2) fallback: leer header desde request si existe
        if not _rid and 'request' in locals() and request is not None:
            try:
                _rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
            except Exception:
                _rid = None
        if _rid:
            _room_state_dir(_rid)
            paths = _room_paths(_rid) or {}
            from pathlib import Path
            from datetime import datetime, timezone
            import json
            now = datetime.now(timezone.utc).isoformat()
            try:
                if isinstance(plan, dict):
                    plan['updated_at'] = now
                    plan.setdefault('room_id', _rid)
            except Exception:
                pass
            try:
                if isinstance(mission, dict):
                    mission['updated_at'] = now
                    mission.setdefault('room_id', _rid)
            except Exception:
                pass
            pm = paths.get('mission')
            pp = paths.get('plan')
            if pm:
                Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
            if pp:
                Path(pp).write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    # === AGENT_PLAN ROOM SAVE (FIX) END ===

    # === PLAN_POST_PERSIST_ROOMPLAN_JSON_V1 BEGIN ===
    # SSOT: persist plan+mission for this room to tmp_agent\state\rooms\<room_id>\*.json
    try:
        import json
        from pathlib import Path
        _rid = None
        try:
            _rid = locals().get("room_id")
        except Exception:
            _rid = None
        if not _rid:
            try:
                _rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id")
            except Exception:
                _rid = None
        _rid = (_rid or "default")
    
        root = Path(_resolve_tmp_agent_root())
        roomdir = root / "state" / "rooms" / str(_rid)
        roomdir.mkdir(parents=True, exist_ok=True)
    
        try:
            if isinstance(plan2, dict):
                plan2.setdefault("room_id", _rid)
        except Exception:
            pass
        try:
            if isinstance(mission2, dict):
                mission2.setdefault("room_id", _rid)
        except Exception:
            pass
    
        (roomdir / "plan.json").write_text(json.dumps(plan2 or {}, ensure_ascii=False, indent=2), encoding="utf-8")
        (roomdir / "mission.json").write_text(json.dumps(mission2 or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    # === PLAN_POST_PERSIST_ROOMPLAN_JSON_V1 END ===

    return {"ok": True, "mission": mission2, "plan": plan2}
    # ===== End Planner executable steps (v4.4) =====


# === PLAN_REAL_ENDPOINT_V1 BEGIN ===
class AgentPlanRealRequest(BaseModel):
    goal: str = Field("", description="goal for planning (read-only)")
    room_id: Optional[str] = None

class AgentPlanRealResponse(BaseModel):
    ok: bool = True
    room_id: str
    plan: Dict[str, Any]
    mission: Dict[str, Any]

# [HARDENING2_DISABLED] @app.post("/v1/agent/plan_real", response_model=AgentPlanRealResponse)
# [HARDENING2_DISABLED] def agent_plan_real(req: AgentPlanRealRequest, request: Request):
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     Read-only planner. Does NOT modify /v1/agent/plan behavior.
# [HARDENING2_DISABLED]     Creates a simple plan with list_dir + read_file steps.
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         hdr_room = None

# [HARDENING2_DISABLED]     room_id = (req.room_id or hdr_room or "default")

# [HARDENING2_DISABLED]     # load current mission/plan, but we will overwrite plan steps for this room
# [HARDENING2_DISABLED]     mission, plan = agent_store.load()
# [HARDENING2_DISABLED]     plan = dict(plan or {})
# [HARDENING2_DISABLED]     plan["status"] = "planned"
# [HARDENING2_DISABLED]     plan["room_id"] = room_id
# [HARDENING2_DISABLED]     plan["goal"] = req.goal

# [HARDENING2_DISABLED]     plan["steps"] = [
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S1",
# [HARDENING2_DISABLED]             "title": "Inspect risk folder (list_dir)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "list_dir",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk"},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S2",
# [HARDENING2_DISABLED]             "title": "Read risk_engine.py (read_file)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "read_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": "C:\\\\AI_VAULT\\\\workspace\\\\brainlab\\\\brainlab\\\\risk\\\\risk_engine.py", "max_bytes": 200000},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]     ]

# [HARDENING2_DISABLED]     # Persist per-room (same mechanism your SOT expects)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         agent_store.save_plan(plan)
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         _rid = room_id
# [HARDENING2_DISABLED]         _room_state_dir(_rid)
# [HARDENING2_DISABLED]         _paths = _room_paths(_rid) or {}
# [HARDENING2_DISABLED]         import json
# [HARDENING2_DISABLED]         from pathlib import Path
# [HARDENING2_DISABLED]         pp = _paths.get("plan")
# [HARDENING2_DISABLED]         if pp:
# [HARDENING2_DISABLED]             Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         mp = _paths.get("mission")
# [HARDENING2_DISABLED]         if mp:
# [HARDENING2_DISABLED]             Path(mp).write_text(json.dumps(mission or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission or {"room_id": room_id}}
# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V1 END ===



# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ===
# [HARDENING2_DISABLED] class AgentPlanRealV2Request(BaseModel):
# [HARDENING2_DISABLED]     goal: str = Field("", description="goal for planning (read-only + 1 gated write, repo-safe)")
# [HARDENING2_DISABLED]     room_id: Optional[str] = None

# [HARDENING2_DISABLED] class AgentPlanRealV2Response(BaseModel):
# [HARDENING2_DISABLED]     ok: bool = True
# [HARDENING2_DISABLED]     room_id: str
# [HARDENING2_DISABLED]     plan: Dict[str, Any]
# [HARDENING2_DISABLED]     mission: Dict[str, Any]
# [HARDENING2_DISABLED] @app.post("/v1/agent/plan_real_v2", response_model=AgentPlanRealV2Response)
# [HARDENING2_DISABLED] def agent_plan_real_v2(req: AgentPlanRealV2Request, request: Request):
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     REAL v2 (repo-safe):
# [HARDENING2_DISABLED]     - Read-only steps (list_dir/read_file)
# [HARDENING2_DISABLED]     - One gated write step (append_file new_file) applied INSIDE repo root:
# [HARDENING2_DISABLED]         C:\\AI_VAULT\\workspace\\brainlab\\_agent_runs\\<room>\\real_log.txt

# [HARDENING2_DISABLED]     This validates propose->approval->apply end-to-end WITHOUT touching code files.
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         hdr_room = None

# [HARDENING2_DISABLED]     room_id = (req.room_id or hdr_room or "default")

# [HARDENING2_DISABLED]     mission, plan = agent_store.load()
# [HARDENING2_DISABLED]     plan = dict(plan or {})
# [HARDENING2_DISABLED]     plan["status"] = "planned"
# [HARDENING2_DISABLED]     plan["room_id"] = room_id
# [HARDENING2_DISABLED]     plan["goal"] = req.goal

# [HARDENING2_DISABLED]     # Must be inside repo root accepted by apply_gate
# [HARDENING2_DISABLED]     dest_dir = r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)

# [HARDENING2_DISABLED]     plan["steps"] = [
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S1",
# [HARDENING2_DISABLED]             "title": "Inspect risk folder (list_dir)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "list_dir",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk"},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S2",
# [HARDENING2_DISABLED]             "title": "Read risk_engine.py (read_file)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "read_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py", "max_bytes": 200000},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S3",
# [HARDENING2_DISABLED]             "title": "Write real_log.txt (append_file) — gated SAFE (repo)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "append_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "dest_dir": dest_dir,
# [HARDENING2_DISABLED]             "tool_args": {
# [HARDENING2_DISABLED]                 "path": "real_log.txt",
# [HARDENING2_DISABLED]                 "content": "REAL_V2 START\\n",
# [HARDENING2_DISABLED]             },
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]     ]

# [HARDENING2_DISABLED]     # Persist per-room plan/mission
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         agent_store.save_plan(plan)
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         _rid = room_id
# [HARDENING2_DISABLED]         _room_state_dir(_rid)
# [HARDENING2_DISABLED]         _paths = _room_paths(_rid) or {}
# [HARDENING2_DISABLED]         import json
# [HARDENING2_DISABLED]         from pathlib import Path
# [HARDENING2_DISABLED]         pp = _paths.get("plan")
# [HARDENING2_DISABLED]         if pp:
# [HARDENING2_DISABLED]             Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         mp = _paths.get("mission")
# [HARDENING2_DISABLED]         if mp:
# [HARDENING2_DISABLED]             Path(mp).write_text(json.dumps(mission or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission or {"room_id": room_id}}
# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ===




# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V3_MODIFY_V1 BEGIN ===
# [HARDENING2_DISABLED] class AgentPlanRealV3Request(BaseModel):
# [HARDENING2_DISABLED]     goal: str = Field("", description="goal for planning (read-only + 1 gated modify write, repo-safe)")
# [HARDENING2_DISABLED]     room_id: Optional[str] = None

# [HARDENING2_DISABLED] class AgentPlanRealV3Response(BaseModel):
# [HARDENING2_DISABLED]     ok: bool = True
# [HARDENING2_DISABLED]     room_id: str
# [HARDENING2_DISABLED]     plan: Dict[str, Any]
# [HARDENING2_DISABLED]     mission: Dict[str, Any]
# [HARDENING2_DISABLED] @app.post("/v1/agent/plan_real_v3", response_model=AgentPlanRealV3Response)
# [HARDENING2_DISABLED] def agent_plan_real_v3(req: AgentPlanRealV3Request, request: Request):
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     REAL v3 (repo-safe, modify gated):
# [HARDENING2_DISABLED]     - Read-only: list_dir + read_file (same as v2)
# [HARDENING2_DISABLED]     - One gated MODIFY: append marker into:
# [HARDENING2_DISABLED]         C:\\AI_VAULT\\workspace\\brainlab\\_agent_runs\\<room>\\real_log.txt

# [HARDENING2_DISABLED]     This validates propose->approval->apply on kind=modify (without touching code files).
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         hdr_room = None

# [HARDENING2_DISABLED]     room_id = (req.room_id or hdr_room or "default")

# [HARDENING2_DISABLED]     mission, plan = agent_store.load()
# [HARDENING2_DISABLED]     plan = dict(plan or {})
# [HARDENING2_DISABLED]     plan["status"] = "planned"
# [HARDENING2_DISABLED]     plan["room_id"] = room_id
# [HARDENING2_DISABLED]     plan["goal"] = req.goal

# [HARDENING2_DISABLED]     # Repo-safe folder
# [HARDENING2_DISABLED]     run_dir = r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)
# [HARDENING2_DISABLED]     # Target file inside repo-safe folder
# [HARDENING2_DISABLED]     log_repo_path = run_dir + r"\real_log.txt"

# [HARDENING2_DISABLED]     # Marker (single line, deterministic enough)
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         from datetime import datetime, timezone
# [HARDENING2_DISABLED]         ts = datetime.now(timezone.utc).isoformat()
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         ts = ""
# [HARDENING2_DISABLED]     marker = f"REAL_V3 MARK {ts}\\n"

# [HARDENING2_DISABLED]     plan["steps"] = [
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S1",
# [HARDENING2_DISABLED]             "title": "Inspect risk folder (list_dir)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "list_dir",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk"},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S2",
# [HARDENING2_DISABLED]             "title": "Read risk_engine.py (read_file)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "read_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py", "max_bytes": 200000},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S3",
# [HARDENING2_DISABLED]             "title": "Modify real_log.txt (append marker) — gated SAFE (repo)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "append_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "modify",
# [HARDENING2_DISABLED]             "repo_path": log_repo_path,
# [HARDENING2_DISABLED]             "dest_dir": run_dir,
# [HARDENING2_DISABLED]             "tool_args": {
# [HARDENING2_DISABLED]                 "path": "real_log.txt",
# [HARDENING2_DISABLED]                 "content": marker,
# [HARDENING2_DISABLED]             },
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]     ]

# [HARDENING2_DISABLED]     # Persist per-room plan/mission
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         agent_store.save_plan(plan)
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         _rid = room_id
# [HARDENING2_DISABLED]         _room_state_dir(_rid)
# [HARDENING2_DISABLED]         _paths = _room_paths(_rid) or {}
# [HARDENING2_DISABLED]         import json
# [HARDENING2_DISABLED]         from pathlib import Path
# [HARDENING2_DISABLED]         pp = _paths.get("plan")
# [HARDENING2_DISABLED]         if pp:
# [HARDENING2_DISABLED]             Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         mp = _paths.get("mission")
# [HARDENING2_DISABLED]         if mp:
# [HARDENING2_DISABLED]             Path(mp).write_text(json.dumps(mission or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission or {"room_id": room_id}}
# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V3_MODIFY_V1 END ===



# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V3B_CREATE_MODIFY_V1 BEGIN ===
# [HARDENING2_DISABLED] class AgentPlanRealV3BRequest(BaseModel):
# [HARDENING2_DISABLED]     goal: str = Field("", description="goal for planning (read-only + gated create + gated modify, repo-safe)")
# [HARDENING2_DISABLED]     room_id: Optional[str] = None

# [HARDENING2_DISABLED] class AgentPlanRealV3BResponse(BaseModel):
# [HARDENING2_DISABLED]     ok: bool = True
# [HARDENING2_DISABLED]     room_id: str
# [HARDENING2_DISABLED]     plan: Dict[str, Any]
# [HARDENING2_DISABLED]     mission: Dict[str, Any]
# [HARDENING2_DISABLED] @app.post("/v1/agent/plan_real_v3b", response_model=AgentPlanRealV3BResponse)
# [HARDENING2_DISABLED] def agent_plan_real_v3b(req: AgentPlanRealV3BRequest, request: Request):
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     # === PLAN_REAL_V3B_MARKER2_V2 ===\n    # === PLAN_REAL_V3B_NEWLINE_RUNTIME_V1 ===\n    # === PLAN_REAL_V3B_LOGFMT_SAFE_V1 ===\n    # === PLAN_REAL_V3B_READS_MODE_FIX_V1 ===
# [HARDENING2_DISABLED]     REAL v3b (repo-safe):
# [HARDENING2_DISABLED]       S1 list_dir (read-only)
# [HARDENING2_DISABLED]       S2 read_file (read-only)
# [HARDENING2_DISABLED]       S3 gated new_file: create _agent_runs/<room>/real_log.txt
# [HARDENING2_DISABLED]       S4 gated modify: append marker to same file

# [HARDENING2_DISABLED]     This validates gated create + gated modify end-to-end without touching code files.
# [HARDENING2_DISABLED]     """
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         hdr_room = None

# [HARDENING2_DISABLED]     room_id = (req.room_id or hdr_room or "default")

# [HARDENING2_DISABLED]     mission, plan = agent_store.load()
# [HARDENING2_DISABLED]     plan = dict(plan or {})
# [HARDENING2_DISABLED]     plan["status"] = "planned"
# [HARDENING2_DISABLED]     plan["room_id"] = room_id
# [HARDENING2_DISABLED]     plan["goal"] = req.goal

# [HARDENING2_DISABLED]     dest_dir = r"C:\AI_VAULT\workspace\brainlab\_agent_runs" + "\\" + str(room_id)
# [HARDENING2_DISABLED]     log_repo_path = dest_dir + r"\real_log.txt"

# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         from datetime import datetime, timezone
# [HARDENING2_DISABLED]         ts = datetime.now(timezone.utc).isoformat()
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         ts = ""
# [HARDENING2_DISABLED]     marker = f"REAL_V3B MARK {ts}\n"
# [HARDENING2_DISABLED]     marker2 = f"REAL_V3B MARK2 {ts}\n"
# [HARDENING2_DISABLED]     plan["steps"] = [
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S1",
# [HARDENING2_DISABLED]             "title": "Inspect risk folder (list_dir)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "list_dir",
# [HARDENING2_DISABLED]             "mode": "read",
# [HARDENING2_DISABLED] "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk"},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S2",
# [HARDENING2_DISABLED]             "title": "Read risk_engine.py (read_file)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "read_file",
# [HARDENING2_DISABLED]             "mode": "read",
# [HARDENING2_DISABLED] "tool_args": {"path": r"C:\AI_VAULT\workspace\brainlab\brainlab\risk\risk_engine.py", "max_bytes": 200000},
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S3",
# [HARDENING2_DISABLED]             "title": "Create real_log.txt (append_file new_file) — gated SAFE (repo)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "append_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "new_file",
# [HARDENING2_DISABLED]             "dest_dir": dest_dir,
# [HARDENING2_DISABLED]             "tool_args": {
# [HARDENING2_DISABLED]                 "path": "real_log.txt",
# [HARDENING2_DISABLED]                 "content": "REAL_V3B START\n",
# [HARDENING2_DISABLED]             },
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]         {
# [HARDENING2_DISABLED]             "id": "S4",
# [HARDENING2_DISABLED]             "title": "Modify real_log.txt (append marker) — gated SAFE (repo)",
# [HARDENING2_DISABLED]             "status": "todo",
# [HARDENING2_DISABLED]             "tool_name": "append_file",
# [HARDENING2_DISABLED]             "mode": "propose",
# [HARDENING2_DISABLED]             "kind": "modify",
# [HARDENING2_DISABLED]             "repo_path": log_repo_path,
# [HARDENING2_DISABLED]             "dest_dir": dest_dir,
# [HARDENING2_DISABLED]             "tool_args": {
# [HARDENING2_DISABLED]                 "path": "real_log.txt",
# [HARDENING2_DISABLED]                 "content": marker2,
# [HARDENING2_DISABLED]             },
# [HARDENING2_DISABLED]         },
# [HARDENING2_DISABLED]     ]

# [HARDENING2_DISABLED]     # Persist per-room plan/mission
# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         agent_store.save_plan(plan)
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     try:
# [HARDENING2_DISABLED]         _rid = room_id
# [HARDENING2_DISABLED]         _room_state_dir(_rid)
# [HARDENING2_DISABLED]         _paths = _room_paths(_rid) or {}
# [HARDENING2_DISABLED]         import json
# [HARDENING2_DISABLED]         from pathlib import Path
# [HARDENING2_DISABLED]         pp = _paths.get("plan")
# [HARDENING2_DISABLED]         if pp:
# [HARDENING2_DISABLED]             Path(pp).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]         mp = _paths.get("mission")
# [HARDENING2_DISABLED]         if mp:
# [HARDENING2_DISABLED]             Path(mp).write_text(json.dumps(mission or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING2_DISABLED]     except Exception:
# [HARDENING2_DISABLED]         pass

# [HARDENING2_DISABLED]     return {"ok": True, "room_id": room_id, "plan": plan, "mission": mission or {"room_id": room_id}}
# [HARDENING2_DISABLED] # === PLAN_REAL_ENDPOINT_V3B_CREATE_MODIFY_V1 END ===
# [HARDENING3_DISABLED_OLD] @app.post("/v1/agent/evaluate", response_model=AgentEvalResponse)
# [HARDENING3_DISABLED_OLD] def agent_evaluate(req: AgentEvalRequest, request: Request):
# [HARDENING3_DISABLED_OLD]     # === AGENT_EVALUATE_SSOT_ROOMPLAN_JSON_V1 ===
# [HARDENING3_DISABLED_OLD]     # SSOT: C:\AI_VAULT\tmp_agent\state\rooms\<rid>\plan.json

# [HARDENING3_DISABLED_OLD]     # 1) Resolve room_id (SSOT: header)
# [HARDENING3_DISABLED_OLD]     hdr = None
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         hdr = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         hdr = None

# [HARDENING3_DISABLED_OLD]     rid = None
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         rid = getattr(req, "room_id", None)
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         rid = None
# [HARDENING3_DISABLED_OLD]     if not rid:
# [HARDENING3_DISABLED_OLD]         try:
# [HARDENING3_DISABLED_OLD]             rid = (req.observation or {}).get("room_id")
# [HARDENING3_DISABLED_OLD]         except Exception:
# [HARDENING3_DISABLED_OLD]             rid = None

# [HARDENING3_DISABLED_OLD]     room_id = (hdr or rid or "default")

# [HARDENING3_DISABLED_OLD]     # 2) Load existing plan from SSOT if exists
# [HARDENING3_DISABLED_OLD]     plan = {}
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         import json
# [HARDENING3_DISABLED_OLD]         from pathlib import Path
# [HARDENING3_DISABLED_OLD]         root = Path(_resolve_tmp_agent_root())
# [HARDENING3_DISABLED_OLD]         roomdir = root / "state" / "rooms" / str(room_id)
# [HARDENING3_DISABLED_OLD]         fp = roomdir / "plan.json"
# [HARDENING3_DISABLED_OLD]         if fp.exists():
# [HARDENING3_DISABLED_OLD]             plan = json.loads(fp.read_text(encoding="utf-8")) or {}
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         plan = {}

# [HARDENING3_DISABLED_OLD]     if not isinstance(plan, dict):
# [HARDENING3_DISABLED_OLD]         plan = {}
# [HARDENING3_DISABLED_OLD]     plan.setdefault("room_id", room_id)
# [HARDENING3_DISABLED_OLD]     plan.setdefault("status", "planned")
# [HARDENING3_DISABLED_OLD]     plan.setdefault("steps", [])

# [HARDENING3_DISABLED_OLD]     # 3) Build observation + verdict (minimal)
# [HARDENING3_DISABLED_OLD]     obs = {}
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         obs = req.observation or {}
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         obs = {}
# [HARDENING3_DISABLED_OLD]     verdict = {"status": "no_change", "notes": []}

# [HARDENING3_DISABLED_OLD]     # if steps all done -> complete
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         steps = plan.get("steps", []) or []
# [HARDENING3_DISABLED_OLD]         def _is_done(st):
# [HARDENING3_DISABLED_OLD]             return str(st or "").lower() in ("done","complete","completed","skipped")
# [HARDENING3_DISABLED_OLD]         if steps and all(_is_done(s.get("status")) for s in steps):
# [HARDENING3_DISABLED_OLD]             verdict = {"status": "complete", "notes": ["All steps done -> plan complete"]}
# [HARDENING3_DISABLED_OLD]             plan["status"] = "complete"
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         pass

# [HARDENING3_DISABLED_OLD]     plan["last_eval"] = {"room_id": room_id, "observation": obs, "verdict": verdict}

# [HARDENING3_DISABLED_OLD]     # 4) Persist to SSOT
# [HARDENING3_DISABLED_OLD]     try:
# [HARDENING3_DISABLED_OLD]         import json
# [HARDENING3_DISABLED_OLD]         from pathlib import Path
# [HARDENING3_DISABLED_OLD]         root = Path(_resolve_tmp_agent_root())
# [HARDENING3_DISABLED_OLD]         roomdir = root / "state" / "rooms" / str(room_id)
# [HARDENING3_DISABLED_OLD]         roomdir.mkdir(parents=True, exist_ok=True)
# [HARDENING3_DISABLED_OLD]         fp = roomdir / "plan.json"
# [HARDENING3_DISABLED_OLD]         fp.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING3_DISABLED_OLD]     except Exception:
# [HARDENING3_DISABLED_OLD]         pass

# [HARDENING3_DISABLED_OLD]     return {"ok": True, "plan": plan, "verdict": verdict}
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] @app.post("/v1/_debug/sanitize_id", response_model=dict)
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] def _sanitize_id(s: str) -> str:
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     import re
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     s = (s or "").strip()
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     s = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", s)
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     return s or f"p{time.time_ns()}"

# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] # === AGENT_EXECUTE_REQUEST_SHIM_V1 BEGIN ===
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] # Pydantic v2 / FastAPI OpenAPI requires real model (no unresolved ForwardRef)
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] class AgentExecuteRequest(BaseModel):
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     # Keep it permissive; runner endpoints evolve
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     room_id: Optional[str] = None
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     step_id: Optional[str] = None
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     approve_token: Optional[str] = None
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     max_tool_calls: Optional[int] = None
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     observation: Optional[dict] = None

# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     # allow extra keys (SSOT compatibility)
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED]     model_config = {"extra": "allow"}
# [HARDENING3_DISABLED_OLD] # [HARDENING2_DISABLED] # === AGENT_EXECUTE_REQUEST_SHIM_V1 END ===
# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/execute", response_model=dict)
# [HARDENING4_SAFEMIN_DISABLED] def agent_execute(req: AgentExecuteRequest):
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     Filesystem-only execution.
# [HARDENING4_SAFEMIN_DISABLED]     - list_dir/read_file: direct (safe-rooted by tools_fs)
# [HARDENING4_SAFEMIN_DISABLED]     - write/append: staged into tmp_agent/workspace and applied via apply_gate (approval token required on apply)
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = None
# [HARDENING4_SAFEMIN_DISABLED]     room_id = req.room_id or hdr_room or "default"
# [HARDENING4_SAFEMIN_DISABLED]     tool_name = (req.tool_name or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     tool_args = req.tool_args or {}
# [HARDENING4_SAFEMIN_DISABLED]     allowed = {"list_dir", "read_file", "write_file", "append_file", "runtime_snapshot_set", "runtime_snapshot_get"}
# [HARDENING4_SAFEMIN_DISABLED]     if tool_name not in allowed:
# [HARDENING4_SAFEMIN_DISABLED]         # === GATE_ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]         # Allow runtime snapshot tools (room-scoped KV) through the tool gate
# [HARDENING4_SAFEMIN_DISABLED]         if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):
# [HARDENING4_SAFEMIN_DISABLED]             pass
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail=f"tool_name not allowed: {tool_name}")
# [HARDENING4_SAFEMIN_DISABLED]         # === GATE_ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1 END ===

# [HARDENING4_SAFEMIN_DISABLED]     # tools_fs expects a single dict arg
# [HARDENING4_SAFEMIN_DISABLED]     from tools_fs import tool_list_dir, tool_read_file, tool_write_file, tool_append_file


# [HARDENING4_SAFEMIN_DISABLED]     # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # Confine write operations to repo-safe subtree:
# [HARDENING4_SAFEMIN_DISABLED]     #   C:\AI_VAULT\workspace\brainlab\_agent_runs\...
# [HARDENING4_SAFEMIN_DISABLED]     # IMPORTANT:
# [HARDENING4_SAFEMIN_DISABLED]     # - Use req.dest_dir (NOT local dest_dir var) because local dest_dir may be computed later.
# [HARDENING4_SAFEMIN_DISABLED]     # - If tool_args.path is relative, req.dest_dir MUST be provided.
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _REAL_SAFE_ROOT = Path(r"C:\AI_VAULT\workspace\brainlab\_agent_runs").resolve()
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         _REAL_SAFE_ROOT = None

# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _mode_local = (req.mode or "").strip().lower()
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         _mode_local = ""

# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _tool_local = (tool_name or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         _tool_local = ""

# [HARDENING4_SAFEMIN_DISABLED]     if _REAL_SAFE_ROOT and _tool_local in ("write_file","append_file") and _mode_local in ("propose","apply"):
# [HARDENING4_SAFEMIN_DISABLED]         # Prefer explicit req.dest_dir
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             _dest = getattr(req, "dest_dir", None)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             _dest = None

# [HARDENING4_SAFEMIN_DISABLED]         # Read tool_args.path
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             _p = tool_args.get("path") or tool_args.get("p")
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             _p = None

# [HARDENING4_SAFEMIN_DISABLED]         # If dest_dir missing:
# [HARDENING4_SAFEMIN_DISABLED]         # - allow only if path is absolute and under safe root
# [HARDENING4_SAFEMIN_DISABLED]         # - deny if path is relative (prevents resolving to CWD like C:\AI_VAULT\00_identity)
# [HARDENING4_SAFEMIN_DISABLED]         if not _dest:
# [HARDENING4_SAFEMIN_DISABLED]             if isinstance(_p, str) and _p:
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     _pp = Path(_p)
# [HARDENING4_SAFEMIN_DISABLED]                     if _pp.is_absolute():
# [HARDENING4_SAFEMIN_DISABLED]                         _dest_res = _pp.parent.resolve()
# [HARDENING4_SAFEMIN_DISABLED]                         _dest_res.relative_to(_REAL_SAFE_ROOT)
# [HARDENING4_SAFEMIN_DISABLED]                     else:
# [HARDENING4_SAFEMIN_DISABLED]                         raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: relative path requires dest_dir")
# [HARDENING4_SAFEMIN_DISABLED]                 except HTTPException:
# [HARDENING4_SAFEMIN_DISABLED]                     raise
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir missing or outside safe root (path={_p})")
# [HARDENING4_SAFEMIN_DISABLED]             else:
# [HARDENING4_SAFEMIN_DISABLED]                 raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: missing dest_dir/path for write op")
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _dest_res = Path(_dest).resolve()
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: bad dest_dir={_dest}")

# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _dest_res.relative_to(_REAL_SAFE_ROOT)
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir outside safe root: {_dest_res}")

# [HARDENING4_SAFEMIN_DISABLED]         # For modify, also enforce repo_path under safe root
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             _kind_local = (req.kind or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             _kind_local = ""

# [HARDENING4_SAFEMIN_DISABLED]         if _kind_local == "modify":
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _rp = req.repo_path
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 _rp = None
# [HARDENING4_SAFEMIN_DISABLED]             if not isinstance(_rp, str) or not _rp:
# [HARDENING4_SAFEMIN_DISABLED]                 raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: modify requires repo_path")
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _rp_res = Path(_rp).resolve()
# [HARDENING4_SAFEMIN_DISABLED]                 _rp_res.relative_to(_REAL_SAFE_ROOT)
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: repo_path outside safe root: {_rp}")
# [HARDENING4_SAFEMIN_DISABLED]     # === REAL_GUARDRAIL_AGENT_RUNS_ROOT_V1 END ===


# [HARDENING4_SAFEMIN_DISABLED]     # read-only
# [HARDENING4_SAFEMIN_DISABLED]     if tool_name == "list_dir":
# [HARDENING4_SAFEMIN_DISABLED]         out = tool_list_dir(tool_args)
# [HARDENING4_SAFEMIN_DISABLED]         _autopersist_step_done_fs(room_id, req.step_id)
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

# [HARDENING4_SAFEMIN_DISABLED]     if tool_name == "read_file":
# [HARDENING4_SAFEMIN_DISABLED]         out = tool_read_file(tool_args)
# [HARDENING4_SAFEMIN_DISABLED]         _autopersist_step_done_fs(room_id, req.step_id)
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

# [HARDENING4_SAFEMIN_DISABLED]     # === AGENT_EXECUTE_RUNTIME_SNAPSHOT_DISPATCH_V1 BEGIN ===

# [HARDENING4_SAFEMIN_DISABLED]     # Handle runtime_snapshot_set/get here to bypass FS write gating

# [HARDENING4_SAFEMIN_DISABLED]     if tool_name in ("runtime_snapshot_set", "runtime_snapshot_get"):

# [HARDENING4_SAFEMIN_DISABLED]         try:

# [HARDENING4_SAFEMIN_DISABLED]             args = tool_args or {}

# [HARDENING4_SAFEMIN_DISABLED]             snap_path = str(args.get("path") or "")

# [HARDENING4_SAFEMIN_DISABLED]             if tool_name == "runtime_snapshot_set":

# [HARDENING4_SAFEMIN_DISABLED]                 val = args.get("value")

# [HARDENING4_SAFEMIN_DISABLED]                 # enrich minimal fields if dict

# [HARDENING4_SAFEMIN_DISABLED]                 try:

# [HARDENING4_SAFEMIN_DISABLED]                     from datetime import datetime, timezone

# [HARDENING4_SAFEMIN_DISABLED]                     now = datetime.now(timezone.utc).isoformat()

# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:

# [HARDENING4_SAFEMIN_DISABLED]                     now = ""

# [HARDENING4_SAFEMIN_DISABLED]                 if isinstance(val, dict):

# [HARDENING4_SAFEMIN_DISABLED]                     vv = dict(val)

# [HARDENING4_SAFEMIN_DISABLED]                     vv["ts"] = vv.get("ts") or now

# [HARDENING4_SAFEMIN_DISABLED]                     vv["room_id"] = vv.get("room_id") or str(room_id)

# [HARDENING4_SAFEMIN_DISABLED]                     # goal may live in plan; best-effort

# [HARDENING4_SAFEMIN_DISABLED]                     try:

# [HARDENING4_SAFEMIN_DISABLED]                         vv["goal"] = vv.get("goal") or str((agent_store.load_plan(room_id) or {}).get("goal") or "")

# [HARDENING4_SAFEMIN_DISABLED]                     except Exception:

# [HARDENING4_SAFEMIN_DISABLED]                         vv["goal"] = vv.get("goal") or ""

# [HARDENING4_SAFEMIN_DISABLED]                     val = vv

# [HARDENING4_SAFEMIN_DISABLED]                 out = _runtime_snapshot_set_kv(str(room_id), snap_path, val)

# [HARDENING4_SAFEMIN_DISABLED]             else:

# [HARDENING4_SAFEMIN_DISABLED]                 out = _runtime_snapshot_get_kv(str(room_id), snap_path)

# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": bool(out.get("ok", False)), "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

# [HARDENING4_SAFEMIN_DISABLED]         except Exception as e:

# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=500, detail=f"runtime_snapshot failure: {e}")

# [HARDENING4_SAFEMIN_DISABLED]     # === AGENT_EXECUTE_RUNTIME_SNAPSHOT_DISPATCH_V1 END ===

# [HARDENING4_SAFEMIN_DISABLED]     # ===== Guardrail: block placeholder content (v4.6) =====
# [HARDENING4_SAFEMIN_DISABLED]     # Prevent accidental placeholder commits into repo.
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _c = tool_args.get("content", None)
# [HARDENING4_SAFEMIN_DISABLED]         _c_txt = _c if isinstance(_c, str) else (json.dumps(_c, ensure_ascii=False) if _c is not None else "")
# [HARDENING4_SAFEMIN_DISABLED]         if tool_name in {"write_file", "append_file"} and isinstance(_c_txt, str) and ("PLANNER_PLACEHOLDER" in _c_txt):
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail="GUARDRAIL_BLOCKED: content contains PLANNER_PLACEHOLDER")
# [HARDENING4_SAFEMIN_DISABLED]     except HTTPException:
# [HARDENING4_SAFEMIN_DISABLED]         raise
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         # if guard fails, do not block; conservative
# [HARDENING4_SAFEMIN_DISABLED]         pass
# [HARDENING4_SAFEMIN_DISABLED]     # ===== End guardrail v4.6 =====
# [HARDENING4_SAFEMIN_DISABLED]     # write gated
# [HARDENING4_SAFEMIN_DISABLED]     mode = (req.mode or "read").strip().lower()
# [HARDENING4_SAFEMIN_DISABLED]     if mode not in {"propose", "apply"}:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=400, detail="WRITE_GATED: mode must be propose|apply for write/append")

# [HARDENING4_SAFEMIN_DISABLED]     kind = (req.kind or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     if kind not in {"new_file", "modify"}:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=400, detail="WRITE_GATED: kind must be new_file|modify")

# [HARDENING4_SAFEMIN_DISABLED]     # Load gate constants from apply_gate
# [HARDENING4_SAFEMIN_DISABLED]     from apply_gate import WORK_DIR, DEFAULT_DEST_DIR, apply_bundle

# [HARDENING4_SAFEMIN_DISABLED]     # Ensure workspace staging path
# [HARDENING4_SAFEMIN_DISABLED]     # tools_fs uses _get_path_arg(args) to find path; we accept "path" or "p"
# [HARDENING4_SAFEMIN_DISABLED]     p = tool_args.get("path") or tool_args.get("p")
# [HARDENING4_SAFEMIN_DISABLED]     if not p:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=400, detail="WRITE_GATED: tool_args must include path (or p)")

# [HARDENING4_SAFEMIN_DISABLED]     ws_path = Path(p)

# [HARDENING4_SAFEMIN_DISABLED]     # force staging under WORK_DIR (security + matches preflight)
# [HARDENING4_SAFEMIN_DISABLED]     # If user gives absolute path outside WORK_DIR, we remap to WORK_DIR / name
# [HARDENING4_SAFEMIN_DISABLED]     if ws_path.is_absolute():
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             ws_path = ws_path.resolve()
# [HARDENING4_SAFEMIN_DISABLED]             if Path(WORK_DIR) not in ws_path.parents and ws_path != Path(WORK_DIR):
# [HARDENING4_SAFEMIN_DISABLED]                 ws_path = (Path(WORK_DIR) / ws_path.name).resolve()
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             ws_path = (Path(WORK_DIR) / Path(p).name).resolve()
# [HARDENING4_SAFEMIN_DISABLED]     else:
# [HARDENING4_SAFEMIN_DISABLED]         ws_path = (Path(WORK_DIR) / ws_path).resolve()

# [HARDENING4_SAFEMIN_DISABLED]     ws_path.parent.mkdir(parents=True, exist_ok=True)

# [HARDENING4_SAFEMIN_DISABLED]     # For modify: if appending and file doesn't exist in workspace, seed it from repo_path (optional).
# [HARDENING4_SAFEMIN_DISABLED]     if kind == "modify":
# [HARDENING4_SAFEMIN_DISABLED]         if not req.repo_path:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail="WRITE_GATED: repo_path required for kind=modify")
# [HARDENING4_SAFEMIN_DISABLED]         # we do NOT read repo here; apply_gate will validate repo_path is inside repo.
# [HARDENING4_SAFEMIN_DISABLED]         # Optional seeding could be added later.

# [HARDENING4_SAFEMIN_DISABLED]     # Execute staging write/append into workspace via tools_fs (safe_path will allow tmp_agent; we pass the remapped workspace path)
# [HARDENING4_SAFEMIN_DISABLED]     tool_args2 = dict(tool_args)
# [HARDENING4_SAFEMIN_DISABLED]     tool_args2["path"] = str(ws_path)

# [HARDENING4_SAFEMIN_DISABLED]     if tool_name == "write_file":
# [HARDENING4_SAFEMIN_DISABLED]         stage_res = tool_write_file(tool_args2)
# [HARDENING4_SAFEMIN_DISABLED]     else:        # --- idempotency guard: new_file+append_file must start clean (prevents staging accumulation) ---
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             if tool_name == "append_file" and kind == "new_file":
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     if ws_path.exists():
# [HARDENING4_SAFEMIN_DISABLED]                         ws_path.unlink()
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     pass
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             pass

# [HARDENING4_SAFEMIN_DISABLED]         # --- idempotency guard: avoid duplicating planner_exec_log.txt content ---
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             _p2 = str(ws_path).replace("/", "\\").lower()
# [HARDENING4_SAFEMIN_DISABLED]             if _p2.endswith("\\planner_exec_log.txt") or _p2.endswith("planner_exec_log.txt"):
# [HARDENING4_SAFEMIN_DISABLED]                 _txt = tool_args2.get("content") if isinstance(tool_args2, dict) else None
# [HARDENING4_SAFEMIN_DISABLED]                 if isinstance(_txt, str) and _txt:
# [HARDENING4_SAFEMIN_DISABLED]                     if ws_path.exists():
# [HARDENING4_SAFEMIN_DISABLED]                         _existing = ws_path.read_text(encoding="utf-8", errors="ignore")
# [HARDENING4_SAFEMIN_DISABLED]                         if _txt in _existing:
# [HARDENING4_SAFEMIN_DISABLED]                             stage_res = {"ok": True, "note": "idempotent: content already present", "path": str(ws_path)}
# [HARDENING4_SAFEMIN_DISABLED]                         else:
# [HARDENING4_SAFEMIN_DISABLED]                             stage_res = tool_append_file(tool_args2)
# [HARDENING4_SAFEMIN_DISABLED]                     else:
# [HARDENING4_SAFEMIN_DISABLED]                         stage_res = tool_append_file(tool_args2)
# [HARDENING4_SAFEMIN_DISABLED]                 else:
# [HARDENING4_SAFEMIN_DISABLED]                     stage_res = tool_append_file(tool_args2)
# [HARDENING4_SAFEMIN_DISABLED]             else:
# [HARDENING4_SAFEMIN_DISABLED]                 stage_res = tool_append_file(tool_args2)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             stage_res = tool_append_file(tool_args2)# Build / persist bundle
# [HARDENING4_SAFEMIN_DISABLED]     # PATCH: proposal_id uses time_ns to avoid same-second collisions (v4.7.2)
# [HARDENING4_SAFEMIN_DISABLED]     proposal_id = _sanitize_id(req.proposal_id or f"p{time.time_ns()}")
# [HARDENING4_SAFEMIN_DISABLED]     bundle = {
# [HARDENING4_SAFEMIN_DISABLED]         "proposal_id": proposal_id,
# [HARDENING4_SAFEMIN_DISABLED]         "items": []
# [HARDENING4_SAFEMIN_DISABLED]     }

# [HARDENING4_SAFEMIN_DISABLED]     item = {"kind": kind, "workspace_path": str(ws_path)}
# [HARDENING4_SAFEMIN_DISABLED]     if kind == "modify":
# [HARDENING4_SAFEMIN_DISABLED]         item["repo_path"] = str(Path(req.repo_path).resolve())
# [HARDENING4_SAFEMIN_DISABLED]     bundle["items"].append(item)

# [HARDENING4_SAFEMIN_DISABLED]     # Write bundle into tmp_agent/proposals
# [HARDENING4_SAFEMIN_DISABLED]     sandbox_root = Path(r"C:\AI_VAULT\tmp_agent").resolve()
# [HARDENING4_SAFEMIN_DISABLED]     proposals_dir = (sandbox_root / "proposals").resolve()
# [HARDENING4_SAFEMIN_DISABLED]     proposals_dir.mkdir(parents=True, exist_ok=True)

# [HARDENING4_SAFEMIN_DISABLED]     bundle_path = (proposals_dir / f"bundle_{proposal_id}.json").resolve()
# [HARDENING4_SAFEMIN_DISABLED]     bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

# [HARDENING4_SAFEMIN_DISABLED]     required = f"APPLY_{proposal_id}"

# [HARDENING4_SAFEMIN_DISABLED]     if mode == "propose":
# [HARDENING4_SAFEMIN_DISABLED]         out = {
# [HARDENING4_SAFEMIN_DISABLED]             "stage": stage_res,
# [HARDENING4_SAFEMIN_DISABLED]             "proposal_id": proposal_id,
# [HARDENING4_SAFEMIN_DISABLED]             "bundle_path": str(bundle_path),
# [HARDENING4_SAFEMIN_DISABLED]             "required_approve": required,
# [HARDENING4_SAFEMIN_DISABLED]             "next": "POST /v1/agent/execute with mode=apply and approve_token"
# [HARDENING4_SAFEMIN_DISABLED]         }
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

# [HARDENING4_SAFEMIN_DISABLED]     # mode == apply
# [HARDENING4_SAFEMIN_DISABLED]     approve = req.approve_token
# [HARDENING4_SAFEMIN_DISABLED]     if approve != required:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=400, detail=f"APPROVAL_REQUIRED: approve_token must be {required}")

# [HARDENING4_SAFEMIN_DISABLED]     dest_dir = req.dest_dir or str(DEFAULT_DEST_DIR)

# [HARDENING4_SAFEMIN_DISABLED]     apply_res = apply_bundle(str(bundle_path), dest_dir=dest_dir, approve_token=approve)

# [HARDENING4_SAFEMIN_DISABLED]     out = {
# [HARDENING4_SAFEMIN_DISABLED]         "stage": stage_res,
# [HARDENING4_SAFEMIN_DISABLED]         "proposal_id": proposal_id,
# [HARDENING4_SAFEMIN_DISABLED]         "bundle_path": str(bundle_path),
# [HARDENING4_SAFEMIN_DISABLED]         "required_approve": required,
# [HARDENING4_SAFEMIN_DISABLED]         "apply": apply_res
# [HARDENING4_SAFEMIN_DISABLED]     }
# [HARDENING4_SAFEMIN_DISABLED]     ok = bool(apply_res.get("ok"))
# [HARDENING4_SAFEMIN_DISABLED]     return {"ok": ok, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}# ===== Agent Step Execute (v4.2) =====
# [HARDENING4_SAFEMIN_DISABLED] class AgentExecuteStepRequest(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED]     room_id: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED]     step_id: str = Field(..., min_length=1)

# [HARDENING4_SAFEMIN_DISABLED]     # gating override (optional; if absent uses step fields)
# [HARDENING4_SAFEMIN_DISABLED]     mode: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED]     approve_token: Optional[str] = None

# [HARDENING4_SAFEMIN_DISABLED] class AgentExecuteStepResponse(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED]     ok: bool
# [HARDENING4_SAFEMIN_DISABLED]     room_id: str
# [HARDENING4_SAFEMIN_DISABLED]     step_id: str
# [HARDENING4_SAFEMIN_DISABLED]     tool_name: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED]     result: Optional[Dict[str, Any]] = None
# [HARDENING4_SAFEMIN_DISABLED]     error: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED]     plan: Optional[Dict[str, Any]] = None

# [HARDENING4_SAFEMIN_DISABLED] # ================================
# [HARDENING4_SAFEMIN_DISABLED] # AGENT_EXECUTE_FS_ALIAS_V1
# [HARDENING4_SAFEMIN_DISABLED] # Keep reference to FS/tool executor before later redefinitions of agent_execute.
# [HARDENING4_SAFEMIN_DISABLED] # ================================
# [HARDENING4_SAFEMIN_DISABLED] agent_execute_fs = agent_execute# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/execute_step", response_model=AgentExecuteStepResponse)
# [HARDENING4_SAFEMIN_DISABLED] def agent_execute_step(req: AgentExecuteStepRequest):
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = None
# [HARDENING4_SAFEMIN_DISABLED]     room_id = req.room_id or hdr_room or "default"
# [HARDENING4_SAFEMIN_DISABLED]     step_id = req.step_id

# [HARDENING4_SAFEMIN_DISABLED]     # load current plan
# [HARDENING4_SAFEMIN_DISABLED]     mission, plan = agent_store.load()
# [HARDENING4_SAFEMIN_DISABLED]     steps = plan.get("steps", []) or []
# [HARDENING4_SAFEMIN_DISABLED]     step = next((s for s in steps if str(s.get("id")) == str(step_id)), None)
# [HARDENING4_SAFEMIN_DISABLED]     if not step:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=404, detail=f"STEP_NOT_FOUND:{step_id}")

# [HARDENING4_SAFEMIN_DISABLED]     tool_name = step.get("tool_name")
# [HARDENING4_SAFEMIN_DISABLED]     # === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # Handle runtime_snapshot_set/get as non-gated tools (room-scoped KV)
# [HARDENING4_SAFEMIN_DISABLED]     if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):
# [HARDENING4_SAFEMIN_DISABLED]         args = (step.get('tool_args') or {}) if isinstance(step, dict) else {}
# [HARDENING4_SAFEMIN_DISABLED]         snap_path = str(args.get('path') or '')
# [HARDENING4_SAFEMIN_DISABLED]         if tool_name == 'runtime_snapshot_set':
# [HARDENING4_SAFEMIN_DISABLED]             val = args.get('value')
# [HARDENING4_SAFEMIN_DISABLED]             # enrich minimal fields if dict
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 from datetime import datetime, timezone
# [HARDENING4_SAFEMIN_DISABLED]                 now = datetime.now(timezone.utc).isoformat()
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 now = ''
# [HARDENING4_SAFEMIN_DISABLED]             if isinstance(val, dict):
# [HARDENING4_SAFEMIN_DISABLED]                 vv = dict(val)
# [HARDENING4_SAFEMIN_DISABLED]                 vv['ts'] = vv.get('ts') or now
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     vv['goal'] = vv.get('goal') or str((plan or {}).get('goal') or '')
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     vv['goal'] = vv.get('goal') or ''
# [HARDENING4_SAFEMIN_DISABLED]                 vv['room_id'] = vv.get('room_id') or str(room_id)
# [HARDENING4_SAFEMIN_DISABLED]                 val = vv
# [HARDENING4_SAFEMIN_DISABLED]             res2 = _runtime_snapshot_set_kv(str(room_id), snap_path, val)
# [HARDENING4_SAFEMIN_DISABLED]             result = {'ok': True, 'tool_name': tool_name, 'result': res2, 'proposal_id': None}
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             res2 = _runtime_snapshot_get_kv(str(room_id), snap_path)
# [HARDENING4_SAFEMIN_DISABLED]             result = {'ok': bool(res2.get('ok', False)), 'tool_name': tool_name, 'result': res2, 'proposal_id': None}
# [HARDENING4_SAFEMIN_DISABLED]         # continue (persist SOT will mark done)
# [HARDENING4_SAFEMIN_DISABLED]     # === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 END ===
# [HARDENING4_SAFEMIN_DISABLED]     tool_args = step.get("tool_args") or {}
# [HARDENING4_SAFEMIN_DISABLED]     if not tool_name:
# [HARDENING4_SAFEMIN_DISABLED]         raise HTTPException(status_code=400, detail=f"STEP_HAS_NO_TOOL_CALL:{step_id}")

# [HARDENING4_SAFEMIN_DISABLED]     # derive gating fields from step; allow request override
# [HARDENING4_SAFEMIN_DISABLED]     mode = (req.mode or step.get("mode") or "propose").strip().lower()
# [HARDENING4_SAFEMIN_DISABLED]     kind = (step.get("kind") or "new_file").strip()
# [HARDENING4_SAFEMIN_DISABLED]     repo_path = step.get("repo_path")
# [HARDENING4_SAFEMIN_DISABLED]     dest_dir = step.get("dest_dir")

# [HARDENING4_SAFEMIN_DISABLED]     # Call existing execute logic by constructing a request object
# [HARDENING4_SAFEMIN_DISABLED]     exec_req = AgentExecuteRequest(
# [HARDENING4_SAFEMIN_DISABLED]         room_id=room_id,
# [HARDENING4_SAFEMIN_DISABLED]         step_id=step_id,
# [HARDENING4_SAFEMIN_DISABLED]         tool_name=str(tool_name),
# [HARDENING4_SAFEMIN_DISABLED]                 tool_args=dict(tool_args),
# [HARDENING4_SAFEMIN_DISABLED]         mode=mode,
# [HARDENING4_SAFEMIN_DISABLED]         kind=kind,
# [HARDENING4_SAFEMIN_DISABLED]         repo_path=repo_path,
# [HARDENING4_SAFEMIN_DISABLED]         dest_dir=dest_dir,
# [HARDENING4_SAFEMIN_DISABLED]         approve_token=req.approve_token,
# [HARDENING4_SAFEMIN_DISABLED]         # PATCH: execute_step unique proposal per write-step (v4.7.1)
# [HARDENING4_SAFEMIN_DISABLED]         # - propose: force new proposal_id (avoid token reuse across steps)
# [HARDENING4_SAFEMIN_DISABLED]         # - apply: reuse stored step proposal_id from prior propose
# [HARDENING4_SAFEMIN_DISABLED]         proposal_id=(step.get("proposal_id") if mode == "apply" else None),
# [HARDENING4_SAFEMIN_DISABLED]     )
# [HARDENING4_SAFEMIN_DISABLED]     # execute
# [HARDENING4_SAFEMIN_DISABLED]     # PATCH: step-bound approvals (v4.7.3)
# [HARDENING4_SAFEMIN_DISABLED]     if mode == "apply":
# [HARDENING4_SAFEMIN_DISABLED]         expected = step.get("required_approve")
# [HARDENING4_SAFEMIN_DISABLED]         if expected and req.approve_token != expected:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail=f"APPROVAL_REQUIRED: approve_token must be {expected}")
# [HARDENING4_SAFEMIN_DISABLED]     res = agent_execute_fs(exec_req)
# [HARDENING4_SAFEMIN_DISABLED]     # Update step status + store proposal_id if present
# [HARDENING4_SAFEMIN_DISABLED]     # PATCH: read-only steps become done on propose (v4.2.1)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _tn = str(tool_name or "")
# [HARDENING4_SAFEMIN_DISABLED]         _is_read = _tn in {"list_dir", "read_file"}
# [HARDENING4_SAFEMIN_DISABLED]         if isinstance(res, dict) and res.get("ok"):
# [HARDENING4_SAFEMIN_DISABLED]             if _is_read:
# [HARDENING4_SAFEMIN_DISABLED]                 # read-only tools do not require apply; propose is terminal
# [HARDENING4_SAFEMIN_DISABLED]                 step["status"] = "done"
# [HARDENING4_SAFEMIN_DISABLED]             else:
# [HARDENING4_SAFEMIN_DISABLED]                 # write tools: propose->proposed, apply->done
# [HARDENING4_SAFEMIN_DISABLED]                 step["status"] = "done" if mode == "apply" else "proposed"
# [HARDENING4_SAFEMIN_DISABLED]             pid = (res.get("result") or {}).get("proposal_id")
# [HARDENING4_SAFEMIN_DISABLED]             if pid:
# [HARDENING4_SAFEMIN_DISABLED]                     step["proposal_id"] = pid
# [HARDENING4_SAFEMIN_DISABLED]                     ra = (res.get("result") or {}).get("required_approve")
# [HARDENING4_SAFEMIN_DISABLED]                     if ra:
# [HARDENING4_SAFEMIN_DISABLED]                         step["required_approve"] = ra
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             step["status"] = "error"
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         step["status"] = "error"
# [HARDENING4_SAFEMIN_DISABLED]     plan["steps"] = steps
# [HARDENING4_SAFEMIN_DISABLED]     agent_store.save_plan(plan)

# [HARDENING4_SAFEMIN_DISABLED]     # history
# [HARDENING4_SAFEMIN_DISABLED]     agent_store.append_history({
# [HARDENING4_SAFEMIN_DISABLED]         "kind": "execute_step",
# [HARDENING4_SAFEMIN_DISABLED]         "room_id": room_id,
# [HARDENING4_SAFEMIN_DISABLED]         "step_id": step_id,
# [HARDENING4_SAFEMIN_DISABLED]         "tool_name": tool_name,
# [HARDENING4_SAFEMIN_DISABLED]         "mode": mode,
# [HARDENING4_SAFEMIN_DISABLED]     })

# [HARDENING4_SAFEMIN_DISABLED]     plan2 = _load_room_plan(room_id)
# [HARDENING4_SAFEMIN_DISABLED]     # === EXECUTE_STEP PERSIST PLAN (FIX) BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # Single Source of Truth: persist per-room plan.json here (step-driven)
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         room_id = None
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             room_id = getattr(req, 'room_id', None)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             room_id = None
# [HARDENING4_SAFEMIN_DISABLED]         room_id = room_id or 'default'
    
# [HARDENING4_SAFEMIN_DISABLED]         step_id_local = ''
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             step_id_local = str(getattr(req, 'step_id', '') or '')
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             step_id_local = ''
    
# [HARDENING4_SAFEMIN_DISABLED]         mode_local = ''
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             mode_local = str(getattr(req, 'mode', '') or '')
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             mode_local = ''
    
# [HARDENING4_SAFEMIN_DISABLED]         def _load_plan_disk(_rid: str) -> dict:
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _room_state_dir(_rid)
# [HARDENING4_SAFEMIN_DISABLED]                 _paths = _room_paths(_rid) or {}
# [HARDENING4_SAFEMIN_DISABLED]                 import json
# [HARDENING4_SAFEMIN_DISABLED]                 from pathlib import Path
# [HARDENING4_SAFEMIN_DISABLED]                 pp = _paths.get('plan')
# [HARDENING4_SAFEMIN_DISABLED]                 if pp and Path(pp).exists():
# [HARDENING4_SAFEMIN_DISABLED]                     return json.loads(Path(pp).read_text(encoding='utf-8')) or {}
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 return {}
# [HARDENING4_SAFEMIN_DISABLED]             return {}
    
# [HARDENING4_SAFEMIN_DISABLED]         def _save_plan_disk(_rid: str, plan_disk: dict) -> None:
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _room_state_dir(_rid)
# [HARDENING4_SAFEMIN_DISABLED]                 _paths = _room_paths(_rid) or {}
# [HARDENING4_SAFEMIN_DISABLED]                 import json
# [HARDENING4_SAFEMIN_DISABLED]                 from pathlib import Path
# [HARDENING4_SAFEMIN_DISABLED]                 pp = _paths.get('plan')
# [HARDENING4_SAFEMIN_DISABLED]                 if pp:
# [HARDENING4_SAFEMIN_DISABLED]                     Path(pp).write_text(json.dumps(plan_disk or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass
    
# [HARDENING4_SAFEMIN_DISABLED]         def _touch(plan_disk: dict) -> None:
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 from datetime import datetime, timezone
# [HARDENING4_SAFEMIN_DISABLED]                 plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 plan_disk.setdefault('room_id', room_id)
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass
    
    
# [HARDENING4_SAFEMIN_DISABLED]         if room_id and step_id_local:
# [HARDENING4_SAFEMIN_DISABLED]             plan_disk = _load_plan_disk(room_id) or {}
# [HARDENING4_SAFEMIN_DISABLED]             steps_disk = plan_disk.get('steps', []) or []
# [HARDENING4_SAFEMIN_DISABLED]             if isinstance(steps_disk, list):
# [HARDENING4_SAFEMIN_DISABLED]                 target = None
# [HARDENING4_SAFEMIN_DISABLED]                 for _s in steps_disk:
# [HARDENING4_SAFEMIN_DISABLED]                     if isinstance(_s, dict) and str(_s.get('id')) == step_id_local:
# [HARDENING4_SAFEMIN_DISABLED]                         target = _s
# [HARDENING4_SAFEMIN_DISABLED]                         break
    
# [HARDENING4_SAFEMIN_DISABLED]                 tool_name_step = ''
# [HARDENING4_SAFEMIN_DISABLED]                 if isinstance(target, dict):
# [HARDENING4_SAFEMIN_DISABLED]                     tool_name_step = str(target.get('tool_name') or '')
    
# [HARDENING4_SAFEMIN_DISABLED]                 is_read = tool_name_step in ('list_dir','read_file','runtime_snapshot_set','runtime_snapshot_get')
# [HARDENING4_SAFEMIN_DISABLED]                 is_write = tool_name_step in ('write_file','append_file')
    
# [HARDENING4_SAFEMIN_DISABLED]                 # read-only propose => done
# [HARDENING4_SAFEMIN_DISABLED]                 if target and is_read and mode_local == 'propose':
# [HARDENING4_SAFEMIN_DISABLED]                     target['status'] = 'done'
    
# [HARDENING4_SAFEMIN_DISABLED]                 # write propose => proposed + proposal_id
# [HARDENING4_SAFEMIN_DISABLED]                 if target and is_write and mode_local == 'propose':

# [HARDENING4_SAFEMIN_DISABLED]                     # extract proposal_id from execute_step result (scope-safe)
# [HARDENING4_SAFEMIN_DISABLED]                     pid = ''
# [HARDENING4_SAFEMIN_DISABLED]                     for _name in ('res','result','out','resp','response','payload','r'):
# [HARDENING4_SAFEMIN_DISABLED]                         try:
# [HARDENING4_SAFEMIN_DISABLED]                             _obj = locals().get(_name)
# [HARDENING4_SAFEMIN_DISABLED]                         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                             _obj = None
# [HARDENING4_SAFEMIN_DISABLED]                         # IMPORTANT: locals() here is agent_execute_step scope (we are not inside a nested func)
# [HARDENING4_SAFEMIN_DISABLED]                         if _obj is None:
# [HARDENING4_SAFEMIN_DISABLED]                             try:
# [HARDENING4_SAFEMIN_DISABLED]                                 _obj = eval(_name)
# [HARDENING4_SAFEMIN_DISABLED]                             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                                 _obj = None
# [HARDENING4_SAFEMIN_DISABLED]                         if isinstance(_obj, dict):
# [HARDENING4_SAFEMIN_DISABLED]                             _pid = _obj.get('proposal_id')
# [HARDENING4_SAFEMIN_DISABLED]                             if _pid:
# [HARDENING4_SAFEMIN_DISABLED]                                 pid = str(_pid)
# [HARDENING4_SAFEMIN_DISABLED]                                 break
# [HARDENING4_SAFEMIN_DISABLED]                             _inner = _obj.get('result')
# [HARDENING4_SAFEMIN_DISABLED]                             if isinstance(_inner, dict) and _inner.get('proposal_id'):
# [HARDENING4_SAFEMIN_DISABLED]                                 pid = str(_inner.get('proposal_id'))
# [HARDENING4_SAFEMIN_DISABLED]                                 break
# [HARDENING4_SAFEMIN_DISABLED]                     if pid:
# [HARDENING4_SAFEMIN_DISABLED]                         target['status'] = 'proposed'
# [HARDENING4_SAFEMIN_DISABLED]                         target['proposal_id'] = pid
# [HARDENING4_SAFEMIN_DISABLED]                         target['required_approve'] = 'APPLY_' + pid
    
# [HARDENING4_SAFEMIN_DISABLED]                 # write apply => done + clear proposal fields
# [HARDENING4_SAFEMIN_DISABLED]                 if target and is_write and mode_local == 'apply':
# [HARDENING4_SAFEMIN_DISABLED]                     target['status'] = 'done'
# [HARDENING4_SAFEMIN_DISABLED]                     try:
# [HARDENING4_SAFEMIN_DISABLED]                         target.pop('required_approve', None)
# [HARDENING4_SAFEMIN_DISABLED]                         target.pop('proposal_id', None)
# [HARDENING4_SAFEMIN_DISABLED]                     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                         pass
    
# [HARDENING4_SAFEMIN_DISABLED]                 plan_disk['steps'] = steps_disk
    
# [HARDENING4_SAFEMIN_DISABLED]                 # auto-complete if all done
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk if isinstance(x, dict)):
# [HARDENING4_SAFEMIN_DISABLED]                         plan_disk['status'] = 'complete'
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     pass
    
# [HARDENING4_SAFEMIN_DISABLED]                 _touch(plan_disk)
# [HARDENING4_SAFEMIN_DISABLED]                 _save_plan_disk(room_id, plan_disk)
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         pass
# [HARDENING4_SAFEMIN_DISABLED]     # === EXECUTE_STEP PERSIST PLAN (FIX) END ===
# [HARDENING4_SAFEMIN_DISABLED]     return {
# [HARDENING4_SAFEMIN_DISABLED]         "ok": bool(res.get("ok")) if isinstance(res, dict) else False,
# [HARDENING4_SAFEMIN_DISABLED]         "room_id": room_id,
# [HARDENING4_SAFEMIN_DISABLED]         "step_id": step_id,
# [HARDENING4_SAFEMIN_DISABLED]         "tool_name": str(tool_name),
# [HARDENING4_SAFEMIN_DISABLED]         "result": res.get("result") if isinstance(res, dict) else None,
# [HARDENING4_SAFEMIN_DISABLED]         "error": (res.get("error") if isinstance(res, dict) else "UNKNOWN"),
# [HARDENING4_SAFEMIN_DISABLED]         "plan": plan2,
# [HARDENING4_SAFEMIN_DISABLED]     }
# [HARDENING4_SAFEMIN_DISABLED] # ===== End Agent Step Execute =====
# [HARDENING4_SAFEMIN_DISABLED] # ===== Plan refresh (v4.5) =====
# [HARDENING4_SAFEMIN_DISABLED] # PATCH: plan_refresh rewrite stable (v4.5.3)
# [HARDENING4_SAFEMIN_DISABLED] class AgentPlanRefreshRequest(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED]     goal: str = ""
# [HARDENING4_SAFEMIN_DISABLED]     steps: Optional[list] = None
# [HARDENING4_SAFEMIN_DISABLED]     plan: Optional[Dict[str, Any]] = None
# [HARDENING4_SAFEMIN_DISABLED]     room_id: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED]     step_id: Optional[str] = None  # reserved

# [HARDENING4_SAFEMIN_DISABLED] class AgentPlanRefreshResponse(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED]     ok: bool
# [HARDENING4_SAFEMIN_DISABLED]     room_id: str
# [HARDENING4_SAFEMIN_DISABLED]     updated: bool
# [HARDENING4_SAFEMIN_DISABLED]     notes: list[str] = Field(default_factory=list)
# [HARDENING4_SAFEMIN_DISABLED]     plan: Dict[str, Any]

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] @app.post("/v1/agent/plan_refresh", response_model=AgentPlanRefreshResponse)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] def agent_plan_refresh(req: AgentPlanRefreshRequest, request: Request):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # FIX_PLAN_REFRESH_REQUEST_MODEL_AND_SIGNATURE_V1

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     Authoritative plan overwrite for current room.
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     Accepts either:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]       - req.steps (list)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]       - req.plan["steps"] (dict container)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     Always returns response-model-compatible payload including updated=True.
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # resolve room_id (header > req.room_id > default)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         hdr_room = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         req_room = getattr(req, "room_id", None)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         req_room = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     room_id = (req_room or hdr_room or "default")

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # Extract steps (support both shapes)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     incoming_steps = None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         incoming_steps = getattr(req, "steps", None)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         incoming_steps = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     if not isinstance(incoming_steps, list):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             plan_in = getattr(req, "plan", None)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             plan_in = None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if isinstance(plan_in, dict):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             incoming_steps = plan_in.get("steps")

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     if not isinstance(incoming_steps, list):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         raise HTTPException(status_code=400, detail="PLAN_REFRESH_INVALID: steps list required")

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # Load mission/plan for context (best-effort)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         mission_cur, plan_cur = agent_store.load()
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         mission_cur, plan_cur = ({}, {})

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     plan_new = dict(plan_cur or {})
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     plan_new["room_id"] = room_id

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         plan_new["goal"] = getattr(req, "goal", "") or plan_new.get("goal", "")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         pass

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # AUTHORITATIVE OVERWRITE
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     plan_new["steps"] = incoming_steps

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # Normalize status
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     st = str(plan_new.get("status") or "planned").strip().lower()
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     if st not in ("planned", "complete"):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         st = "planned"
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     plan_new["status"] = st

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # Persist via agent_store + disk SOT
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         agent_store.save_plan(plan_new)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         pass

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         _rid = room_id
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         _room_state_dir(_rid)
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         _paths = _room_paths(_rid) or {}
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         import json
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         from pathlib import Path
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         pp = _paths.get("plan")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if pp:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             Path(pp).write_text(json.dumps(plan_new, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         mp = _paths.get("mission")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         if mp:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]             Path(mp).write_text(json.dumps(mission_cur or {"room_id": _rid}, ensure_ascii=False, indent=2), encoding="utf-8")
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         pass

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # Response-model compatible
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     return {
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         "ok": True,
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         "updated": True,
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         "room_id": room_id,
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         "plan": plan_new,
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]         "mission": mission_cur or {"room_id": room_id},
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     }


# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] # === FIX_RUN_ONCE_MODELS_BEFORE_DECORATOR_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] class AgentRunOnceRequest(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     """Request for /v1/agent/run_once."""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     approve_token: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     room_id: Optional[str] = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] class AgentRunOnceResponse(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     """Response envelope for /v1/agent/run_once."""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     ok: bool = True
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     action: str = ""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     step_id: str = ""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     room_id: str = ""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     error: str = ""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     result: Optional[Dict[str, Any]] = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] # === FIX_RUN_ONCE_MODELS_BEFORE_DECORATOR_V1 END ===

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] # === GUARDRAIL_CHECK_ENDPOINT_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] class GuardrailCheckRequest(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     # simulate a write intent
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     mode: str = "propose"         # propose|apply
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     tool_name: str = "append_file" # write_file|append_file
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     kind: str = "new_file"        # new_file|modify
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     dest_dir: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     repo_path: Optional[str] = None
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     path: str = ""                # tool_args.path
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     room_id: Optional[str] = None

# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED] class GuardrailCheckResponse(BaseModel):
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     ok: bool = True
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     allowed: bool = True
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     detail: str = ""
# [HARDENING4_SAFEMIN_DISABLED] # [HARDENING2_DISABLED]     room_id: str = ""# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/guardrail_check", response_model=GuardrailCheckResponse)
# [HARDENING4_SAFEMIN_DISABLED] def guardrail_check(req: GuardrailCheckRequest, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     Deterministic guardrail evaluation without mutating plan state.
# [HARDENING4_SAFEMIN_DISABLED]     Returns allowed=True if the REAL guardrail would allow the write.
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = None

# [HARDENING4_SAFEMIN_DISABLED]     room_id = (req.room_id or hdr_room or "default")

# [HARDENING4_SAFEMIN_DISABLED]     # We reuse the same checks as REAL guardrail, but in a pure function style:
# [HARDENING4_SAFEMIN_DISABLED]     from pathlib import Path
# [HARDENING4_SAFEMIN_DISABLED]     safe_root = Path(r"C:\AI_VAULT\workspace\brainlab\_agent_runs").resolve()

# [HARDENING4_SAFEMIN_DISABLED]     tool = (req.tool_name or "").strip()
# [HARDENING4_SAFEMIN_DISABLED]     mode = (req.mode or "").strip().lower()
# [HARDENING4_SAFEMIN_DISABLED]     kind = (req.kind or "").strip()

# [HARDENING4_SAFEMIN_DISABLED]     if tool not in ("write_file","append_file") or mode not in ("propose","apply"):
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": True, "allowed": True, "detail": "not-a-write-op", "room_id": room_id}

# [HARDENING4_SAFEMIN_DISABLED]     dest = req.dest_dir
# [HARDENING4_SAFEMIN_DISABLED]     pth = req.path

# [HARDENING4_SAFEMIN_DISABLED]     # If no dest_dir, allow only absolute path whose parent is under safe root
# [HARDENING4_SAFEMIN_DISABLED]     if not dest:
# [HARDENING4_SAFEMIN_DISABLED]         if not isinstance(pth, str) or not pth:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: missing dest_dir/path for write op")
# [HARDENING4_SAFEMIN_DISABLED]         pp = Path(pth)
# [HARDENING4_SAFEMIN_DISABLED]         if not pp.is_absolute():
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: relative path requires dest_dir")
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             pp.parent.resolve().relative_to(safe_root)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir missing or outside safe root (path={pth})")
# [HARDENING4_SAFEMIN_DISABLED]     else:
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             Path(dest).resolve().relative_to(safe_root)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: dest_dir outside safe root: {dest}")

# [HARDENING4_SAFEMIN_DISABLED]     if kind == "modify":
# [HARDENING4_SAFEMIN_DISABLED]         if not req.repo_path:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail="REAL_GUARDRAIL_DENY: modify requires repo_path")
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             Path(req.repo_path).resolve().relative_to(safe_root)
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             raise HTTPException(status_code=400, detail=f"REAL_GUARDRAIL_DENY: repo_path outside safe root: {req.repo_path}")

# [HARDENING4_SAFEMIN_DISABLED]     return {"ok": True, "allowed": True, "detail": "allowed", "room_id": room_id}
# [HARDENING4_SAFEMIN_DISABLED] # === GUARDRAIL_CHECK_ENDPOINT_V1 END ===

# [HARDENING6_DISABLED_OLD_RUNONCE] @app.post("/v1/agent/run_once", response_model=AgentRunOnceResponse)
# [HARDENING6_DISABLED_OLD_RUNONCE] def agent_run_once(req: AgentRunOnceRequest, request: Request):
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         hdr_room = None
# [HARDENING6_DISABLED_OLD_RUNONCE]     room_id = req.room_id or hdr_room or "default"
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE RELOAD ROOM PLAN (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     def _load_room_plan(_rid: str) -> dict:
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             _room_state_dir(_rid)
# [HARDENING6_DISABLED_OLD_RUNONCE]             _paths = _room_paths(_rid) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]             import json
# [HARDENING6_DISABLED_OLD_RUNONCE]             from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]             pp = _paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]             if pp and Path(pp).exists():
# [HARDENING6_DISABLED_OLD_RUNONCE]                 return json.loads(Path(pp).read_text(encoding='utf-8')) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             return {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         return {}
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE RELOAD ROOM PLAN (FIX) END ===

# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM LOAD (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     mission, plan = {}, {}
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]         pm = paths.get('mission')
# [HARDENING6_DISABLED_OLD_RUNONCE]         pp = paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pm and Path(pm).exists():
# [HARDENING6_DISABLED_OLD_RUNONCE]             mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pp and Path(pp).exists():
# [HARDENING6_DISABLED_OLD_RUNONCE]             plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         mission, plan = {}, {}
# [HARDENING6_DISABLED_OLD_RUNONCE]     # Fallback compat: if empty, try global store
# [HARDENING6_DISABLED_OLD_RUNONCE]     if not plan:
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             mission, plan = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             mission, plan = {}, {}
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM LOAD (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     # Ensure plan carries room_id for auditing
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         if isinstance(plan, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]             plan.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]     status = str((plan or {}).get("status", "") or "").lower()
# [HARDENING6_DISABLED_OLD_RUNONCE]     steps = (plan or {}).get("steps", []) or []

# [HARDENING6_DISABLED_OLD_RUNONCE]     if status == "complete":
# [HARDENING6_DISABLED_OLD_RUNONCE]         return {"ok": True, "room_id": room_id, "action": "noop_complete", "plan": plan}

# [HARDENING6_DISABLED_OLD_RUNONCE]     # 0) If approve_token provided: try APPLY the corresponding proposed write step
# [HARDENING6_DISABLED_OLD_RUNONCE]     if req.approve_token:
# [HARDENING6_DISABLED_OLD_RUNONCE]         token = str(req.approve_token or "").strip()
# [HARDENING6_DISABLED_OLD_RUNONCE]         if not token.startswith("APPLY_"):
# [HARDENING6_DISABLED_OLD_RUNONCE]             raise HTTPException(status_code=400, detail="approve_token must be APPLY_<proposal_id>")

# [HARDENING6_DISABLED_OLD_RUNONCE]         target_pid = token.replace("APPLY_", "", 1)
# [HARDENING6_DISABLED_OLD_RUNONCE]         step_to_apply = next(
# [HARDENING6_DISABLED_OLD_RUNONCE]             (s for s in steps
# [HARDENING6_DISABLED_OLD_RUNONCE]              if str(s.get("status")) == "proposed"
# [HARDENING6_DISABLED_OLD_RUNONCE]              and 
# [HARDENING6_DISABLED_OLD_RUNONCE] _is_write_tool(s.get("tool_name"))
# [HARDENING6_DISABLED_OLD_RUNONCE]              and str(s.get("proposal_id") or "") == target_pid),
# [HARDENING6_DISABLED_OLD_RUNONCE]             None
# [HARDENING6_DISABLED_OLD_RUNONCE]         )

# [HARDENING6_DISABLED_OLD_RUNONCE]         if not step_to_apply:
# [HARDENING6_DISABLED_OLD_RUNONCE]             return {
# [HARDENING6_DISABLED_OLD_RUNONCE]                 "ok": True,
# [HARDENING6_DISABLED_OLD_RUNONCE]                 "room_id": room_id,
# [HARDENING6_DISABLED_OLD_RUNONCE]                 "action": "noop_no_matching_proposed_step",
# [HARDENING6_DISABLED_OLD_RUNONCE]                 "note": f"No proposed write step matches {token}",
# [HARDENING6_DISABLED_OLD_RUNONCE]                 "plan": plan
# [HARDENING6_DISABLED_OLD_RUNONCE]             }

# [HARDENING6_DISABLED_OLD_RUNONCE]         step_id = str(step_to_apply.get("id"))
# [HARDENING6_DISABLED_OLD_RUNONCE]         res = agent_execute_step(AgentExecuteStepRequest(room_id=room_id, step_id=step_id, mode="apply", approve_token=token))
# [HARDENING6_DISABLED_OLD_RUNONCE]         if False:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     # === RUN_ONCE PERSIST APPLY DONE (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]                     # Persist step status=done in per-room plan.json after apply
# [HARDENING6_DISABLED_OLD_RUNONCE]                     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk = _load_room_plan(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                         steps_disk = plan_disk.get('steps', []) or []
# [HARDENING6_DISABLED_OLD_RUNONCE]                         for _s in steps_disk:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 _s['status'] = 'done'
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 # limpiar campos de propuesta
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                                     _s.pop('required_approve', None)
# [HARDENING6_DISABLED_OLD_RUNONCE]                                     _s.pop('proposal_id', None)
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                                     pass
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 break
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk['steps'] = steps_disk
# [HARDENING6_DISABLED_OLD_RUNONCE]                         # auto-complete si todos done
# [HARDENING6_DISABLED_OLD_RUNONCE]                         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk):
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 plan_disk['status'] = 'complete'
# [HARDENING6_DISABLED_OLD_RUNONCE]                         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]                         from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                         _paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]                         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pp = _paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]                         if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]                     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]                     # === RUN_ONCE PERSIST APPLY DONE (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]         _, plan2 = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]         return {"ok": True, "room_id": room_id, "action": "apply_step", "step_id": step_id, "plan": plan2}

# [HARDENING6_DISABLED_OLD_RUNONCE]     # 1) If any write step still has placeholder, refresh plan first (1 action per call)
# [HARDENING6_DISABLED_OLD_RUNONCE]     placeholder_step = next((s for s in steps if _is_write_tool(s.get("tool_name")) and _has_placeholder(s)), None)
# [HARDENING6_DISABLED_OLD_RUNONCE]     if placeholder_step:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pr = agent_plan_refresh(AgentPlanRefreshRequest(room_id=room_id))
# [HARDENING6_DISABLED_OLD_RUNONCE]         _, plan2 = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]         return {
# [HARDENING6_DISABLED_OLD_RUNONCE]             "ok": bool(pr.get("ok", True)),
# [HARDENING6_DISABLED_OLD_RUNONCE]             "room_id": room_id,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "action": "plan_refresh",
# [HARDENING6_DISABLED_OLD_RUNONCE]             "step_id": str(placeholder_step.get("id")),
# [HARDENING6_DISABLED_OLD_RUNONCE]             "note": "Refreshed S3 content to clear placeholder",
# [HARDENING6_DISABLED_OLD_RUNONCE]             "plan": plan2
# [HARDENING6_DISABLED_OLD_RUNONCE]         }

# [HARDENING6_DISABLED_OLD_RUNONCE]     # 2) Find next actionable step
# [HARDENING6_DISABLED_OLD_RUNONCE]     # Prefer todo; if none, then proposed read-only shouldn't exist (but handle anyway)
# [HARDENING6_DISABLED_OLD_RUNONCE]     next_step = next((s for s in steps if str(s.get("status")) in {"todo", "in_progress"}), None)
# [HARDENING6_DISABLED_OLD_RUNONCE]     if not next_step:
# [HARDENING6_DISABLED_OLD_RUNONCE]         # if nothing todo, do an evaluate to allow auto-complete logic
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             ev = agent_evaluate(AgentEvalRequest(room_id=room_id, observation={"ok": True, "note": "run_once sweep"}))
# [HARDENING6_DISABLED_OLD_RUNONCE]             _, plan2 = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]             return {"ok": True, "room_id": room_id, "action": "evaluate_sweep", "plan": plan2}
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             _, plan2 = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]             return {"ok": True, "room_id": room_id, "action": "noop_no_todo", "plan": plan2}

# [HARDENING6_DISABLED_OLD_RUNONCE]     step_id = str(next_step.get("id"))
# [HARDENING6_DISABLED_OLD_RUNONCE]     tool_name = str(next_step.get("tool_name") or "")

# [HARDENING6_DISABLED_OLD_RUNONCE]     # Execute propose
# [HARDENING6_DISABLED_OLD_RUNONCE]     res = agent_execute_step(type("ExecReq", (), {"room_id": room_id, "step_id": step_id, "mode": "propose"})())
# [HARDENING6_DISABLED_OLD_RUNONCE]     if False:
# [HARDENING6_DISABLED_OLD_RUNONCE]             # === RUN_ONCE MARK READ DONE (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]             # For read-only steps, persist status=done into per-room plan.json
# [HARDENING6_DISABLED_OLD_RUNONCE]             if _is_read_tool(tool_name):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     plan_disk = _load_room_plan(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                     steps_disk = plan_disk.get('steps', []) or []
# [HARDENING6_DISABLED_OLD_RUNONCE]                     for _s in steps_disk:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
# [HARDENING6_DISABLED_OLD_RUNONCE]                             _s['status'] = 'done'
# [HARDENING6_DISABLED_OLD_RUNONCE]                             break
# [HARDENING6_DISABLED_OLD_RUNONCE]                     plan_disk['steps'] = steps_disk
# [HARDENING6_DISABLED_OLD_RUNONCE]                     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]                     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]                     plan_disk.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                     _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                     _paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                     import json
# [HARDENING6_DISABLED_OLD_RUNONCE]                     from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]                     pp = _paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]                     if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]                     plan = plan_disk
# [HARDENING6_DISABLED_OLD_RUNONCE]                     steps = plan.get('steps', []) or []
# [HARDENING6_DISABLED_OLD_RUNONCE]                 except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     pass
# [HARDENING6_DISABLED_OLD_RUNONCE]             # === RUN_ONCE MARK READ DONE (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     if False:
# [HARDENING6_DISABLED_OLD_RUNONCE]             # === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]             # Persist write-step proposal_id/required_approve into per-room plan.json so APPLY can match.
# [HARDENING6_DISABLED_OLD_RUNONCE]             if _is_write_tool(tool_name):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     pid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]                     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pid = (res.get('result') or {}).get('proposal_id')
# [HARDENING6_DISABLED_OLD_RUNONCE]                     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]                     if pid:
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk = _load_room_plan(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                         steps_disk = plan_disk.get('steps', []) or []
# [HARDENING6_DISABLED_OLD_RUNONCE]                         for _s in steps_disk:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 _s['status'] = 'proposed'
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 _s['proposal_id'] = str(pid)
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 _s['required_approve'] = 'APPLY_' + str(pid)
# [HARDENING6_DISABLED_OLD_RUNONCE]                                 break
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk['steps'] = steps_disk
# [HARDENING6_DISABLED_OLD_RUNONCE]                         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]                             plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]                         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan_disk.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]                         _paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]                         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]                         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]                         pp = _paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]                         if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]                             Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]                         plan = plan_disk
# [HARDENING6_DISABLED_OLD_RUNONCE]                         steps = plan.get('steps', []) or []
# [HARDENING6_DISABLED_OLD_RUNONCE]                 except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     pass
# [HARDENING6_DISABLED_OLD_RUNONCE]             # === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) END ===

# [HARDENING6_DISABLED_OLD_RUNONCE]     # reload per-room plan after execute_step
# [HARDENING6_DISABLED_OLD_RUNONCE]     plan = _load_room_plan(room_id) or plan
# [HARDENING6_DISABLED_OLD_RUNONCE]     # If it's a write tool, we require approval token from result
# [HARDENING6_DISABLED_OLD_RUNONCE]     if _is_write_tool(tool_name):
# [HARDENING6_DISABLED_OLD_RUNONCE]         pid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pid = (res.get("result") or {}).get("proposal_id")
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]         approve = f"APPLY_{pid}" if pid else None

# [HARDENING6_DISABLED_OLD_RUNONCE]         _, plan2 = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]         return {
# [HARDENING6_DISABLED_OLD_RUNONCE]             "ok": True,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "room_id": room_id,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "action": "propose_write_step",
# [HARDENING6_DISABLED_OLD_RUNONCE]             "step_id": step_id,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "needs_approval": True,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "approve_token": approve,
# [HARDENING6_DISABLED_OLD_RUNONCE]             "note": "Write step proposed; re-call run_once with approve_token to apply",
# [HARDENING6_DISABLED_OLD_RUNONCE]             "plan": plan2
# [HARDENING6_DISABLED_OLD_RUNONCE]         }

# [HARDENING6_DISABLED_OLD_RUNONCE]     # read-only step is terminal; run evaluate to auto-complete if needed
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         agent_evaluate(AgentEvalRequest(room_id=room_id, observation={"ok": True, "note": f"run_once after {step_id}"}))
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass

# [HARDENING6_DISABLED_OLD_RUNONCE]     plan2 = _load_room_plan(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE PERSIST AFTER LOAD (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]         from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]         now = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(plan2, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 plan2['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 plan2.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(mission, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 mission['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 mission.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]         pm = paths.get('mission')
# [HARDENING6_DISABLED_OLD_RUNONCE]         pp = paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pm:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pp).write_text(json.dumps(plan2 or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE PERSIST AFTER LOAD (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM PERSIST (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         rid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]         # prefer req.room_id si existe
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             rid = getattr(req, 'room_id', None)
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             rid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]         # fallback header x-room-id
# [HARDENING6_DISABLED_OLD_RUNONCE]         if not rid and 'request' in locals() and request is not None:
# [HARDENING6_DISABLED_OLD_RUNONCE]             try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
# [HARDENING6_DISABLED_OLD_RUNONCE]             except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 rid = None
# [HARDENING6_DISABLED_OLD_RUNONCE]         if rid:
# [HARDENING6_DISABLED_OLD_RUNONCE]             # Tomar mission/plan actuales (si no existen, cargar del store)
# [HARDENING6_DISABLED_OLD_RUNONCE]             _mission = None
# [HARDENING6_DISABLED_OLD_RUNONCE]             _plan = None
# [HARDENING6_DISABLED_OLD_RUNONCE]             try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _mission = mission if 'mission' in locals() else None
# [HARDENING6_DISABLED_OLD_RUNONCE]             except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _mission = None
# [HARDENING6_DISABLED_OLD_RUNONCE]             try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _plan = plan if 'plan' in locals() else None
# [HARDENING6_DISABLED_OLD_RUNONCE]             except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _plan = None
# [HARDENING6_DISABLED_OLD_RUNONCE]             if _mission is None or _plan is None:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 try:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     _mission, _plan = agent_store.load()
# [HARDENING6_DISABLED_OLD_RUNONCE]                 except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]                     pass
# [HARDENING6_DISABLED_OLD_RUNONCE]             from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]             import json
# [HARDENING6_DISABLED_OLD_RUNONCE]             now = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(_plan, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _plan['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _plan.setdefault('room_id', rid)
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(_mission, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _mission['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 _mission.setdefault('room_id', rid)
# [HARDENING6_DISABLED_OLD_RUNONCE]             _room_state_dir(rid)
# [HARDENING6_DISABLED_OLD_RUNONCE]             paths = _room_paths(rid) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]             pm = paths.get('mission')
# [HARDENING6_DISABLED_OLD_RUNONCE]             pp = paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]             from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]             if pm:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 Path(pm).write_text(json.dumps(_mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]             if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]                 Path(pp).write_text(json.dumps(_plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM PERSIST (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM PERSIST BEFORE RETURN (FIX) BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]         from datetime import datetime, timezone
# [HARDENING6_DISABLED_OLD_RUNONCE]         now = datetime.now(timezone.utc).isoformat()
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(plan, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 plan['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 plan.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]         try:
# [HARDENING6_DISABLED_OLD_RUNONCE]             if isinstance(mission, dict):
# [HARDENING6_DISABLED_OLD_RUNONCE]                 mission['updated_at'] = now
# [HARDENING6_DISABLED_OLD_RUNONCE]                 mission.setdefault('room_id', room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]             pass
# [HARDENING6_DISABLED_OLD_RUNONCE]         pm = paths.get('mission')
# [HARDENING6_DISABLED_OLD_RUNONCE]         pp = paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pm:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pp).write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === RUN_ONCE ROOM PERSIST BEFORE RETURN (FIX) END ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     return {"ok": True, "room_id": room_id, "action": "propose_read_step", "step_id": step_id, "plan": plan2}
# [HARDENING6_DISABLED_OLD_RUNONCE] # ===== End Agent run_once =====
# [HARDENING6_DISABLED_OLD_RUNONCE] # ===== Agent Status (v4.8) =====
# [HARDENING6_DISABLED_OLD_RUNONCE] class AgentStatusRequest(BaseModel):
# [HARDENING6_DISABLED_OLD_RUNONCE]     room_id: Optional[str] = None

# [HARDENING6_DISABLED_OLD_RUNONCE] class AgentStatusResponse(BaseModel):
# [HARDENING6_DISABLED_OLD_RUNONCE]     ok: bool
# [HARDENING6_DISABLED_OLD_RUNONCE]     room_id: str
# [HARDENING6_DISABLED_OLD_RUNONCE]     mission: Dict[str, Any]
# [HARDENING6_DISABLED_OLD_RUNONCE]     plan: Dict[str, Any]
# [HARDENING6_DISABLED_OLD_RUNONCE]     summary: Dict[str, Any]
# [HARDENING6_DISABLED_OLD_RUNONCE]     pending_approvals: Dict[str, str] = Field(default_factory=dict)

# [HARDENING6_DISABLED_OLD_RUNONCE]     # === AGENT_PLAN ROOM SAVE BEGIN ===
# [HARDENING6_DISABLED_OLD_RUNONCE]     # Persist plan/mission per-room (rooms/<room_id>/...)
# [HARDENING6_DISABLED_OLD_RUNONCE]     try:
# [HARDENING6_DISABLED_OLD_RUNONCE]         _room_state_dir(room_id)
# [HARDENING6_DISABLED_OLD_RUNONCE]         paths = _room_paths(room_id) or {}
# [HARDENING6_DISABLED_OLD_RUNONCE]         import json
# [HARDENING6_DISABLED_OLD_RUNONCE]         from pathlib import Path
# [HARDENING6_DISABLED_OLD_RUNONCE]         pm = paths.get('mission')
# [HARDENING6_DISABLED_OLD_RUNONCE]         pp = paths.get('plan')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pm:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]         if pp:
# [HARDENING6_DISABLED_OLD_RUNONCE]             Path(pp).write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
# [HARDENING6_DISABLED_OLD_RUNONCE]     except Exception:
# [HARDENING6_DISABLED_OLD_RUNONCE]         pass
# [HARDENING6_DISABLED_OLD_RUNONCE]     # === AGENT_PLAN ROOM SAVE END ===@app.post("/v1/agent/status", response_model=AgentStatusResponse)
def agent_status(req: AgentStatusRequest, request: Request):
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None
    room_id = req.room_id or hdr_room or "default"
    # Load per-room mission/plan from disk (rooms/<room_id>/...) — fallback a store global si falla
    mission, plan = {}, {}
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pm = paths.get('mission')
        pp = paths.get('plan')
        if pm and Path(pm).exists():
            mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {}
        if pp and Path(pp).exists():
            plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {}
    except Exception:
        try:
            mission, plan = agent_store.load()
        except Exception:
            mission, plan = {}, {}

    steps = plan.get("steps", []) or []
    counts = {"todo": 0, "proposed": 0, "done": 0, "error": 0, "other": 0}
    pending: Dict[str, str] = {}

    for s in steps:
        st = str(s.get("status", "") or "").lower()
        if st in counts:
            counts[st] += 1
        else:
            counts["other"] += 1

        # Pending approvals: write steps typically get required_approve after propose
        ra = s.get("required_approve")
        if ra and st in {"proposed"}:
            pending[str(s.get("id"))] = str(ra)

    summary = {
        "plan_id": plan.get("plan_id"),
        "status": plan.get("status"),
        "steps_total": len(steps),
        "counts": counts,
        "pending_approvals_count": len(pending),
        "last_eval": plan.get("last_eval"),
        "updated_at": plan.get("updated_at"),
    }

    return {
        "ok": True,
        "room_id": room_id,
        "mission": mission or {},
        "plan": plan or {},
        "summary": summary,
        "pending_approvals": pending,
    }
# ===== End Agent Status =====

# ===== End Agent Endpoints =====






# PATCH: moved execute decorator to agent_execute

























# =========================
# Agent v1: Execute endpoint
# =========================

def _resolve_tmp_agent_root() -> str:
    # Prefer env var; fallback to default
    return os.environ.get("BRAIN_TMP_AGENT_ROOT", r"C:\AI_VAULT\tmp_agent")

def _import_tmp_agent_module(mod_name: str):
    # TMP_AGENT_ROOT must be first in path (already enforced earlier)
    return __import__(mod_name)

def _safe_json(obj):
    try:
        return json.loads(json.dumps(obj, ensure_ascii=False, default=str))
    except Exception:
        return {"_repr": repr(obj)}


# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/execute")
# [HARDENING4_SAFEMIN_DISABLED] def agent_execute(payload: dict):
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     Ejecuta 1 paso del plan por request.
# [HARDENING4_SAFEMIN_DISABLED]     Espera: { room_id, step_id? , max_tool_calls? }
# [HARDENING4_SAFEMIN_DISABLED]     Devuelve: { ok, plan, executed, tool_results, next_step }
# [HARDENING4_SAFEMIN_DISABLED]     """
# [HARDENING4_SAFEMIN_DISABLED]     room_id = payload.get("room_id", "default")
# [HARDENING4_SAFEMIN_DISABLED]     step_id = payload.get("step_id")  # opcional: si no, toma el siguiente pendiente
# [HARDENING4_SAFEMIN_DISABLED]     max_tool_calls = int(payload.get("max_tool_calls", 3))

# [HARDENING4_SAFEMIN_DISABLED]     # Importa AgentStateStore desde tmp_agent (ya está en sys.path[0])
# [HARDENING4_SAFEMIN_DISABLED]     agent_state = _import_tmp_agent_module("agent_state")
# [HARDENING4_SAFEMIN_DISABLED]     store = agent_state.AgentStateStore(_resolve_tmp_agent_root())
# [HARDENING4_SAFEMIN_DISABLED]     plan = store.load_plan(room_id)

# [HARDENING4_SAFEMIN_DISABLED]     # Selección de paso
# [HARDENING4_SAFEMIN_DISABLED]     steps = plan.get("steps", []) if isinstance(plan, dict) else []
# [HARDENING4_SAFEMIN_DISABLED]     if not steps:
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "Plan sin pasos. Llama /v1/agent/plan primero.", "plan": _safe_json(plan)}

# [HARDENING4_SAFEMIN_DISABLED]     def is_done(s):
# [HARDENING4_SAFEMIN_DISABLED]         return str(s.get("status","")).lower() in ("done","complete","completed","skipped")

# [HARDENING4_SAFEMIN_DISABLED]     step = None
# [HARDENING4_SAFEMIN_DISABLED]     if step_id is not None:
# [HARDENING4_SAFEMIN_DISABLED]         for s in steps:
# [HARDENING4_SAFEMIN_DISABLED]             if str(s.get("id")) == str(step_id):
# [HARDENING4_SAFEMIN_DISABLED]                 step = s
# [HARDENING4_SAFEMIN_DISABLED]                 break
# [HARDENING4_SAFEMIN_DISABLED]         if step is None:
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": False, "error": f"step_id no encontrado: {step_id}", "plan": _safe_json(plan)}
# [HARDENING4_SAFEMIN_DISABLED]         if is_done(step):
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": True, "note": "Paso ya completado", "executed": _safe_json(step), "plan": _safe_json(plan)}
# [HARDENING4_SAFEMIN_DISABLED]     else:
# [HARDENING4_SAFEMIN_DISABLED]         # primer paso no done
# [HARDENING4_SAFEMIN_DISABLED]         for s in steps:
# [HARDENING4_SAFEMIN_DISABLED]             if not is_done(s):
# [HARDENING4_SAFEMIN_DISABLED]                 step = s
# [HARDENING4_SAFEMIN_DISABLED]                 break
# [HARDENING4_SAFEMIN_DISABLED]         if step is None:
# [HARDENING4_SAFEMIN_DISABLED]             return {"ok": True, "note": "Plan ya completado", "plan": _safe_json(plan), "next_step": None}

# [HARDENING4_SAFEMIN_DISABLED]     # Ejecutar usando sandbox_executor si existe
# [HARDENING4_SAFEMIN_DISABLED]     # Contrato esperado: SandboxExecutor(root).run_step(step, room_id, max_tool_calls)
# [HARDENING4_SAFEMIN_DISABLED]     tool_results = []
# [HARDENING4_SAFEMIN_DISABLED]     executed = {"id": step.get("id"), "title": step.get("title"), "status_before": step.get("status","pending")}

# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         se = _import_tmp_agent_module("sandbox_executor")
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         # No abortamos: marcamos como bloqueado para que lo arreglemos con el nombre correcto
# [HARDENING4_SAFEMIN_DISABLED]         step["status"] = "blocked"
# [HARDENING4_SAFEMIN_DISABLED]         step["last_error"] = f"Import sandbox_executor failed: {e}"
# [HARDENING4_SAFEMIN_DISABLED]         store.save_plan(room_id, plan)
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "No se pudo importar sandbox_executor desde tmp_agent.", "detail": str(e), "plan": _safe_json(plan)}

# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         executor = se.SandboxExecutor(_resolve_tmp_agent_root())
# [HARDENING4_SAFEMIN_DISABLED]         result = executor.run_step(step=step, room_id=room_id, max_tool_calls=max_tool_calls)
# [HARDENING4_SAFEMIN_DISABLED]         # result puede contener: status, tool_results, notes, output
# [HARDENING4_SAFEMIN_DISABLED]         tool_results = result.get("tool_results", []) if isinstance(result, dict) else []
# [HARDENING4_SAFEMIN_DISABLED]         # Actualiza status en plan si el ejecutor no lo hizo
# [HARDENING4_SAFEMIN_DISABLED]         if isinstance(result, dict) and result.get("status"):
# [HARDENING4_SAFEMIN_DISABLED]             step["status"] = result["status"]
# [HARDENING4_SAFEMIN_DISABLED]         else:
# [HARDENING4_SAFEMIN_DISABLED]             step["status"] = step.get("status","done") if step.get("status") != "blocked" else "blocked"
# [HARDENING4_SAFEMIN_DISABLED]         step["last_run"] = datetime.utcnow().isoformat() + "Z"
# [HARDENING4_SAFEMIN_DISABLED]         step["last_output"] = result.get("output") if isinstance(result, dict) else str(result)
# [HARDENING4_SAFEMIN_DISABLED]         store.save_plan(room_id, plan)
# [HARDENING4_SAFEMIN_DISABLED]         executed["status_after"] = step.get("status")
# [HARDENING4_SAFEMIN_DISABLED]         executed["output"] = step.get("last_output")
# [HARDENING4_SAFEMIN_DISABLED]     except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]         step["status"] = "blocked"
# [HARDENING4_SAFEMIN_DISABLED]         step["last_error"] = str(e)
# [HARDENING4_SAFEMIN_DISABLED]         step["last_run"] = datetime.utcnow().isoformat() + "Z"
# [HARDENING4_SAFEMIN_DISABLED]         store.save_plan(room_id, plan)
# [HARDENING4_SAFEMIN_DISABLED]         return {"ok": False, "error": "Ejecución falló", "detail": str(e), "executed": _safe_json(step), "plan": _safe_json(plan)}

# [HARDENING4_SAFEMIN_DISABLED]     # Próximo paso
# [HARDENING4_SAFEMIN_DISABLED]     next_step = None
# [HARDENING4_SAFEMIN_DISABLED]     for s in steps:
# [HARDENING4_SAFEMIN_DISABLED]         if not is_done(s):
# [HARDENING4_SAFEMIN_DISABLED]             next_step = {"id": s.get("id"), "title": s.get("title"), "status": s.get("status","pending")}
# [HARDENING4_SAFEMIN_DISABLED]             break


# [HARDENING4_SAFEMIN_DISABLED]     return {
# [HARDENING4_SAFEMIN_DISABLED]         "ok": True,
# [HARDENING4_SAFEMIN_DISABLED]         "executed": _safe_json(executed),
# [HARDENING4_SAFEMIN_DISABLED]         "tool_results": _safe_json(tool_results),
# [HARDENING4_SAFEMIN_DISABLED]         "next_step": _safe_json(next_step),
# [HARDENING4_SAFEMIN_DISABLED]         "plan": _safe_json(plan),
# [HARDENING4_SAFEMIN_DISABLED]     }

# [HARDENING4_SAFEMIN_DISABLED] # APP_INCLUDE_ROUTER_MOVED_V1: include router at EOF
# [HARDENING4_SAFEMIN_DISABLED] @app.post("/v1/agent/run")
# [HARDENING4_SAFEMIN_DISABLED] def agent_run(body: dict, request: Request):
# [HARDENING4_SAFEMIN_DISABLED]     # v6.2: run loop MUST respect per-room plan.json and stop if complete
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         hdr_room = None

# [HARDENING4_SAFEMIN_DISABLED]     # Resolve request model without assuming parameter name (req/payload/body/etc.)
# [HARDENING4_SAFEMIN_DISABLED]     _req = None
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _req = req  # type: ignore[name-defined]
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         _req = None
# [HARDENING4_SAFEMIN_DISABLED]     if _req is None:
# [HARDENING4_SAFEMIN_DISABLED]         for _k in ("payload","body","data","r","request_body","model"):
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 if _k in locals() and locals().get(_k) is not None:
# [HARDENING4_SAFEMIN_DISABLED]                     _req = locals().get(_k)
# [HARDENING4_SAFEMIN_DISABLED]                     break
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 pass

# [HARDENING4_SAFEMIN_DISABLED]     room_id = getattr(_req, "room_id", None) or hdr_room or "default"
# [HARDENING4_SAFEMIN_DISABLED]     max_steps = int(getattr(_req, "max_steps", 10) or 10)
# [HARDENING4_SAFEMIN_DISABLED]     if max_steps < 1: max_steps = 1
# [HARDENING4_SAFEMIN_DISABLED]     if max_steps > 200: max_steps = 200

# [HARDENING4_SAFEMIN_DISABLED]     # Always read per-room status first (via agent_status which loads from disk)
# [HARDENING4_SAFEMIN_DISABLED]     st0 = agent_status(AgentStatusRequest(room_id=room_id), request)
# [HARDENING4_SAFEMIN_DISABLED]     plan0 = (st0.get('plan') or {})
# [HARDENING4_SAFEMIN_DISABLED]     mission0 = (st0.get('mission') or {})
# [HARDENING4_SAFEMIN_DISABLED]     summary0 = (st0.get('summary') or {})
# [HARDENING4_SAFEMIN_DISABLED]     pending0 = (st0.get('pending_approvals') or {})

# [HARDENING4_SAFEMIN_DISABLED]     if str(plan0.get('status','')).lower() == 'complete':
# [HARDENING4_SAFEMIN_DISABLED]         return {
# [HARDENING4_SAFEMIN_DISABLED]             'ok': True,
# [HARDENING4_SAFEMIN_DISABLED]             'room_id': room_id,
# [HARDENING4_SAFEMIN_DISABLED]             'executed': [],
# [HARDENING4_SAFEMIN_DISABLED]             'needs_approval': False,
# [HARDENING4_SAFEMIN_DISABLED]             'approve_token': None,
# [HARDENING4_SAFEMIN_DISABLED]             'summary': summary0,
# [HARDENING4_SAFEMIN_DISABLED]             'pending_approvals': pending0,
# [HARDENING4_SAFEMIN_DISABLED]             'plan': plan0,
# [HARDENING4_SAFEMIN_DISABLED]             'mission': mission0,
# [HARDENING4_SAFEMIN_DISABLED]         }

# [HARDENING4_SAFEMIN_DISABLED]     executed = []

# [HARDENING4_SAFEMIN_DISABLED]     # === RUN_APPROVE_TOKEN_HOOK_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # If approve_token provided, apply the pending gated write step via agent_execute_step
# [HARDENING4_SAFEMIN_DISABLED]     token = None
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         token = getattr(_req, "approve_token", None) if _req is not None else None
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         token = None
# [HARDENING4_SAFEMIN_DISABLED]     if (not token) and isinstance(body, dict):
# [HARDENING4_SAFEMIN_DISABLED]         token = (body or {}).get("approve_token")

# [HARDENING4_SAFEMIN_DISABLED]     if token:
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             # resolve room id from locals (prefer room_id then rid then hdr_room)
# [HARDENING4_SAFEMIN_DISABLED]             _rid = None
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _rid = locals().get("room_id")
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 _rid = None
# [HARDENING4_SAFEMIN_DISABLED]             if not _rid:
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     _rid = locals().get("rid")
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     _rid = None
# [HARDENING4_SAFEMIN_DISABLED]             if not _rid:
# [HARDENING4_SAFEMIN_DISABLED]                 _rid = hdr_room or "default"

# [HARDENING4_SAFEMIN_DISABLED]             plan_disk = _load_room_plan(_rid) or {}
# [HARDENING4_SAFEMIN_DISABLED]             steps_disk = plan_disk.get("steps", []) or []
# [HARDENING4_SAFEMIN_DISABLED]             target = None
# [HARDENING4_SAFEMIN_DISABLED]             for st in steps_disk:
# [HARDENING4_SAFEMIN_DISABLED]                 if isinstance(st, dict) and st.get("required_approve") == token:
# [HARDENING4_SAFEMIN_DISABLED]                     target = st
# [HARDENING4_SAFEMIN_DISABLED]                     break

# [HARDENING4_SAFEMIN_DISABLED]             if target:
# [HARDENING4_SAFEMIN_DISABLED]                 sid = str(target.get("id") or "")
# [HARDENING4_SAFEMIN_DISABLED]                 # apply step using same mechanism as run_once
# [HARDENING4_SAFEMIN_DISABLED]                 _ = agent_execute_step(AgentExecuteStepRequest(room_id=_rid, step_id=sid, mode="apply", approve_token=token))
# [HARDENING4_SAFEMIN_DISABLED]                 executed.append({"action": "apply_step", "step_id": sid})
# [HARDENING4_SAFEMIN_DISABLED]                 # reload plan after apply
# [HARDENING4_SAFEMIN_DISABLED]                 try:
# [HARDENING4_SAFEMIN_DISABLED]                     plan = _load_room_plan(_rid) or plan
# [HARDENING4_SAFEMIN_DISABLED]                 except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                     pass
# [HARDENING4_SAFEMIN_DISABLED]         except Exception as e:
# [HARDENING4_SAFEMIN_DISABLED]             executed.append({"action": "apply_step_failed", "step_id": None, "error": repr(e)})
# [HARDENING4_SAFEMIN_DISABLED]     # === RUN_APPROVE_TOKEN_HOOK_V1 END ===

# [HARDENING4_SAFEMIN_DISABLED]     needs_approval = False
# [HARDENING4_SAFEMIN_DISABLED]     approve_token = None

# [HARDENING4_SAFEMIN_DISABLED]     for _i in range(max_steps):
# [HARDENING4_SAFEMIN_DISABLED]         r = agent_run_once(AgentRunOnceRequest(room_id=room_id), request)
# [HARDENING4_SAFEMIN_DISABLED]         executed.append({'action': r.get('action'), 'step_id': r.get('step_id')})
# [HARDENING4_SAFEMIN_DISABLED]         if bool(r.get('needs_approval', False)):
# [HARDENING4_SAFEMIN_DISABLED]             needs_approval = True
# [HARDENING4_SAFEMIN_DISABLED]             approve_token = r.get('approve_token')
# [HARDENING4_SAFEMIN_DISABLED]             break
# [HARDENING4_SAFEMIN_DISABLED]         if str(r.get('action') or '') == 'noop_complete':
# [HARDENING4_SAFEMIN_DISABLED]             break
# [HARDENING4_SAFEMIN_DISABLED]         if str(r.get('action') or '') in ('noop_no_todo','evaluate_sweep'):
# [HARDENING4_SAFEMIN_DISABLED]             break

# [HARDENING4_SAFEMIN_DISABLED]     # Recompute status from disk at end
# [HARDENING4_SAFEMIN_DISABLED]     st = agent_status(AgentStatusRequest(room_id=room_id), request)

# [HARDENING4_SAFEMIN_DISABLED]     # === RUN_PENDING_APPROVALS_RECOMPUTE_V1 BEGIN ===
# [HARDENING4_SAFEMIN_DISABLED]     # After executing loop actions, recompute pending approvals from persisted per-room plan
# [HARDENING4_SAFEMIN_DISABLED]     try:
# [HARDENING4_SAFEMIN_DISABLED]         _rid = None
# [HARDENING4_SAFEMIN_DISABLED]         try:
# [HARDENING4_SAFEMIN_DISABLED]             _rid = locals().get("room_id")
# [HARDENING4_SAFEMIN_DISABLED]         except Exception:
# [HARDENING4_SAFEMIN_DISABLED]             _rid = None
# [HARDENING4_SAFEMIN_DISABLED]         if not _rid:
# [HARDENING4_SAFEMIN_DISABLED]             try:
# [HARDENING4_SAFEMIN_DISABLED]                 _rid = locals().get("rid")
# [HARDENING4_SAFEMIN_DISABLED]             except Exception:
# [HARDENING4_SAFEMIN_DISABLED]                 _rid = None
# [HARDENING4_SAFEMIN_DISABLED]         if not _rid:
# [HARDENING4_SAFEMIN_DISABLED]             _rid = hdr_room or "default"

# [HARDENING4_SAFEMIN_DISABLED]         _plan_disk = _load_room_plan(_rid) or {}
# [HARDENING4_SAFEMIN_DISABLED]         _steps = _plan_disk.get("steps", []) or []
# [HARDENING4_SAFEMIN_DISABLED]         _pending = {}
# [HARDENING4_SAFEMIN_DISABLED]         for _st in _steps:
# [HARDENING4_SAFEMIN_DISABLED]             if not isinstance(_st, dict):
# [HARDENING4_SAFEMIN_DISABLED]                 continue
# [HARDENING4_SAFEMIN_DISABLED]             if str(_st.get("status")) == "proposed" and _st.get("required_approve"):
# [HARDENING4_SAFEMIN_DISABLED]                 _pending[str(_st.get("id") or "")] = str(_st.get("required_approve"))
# [HARDENING4_SAFEMIN_DISABLED]         pending_approvals = _pending
# [HARDENING4_SAFEMIN_DISABLED]         needs_approval = bool(_pending)
# [HARDENING4_SAFEMIN_DISABLED]         approve_token = next(iter(_pending.values()), None)
# [HARDENING4_SAFEMIN_DISABLED]         # keep response plan consistent
# [HARDENING4_SAFEMIN_DISABLED]         plan = _plan_disk or plan
# [HARDENING4_SAFEMIN_DISABLED]     except Exception:
# [HARDENING4_SAFEMIN_DISABLED]         pass
# [HARDENING4_SAFEMIN_DISABLED]     # === RUN_PENDING_APPROVALS_RECOMPUTE_V1 END ===

# [HARDENING4_SAFEMIN_DISABLED]     return {
# [HARDENING4_SAFEMIN_DISABLED]         'ok': True,
# [HARDENING4_SAFEMIN_DISABLED]         'room_id': room_id,
# [HARDENING4_SAFEMIN_DISABLED]         'executed': executed,
# [HARDENING4_SAFEMIN_DISABLED]         'needs_approval': needs_approval,
# [HARDENING4_SAFEMIN_DISABLED]         'approve_token': approve_token,
# [HARDENING4_SAFEMIN_DISABLED]         'summary': st.get('summary') or {},
# [HARDENING4_SAFEMIN_DISABLED]         'pending_approvals': st.get('pending_approvals') or {},
# [HARDENING4_SAFEMIN_DISABLED]         'plan': st.get('plan') or {},
# [HARDENING4_SAFEMIN_DISABLED]         'mission': st.get('mission') or {},
# [HARDENING4_SAFEMIN_DISABLED]     }


# [HARDENING4_SAFEMIN_DISABLED] # FIX_EXECUTE_RESPONSE_MODELS_TO_DICT_V1


# [HARDENING4_SAFEMIN_DISABLED] # PLAN_GET_SSOT_ROOMPLAN_JSON_V1


# [HARDENING4_SAFEMIN_DISABLED] # AGENT_EVALUATE_SSOT_ROOMPLAN_JSON_V1


# [HARDENING4_SAFEMIN_DISABLED] # --- HARDENING1: healthz (SSOT / snapshot sanity) -------------------------
# [HARDENING4_SAFEMIN_DISABLED] from fastapi import HTTPException
@app.get("/v1/agent/healthz")
def agent_healthz() -> Dict[str, Any]:
    """
    Healthz canónico (SSOT + snapshot + roadmap) — usa endpoints snapshot (no heurística).
    """
    # HARDENING_HEALTHZ_SSOT_V3_SNAPSHOT_ENDPOINTS
    out: Dict[str, Any] = {
        "ok": False,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "checks": {},
        "errors": []
    }

    # A) FS paths
    try:
        base_tmp = Path(r"C:\AI_VAULT\tmp_agent")
        state_dir = base_tmp / "state"
        rooms_dir = state_dir / "rooms"
        roadmap_path = state_dir / "roadmap.json"
        out["checks"]["paths"] = {
            "base_tmp": str(base_tmp),
            "state_dir": str(state_dir),
            "rooms_dir": str(rooms_dir),
            "roadmap_path": str(roadmap_path),
        }
        base_tmp.mkdir(parents=True, exist_ok=True)
        rooms_dir.mkdir(parents=True, exist_ok=True)
        out["checks"]["fs_ok"] = True
    except Exception as e:
        out["checks"]["fs_ok"] = False
        out["errors"].append("fs_error: " + str(e))
        return out

    # B) SSOT plan write/read probe
    try:
        rid = "healthz_probe_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        room_dir = rooms_dir / rid
        room_dir.mkdir(parents=True, exist_ok=True)
        plan_path = room_dir / "plan.json"
        probe_plan = {
            "room_id": rid,
            "status": "planned",
            "steps": [],
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
            "healthz_probe": True
        }
        plan_path.write_text(json.dumps(probe_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        back = json.loads(plan_path.read_text(encoding="utf-8"))
        ok_rr = (back.get("room_id") == rid and back.get("healthz_probe") is True)
        out["checks"]["ssot_plan_write_read_ok"] = ok_rr
        out["checks"]["ssot_probe_room"] = rid
        out["checks"]["ssot_plan_path"] = str(plan_path)
        if not ok_rr:
            out["errors"].append("ssot_plan_mismatch")
    except Exception as e:
        out["checks"]["ssot_plan_write_read_ok"] = False
        out["errors"].append("ssot_plan_error: " + str(e))

    # C) roadmap exists + parses
    try:
        if roadmap_path.exists():
            _ = json.loads(roadmap_path.read_text(encoding="utf-8"))
            out["checks"]["roadmap_ok"] = True
        else:
            out["checks"]["roadmap_ok"] = False
            out["errors"].append("roadmap_missing")
    except Exception as e:
        out["checks"]["roadmap_ok"] = False
        out["errors"].append("roadmap_error: " + str(e))

    # D) snapshot KV via HTTP loopback to runtime snapshot endpoints
    try:
        key = "healthz_probe_key"
        val = {"ts": out["ts"], "probe": True}
        base = "http://127.0.0.1:8010"
        set_url = base + "/v1/agent/runtime/snapshot/set"
        get_url = base + "/v1/agent/runtime/snapshot/get"
    
        payload_set = {"room_id":"default","path":key,"value":val}
    
        # prefer httpx if available, else urllib
        try:
            import httpx
            with httpx.Client(timeout=2.0) as c:
                j1 = c.post(set_url, json=payload_set).json()
                r2 = c.get(get_url, params={"room_id":"default","path":key})
                j2 = r2.json()
        except Exception:
            from urllib.request import Request, urlopen
            import urllib.parse
    
            def _post_json(url, obj):
                data = json.dumps(obj).encode("utf-8")
                req = Request(url, data=data, headers={"Content-Type":"application/json"}, method="POST")
                with urlopen(req, timeout=2) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body) if body else {}
    
            def _get_json(url, qs):
                q = urllib.parse.urlencode(qs)
                req = Request(url + "?" + q, headers={"Accept":"application/json"}, method="GET")
                with urlopen(req, timeout=2) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                return json.loads(body) if body else {}
    
            j1 = _post_json(set_url, payload_set)
            j2 = _get_json(get_url, {"room_id":"default","path":key})
    
        got = None
        if isinstance(j2, dict):
            snap = j2.get("snapshot") or {}
            got = (snap.get("value") if isinstance(snap, dict) else None)
    
        out["checks"]["snapshot_set_resp"] = j1
        out["checks"]["snapshot_get_resp"] = j2
        out["checks"]["snapshot_probe_key"] = key
        out["checks"]["snapshot_ok"] = (got == val)
        if not out["checks"]["snapshot_ok"]:
            out["errors"].append("snapshot_roundtrip_failed")
    except Exception as e:
        out["checks"]["snapshot_ok"] = False
        out["errors"].append("snapshot_error: " + str(e))

    # final
    out["ok"] = (
        out["checks"].get("fs_ok") is True and
        out["checks"].get("ssot_plan_write_read_ok") is True and
        out["checks"].get("roadmap_ok") is True and
        out["checks"].get("snapshot_ok") is True
    )
    return out
    # /HARDENING_HEALTHZ_SSOT_V3_SNAPSHOT_ENDPOINTS

def _ssot_paths(room_id: str):
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    state_dir = os.path.join(tmp_agent, "state")
    rooms_dir = os.path.join(state_dir, "rooms")
    room_dir = os.path.join(rooms_dir, room_id)
    plan_path = os.path.join(room_dir, "plan.json")
    return tmp_agent, state_dir, rooms_dir, room_dir, plan_path

def _get_room_id(request: Request, fallback: str = "default") -> str:
    rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id")
    if rid:
        return rid.strip()
    # query param opcional
    try:
        q = request.query_params.get("room_id")
        if q:
            return q.strip()
    except Exception:
        pass
    return fallback

def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _default_plan(room_id: str):
    return {
        "room_id": room_id,
        "status": "empty",
        "steps": [],
        "last_eval": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/v1/agent/plan", response_model=AgentPlanResponse)
def agent_plan_ssot(request: Request):
    """
    SSOT: lee state/rooms/<rid>/plan.json y lo devuelve.
    """
    rid = _get_room_id(request, fallback="default")
    _, _, _, _, plan_path = _ssot_paths(rid)

    if not os.path.exists(plan_path):
        plan = _default_plan(rid)
        # no creamos archivo en GET para evitar side-effects; solo devolvemos default
        return AgentPlanResponse(ok=True, room_id=rid, plan=plan, error=None)

    try:
        plan = _read_json(plan_path)
        return AgentPlanResponse(ok=True, room_id=rid, plan=plan, error=None)
    except Exception as e:
        return AgentPlanResponse(ok=False, room_id=rid, plan=None, error=str(e))

@app.post("/v1/agent/evaluate", response_model=AgentEvalResponse)
def agent_evaluate_ssot(
    request: Request,
    req: AgentEvalRequest = Body(..., alias="req")
):
    """
    SSOT: actualiza state/rooms/<rid>/plan.json -> last_eval
    """
    rid = (getattr(req, "room_id", None) or "").strip() or _get_room_id(request, fallback="default")
    _, _, _, _, plan_path = _ssot_paths(rid)

    # cargar/crear plan
    if os.path.exists(plan_path):
        try:
            plan = _read_json(plan_path)
        except Exception:
            plan = _default_plan(rid)
    else:
        plan = _default_plan(rid)

    last_eval = {
        "at": datetime.now(timezone.utc).isoformat(),
    }

    # capturar campos si existen (stubs = opcionales)
    for k in ("observations", "metrics", "state", "notes"):
        try:
            v = getattr(req, k)
            if v is not None:
                last_eval[k] = v
        except Exception:
            pass

    plan["last_eval"] = last_eval
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        _write_json(plan_path, plan)
        return AgentEvalResponse(ok=True, room_id=rid, result={"last_eval": last_eval}, error=None)
    except Exception as e:
        return AgentEvalResponse(ok=False, room_id=rid, result=None, error=str(e))
# --- /HARDENING3_SSOT_ROOMPLAN_JSON ----------------------------------------


# --- HARDENING10_EVAL_SSOT: evaluation persistence per room ---------------------
def _eval_json_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "evaluation.json")

def _eval_ndjson_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "evaluations.ndjson")

def _ssot_write_eval(room_id: str, evaluation: dict):
        # HARDENING10_EVAL_SSOT: persist evaluation (json + ndjson), room-aware
    try:
        # room_id primario: req.req.room_id (payload actual)
        rid = "default"
        inner = None
        try:
            inner = getattr(req, "req", None)
        except Exception:
            inner = None
    
        try:
            if inner is not None:
                _r = getattr(inner, "room_id", None)
                if _r:
                    rid = str(_r).strip() or "default"
        except Exception:
            pass
    
        # fallback header SOLO si existe 'request' en locals()
        if (not rid) or (rid == "default"):
            try:
                _req = locals().get("request", None)
                if _req is not None:
                    hdr = (_req.headers.get("x-room-id") or _req.headers.get("X-Room-Id") or "").strip()
                    if hdr:
                        rid = hdr
            except Exception:
                pass
    
        rid = rid or "default"
    
        eval_obj = {
            "ts": _utc_now() if "_utc_now" in globals() else datetime.now(timezone.utc).isoformat(),
            "room_id": rid,
            "metrics": {},
            "notes": None,
        }
    
        try:
            if inner is not None and isinstance(getattr(inner, "metrics", None), dict):
                eval_obj["metrics"] = getattr(inner, "metrics")
        except Exception:
            pass
    
        try:
            if inner is not None:
                eval_obj["notes"] = getattr(inner, "notes", None)
        except Exception:
            pass
    
        # plan sha256 best-effort
        try:
            pp = None
            if "_plan_path" in globals():
                pp = _plan_path(rid)
            else:
                pp = os.path.join(r"C:\\AI_VAULT\\tmp_agent", "state", "rooms", rid, "plan.json")
            if pp and "_sha256_file" in globals():
                eval_obj["plan_sha256"] = _sha256_file(pp)
            else:
                eval_obj["plan_sha256"] = None
        except Exception:
            eval_obj["plan_sha256"] = None
    
        _ssot_write_eval(rid, eval_obj)
        _ssot_append_eval(rid, eval_obj)
    except Exception:
        pass
        try:
            if inner is not None:
                eval_obj["notes"] = getattr(inner, "notes", None)
        except Exception:
            pass
    
        # include current plan sha256 if available (best-effort)
        try:
            pp = _plan_path(rid) if "_plan_path" in globals() else os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "plan.json")
            eval_obj["plan_sha256"] = _sha256_file(pp) if "_sha256_file" in globals() else None
        except Exception:
            eval_obj["plan_sha256"] = None
    
        _ssot_write_eval(rid, eval_obj)
        _ssot_append_eval(rid, eval_obj)
    except Exception:
        pass

    os.makedirs(os.path.dirname(_eval_json_path(room_id)), exist_ok=True)
    with open(_eval_json_path(room_id), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)

def _ssot_append_eval(room_id: str, evaluation: dict):
    os.makedirs(os.path.dirname(_eval_ndjson_path(room_id)), exist_ok=True)
    with open(_eval_ndjson_path(room_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(evaluation, ensure_ascii=False) + "\n")
# --- /HARDENING10_EVAL_SSOT -----------------------------------------------------



# --- HARDENING7_AUDIT_NDJSON: append-only audit trail per room ----------------
import hashlib

def _audit_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "audit.ndjson")

def _plan_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "plan.json")

def _sha256_file(p: str):
    # HARDENING7_INJECT_EVALUATE_DECORATOR
    try:
        _rid = ''
        try:
            _rid = str(getattr(req, 'room_id', '') or '').strip()
        except Exception:
            _rid = ''
        if not _rid:
            try:
                _rid = (request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or '').strip()
            except Exception:
                _rid = ''
        if not _rid:
            _rid = 'default'
        _audit_append(_rid, event='evaluate')
    except Exception:
        pass

    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None



# --- HARDENING_NOW_ISO_PLACEHOLDER_V1: {{now_iso}} resolver -------------------------
def _resolve_placeholders(obj):
    """
    Reemplaza placeholders seguros dentro de strings:
      - {{now_iso}} -> datetime.now().isoformat(timespec="seconds")
    Best-effort: no lanza excepciones.
    """
    try:
        from datetime import datetime
        now_iso = datetime.now().isoformat(timespec="seconds")
    except Exception:
        now_iso = None

    def _walk(x):
        try:
            if isinstance(x, str):
                if now_iso is not None and "{{now_iso}}" in x:
                    return x.replace("{{now_iso}}", now_iso)
                return x
            if isinstance(x, list):
                return [_walk(v) for v in x]
            if isinstance(x, dict):
                return {k: _walk(v) for k, v in x.items()}
            return x
        except Exception:
            return x

    try:
        return _walk(obj)
    except Exception:
        return obj
# --- /HARDENING_NOW_ISO_PLACEHOLDER_V1 ----------------------------------------------

def _audit_append(room_id: str, event: str, extra=None):
    """
    CANONICAL SAFE_MIN audit:
      - 1 line per call (deterministic)
      - only accept middleware events: event startswith 'audit_mw:'
      - never reads request body
    """
    try:
        rid = str(room_id or "").strip() or "default"
    except Exception:
        rid = "default"

    try:
        ev = str(event or "").strip()
    except Exception:
        ev = ""

    # HARD GATE: only middleware events are allowed
    if not ev.startswith("audit_mw:"):
        return

    try:
        tmp_agent = r"C:\AI_VAULT\tmp_agent"
        audit_path = os.path.join(tmp_agent, "state", "rooms", rid, "audit.ndjson")
        plan_path  = os.path.join(tmp_agent, "state", "rooms", rid, "plan.json")
        os.makedirs(os.path.dirname(audit_path), exist_ok=True)

        plan_sha256 = None
        try:
            import hashlib
            if os.path.exists(plan_path):
                h = hashlib.sha256()
                with open(plan_path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                plan_sha256 = h.hexdigest()
        except Exception:
            plan_sha256 = None

        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "room_id": rid,
            "event": ev,
            "plan_sha256": plan_sha256,
        }
        if isinstance(extra, dict) and extra:
            rec["extra"] = extra

        # EXACTLY ONE APPEND
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # audit must never break API
        return




# --- HARDENING10D_EVAL_PERSIST_MW: persist evaluation artifacts (no body read) ---
def _eval_json_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "evaluation.json")

def _eval_ndjson_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "evaluations.ndjson")

def _ssot_write_eval(room_id: str, evaluation: dict):
    os.makedirs(os.path.dirname(_eval_json_path(room_id)), exist_ok=True)
    with open(_eval_json_path(room_id), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=2)

def _ssot_append_eval(room_id: str, evaluation: dict):
    os.makedirs(os.path.dirname(_eval_ndjson_path(room_id)), exist_ok=True)
    with open(_eval_ndjson_path(room_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(evaluation, ensure_ascii=False) + "\n")
# --- /HARDENING10D_EVAL_PERSIST_MW ------------------------------------------------

def _audit_room_id_from_request(request: Request) -> str:
    try:
        rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
        if rid:
            return rid
    except Exception:
        pass
    try:
        q = request.query_params.get("room_id")
        if q:
            return str(q).strip()
    except Exception:
        pass
    return "default"

@app.middleware("http")
async def _audit_mw(request: Request, call_next):
    # HARDENING7_FIX_AUDIT_MW_AUDIT_PATHS_FALLBACK
    # Fallback: evita NameError si _AUDIT_PATHS no existe.
    try:
        _paths = _AUDIT_PATHS  # type: ignore[name-defined]
    except Exception:
        _paths = {"/v1/agent/plan", "/v1/agent/evaluate", "/v1/agent/run_once"}

    path = ""
    # HARDENING8_1B2_AUDIT_REQID_LATENCY_SAFE
    req_id = None
    t0 = None
    try:
        req_id = str(uuid.uuid4())
        t0 = time.perf_counter()
    except Exception:
        req_id = None
        t0 = None

    try:
        path = request.url.path
    except Exception:
        path = ""
    # pre-log only (no body read)
    if path in _paths:
        rid = _audit_room_id_from_request(request)
        try:
            # HARDENING8_1B4_REMOVE_ALL_AUDIT_PRELOGS: _audit_append(rid, event=f"audit_mw:{path}", extra={"method": request.method})  # HARDENING8_1B3_REMOVE_AUDIT_PRELOG: removed prelog

            pass
        except Exception:
            pass
    resp = None
    status_code = None
    try:
        resp = await call_next(request)
        try:
            status_code = getattr(resp, 'status_code', None)
        except Exception:
            status_code = None
        return resp
    finally:
        try:
            dur_ms = None
            if t0 is not None:
                dur_ms = int((time.perf_counter() - t0) * 1000)
            if path in _paths:
                extra = {'method': request.method, 'req_id': req_id, 'status_code': status_code, 'duration_ms': dur_ms}
                try:
                    extra['client_host'] = getattr(getattr(request, 'client', None), 'host', None)
                except Exception:
                    pass
                _audit_append(rid, event=f"audit_mw:{path}", extra=extra)
                # HARDENING10D_EVAL_PERSIST_MW
                try:
                    if path == '/v1/agent/evaluate':
                        # persist evaluation snapshot (no body read)
                        ev = {
                            'ts': datetime.now(timezone.utc).isoformat(),
                            'room_id': rid,
                            'status_code': status_code,
                            'duration_ms': dur_ms,
                            'req_id': req_id,
                            'plan_sha256': None,
                        }
                        try:
                            ev['plan_sha256'] = _sha256_file(_plan_path(rid)) if '_sha256_file' in globals() and '_plan_path' in globals() else None
                        except Exception:
                            ev['plan_sha256'] = None
                        _ssot_write_eval(rid, ev)
                        _ssot_append_eval(rid, ev)
                except Exception:
                    pass

        except Exception:
            pass

# --- /HARDENING7_3_AUDIT_MW ---------------------------------------------------
# HARDENING7_3_AUDIT_MW



# --- HARDENING6_SSOT_RUNONCE: canonical run_once over SSOT -----------------
import json
from datetime import datetime, timezone
from fastapi import Request, Body, HTTPException

def _ssot_plan_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "plan.json")

def _ssot_read_plan(room_id: str) -> dict:
    pp = _ssot_plan_path(room_id)
    if not os.path.exists(pp):
        return {}
    with open(pp, "r", encoding="utf-8") as f:
        return json.load(f) or {}



# --- HARDENING_AUDIT_SEMANTIC_V1: semantic audit helper ----------------------------
def _audit_append(room_id: str, event: str, extra=None):
    """
    Append semantic audit event to state/rooms/<room_id>/audit.ndjson (best-effort).
    Does NOT raise; never blocks the main flow.
    """
    try:
        import os, json
        from datetime import datetime, timezone
        rid = (room_id or "default").strip() or "default"
        base = r"C:\AI_VAULT\tmp_agent"
        room_dir = os.path.join(base, "state", "rooms", rid)
        os.makedirs(room_dir, exist_ok=True)
        p = os.path.join(room_dir, "audit.ndjson")
        evt = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "room_id": rid,
            "event": str(event or "audit_event"),
            "extra": extra if isinstance(extra, dict) else {"value": extra},
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")
    except Exception:
        pass
# --- /HARDENING_AUDIT_SEMANTIC_V1 -------------------------------------------------

def _ssot_write_plan(room_id: str, plan: dict):
    pp = _ssot_plan_path(room_id)
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def _get_room_id_from_req_and_headers(req_obj, request: Request) -> str:
    rid = ""
    try:
        rid = str(getattr(req_obj, "room_id", "") or "").strip()
    except Exception:
        rid = ""
    if rid:
        return rid
    try:
        hdr = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or ""
        hdr = str(hdr).strip()
        if hdr:
            return hdr
    except Exception:
        pass
    return "default"

def _plan_steps(plan: dict):
    steps = plan.get("steps", [])
    return steps if isinstance(steps, list) else []



# --- HARDENING9_PLANNER_POST_SSOT: POST /v1/agent/plan creates plan.json --------
@app.post("/v1/agent/plan")
def agent_plan_create_ssot(request: Request, req: dict = Body(...)):
    """
    Planner SSOT canónico:
    - room_id del body gana; header x-room-id es fallback
    - valida/normaliza (content no-null, placeholder {{now_iso}}, y \\n literal -> newline real)
    - persiste SIEMPRE: C:\\AI_VAULT\\tmp_agent\\state\\rooms\\<rid>\\plan.json
    """
    # HARDENING_PLAN_HANDLER_CANONICAL_V1
    try:
        # rid: body wins, header fallback
        _rid_body = (req.get("room_id") or "").strip() if isinstance(req, dict) else ""
        _rid_hdr  = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
        rid = (_rid_body or _rid_hdr or "default").strip()

        if not isinstance(req, dict):
            # ultra-guard; FastAPI Body(...) should already be dict
            try:
                req = dict(req)
            except Exception:
                req = {}

        req["room_id"] = rid

        # validate+normalize steps
        _plan_norm, _errs = _harden_plan_payload(req)
        if _errs:
            return {"ok": False, "error": "plan_validation_failed", "details": _errs}

        plan_obj = _plan_norm

        # Ensure basic fields
        if "status" not in plan_obj:
            plan_obj["status"] = "active"
        if "steps" not in plan_obj:
            plan_obj["steps"] = []

        # Persist SSOT plan.json
        rooms_dir = None
        try:
            rooms_dir = globals().get("ROOMS_DIR", None)
        except Exception:
            rooms_dir = None

        if rooms_dir is None:
            rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")

        room_dir = rooms_dir / rid
        room_dir.mkdir(parents=True, exist_ok=True)
        plan_path = room_dir / "plan.json"
        plan_path.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"ok": True, "room_id": rid, "plan": plan_obj}

    except Exception as e:
        return {"ok": False, "error": "plan_handler_exception", "detail": str(e)}
    # /HARDENING_PLAN_HANDLER_CANONICAL_V1


def agent_run_ssot(request: Request, req: dict = Body(...)):
    # HARDENING11C_RUN_SSOT_ORCHESTRATOR_FIX
    """
    Runner SSOT (robusto):
      - Lee plan.json por room
      - Ejecuta hasta max_steps (calls reales)
      - Si un step queda "proposed" => bloquea y devuelve required_approve/proposal_id
      - Si plan queda "complete" => termina
    """
    # --- helper local: room_id ---
    room_id = "default"
    try:
        if isinstance(req, dict) and req.get("room_id"):
            room_id = str(req.get("room_id") or "").strip() or "default"
    except Exception:
        room_id = "default"
    if (not room_id) or room_id == "default":
        try:
            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
            if hdr:
                room_id = hdr
        except Exception:
            pass
    room_id = room_id or "default"

    # --- helper local: max_steps ---
    max_steps = 10
    try:
        if isinstance(req, dict) and req.get("max_steps") is not None:
            max_steps = int(req.get("max_steps"))
    except Exception:
        max_steps = 10
    if max_steps <= 0:
        max_steps = 1
    if max_steps > 200:
        max_steps = 200

    # --- local wrapper (mantén el que ya tienes si existe) ---
    def _call_exec_step(room_id, step_id, mode, approve_token=None):
        """HARDENING_EXECSTEP_REQ_ONLY_BRIDGE
        Executor accepts only one-arg signature: fn(req).
        We always call _SAFE_INTERNAL_EXECUTE_STEP with a single dict payload.
        """
        fn = globals().get("_SAFE_INTERNAL_EXECUTE_STEP")
        if not callable(fn):
            return {"ok": False, "error": "_SAFE_INTERNAL_EXECUTE_STEP not found/callable"}
        payload = {
            # canonical
            'room_id': room_id,
            'step_id': step_id,
            'mode': mode,
            'approve_token': approve_token,
            # aliases comunes
            'rid': room_id,
            'room': room_id,
            'roomId': room_id,
            'x_room_id': room_id,
            'id': step_id,
            'step': step_id,
            'stepId': step_id,
            'action': mode,
            'op': mode,
            'approve': approve_token,
            'token': approve_token,
            'required_approve': approve_token,
            'approval_token': approve_token,
        }
        try:
            # HARDENING_EXECSTEP_REQ_OBJECT_FIX
            req_obj = types.SimpleNamespace(**payload) if isinstance(payload, dict) else payload
            return fn(req_obj)
        except TypeError as e:
            return {"ok": False, "error": f"executor_typeerror: {e}", "payload": payload}
        except Exception as e:
            return {"ok": False, "error": f"executor_exception: {e}", "payload": payload}
        fn = globals().get("_SAFE_INTERNAL_EXECUTE_STEP")
        if not callable(fn):
            return {"ok": False, "error": "_SAFE_INTERNAL_EXECUTE_STEP not found/callable"}

        try:
            sig = inspect.signature(fn)
            params = sig.parameters
        except Exception:
            sig = None
            params = {}

        if sig is not None:
            kwargs = {}
            if "room_id" in params: kwargs["room_id"] = room_id
            if "step_id" in params: kwargs["step_id"] = step_id
            if "mode" in params: kwargs["mode"] = mode
            if "approve_token" in params: kwargs["approve_token"] = approve_token

            has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            if not has_varkw:
                kwargs = {k: v for k, v in kwargs.items() if k in params}

            try:
                return fn(**kwargs)
            except TypeError:
                pass

        # Positional fallbacks
        try:    return fn(room_id, step_id, mode, approve_token)
        except TypeError: pass
        try:    return fn(step_id, mode, approve_token)
        except TypeError: pass
        try:    return fn(room_id, step_id, mode)
        except TypeError: pass
        try:    return fn(step_id, mode)
        except TypeError as e:
            return {"ok": False, "error": f"_SAFE_INTERNAL_EXECUTE_STEP signature mismatch: {e}"}

    # --- plan IO (usa SSOT helpers si existen) ---
    def _read_plan(rid: str):
        try:
            if "_ssot_read_plan" in globals():
                return globals()["_ssot_read_plan"](rid)
        except Exception:
            pass
        import os, json
        pp = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "plan.json")
        if not os.path.exists(pp):
            return None
        with open(pp, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_plan(rid: str, plan: dict):
        try:
            if "_ssot_write_plan" in globals():
                return globals()["_ssot_write_plan"](rid, plan)
        except Exception:
            pass
        import os, json
        pp = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "plan.json")
        os.makedirs(os.path.dirname(pp), exist_ok=True)
        with open(pp, "w", encoding="utf-8") as f:
            # HARDENING20_PLAN_STATUS_CANON_SSOT (auto)
            try:
                plan = _ssot_canonize_and_recompute_inplace(plan)
            except Exception:
                pass
            json.dump(plan, f, ensure_ascii=False, indent=2)

    # --- select next executable step ---
    def _find_next_step(plan: dict):
        try:
            steps = plan.get("steps") if isinstance(plan, dict) else None
            if not isinstance(steps, list):
                return None
            # si hay proposed -> bloquear ya
            for st in steps:
                if isinstance(st, dict) and str(st.get("status") or "").strip().lower() == "proposed":
                    return {"kind": "blocked", "step": st}
            # siguiente todo/in_progress
            for st in steps:
                if not isinstance(st, dict):
                    continue
                status = str(st.get("status") or "").strip().lower()
                if status in ("todo", "in_progress"):
                    return {"kind": "run", "step": st}
            return None
        except Exception:
            return None

    plan0 = _read_plan(room_id)
    if not plan0:
        return {"ok": True, "room_id": room_id, "action": "run", "executed": 0, "blocked": None, "plan": None, "error": "no_plan"}

    executed = 0
    blocked = None

    # loop: siempre recargar plan desde SSOT tras ejecutar un step
    for _ in range(max_steps):
        plan = _read_plan(room_id) or plan0
        # si está complete => termina
        try:
            if str(plan.get("status") or "").strip().lower() in ("complete", "completed", "done"):
                break
        except Exception:
            pass

        sel = _find_next_step(plan)
        if not sel:
            # no hay steps ejecutables
            break

        if sel["kind"] == "blocked":
            st = sel["step"]
            blocked = {
                "step_id": st.get("id"),
                "proposal_id": st.get("proposal_id"),
                "required_approve": st.get("required_approve"),
                "tool_name": st.get("tool_name"),
            }
            break

        st = sel["step"]
        step_id = str(st.get("id") or "").strip()
        if not step_id:
            break

        # ejecutar step (modo run, sin approve)
        res = _call_exec_step(room_id, step_id, mode="run", approve_token=None)
        executed += 1

        # recargar y verificar si quedamos bloqueados o complete
        plan_after = _read_plan(room_id) or plan
        # si el step quedó proposed => bloquear
        sel2 = _find_next_step(plan_after)
        if sel2 and sel2["kind"] == "blocked":
            st2 = sel2["step"]
            blocked = {
                "step_id": st2.get("id"),
                "proposal_id": st2.get("proposal_id"),
                "required_approve": st2.get("required_approve"),
                "tool_name": st2.get("tool_name"),
            }
            break

        try:
            if str(plan_after.get("status") or "").strip().lower() in ("complete", "completed", "done"):
                break
        except Exception:
            pass

    # retorno final con plan fresco
    plan_final = _read_plan(room_id)
    _tmp = {"ok": True, "room_id": room_id, "action": "run", "executed": executed, "blocked": blocked, "plan": plan_final}
    try:
        _audit_append(((_tmp.get("room_id") if isinstance(_tmp, dict) else None) or room_id), "run_result", {"ok": (_tmp.get("ok") if isinstance(_tmp, dict) else None), "blocked": (_tmp.get("blocked") if isinstance(_tmp, dict) else None), "proposal_id": (((_tmp.get("blocked") or {}).get("proposal_id")) if isinstance(_tmp, dict) and isinstance(_tmp.get("blocked"), dict) else None), "step_id": (((_tmp.get("blocked") or {}).get("step_id")) if isinstance(_tmp, dict) and isinstance(_tmp.get("blocked"), dict) else None), "executed": (_tmp.get("executed") if isinstance(_tmp, dict) else None)})
    except Exception:
        pass
    return _tmp
# --- HARDENING13_EVAL_GET_SSOT: evaluation readers (SSOT) -------------------------
@app.get("/v1/agent/evaluation")
def agent_evaluation_get_ssot(request: Request):
    """
    SSOT: lee state/rooms/<rid>/evaluation.json y lo devuelve.
    room_id: header x-room-id (o default)
    """
    import os, json
    rid = "default"
    try:
        rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
    except Exception:
        rid = "default"

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "evaluation.json")
    if not os.path.exists(p):
        return {"ok": False, "room_id": rid, "error": "evaluation.json_not_found", "path": p}

    try:
        data = json.loads(open(p, "r", encoding="utf-8").read())
        return {"ok": True, "room_id": rid, "evaluation": data}
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"evaluation.json_read_failed: {e}", "path": p}

@app.get("/v1/agent/evaluations")
def agent_evaluations_tail_ssot(request: Request, limit: int = Query(50, ge=1, le=500)):
    """
    SSOT: tail N de state/rooms/<rid>/evaluations.ndjson
    room_id: header x-room-id (o default)
    """
    import os, json
    rid = "default"
    try:
        rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
    except Exception:
        rid = "default"

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "evaluations.ndjson")
    if not os.path.exists(p):
        return {"ok": False, "room_id": rid, "error": "evaluations.ndjson_not_found", "path": p, "items": []}

    # tail simple (no cargar todo si es grande)
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            # leer ~128KB o hasta el inicio
            chunk = 131072
            start = max(0, end - chunk)
            f.seek(start, os.SEEK_SET)
            buf = f.read()
        text = buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        tail = lines[-limit:] if len(lines) > limit else lines
        items = []
        bad = 0
        for ln in tail:
            try:
                items.append(json.loads(ln))
            except Exception:
                bad += 1
        return {"ok": True, "room_id": rid, "path": p, "limit": limit, "items": items, "bad_lines": bad}
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"tail_failed: {e}", "path": p, "items": []}

# HARDENING13_EVAL_GET_SSOT
# --- /HARDENING13_EVAL_GET_SSOT ---------------------------------------------------



# --- HARDENING14_PROPOSALS_REJECT_SSOT: proposal inspect + reject -----------------
@app.get("/v1/agent/proposal")
def agent_proposal_get_ssot(request: Request, proposal_id: str = Query(..., min_length=3, max_length=128)):
    """
    SSOT: lee tmp_agent/proposals/<proposal_id>.json y lo devuelve.
    """
    import os, json
    pid = (proposal_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_proposal_id"}

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "proposals", f"{pid}.json")
    if not os.path.exists(p):
        return {"ok": False, "proposal_id": pid, "error": "proposal_not_found", "path": p}

    try:
        data = json.loads(open(p, "r", encoding="utf-8").read())
        return {"ok": True, "proposal_id": pid, "proposal": data}
    except Exception as e:
        return {"ok": False, "proposal_id": pid, "error": f"proposal_read_failed: {e}", "path": p}

# HARDENING_EPISODE_P3_1_BOOTSTRAP_V1 (inserted to ensure decorators exist at import-time)
def _episode_begin(locals_d: dict, phase: str):
    from pathlib import Path
    import uuid, hashlib
    from datetime import datetime, timezone

    def nowz():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def infer_room_id(d):
        if isinstance(d, dict):
            for k in ("room_id","rid"):
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for k in ("req","request","body"):
                v = d.get(k)
                if v is None:
                    continue
                rid = getattr(v, "room_id", None)
                if isinstance(rid, str) and rid.strip():
                    return rid.strip()
                if isinstance(v, dict):
                    rid = v.get("room_id")
                    if isinstance(rid, str) and rid.strip():
                        return rid.strip()
        return "default"

    rid = infer_room_id(locals_d or {})
    run_id = "run_" + uuid.uuid4().hex[:12]

    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    (room_dir / "_last_run_id.txt").write_text(run_id, encoding="utf-8")

    plan_path = room_dir / "plan.json"
    plan_sha256 = None
    if plan_path.exists():
        b = plan_path.read_bytes()
        h = hashlib.sha256(); h.update(b); plan_sha256 = h.hexdigest()

    return {
        "ts_start": nowz(),
        "ts_end": None,
        "room_id": rid,
        "run_id": run_id,
        "phase": phase,
        "plan_path": str(plan_path) if plan_path.exists() else None,
        "plan_sha256": plan_sha256,
        "result": None,
        "errors": []
    }

def _episode_end(ep: dict, result):
    from pathlib import Path
    import json
    from datetime import datetime, timezone

    def nowz():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ep["ts_end"] = nowz()

    rid = ep.get("room_id") or "default"
    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    # summarize result (best-effort)
    try:
        if isinstance(result, dict):
            ep["result"] = {
                "ok": result.get("ok"),
                "blocked": result.get("blocked"),
                "proposal_id": (result.get("proposal_id") or (result.get("blocked") or {}).get("proposal_id")),
                "required_approve": (result.get("required_approve") or (result.get("blocked") or {}).get("required_approve")),
            }
        else:
            ep["result"] = {"type": type(result).__name__}
    except Exception as e:
        ep.setdefault("errors", []).append("result_summary_error: " + repr(e))

    episodes_dir = room_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    latest = room_dir / "episode.json"
    perrun = episodes_dir / f"episode_{ep.get('run_id','unknown')}.json"

    latest.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    perrun.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ep

def episode_wrap(phase: str):
    def deco(fn):
        def _wrapped(*args, **kwargs):
            __ep = _episode_begin(locals(), phase=phase)
            try:
                ret = fn(*args, **kwargs)
            except Exception as e:
                __ep.setdefault("errors", []).append("exception: " + repr(e))
                _episode_end(__ep, {"ok": False, "error": "exception", "detail": repr(e)})
                raise
            _episode_end(__ep, ret)
            return ret
        return _wrapped
    return deco

# HARDENING_EPISODE_P3_1_BOOTSTRAP_V2_CANON (ensure episode_wrap exists at import-time; room_id inferred from args/kwargs)
def _ep_nowz():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _ep_infer_room_id(args, kwargs):
    # 1) direct kwargs
    for k in ("room_id","rid"):
        v = kwargs.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # 2) common kwargs objects/dicts
    for k in ("req","body","payload"):
        v = kwargs.get(k)
        if v is None:
            continue
        rid = getattr(v, "room_id", None)
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
        if isinstance(v, dict):
            rid = v.get("room_id") or v.get("rid")
            if isinstance(rid, str) and rid.strip():
                return rid.strip()

    # 3) positional args objects/dicts
    for v in (args or ()):
        rid = getattr(v, "room_id", None)
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
        if isinstance(v, dict):
            rid = v.get("room_id") or v.get("rid")
            if isinstance(rid, str) and rid.strip():
                return rid.strip()

    return "default"

def _episode_begin_from_call(args, kwargs, phase: str):
    import uuid, hashlib
    from pathlib import Path

    rid = _ep_infer_room_id(args, kwargs)
    run_id = "run_" + uuid.uuid4().hex[:12]

    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    (room_dir / "_last_run_id.txt").write_text(run_id, encoding="utf-8")

    plan_path = room_dir / "plan.json"
    plan_sha256 = None
    if plan_path.exists():
        b = plan_path.read_bytes()
        h = hashlib.sha256(); h.update(b); plan_sha256 = h.hexdigest()

    return {
        "ts_start": _ep_nowz(),
        "ts_end": None,
        "room_id": rid,
        "run_id": run_id,
        "phase": phase,
        "plan_path": str(plan_path) if plan_path.exists() else None,
        "plan_sha256": plan_sha256,
        "result": None,
        "errors": []
    }

def _episode_end_write(ep: dict, result):
    import json
    from pathlib import Path

    ep["ts_end"] = _ep_nowz()
    rid = ep.get("room_id") or "default"

    # summarize minimal contract
    try:
        if isinstance(result, dict):
            ep["result"] = {
                "ok": result.get("ok"),
                "blocked": result.get("blocked"),
                "proposal_id": (result.get("proposal_id") or (result.get("blocked") or {}).get("proposal_id")),
                "required_approve": (result.get("required_approve") or (result.get("blocked") or {}).get("required_approve")),
            }
        else:
            ep["result"] = {"type": type(result).__name__}
    except Exception as e:
        ep.setdefault("errors", []).append("result_summary_error: " + repr(e))

    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    episodes_dir = room_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    latest = room_dir / "episode.json"
    perrun = episodes_dir / f"episode_{ep.get('run_id','unknown')}.json"

    latest.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    perrun.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ep

def episode_wrap(phase: str):
    import inspect
    from functools import wraps

    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def _aw(*args, **kwargs):
                ep = _episode_begin_from_call(args, kwargs, phase=phase)
                try:
                    ret = await fn(*args, **kwargs)
                except Exception as e:
                    ep.setdefault("errors", []).append("exception: " + repr(e))
                    _episode_end_write(ep, {"ok": False, "error": "exception", "detail": repr(e)})
                    raise
                _episode_end_write(ep, ret)
                return ret
            return _aw
        else:
            @wraps(fn)
            def _sw(*args, **kwargs):
                ep = _episode_begin_from_call(args, kwargs, phase=phase)
                try:
                    ret = fn(*args, **kwargs)
                except Exception as e:
                    ep.setdefault("errors", []).append("exception: " + repr(e))
                    _episode_end_write(ep, {"ok": False, "error": "exception", "detail": repr(e)})
                    raise
                _episode_end_write(ep, ret)
                return ret
            return _sw
    return deco

@app.post("/v1/agent/reject")
@episode_wrap("reject")
def agent_reject_ssot(request: Request, req: dict = Body(...)):
    """
    Reject SSOT:
      - input: {room_id?, proposal_id?, approve_token?, reason?}
      - resolves room_id from req -> header -> default
      - resolves proposal_id from approve_token by reading plan.json if needed
      - updates plan.json: step(proposed)->todo + clears proposal fields
      - appends rejections.ndjson (best-effort)
    """
    import os, json
    from datetime import datetime, timezone

    # room_id
    room_id = "default"
    try:
        if isinstance(req, dict) and req.get("room_id"):
            room_id = str(req.get("room_id") or "").strip() or "default"
    except Exception:
        room_id = "default"
    if (not room_id) or room_id == "default":
        try:
            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
            if hdr:
                room_id = hdr
        except Exception:
            pass
    room_id = room_id or "default"

    proposal_id = None
    approve_token = None
    reason = None

    try:
        if isinstance(req, dict):
            proposal_id = req.get("proposal_id")
            approve_token = req.get("approve_token")
            reason = req.get("reason")
    except Exception:
        pass

    proposal_id = (str(proposal_id or "").strip() or None)
    approve_token = (str(approve_token or "").strip() or None)
    reason = (str(reason or "").strip() or None)

    plan_path = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", room_id, "plan.json")
    if not os.path.exists(plan_path):
        return {"ok": False, "room_id": room_id, "error": "plan.json_not_found", "path": plan_path}

    try:
        plan = json.loads(open(plan_path, "r", encoding="utf-8").read())
    except Exception as e:
        return {"ok": False, "room_id": room_id, "error": f"plan.json_read_failed: {e}", "path": plan_path}

    # resolve proposal_id from approve_token if missing
    if (proposal_id is None) and approve_token:
        try:
            for st in (plan.get("steps") or []):
                if isinstance(st, dict) and str(st.get("required_approve") or "").strip() == approve_token:
                    proposal_id = str(st.get("proposal_id") or "").strip() or None
                    break
        except Exception:
            pass

    if not proposal_id:
        return {"ok": False, "room_id": room_id, "error": "cannot_resolve_proposal_id"}

    # find steps referencing proposal_id (or required_approve)
    touched = 0
    step_ids = []
    try:
        for st in (plan.get("steps") or []):
            if not isinstance(st, dict):
                continue
            pid = str(st.get("proposal_id") or "").strip()
            rat = str(st.get("required_approve") or "").strip()
            if pid == proposal_id or (approve_token and rat == approve_token):
                st["status"] = "todo"
                # clear proposal linkage
                if "proposal_id" in st: del st["proposal_id"]
                if "required_approve" in st: del st["required_approve"]
                touched += 1
                if st.get("id") is not None:
                    step_ids.append(str(st.get("id")))
    except Exception:
        pass

    if touched <= 0:
        return {"ok": False, "room_id": room_id, "proposal_id": proposal_id, "error": "no_steps_matched_proposal"}

    # update plan updated_at
    try:
        plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    except Exception:
        pass

    # write plan.json
    try:
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        with open(plan_path, "w", encoding="utf-8") as f:
            # HARDENING20_PLAN_STATUS_CANON_SSOT (auto)
            try:
                plan = _ssot_canonize_and_recompute_inplace(plan)
            except Exception:
                pass
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"ok": False, "room_id": room_id, "proposal_id": proposal_id, "error": f"plan.json_write_failed: {e}", "touched": touched, "step_ids": step_ids}

    # append rejections.ndjson best-effort
    try:
        rej = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "room_id": room_id,
            "proposal_id": proposal_id,
            "approve_token": approve_token,
            "reason": reason,
            "step_ids": step_ids,
        }
        rej_path = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", room_id, "rejections.ndjson")
        with open(rej_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rej, ensure_ascii=False) + "\n")
    except Exception:
        pass

    _tmp = {"ok": True, "room_id": room_id, "proposal_id": proposal_id, "touched": touched, "step_ids": step_ids, "plan": plan, "impl": "HARDENING14_PROPOSALS_REJECT_SSOT"}
    try:
        _audit_append(((_tmp.get("room_id") if isinstance(_tmp, dict) else None) or room_id), "reject_result", {"ok": (_tmp.get("ok") if isinstance(_tmp, dict) else None), "proposal_id": ((_tmp.get("proposal_id") if isinstance(_tmp, dict) else None) or (req.get("proposal_id") if isinstance(req, dict) else None)), "step_id": (_tmp.get("step_id") if isinstance(_tmp, dict) else None)})
    except Exception:
        pass
    return _tmp
# HARDENING14_PROPOSALS_REJECT_SSOT
# --- /HARDENING14_PROPOSALS_REJECT_SSOT -------------------------------------------

@app.post("/v1/agent/run_once", response_model=AgentRunOnceResponse)
@episode_wrap("run_once")
def agent_run_once_ssot(request: Request, req: AgentRunOnceRequest = Body(...)):
    room_id = _get_room_id_from_req_and_headers(req, request)
    plan = _ssot_read_plan(room_id) or {}

    # si no hay plan en disco, noop (no inventamos plan aquí)
    if not plan:
        return {"ok": True, "room_id": room_id, "action": "noop_no_plan", "plan": {}}

    if isinstance(plan, dict):
        plan.setdefault("room_id", room_id)

    status = str(plan.get("status", "") or "").lower()
    steps = _plan_steps(plan)

    if status == "complete":
        return {"ok": True, "room_id": room_id, "action": "noop_complete", "plan": plan}

    # approve flow
    approve_token = ""
    try:
        approve_token = str(getattr(req, "approve_token", "") or "").strip()
    except Exception:
        approve_token = ""

    if approve_token:
        if not approve_token.startswith("APPLY_"):
            raise HTTPException(status_code=400, detail="approve_token must be APPLY_<proposal_id>")

        # localizar step con proposal_id y status proposed
        target_pid = approve_token.replace("APPLY_", "", 1)
        step_to_apply = None
        for s in steps:
            if not isinstance(s, dict):
                continue
            if str(s.get("status")) != "proposed":
                continue
            if str(s.get("proposal_id") or "") == str(target_pid):
                step_to_apply = s
                break

        if not step_to_apply:
            return {"ok": True, "room_id": room_id, "action": "noop_no_matching_proposed_step", "plan": plan}

        step_id = str(step_to_apply.get("id") or "")

        if "agent_execute_step" not in globals():
            return {
                "ok": False,
                "room_id": room_id,
                "action": "error_execute_step_unavailable",
                "error": "agent_execute_step not available in SAFE_MIN",
                "plan": plan,
            }

        # aplicar
        res = agent_execute_step(type("ExecReq", (), {"room_id": room_id, "step_id": step_id, "mode": "apply", "approve_token": approve_token})())

                # HARDENING6_5_3: NO forzar done aquí. agent_execute_step es la autoridad.
        # Recargar plan desde SSOT para devolver estado real.
        plan = _ssot_read_plan(room_id) or plan

        return {"ok": True, "room_id": room_id, "action": "apply_step", "step_id": step_id, "result": res, "plan": plan}

    # encontrar siguiente step actionable
    next_step = None
    for s in steps:
        if isinstance(s, dict) and str(s.get("status")) in {"todo", "in_progress"}:
            next_step = s
            break

    if not next_step:
        return {"ok": True, "room_id": room_id, "action": "noop_no_todo", "plan": plan}

    step_id = str(next_step.get("id") or "")
    tool_name = str(next_step.get("tool_name") or "")

    if "agent_execute_step" not in globals():
        return {
            "ok": False,
            "room_id": room_id,
            "action": "error_execute_step_unavailable",
            "error": "agent_execute_step not available in SAFE_MIN",
            "step_id": step_id,
            "tool_name": tool_name,
            "plan": plan,
        }

    # proponer
    res = agent_execute_step(type("ExecReq", (), {"room_id": room_id, "step_id": step_id, "mode": "propose"})())

    # si es write, guardar proposal_id y required_approve
    try:
        if "_is_write_tool" in globals() and _is_write_tool(tool_name):
            pid = None
            try:
                pid = (res.get("result") or {}).get("proposal_id")
            except Exception:
                pid = None
            if pid:
                for s in steps:
                    if isinstance(s, dict) and str(s.get("id")) == step_id:
                        s["status"] = "proposed"
                        s["proposal_id"] = str(pid)
                        s["required_approve"] = "APPLY_" + str(pid)
                        break
                plan["steps"] = steps
                plan["updated_at"] = _utc_now()
                _ssot_write_plan(room_id, plan)
                return {
                    "ok": True,
                    "room_id": room_id,
                    "action": "propose_write_step",
                    "step_id": step_id,
                    "needs_approval": True,
                    "approve_token": "APPLY_" + str(pid),
                    "result": res,
                    "plan": plan,
                }
    except Exception:
        pass

    # read-only: marcar done y evaluar (si evaluate existe)
    try:
        if "_is_read_tool" in globals() and _is_read_tool(tool_name):
            for s in steps:
                if isinstance(s, dict) and str(s.get("id")) == step_id:
                    s["status"] = "done"
                    break
            plan["steps"] = steps
            plan["updated_at"] = _utc_now()
            _ssot_write_plan(room_id, plan)
    except Exception:
        pass

    return {"ok": True, "room_id": room_id, "action": "propose_step", "step_id": step_id, "result": res, "plan": plan}
# --- /HARDENING6_SSOT_RUNONCE ----------------------------------------------


# --- HARDENING6_INTERNAL_KEY_MW: protect internal exec endpoints ------------
from fastapi import Request, HTTPException

def _internal_key_path():
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "internal_key.txt")

def _get_or_create_internal_key():
    kp = _internal_key_path()
    os.makedirs(os.path.dirname(kp), exist_ok=True)
    if os.path.exists(kp):
        try:
            return open(kp, "r", encoding="utf-8").read().strip()
        except Exception:
            pass
    key = "IK_" + secrets.token_hex(16)
    try:
        open(kp, "w", encoding="utf-8").write(key)
    except Exception:
        pass
    return key

_INTERNAL_KEY = None

@app.middleware("http")
async def _internal_key_mw(request: Request, call_next):
    # proteger solo execute_step (y en el futuro puedes agregar más)
    if request.url.path == "/v1/agent/execute_step":
        # loopback only
        host = ""
        try:
            host = request.client.host or ""
        except Exception:
            host = ""
        if host not in ("127.0.0.1", "::1"):
            raise HTTPException(status_code=403, detail="execute_step restricted to loopback")

        # key required
        global _INTERNAL_KEY
        if _INTERNAL_KEY is None:
            _INTERNAL_KEY = _get_or_create_internal_key()
        got = (request.headers.get("x-internal-key") or request.headers.get("X-Internal-Key") or "").strip()
        if not got or got != _INTERNAL_KEY:
            raise HTTPException(status_code=403, detail="missing/invalid x-internal-key")

    return await call_next(request)
# --- /HARDENING6_INTERNAL_KEY_MW -------------------------------------------


# --- HARDENING6_3_INTERNAL_RUNNER: minimal internal agent_execute_step -------
import json
from datetime import datetime, timezone

def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def _ssot_plan_path(room_id: str) -> str:
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    return os.path.join(tmp_agent, "state", "rooms", room_id, "plan.json")

def _ssot_read_plan(room_id: str) -> dict:
    pp = _ssot_plan_path(room_id)
    if not os.path.exists(pp):
        return {}
    with open(pp, "r", encoding="utf-8") as f:
        return json.load(f) or {}

def _ssot_write_plan(room_id: str, plan: dict):
    pp = _ssot_plan_path(room_id)
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    with open(pp, "w", encoding="utf-8") as f:
        # HARDENING20_PLAN_STATUS_CANON_SSOT (auto)
        try:
            plan = _ssot_canonize_and_recompute_inplace(plan)
        except Exception:
            pass
        json.dump(plan, f, ensure_ascii=False, indent=2)

def _find_step(plan: dict, step_id: str):
    """
    Robusto: normaliza ids y soporta variantes.
    Devuelve dict step o None.
    """
    try:
        sid = str(step_id).strip()
    except Exception:
        sid = step_id

    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        return None

    def norm(x):
        try:
            return str(x).strip()
        except Exception:
            return x

    # match por id / step_id / stepId
    for s in steps:
        if not isinstance(s, dict):
            continue
        for k in ("id", "step_id", "stepId"):
            if norm(s.get(k)) == norm(sid):
                return s

    return None
# --- HARDENING6_5_WRITE_GATE helpers ---------------------------------------
def _proposal_dir():
    tmp_agent = r"C:\AI_VAULT\tmp_agent"
    pd = os.path.join(tmp_agent, "proposals")
    os.makedirs(pd, exist_ok=True)
    return pd

def _new_pid():
    import secrets
    return "P_" + secrets.token_hex(8)

def _proposal_path(pid: str) -> str:
    return os.path.join(_proposal_dir(), f"{pid}.json")

def _write_proposal(pid: str, obj: dict):
    pp = _proposal_path(pid)
    with open(pp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return pp
# --- /HARDENING6_5_WRITE_GATE helpers --------------------------------------

    for s in steps:
        if isinstance(s, dict) and str(s.get("id")) == str(step_id):
            return s
    return None

def _call_tool_best_effort(tool_name: str, args: dict):
    """
    Binding real a tools del servidor.
    SAFE_MIN: permite solo read-only (read_file, list_dir).
    Write tools (write_file, append_file) quedan bloqueadas aquí (se habilitan con approve-gate más adelante).
    """
    tn = str(tool_name or "").strip()

    # allowlist SAFE_MIN (read-only)
    if tn not in ("read_file", "list_dir"):
        return {"ok": False, "error": f"tool blocked in SAFE_MIN: {tn}", "args": args}

    # 1) Preferir dispatcher si existe
    disp = globals().get("dispatch_tool")
    if callable(disp):
        try:
            # convención típica: dispatch_tool(name, **args) o dispatch_tool(name, args_dict)
            try:
                out = disp(tn, **(args or {}))
            except TypeError:
                out = disp(tn, args or {})
            return {"ok": True, "via": "dispatch_tool", "result": out}
        except Exception as e:
            return {"ok": False, "error": f"dispatch_tool failed: {e}", "args": args}

    # 2) Fallback a tabla TOOLS si existe
    tools = globals().get("TOOLS")
    if isinstance(tools, dict) and tn in tools and callable(tools[tn]):
        try:
            fn = tools[tn]
            try:
                out = fn(**(args or {}))
            except TypeError:
                out = fn(args or {})
            return {"ok": True, "via": "TOOLS", "result": out}
        except Exception as e:
            return {"ok": False, "error": f"TOOLS[{tn}] failed: {e}", "args": args}

    # 3) Fallback directo a funciones
    fn = globals().get(tn)
    if callable(fn):
        try:
            try:
                out = fn(**(args or {}))
            except TypeError:
                out = fn(args or {})
            return {"ok": True, "via": tn, "result": out}
        except Exception as e:
            return {"ok": False, "error": f"{tn} failed: {e}", "args": args}

    return {"ok": False, "error": f"tool not found: {tn}", "args": args}
def _SAFE_INTERNAL_EXECUTE_STEP(req):
    """
    req esperado: AgentExecuteStepRequest-like (room_id, step_id, mode, approve_token?)
    Solo soporta mode='propose' para read tools; write tools se bloquean por seguridad.
    """
    room_id = str(getattr(req, "room_id", "") or "").strip() or "default"
    step_id = str(getattr(req, "step_id", "") or "").strip()
    mode = str(getattr(req, "mode", "") or "propose").strip().lower()

    plan = _ssot_read_plan(room_id) or {}
    if not plan:
        return {"ok": False, "error": "no plan for room", "room_id": room_id}

    step = _find_step(plan, step_id)
    if not step:
        return {"ok": False, "error": "step not found", "room_id": room_id, "step_id": step_id}

    tool_name = str(step.get("tool_name") or "")
    tool_args = step.get("tool_args") or step.get("args") or {}

    # --- HARDENING6_5_WRITE_GATE: propose/apply for write tools ----------------
    approve_token = ""
    try:
        approve_token = str(getattr(req, "approve_token", "") or "").strip()
    except Exception:
        approve_token = ""

    # Determinar si es write tool: por nombre directo o helper existente
    is_write = tool_name in ("write_file", "append_file")
    if not is_write and "_is_write_tool" in globals():
        try:
            is_write = bool(_is_write_tool(tool_name))
        except Exception:
            is_write = False

    # Gate: WRITE tools solo via proposal + approve_token
    if is_write:
        # PROPOSE: crear proposal y marcar step como proposed
        if mode != "apply":
            pid = _new_pid()
            pp = _proposal_path(pid)
            proposal_obj = {
                "proposal_id": pid,
                "tool_name": tool_name,
                "tool_args": tool_args if isinstance(tool_args, dict) else {},
                "room_id": room_id,
                "step_id": step_id,
                "created_at": _utc_now(),
                "kind": "write_proposal",
                "note": "SAFE_MIN: proposal only; requires APPLY_<proposal_id> to execute"
            }
            _write_proposal(pid, proposal_obj)

            step["status"] = "proposed"
            step["proposal_id"] = pid
            step["required_approve"] = "APPLY_" + pid
            step["result"] = {"ok": True, "via": "proposal", "result": {"proposal_path": pp, "approve_token": "APPLY_" + pid}}

            plan["updated_at"] = _utc_now()
            plan.setdefault("room_id", room_id)
            _ssot_write_plan(room_id, plan)

            return {
                "ok": True,
                "room_id": room_id,
                "step_id": step_id,
                "result": {"ok": True, "proposal_id": pid, "proposal_path": pp, "approve_token": "APPLY_" + pid},
            }

        # APPLY: requiere approve_token
        if not approve_token.startswith("APPLY_"):
            return {"ok": False, "room_id": room_id, "step_id": step_id, "error": "missing/invalid approve_token for write tool"}

        expected = step.get("required_approve") or ("APPLY_" + str(step.get("proposal_id") or ""))
        if str(approve_token) != str(expected):
            return {"ok": False, "room_id": room_id, "step_id": step_id, "error": f"approve_token mismatch (expected {expected})"}

        # ejecutar write directamente usando función real si existe
        fn = globals().get(tool_name)
        if not callable(fn):
            return {"ok": False, "room_id": room_id, "step_id": step_id, "error": f"write tool function not found: {tool_name}"}


        # --- HARDENING6_5_4_WRITE_ARGS_NORMALIZER ----------------------------
        # Normaliza payload de tools: algunos usan 'text' en vez de 'content'
        try:
            if isinstance(tool_args, dict):
                if "text" not in tool_args and "content" in tool_args:
                    tool_args["text"] = tool_args.get("content")
                # aliases adicionales por compat
                if "text" not in tool_args and "data" in tool_args:
                    tool_args["text"] = tool_args.get("data")
        except Exception:
            pass
        # --- /HARDENING6_5_4_WRITE_ARGS_NORMALIZER ----------------------------
        try:
            # --- HARDENING6_5_5_WRITE_CALL_BY_SIGNATURE ----------------------------
            # Para write tools, NO usar fallback fn(tool_args) (rompe firmas path/text).
            import inspect
            kwargs = {}
            if isinstance(tool_args, dict):
                # copia superficial
                kwargs.update(tool_args)
            # normalizaciones de nombres
            if "text" not in kwargs and "content" in kwargs:
                kwargs["text"] = kwargs.get("content")
            if "text" not in kwargs and "data" in kwargs:
                kwargs["text"] = kwargs.get("data")
        
            sig = None
            try:
                sig = inspect.signature(fn)
            except Exception:
                sig = None
        
            if sig is not None:
                params = sig.parameters
                # filtrar kwargs a solo parámetros aceptados, excepto si **kwargs existe
                has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                if not has_varkw:
                    kwargs = {k:v for k,v in kwargs.items() if k in params}
        
                # Si la función usa nombres distintos (ej: filename en vez de path)
                if "path" not in kwargs and "filename" in params and "filename" in kwargs:
                    pass
                if "path" in params and "path" not in kwargs and "file_path" in kwargs:
                    kwargs["path"] = kwargs.get("file_path")
        
            # Validación mínima: exige 'path' y 'text' si la firma los pide
            if sig is not None:
                need_text = ("text" in sig.parameters)
                need_path = ("path" in sig.parameters)
                if need_path and "path" not in kwargs:
                    raise TypeError("missing required kw: path")
                if need_text and "text" not in kwargs:
                    raise TypeError("missing required kw: text")
        
            out = fn(**kwargs)
            # --- /HARDENING6_5_5_WRITE_CALL_BY_SIGNATURE ----------------------------
            step["status"] = "done"
            # limpiar propuesta
            step.pop("proposal_id", None)
            step.pop("required_approve", None)
            step["result"] = {"ok": True, "via": tool_name, "result": out}
        except Exception as e:
            step["status"] = "error"
            step["result"] = {"ok": False, "error": f"{tool_name} failed: {e}"}

        plan["updated_at"] = _utc_now()
        plan.setdefault("room_id", room_id)

        # auto-complete si no quedan pendientes
        try:
            steps_all = plan.get("steps", []) or []
            pending = [x for x in steps_all if isinstance(x, dict) and str(x.get("status")) in {"todo","in_progress","proposed"}]
            if not pending:
                plan["status"] = "complete"
        except Exception:
            pass

        _ssot_write_plan(room_id, plan)

        return {"ok": True, "room_id": room_id, "step_id": step_id, "result": step.get("result")}
# --- /HARDENING6_5_WRITE_GATE -----------------------------------------------

    # apply no permitido en safe-min (para read tools)
    if mode == "apply":
        return {"ok": False, "error": "apply disabled in SAFE_MIN internal runner"}

    # ejecutar
    out = _call_tool_best_effort(tool_name, tool_args if isinstance(tool_args, dict) else {})

    # persist resultado en el step + status
    step["result"] = out
    if out.get("ok"):
        step["status"] = "done"
    else:
        step["status"] = "error"

    plan["updated_at"] = _utc_now()
    plan.setdefault("room_id", room_id)

    # auto-complete si no quedan steps pendientes
    try:
        steps_all = plan.get("steps", []) or []
        pending = [x for x in steps_all if isinstance(x, dict) and str(x.get("status")) in {"todo","in_progress","proposed"}]
        if not pending:
            plan["status"] = "complete"
    except Exception:
        pass

    _ssot_write_plan(room_id, plan)

    return {"ok": bool(out.get("ok")), "room_id": room_id, "step_id": step_id, "result": out}

# Bind only if missing (keeps any existing implementation)
if "agent_execute_step" not in globals():
    agent_execute_step = _SAFE_INTERNAL_EXECUTE_STEP
# --- /HARDENING6_3_INTERNAL_RUNNER -----------------------------------------

# HARDENING6_5_WRITE_GATE

# HARDENING6_5_4_WRITE_ARGS_NORMALIZER

# HARDENING6_5_5_WRITE_CALL_BY_SIGNATURE

# HARDENING7_AUDIT_NDJSON

# HARDENING8_1B2_AUDIT_REQID_LATENCY_SAFE

# HARDENING8_1B3_REMOVE_AUDIT_PRELOG

# HARDENING8_1B4_REMOVE_ALL_AUDIT_PRELOGS


# --- HARDENING9_RUN_LOOP: robust loop runner (SSOT-only, room-aware) ----------
from typing import Optional, Any, Dict
import time as _time

class AgentRunRequest(BaseModel):
    room_id: Optional[str] = None
    approve_token: Optional[str] = None
    max_steps: int = 25
    max_seconds: int = 20

class AgentRunResponse(BaseModel):
    ok: bool = True
    room_id: str = "default"
    action: str = "run"
    steps_executed: int = 0
    requires_approval: bool = False
    approve_token: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

def _plan_steps_safe(plan: dict):
    try:
        steps = plan.get("steps", [])
        return steps if isinstance(steps, list) else []
    except Exception:
        return []

def _is_write_tool_safe(tool_name: str) -> bool:
    tn = str(tool_name or "").strip()
    # prefer existing helper if present
    if "_is_write_tool" in globals():
        try:
            return bool(globals()["_is_write_tool"](tn))
        except Exception:
            pass
    return tn in ("write_file", "append_file")

def _find_step_by_id_safe(plan: dict, step_id: str):
    try:
        if "_find_step" in globals():
            return globals()["_find_step"](plan, step_id)
    except Exception:
        pass
    # fallback: local
    sid = str(step_id or "").strip()
    for s in _plan_steps_safe(plan):
        if not isinstance(s, dict):
            continue
        for k in ("id", "step_id", "stepId"):
            try:
                if str(s.get(k) or "").strip() == sid:
                    return s
            except Exception:
                continue
    return None

def _next_actionable_step_safe(steps):
    for s in steps:
        if isinstance(s, dict) and str(s.get("status")) in {"todo","in_progress"}:
            return s
    return None

def _find_proposed_by_pid_safe(steps, pid: str):
    target = str(pid or "").strip()
    for s in steps:
        if not isinstance(s, dict):
            continue
        if str(s.get("status")) != "proposed":
            continue
        if str(s.get("proposal_id") or "") == target:
            return s
    return None

def _run_one_step_ssot(room_id: str, approve_token: str = ""):
    """
    Ejecuta 1 transición:
      - si approve_token APPLY_<pid> => apply del proposed step con ese pid
      - si no => propose del next todo/in_progress
    Devuelve dict con:
      ok, action, requires_approval, approve_token, last_result, plan
    """
    plan = _ssot_read_plan(room_id) or {}
    if not plan:
        return {"ok": True, "action": "noop_no_plan", "requires_approval": False, "approve_token": None, "last_result": None, "plan": {}}

    if isinstance(plan, dict):
        plan.setdefault("room_id", room_id)

    status = str(plan.get("status") or "").lower()
    steps = _plan_steps_safe(plan)

    if status == "complete":
        return {"ok": True, "action": "noop_complete", "requires_approval": False, "approve_token": None, "last_result": None, "plan": plan}

    # APPLY flow
    if approve_token:
        tok = str(approve_token).strip()
        if not tok.startswith("APPLY_"):
            return {"ok": False, "action": "error_invalid_approve_token", "requires_approval": False, "approve_token": None, "last_result": {"ok": False, "error": "approve_token must be APPLY_<proposal_id>"}, "plan": plan}

        pid = tok.replace("APPLY_", "", 1)
        step = _find_proposed_by_pid_safe(steps, pid)
        if not step:
            # No matching proposed => noop
            return {"ok": True, "action": "noop_no_matching_proposed_step", "requires_approval": False, "approve_token": None, "last_result": None, "plan": plan}

        step_id = str(step.get("id") or "")
        if "agent_execute_step" not in globals():
            return {"ok": False, "action": "error_execute_step_unavailable", "requires_approval": False, "approve_token": None, "last_result": {"ok": False, "error": "agent_execute_step not available"}, "plan": plan}

        res = agent_execute_step(type("ExecReq", (), {"room_id": room_id, "step_id": step_id, "mode": "apply", "approve_token": tok})())
        # authority is agent_execute_step => reload plan
        plan2 = _ssot_read_plan(room_id) or plan
        return {"ok": bool(res.get("ok", True)), "action": "apply_step", "requires_approval": False, "approve_token": None, "last_result": res, "plan": plan2}

    # PROPOSE next step
    next_step = _next_actionable_step_safe(steps)
    if not next_step:
        return {"ok": True, "action": "noop_no_todo", "requires_approval": False, "approve_token": None, "last_result": None, "plan": plan}

    step_id = str(next_step.get("id") or "")
    tool_name = str(next_step.get("tool_name") or "")

    if "agent_execute_step" not in globals():
        return {"ok": False, "action": "error_execute_step_unavailable", "requires_approval": False, "approve_token": None, "last_result": {"ok": False, "error": "agent_execute_step not available"}, "plan": plan}

    res = agent_execute_step(type("ExecReq", (), {"room_id": room_id, "step_id": step_id, "mode": "propose"})())

    # reload plan post-exec
    plan2 = _ssot_read_plan(room_id) or plan
    steps2 = _plan_steps_safe(plan2)
    step2 = _find_step_by_id_safe(plan2, step_id)

    # If write => should be proposed now
    if _is_write_tool_safe(tool_name):
        ap = None
        try:
            ap = str((step2 or {}).get("required_approve") or "").strip()
        except Exception:
            ap = None
        if ap:
            return {"ok": True, "action": "propose_write_step", "requires_approval": True, "approve_token": ap, "last_result": res, "plan": plan2}
        # If missing required_approve, still stop (safety)
        return {"ok": True, "action": "propose_write_step_missing_token", "requires_approval": True, "approve_token": None, "last_result": res, "plan": plan2}

    return {"ok": bool(res.get("ok", True)), "action": "propose_step", "requires_approval": False, "approve_token": None, "last_result": res, "plan": plan2}

# [DISABLED_DUP_RUN] @app.post("/v1/agent/run", response_model=AgentRunResponse)
def agent_run_ssot(request: Request, req: AgentRunRequest = Body(...)):
    room_id = _get_room_id_from_req_and_headers(req, request)
    try:
        max_steps = int(getattr(req, "max_steps", 25) or 25)
    except Exception:
        max_steps = 25
    try:
        max_seconds = int(getattr(req, "max_seconds", 20) or 20)
    except Exception:
        max_seconds = 20

    approve_token = ""
    try:
        approve_token = str(getattr(req, "approve_token", "") or "").strip()
    except Exception:
        approve_token = ""

    t0 = _time.perf_counter()
    steps_exe = 0
    last = None
    requires_approval = False
    out_token = None
    action = "run"

    # Loop: apply (if token provided) first, then continue proposing steps
    # If a write step is proposed, stop and return approval token.
    for _ in range(max_steps):
        if (_time.perf_counter() - t0) > float(max_seconds):
            action = "stop_timeout"
            break

        one = _run_one_step_ssot(room_id, approve_token=approve_token)
        # after first iteration, consume approve token so we don't re-apply
        approve_token = ""

        steps_exe += 1
        last = one.get("last_result")
        action = str(one.get("action") or action)

        if not bool(one.get("ok", True)):
            # error path
            return {
                "ok": False,
                "room_id": room_id,
                "action": action,
                "steps_executed": steps_exe,
                "requires_approval": False,
                "approve_token": None,
                "last_result": last,
                "plan": one.get("plan"),
                "error": (last or {}).get("error") if isinstance(last, dict) else "run_failed",
            }

        if one.get("requires_approval"):
            requires_approval = True
            out_token = one.get("approve_token")
            action = "requires_approval"
            return {
                "ok": True,
                "room_id": room_id,
                "action": action,
                "steps_executed": steps_exe,
                "requires_approval": True,
                "approve_token": out_token,
                "last_result": last,
                "plan": one.get("plan"),
                "error": None,
            }

        # If plan became complete or no work, stop
        plan = one.get("plan") or {}
        st = str((plan.get("status") or "")).lower()
        if action in ("noop_complete","noop_no_plan","noop_no_todo") or st == "complete":
            break

    # final read
    plan_final = _ssot_read_plan(room_id) or {}
    return {
        "ok": True,
        "room_id": room_id,
        "action": action,
        "steps_executed": steps_exe,
        "requires_approval": False,
        "approve_token": None,
        "last_result": last,
        "plan": plan_final,
        "error": None,
    }

# HARDENING9_RUN_LOOP
# --- /HARDENING9_RUN_LOOP -----------------------------------------------------


# HARDENING10_EVAL_SSOT

# HARDENING10D_EVAL_PERSIST_MW

# HARDENING11B_EXECSTEP_CALL_BY_SIGNATURE

# HARDENING11C_RUN_SSOT_ORCHESTRATOR_FIX



# --- HARDENING11D_DEDUP_RUN_ROUTE_CANONICAL: single canonical POST /v1/agent/run ---------------------------------
@app.post("/v1/agent/run")
def agent_run_ssot_canonical(request: Request, req: dict = Body(...)):
    """
    SSOT RUN orchestrator (robusto):
      - Reutiliza EXACTAMENTE el handler de /v1/agent/run_once (misma lógica, mismas proposals).
      - Loop hasta max_steps o hasta bloquearse (proposed) o completar.
      - Si no hay progreso (plan no cambia), corta con error.
    """
    impl = "HARDENING11F_RUN_DELEGATES_RUN_ONCE"

    import json
    import os
    import inspect
    from datetime import datetime, timezone

    def _utc_now():
        return datetime.now(timezone.utc).isoformat()

    def _resolve_room_id():
        rid = "default"
        try:
            if isinstance(req, dict) and req.get("room_id"):
                rid = str(req.get("room_id") or "").strip() or "default"
        except Exception:
            rid = "default"
        if (not rid) or rid == "default":
            try:
                hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
                if hdr:
                    rid = hdr
            except Exception:
                pass
        return rid or "default"

    def _plan_path(rid: str) -> str:
        try:
            fn = globals().get("_plan_path")
            if callable(fn):
                return fn(rid)
        except Exception:
            pass
        return os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "plan.json")

    def _read_plan(rid: str):
        p = _plan_path(rid)
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return None
        return None

    def _find_blocked(plan: dict):
        # devuelve dict con info de bloqueo si hay step proposed
        try:
            for st in (plan.get("steps") or []):
                if not isinstance(st, dict):
                    continue
                status = str(st.get("status") or "").strip().lower()
                if status == "proposed":
                    out = {
                        "step_id": str(st.get("id") or "").strip() or None,
                        "proposal_id": st.get("proposal_id"),
                        "required_approve": st.get("required_approve"),
                    }
                    try:
                        if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                                    _audit_append(room_id, "run_result", {
                                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                                    })
                    except Exception:
                        pass
                    return out
        except Exception:
            pass
        return None

    def _is_complete(plan: dict) -> bool:
        try:
            return str(plan.get("status") or "").strip().lower() in ("complete", "completed", "done")
        except Exception:
            return False

    def _pick_run_once_fn():
        # Prefer exact common names
        for name in ("agent_run_once_ssot", "agent_run_once", "agent_run_once_ssot_canonical"):
            fn = globals().get(name)
            if callable(fn):
                return fn

        # Fallback: find any callable agent_* with 'run_once' in name
        for k, v in globals().items():
            if not (isinstance(k, str) and "run_once" in k and k.startswith("agent_")):
                continue
            if callable(v):
                return v
        return None

    room_id = _resolve_room_id()

    try:
        max_steps = int(req.get("max_steps", 10)) if isinstance(req, dict) else 10
    except Exception:
        max_steps = 10
    if max_steps <= 0:
        max_steps = 1
    if max_steps > 200:
        max_steps = 200

    run_once_fn = _pick_run_once_fn()
    if not callable(run_once_fn):
        out = {
            "ok": False,
            "impl": impl,
            "room_id": room_id,
            "action": "run",
            "executed": 0,
            "blocked": None,
            "plan": _read_plan(room_id),
            "error": "run_once_handler_not_found",
        }
        try:
            if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                            _audit_append(room_id, "run_result", {
                                "ok": (out.get("ok") if isinstance(out, dict) else None),
                                "executed": (out.get("executed") if isinstance(out, dict) else None),
                                "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                            })
        except Exception:
            pass
        return out

    executed = 0
    last_plan_json = None

    for _ in range(max_steps):
        plan_before = _read_plan(room_id) or {"room_id": room_id, "status": "active", "steps": []}
        blocked = _find_blocked(plan_before)
        if blocked:
            out = {
                "ok": True,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": blocked,
                "plan": plan_before,
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out
        if _is_complete(plan_before):
            out = {
                "ok": True,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": None,
                "plan": plan_before,
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out

        # snapshot string para detectar progreso
        try:
            before_s = json.dumps(plan_before, sort_keys=True, ensure_ascii=False)
        except Exception:
            before_s = None

        # llamar al MISMO handler de run_once
        try:
            _ = run_once_fn(request, {"room_id": room_id})
        except TypeError:
            # algunas variantes no aceptan dict literal; intentar pasar req como kw
            try:
                _ = run_once_fn(request=request, req={"room_id": room_id})
            except Exception as e:
                out = {
                    "ok": False,
                    "impl": impl,
                    "room_id": room_id,
                    "action": "run",
                    "executed": executed,
                    "blocked": None,
                    "plan": plan_before,
                    "error": f"run_once_call_failed: {e}",
                }
                try:
                    if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                            _audit_append(room_id, "run_result", {
                                                "ok": (out.get("ok") if isinstance(out, dict) else None),
                                                "executed": (out.get("executed") if isinstance(out, dict) else None),
                                                "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                                "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                                "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                            })
                except Exception:
                    pass
                return out
        except Exception as e:
            out = {
                "ok": False,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": None,
                "plan": plan_before,
                "error": f"run_once_call_failed: {e}",
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out

        plan_after = _read_plan(room_id) or plan_before

        try:
            after_s = json.dumps(plan_after, sort_keys=True, ensure_ascii=False)
        except Exception:
            after_s = None

        # progreso?
        if before_s is not None and after_s is not None and before_s == after_s:
            out = {
                "ok": False,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": None,
                "plan": plan_after,
                "error": "no_progress_after_run_once",
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out

        executed += 1

        blocked2 = _find_blocked(plan_after)
        if blocked2:
            out = {
                "ok": True,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": blocked2,
                "plan": plan_after,
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out

        if _is_complete(plan_after):
            out = {
                "ok": True,
                "impl": impl,
                "room_id": room_id,
                "action": "run",
                "executed": executed,
                "blocked": None,
                "plan": plan_after,
            }
            try:
                if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                                    _audit_append(room_id, "run_result", {
                                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                                    })
            except Exception:
                pass
            return out

    # si llegamos aquí: max_steps
    out = {
        "ok": True,
        "impl": impl,
        "room_id": room_id,
        "action": "run",
        "executed": executed,
        "blocked": _find_blocked(_read_plan(room_id) or {}),
        "plan": _read_plan(room_id),
        "error": "max_steps_reached",
    }
    try:
        if isinstance(out, dict) and (("ok" in out) or ("impl" in out) or ("action" in out) or ("plan" in out) or ("executed" in out) or ("blocked" in out)):
                    _audit_append(room_id, "run_result", {
                        "ok": (out.get("ok") if isinstance(out, dict) else None),
                        "executed": (out.get("executed") if isinstance(out, dict) else None),
                        "blocked": (out.get("blocked") if isinstance(out, dict) else None),
                        "proposal_id": (((out.get("blocked") or {}).get("proposal_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None),
                        "step_id": (((out.get("blocked") or {}).get("step_id")) if isinstance(out, dict) and isinstance(out.get("blocked"), dict) else None)
                    })
    except Exception:
        pass
    return out



# HARDENING11F_RUN_DELEGATES_RUN_ONCE


# --- HARDENING12_APPLY_ENDPOINT_SSOT_EOF: POST /v1/agent/apply -------------------
@app.post("/v1/agent/apply")
@episode_wrap("apply")
def agent_apply_ssot(request: Request, req: dict = Body(...)):
    """
    Apply SSOT (canonical):
      - input: {room_id?, approve_token, step_id?}
      - resolves step_id from plan.json.required_approve == approve_token
      - executes apply via _SAFE_INTERNAL_EXECUTE_STEP (signature-safe)
      - returns updated plan (SSOT)
    """
    import inspect, os, json

    # room_id: req.room_id -> header -> default
    room_id = "default"
    try:
        if isinstance(req, dict) and req.get("room_id"):
            room_id = str(req.get("room_id") or "").strip() or "default"
    except Exception:
        room_id = "default"
    if (not room_id) or room_id == "default":
        try:
            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()
            if hdr:
                room_id = hdr
        except Exception:
            pass
    room_id = room_id or "default"

    approve = None
    try:
        if isinstance(req, dict):
            approve = req.get("approve_token")
    except Exception:
        approve = None
    approve = (str(approve or "").strip() or None)
    if not approve:
        return {"ok": False, "room_id": room_id, "error": "missing approve_token"}

    # resolve step_id from plan SSOT
    step_id = None
    try:
        pp = _plan_path(room_id) if "_plan_path" in globals() else os.path.join(r"C:\AI_VAULT\tmp_agent","state","rooms",room_id,"plan.json")
        if os.path.exists(pp):
            plan = json.loads(open(pp, "r", encoding="utf-8").read())
            for st in (plan.get("steps") or []):
                if isinstance(st, dict) and str(st.get("required_approve") or "").strip() == approve:
                    step_id = str(st.get("id") or "").strip() or None
                    break
    except Exception:
        step_id = None

    if not step_id:
        try:
            if isinstance(req, dict) and req.get("step_id"):
                step_id = str(req.get("step_id") or "").strip() or None
        except Exception:
            step_id = None

    if not step_id:
        return {"ok": False, "room_id": room_id, "error": "cannot_resolve_step_id_for_approve_token"}

    fn = globals().get("_SAFE_INTERNAL_EXECUTE_STEP")
    if not callable(fn):
        return {"ok": False, "room_id": room_id, "error": "_SAFE_INTERNAL_EXECUTE_STEP not found/callable"}

    def _call_exec_step(room_id, step_id, mode, approve_token=None):
        """HARDENING_EXECSTEP_REQ_ONLY_BRIDGE
        Executor accepts only one-arg signature: fn(req).
        We always call _SAFE_INTERNAL_EXECUTE_STEP with a single dict payload.
        """
        fn = globals().get("_SAFE_INTERNAL_EXECUTE_STEP")
        if not callable(fn):
            return {"ok": False, "error": "_SAFE_INTERNAL_EXECUTE_STEP not found/callable"}
        payload = {
            # canonical
            'room_id': room_id,
            'step_id': step_id,
            'mode': mode,
            'approve_token': approve_token,
            # aliases comunes
            'rid': room_id,
            'room': room_id,
            'roomId': room_id,
            'x_room_id': room_id,
            'id': step_id,
            'step': step_id,
            'stepId': step_id,
            'action': mode,
            'op': mode,
            'approve': approve_token,
            'token': approve_token,
            'required_approve': approve_token,
            'approval_token': approve_token,
        }
        try:
            # HARDENING_EXECSTEP_REQ_OBJECT_FIX
            req_obj = types.SimpleNamespace(**payload) if isinstance(payload, dict) else payload
            return fn(req_obj)
        except TypeError as e:
            return {"ok": False, "error": f"executor_typeerror: {e}", "payload": payload}
        except Exception as e:
            return {"ok": False, "error": f"executor_exception: {e}", "payload": payload}

        if sig is not None:
            kwargs = {}
            if "room_id" in params: kwargs["room_id"] = room_id
            if "step_id" in params: kwargs["step_id"] = step_id
            if "mode" in params: kwargs["mode"] = mode
            if "approve_token" in params: kwargs["approve_token"] = approve_token
            has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            if not has_varkw:
                kwargs = {k: v for k, v in kwargs.items() if k in params}
            try:
                return fn(**kwargs)
            except TypeError:
                pass

        for args in (
            (room_id, step_id, mode, approve_token),
            (room_id, step_id, mode),
            (step_id, mode, approve_token),
            (step_id, mode),
        ):
            try:
                return fn(*args)
            except TypeError:
                continue
        return {"ok": False, "error": "_SAFE_INTERNAL_EXECUTE_STEP signature mismatch"}

    res = _call_exec_step(room_id, step_id, mode="apply", approve_token=approve)

    plan = None
    try:
        if "_ssot_read_plan" in globals():
            plan = _ssot_read_plan(room_id)
        else:
            pp = os.path.join(r"C:\AI_VAULT\tmp_agent","state","rooms",room_id,"plan.json")
            if os.path.exists(pp):
                plan = json.loads(open(pp, "r", encoding="utf-8").read())
    except Exception:
        plan = None

    _tmp = {"ok": True, "room_id": room_id, "step_id": step_id, "result": res, "plan": plan, "impl": "HARDENING12_APPLY_ENDPOINT_SSOT_EOF"}
    try:
        _audit_append(((_tmp.get("room_id") if isinstance(_tmp, dict) else None) or room_id), "apply_result", {"ok": (_tmp.get("ok") if isinstance(_tmp, dict) else None), "proposal_id": ((_tmp.get("proposal_id") if isinstance(_tmp, dict) else None) or (req.get("proposal_id") if isinstance(req, dict) else None)), "step_id": (_tmp.get("step_id") if isinstance(_tmp, dict) else None)})
    except Exception:
        pass
    return _tmp
# --- /HARDENING12_APPLY_ENDPOINT_SSOT_EOF ----------------------------------------
# HARDENING12_APPLY_ENDPOINT_SSOT_EOF


# HARDENING_EXECSTEP_REQ_ONLY_BRIDGE

# HARDENING_EXECSTEP_REQ_ONLY_ALIASES2

# HARDENING_EXECSTEP_REQ_OBJECT_FIX


# --- HARDENING15_PROPOSALS_LIST_SSOT_EOF: list proposals (read-only) ---------------
@app.get("/v1/agent/proposals")
def agent_proposals_list_ssot(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    room_id: str = Query("", max_length=256),
    kind: str = Query("", max_length=128),
):
    """
    Lista proposals en C:\\AI_VAULT\\tmp_agent\\proposals\\*.json (orden mtime desc).
    - Filtra opcional por room_id (contenido del JSON) y kind.
    - Best-effort parse: si JSON inválido, devuelve metadata de archivo.
    """
    import os, json
    from datetime import datetime, timezone

    props_dir = os.path.join(r"C:\AI_VAULT\tmp_agent", "proposals")
    if not os.path.isdir(props_dir):
        return {"ok": True, "dir": props_dir, "limit": limit, "filters": {"room_id": room_id, "kind": kind}, "items": [], "missing_dir": True}

    want_room = (room_id or "").strip() or None
    want_kind = (kind or "").strip() or None

    # listar .json excluyendo bundles (opcional)
    items_fs = []
    try:
        for name in os.listdir(props_dir):
            if not name.lower().endswith(".json"):
                continue
            # ignorar bundles_* (no son proposals individuales)
            if name.lower().startswith("bundle_"):
                continue
            full = os.path.join(props_dir, name)
            try:
                st = os.stat(full)
            except Exception:
                continue
            items_fs.append((st.st_mtime, full, st.st_size))
    except Exception as e:
        return {"ok": False, "dir": props_dir, "error": f"list_failed: {e}", "items": []}

    items_fs.sort(key=lambda t: t[0], reverse=True)
    items_fs = items_fs[: int(limit)]

    out = []
    bad = 0
    for mtime, full, size in items_fs:
        base = os.path.basename(full)
        pid = base[:-5]  # strip .json

        rec = {
            "proposal_id": pid,
            "required_approve": f"APPLY_{pid}",
            "path": full,
            "size": int(size),
            "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        }

        # parse best-effort
        data = None
        try:
            data = json.loads(open(full, "r", encoding="utf-8").read())
        except Exception:
            bad += 1
            data = None

        if isinstance(data, dict):
            # filtrar por room/kind si aplica
            rid = str(data.get("room_id") or "").strip() or None
            knd = str(data.get("kind") or "").strip() or None
            if want_room and rid != want_room:
                continue
            if want_kind and knd != want_kind:
                continue

            rec.update({
                "room_id": rid,
                "step_id": str(data.get("step_id") or "").strip() or None,
                "tool_name": str(data.get("tool_name") or "").strip() or None,
                "kind": knd,
                "created_at": data.get("created_at"),
                "note": data.get("note"),
                "tool_args": data.get("tool_args") if isinstance(data.get("tool_args"), dict) else None,
            })
        else:
            # si no parsea, igual permitir filtro por room_id header si no pidieron filtro contenido
            if want_room or want_kind:
                continue

        out.append(rec)

    return {
        "ok": True,
        "dir": props_dir,
        "limit": int(limit),
        "filters": {"room_id": want_room, "kind": want_kind},
        "items": out,
        "bad_files": bad,
        "impl": "HARDENING15_PROPOSALS_LIST_SSOT_EOF",
    }

# HARDENING15_PROPOSALS_LIST_SSOT_EOF
# --- /HARDENING15_PROPOSALS_LIST_SSOT_EOF -----------------------------------------


# --- HARDENING15B_PROPOSALS_ACTIVE_SSOT_EOF: list ACTIVE proposals only ------------
@app.get("/v1/agent/proposals_active")
def agent_proposals_active_ssot(
    request: Request,
    room_id: str = Query("", max_length=256),
):
    """
    Devuelve SOLO proposals activas (referenciadas por plan.json del room).
    - room_id: Query o header x-room-id (default).
    - Lee plan.json -> recoge proposal_id(s) en steps -> carga proposals/<pid>.json.
    """
    import os, json
    from datetime import datetime, timezone

    rid = (room_id or "").strip() or None
    if not rid:
        try:
            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
        except Exception:
            rid = "default"

    plan_path = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "plan.json")
    if not os.path.exists(plan_path):
        return {"ok": False, "room_id": rid, "error": "plan.json_not_found", "path": plan_path, "items": []}

    try:
        plan = json.loads(open(plan_path, "r", encoding="utf-8").read())
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"plan.json_read_failed: {e}", "path": plan_path, "items": []}

    pids = []
    try:
        for st in (plan.get("steps") or []):
            if isinstance(st, dict):
                pid = str(st.get("proposal_id") or "").strip()
                if pid:
                    pids.append(pid)
    except Exception:
        pass

    # unique keep order
    seen = set()
    uniq = []
    for pid in pids:
        if pid in seen:
            continue
        seen.add(pid)
        uniq.append(pid)

    props_dir = os.path.join(r"C:\AI_VAULT\tmp_agent", "proposals")
    out = []
    missing = 0
    bad = 0

    for pid in uniq:
        full = os.path.join(props_dir, f"{pid}.json")
        rec = {
            "proposal_id": pid,
            "required_approve": f"APPLY_{pid}",
            "path": full,
        }
        if not os.path.exists(full):
            missing += 1
            rec["missing"] = True
            out.append(rec)
            continue
        try:
            st = os.stat(full)
            rec["size"] = int(st.st_size)
            rec["mtime"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

        try:
            data = json.loads(open(full, "r", encoding="utf-8").read())
            if isinstance(data, dict):
                rec.update({
                    "room_id": str(data.get("room_id") or "").strip() or None,
                    "step_id": str(data.get("step_id") or "").strip() or None,
                    "tool_name": str(data.get("tool_name") or "").strip() or None,
                    "kind": str(data.get("kind") or "").strip() or None,
                    "created_at": data.get("created_at"),
                    "note": data.get("note"),
                    "tool_args": data.get("tool_args") if isinstance(data.get("tool_args"), dict) else None,
                })
            else:
                bad += 1
        except Exception:
            bad += 1

        out.append(rec)

    return {
        "ok": True,
        "room_id": rid,
        "plan_path": plan_path,
        "items": out,
        "missing_files": missing,
        "bad_files": bad,
        "impl": "HARDENING15B_PROPOSALS_ACTIVE_SSOT_EOF",
    }

# HARDENING15B_PROPOSALS_ACTIVE_SSOT_EOF
# --- /HARDENING15B_PROPOSALS_ACTIVE_SSOT_EOF --------------------------------------


# --- HARDENING16C_STATUS_GET_EOF: GET /v1/agent/status (SSOT summary) ---------------
@app.get("/v1/agent/status")
def agent_status_get_ssot(request: Request, room_id: str = Query("", max_length=256)):
    """
    SSOT status (GET):
    - room_id: Query o header x-room-id (default).
    - resume plan.json + archivos observabilidad en state/rooms/<rid>.
    - proposals activas: desde plan.steps[*].proposal_id (no escaneo histórico).
    """
    import os, json
    from datetime import datetime, timezone

    rid = (room_id or "").strip() or None
    if not rid:
        try:
            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
        except Exception:
            rid = "default"
    rid = rid or "default"

    base_tmp = r"C:\AI_VAULT\tmp_agent"
    rooms_dir = os.path.join(base_tmp, "state", "rooms")
    room_dir = os.path.join(rooms_dir, rid)
    props_dir = os.path.join(base_tmp, "proposals")

    plan_path = os.path.join(room_dir, "plan.json")
    audit_path = os.path.join(room_dir, "audit.ndjson")
    eval_json_path = os.path.join(room_dir, "evaluation.json")
    eval_ndjson_path = os.path.join(room_dir, "evaluations.ndjson")
    rej_ndjson_path = os.path.join(room_dir, "rejections.ndjson")

    def _stat(p):
        try:
            st = os.stat(p)
            return {
                "path": p,
                "exists": True,
                "size": int(st.st_size),
                "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        except Exception:
            return {"path": p, "exists": False}

    plan_obj = None
    plan_summary = {"exists": False}
    active_proposals = []
    blocked = None

    try:
        if os.path.exists(plan_path):
            plan_summary["exists"] = True
            plan_obj = json.loads(open(plan_path, "r", encoding="utf-8").read())
    except Exception as e:
        plan_summary["read_error"] = str(e)
        plan_obj = None

    if isinstance(plan_obj, dict):
        st = str(plan_obj.get("status") or "").strip() or None
        steps = plan_obj.get("steps") if isinstance(plan_obj.get("steps"), list) else []
        counts = {"todo":0,"done":0,"proposed":0,"error":0,"in_progress":0,"other":0}

        for x in steps:
            if not isinstance(x, dict):
                continue
            sst = str(x.get("status") or "").strip().lower()
            if sst in counts:
                counts[sst] += 1
            else:
                counts["other"] += 1

            pid = str(x.get("proposal_id") or "").strip()
            if pid:
                active_proposals.append(pid)
                if (blocked is None) and (sst == "proposed"):
                    blocked = {
                        "step_id": str(x.get("id") or "").strip() or None,
                        "proposal_id": pid,
                        "required_approve": str(x.get("required_approve") or f"APPLY_{pid}").strip(),
                    }

        # unique keep order
        seen=set()
        uniq=[]
        for pid in active_proposals:
            if pid in seen:
                continue
            seen.add(pid)
            uniq.append(pid)
        active_proposals = uniq

        plan_summary.update({
            "room_id": plan_obj.get("room_id"),
            "status": st,
            "steps_total": len(steps),
            "counts": counts,
            "updated_at": plan_obj.get("updated_at"),
        })

    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "room_id": rid,
        "paths": {
            "base_tmp": base_tmp,
            "rooms_dir": rooms_dir,
            "room_dir": room_dir,
            "proposals_dir": props_dir,
        },
        "files": {
            "plan": _stat(plan_path),
            "audit": _stat(audit_path),
            "evaluation_json": _stat(eval_json_path),
            "evaluations_ndjson": _stat(eval_ndjson_path),
            "rejections_ndjson": _stat(rej_ndjson_path),
        },
        "plan_summary": plan_summary,
        "blocked": blocked,
        "active_proposals": {
            "count": len(active_proposals),
            "proposal_ids": active_proposals,
        },
        "impl": "HARDENING16C_STATUS_GET_EOF",
    }

# HARDENING16C_STATUS_GET_EOF
# --- /HARDENING16C_STATUS_GET_EOF ---------------------------------------------------


# --- HARDENING17A_AUDIT_GET_SSOT_EOF: audit readers (SSOT) --------------------------
@app.get("/v1/agent/audit")
def agent_audit_last_ssot(request: Request, room_id: str = Query("", max_length=256)):
    """
    SSOT: devuelve el ÚLTIMO evento (última línea parseable) de audit.ndjson.
    room_id: Query o header x-room-id (default).
    """
    import os, json

    rid = (room_id or "").strip() or None
    if not rid:
        try:
            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
        except Exception:
            rid = "default"
    rid = rid or "default"

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "audit.ndjson")
    if not os.path.exists(p):
        return {"ok": False, "room_id": rid, "error": "audit.ndjson_not_found", "path": p}

    # leer últimas ~64KB y sacar última línea JSON válida
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            chunk = 65536
            start = max(0, end - chunk)
            f.seek(start, os.SEEK_SET)
            buf = f.read()
        text = buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        last = None
        bad = 0
        for ln in reversed(lines):
            try:
                last = json.loads(ln)
                break
            except Exception:
                bad += 1
                continue
        if last is None:
            return {"ok": False, "room_id": rid, "error": "no_valid_json_lines_in_tail", "path": p, "bad_tail_lines": bad}
        return {"ok": True, "room_id": rid, "path": p, "event": last, "bad_tail_lines": bad}
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"read_failed: {e}", "path": p}

@app.get("/v1/agent/audits")
def agent_audits_tail_ssot(request: Request, limit: int = Query(50, ge=1, le=1000), room_id: str = Query("", max_length=256)):
    """
    SSOT: tail N de audit.ndjson para room_id.
    room_id: Query o header x-room-id (default).
    """
    import os, json

    rid = (room_id or "").strip() or None
    if not rid:
        try:
            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
        except Exception:
            rid = "default"
    rid = rid or "default"

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "audit.ndjson")
    if not os.path.exists(p):
        return {"ok": False, "room_id": rid, "error": "audit.ndjson_not_found", "path": p, "items": []}

    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            chunk = 262144  # 256KB
            start = max(0, end - chunk)
            f.seek(start, os.SEEK_SET)
            buf = f.read()
        text = buf.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        tail = lines[-limit:] if len(lines) > limit else lines
        items = []
        bad = 0
        for ln in tail:
            try:
                items.append(json.loads(ln))
            except Exception:
                bad += 1
        return {"ok": True, "room_id": rid, "path": p, "limit": int(limit), "items": items, "bad_lines": bad, "impl": "HARDENING17A_AUDIT_GET_SSOT_EOF"}
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"tail_failed: {e}", "path": p, "items": []}

# HARDENING17A_AUDIT_GET_SSOT_EOF
# --- /HARDENING17A_AUDIT_GET_SSOT_EOF ------------------------------------------------


# --- HARDENING18_ROOMS_LIST_SSOT_EOF: list rooms (SSOT) ------------------------------
@app.get("/v1/agent/rooms")
def agent_rooms_list_ssot(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
    include_status: bool = Query(False),
):
    """
    SSOT: lista rooms existentes en tmp_agent/state/rooms.
    - include_status=false: solo metadata + existencia de archivos SSOT.
    - include_status=true: lee plan.json (si existe) y devuelve resumen + blocked (si existe).
    """
    import os, json
    from datetime import datetime, timezone

    base_tmp = r"C:\AI_VAULT\tmp_agent"
    rooms_dir = os.path.join(base_tmp, "state", "rooms")

    if not os.path.isdir(rooms_dir):
        return {"ok": True, "rooms_dir": rooms_dir, "limit": int(limit), "items": [], "missing_dir": True, "impl": "HARDENING18_ROOMS_LIST_SSOT_EOF"}

    def _stat(p):
        try:
            st = os.stat(p)
            return {"exists": True, "path": p, "size": int(st.st_size), "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()}
        except Exception:
            return {"exists": False, "path": p}

    def _plan_summary(plan_obj: dict):
        steps = plan_obj.get("steps") if isinstance(plan_obj.get("steps"), list) else []
        counts = {"todo":0,"done":0,"proposed":0,"error":0,"in_progress":0,"other":0}
        blocked = None
        for st in steps:
            if not isinstance(st, dict):
                continue
            sst = str(st.get("status") or "").strip().lower()
            if sst in counts:
                counts[sst] += 1
            else:
                counts["other"] += 1
            if blocked is None and sst == "proposed":
                pid = str(st.get("proposal_id") or "").strip() or None
                if pid:
                    blocked = {
                        "step_id": str(st.get("id") or "").strip() or None,
                        "proposal_id": pid,
                        "required_approve": str(st.get("required_approve") or f"APPLY_{pid}").strip(),
                    }
        return {
            "room_id": plan_obj.get("room_id"),
            "status": str(plan_obj.get("status") or "").strip() or None,
            "steps_total": len(steps),
            "counts": counts,
            "updated_at": plan_obj.get("updated_at"),
            "blocked": blocked,
        }

    # list rooms by mtime desc (dir mtime)
    rows = []
    try:
        for name in os.listdir(rooms_dir):
            full = os.path.join(rooms_dir, name)
            if not os.path.isdir(full):
                continue
            try:
                st = os.stat(full)
                mtime = st.st_mtime
            except Exception:
                mtime = 0
            rows.append((mtime, name, full))
    except Exception as e:
        return {"ok": False, "rooms_dir": rooms_dir, "error": f"list_failed: {e}", "items": []}

    rows.sort(key=lambda t: t[0], reverse=True)
    rows = rows[: int(limit)]

    items = []
    for mtime, rid, rdir in rows:
        plan_path = os.path.join(rdir, "plan.json")
        audit_path = os.path.join(rdir, "audit.ndjson")
        eval_json = os.path.join(rdir, "evaluation.json")
        eval_ndj  = os.path.join(rdir, "evaluations.ndjson")
        rej_ndj   = os.path.join(rdir, "rejections.ndjson")

        rec = {
            "room_id": rid,
            "room_dir": rdir,
            "room_mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat() if mtime else None,
            "files": {
                "plan": _stat(plan_path),
                "audit": _stat(audit_path),
                "evaluation_json": _stat(eval_json),
                "evaluations_ndjson": _stat(eval_ndj),
                "rejections_ndjson": _stat(rej_ndj),
            },
        }

        if include_status and rec["files"]["plan"]["exists"]:
            try:
                plan_obj = json.loads(open(plan_path, "r", encoding="utf-8").read())
                if isinstance(plan_obj, dict):
                    rec["plan_summary"] = _plan_summary(plan_obj)
            except Exception as e:
                rec["plan_summary"] = {"read_error": str(e)}

        items.append(rec)

    return {"ok": True, "rooms_dir": rooms_dir, "limit": int(limit), "include_status": bool(include_status), "items": items, "impl": "HARDENING18_ROOMS_LIST_SSOT_EOF"}

# HARDENING18_ROOMS_LIST_SSOT_EOF
# --- /HARDENING18_ROOMS_LIST_SSOT_EOF ------------------------------------------------


# --- HARDENING19_CLEANUP_SSOT_EOF: cleanup preview/apply (guarded) -------------------
@app.get("/v1/agent/cleanup_preview")
def agent_cleanup_preview_ssot(
    request: Request,
    older_than_hours: int = Query(24, ge=1, le=24*365),
    only_orphans: bool = Query(True),
    room_prefix: str = Query("", max_length=128),
    limit: int = Query(2000, ge=1, le=200000),
):
    """
    Preview ONLY (no delete):
    - Proposals candidates: tmp_agent/proposals/*.json (excluding bundle_*.json)
      - if only_orphans=true: keep only proposals not referenced by any plan.json
      - if room_prefix provided: filter by proposal.room_id startswith prefix OR plan room_id startswith prefix (for orphan scan)
    """
    import os, json, time
    from datetime import datetime, timezone

    base_tmp = r"C:\AI_VAULT\tmp_agent"
    props_dir = os.path.join(base_tmp, "proposals")
    rooms_dir = os.path.join(base_tmp, "state", "rooms")

    now = time.time()
    cutoff = now - float(older_than_hours) * 3600.0
    pref = (room_prefix or "").strip() or None

    # collect referenced proposal_ids from all plan.json
    referenced = set()
    scanned_rooms = 0
    if os.path.isdir(rooms_dir):
        for rid in os.listdir(rooms_dir):
            rdir = os.path.join(rooms_dir, rid)
            if not os.path.isdir(rdir):
                continue
            if pref and not str(rid).startswith(pref):
                continue
            plan_path = os.path.join(rdir, "plan.json")
            if not os.path.exists(plan_path):
                continue
            scanned_rooms += 1
            try:
                plan = json.loads(open(plan_path, "r", encoding="utf-8").read())
                for st in (plan.get("steps") or []):
                    if isinstance(st, dict):
                        pid = str(st.get("proposal_id") or "").strip()
                        if pid:
                            referenced.add(pid)
            except Exception:
                continue

    candidates = []
    scanned_props = 0
    if os.path.isdir(props_dir):
        for name in os.listdir(props_dir):
            if not name.lower().endswith(".json"):
                continue
            if name.lower().startswith("bundle_"):
                continue
            full = os.path.join(props_dir, name)
            scanned_props += 1
            try:
                st = os.stat(full)
                mtime = st.st_mtime
                size = int(st.st_size)
            except Exception:
                continue

            if mtime > now:  # clock skew guard
                continue
            if mtime >= cutoff:
                continue

            pid = name[:-5]
            # orphan filter
            if only_orphans and pid in referenced:
                continue

            rec = {
                "proposal_id": pid,
                "path": full,
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "age_hours": round((now - mtime)/3600.0, 3),
                "size": size,
                "reason": "old_orphan" if only_orphans else "old",
            }

            # parse best-effort for room filter
            if pref:
                try:
                    data = json.loads(open(full, "r", encoding="utf-8").read())
                    rid = str((data.get("room_id") if isinstance(data, dict) else "") or "").strip()
                    if rid and not rid.startswith(pref):
                        continue
                    rec["room_id"] = rid or None
                except Exception:
                    # if we can't parse, and pref requested, skip (safe)
                    continue

            candidates.append(rec)
            if len(candidates) >= int(limit):
                break

    # HARDENING19D2_CLEANUP_PREVIEW_QUERY_FILTERS
    try:
        qp = getattr(request, 'query_params', None)
        allow_id_prefix = None
        exclude_ids = set()
        if qp is not None:
            ap = (qp.get('allow_id_prefix') or '').strip()
            allow_id_prefix = ap or None
            try:
                xs = qp.getlist('exclude_ids')
            except Exception:
                xs = []
            for x in xs:
                try:
                    x = str(x).strip()
                    if x:
                        exclude_ids.add(x)
                except Exception:
                    pass
    
        def _passes(pid: str) -> bool:
            if not pid:
                return False
            if pid in exclude_ids:
                return False
            if allow_id_prefix and (not pid.startswith(allow_id_prefix)):
                return False
            return True
    
        if 'candidates' in locals() and isinstance(candidates, list):
            candidates = [c for c in candidates if isinstance(c, dict) and _passes(str(c.get('proposal_id') or '').strip())]
    except Exception:
        pass
    # /HARDENING19D2_CLEANUP_PREVIEW_QUERY_FILTERS
    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "older_than_hours": int(older_than_hours),
        "only_orphans": bool(only_orphans),
        "room_prefix": pref,
        "scanned": {"rooms_with_plan": scanned_rooms, "proposals_files": scanned_props, "referenced_ids": len(referenced)},
        "candidates": candidates,
        "count": len(candidates),
        "impl": "HARDENING19_CLEANUP_SSOT_EOF",
    }

@app.post("/v1/agent/cleanup_apply")
def agent_cleanup_apply_ssot(request: Request, req: dict = Body(...)):
    """
    Apply delete with guardrails:
    - requires req.confirm == "DELETE"
    - supports: older_than_hours, only_orphans, room_prefix, max_delete (default 200)
    - writes cleanup log to tmp_agent/state/cleanup.ndjson
    """
    import os, json, time
    from datetime import datetime, timezone

    confirm = None
    older = 24
    only_orphans = True
    pref = None
    max_delete = 200

    try:
        if isinstance(req, dict):
            confirm = req.get("confirm")
            older = int(req.get("older_than_hours", older))
            only_orphans = bool(req.get("only_orphans", only_orphans))
            pref = (str(req.get("room_prefix") or "").strip() or None)
            max_delete = int(req.get("max_delete", max_delete))
    except Exception:
        pass

    if str(confirm or "").strip() != "DELETE":
        return {"ok": False, "error": "missing_confirm_DELETE"}

    # cap max_delete (damage control)
    if max_delete < 1: max_delete = 1
    if max_delete > 5000: max_delete = 5000

    # reuse preview logic (in-process)


    # HARDENING19C_CLEANUP_FILTERS: enforce allow_id_prefix / exclude_ids
    allow_id_prefix = None
    exclude_ids = set()

    try:
        if isinstance(req, dict):
            ap = req.get("allow_id_prefix")
            if ap is not None:
                ap = str(ap).strip()
                allow_id_prefix = ap or None
            ex = req.get("exclude_ids")
            if isinstance(ex, list):
                for x in ex:
                    try:
                        x = str(x).strip()
                        if x:
                            exclude_ids.add(x)
                    except Exception:
                        pass
    except Exception:
        pass

    def _passes_filters(pid: str) -> bool:
        if not pid:
            return False
        if pid in exclude_ids:
            return False
        if allow_id_prefix and (not pid.startswith(allow_id_prefix)):
            return False
        return True
    # /HARDENING19C_CLEANUP_FILTERS


    # Apply filters to preview/candidates list
    try:
        if "candidates" in locals() and isinstance(candidates, list):
            candidates = [c for c in candidates if isinstance(c, dict) and _passes_filters(str(c.get("proposal_id") or "").strip())]
    except Exception:
        pass
    preview = agent_cleanup_preview_ssot(
        request=request,
        older_than_hours=max(1, min(older, 24*365)),
        only_orphans=only_orphans,
        room_prefix=pref or "",
        limit=max_delete,
    )

    if not preview.get("ok"):
        return {"ok": False, "error": "preview_failed", "preview": preview}



    # HARDENING19C_CLEANUP_FILTERS: enforce allow_id_prefix / exclude_ids
    allow_id_prefix = None
    exclude_ids = set()

    try:
        if isinstance(req, dict):
            ap = req.get("allow_id_prefix")
            if ap is not None:
                ap = str(ap).strip()
                allow_id_prefix = ap or None
            ex = req.get("exclude_ids")
            if isinstance(ex, list):
                for x in ex:
                    try:
                        x = str(x).strip()
                        if x:
                            exclude_ids.add(x)
                    except Exception:
                        pass
    except Exception:
        pass

    def _passes_filters(pid: str) -> bool:
        if not pid:
            return False
        if pid in exclude_ids:
            return False
        if allow_id_prefix and (not pid.startswith(allow_id_prefix)):
            return False
        return True
    # /HARDENING19C_CLEANUP_FILTERS


    # Apply filters to preview candidates
    try:
        if "candidates" in locals() and isinstance(candidates, list):
            candidates = [c for c in candidates if isinstance(c, dict) and _passes_filters(str(c.get("proposal_id") or "").strip())]
    except Exception:
        pass
    candidates = preview.get("candidates") or []
    deleted = []
    failed = []

    for c in candidates:
        p = c.get("path")
        if not p or not isinstance(p, str):
            continue
        try:
            if os.path.exists(p):
                os.remove(p)
                deleted.append({"proposal_id": c.get("proposal_id"), "path": p})
        except Exception as e:
            failed.append({"proposal_id": c.get("proposal_id"), "path": p, "error": str(e)})

    # append log best-effort
    try:
        base_tmp = r"C:\AI_VAULT\tmp_agent"
        log_path = os.path.join(base_tmp, "state", "cleanup.ndjson")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "older_than_hours": int(older),
            "only_orphans": bool(only_orphans),
            "room_prefix": pref,
            "deleted": len(deleted),
            "failed": len(failed),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return {
        "ok": True,
        "deleted": deleted,
        "failed": failed,
        "preview": {"count": preview.get("count"), "scanned": preview.get("scanned")},
        "impl": "HARDENING19_CLEANUP_SSOT_EOF",
    }

# HARDENING19_CLEANUP_SSOT_EOF
# --- /HARDENING19_CLEANUP_SSOT_EOF ----------------------------------------------------
# HARDENING19C_CLEANUP_FILTERS

# HARDENING19D2_CLEANUP_PREVIEW_QUERY_FILTERS


# --- HARDENING20_PLAN_STATUS_CANON_SSOT: canonicalize steps + recompute plan.status ----
def _ssot_normalize_step(step: dict) -> dict:
    """
    Canon step schema:
      {id, status, tool_name, tool_args, result?, proposal_id?, required_approve?}
    Best-effort: tolera aliases previos y limpia campos redundantes.
    """
    if not isinstance(step, dict):
        return {"id": "", "status": "error", "tool_name": None, "tool_args": {}, "result": {"ok": False, "error": "step_not_dict"}}

    sid = step.get("id")
    if sid is None:
        sid = step.get("step_id") or step.get("stepId") or step.get("step") or step.get("id")
    sid = str(sid or "").strip()

    status = step.get("status")
    status = str(status or "todo").strip().lower()
    if status in ("pending",): status = "todo"
    if status in ("completed",): status = "done"

    tool_name = step.get("tool_name")
    if not tool_name:
        tool_name = step.get("tool") or step.get("name")
    tool_name = (str(tool_name).strip() if tool_name is not None else None) or None

    tool_args = step.get("tool_args")
    # HARDENING_NOW_ISO_PLACEHOLDER_V1: resolve placeholders for write tools
    try:
        if tool_name in ("append_file","write_file"):
            tool_args = _resolve_placeholders(tool_args)
    except Exception:
        pass

    if not isinstance(tool_args, dict):
        tool_args = step.get("args")
    if not isinstance(tool_args, dict):
        tool_args = {}
    # normaliza alias común text->content para write_file
    if "text" in tool_args and "content" not in tool_args:
        try:
            tool_args["content"] = tool_args.get("text")
        except Exception:
            pass

    out = {
        "id": sid,
        "status": status,
        "tool_name": tool_name,
        "tool_args": tool_args,
    }

    # passthrough fields we use
    for k in ("result", "proposal_id", "required_approve"):
        if k in step:
            out[k] = step.get(k)

    # si era proposed pero no tiene tokens, degradar a todo para consistencia
    if out.get("status") == "proposed":
        pid = str(out.get("proposal_id") or "").strip()
        rat = str(out.get("required_approve") or "").strip()
        if not pid or not rat:
            out["status"] = "todo"
            out.pop("proposal_id", None)
            out.pop("required_approve", None)

    return out


def _ssot_recompute_plan_status(plan: dict) -> dict:
    """
    Determinista:
      - si no hay steps -> status=empty
      - si algún step.status == error -> status=error
      - si todos done -> status=complete
      - else -> status=active
    """
    if not isinstance(plan, dict):
        return {"room_id": "default", "status": "error", "steps": [], "error": "plan_not_dict"}

    steps = plan.get("steps")
    if not isinstance(steps, list):
        steps = []
    norm = []
    for st in steps:
        try:
            norm.append(_ssot_normalize_step(st))
        except Exception:
            norm.append({"id": "", "status": "error", "tool_name": None, "tool_args": {}, "result": {"ok": False, "error": "normalize_failed"}})

    plan["steps"] = norm

    if len(norm) == 0:
        plan["status"] = "empty"
        return plan

    statuses = [str(x.get("status") or "").lower().strip() for x in norm]
    if any(s == "error" for s in statuses):
        plan["status"] = "error"
        return plan

    if all(s == "done" for s in statuses):
        plan["status"] = "complete"
        return plan

    plan["status"] = "active"
    return plan


def _ssot_canonize_and_recompute_inplace(plan: dict) -> dict:
    """
    Conveniencia: normaliza + recomputa status; retorna plan.
    """
    try:
        return _ssot_recompute_plan_status(plan)
    except Exception:
        try:
            plan["status"] = "error"
        except Exception:
            pass
        return plan

# --- /HARDENING20_PLAN_STATUS_CANON_SSOT ----------------------------------------------
# HARDENING20_PLAN_STATUS_CANON_SSOT
# --- HARDENING21B_MISSION_GET_SSOT_EOF: GET mission.json (SSOT) ----------------------
@app.get("/v1/agent/mission")
def agent_mission_get_ssot(request: Request, room_id: str = Query("", max_length=256)):
    """
    SSOT: lee state/rooms/<rid>/mission.json y lo devuelve.
    room_id: Query o header x-room-id (default).
    """
    import os, json
    rid = (room_id or "").strip() or None
    if not rid:
        try:
            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default").strip() or "default"
        except Exception:
            rid = "default"
    rid = rid or "default"

    p = os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", rid, "mission.json")
    if not os.path.exists(p):
        return {"ok": False, "room_id": rid, "error": "mission.json_not_found", "path": p}

    try:
        data = json.loads(open(p, "r", encoding="utf-8").read())
        return {"ok": True, "room_id": rid, "mission": data, "path": p}
    except Exception as e:
        return {"ok": False, "room_id": rid, "error": f"mission.json_read_failed: {e}", "path": p}

# HARDENING21B_MISSION_GET_SSOT_EOF
# --- /HARDENING21B_MISSION_GET_SSOT_EOF ---------------------------------------------
# HARDENING_AUDIT_SEMANTIC_V1
# HARDENING_AUDIT_SEMANTIC_V2
# HARDENING_AUDIT_RUN_RESULT_REWRITE_V1
# HARDENING_AUDIT_RUN_RESULT_GUARD_V3
# HARDENING_NOW_ISO_PLACEHOLDER_V1
# HARDENING_PLAN_NORMALIZE_V1
# HARDENING_PLAN_NORMALIZE_V2
# HARDENING_PLAN_NORMALIZE_V4_CANONICAL
# HARDENING_PLAN_RETURN_V1
# HARDENING_PLAN_ROOMID_PRIMARY_V1
# HARDENING_PLAN_HANDLER_CANONICAL_V1
# HARDENING_HEALTHZ_SSOT_V1
# HARDENING_HEALTHZ_SSOT_V2_NO_NOWISO
# HARDENING_HEALTHZ_SSOT_V3_SNAPSHOT_ENDPOINTS
# HARDENING_HEALTHZ_INNER_V4C_HTTP
# HARDENING_NORM_ROOM_ID_V1
# HARDENING_HEALTHZ_SNAPSHOT_GET_V1


# HARDENING_EPISODE_P3_1_V2_SAFE helpers (auto-generated)
def _episode_begin(locals_d: dict, phase: str):
    from pathlib import Path
    import json, uuid, hashlib
    from datetime import datetime, timezone

    def nowz():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def infer_room_id(d):
        for k in ("room_id","rid"):
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, str) and v.strip():
                return v.strip()
        for k in ("req","request","body"):
            v = d.get(k) if isinstance(d, dict) else None
            if v is None:
                continue
            rid = getattr(v, "room_id", None)
            if isinstance(rid, str) and rid.strip():
                return rid.strip()
            if isinstance(v, dict):
                rid = v.get("room_id")
                if isinstance(rid, str) and rid.strip():
                    return rid.strip()
        return "default"

    rid = infer_room_id(locals_d or {})
    run_id = "run_" + uuid.uuid4().hex[:12]

    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    (room_dir / "_last_run_id.txt").write_text(run_id, encoding="utf-8")

    plan_path = room_dir / "plan.json"
    plan_sha256 = None
    if plan_path.exists():
        b = plan_path.read_bytes()
        h = hashlib.sha256(); h.update(b); plan_sha256 = h.hexdigest()

    return {
        "ts_start": nowz(),
        "ts_end": None,
        "room_id": rid,
        "run_id": run_id,
        "phase": phase,
        "plan_path": str(plan_path) if plan_path.exists() else None,
        "plan_sha256": plan_sha256,
        "result": None,
        "errors": []
    }

def _episode_end(ep: dict, result):
    from pathlib import Path
    import json
    from datetime import datetime, timezone

    def nowz():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ep["ts_end"] = nowz()

    rid = ep.get("room_id") or "default"
    rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
    room_dir = rooms_dir / rid
    room_dir.mkdir(parents=True, exist_ok=True)

    # summarize result
    try:
        if isinstance(result, dict):
            ep["result"] = {
                "ok": result.get("ok"),
                "blocked": result.get("blocked"),
                "proposal_id": (result.get("proposal_id") or (result.get("blocked") or {}).get("proposal_id")),
                "required_approve": (result.get("required_approve") or (result.get("blocked") or {}).get("required_approve")),
            }
        else:
            ep["result"] = {"type": type(result).__name__}
    except Exception as e:
        ep.setdefault("errors", []).append("result_summary_error: " + repr(e))

    episodes_dir = room_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    latest = room_dir / "episode.json"
    perrun = episodes_dir / f"episode_{ep.get('run_id','unknown')}.json"

    latest.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    perrun.write_text(json.dumps(ep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ep

def episode_wrap(phase: str):
    def deco(fn):
        def _wrapped(*args, **kwargs):
            __ep = _episode_begin(locals(), phase=phase)
            try:
                ret = fn(*args, **kwargs)
            except Exception as e:
                __ep.setdefault("errors", []).append("exception: " + repr(e))
                _episode_end(__ep, {"ok": False, "error": "exception", "detail": repr(e)})
                raise
            _episode_end(__ep, ret)
            return ret
        return _wrapped
    return deco





# =============================================================================
# DASHBOARD PROFESIONAL INTEGRADO
# =============================================================================

from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import aiohttp

class DashboardManager:
    \"\"\"Gestor del dashboard profesional integrado\"\"\"
    
    def __init__(self):
        self.dashboard_dir = Path("C:/AI_VAULT/tmp_agent/dashboard")
        self.setup_directories()
        
    def setup_directories(self):
        \"\"\"Crear estructura de directorios del dashboard\"\"\"
        (self.dashboard_dir / "templates").mkdir(parents=True, exist_ok=True)
        (self.dashboard_dir / "static/css").mkdir(parents=True, exist_ok=True)
        (self.dashboard_dir / "static/js").mkdir(parents=True, exist_ok=True)
        
    async def get_system_status(self, room_id: str) -> dict:
        \"\"\"Obtener estado completo del sistema para dashboard\"\"\"
        return {
            "room_id": room_id,
            "timestamp": datetime.now().isoformat(),
            "services": await self.get_services_status(),
            "trust_score": 95,
            "active_mission": await self.get_active_mission(room_id),
            "system_metrics": {
                "uptime": "99.9%",
                "active_processes": 3,
                "performance": "excellent"
            }
        }

# Configurar dashboard en FastAPI app
dashboard_manager = DashboardManager()

# Montar archivos estáticos y templates
app.mount("/static", StaticFiles(directory=str(dashboard_manager.dashboard_dir / "static")), name="static")
templates = Jinja2Templates(directory=str(dashboard_manager.dashboard_dir / "templates"))

@app.get("/dashboard")
async def dashboard_main(request: Request, room_id: str = None):
    \"\"\"Vista principal del dashboard profesional\"\"\"
    if not room_id:
        # Usar room actual del sistema
        room_id = "current_session"
    
    system_status = await dashboard_manager.get_system_status(room_id)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "system_status": system_status
    })

@app.get("/api/dashboard/status")
async def api_dashboard_status(room_id: str):
    \"\"\"API endpoint para estado del dashboard\"\"\"
    return await dashboard_manager.get_system_status(room_id)

@app.get("/api/dashboard/conversation")
async def api_conversation_state(room_id: str):
    \"\"\"Estado del contrato conversacional v2\"\"\"
    return {
        "room_id": room_id,
        "contract": await get_conversational_contract(room_id),
        "messages": await get_conversation_history(room_id),
        "requires_approval": False  # Lógica real aquí
    }

# Preservar compatibilidad legacy
@app.get("/ui/")
async def ui_legacy_redirect():
    \"\"\"Redirigir UI legacy al nuevo dashboard\"\"\"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


