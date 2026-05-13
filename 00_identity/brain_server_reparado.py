from __future__ import annotations

import secrets

import uuid

import types

import uuid

import types



# --- HARDENING_PLAN_NORMALIZE_V3_CANONICAL --------------------------------------------

from datetime import datetime, timezone



def _now_iso_utc_z() -> str:

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")



def _normalize_content_str(x):

    if x is None:

        return None

    if not isinstance(x, str):

        x = str(x)



    stripped = x.lstrip()

    if stripped.startswith("{") or stripped.startswith("["):

        return x



    if "__NOW_ISO_PLACEHOLDER__" in x:

        x = x.replace("__NOW_ISO_PLACEHOLDER__", _now_iso_utc_z())

    if "{{now_iso}}" in x:

        x = x.replace("{{now_iso}}", _now_iso_utc_z())



    x = x.replace("__LITERAL_BACKSLASH_N__", "\n")

    x = x.replace("\\r\\n", "\r\n")

    x = x.replace("\\n", "\n")

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

            args["text"] = norm



    return plan, errs

# --- /HARDENING_PLAN_NORMALIZE_V3_CANONICAL -----------------------------------------



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



# PATCH_FORCE_LF_WRITER_V1

def write_file(path: str, text: str) -> dict:

    p = Path(path)

    if not _is_allowed(p):

        raise PermissionError(f"WRITE_NOT_IN_ALLOWLIST: {p}")

    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(text, encoding="utf-8", newline="\n")

    return {"path": str(p), "bytes": len(text.encode("utf-8"))}



def append_file(path: str, text: str) -> dict:

    p = Path(path)

    if not _is_allowed(p):

        raise PermissionError(f"WRITE_NOT_IN_ALLOWLIST: {p}")

    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("a", encoding="utf-8", newline="\n") as f:

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





def _norm_room_id(value) -> str:

    try:

        s = str(value or "default").strip()

    except Exception:

        s = "default"

    if not s:

        s = "default"

    import re as _re

    s = _re.sub(r"[^A-Za-z0-9._-]+", "_", s)

    s = s.strip("._-") or "default"

    return s[:120]



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



# [HARDENING3_DISABLED_OLD] Legacy plan endpoint/decorator text was left commented here during SSOT migration.

# Legacy pre-SSOT plan function; active POST /v1/agent/plan lives later in the file.

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

# [HARDENING4_SAFEMIN_DISABLED] Legacy execute-step implementation below is kept only as commented reference.

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





# Legacy pre-SSOT run_once implementation kept only as commented reference below.

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



# AUTO_BUILD_FASTAPI_CONTROL_V1 BEGIN

def _autobuild_now_utc_z():

    try:

        return _now_iso_utc_z()

    except Exception:

        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _autobuild_norm_room_id(room_id):

    try:

        return _norm_room_id(room_id)

    except Exception:

        rid = str(room_id or "default").strip()

        return rid or "default"



def _autobuild_rooms_root():

    from pathlib import Path as _Path

    root = _Path(r"C:\AI_VAULT\tmp_agent\state\rooms")

    root.mkdir(parents=True, exist_ok=True)

    return root



def _autobuild_room_dir(room_id):

    d = _autobuild_rooms_root() / _autobuild_norm_room_id(room_id)

    d.mkdir(parents=True, exist_ok=True)

    return d



def _autobuild_state_path(room_id):

    return _autobuild_room_dir(room_id) / "autobuild_state.json"



def _autobuild_default_state(room_id):

    rid = _autobuild_norm_room_id(room_id)

    return {

        "ok": True,

        "room_id": rid,

        "status": "idle",

        "enabled": False,

        "runner_script": r"C:\AI_VAULT\tmp_agent\ops\autobuild_roadmap_runner_v1.ps1",

        "max_items_per_run": 1,

        "stop_on_error": True,

        "runs": 0,

        "last_run_utc": None,

        "last_summary_path": None,

        "last_summary": None,

        "last_exit_code": None,

        "last_stdout_tail": None,

        "last_stderr_tail": None,

        "updated_utc": _autobuild_now_utc_z(),

    }



def _autobuild_read_state(room_id):

    import json as _json

    p = _autobuild_state_path(room_id)

    base = _autobuild_default_state(room_id)

    if not p.exists():

        return base

    try:

        raw = _json.loads(p.read_text(encoding="utf-8"))

        if isinstance(raw, dict):

            base.update(raw)

    except Exception:

        pass

    base["room_id"] = _autobuild_norm_room_id(room_id)

    return base



def _autobuild_write_state(room_id, state):

    import json as _json

    p = _autobuild_state_path(room_id)

    data = dict(state) if isinstance(state, dict) else _autobuild_default_state(room_id)

    data["room_id"] = _autobuild_norm_room_id(room_id)

    data["updated_utc"] = _autobuild_now_utc_z()

    p.write_text(_json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return data



def _autobuild_to_bool(value, default=False):

    if value is None:

        return default

    if isinstance(value, bool):

        return value

    s = str(value).strip().lower()

    if s in ("1", "true", "yes", "y", "on"):

        return True

    if s in ("0", "false", "no", "n", "off"):

        return False

    return default



def _autobuild_find_latest_summary(new_only_names=None):

    from pathlib import Path as _Path

    import json as _json



    ops_root = _Path(r"C:\AI_VAULT\tmp_agent\ops")

    candidates = sorted(

        [p for p in ops_root.glob("autobuild_roadmap_runner_v1_*") if p.is_dir()],

        key=lambda p: p.stat().st_mtime,

        reverse=True

    )

    if new_only_names:

        filtered = [p for p in candidates if p.name in new_only_names]

        if filtered:

            candidates = filtered



    for d in candidates:

        s = d / "99_summary.json"

        if s.exists():

            try:

                data = _json.loads(s.read_text(encoding="utf-8"))

            except Exception:

                data = None

            return {

                "summary_path": str(s),

                "summary": data,

                "run_dir": str(d),

            }



    return {

        "summary_path": None,

        "summary": None,

        "run_dir": None,

    }



def _autobuild_run_once_shell(room_id, max_items=1, stop_on_error=True, dry_run=False):

    from pathlib import Path as _Path

    import subprocess as _subprocess



    runner = _Path(r"C:\AI_VAULT\tmp_agent\ops\autobuild_roadmap_runner_v1.ps1")

    before = set()

    ops_root = _Path(r"C:\AI_VAULT\tmp_agent\ops")

    if ops_root.exists():

        before = {p.name for p in ops_root.glob("autobuild_roadmap_runner_v1_*") if p.is_dir()}



    if dry_run:

        latest = _autobuild_find_latest_summary()

        return {

            "ok": True,

            "dry_run": True,

            "room_id": _autobuild_norm_room_id(room_id),

            "runner_script": str(runner),

            "runner_exists": runner.exists(),

            "summary_path": latest.get("summary_path"),

            "summary": latest.get("summary"),

            "run_dir": latest.get("run_dir"),

            "exit_code": 0,

            "stdout_tail": "",

            "stderr_tail": "",

        }



    if not runner.exists():

        return {

            "ok": False,

            "dry_run": False,

            "room_id": _autobuild_norm_room_id(room_id),

            "runner_script": str(runner),

            "runner_exists": False,

            "summary_path": None,

            "summary": None,

            "run_dir": None,

            "exit_code": 9009,

            "stdout_tail": "",

            "stderr_tail": f"No existe runner: {runner}",

        }



    cmd = [

        "powershell",

        "-NoProfile",

        "-ExecutionPolicy",

        "Bypass",

        "-File",

        str(runner),

        "-MaxItems",

        str(int(max_items or 1)),

    ]

    if stop_on_error:

        cmd.append("-StopOnError")



    cp = _subprocess.run(

        cmd,

        capture_output=True,

        text=True,

        encoding="utf-8",

        errors="replace"

    )



    after = set()

    if ops_root.exists():

        after = {p.name for p in ops_root.glob("autobuild_roadmap_runner_v1_*") if p.is_dir()}



    new_names = sorted(list(after - before))

    latest = _autobuild_find_latest_summary(set(new_names) if new_names else None)



    return {

        "ok": cp.returncode == 0,

        "dry_run": False,

        "room_id": _autobuild_norm_room_id(room_id),

        "runner_script": str(runner),

        "runner_exists": True,

        "summary_path": latest.get("summary_path"),

        "summary": latest.get("summary"),

        "run_dir": latest.get("run_dir"),

        "exit_code": cp.returncode,

        "stdout_tail": (cp.stdout or "")[-4000:],

        "stderr_tail": (cp.stderr or "")[-4000:],

    }



@app.post("/v1/agent/autobuild/start")

async def agent_autobuild_start(payload: dict = None):

    payload = payload or {}

    room_id = _autobuild_norm_room_id(payload.get("room_id"))

    state = _autobuild_read_state(room_id)



    state["enabled"] = True

    state["status"] = "active"

    state["runner_script"] = str(payload.get("runner_script") or state.get("runner_script") or r"C:\AI_VAULT\tmp_agent\ops\autobuild_roadmap_runner_v1.ps1")

    state["max_items_per_run"] = int(payload.get("max_items_per_run") or state.get("max_items_per_run") or 1)

    state["stop_on_error"] = _autobuild_to_bool(payload.get("stop_on_error"), state.get("stop_on_error", True))

    state["started_utc"] = state.get("started_utc") or _autobuild_now_utc_z()



    state = _autobuild_write_state(room_id, state)

    return {

        "ok": True,

        "room_id": room_id,

        "state_path": str(_autobuild_state_path(room_id)),

        "state": state,

        "impl": "AUTO_BUILD_FASTAPI_CONTROL_V1",

    }



@app.get("/v1/agent/autobuild/status")

async def agent_autobuild_status(room_id: str = "default"):

    rid = _autobuild_norm_room_id(room_id)

    state = _autobuild_read_state(rid)

    return {

        "ok": True,

        "room_id": rid,

        "state_path": str(_autobuild_state_path(rid)),

        "state": state,

        "impl": "AUTO_BUILD_FASTAPI_CONTROL_V1",

    }



@app.post("/v1/agent/autobuild/run_once")

async def agent_autobuild_run_once(payload: dict = None):

    import asyncio



    payload = payload or {}

    room_id = _autobuild_norm_room_id(payload.get("room_id"))

    state = _autobuild_read_state(room_id)



    if not state.get("enabled"):

        state["enabled"] = True

    state["status"] = "running"



    max_items = int(payload.get("max_items") or state.get("max_items_per_run") or 1)

    stop_on_error = _autobuild_to_bool(payload.get("stop_on_error"), state.get("stop_on_error", True))

    dry_run = _autobuild_to_bool(payload.get("dry_run"), False)



    result = await asyncio.to_thread(

        _autobuild_run_once_shell,

        room_id=room_id,

        max_items=max_items,

        stop_on_error=stop_on_error,

        dry_run=dry_run,

    )



    state["runs"] = int(state.get("runs") or 0) + 1

    state["last_run_utc"] = _autobuild_now_utc_z()

    state["last_exit_code"] = result.get("exit_code")

    state["last_summary_path"] = result.get("summary_path")

    state["last_summary"] = result.get("summary")

    state["last_stdout_tail"] = result.get("stdout_tail")

    state["last_stderr_tail"] = result.get("stderr_tail")

    state["last_run_dir"] = result.get("run_dir")

    state["last_mode"] = ((result.get("summary") or {}).get("last_mode") if isinstance(result.get("summary"), dict) else None)



    if dry_run:

        state["status"] = "active"

    elif result.get("ok"):

        stop_reason = None

        if isinstance(result.get("summary"), dict):

            stop_reason = result["summary"].get("stop_reason")

        state["status"] = "idle" if stop_reason in ("roadmap_exhausted", "completed_requested_cycles") else "active"

    else:

        state["status"] = "error"



    state = _autobuild_write_state(room_id, state)



    return {

        "ok": bool(result.get("ok")),

        "room_id": room_id,

        "state_path": str(_autobuild_state_path(room_id)),

        "state": state,

        "result": result,

        "impl": "AUTO_BUILD_FASTAPI_CONTROL_V2_THREADSAFE_RUNONCE",

    }

# AUTO_BUILD_FASTAPI_CONTROL_V1 END





@app.get("/v1/agent/healthz")

def agent_healthz():

    """

    Verifica coherencia mínima del runtime:

      - Acceso a C:\\AI_VAULT\\tmp_agent

      - Escritura/lectura SSOT plan.json en state\\rooms\\__healthz__\\

      - Snapshot KV base (state\\runtime_snapshot.json como dict)

    """

    tmp_agent = r"C:\AI_VAULT\tmp_agent"

    state_dir = os.path.join(tmp_agent, "state")

    rooms_dir = os.path.join(state_dir, "rooms")



    report = {

        "ok": True,

        "tmp_agent": {"path": tmp_agent, "exists": False},

        "room_plan_rw": {"room_id": "__healthz__", "path": None, "ok": False, "error": None},

        "snapshot_kv": {"path": None, "ok": False, "error": None},

    }



    try:

        report["tmp_agent"]["exists"] = os.path.isdir(tmp_agent)

        if not report["tmp_agent"]["exists"]:

            raise FileNotFoundError(tmp_agent)



        os.makedirs(rooms_dir, exist_ok=True)



        # SSOT plan.json RW (room dedicado healthz)

        rid = "__healthz__"

        rdir = os.path.join(rooms_dir, rid)

        os.makedirs(rdir, exist_ok=True)

        plan_path = os.path.join(rdir, "plan.json")

        report["room_plan_rw"]["path"] = plan_path



        probe = {"room_id": rid, "status": "healthz", "steps": [], "last_eval": None}

        with open(plan_path, "w", encoding="utf-8") as f:

            import json

            json.dump(probe, f, ensure_ascii=False, indent=2)

        with open(plan_path, "r", encoding="utf-8") as f:

            _ = f.read()

        report["room_plan_rw"]["ok"] = True



        # Snapshot KV base (mínimo viable = runtime_snapshot.json dict)

        snap_path = os.path.join(state_dir, "runtime_snapshot.json")

        report["snapshot_kv"]["path"] = snap_path

        os.makedirs(state_dir, exist_ok=True)

        if os.path.exists(snap_path):

            import json

            try:

                data = json.load(open(snap_path, "r", encoding="utf-8"))

                if not isinstance(data, dict):

                    raise TypeError("runtime_snapshot.json no es dict")

            except Exception as e:

                raise RuntimeError(f"Snapshot inválido: {e}")

        else:

            import json

            json.dump({}, open(snap_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

        report["snapshot_kv"]["ok"] = True



    except Exception as e:

        report["ok"] = False

        # coloca error en el bucket más relevante si aplica

        if report["tmp_agent"]["exists"] is False:

            report["tmp_agent"]["error"] = str(e)

        elif report["room_plan_rw"]["ok"] is False:

            report["room_plan_rw"]["error"] = str(e)

        elif report["snapshot_kv"]["ok"] is False:

            report["snapshot_kv"]["error"] = str(e)

        else:

            report["error"] = str(e)



    if not report["ok"]:

        # no reventamos con stacktrace; devolvemos reporte consistente

        raise HTTPException(status_code=503, detail=report)



    return report

# --- /HARDENING1: healthz --------------------------------------------------





# --- HARDENING3_SSOT_ROOMPLAN_JSON: canonical plan/evaluate -----------------

import json

from datetime import datetime, timezone

from fastapi import Request, Body



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

    try:

        with open(pp, "r", encoding="utf-8") as f:

            return json.load(f) or {}

    except Exception:

        return {}







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





# PATCH_P2_1_CONTENT_NULL_V1

def _p2_1_safe_tool_args(tool_name, tool_args):

    try:

        args = dict(tool_args) if isinstance(tool_args, dict) else {}



        if tool_name in ("write_file", "append_file"):

            raw = args.get("content", None)



            if raw is None and "text" in args:

                raw = args.get("text", None)



            if raw is None:

                raw = "__NOW_ISO_PLACEHOLDER__\n"



            if not isinstance(raw, str):

                raw = str(raw)



            norm = _normalize_content_str(raw)



            if norm is None or norm == "":

                norm = _now_iso_utc_z() + "\n"



            if norm != raw:

                args["raw_content"] = raw



            args["content"] = norm

            args["text"] = norm



        return args

    except Exception:

        return tool_args if isinstance(tool_args, dict) else {}

def _plan_steps(plan: dict):

    steps = plan.get("steps", [])

    return steps if isinstance(steps, list) else []









# PATCH_P6_1_GOAL_STACK_V1

def _goal_stack_path(room_id: str) -> str:

    try:

        base_dir = os.path.dirname(_ssot_plan_path(room_id))

    except Exception:

        base_dir = str(Path(r"C:\AI_VAULT\tmp_agent\state\rooms") / str(room_id or "default"))

    os.makedirs(base_dir, exist_ok=True)

    return os.path.join(base_dir, "goal_stack.json")



def _goal_stack_read(room_id: str) -> dict:

    rid = str(room_id or "default").strip() or "default"

    p = _goal_stack_path(rid)

    try:

        if os.path.exists(p):

            with open(p, "r", encoding="utf-8") as f:

                data = json.load(f)

            if isinstance(data, dict):

                goals = data.get("goals")

                if not isinstance(goals, list):

                    goals = []

                return {

                    "room_id": rid,

                    "goals": goals,

                    "updated_at": data.get("updated_at") or _utc_now()

                }

    except Exception:

        pass

    return {"room_id": rid, "goals": [], "updated_at": _utc_now()}



def _goal_stack_write(room_id: str, payload: dict) -> dict:

    rid = str(room_id or "default").strip() or "default"

    data = payload if isinstance(payload, dict) else {}

    goals = data.get("goals")

    if not isinstance(goals, list):

        goals = []

    out = {

        "room_id": rid,

        "goals": goals,

        "updated_at": data.get("updated_at") or _utc_now()

    }

    p = _goal_stack_path(rid)

    with open(p, "w", encoding="utf-8", newline="\n") as f:

        json.dump(out, f, ensure_ascii=False, indent=2)

    return out



def _goal_stack_norm_goal(goal_obj, fallback_title="") -> dict | None:

    if not isinstance(goal_obj, dict):

        goal_obj = {}

    title = str(goal_obj.get("title") or fallback_title or "").strip()

    if not title:

        return None

    goal_id = str(goal_obj.get("goal_id") or "").strip()

    if not goal_id:

        goal_id = "G_" + hashlib.sha1(f"{title}|{_utc_now()}".encode("utf-8")).hexdigest()[:12]

    out = {

        "goal_id": goal_id,

        "title": title,

        "status": str(goal_obj.get("status") or "active").strip().lower() or "active",

        "created_at": goal_obj.get("created_at") or _utc_now(),

    }

    if isinstance(goal_obj.get("meta"), dict):

        out["meta"] = goal_obj.get("meta")

    return out



@app.get("/v1/agent/goals")

def agent_goals_get(request: Request, room_id: str = "default"):

    rid = str(room_id or "").strip()

    if not rid:

        try:

            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

        except Exception:

            rid = ""

    rid = rid or "default"

    gs = _goal_stack_read(rid)

    current_goal = gs["goals"][-1] if isinstance(gs.get("goals"), list) and gs.get("goals") else None

    return {

        "ok": True,

        "room_id": rid,

        "goal_stack": gs,

        "current_goal": current_goal,

        "impl": "PATCH_P6_1_GOAL_STACK_V1"

    }



@app.post("/v1/agent/goals")

def agent_goals_post(request: Request, req: dict = Body(...)):

    rid = "default"

    try:

        if isinstance(req, dict) and req.get("room_id"):

            rid = str(req.get("room_id") or "").strip() or "default"

    except Exception:

        rid = "default"

    if not rid or rid == "default":

        try:

            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

            if hdr:

                rid = hdr

        except Exception:

            pass

    rid = rid or "default"



    action = "push"

    try:

        if isinstance(req, dict) and req.get("action"):

            action = str(req.get("action") or "push").strip().lower() or "push"

    except Exception:

        action = "push"



    gs = _goal_stack_read(rid)

    goals = gs.get("goals") if isinstance(gs.get("goals"), list) else []

    popped = None



    if action == "push":

        goal_in = req.get("goal") if isinstance(req, dict) and isinstance(req.get("goal"), dict) else {}

        fallback_title = str(req.get("title") or "").strip() if isinstance(req, dict) else ""

        goal = _goal_stack_norm_goal(goal_in, fallback_title=fallback_title)

        if goal is None:

            return {"ok": False, "room_id": rid, "error": "goal_title_required"}

        goals.append(goal)



    elif action == "pop":

        if goals:

            popped = goals.pop()



    elif action == "clear":

        goals = []



    else:

        return {"ok": False, "room_id": rid, "error": f"unsupported_action:{action}"}



    gs["goals"] = goals

    gs["updated_at"] = _utc_now()

    gs = _goal_stack_write(rid, gs)

    current_goal = gs["goals"][-1] if gs["goals"] else None



    return {

        "ok": True,

        "room_id": rid,

        "action": action,

        "goal_stack": gs,

        "current_goal": current_goal,

        "popped": popped,

        "impl": "PATCH_P6_1_GOAL_STACK_V1"

    }







# PATCH_P6_2_AUTONOMY_V1

def _autonomy_path(room_id: str) -> str:

    try:

        base_dir = os.path.dirname(_ssot_plan_path(room_id))

    except Exception:

        base_dir = str(Path(r"C:\AI_VAULT\tmp_agent\state\rooms") / str(room_id or "default"))

    os.makedirs(base_dir, exist_ok=True)

    return os.path.join(base_dir, "autonomy.json")



def _autonomy_default(room_id: str) -> dict:

    rid = str(room_id or "default").strip() or "default"

    return {

        "room_id": rid,

        "enabled": False,

        "max_auto_steps": 1,

        "require_approval_for_writes": True,

        "updated_at": _utc_now()

    }



def _autonomy_read(room_id: str) -> dict:

    rid = str(room_id or "default").strip() or "default"

    p = _autonomy_path(rid)

    base = _autonomy_default(rid)

    try:

        if os.path.exists(p):

            with open(p, "r", encoding="utf-8") as f:

                data = json.load(f)

            if isinstance(data, dict):

                base["enabled"] = bool(data.get("enabled", base["enabled"]))

                try:

                    base["max_auto_steps"] = max(1, int(data.get("max_auto_steps", base["max_auto_steps"])))

                except Exception:

                    base["max_auto_steps"] = 1

                base["require_approval_for_writes"] = bool(

                    data.get("require_approval_for_writes", base["require_approval_for_writes"])

                )

                base["updated_at"] = data.get("updated_at") or _utc_now()

    except Exception:

        pass

    return base



def _autonomy_write(room_id: str, payload: dict) -> dict:

    rid = str(room_id or "default").strip() or "default"

    cur = _autonomy_default(rid)

    if isinstance(payload, dict):

        cur["enabled"] = bool(payload.get("enabled", cur["enabled"]))

        try:

            cur["max_auto_steps"] = max(1, int(payload.get("max_auto_steps", cur["max_auto_steps"])))

        except Exception:

            cur["max_auto_steps"] = 1

        cur["require_approval_for_writes"] = bool(

            payload.get("require_approval_for_writes", cur["require_approval_for_writes"])

        )

        cur["updated_at"] = payload.get("updated_at") or _utc_now()

    p = _autonomy_path(rid)

    with open(p, "w", encoding="utf-8", newline="\n") as f:

        json.dump(cur, f, ensure_ascii=False, indent=2)

    return cur



@app.get("/v1/agent/autonomy")

def agent_autonomy_get(request: Request, room_id: str = "default"):

    rid = str(room_id or "").strip()

    if not rid:

        try:

            rid = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

        except Exception:

            rid = ""

    rid = rid or "default"

    data = _autonomy_read(rid)

    return {

        "ok": True,

        "room_id": rid,

        "autonomy": data,

        "impl": "PATCH_P6_2_AUTONOMY_V1"

    }



@app.post("/v1/agent/autonomy")

def agent_autonomy_post(request: Request, req: dict = Body(...)):

    rid = "default"

    try:

        if isinstance(req, dict) and req.get("room_id"):

            rid = str(req.get("room_id") or "").strip() or "default"

    except Exception:

        rid = "default"

    if not rid or rid == "default":

        try:

            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

            if hdr:

                rid = hdr

        except Exception:

            pass

    rid = rid or "default"



    cur = _autonomy_read(rid)

    if isinstance(req, dict):

        if "enabled" in req:

            cur["enabled"] = bool(req.get("enabled"))

        if "max_auto_steps" in req:

            try:

                cur["max_auto_steps"] = max(1, int(req.get("max_auto_steps")))

            except Exception:

                pass

        if "require_approval_for_writes" in req:

            cur["require_approval_for_writes"] = bool(req.get("require_approval_for_writes"))



    cur["updated_at"] = _utc_now()

    cur = _autonomy_write(rid, cur)



    return {

        "ok": True,

        "room_id": rid,

        "autonomy": cur,

        "impl": "PATCH_P6_2_AUTONOMY_V1"

    }







# PATCH_P5_1_RAG_MIN_V1

def _rag_base_dir(room_id: str) -> str:

    try:

        base_dir = os.path.dirname(_ssot_plan_path(room_id))

    except Exception:

        base_dir = str(Path(r"C:\AI_VAULT\tmp_agent\state\rooms") / str(room_id or "default"))

    out = os.path.join(base_dir, "knowledge")

    os.makedirs(out, exist_ok=True)

    return out



def _rag_index_path(room_id: str) -> str:

    return os.path.join(_rag_base_dir(room_id), "rag_index.json")



def _rag_read_index(room_id: str) -> dict:

    rid = str(room_id or "default").strip() or "default"

    p = _rag_index_path(rid)

    base = {"room_id": rid, "docs": [], "updated_at": _utc_now()}

    try:

        if os.path.exists(p):

            with open(p, "r", encoding="utf-8") as f:

                data = json.load(f)

            if isinstance(data, dict):

                docs = data.get("docs")

                if not isinstance(docs, list):

                    docs = []

                return {

                    "room_id": rid,

                    "docs": docs,

                    "updated_at": data.get("updated_at") or _utc_now()

                }

    except Exception:

        pass

    return base



def _rag_write_index(room_id: str, payload: dict) -> dict:

    rid = str(room_id or "default").strip() or "default"

    docs = payload.get("docs") if isinstance(payload, dict) else []

    if not isinstance(docs, list):

        docs = []

    out = {

        "room_id": rid,

        "docs": docs,

        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else _utc_now()

    }

    if not out["updated_at"]:

        out["updated_at"] = _utc_now()

    p = _rag_index_path(rid)

    with open(p, "w", encoding="utf-8", newline="\n") as f:

        json.dump(out, f, ensure_ascii=False, indent=2)

    return out



def _rag_norm_text(x):

    if x is None:

        return ""

    x = str(x)

    x = x.replace("\r\n", "\n").replace("\r", "\n")

    return x.strip()



def _rag_tokens(x: str) -> list:

    try:

        import re as _re

        toks = _re.findall(r"[a-zA-Z0-9_]{2,}", str(x or "").lower())

        return toks

    except Exception:

        return []



def _rag_score(query: str, text: str) -> int:

    q = set(_rag_tokens(query))

    t = set(_rag_tokens(text))

    if not q or not t:

        return 0

    return len(q.intersection(t))



def _rag_make_doc(doc_in: dict, fallback_title: str = "", fallback_source: str = "") -> dict | None:

    if not isinstance(doc_in, dict):

        doc_in = {}

    title = str(doc_in.get("title") or fallback_title or "").strip()

    source = str(doc_in.get("source") or fallback_source or "").strip()

    content = _rag_norm_text(doc_in.get("content"))

    if not title:

        title = source or "untitled"

    if not content:

        return None

    doc_id = str(doc_in.get("doc_id") or "").strip()

    if not doc_id:

        doc_id = "D_" + hashlib.sha1(f"{title}|{source}|{content[:120]}".encode("utf-8")).hexdigest()[:12]

    return {

        "doc_id": doc_id,

        "title": title,

        "source": source,

        "content": content,

        "chars": len(content),

        "updated_at": _utc_now()

    }



@app.post("/v1/agent/rag/index")

def agent_rag_index(request: Request, req: dict = Body(...)):

    rid = "default"

    try:

        if isinstance(req, dict) and req.get("room_id"):

            rid = str(req.get("room_id") or "").strip() or "default"

    except Exception:

        rid = "default"

    if not rid or rid == "default":

        try:

            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

            if hdr:

                rid = hdr

        except Exception:

            pass

    rid = rid or "default"



    idx = _rag_read_index(rid)

    docs = idx.get("docs") if isinstance(idx.get("docs"), list) else []



    mode = "append"

    try:

        if isinstance(req, dict) and req.get("mode"):

            mode = str(req.get("mode") or "append").strip().lower() or "append"

    except Exception:

        mode = "append"



    if mode == "replace":

        docs = []



    added = []



    # source file

    if isinstance(req, dict) and req.get("path"):

        p = str(req.get("path") or "").strip()

        if p:

            try:

                full = Path(p)

                if full.exists() and full.is_file():

                    txt = full.read_text(encoding="utf-8", errors="replace")

                    doc = _rag_make_doc({"title": full.name, "source": str(full), "content": txt})

                    if doc:

                        docs = [d for d in docs if str(d.get("doc_id")) != doc["doc_id"]]

                        docs.append(doc)

                        added.append(doc["doc_id"])

            except Exception:

                pass



    # inline single doc

    if isinstance(req, dict) and isinstance(req.get("doc"), dict):

        d = _rag_make_doc(req.get("doc") or {})

        if d:

            docs = [x for x in docs if str(x.get("doc_id")) != d["doc_id"]]

            docs.append(d)

            added.append(d["doc_id"])



    # inline docs[]

    if isinstance(req, dict) and isinstance(req.get("docs"), list):

        for item in req.get("docs") or []:

            d = _rag_make_doc(item if isinstance(item, dict) else {})

            if d:

                docs = [x for x in docs if str(x.get("doc_id")) != d["doc_id"]]

                docs.append(d)

                added.append(d["doc_id"])



    idx["docs"] = docs

    idx["updated_at"] = _utc_now()

    idx = _rag_write_index(rid, idx)



    return {

        "ok": True,

        "room_id": rid,

        "added_doc_ids": added,

        "docs_count": len(idx["docs"]),

        "index": idx,

        "impl": "PATCH_P5_1_RAG_MIN_V1"

    }



@app.post("/v1/agent/rag/query")

def agent_rag_query(request: Request, req: dict = Body(...)):

    rid = "default"

    try:

        if isinstance(req, dict) and req.get("room_id"):

            rid = str(req.get("room_id") or "").strip() or "default"

    except Exception:

        rid = "default"

    if not rid or rid == "default":

        try:

            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

            if hdr:

                rid = hdr

        except Exception:

            pass

    rid = rid or "default"



    query = ""

    try:

        if isinstance(req, dict) and req.get("query"):

            query = str(req.get("query") or "").strip()

    except Exception:

        query = ""



    try:

        top_k = max(1, int(req.get("top_k", 3))) if isinstance(req, dict) else 3

    except Exception:

        top_k = 3



    idx = _rag_read_index(rid)

    docs = idx.get("docs") if isinstance(idx.get("docs"), list) else []



    scored = []

    for d in docs:

        content = str(d.get("content") or "")

        title = str(d.get("title") or "")

        source = str(d.get("source") or "")

        hay = f"{title}\n{source}\n{content}"

        sc = _rag_score(query, hay)

        if sc > 0 or not query:

            preview = content[:400]

            scored.append({

                "score": sc,

                "doc_id": d.get("doc_id"),

                "title": title,

                "source": source,

                "preview": preview,

                "chars": d.get("chars", len(content))

            })



    scored.sort(key=lambda x: (-int(x.get("score", 0)), str(x.get("title") or "")))

    results = scored[:top_k]



    return {

        "ok": True,

        "room_id": rid,

        "query": query,

        "top_k": top_k,

        "results": results,

        "docs_count": len(docs),

        "impl": "PATCH_P5_1_RAG_MIN_V1"

    }





# --- HARDENING9_PLANNER_POST_SSOT: POST /v1/agent/plan creates plan.json --------

# Active SSOT plan endpoint.

@app.post("/v1/agent/plan")

def agent_plan_create_ssot(request: Request, req: dict = Body(...)):

    """

    Planner SSOT mínimo (NO ejecuta).

    - Escribe plan.json por room: C:\\AI_VAULT\\tmp_agent\\state\\rooms\\<room_id>\\plan.json

    - Si req.steps viene, lo valida de forma mínima y lo usa.

    - Si no viene, crea 1 step default list_dir C:\\AI_VAULT.

    """

    # room_id: prioridad req.room_id -> header x-room-id -> default

    room_id = "default"

    # PATCH_PLAN_BIND_REQ_V2

    plan = req if isinstance(req, dict) else None



    # HARDENING_PLAN_HANDLER_CANONICAL_V1

    try:

        if isinstance(req, dict) and req.get("room_id"):

            room_id = str(req.get("room_id") or "").strip() or "default"

    except Exception:

        room_id = "default"

    if not room_id or room_id == "default":

        try:

            hdr = (request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "").strip()

            if hdr:

                room_id = hdr

        except Exception:

            pass

    room_id = room_id or "default"



    if isinstance(plan, dict):

        try:

            plan["room_id"] = room_id

        except Exception:

            pass

        _plan_norm, _plan_errs = _harden_plan_payload(plan)

        if _plan_errs:

            return {"ok": False, "error": "plan_validation_failed", "details": _plan_errs}

        plan = _plan_norm

        try:

            plan["room_id"] = room_id

        except Exception:

            pass



    # construir steps

    steps = None

    try:

        if isinstance(req, dict) and isinstance(req.get("steps"), list):

            steps = req.get("steps")

    except Exception:

        steps = None



    if steps is None:

        steps = [

            {"id": "1", "status": "todo", "tool_name": "list_dir", "tool_args": {"path": r"C:\AI_VAULT"}}

        ]



    # validación mínima + normalización ids/status

    norm_steps = []

    idx = 1

    for st in steps:

        if not isinstance(st, dict):

            continue

        sid = st.get("id") or st.get("step_id") or str(idx)

        sid = str(sid).strip() or str(idx)

        tool_name = str(st.get("tool_name") or "").strip()

        if not tool_name:

            continue

        tool_args = st.get("tool_args") if isinstance(st.get("tool_args"), dict) else (st.get("args") if isinstance(st.get("args"), dict) else {})

        tool_args = _p2_1_safe_tool_args(tool_name, tool_args)

        status = str(st.get("status") or "todo").strip().lower()

        if status not in {"todo","in_progress","proposed","done","error"}:

            status = "todo"

        norm_steps.append({"id": sid, "status": status, "tool_name": tool_name, "tool_args": tool_args})

        idx += 1



    plan = {

        "room_id": room_id,

        "status": "active",

        "steps": norm_steps,

        "updated_at": _utc_now() if "_utc_now" in globals() else datetime.now(timezone.utc).isoformat()

    }



    # SSOT write

    try:

        _ssot_write_plan(room_id, plan)

    except Exception as e:

        return {"ok": False, "room_id": room_id, "error": f"ssot_write_plan failed: {e}", "plan": plan}





    # HARDENING21_MISSION_PLANNER_SSOT: persist mission.json + append planner.ndjson (best-effort)

    try:

        import hashlib, json, os

        from datetime import datetime, timezone

        _mission = None

        try:

            if isinstance(req, dict) and isinstance(req.get("mission"), dict):

                _mission = dict(req.get("mission") or {})

        except Exception:

            _mission = None

    

        if isinstance(_mission, dict):

            _now = datetime.now(timezone.utc).isoformat()

            # enrich mission with room + timestamps (non-breaking)

            try:

                _mission.setdefault("room_id", plan.get("room_id") if isinstance(plan, dict) else None)

            except Exception:

                pass

            if not _mission.get("created_at"):

                _mission["created_at"] = _now

            _mission["updated_at"] = _now

    

            # resolve room dir from plan path if available

            try:

                _pp = _plan_path(room_id) if "_plan_path" in globals() else os.path.join(r"C:\AI_VAULT\tmp_agent","state","rooms",room_id,"plan.json")

            except Exception:

                _pp = os.path.join(r"C:\AI_VAULT\tmp_agent","state","rooms",room_id,"plan.json")

            _roomdir = os.path.dirname(_pp)

            os.makedirs(_roomdir, exist_ok=True)

    

            # mission.json

            _mp = os.path.join(_roomdir, "mission.json")

            with open(_mp, "w", encoding="utf-8") as _f:

                json.dump(_mission, _f, ensure_ascii=False, indent=2)

    

            # append planner.ndjson (evidence)

            try:

                _msha = hashlib.sha256(json.dumps(_mission, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

            except Exception:

                _msha = None

            try:

                _psha = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest() if isinstance(plan, dict) else None

            except Exception:

                _psha = None

    

            _plog = os.path.join(_roomdir, "planner.ndjson")

            _evt = {

                "ts": _now,

                "room_id": room_id,

                "event": "planner_plan_create",

                "mission_sha256": _msha,

                "plan_sha256": _psha,

            }

            with open(_plog, "a", encoding="utf-8") as _f:

                _f.write(json.dumps(_evt, ensure_ascii=False) + "\n")

    except Exception:

        pass



    return {"ok": True, "room_id": room_id, "plan": plan}

# --- /HARDENING9_PLANNER_POST_SSOT ---------------------------------------------





# --- HARDENING11_RUN_ENDPOINT: POST /v1/agent/run (multi-step) -------------------

# [DISABLED_DUP_RUN] @app.post("/v1/agent/run")

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



@app.post("/v1/agent/reject")

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



def _sanitize_episode_id(value: str) -> str:

    try:

        value = str(value or '').strip()

    except Exception:

        value = ''

    value = re.sub(r'[^a-zA-Z0-9_\-.]', '_', value)

    return value or ('ep_' + uuid.uuid4().hex[:12])





def _episode_envelope_path(room_id: str, episode_id: str) -> str:

    return os.path.join(_room_state_dir(room_id), f'episode_{_sanitize_episode_id(episode_id)}.json')





def _episode_observation_path(room_id: str, episode_id: str) -> str:

    return os.path.join(_room_state_dir(room_id), f'episode_observation_{_sanitize_episode_id(episode_id)}.json')





def _episode_snapshot_path(room_id: str, episode_id: str) -> str:

    return os.path.join(_room_state_dir(room_id), f'episode_snapshot_{_sanitize_episode_id(episode_id)}.json')





def _write_episode_target_snapshot(room_id: str, episode_id: str, payload: dict) -> str:

    payload = payload or {}

    proposal = payload.get('proposal') or {}

    tool_name = str(proposal.get('tool_name') or '').strip()

    if tool_name not in {'write_file', 'append_file'}:

        return ''

    tool_args = proposal.get('tool_args') or {}

    target_path = str((tool_args or {}).get('path') or '').strip()

    if not target_path:

        return ''

    try:

        target_resolved = str(Path(target_path).resolve())

        room_root = str(Path(_room_state_dir(room_id)).resolve())

        if not target_resolved.startswith(room_root):

            return ''

    except Exception:

        return ''



    existed_before = os.path.exists(target_resolved)

    snapshot = {

        'schema_version': 'episode_snapshot_v1',

        'recorded_utc': _utc_now(),

        'room_id': room_id,

        'episode_id': _sanitize_episode_id(episode_id),

        'target_path': target_resolved,

        'tool_name': tool_name,

        'existed_before': existed_before,

        'content_before': None,

    }

    if existed_before:

        try:

            with open(target_resolved, 'r', encoding='utf-8') as f:

                snapshot['content_before'] = f.read()

        except Exception:

            snapshot['content_before'] = None

    out_path = _episode_snapshot_path(room_id, episode_id)

    with open(out_path, 'w', encoding='utf-8') as f:

        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    return out_path





def _restore_episode_target_snapshot(snapshot_path: str) -> dict:

    snapshot = _read_json_file_safe(snapshot_path)

    if not snapshot:

        return {'ok': False, 'reason': 'snapshot_not_found'}

    target_path = str(snapshot.get('target_path') or '').strip()

    if not target_path:

        return {'ok': False, 'reason': 'snapshot_missing_target_path'}

    existed_before = bool(snapshot.get('existed_before'))

    try:

        if existed_before:

            with open(target_path, 'w', encoding='utf-8') as f:

                f.write(str(snapshot.get('content_before') or ''))

            return {'ok': True, 'reason': 'target_restored', 'target_path': target_path}

        if os.path.exists(target_path):

            os.remove(target_path)

        return {'ok': True, 'reason': 'target_removed', 'target_path': target_path}

    except Exception as e:

        return {'ok': False, 'reason': 'rollback_failed', 'target_path': target_path, 'error': str(e)}



def _seed_episode_plan_ssot(room_id: str, payload: dict) -> dict:

    payload = payload or {}

    plan = _ssot_read_plan(room_id) or {}

    if not isinstance(plan, dict):

        plan = {}



    approve_token = str(payload.get('approve_token') or '').strip()

    episode_id = _sanitize_episode_id(payload.get('episode_id'))

    phase_id = str(payload.get('phase_id') or payload.get('phase') or '').strip()

    roadmap_id = str(payload.get('roadmap_id') or '').strip()

    mission_id = str(payload.get('mission_id') or '').strip()

    proposal = payload.get('proposal') or {}

    tool_name = str(proposal.get('tool_name') or '').strip()

    tool_args = proposal.get('tool_args') or {}

    acceptance = proposal.get('acceptance') or []

    summary = str(proposal.get('summary') or '').strip()

    target_artifact = str(proposal.get('target_artifact') or '').strip()



    room_dir = _room_state_dir(room_id)

    os.makedirs(room_dir, exist_ok=True)



    envelope_doc = dict(payload)

    envelope_doc.setdefault('episode_id', episode_id)

    envelope_doc.setdefault('room_id', room_id)

    envelope_doc.setdefault('phase_id', phase_id)

    envelope_doc.setdefault('roadmap_id', roadmap_id)

    envelope_doc.setdefault('mission_id', mission_id)

    envelope_doc['saved_utc'] = _utc_now()

    with open(_episode_envelope_path(room_id, episode_id), 'w', encoding='utf-8') as f:

        json.dump(envelope_doc, f, ensure_ascii=False, indent=2)



    steps = _plan_steps_safe(plan)

    active_steps = [s for s in steps if isinstance(s, dict) and str(s.get('status') or '') in {'todo', 'in_progress', 'proposed'}]

    status = str(plan.get('status') or '').strip().lower()



    plan['room_id'] = room_id

    plan['episode_id'] = episode_id

    if phase_id:

        plan['phase_id'] = phase_id

    if roadmap_id:

        plan['roadmap_id'] = roadmap_id

    if mission_id:

        plan['mission_id'] = mission_id

    plan['updated_at'] = _utc_now()



    if approve_token and active_steps:

        _ssot_write_plan(room_id, plan)

        return plan



    if active_steps and status not in {'complete', 'error', 'failed', 'idle'}:

        _ssot_write_plan(room_id, plan)

        return plan



    if not tool_name:

        raise HTTPException(status_code=400, detail='proposal.tool_name is required when no active plan exists for the room')



    step_id = 'EP_' + _sanitize_episode_id(episode_id)[-12:]

    step = {

        'id': step_id,

        'status': 'todo',

        'tool_name': tool_name,

        'tool_args': tool_args if isinstance(tool_args, dict) else {},

        'episode_id': episode_id,

        'phase_id': phase_id,

        'roadmap_id': roadmap_id,

        'mission_id': mission_id,

        'summary': summary,

        'target_artifact': target_artifact,

        'acceptance': acceptance if isinstance(acceptance, list) else [str(acceptance)],

    }

    plan['status'] = 'active'

    plan['steps'] = [step]

    plan['source'] = 'episode_execute_v1'

    _ssot_write_plan(room_id, plan)

    try:

        _audit_append(room_id, 'episode_seeded', {'episode_id': episode_id, 'step_id': step_id, 'tool_name': tool_name, 'phase_id': phase_id})

    except Exception:

        pass

    return _ssot_read_plan(room_id) or plan







def _episode_programmatic_apply_allowed(room_id: str, payload: dict, plan: dict) -> dict:

    payload = payload or {}

    proposal = payload.get('proposal') or {}

    tool_name = str(proposal.get('tool_name') or '').strip()

    if not bool(payload.get('auto_apply_if_allowed')):

        return {'allowed': False, 'reason': 'auto_apply_not_requested'}

    if tool_name not in {'write_file', 'append_file'}:

        return {'allowed': False, 'reason': 'tool_not_programmatic_apply_safe'}

    tool_args = proposal.get('tool_args') or {}

    target_path = str((tool_args or {}).get('path') or '').strip()

    if not target_path:

        return {'allowed': False, 'reason': 'missing_target_path'}

    try:

        target_resolved = str(Path(target_path).resolve())

        room_root = str(Path(_room_state_dir(room_id)).resolve())

    except Exception:

        return {'allowed': False, 'reason': 'path_resolution_failed'}

    if not target_resolved.startswith(room_root):

        return {'allowed': False, 'reason': 'path_outside_room_scope', 'target_path': target_resolved}

    return {'allowed': True, 'reason': 'room_scoped_write_allowed', 'target_path': target_resolved}



def _execute_episode_payload_impl(room_id: str, payload: dict) -> dict:

    payload = payload or {}

    approve_token = str(payload.get('approve_token') or '').strip()

    episode_id = _sanitize_episode_id(payload.get('episode_id'))

    payload['room_id'] = room_id

    payload['episode_id'] = episode_id



    plan = _seed_episode_plan_ssot(room_id, payload)

    one = _run_one_step_ssot(room_id, approve_token=approve_token)

    plan2 = one.get('plan') or _ssot_read_plan(room_id) or plan

    last = one.get('last_result') if isinstance(one, dict) else None

    action = str(one.get('action') or '')

    requires_approval = bool(one.get('requires_approval'))

    out_token = one.get('approve_token')

    policy_decision = _episode_programmatic_apply_allowed(room_id, payload, plan2)

    rollback_snapshot = ''



    if out_token and requires_approval and bool(policy_decision.get('allowed')):

        rollback_snapshot = _write_episode_target_snapshot(room_id, episode_id, payload)

        auto_apply = _run_one_step_ssot(room_id, approve_token=str(out_token))

        plan2 = auto_apply.get('plan') or _ssot_read_plan(room_id) or plan2

        last = auto_apply.get('last_result') if isinstance(auto_apply, dict) else last

        action = 'auto_apply_step'

        requires_approval = False

        out_token = None

        one = auto_apply



    obs_status = 'ok'

    if not bool(one.get('ok', True)):

        obs_status = 'error'

    elif requires_approval or action in {'propose_write_step', 'propose_write_step_missing_token', 'requires_approval'}:

        obs_status = 'proposed'

    elif str((plan2 or {}).get('status') or '').strip().lower() == 'complete':

        obs_status = 'done'



    room_dir = _room_state_dir(room_id)

    artifacts = []

    try:

        artifacts = sorted([

            name for name in os.listdir(room_dir)

            if name.endswith('.json') and name not in {'plan.json', 'mission.json'}

        ])

    except Exception:

        artifacts = []



    phase_value = str(payload.get('phase_id') or payload.get('phase') or '').strip()

    next_action = 'apply_with_approve_token' if out_token else ('continue_episode_loop' if bool(one.get('ok', True)) else 'inspect_failure_and_replan')

    observation = {

        'episode_id': episode_id,

        'room_id': room_id,

        'phase_id': phase_value,

        'status': obs_status,

        'action': action,

        'artifacts': artifacts,

        'approve_token': out_token,

        'failure_code': (last or {}).get('error') if isinstance(last, dict) else None,

        'diff_summary': str((last or {}).get('error') or (last or {}).get('result') or action),

        'stdout_tail': [],

        'stderr_tail': [],

        'policy_decision': policy_decision,

        'rollback_snapshot': rollback_snapshot or None,

        'next_recommended_action': next_action,

        'recorded_utc': _utc_now(),

    }

    reinjection_payload = {

        'episode_id': episode_id,

        'room_id': room_id,

        'phase_id': phase_value,

        'roadmap_id': str(payload.get('roadmap_id') or '').strip(),

        'mission_id': str(payload.get('mission_id') or '').strip(),

        'proposal_summary': str(((payload.get('proposal') or {}).get('summary') or '')).strip(),

        'observation': observation,

        'planner_input_contract': {

            'use_as': 'next_planning_turn_input',

            'required_focus': ['status','artifacts','diff_summary','failure_code','next_recommended_action'],

            'goal': 'Decide the next bounded action from the previous episode evidence.'

        }

    }



    with open(_episode_observation_path(room_id, episode_id), 'w', encoding='utf-8') as f:

        json.dump(observation, f, ensure_ascii=False, indent=2)

    with open(os.path.join(room_dir, f'reinjection_payload_{_sanitize_episode_id(episode_id)}.json'), 'w', encoding='utf-8') as f:

        json.dump(reinjection_payload, f, ensure_ascii=False, indent=2)



    try:

        _audit_append(room_id, 'episode_execute_result', {'episode_id': episode_id, 'action': action, 'ok': bool(one.get('ok', True)), 'status': obs_status, 'next_recommended_action': next_action})

    except Exception:

        pass



    return {

        'ok': bool(one.get('ok', True)),

        'room_id': room_id,

        'episode_id': episode_id,

        'action': action,

        'requires_approval': requires_approval,

        'approve_token': out_token,

        'plan': plan2,

        'observation': observation,

        'reinjection_payload': reinjection_payload,

        'last_result': last,

        'error': (last or {}).get('error') if isinstance(last, dict) else None,

    }

@app.post('/v1/agent/episode/execute')

def agent_episode_execute(request: Request, payload: Dict[str, Any] = Body(...)):

    payload = payload or {}

    room_id = _safe_room_id(str(payload.get('room_id') or request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or 'default'))

    return _execute_episode_payload_impl(room_id, payload)



def _latest_reinjection_payload_path(room_id: str) -> str:

    room_dir = _room_state_dir(room_id)

    try:

        cands = [os.path.join(room_dir, n) for n in os.listdir(room_dir) if str(n).startswith('reinjection_payload_') and str(n).endswith('.json')]

        if not cands:

            return ''

        cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        return cands[0]

    except Exception:

        return ''





def _read_json_file_safe(path: str) -> dict:

    try:

        if not path or not os.path.exists(path):

            return {}

        with open(path, 'r', encoding='utf-8') as f:

            data = json.load(f) or {}

        return data if isinstance(data, dict) else {}

    except Exception:

        return {}





@app.post('/v1/agent/backlog/synthesize')

def agent_backlog_synthesize(request: Request, payload: Dict[str, Any] = Body(...)):

    payload = payload or {}

    room_id = _safe_room_id(str(payload.get('room_id') or request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or 'default'))

    room_dir = _room_state_dir(room_id)

    evidence_path = str(payload.get('reinjection_payload_path') or '').strip()

    if not evidence_path:

        evidence_path = _latest_reinjection_payload_path(room_id)

    evidence = _read_json_file_safe(evidence_path)

    if not evidence:

        alt_room = str(payload.get('source_room_id') or '').strip()

        if alt_room:

            evidence_path = _latest_reinjection_payload_path(alt_room)

            evidence = _read_json_file_safe(evidence_path)



    if not evidence:

        return {

            'ok': False,

            'room_id': room_id,

            'action': 'no_reinjection_payload',

            'error': 'reinjection payload not found',

            'backlog': [],

        }



    observation = evidence.get('observation') or {}

    next_action = str((observation or {}).get('next_recommended_action') or 'inspect_failure_and_replan').strip()

    summary = str(evidence.get('proposal_summary') or '').strip()

    phase_id = str(evidence.get('phase_id') or '').strip() or str(payload.get('phase_id') or '').strip()

    roadmap_id = str(evidence.get('roadmap_id') or '').strip()

    mission_id = str(evidence.get('mission_id') or '').strip()

    artifacts = observation.get('artifacts') or []

    failure_code = observation.get('failure_code') if isinstance(observation, dict) else None



    backlog = []

    backlog.append({

        'id': 'BLG_' + uuid.uuid4().hex[:10],

        'kind': 'next_action',

        'title': f'Execute recommended action: {next_action}',

        'status': 'todo' if not failure_code else 'blocked',

        'confidence': 'high' if not failure_code else 'medium',

        'evidence_path': evidence_path,

        'evidence_artifacts': artifacts,

        'summary': summary,

        'recommended_action': next_action,

        'failure_code': failure_code,

    })

    if failure_code:

        backlog.append({

            'id': 'BLG_' + uuid.uuid4().hex[:10],

            'kind': 'recovery',

            'title': f'Investigate and recover from {failure_code}',

            'status': 'todo',

            'confidence': 'medium',

            'evidence_path': evidence_path,

            'summary': str((observation or {}).get('diff_summary') or ''),

        })



    synthesis = {

        'schema_version': 'backlog_synthesis_v1',

        'generated_utc': _utc_now(),

        'room_id': room_id,

        'phase_id': phase_id,

        'roadmap_id': roadmap_id,

        'mission_id': mission_id,

        'source_reinjection_payload': evidence_path,

        'backlog': backlog[:3],

    }

    out_path = os.path.join(room_dir, 'backlog_synthesis.json')

    with open(out_path, 'w', encoding='utf-8') as f:

        json.dump(synthesis, f, ensure_ascii=False, indent=2)

    try:

        _audit_append(room_id, 'backlog_synthesized', {'phase_id': phase_id, 'count': len(synthesis['backlog']), 'source_reinjection_payload': evidence_path})

    except Exception:

        pass

    return {

        'ok': True,

        'room_id': room_id,

        'action': 'backlog_synthesized',

        'backlog': synthesis['backlog'],

        'artifact': out_path,

        'source_reinjection_payload': evidence_path,

    }



@app.post('/v1/agent/episode/validate')

def agent_episode_validate(request: Request, payload: Dict[str, Any] = Body(...)):

    payload = payload or {}

    room_id = _safe_room_id(str(payload.get('room_id') or request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or 'default'))

    episode_id = _sanitize_episode_id(payload.get('episode_id'))

    room_dir = _room_state_dir(room_id)

    observation = _read_json_file_safe(_episode_observation_path(room_id, episode_id))

    envelope = _read_json_file_safe(_episode_envelope_path(room_id, episode_id))

    plan = _ssot_read_plan(room_id) or {}

    snapshot_path = _episode_snapshot_path(room_id, episode_id)

    proposal = envelope.get('proposal') or {}

    tool_args = proposal.get('tool_args') or {}

    target_path = str(payload.get('target_path') or ((observation.get('policy_decision') or {}).get('target_path') if isinstance(observation, dict) else '') or (tool_args.get('path') if isinstance(tool_args, dict) else '') or '').strip()



    checks = []

    target_exists = bool(target_path and os.path.exists(target_path))

    checks.append({'id': 'target_path_present', 'ok': bool(target_path), 'detail': target_path or 'missing'})

    checks.append({'id': 'target_exists', 'ok': target_exists, 'detail': target_path or 'missing'})

    checks.append({'id': 'observation_present', 'ok': bool(observation), 'detail': _episode_observation_path(room_id, episode_id)})

    checks.append({'id': 'snapshot_present', 'ok': os.path.exists(snapshot_path), 'detail': snapshot_path})

    checks.append({'id': 'room_dir_present', 'ok': os.path.isdir(room_dir), 'detail': room_dir})

    checks.append({'id': 'plan_present', 'ok': isinstance(plan, dict) and bool(plan), 'detail': os.path.join(room_dir, 'plan.json')})



    validation_ok = all(bool(c.get('ok')) for c in checks if str(c.get('id')) not in {'snapshot_present'})

    rollback_requested = bool(payload.get('rollback_on_failure')) and not validation_ok

    force_rollback = bool(payload.get('force_rollback'))

    rollback_result = None

    rollback_performed = False



    if rollback_requested or force_rollback:

        rollback_result = _restore_episode_target_snapshot(snapshot_path)

        rollback_performed = bool((rollback_result or {}).get('ok'))



    report = {

        'schema_version': 'episode_validation_report_v1',

        'recorded_utc': _utc_now(),

        'room_id': room_id,

        'episode_id': episode_id,

        'phase_id': str(payload.get('phase_id') or envelope.get('phase_id') or '').strip(),

        'status': 'ok' if validation_ok and not rollback_performed else ('rolled_back' if rollback_performed else 'error'),

        'validation_ok': validation_ok,

        'checks': checks,

        'target_path': target_path,

        'rollback_requested': rollback_requested,

        'force_rollback': force_rollback,

        'rollback_performed': rollback_performed,

        'rollback_result': rollback_result,

        'snapshot_path': snapshot_path if os.path.exists(snapshot_path) else '',

    }

    report_path = os.path.join(room_dir, f'episode_validation_{episode_id}.json')

    with open(report_path, 'w', encoding='utf-8') as f:

        json.dump(report, f, ensure_ascii=False, indent=2)

    if rollback_performed:

        rollback_path = os.path.join(room_dir, f'episode_rollback_{episode_id}.json')

        with open(rollback_path, 'w', encoding='utf-8') as f:

            json.dump(rollback_result or {}, f, ensure_ascii=False, indent=2)

    try:

        _audit_append(room_id, 'episode_validation_result', {'episode_id': episode_id, 'validation_ok': validation_ok, 'rollback_performed': rollback_performed, 'target_path': target_path})

    except Exception:

        pass

    return {

        'ok': validation_ok or rollback_performed,

        'room_id': room_id,

        'episode_id': episode_id,

        'action': 'episode_validated',

        'report': report,

        'artifact': report_path,

    }

def _derive_unattended_episode_payload(room_id: str, phase_id: str, cycle_index: int, previous_reinjection: dict, base_payload: dict) -> dict:

    prev_obs = (previous_reinjection or {}).get('observation') or {}

    prev_summary = str((previous_reinjection or {}).get('proposal_summary') or '').strip()

    summary_path = os.path.join(_room_state_dir(room_id), 'unattended_cycle_summary.txt')

    if cycle_index == 2:

        return {

            'room_id': room_id,

            'phase_id': phase_id,

            'roadmap_id': str(base_payload.get('roadmap_id') or '').strip(),

            'mission_id': str(base_payload.get('mission_id') or '').strip(),

            'episode_id': f"{_sanitize_episode_id(base_payload.get('episode_id'))}_c02",

            'proposal': {

                'summary': f"Persist unattended loop state after {prev_summary or 'initial cycle'}",

                'tool_name': 'runtime_snapshot_set',

                'tool_args': {

                    'key': 'ap07_cycle_02_state',

                    'value': {

                        'previous_status': str(prev_obs.get('status') or ''),

                        'previous_action': str(prev_obs.get('action') or ''),

                        'source_episode': str(previous_reinjection.get('episode_id') or ''),

                    }

                },

                'acceptance': ['runtime snapshot persisted for unattended cycle 2'],

                'target_artifact': 'runtime_snapshot.json'

            }

        }

    if cycle_index == 3:

        lines = [

            'AP-07 unattended cycle summary',

            f"previous_episode={str(previous_reinjection.get('episode_id') or '')}",

            f"previous_status={str(prev_obs.get('status') or '')}",

            f"previous_action={str(prev_obs.get('action') or '')}",

        ]

        return {

            'room_id': room_id,

            'phase_id': phase_id,

            'roadmap_id': str(base_payload.get('roadmap_id') or '').strip(),

            'mission_id': str(base_payload.get('mission_id') or '').strip(),

            'episode_id': f"{_sanitize_episode_id(base_payload.get('episode_id'))}_c03",

            'auto_apply_if_allowed': True,

            'proposal': {

                'summary': 'Write unattended cycle summary artifact from prior observation',

                'tool_name': 'write_file',

                'tool_args': {

                    'path': summary_path,

                    'content': "\n".join(lines) + "\n"

                },

                'acceptance': ['summary artifact written for unattended cycle 3'],

                'target_artifact': 'unattended_cycle_summary.txt'

            }

        }

    return {

        'room_id': room_id,

        'phase_id': phase_id,

        'roadmap_id': str(base_payload.get('roadmap_id') or '').strip(),

        'mission_id': str(base_payload.get('mission_id') or '').strip(),

        'episode_id': f"{_sanitize_episode_id(base_payload.get('episode_id'))}_c{cycle_index:02d}",

        'auto_apply_if_allowed': True,

        'proposal': {

            'summary': f'Append unattended cycle {cycle_index} heartbeat to summary artifact',

            'tool_name': 'append_file',

            'tool_args': {

                'path': summary_path,

                'content': f"cycle={cycle_index} status={str(prev_obs.get('status') or '')} action={str(prev_obs.get('action') or '')}\n"

            },

            'acceptance': [f'summary artifact appended for unattended cycle {cycle_index}'],

            'target_artifact': 'unattended_cycle_summary.txt'

        }

    }





@app.post('/v1/agent/loop/unattended_cycle')

def agent_loop_unattended_cycle(request: Request, payload: Dict[str, Any] = Body(...)):

    payload = payload or {}

    room_id = _safe_room_id(str(payload.get('room_id') or request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or 'default'))

    phase_id = str(payload.get('phase_id') or payload.get('phase') or 'AP-07').strip()

    max_cycles = max(1, min(int(payload.get('max_cycles') or 3), 6))

    base_payload = dict(payload)

    base_payload['room_id'] = room_id

    cycles = []

    current_payload = dict(base_payload)

    current_payload.setdefault('episode_id', 'ap07_unattended_seed')

    current_payload.setdefault('auto_apply_if_allowed', True)

    if not isinstance(current_payload.get('proposal'), dict):

        current_payload['proposal'] = {

            'summary': 'Seed unattended cycle room with autonomous baseline artifact',

            'tool_name': 'write_file',

            'tool_args': {

                'path': os.path.join(_room_state_dir(room_id), 'ap07_unattended_seed.txt'),

                'content': 'seed unattended cycle\n'

            },

            'acceptance': ['seed artifact written inside room scope'],

            'target_artifact': 'ap07_unattended_seed.txt'

        }

    previous_reinjection = {}

    for idx in range(1, max_cycles + 1):

        if idx > 1:

            current_payload = _derive_unattended_episode_payload(room_id, phase_id, idx, previous_reinjection, base_payload)

        result = _execute_episode_payload_impl(room_id, current_payload)

        cycle_entry = {

            'cycle_index': idx,

            'episode_id': str(result.get('episode_id') or ''),

            'action': str(result.get('action') or ''),

            'status': str(((result.get('observation') or {}).get('status') or '')),

            'ok': bool(result.get('ok', False)),

            'artifacts': list(((result.get('observation') or {}).get('artifacts') or [])),

            'next_recommended_action': str((((result.get('reinjection_payload') or {}).get('observation') or {}).get('next_recommended_action') or '')),

        }

        cycles.append(cycle_entry)

        previous_reinjection = result.get('reinjection_payload') or {}

        if not bool(result.get('ok', False)):

            break



    report = {

        'schema_version': 'unattended_cycle_execution_v1',

        'generated_utc': _utc_now(),

        'room_id': room_id,

        'phase_id': phase_id,

        'requested_cycles': max_cycles,

        'completed_cycles': len(cycles),

        'all_ok': all(bool(c.get('ok')) for c in cycles),

        'cycles': cycles,

        'latest_reinjection_payload': _latest_reinjection_payload_path(room_id),

    }

    report_path = os.path.join(_room_state_dir(room_id), 'unattended_cycle_execution.json')

    with open(report_path, 'w', encoding='utf-8') as f:

        json.dump(report, f, ensure_ascii=False, indent=2)

    try:

        _audit_append(room_id, 'unattended_cycle_completed', {'phase_id': phase_id, 'completed_cycles': len(cycles), 'all_ok': bool(report.get('all_ok'))})

    except Exception:

        pass

    return {

        'ok': bool(report.get('all_ok')),

        'room_id': room_id,

        'action': 'unattended_cycle_completed',

        'report': report,

        'artifact': report_path,

    }

# Active SSOT run_once endpoint.

@app.post("/v1/agent/run_once", response_model=AgentRunOnceResponse)

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

    try:

        with open(pp, "r", encoding="utf-8") as f:

            return json.load(f) or {}

    except Exception:

        return {}



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



def _persist_step_result_ssot(room_id: str, plan: dict) -> None:

    plan["updated_at"] = _utc_now()

    plan.setdefault("room_id", room_id)



    try:

        steps_all = plan.get("steps", []) or []

        pending = [x for x in steps_all if isinstance(x, dict) and str(x.get("status")) in {"todo", "in_progress", "proposed"}]

        if not pending:

            plan["status"] = "complete"

    except Exception:

        pass



    _ssot_write_plan(room_id, plan)



# Active SSOT step runner used by run_once.

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



    # runtime snapshot tools are room-scoped state ops and do not require apply.

    if tool_name in ("runtime_snapshot_set", "runtime_snapshot_get"):

        if mode == "apply":

            return {"ok": False, "room_id": room_id, "step_id": step_id, "error": f"apply not supported for {tool_name}"}



        snap_path = ""

        if isinstance(tool_args, dict):

            snap_path = str(tool_args.get("path") or "")



        try:

            if tool_name == "runtime_snapshot_set":

                value = tool_args.get("value") if isinstance(tool_args, dict) else None

                if isinstance(value, dict):

                    value = dict(value)

                    value.setdefault("room_id", room_id)

                    value.setdefault("ts", _utc_now())

                out = _runtime_snapshot_set_kv(room_id, snap_path, value)

            else:

                out = _runtime_snapshot_get_kv(room_id, snap_path)

        except Exception as e:

            out = {"ok": False, "error": f"{tool_name} failed: {e}", "args": tool_args}



        step["result"] = out

        step["status"] = "done" if out.get("ok") else "error"

        _persist_step_result_ssot(room_id, plan)

        return {"ok": bool(out.get("ok")), "room_id": room_id, "step_id": step_id, "result": out}

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

        _persist_step_result_ssot(room_id, plan)



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

    _persist_step_result_ssot(room_id, plan)



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

def agent_apply_ssot(request: Request, req: dict = Body(...)):

    """

    Apply SSOT (canonical):

      - input: {room_id?, approve_token, step_id?}

      - resolves step_id from plan.json.required_approve == approve_token

      - executes apply via _SAFE_INTERNAL_EXECUTE_STEP (signature-safe)

      - writes evaluation.json and evaluations.ndjson on each apply attempt

      - returns updated plan (SSOT)

    """

    import os, json, types

    from datetime import datetime, timezone



    impl = "HARDENING12_APPLY_ENDPOINT_SSOT_EVAL_V1"



    def _now_iso_apply_eval():

        try:

            return datetime.now(timezone.utc).isoformat()

        except Exception:

            return ""



    def _room_dir_apply_eval(_room_id: str) -> str:

        try:

            fn = globals().get("_room_dir")

            if callable(fn):

                return str(fn(_room_id))

        except Exception:

            pass

        return os.path.join(r"C:\AI_VAULT\tmp_agent", "state", "rooms", str(_room_id or "default"))



    def _plan_path_apply_eval(_room_id: str) -> str:

        try:

            fn = globals().get("_plan_path")

            if callable(fn):

                return str(fn(_room_id))

        except Exception:

            pass

        return os.path.join(_room_dir_apply_eval(_room_id), "plan.json")



    def _read_plan_apply_eval(_room_id: str):

        try:

            fn = globals().get("_read_plan")

            if callable(fn):

                return fn(_room_id)

        except Exception:

            pass

        try:

            pp = _plan_path_apply_eval(_room_id)

            if os.path.exists(pp):

                with open(pp, "r", encoding="utf-8") as f:

                    return json.load(f)

        except Exception:

            pass

        return {}



    def _safe_write_json_apply_eval(path: str, obj: dict):

        tmp = path + ".tmp"

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(tmp, "w", encoding="utf-8", newline="\n") as f:

            json.dump(obj, f, ensure_ascii=False, indent=2)

            f.write("\n")

        os.replace(tmp, path)



    def _safe_append_ndjson_apply_eval(path: str, obj: dict):

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "a", encoding="utf-8", newline="\n") as f:

            f.write(json.dumps(obj, ensure_ascii=False) + "\n")



    def _safe_audit_apply_eval(_room_id: str, event: str, extra: dict):

        try:

            fn = globals().get("_audit_append")

            if callable(fn):

                fn(_room_id, event, extra)

        except Exception:

            pass



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



    step_id = None

    try:

        plan = _read_plan_apply_eval(room_id) or {}

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



    def _call_exec_step(_room_id, _step_id, mode, approve_token=None):

        fn_local = globals().get("_SAFE_INTERNAL_EXECUTE_STEP")

        if not callable(fn_local):

            return {"ok": False, "error": "_SAFE_INTERNAL_EXECUTE_STEP not found/callable"}



        payload = {

            "room_id": _room_id,

            "step_id": _step_id,

            "mode": mode,

            "approve_token": approve_token,

            "rid": _room_id,

            "room": _room_id,

            "roomId": _room_id,

            "x_room_id": _room_id,

            "id": _step_id,

            "step": _step_id,

            "stepId": _step_id,

            "action": mode,

            "op": mode,

            "approve": approve_token,

            "token": approve_token,

            "required_approve": approve_token,

            "approval_token": approve_token,

        }



        try:

            req_obj = types.SimpleNamespace(**payload)

            return fn_local(req_obj)

        except TypeError as e:

            return {"ok": False, "error": f"executor_typeerror: {e}", "payload": payload}

        except Exception as e:

            return {"ok": False, "error": f"executor_exception: {e}", "payload": payload}



    res = _call_exec_step(room_id, step_id, mode="apply", approve_token=approve)



    plan_after = {}

    try:

        plan_after = _read_plan_apply_eval(room_id) or {}

    except Exception:

        plan_after = {}



    out = {

        "ok": bool(res.get("ok", False)) if isinstance(res, dict) else False,

        "room_id": room_id,

        "step_id": step_id,

        "result": res,

        "plan": plan_after,

        "impl": impl,

    }



    try:

        _safe_audit_apply_eval(room_id, "apply_result", {

            "ok": (out.get("ok") if isinstance(out, dict) else None),

            "proposal_id": (approve.replace("APPLY_", "", 1) if isinstance(approve, str) and approve.startswith("APPLY_") else None),

            "step_id": step_id,

        })

    except Exception:

        pass



    try:

        room_dir = _room_dir_apply_eval(room_id)

        plan_path = _plan_path_apply_eval(room_id)

        audit_path = os.path.join(room_dir, "audit.ndjson")

        eval_json_path = os.path.join(room_dir, "evaluation.json")

        eval_ndjson_path = os.path.join(room_dir, "evaluations.ndjson")

        proposal_id = approve.replace("APPLY_", "", 1) if isinstance(approve, str) and approve.startswith("APPLY_") else None



        steps = list((plan_after or {}).get("steps") or [])

        blocked = None

        try:

            fb = globals().get("_find_blocked")

            if callable(fb):

                blocked = fb(plan_after or {})

        except Exception:

            blocked = None



        files_present = []

        try:

            if os.path.isdir(room_dir):

                files_present = sorted(os.listdir(room_dir))

        except Exception:

            files_present = []



        eval_obj = {

            "ts": _now_iso_apply_eval(),

            "impl": impl,

            "ok": bool(out.get("ok", False)),

            "room_id": room_id,

            "step_id": step_id,

            "proposal_id": proposal_id,

            "approve_token": approve,

            "plan_status": (plan_after.get("status") if isinstance(plan_after, dict) else None),

            "steps_total": len(steps),

            "counts": {

                "done": sum(1 for s in steps if isinstance(s, dict) and str(s.get("status") or "") == "done"),

                "proposed": sum(1 for s in steps if isinstance(s, dict) and str(s.get("status") or "") == "proposed"),

                "error": sum(1 for s in steps if isinstance(s, dict) and str(s.get("status") or "") == "error"),

            },

            "blocked": blocked,

            "result_ok": (res.get("ok") if isinstance(res, dict) else None),

            "result_via": (res.get("via") if isinstance(res, dict) else None),

            "result_error": (res.get("error") if isinstance(res, dict) else None),

            "artifact_checks": {

                "plan_json_exists": os.path.exists(plan_path),

                "audit_ndjson_exists": os.path.exists(audit_path),

                "probe_txt_exists": os.path.exists(os.path.join(room_dir, "probe.txt")),

                "files_present": files_present,

            },

        }



        _safe_write_json_apply_eval(eval_json_path, eval_obj)

        _safe_append_ndjson_apply_eval(eval_ndjson_path, eval_obj)



        try:

            _safe_audit_apply_eval(room_id, "evaluation_result", {

                "ok": bool(eval_obj.get("ok", False)),

                "step_id": step_id,

                "proposal_id": proposal_id,

                "plan_status": eval_obj.get("plan_status"),

                "result_ok": eval_obj.get("result_ok"),

            })

        except Exception:

            pass

    except Exception:

        pass



    return out





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

























































# === AUTOBUILD_DASHBOARD_CONTROL_TOWER_V1 BEGIN ===

from pathlib import Path as _ABDPath

import json as _abd_json



_ABD_STATE_ROOT = _ABDPath(r"C:\AI_VAULT\tmp_agent\state")

_ABD_OPS_ROOT = _ABDPath(r"C:\AI_VAULT\tmp_agent\ops")

_ABD_ROOMS_ROOT = _ABD_STATE_ROOT / "rooms"

_ABD_ROADMAP_PATH = _ABD_STATE_ROOT / "roadmap.json"

_ABD_ROUTE_LOCK_PATH = _ABD_STATE_ROOT / "brain_route_lock.json"

_ABD_RUNNER_STATE_PATH = _ABD_STATE_ROOT / "autobuild_runner_state.json"



def _abd_now_utc():

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _abd_read_text(path):

    try:

        p = _ABDPath(path)

        if not p.exists():

            return None

        return p.read_text(encoding="utf-8-sig")

    except Exception:

        return None



def _abd_read_json(path, default=None):

    try:

        txt = _abd_read_text(path)

        if txt is None:

            return default

        return _abd_json.loads(txt)

    except Exception as e:

        if default is not None:

            return default

        return {"_error": str(e), "_path": str(path)}



def _abd_list_dirs(root, prefix, limit=20):

    try:

        xs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]

        xs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return xs[:limit]

    except Exception:

        return []



def _abd_latest_room(prefix):

    xs = _abd_list_dirs(_ABD_ROOMS_ROOT, prefix, limit=1)

    return xs[0] if xs else None



def _abd_latest_ops(prefix):

    xs = _abd_list_dirs(_ABD_OPS_ROOT, prefix, limit=1)

    return xs[0] if xs else None



def _abd_roadmap_counts(roadmap):

    work_items = roadmap.get("work_items") or []

    counts = {

        "total": len(work_items),

        "done": 0,

        "in_progress": 0,

        "blocked": 0,

        "pending": 0

    }

    for item in work_items:

        st = str(item.get("status") or "").strip().lower()

        if st in ("done", "complete", "completed"):

            counts["done"] += 1

        elif st in ("in_progress", "active", "started"):

            counts["in_progress"] += 1

        elif st in ("blocked", "error", "failed"):

            counts["blocked"] += 1

        else:

            counts["pending"] += 1

    return counts



def _abd_latest_v17():

    room = _abd_latest_room("autoloop_advisor_v10_")

    if not room:

        return None

    v17 = room / "autoloop_v17_effective_success.json"

    if v17.exists():

        data = _abd_read_json(v17, default={}) or {}

        data["_room"] = str(room)

        data["_path"] = str(v17)

        return data

    return None



def _abd_latest_v12_decision():

    room = _abd_latest_room("autoloop_advisor_v10_")

    if not room:

        return None

    p = room / "autoloop_v12_decision.json"

    if p.exists():

        data = _abd_read_json(p, default={}) or {}

        data["_room"] = str(room)

        data["_path"] = str(p)

        return data

    return None



def _abd_latest_runner_summary():

    d = _abd_latest_ops("autobuild_roadmap_runner_v1_")

    if not d:

        return None

    p = d / "99_summary.json"

    if not p.exists():

        return None

    data = _abd_read_json(p, default={}) or {}

    data["_dir"] = str(d)

    data["_path"] = str(p)

    return data



def _abd_collect_cycles(limit=25):

    out = []

    for d in _abd_list_dirs(_ABD_OPS_ROOT, "autobuild_roadmap_runner_v1_", limit=30):

        s = _abd_read_json(d / "99_summary.json", default={}) or {}

        cycles = s.get("cycles") or []

        ts = s.get("ts_utc")

        run_id = s.get("run_id") or d.name

        for c in cycles:

            row = {

                "run_id": run_id,

                "ts_utc": ts,

                "cycle": c.get("cycle"),

                "item": c.get("item"),

                "executor_exit": c.get("executor_exit"),

                "base_room": c.get("base_room"),

                "v17_json": c.get("v17_json"),

                "ok": c.get("ok"),

                "mode": c.get("mode"),

                "artifact_path": c.get("artifact_path"),

                "artifact_ok": c.get("artifact_ok"),

            }

            out.append(row)

            if len(out) >= limit:

                return out

    return out



def _abd_collect_deviations(limit=25):

    out = []

    rooms = _abd_list_dirs(_ABD_ROOMS_ROOT, "autoloop_advisor_v10_", limit=50)

    for room in rooms:

        decision = _abd_read_json(room / "autoloop_v12_decision.json", default={}) or {}

        v17 = _abd_read_json(room / "autoloop_v17_effective_success.json", default={}) or {}

        if decision:

            if decision.get("apply_request_integrity_ok") is False:

                out.append({

                    "severity": "high",

                    "kind": "artifact_integrity",

                    "room": str(room),

                    "detail": decision.get("apply_request_integrity_why"),

                    "auto_resolved": bool(v17.get("ok"))

                })

            if decision.get("needs_bridge") is True:

                out.append({

                    "severity": "medium",

                    "kind": "bridge_fallback_needed",

                    "room": str(room),

                    "detail": "base artifact no íntegro; se requirió bridge",

                    "auto_resolved": bool(v17.get("ok"))

                })

        if v17 and v17.get("ok") is not True:

            out.append({

                "severity": "high",

                "kind": "effective_result_failed",

                "room": str(room),

                "detail": v17.get("notes"),

                "auto_resolved": False

            })

        if len(out) >= limit:

            break

    return out[:limit]



@app.get("/v1/agent/dashboard/summary")

def agent_dashboard_summary():

    roadmap = _abd_read_json(_ABD_ROADMAP_PATH, default={}) or {}

    route_lock = _abd_read_json(_ABD_ROUTE_LOCK_PATH, default={}) or {}

    runner_state = _abd_read_json(_ABD_RUNNER_STATE_PATH, default={}) or {}

    latest_runner = _abd_latest_runner_summary() or {}

    latest_v17 = _abd_latest_v17() or {}

    latest_v12 = _abd_latest_v12_decision() or {}

    return {

        "ok": True,

        "ts_utc": _abd_now_utc(),

        "roadmap_counts": _abd_roadmap_counts(roadmap),

        "latest_runner": latest_runner,

        "latest_v17": latest_v17,

        "latest_v12_decision": latest_v12,

        "runner_state": runner_state,

        "route_lock": {

            "path": str(_ABD_ROUTE_LOCK_PATH),

            "objective_primary": route_lock.get("objective_primary"),

            "current_focus": route_lock.get("current_build_focus"),

            "next_checkpoint": route_lock.get("next_checkpoint"),

        },

        "urls": {

            "dashboard_html": "/ui/autobuild-dashboard",

            "summary": "/v1/agent/dashboard/summary",

            "roadmap": "/v1/agent/dashboard/roadmap",

            "cycles": "/v1/agent/dashboard/cycles",

            "deviations": "/v1/agent/dashboard/deviations",

            "route": "/v1/agent/dashboard/route",

        }

    }



@app.get("/v1/agent/dashboard/roadmap")

def agent_dashboard_roadmap():

    roadmap = _abd_read_json(_ABD_ROADMAP_PATH, default={}) or {}

    work_items = roadmap.get("work_items") or []

    work_items = sorted(work_items, key=lambda x: (x.get("priority", 999), str(x.get("id") or "")))

    pending = [x for x in work_items if str(x.get("status") or "").lower() not in ("done","complete","completed")]

    return {

        "ok": True,

        "ts_utc": _abd_now_utc(),

        "path": str(_ABD_ROADMAP_PATH),

        "objective": roadmap.get("objective"),

        "philosophy": roadmap.get("philosophy"),

        "counts": _abd_roadmap_counts(roadmap),

        "work_items": work_items,

        "pending": pending

    }



@app.get("/v1/agent/dashboard/cycles")

def agent_dashboard_cycles(limit: int = 25):

    limit = max(1, min(int(limit), 100))

    return {

        "ok": True,

        "ts_utc": _abd_now_utc(),

        "cycles": _abd_collect_cycles(limit=limit)

    }



@app.get("/v1/agent/dashboard/deviations")

def agent_dashboard_deviations(limit: int = 25):

    limit = max(1, min(int(limit), 100))

    return {

        "ok": True,

        "ts_utc": _abd_now_utc(),

        "deviations": _abd_collect_deviations(limit=limit)

    }



@app.get("/v1/agent/dashboard/route")

def agent_dashboard_route():

    route_lock = _abd_read_json(_ABD_ROUTE_LOCK_PATH, default={}) or {}

    return {

        "ok": True,

        "ts_utc": _abd_now_utc(),

        "path": str(_ABD_ROUTE_LOCK_PATH),

        "route": route_lock

    }



@app.get("/ui/autobuild-dashboard")

def ui_autobuild_dashboard():

    from fastapi.responses import HTMLResponse

    html = """

<!doctype html>

<html lang="es">

<head>

<meta charset="utf-8">

<title>Brain Lab - Autobuild Dashboard</title>

<meta name="viewport" content="width=device-width,initial-scale=1">

<style>

body{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:20px}

h1,h2{margin:0 0 12px}

.small{font-size:12px;color:#94a3b8}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:18px}

.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px}

.good{color:#22c55e}.warn{color:#f59e0b}.bad{color:#ef4444}

table{width:100%;border-collapse:collapse;font-size:13px}

th,td{border-bottom:1px solid #233046;padding:8px;text-align:left;vertical-align:top}

code,pre{white-space:pre-wrap;word-break:break-word}

.section{margin-top:18px}

.badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#1f2937;border:1px solid #334155;font-size:12px}

a{color:#93c5fd}

</style>

</head>

<body>

<h1>Brain Lab — Autobuild Dashboard</h1>

<div class="small">Monitoreo visual de progreso, calidad y desviaciones. Refresca cada 10 segundos.</div>



<div class="grid" id="cards"></div>



<div class="section card">

  <h2>Ruta fijada</h2>

  <pre id="route"></pre>

</div>



<div class="section card">

  <h2>Roadmap</h2>

  <div id="roadmap_counts" class="small"></div>

  <table id="roadmap_tbl">

    <thead><tr><th>ID</th><th>Título</th><th>Status</th><th>Priority</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Últimos ciclos</h2>

  <table id="cycles_tbl">

    <thead><tr><th>Run</th><th>Ciclo</th><th>Item</th><th>Modo</th><th>OK</th><th>Artifact</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Desviaciones</h2>

  <table id="dev_tbl">

    <thead><tr><th>Severidad</th><th>Tipo</th><th>Room</th><th>Auto-resuelta</th><th>Detalle</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<script>

function esc(v){ return String(v ?? "").replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }

function clsBool(v){ return v === true ? 'good' : (v === false ? 'bad' : 'warn'); }



async function j(url){

  const r = await fetch(url, {cache:'no-store'});

  if(!r.ok) throw new Error(url + ' -> ' + r.status);

  return await r.json();

}



function card(title, value, extra, css){

  return `<div class="card"><div class="small">${esc(title)}</div><div class="${css||''}" style="font-size:22px;font-weight:700;margin-top:8px">${esc(value)}</div><div class="small" style="margin-top:8px">${esc(extra||'')}</div></div>`;

}



async function load(){

  const [summary, roadmap, cycles, deviations, route] = await Promise.all([

    j('/v1/agent/dashboard/summary'),

    j('/v1/agent/dashboard/roadmap'),

    j('/v1/agent/dashboard/cycles?limit=20'),

    j('/v1/agent/dashboard/deviations?limit=20'),

    j('/v1/agent/dashboard/route')

  ]);



  const rc = roadmap.counts || {};

  const latest = summary.latest_v17 || {};

  const decision = summary.latest_v12_decision || {};

  const runner = summary.runner_state || {};

  const cards = [

    card('Autobuild', runner.status || 'unknown', `runs=${runner.runs ?? ''}`, runner.status === 'running' ? 'warn' : 'good'),

    card('Roadmap', `${rc.done ?? 0}/${rc.total ?? 0}`, `pending=${rc.pending ?? 0} blocked=${rc.blocked ?? 0}`, (rc.blocked||0) > 0 ? 'bad' : 'good'),

    card('Último modo', latest.mode || summary.latest_runner?.last_mode || 'n/a', latest.base_room || '', latest.mode === 'bridge_fallback' ? 'warn' : 'good'),

    card('Artifact íntegro', decision.apply_request_integrity_ok, latest.checks?.artifact_ok ? 'artifact efectivo OK' : '', clsBool(decision.apply_request_integrity_ok)),

    card('Último resultado', latest.ok, latest._room || '', clsBool(latest.ok)),

    card('Foco actual', summary.route_lock?.current_focus || 'n/a', summary.route_lock?.next_checkpoint || '', 'warn')

  ];

  document.getElementById('cards').innerHTML = cards.join('');



  document.getElementById('route').textContent = JSON.stringify(route.route || {}, null, 2);



  document.getElementById('roadmap_counts').textContent =

    `total=${rc.total ?? 0} done=${rc.done ?? 0} in_progress=${rc.in_progress ?? 0} pending=${rc.pending ?? 0} blocked=${rc.blocked ?? 0}`;



  const rt = document.querySelector('#roadmap_tbl tbody');

  rt.innerHTML = (roadmap.work_items || []).map(x =>

    `<tr><td>${esc(x.id)}</td><td>${esc(x.title)}</td><td><span class="badge">${esc(x.status)}</span></td><td>${esc(x.priority)}</td></tr>`

  ).join('');



  const ct = document.querySelector('#cycles_tbl tbody');

  ct.innerHTML = (cycles.cycles || []).map(x =>

    `<tr><td>${esc(x.run_id)}</td><td>${esc(x.cycle)}</td><td>${esc(x.item)}</td><td>${esc(x.mode)}</td><td class="${clsBool(x.ok)}">${esc(x.ok)}</td><td class="${clsBool(x.artifact_ok)}">${esc(x.artifact_ok)}</td></tr>`

  ).join('');



  const dt = document.querySelector('#dev_tbl tbody');

  dt.innerHTML = (deviations.deviations || []).map(x =>

    `<tr><td class="${x.severity==='high'?'bad':(x.severity==='medium'?'warn':'good')}">${esc(x.severity)}</td><td>${esc(x.kind)}</td><td>${esc(x.room)}</td><td class="${clsBool(x.auto_resolved)}">${esc(x.auto_resolved)}</td><td>${esc(JSON.stringify(x.detail))}</td></tr>`

  ).join('');

}



load().catch(err => {

  document.body.insertAdjacentHTML('beforeend', `<div class="card bad">Error cargando dashboard: ${esc(err.message)}</div>`);

});

setInterval(() => load().catch(()=>{}), 10000);





function liveSet(id, value){

  const el = document.getElementById(id);

  if (!el) return;

  el.textContent = value ?? "";

}

function liveJoin(xs){

  return Array.isArray(xs) ? xs.join("\n") : "";

}



async function loadLiveRealtime(){

  try {

    const r = await fetch("/ui/api/autobuild-dashboard-v3-live", { cache: "no-store" });

    if (!r.ok) {

      throw new Error(`live api http ${r.status}`);

    }

    const d = await r.json();

    renderLiveRealtime(d);

  } catch (e) {

    const host = document.getElementById("liveRealtimeGrid");

    if (host) {

      host.innerHTML = `

        <div class="card wide">

          <div class="k">Tiempo real del runtime</div>

          <pre class="mini mono">${blEscHtml("live render error: " + (e?.message || e))}</pre>

        </div>

      `;

    }

    console.error("BL live realtime error", e);

  }

}



function renderLiveRealtime(live){

  const rt = (live && live.runtime) || {};

  const loop = ((live || {}).latest_loop || {}).summary || {};

  const histLen = Array.isArray(loop.history) ? loop.history.length : 0;



  liveSet("liveBrainRequestsBox", liveJoin((live || {}).brain_requests_tail || []));

  liveSet("liveBitacoraBox", liveJoin((live || {}).bitacora_tail || []));

  liveSet(

    "liveRuntimeBox",

    [

      "runtime_phase=" + (rt.runtime_phase || ""),

      "runtime_stage=" + (rt.runtime_stage || ""),

      "runtime_title=" + (rt.runtime_title || ""),

      "runtime_progress=" + (rt.runtime_progress_label || ""),

      "runtime_done=" + String(rt.runtime_done ?? ""),

      "runtime_total=" + String(rt.runtime_total ?? ""),

      "runtime_next_item=" + (rt.runtime_next_item || "")

    ].join("\n")

  );

  liveSet(

    "liveLoopSummaryBox",

    [

      "current_phase=" + (loop.current_phase || ""),

      "current_stage=" + (loop.current_stage || ""),

      "active_title=" + (loop.active_title || ""),

      "history_len=" + String(histLen),

      "dir=" + (((live || {}).latest_loop || {}).dir || "")

    ].join("\n")

  );

  liveSet("liveLoopStdoutBox", liveJoin((((live || {}).stdout || {}).loop_tail) || []));

  liveSet("liveLoopStderrBox", liveJoin((((live || {}).stderr || {}).loop_tail) || []));

  liveSet("liveBrainStderrBox", liveJoin((((live || {}).stderr || {}).brain_tail) || []));



  const proposals = Array.isArray((live || {}).recent_proposals) ? live.recent_proposals : [];

  liveSet(

    "liveProposalsBox",

    proposals.map(x =>

      (x.proposal_id || "") + " | room=" + (x.room_id || "") + " | step=" + (x.step_id || "") + " | tool=" + (x.tool_name || "")

    ).join("\n")

  );



  const artifacts = Array.isArray((live || {}).recent_artifacts) ? live.recent_artifacts : [];

  liveSet(

    "liveArtifactsBox",

    artifacts.map(x =>

      "room=" + (x.room || "") + " | " + (x.name || "") + "\n" + liveJoin(x.tail || []) + "\n---"

    ).join("\n")

  );

}



</script>



<script>

(function(){

  const MARK = "BL_LIVE_PANEL_BOOT_V4";

  if (window[MARK]) return;

  window[MARK] = true;



  function esc(x){

    return String(x ?? "")

      .replaceAll("&","&amp;")

      .replaceAll("<","&lt;")

      .replaceAll(">","&gt;");

  }



  function arr(x){

    return Array.isArray(x) ? x : [];

  }



  function fmt(x){

    if (x === null || x === undefined) return "";

    if (typeof x === "string") return x;

    try { return JSON.stringify(x, null, 2); } catch { return String(x); }

  }



  function pre(title, content){

    return `

      <div class="card">

        <div class="k">${esc(title)}</div>

        <pre class="mini mono">${esc(content)}</pre>

      </div>

    `;

  }



  function preWide(title, content){

    return `

      <div class="card wide">

        <div class="k">${esc(title)}</div>

        <pre class="mini mono">${esc(content)}</pre>

      </div>

    `;

  }



  function artifactsBlock(items){

    const a = arr(items);

    if (!a.length) return preWide("Artifacts recientes", "sin artifacts recientes");

    const txt = a.slice(0,12).map(it => {

      const head = `[${it.room || "n/a"}] ${it.name || "artifact"}\n${it.path || ""}`;

      const tail = arr(it.tail).join("\n");

      return head + (tail ? "\n" + tail : "");

    }).join("\n\n----------------\n\n");

    return preWide("Artifacts recientes", txt);

  }



  function proposalsBlock(items){

    const a = arr(items);

    if (!a.length) return pre("Propuestas recientes", "sin propuestas recientes");

    return pre("Propuestas recientes", a.map(x => fmt(x)).join("\n\n"));

  }



  function runtimeBlock(rt){

    rt = rt || {};

    const c = rt.runtime_counts || {};

    const txt =

`phase=${rt.runtime_phase || ""}

stage=${rt.runtime_stage || ""}

title=${rt.runtime_title || ""}

next=${rt.runtime_next_item || ""}

done=${c.done ?? rt.runtime_done ?? 0}

pending=${c.pending ?? rt.runtime_pending ?? 0}

in_progress=${c.in_progress ?? rt.runtime_in_progress ?? 0}

blocked=${c.blocked ?? rt.runtime_blocked ?? 0}

total=${c.total ?? rt.runtime_total ?? 0}`;

    return txt;

  }



  function render(d){

    const host = document.getElementById("liveRealtimeGrid");

    if (!host) return;



    const live = d?.live_sources || {};

    const stdout = d?.stdout || {};

    const stderr = d?.stderr || {};

    const rt = d?.runtime || {};



    host.innerHTML = `

      ${pre("Eventos brain_requests.ndjson", arr(d?.brain_requests_tail).join("\n") || "sin eventos")}

      ${pre("Bitácora viva", arr(d?.bitacora_tail).join("\n") || "sin bitácora")}

      ${pre("Loop runtime", runtimeBlock(rt))}

      ${pre("Subruntime NL-06", runtimeBlock(rt))}

      ${pre("Loop STDOUT", ("path=" + (stdout.loop_path || "") + "\n\n" + (arr(stdout.loop_tail).join("\n") || "sin stdout")))}

      ${pre("Loop STDERR", ("path=" + (stderr.loop_path || "") + "\n\n" + (arr(stderr.loop_tail).join("\n") || "sin stderr")))}

      ${pre("Brain 8010 STDERR", ("path=" + (stderr.brain_path || "") + "\n\n" + (arr(stderr.brain_tail).join("\n") || "sin errores")))}

      ${proposalsBlock(d?.recent_proposals)}

      ${artifactsBlock(d?.recent_artifacts)}

      ${preWide("Fuentes live y rutas activas", fmt(live))}

    `;

  }



  async function load(){

    try {

      const r = await fetch("/ui/api/autobuild-dashboard-v3-live", { cache: "no-store" });

      if (!r.ok) throw new Error("live api http " + r.status);

      const d = await r.json();

      render(d);

    } catch (e) {

      const host = document.getElementById("liveRealtimeGrid");

      if (host) {

        host.innerHTML = `

          <div class="card wide">

            <div class="k">Tiempo real del runtime</div>

            <pre class="mini mono">${esc("live boot error: " + (e?.message || e))}</pre>

          </div>

        `;

      }

      console.error(MARK, e);

    }

  }



  function boot(){

    if (!document.getElementById("liveRealtimeGrid")) return;

    load();

    setInterval(load, 10000);

  }



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", boot);

  } else {

    boot();

  }

})();

</script>



</body>

</html>

"""

    return HTMLResponse(content=html)

# === AUTOBUILD_DASHBOARD_CONTROL_TOWER_V1 END ===







# AUTO_BUILD_AB08_SOURCES_BOOTSTRAP_V1

from pathlib import Path as _AB08_Path



_AB08_STATE_ROOT = _AB08_Path(r"C:\AI_VAULT\tmp_agent\state")

_AB08_SOURCE_REGISTRY_PATH = _AB08_STATE_ROOT / "source_registry.json"

_AB08_INGESTION_STATE_PATH = _AB08_STATE_ROOT / "ingestion_state.json"



def _ab08_now_utc_z():

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _ab08_norm_room_id(room_id=None):

    try:

        fn = globals().get("_autobuild_norm_room_id")

        if callable(fn):

            return fn(room_id)

    except Exception:

        pass

    v = str(room_id or "default").strip()

    return v or "default"



def _ab08_read_json(path, default):

    import json

    try:

        if path.exists():

            return json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        pass

    return default



def _ab08_write_json(path, data):

    import json

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    tmp.replace(path)



def _ab08_default_source_registry():

    return {

        "schema_version": "source_registry_v1",

        "updated_utc": _ab08_now_utc_z(),

        "sources": [

            {

                "source_id": "manual_notes",

                "kind": "manual",

                "enabled": True,

                "trust_level": "medium",

                "validation_required": True,

                "normalization_policy": "structured_json"

            },

            {

                "source_id": "local_files",

                "kind": "files_local",

                "enabled": True,

                "trust_level": "high",

                "validation_required": True,

                "normalization_policy": "extract_then_json"

            },

            {

                "source_id": "market_data",

                "kind": "market",

                "enabled": True,

                "trust_level": "high",

                "validation_required": True,

                "normalization_policy": "timeseries_json"

            },

            {

                "source_id": "research",

                "kind": "research",

                "enabled": True,

                "trust_level": "medium",

                "validation_required": True,

                "normalization_policy": "summary_plus_citations"

            }

        ]

    }



def _ab08_default_ingestion_state(room_id="system"):

    rid = _ab08_norm_room_id(room_id)

    return {

        "schema_version": "ingestion_state_v1",

        "updated_utc": _ab08_now_utc_z(),

        "last_room_id": rid,

        "summary": {

            "total_sources": 0,

            "enabled_sources": 0,

            "last_ingestion_utc": None,

            "last_run_id": None

        },

        "audit_trail": [

            {

                "ts_utc": _ab08_now_utc_z(),

                "room_id": rid,

                "event": "bootstrap_seed",

                "ok": True

            }

        ]

    }



def _ab08_ensure_registry():

    reg = _ab08_read_json(_AB08_SOURCE_REGISTRY_PATH, None)

    if not isinstance(reg, dict) or not isinstance(reg.get("sources"), list):

        reg = _ab08_default_source_registry()

        _ab08_write_json(_AB08_SOURCE_REGISTRY_PATH, reg)

    return reg



def _ab08_ensure_ingestion(room_id="system"):

    ing = _ab08_read_json(_AB08_INGESTION_STATE_PATH, None)

    if not isinstance(ing, dict) or not isinstance(ing.get("summary"), dict):

        ing = _ab08_default_ingestion_state(room_id)

        _ab08_write_json(_AB08_INGESTION_STATE_PATH, ing)

    return ing



def _ab08_build_summary(room_id="default"):

    reg = _ab08_ensure_registry()

    ing = _ab08_ensure_ingestion(room_id)

    srcs = reg.get("sources") or []

    total = len(srcs)

    enabled = sum(1 for s in srcs if s.get("enabled") is True)



    ing["updated_utc"] = _ab08_now_utc_z()

    ing["last_room_id"] = _ab08_norm_room_id(room_id)

    ing["summary"]["total_sources"] = total

    ing["summary"]["enabled_sources"] = enabled

    _ab08_write_json(_AB08_INGESTION_STATE_PATH, ing)



    return reg, ing



@app.get("/v1/agent/sources/summary")

def agent_sources_summary(room_id: str = "default"):

    reg, ing = _ab08_build_summary(room_id)

    srcs = reg.get("sources") or []

    return {

        "ok": True,

        "room_id": _ab08_norm_room_id(room_id),

        "source_registry_path": str(_AB08_SOURCE_REGISTRY_PATH),

        "ingestion_state_path": str(_AB08_INGESTION_STATE_PATH),

        "counts": {

            "total": len(srcs),

            "enabled": sum(1 for s in srcs if s.get("enabled") is True),

            "validation_required": sum(1 for s in srcs if s.get("validation_required") is True),

        },

        "sources": srcs,

        "ingestion_summary": ing.get("summary") or {},

        "last_room_id": ing.get("last_room_id"),

        "impl": "AUTO_BUILD_AB08_SOURCES_BOOTSTRAP_V1"

    }



@app.get("/v1/agent/ingestion/status")

def agent_ingestion_status(room_id: str = "default"):

    reg, ing = _ab08_build_summary(room_id)

    return {

        "ok": True,

        "room_id": _ab08_norm_room_id(room_id),

        "source_registry_path": str(_AB08_SOURCE_REGISTRY_PATH),

        "ingestion_state_path": str(_AB08_INGESTION_STATE_PATH),

        "state": ing,

        "source_count": len(reg.get("sources") or []),

        "impl": "AUTO_BUILD_AB08_SOURCES_BOOTSTRAP_V1"

    }











# AUTO_BUILD_AB08_INGESTION_AUDIT_V1

def _ab08_append_ingestion_audit(event: dict):

    ing = _ab08_ensure_ingestion((event or {}).get("room_id") or "default")

    trail = ing.get("audit_trail")

    if not isinstance(trail, list):

        trail = []



    rec = {

        "ts_utc": _ab08_now_utc_z(),

        "room_id": _ab08_norm_room_id((event or {}).get("room_id")),

        "run_id": str((event or {}).get("run_id") or "").strip() or None,

        "source_id": str((event or {}).get("source_id") or "").strip() or None,

        "phase": str((event or {}).get("phase") or "capture").strip() or "capture",

        "status": str((event or {}).get("status") or "ok").strip() or "ok",

        "items_in": int((event or {}).get("items_in") or 0),

        "items_out": int((event or {}).get("items_out") or 0),

        "note": str((event or {}).get("note") or "").strip() or None

    }



    trail.append(rec)

    trail = trail[-200:]

    ing["audit_trail"] = trail

    ing["updated_utc"] = _ab08_now_utc_z()

    ing["last_room_id"] = rec["room_id"]

    ing["summary"]["last_ingestion_utc"] = rec["ts_utc"]

    ing["summary"]["last_run_id"] = rec["run_id"]



    _ab08_write_json(_AB08_INGESTION_STATE_PATH, ing)

    return ing, rec



@app.post("/v1/agent/ingestion/record")

def agent_ingestion_record(payload: dict = None):

    payload = payload or {}

    room_id = _ab08_norm_room_id(payload.get("room_id"))

    _ab08_ensure_registry()

    ing, rec = _ab08_append_ingestion_audit({

        "room_id": room_id,

        "run_id": payload.get("run_id"),

        "source_id": payload.get("source_id"),

        "phase": payload.get("phase"),

        "status": payload.get("status"),

        "items_in": payload.get("items_in"),

        "items_out": payload.get("items_out"),

        "note": payload.get("note"),

    })

    return {

        "ok": True,

        "room_id": room_id,

        "recorded": rec,

        "audit_count": len(ing.get("audit_trail") or []),

        "ingestion_state_path": str(_AB08_INGESTION_STATE_PATH),

        "impl": "AUTO_BUILD_AB08_INGESTION_AUDIT_V1"

    }



@app.get("/v1/agent/ingestion/audit")

def agent_ingestion_audit(room_id: str = "default", limit: int = 20):

    _ab08_ensure_registry()

    ing = _ab08_ensure_ingestion(room_id)

    trail = ing.get("audit_trail") or []

    try:

        limit = max(1, min(int(limit), 200))

    except Exception:

        limit = 20

    items = trail[-limit:]

    return {

        "ok": True,

        "room_id": _ab08_norm_room_id(room_id),

        "count": len(items),

        "items": items,

        "ingestion_state_path": str(_AB08_INGESTION_STATE_PATH),

        "impl": "AUTO_BUILD_AB08_INGESTION_AUDIT_V1"

    }











# AUTO_BUILD_AB09_FINANCIAL_MISSION_V1

from pathlib import Path as _AB09_Path



_AB09_STATE_ROOT = _AB09_Path(r"C:\AI_VAULT\tmp_agent\state")

_AB09_FIN_MISSION_PATH = _AB09_STATE_ROOT / "financial_mission.json"

_AB09_ROUTE_LOCK_PATH = _AB09_STATE_ROOT / "brain_route_lock.json"



def _ab09_now_utc_z():

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _ab09_read_json(path, default):

    import json

    try:

        if path.exists():

            return json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        pass

    return default



def _ab09_write_json(path, data):

    import json

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    tmp.replace(path)



def _ab09_default_financial_mission():

    return {

        "schema_version": "financial_mission_v1",

        "updated_utc": _ab09_now_utc_z(),

        "objective_primary": "maximize_risk_adjusted_compounded_growth",

        "utility_u": {

            "name": "U_financial_survival_first",

            "statement": "Maximizar crecimiento compuesto ajustado a riesgo minimizando probabilidad de ruina y drawdowns irreversibles.",

            "priority_order": [

                "survival",

                "stability",

                "compounded_growth",

                "capital_efficiency",

                "operational_autonomy"

            ],

            "penalties": {

                "ruin_probability": "very_high",

                "max_drawdown_breach": "high",

                "unvalidated_action": "high",

                "illiquid_exposure": "medium"

            }

        },

        "guardrails": {

            "survival_first": True,

            "max_tolerated_drawdown_pct": 30,

            "require_validation_before_scaling": True,

            "prefer_reversible_changes": True,

            "no_freeform_narrative_as_truth": True

        },

        "capital_architecture": {

            "core": {

                "role": "preservation_and_compounding",

                "target_share_pct": 70

            },

            "satellite": {

                "role": "measured_alpha",

                "target_share_pct": 20

            },

            "explorer": {

                "role": "high_uncertainty_experiments",

                "target_share_pct": 10

            }

        },

        "audit": {

            "owner": "brain-openai-fastapi",

            "mode": "financial_first"

        }

    }



def _ab09_default_route_lock():

    return {

        "schema_version": "brain_route_lock_v1",

        "updated_utc": _ab09_now_utc_z(),

        "current_focus": "survival_first_financial_autobuild",

        "selection_policy": "survival_gt_stability_gt_compounded_growth_gt_nominal_return",

        "next_checkpoint": "AB-09_financial_mission_seeded",

        "mission_alignment": {

            "survival_over_nominal_return": True,

            "prefer_validated_paths": True,

            "allow_offline_fallback_only_when_controlled": True

        }

    }



def _ab09_ensure_financial_mission():

    data = _ab09_read_json(_AB09_FIN_MISSION_PATH, None)

    if not isinstance(data, dict) or not isinstance(data.get("utility_u"), dict):

        data = _ab09_default_financial_mission()

        _ab09_write_json(_AB09_FIN_MISSION_PATH, data)

        return data



    changed = False

    if "schema_version" not in data:

        data["schema_version"] = "financial_mission_v1"; changed = True

    if "updated_utc" not in data:

        data["updated_utc"] = _ab09_now_utc_z(); changed = True

    if "objective_primary" not in data:

        data["objective_primary"] = "maximize_risk_adjusted_compounded_growth"; changed = True

    if not isinstance(data.get("utility_u"), dict):

        data["utility_u"] = _ab09_default_financial_mission()["utility_u"]; changed = True

    if not isinstance(data.get("guardrails"), dict):

        data["guardrails"] = _ab09_default_financial_mission()["guardrails"]; changed = True

    if not isinstance(data.get("capital_architecture"), dict):

        data["capital_architecture"] = _ab09_default_financial_mission()["capital_architecture"]; changed = True



    if changed:

        data["updated_utc"] = _ab09_now_utc_z()

        _ab09_write_json(_AB09_FIN_MISSION_PATH, data)

    return data



def _ab09_ensure_route_lock():

    data = _ab09_read_json(_AB09_ROUTE_LOCK_PATH, None)

    if not isinstance(data, dict):

        data = _ab09_default_route_lock()

        _ab09_write_json(_AB09_ROUTE_LOCK_PATH, data)

        return data



    changed = False

    if "schema_version" not in data:

        data["schema_version"] = "brain_route_lock_v1"; changed = True

    if "current_focus" not in data:

        data["current_focus"] = "survival_first_financial_autobuild"; changed = True

    if "selection_policy" not in data:

        data["selection_policy"] = "survival_gt_stability_gt_compounded_growth_gt_nominal_return"; changed = True

    if not isinstance(data.get("mission_alignment"), dict):

        data["mission_alignment"] = _ab09_default_route_lock()["mission_alignment"]; changed = True



    if changed:

        data["updated_utc"] = _ab09_now_utc_z()

        _ab09_write_json(_AB09_ROUTE_LOCK_PATH, data)

    return data



@app.get("/v1/agent/mission/financial")

def agent_financial_mission():

    mission = _ab09_ensure_financial_mission()

    route = _ab09_ensure_route_lock()

    return {

        "ok": True,

        "mission_path": str(_AB09_FIN_MISSION_PATH),

        "route_lock_path": str(_AB09_ROUTE_LOCK_PATH),

        "mission": mission,

        "route_lock": route,

        "impl": "AUTO_BUILD_AB09_FINANCIAL_MISSION_V1"

    }



@app.get("/v1/agent/utility_u")

def agent_utility_u():

    mission = _ab09_ensure_financial_mission()

    route = _ab09_ensure_route_lock()

    return {

        "ok": True,

        "objective_primary": mission.get("objective_primary"),

        "utility_u": mission.get("utility_u") or {},

        "guardrails": mission.get("guardrails") or {},

        "capital_architecture": mission.get("capital_architecture") or {},

        "route_lock_focus": route.get("current_focus"),

        "route_lock_policy": route.get("selection_policy"),

        "impl": "AUTO_BUILD_AB09_FINANCIAL_MISSION_V1"

    }


_BL02_UTILITY_SNAPSHOT_PATH = _AB09_STATE_ROOT / "utility_u_latest.json"
_BL02_SCORECARD_PATH = _AB09_STATE_ROOT / "rooms" / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json"
_BL02_PROMOTION_POLICY_PATH = _AB09_STATE_ROOT / "governed_promotion_policy.json"
_BL02_EXECUTION_VERIFICATIONS_ROOT = _AB09_STATE_ROOT / "execution_verifications"


def _bl02_latest_execution_verification_status():

    try:

        xs = sorted(
            [p for p in _BL02_EXECUTION_VERIFICATIONS_ROOT.glob("*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not xs:

            return {"status": "n/a", "path": None}

        obj = _ab09_read_json(xs[0], {}) or {}

        return {
            "status": str(obj.get("verification_status") or obj.get("status") or "n/a").strip().lower(),
            "path": str(xs[0]),
        }

    except Exception:

        return {"status": "n/a", "path": None}


def _bl02_compute_utility_proxy():

    mission = _ab09_ensure_financial_mission()

    route = _ab09_ensure_route_lock()

    scorecard = _ab09_read_json(_BL02_SCORECARD_PATH, {}) or {}

    promotion = _ab09_read_json(_BL02_PROMOTION_POLICY_PATH, {}) or {}

    seed = scorecard.get("seed_metrics") if isinstance(scorecard.get("seed_metrics"), dict) else {}

    entries_taken = int(seed.get("entries_taken") or 0)
    entries_resolved = int(seed.get("entries_resolved") or 0)
    wins = int(seed.get("wins") or 0)
    losses = int(seed.get("losses") or 0)
    valid_candidates_skipped = int(seed.get("valid_candidates_skipped") or 0)
    growth_signal = float(seed.get("net_expectancy_after_payout") or 0.0)
    drawdown_penalty = float(seed.get("max_drawdown") or 0.0)
    tail_risk_penalty = 0.0
    fragility_penalty = round(1.0 if entries_resolved == 0 else min(1.0, valid_candidates_skipped / max(entries_resolved, 1)), 4)

    latest_verification = _bl02_latest_execution_verification_status()
    governance_penalty = 0.0 if latest_verification.get("status") == "passed" else 1.0

    u_proxy_score = round(
        growth_signal
        - drawdown_penalty
        - tail_risk_penalty
        - governance_penalty
        - fragility_penalty,
        4,
    )

    blockers = []
    if entries_resolved < 20:
        blockers.append("insufficient_resolved_sample")
    if u_proxy_score <= 0:
        blockers.append("u_proxy_non_positive")
    if governance_penalty > 0:
        blockers.append("governance_not_recently_verified")
    if not bool((promotion or {}).get("promotion_rules")):
        blockers.append("promotion_policy_missing")

    verdict = "no_promote"
    if not blockers:
        verdict = "candidate_for_gate_review"

    snapshot = {
        "schema_version": "utility_u_proxy_snapshot_v1",
        "updated_utc": _ab09_now_utc_z(),
        "objective_primary": mission.get("objective_primary"),
        "utility_name": str((mission.get("utility_u") or {}).get("name") or ""),
        "route_lock_focus": route.get("current_focus"),
        "mode": "proxy_inicial_bl02",
        "components": {
            "growth_signal": growth_signal,
            "drawdown_penalty": drawdown_penalty,
            "tail_risk_penalty": tail_risk_penalty,
            "governance_penalty": governance_penalty,
            "fragility_penalty": fragility_penalty,
        },
        "sample": {
            "entries_taken": entries_taken,
            "entries_resolved": entries_resolved,
            "wins": wins,
            "losses": losses,
            "valid_candidates_skipped": valid_candidates_skipped,
        },
        "promotion_gate": {
            "promotion_policy_present": bool((promotion or {}).get("promotion_rules")),
            "latest_verification_status": latest_verification.get("status"),
            "latest_verification_path": latest_verification.get("path"),
            "blockers": blockers,
            "verdict": verdict,
        },
        "u_proxy_score": u_proxy_score,
    }

    try:
        _ab09_write_json(_BL02_UTILITY_SNAPSHOT_PATH, snapshot)
    except Exception:
        pass

    return snapshot


@app.get("/v1/agent/utility_u/proxy")

def agent_utility_u_proxy():

    snapshot = _bl02_compute_utility_proxy()

    return {
        "ok": True,
        "snapshot_path": str(_BL02_UTILITY_SNAPSHOT_PATH),
        "snapshot": snapshot,
        "impl": "BL02_UTILITY_PROXY_V1",
    }


_BL02_PROMOTION_GATE_ASSESSMENT_PATH = _AB09_STATE_ROOT / "utility_u_promotion_gate_latest.json"


def _bl02_compute_promotion_gate_assessment():

    snapshot = _bl02_compute_utility_proxy()

    blockers = list(((snapshot.get("promotion_gate") or {}).get("blockers") or []))
    verdict = str(((snapshot.get("promotion_gate") or {}).get("verdict") or "no_promote")).strip()
    allow_promote = verdict == "candidate_for_gate_review" and not blockers

    assessment = {
        "schema_version": "utility_u_promotion_gate_v1",
        "updated_utc": _ab09_now_utc_z(),
        "source_snapshot_path": str(_BL02_UTILITY_SNAPSHOT_PATH),
        "u_proxy_score": snapshot.get("u_proxy_score"),
        "verdict": verdict,
        "allow_promote": allow_promote,
        "blockers": blockers,
        "required_next_actions": [
            "increase_resolved_sample" if "insufficient_resolved_sample" in blockers else None,
            "improve_expectancy_or_reduce_penalties" if "u_proxy_non_positive" in blockers else None,
            "restore_recent_governed_verification" if "governance_not_recently_verified" in blockers else None,
        ],
        "notes": "Gate inicial de BL-02. No sustituye evaluacion cuant robusta; impide promocion mientras U proxy o la muestra sigan en estado debil.",
    }
    assessment["required_next_actions"] = [x for x in assessment["required_next_actions"] if x]

    try:
        _ab09_write_json(_BL02_PROMOTION_GATE_ASSESSMENT_PATH, assessment)
    except Exception:
        pass

    return assessment


@app.get("/v1/agent/utility_u/promotion-gate")

def agent_utility_u_promotion_gate():

    assessment = _bl02_compute_promotion_gate_assessment()

    return {
        "ok": True,
        "assessment_path": str(_BL02_PROMOTION_GATE_ASSESSMENT_PATH),
        "assessment": assessment,
        "impl": "BL02_UTILITY_PROMOTION_GATE_V1",
    }


_BL02_PAPER_ROOM_ID = "brain_binary_paper_pb05_journal"
_BL02_PAPER_READINESS_PATH = _AB09_STATE_ROOT / "rooms" / _BL02_PAPER_ROOM_ID / "paper_capture_readiness.json"
_BL02_PAPER_CAPTURE_PATH = _AB09_STATE_ROOT / "rooms" / _BL02_PAPER_ROOM_ID / "paper_session_capture_seed.json"
_BL02_PAPER_EVAL_PATH = _AB09_STATE_ROOT / "rooms" / _BL02_PAPER_ROOM_ID / "evaluation.json"
_BL02_PAPER_EVALS_PATH = _AB09_STATE_ROOT / "rooms" / _BL02_PAPER_ROOM_ID / "evaluations.ndjson"


def _bl02_compute_paper_session_evaluation():

    scorecard = _ab09_read_json(_BL02_SCORECARD_PATH, {}) or {}
    readiness = _ab09_read_json(_BL02_PAPER_READINESS_PATH, {}) or {}
    capture = _ab09_read_json(_BL02_PAPER_CAPTURE_PATH, {}) or {}
    utility_gate = _bl02_compute_promotion_gate_assessment()
    seed = scorecard.get("seed_metrics") if isinstance(scorecard.get("seed_metrics"), dict) else {}

    active_blockers = list(readiness.get("active_blockers") or [])
    top_skip_reasons = list(scorecard.get("top_skip_reasons") or [])
    entries_resolved = int(seed.get("entries_resolved") or 0)
    valid_candidates_skipped = int(seed.get("valid_candidates_skipped") or 0)

    paper_ready = bool(readiness.get("ready_for_m1_validation"))
    allow_strategy_review = bool(utility_gate.get("allow_promote")) and paper_ready

    reasons = []
    if not paper_ready:
        reasons.append("paper_validation_not_ready")
    reasons.extend(list(utility_gate.get("blockers") or []))

    evaluation = {
        "schema_version": "bl02_paper_session_evaluation_v1",
        "updated_utc": _ab09_now_utc_z(),
        "room_id": _BL02_PAPER_ROOM_ID,
        "source_paths": {
            "scorecard": str(_BL02_SCORECARD_PATH),
            "readiness": str(_BL02_PAPER_READINESS_PATH),
            "capture": str(_BL02_PAPER_CAPTURE_PATH),
            "utility_gate": str(_BL02_PROMOTION_GATE_ASSESSMENT_PATH),
        },
        "summary": {
            "entries_resolved": entries_resolved,
            "valid_candidates_skipped": valid_candidates_skipped,
            "pairs": list(readiness.get("pairs") or []),
            "minute_row_count": int(readiness.get("minute_row_count") or 0),
            "captured_candidates": int(capture.get("captured_candidates") or 0),
        },
        "utility_gate": {
            "u_proxy_score": utility_gate.get("u_proxy_score"),
            "verdict": utility_gate.get("verdict"),
            "allow_promote": bool(utility_gate.get("allow_promote")),
            "blockers": list(utility_gate.get("blockers") or []),
        },
        "paper_readiness": {
            "ready_for_m1_validation": paper_ready,
            "active_blockers": active_blockers,
            "top_skip_reasons": top_skip_reasons,
        },
        "decision": {
            "allow_strategy_review": allow_strategy_review,
            "status": "blocked" if not allow_strategy_review else "reviewable",
            "reasons": reasons,
        },
        "notes": "Evaluacion paper inicial de BL-02. Reutiliza U gate y readiness del carril paper para impedir promocion o revision prematura de estrategias cuando la muestra sigue debil.",
    }

    try:
        _BL02_PAPER_EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _BL02_PAPER_EVAL_PATH.write_text(__import__('json').dumps(evaluation, ensure_ascii=True, indent=2), encoding='utf-8')
        with _BL02_PAPER_EVALS_PATH.open('a', encoding='utf-8') as f:
            f.write(__import__('json').dumps(evaluation, ensure_ascii=True) + "\n")
    except Exception:
        pass

    return evaluation


@app.get("/v1/agent/paper-session/evaluation")

def agent_paper_session_evaluation():

    evaluation = _bl02_compute_paper_session_evaluation()

    return {
        "ok": True,
        "evaluation_path": str(_BL02_PAPER_EVAL_PATH),
        "evaluation": evaluation,
        "impl": "BL02_PAPER_SESSION_EVALUATION_V1",
    }











# AUTO_BUILD_AB10_BASELINE_KILLSWITCH_V1

from pathlib import Path as _AB10_Path



_AB10_STATE_ROOT = _AB10_Path(r"C:\AI_VAULT\tmp_agent\state")

_AB10_OPS_ROOT = _AB10_Path(r"C:\AI_VAULT\tmp_agent\ops")

_AB10_BASELINES_ROOT = _AB10_OPS_ROOT / "baselines"

_AB10_BASELINE_REGISTRY_PATH = _AB10_STATE_ROOT / "baseline_registry.json"

_AB10_RUNTIME_SNAPSHOT_PATH = _AB10_STATE_ROOT / "runtime_snapshot.json"



def _ab10_now_utc_z():

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _ab10_read_json(path, default):

    try:

        if path.exists():

            return json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        pass

    return default



def _ab10_write_json(path, data):

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")

    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    tmp.replace(path)



def _ab10_snapshot_info():

    if not _AB10_RUNTIME_SNAPSHOT_PATH.exists():

        return {

            "exists": False,

            "path": str(_AB10_RUNTIME_SNAPSHOT_PATH),

            "mtime_utc": None,

            "size": None

        }

    st = _AB10_RUNTIME_SNAPSHOT_PATH.stat()

    return {

        "exists": True,

        "path": str(_AB10_RUNTIME_SNAPSHOT_PATH),

        "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),

        "size": int(st.st_size)

    }



def _ab10_default_registry():

    return {

        "schema_version": "baseline_registry_v1",

        "updated_utc": _ab10_now_utc_z(),

        "active_baseline_id": None,

        "baselines": [],

        "kill_switch": {

            "enabled": False,

            "reason": None,

            "updated_utc": _ab10_now_utc_z()

        },

        "last_valid_snapshot": _ab10_snapshot_info(),

        "audit": []

    }



def _ab10_ensure_registry():

    reg = _ab10_read_json(_AB10_BASELINE_REGISTRY_PATH, None)

    if not isinstance(reg, dict):

        reg = _ab10_default_registry()

        _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)

        return reg



    changed = False

    if "schema_version" not in reg:

        reg["schema_version"] = "baseline_registry_v1"; changed = True

    if "active_baseline_id" not in reg:

        reg["active_baseline_id"] = None; changed = True

    if not isinstance(reg.get("baselines"), list):

        reg["baselines"] = []; changed = True

    if not isinstance(reg.get("kill_switch"), dict):

        reg["kill_switch"] = _ab10_default_registry()["kill_switch"]; changed = True

    reg["last_valid_snapshot"] = _ab10_snapshot_info()

    reg["updated_utc"] = _ab10_now_utc_z()

    if not isinstance(reg.get("audit"), list):

        reg["audit"] = []; changed = True



    if changed:

        _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)

    else:

        _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)

    return reg



def _ab10_capture_candidates():

    return [

        _AB10_Path(r"C:\AI_VAULT\00_identity\brain_server.py"),

        _AB10_Path(r"C:\AI_VAULT\tmp_agent\state\roadmap.json"),

        _AB10_Path(r"C:\AI_VAULT\tmp_agent\state\source_registry.json"),

        _AB10_Path(r"C:\AI_VAULT\tmp_agent\state\ingestion_state.json"),

        _AB10_Path(r"C:\AI_VAULT\tmp_agent\state\financial_mission.json"),

        _AB10_Path(r"C:\AI_VAULT\tmp_agent\state\brain_route_lock.json"),

    ]



def _ab10_capture_baseline(label="manual_lkg"):

    reg = _ab10_ensure_registry()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    baseline_id = f"baseline_{ts}"

    bdir = _AB10_BASELINES_ROOT / baseline_id

    bdir.mkdir(parents=True, exist_ok=True)



    files_meta = []

    for src in _ab10_capture_candidates():

        rec = {

            "original_path": str(src),

            "stored_name": src.name,

            "exists": src.exists()

        }

        if src.exists():

            dst = bdir / src.name

            shutil.copy2(src, dst)

            rec["stored_path"] = str(dst)

            rec["size"] = int(dst.stat().st_size)

        else:

            rec["stored_path"] = None

            rec["size"] = None

        files_meta.append(rec)



    manifest = {

        "baseline_id": baseline_id,

        "label": str(label or "manual_lkg"),

        "captured_utc": _ab10_now_utc_z(),

        "dir": str(bdir),

        "files": files_meta

    }

    _ab10_write_json(bdir / "manifest.json", manifest)



    reg["active_baseline_id"] = baseline_id

    reg["updated_utc"] = _ab10_now_utc_z()

    reg["last_valid_snapshot"] = _ab10_snapshot_info()

    reg["baselines"].append({

        "baseline_id": baseline_id,

        "label": manifest["label"],

        "captured_utc": manifest["captured_utc"],

        "dir": str(bdir),

        "file_count": len(files_meta)

    })

    reg["audit"].append({

        "ts_utc": _ab10_now_utc_z(),

        "event": "capture_baseline",

        "baseline_id": baseline_id,

        "ok": True

    })

    reg["audit"] = reg["audit"][-200:]

    _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)

    return reg, manifest



def _ab10_find_baseline(reg, baseline_id=None):

    bid = str(baseline_id or reg.get("active_baseline_id") or "").strip()

    if not bid:

        return None, None

    for b in reg.get("baselines") or []:

        if str(b.get("baseline_id")) == bid:

            bdir = _AB10_Path(str(b.get("dir") or ""))

            return b, bdir

    return None, None



def _ab10_revert_baseline(baseline_id=None):

    reg = _ab10_ensure_registry()

    b, bdir = _ab10_find_baseline(reg, baseline_id)

    if not b or not bdir or not bdir.exists():

        return {

            "ok": False,

            "error": "baseline_not_found",

            "baseline_id": baseline_id

        }



    manifest = _ab10_read_json(bdir / "manifest.json", {})

    restored = []

    for rec in manifest.get("files") or []:

        stored_path = rec.get("stored_path")

        original_path = rec.get("original_path")

        if stored_path and original_path and _AB10_Path(stored_path).exists():

            dst = _AB10_Path(original_path)

            dst.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(_AB10_Path(stored_path), dst)

            restored.append({

                "baseline_id": manifest.get("baseline_id"),

                "restored_to": str(dst),

                "from": str(stored_path)

            })



    reg["updated_utc"] = _ab10_now_utc_z()

    reg["last_valid_snapshot"] = _ab10_snapshot_info()

    reg["audit"].append({

        "ts_utc": _ab10_now_utc_z(),

        "event": "revert_baseline",

        "baseline_id": manifest.get("baseline_id"),

        "ok": True,

        "restored_count": len(restored)

    })

    reg["audit"] = reg["audit"][-200:]

    _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)



    return {

        "ok": True,

        "baseline_id": manifest.get("baseline_id"),

        "restored_files": restored,

        "restart_required": True

    }



def _ab10_set_kill_switch(enabled, reason=None):

    reg = _ab10_ensure_registry()

    reg["kill_switch"] = {

        "enabled": bool(enabled),

        "reason": str(reason or "").strip() or None,

        "updated_utc": _ab10_now_utc_z()

    }

    reg["updated_utc"] = _ab10_now_utc_z()

    reg["audit"].append({

        "ts_utc": _ab10_now_utc_z(),

        "event": "kill_switch",

        "enabled": bool(enabled),

        "reason": str(reason or "").strip() or None,

        "ok": True

    })

    reg["audit"] = reg["audit"][-200:]

    _ab10_write_json(_AB10_BASELINE_REGISTRY_PATH, reg)

    return reg



@app.get("/v1/agent/baseline/status")

def agent_baseline_status():

    reg = _ab10_ensure_registry()

    return {

        "ok": True,

        "baseline_registry_path": str(_AB10_BASELINE_REGISTRY_PATH),

        "runtime_snapshot_path": str(_AB10_RUNTIME_SNAPSHOT_PATH),

        "active_baseline_id": reg.get("active_baseline_id"),

        "last_valid_snapshot": reg.get("last_valid_snapshot") or {},

        "kill_switch": reg.get("kill_switch") or {},

        "baselines": reg.get("baselines") or [],

        "audit_tail": (reg.get("audit") or [])[-20:],

        "impl": "AUTO_BUILD_AB10_BASELINE_KILLSWITCH_V1"

    }



@app.post("/v1/agent/baseline/capture")

def agent_baseline_capture(payload: dict = None):

    payload = payload or {}

    reg, manifest = _ab10_capture_baseline(payload.get("label") or "manual_lkg")

    return {

        "ok": True,

        "baseline_registry_path": str(_AB10_BASELINE_REGISTRY_PATH),

        "active_baseline_id": reg.get("active_baseline_id"),

        "manifest": manifest,

        "impl": "AUTO_BUILD_AB10_BASELINE_KILLSWITCH_V1"

    }



@app.post("/v1/agent/baseline/revert")

def agent_baseline_revert(payload: dict = None):

    payload = payload or {}

    out = _ab10_revert_baseline(payload.get("baseline_id"))

    out["baseline_registry_path"] = str(_AB10_BASELINE_REGISTRY_PATH)

    out["impl"] = "AUTO_BUILD_AB10_BASELINE_KILLSWITCH_V1"

    return out



@app.post("/v1/agent/baseline/kill_switch")

def agent_baseline_kill_switch(payload: dict = None):

    payload = payload or {}

    reg = _ab10_set_kill_switch(bool(payload.get("enabled")), payload.get("reason"))

    return {

        "ok": True,

        "kill_switch": reg.get("kill_switch") or {},

        "baseline_registry_path": str(_AB10_BASELINE_REGISTRY_PATH),

        "impl": "AUTO_BUILD_AB10_BASELINE_KILLSWITCH_V1"

    }











# AUTO_BUILD_DASHBOARD_V2_PARALLEL_V1

def _abdv2_fix_text(v):

    if not isinstance(v, str):

        return v

    s = v

    repl = {

        "Ã¡":"á","Ã©":"é","Ã­":"í","Ã³":"ó","Ãº":"ú",

        "Ã±":"ñ","Ã":"Á","Ã‰":"É","Ã":"Í","Ã“":"Ó","Ãš":"Ú",

        "Â":"","funci≤n":"función","hÃ­brido":"híbrido","tÃ©cnica":"técnica",

        "auditorÃ­a":"auditoría","lÃ­mites":"límites","SatÃ©lite":"Satélite"

    }

    for a,b in repl.items():

        s = s.replace(a,b)

    try:

        if "Ã" in s or "Â" in s:

            s2 = s.encode("latin1","ignore").decode("utf-8","ignore")

            if s2:

                s = s2

    except Exception:

        pass

    return s



def _abdv2_read_json(path, default=None):

    try:

        from pathlib import Path

        import json

        p = Path(path)

        if not p.exists():

            return default

        return json.loads(p.read_text(encoding="utf-8-sig"))

    except Exception:

        return default



def _abdv2_counts(roadmap):

    items = (roadmap or {}).get("work_items") or []

    done = [x for x in items if str((x or {}).get("status")) == "done"]

    pending = [x for x in items if str((x or {}).get("status")) == "pending"]

    inprog = [x for x in items if str((x or {}).get("status")) == "in_progress"]

    blocked = [x for x in items if str((x or {}).get("status")) == "blocked"]

    return {

        "total": len(items),

        "done": len(done),

        "pending": len(pending),

        "in_progress": len(inprog),

        "blocked": len(blocked),

    }



def _abdv2_next_item(roadmap):

    items = (roadmap or {}).get("work_items") or []

    ordered = [x for x in items if str((x or {}).get("status")) in ("in_progress","pending")]

    ordered = sorted(ordered, key=lambda x: (0 if str((x or {}).get("status")) == "in_progress" else 1, int((x or {}).get("priority") or 999)))

    if not ordered:

        return {}

    x = ordered[0] or {}

    return {

        "id": x.get("id"),

        "title": _abdv2_fix_text(x.get("title")),

        "status": x.get("status"),

        "priority": x.get("priority"),

        "objective": _abdv2_fix_text(x.get("objective")),

    }



def _abdv2_model_summary():

    p = r"C:\AI_VAULT\tmp_agent\state\model_registry.json"

    obj = _abdv2_read_json(p, default={}) or {}

    models = obj.get("models") if isinstance(obj, dict) else None

    if not isinstance(models, list):

        models = []

    flat = str(obj)

    return {

        "path": p,

        "exists": Path(p).exists(),

        "count": len(models),

        "has_openai": ("openai" in flat.lower()),

        "has_ollama": ("ollama" in flat.lower()),

        "has_qwen14b": ("qwen" in flat.lower() and "14b" in flat.lower()),

        "has_rules": ("rules" in flat.lower() or "validator" in flat.lower() or "hard_rules" in flat.lower()),

        "models": models,

    }



def _abdv2_baseline_summary():

    p = r"C:\AI_VAULT\tmp_agent\state\baseline_registry.json"

    obj = _abdv2_read_json(p, default={}) or {}

    ks = (obj.get("kill_switch") or {}) if isinstance(obj, dict) else {}

    return {

        "path": p,

        "exists": Path(p).exists(),

        "active_baseline_id": obj.get("active_baseline_id") if isinstance(obj, dict) else None,

        "baselines_count": len((obj.get("baselines") or [])) if isinstance(obj, dict) else 0,

        "kill_switch_enabled": bool(ks.get("enabled")) if isinstance(ks, dict) else False,

        "kill_switch_reason": ks.get("reason") if isinstance(ks, dict) else None,

        "last_valid_snapshot": (obj.get("last_valid_snapshot") or {}) if isinstance(obj, dict) else {},

    }



def _abdv2_ingestion_summary():

    src_path = r"C:\AI_VAULT\tmp_agent\state\source_registry.json"

    ing_path = r"C:\AI_VAULT\tmp_agent\state\ingestion_state.json"

    src = _abdv2_read_json(src_path, default={}) or {}

    ing = _abdv2_read_json(ing_path, default={}) or {}

    sources = src.get("sources") if isinstance(src, dict) else []

    if not isinstance(sources, list):

        sources = []

    enabled = sum(1 for s in sources if isinstance(s, dict) and s.get("enabled") is True)

    summ = ing.get("summary") if isinstance(ing, dict) else {}

    if not isinstance(summ, dict):

        summ = {}

    return {

        "source_registry_path": src_path,

        "ingestion_state_path": ing_path,

        "source_registry_exists": Path(src_path).exists(),

        "ingestion_state_exists": Path(ing_path).exists(),

        "total_sources": len(sources),

        "enabled_sources": enabled,

        "last_ingestion_utc": summ.get("last_ingestion_utc"),

        "last_run_id": summ.get("last_run_id"),

        "last_room_id": ing.get("last_room_id") if isinstance(ing, dict) else None,

    }



def _abdv2_mission_summary():

    p = r"C:\AI_VAULT\tmp_agent\state\financial_mission.json"

    obj = _abdv2_read_json(p, default={}) or {}

    u = obj.get("utility_u") if isinstance(obj, dict) else {}

    if not isinstance(u, dict):

        u = {}

    cap = obj.get("capital_architecture") if isinstance(obj, dict) else {}

    if not isinstance(cap, dict):

        cap = {}

    return {

        "path": p,

        "exists": Path(p).exists(),

        "objective_primary": obj.get("objective_primary") if isinstance(obj, dict) else None,

        "utility_name": u.get("name"),

        "utility_statement": _abdv2_fix_text(u.get("statement")),

        "priority_order": u.get("priority_order") if isinstance(u, dict) else [],

        "core_pct": ((cap.get("core") or {}).get("target_share_pct")) if isinstance(cap, dict) else None,

        "satellite_pct": ((cap.get("satellite") or {}).get("target_share_pct")) if isinstance(cap, dict) else None,

        "explorer_pct": ((cap.get("explorer") or {}).get("target_share_pct")) if isinstance(cap, dict) else None,

    }



def _abdv2_route_lock_summary():

    p = r"C:\AI_VAULT\tmp_agent\state\brain_route_lock.json"

    obj = _abdv2_read_json(p, default={}) or {}

    return {

        "path": p,

        "exists": Path(p).exists(),

        "current_focus": _abdv2_fix_text(obj.get("current_focus")) if isinstance(obj, dict) else None,

        "next_checkpoint": _abdv2_fix_text(obj.get("next_checkpoint")) if isinstance(obj, dict) else None,

        "selection_policy": obj.get("selection_policy") if isinstance(obj, dict) else None,

        "survival_over_nominal_return": (((obj.get("mission_alignment") or {}).get("survival_over_nominal_return")) if isinstance(obj, dict) else None),

        "raw": obj,

    }



def _abdv2_latest_run():

    latest = _abd_latest_runner_summary() or {}

    cycles = _abd_collect_cycles(limit=10)

    c0 = cycles[0] if cycles else {}

    summ = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}

    checks = summ.get("checks") if isinstance(summ, dict) else {}

    if not isinstance(checks, dict):

        checks = {}

    return {

        "run_id": summ.get("run_id") or Path(str(latest.get("_dir") or "")).name or None,

        "ts_utc": summ.get("ts_utc"),

        "cycle": c0.get("cycle"),

        "item": c0.get("item"),

        "mode": c0.get("mode"),

        "ok": c0.get("ok", latest.get("ok")),

        "artifact_ok": c0.get("artifact_ok", checks.get("artifact_ok")),

        "executor_exit": c0.get("executor_exit"),

        "summary_path": latest.get("_path"),

        "run_dir": latest.get("_dir"),

        "stop_reason": summ.get("stop_reason"),

        "smoke_ok": checks.get("smoke_ok"),

    }



def _abdv2_deviations_summary():

    rows = _abd_collect_deviations(limit=80)

    high = [x for x in rows if (x or {}).get("severity") == "high"]

    unresolved = [x for x in rows if not bool((x or {}).get("auto_resolved"))]

    return {

        "total": len(rows),

        "high": len(high),

        "unresolved": len(unresolved),

        "items": rows[:20],

    }



def _abdv2_overview():

    roadmap = _abdv2_read_json(r"C:\AI_VAULT\tmp_agent\state\roadmap.json", default={}) or {}

    counts = _abdv2_counts(roadmap)

    next_item = _abdv2_next_item(roadmap)

    mission = _abdv2_mission_summary()

    route = _abdv2_route_lock_summary()

    models = _abdv2_model_summary()

    ingestion = _abdv2_ingestion_summary()

    baseline = _abdv2_baseline_summary()

    latest = _abdv2_latest_run()

    deviations = _abdv2_deviations_summary()



    route_lock_stale = False

    try:

        cp = str(route.get("next_checkpoint") or "")

        ni = str(next_item.get("id") or "")

        if cp.startswith("AB-") and ni.startswith("CM-"):

            route_lock_stale = True

    except Exception:

        pass



    global_status = "green"

    reasons = []

    if baseline.get("kill_switch_enabled"):

        global_status = "red"; reasons.append("kill_switch_enabled")

    if deviations.get("unresolved", 0) > 0:

        if global_status != "red":

            global_status = "yellow"

        reasons.append("unresolved_deviations")

    if latest.get("artifact_ok") is False or latest.get("ok") is False:

        global_status = "red"; reasons.append("latest_run_not_ok")

    if route_lock_stale:

        if global_status == "green":

            global_status = "yellow"

        reasons.append("route_lock_stale_vs_fused_roadmap")



    items = roadmap.get("work_items") if isinstance(roadmap, dict) else []

    if not isinstance(items, list):

        items = []



    fixed_items = []

    for x in items:

        if not isinstance(x, dict):

            continue

        y = dict(x)

        y["title"] = _abdv2_fix_text(y.get("title"))

        y["objective"] = _abdv2_fix_text(y.get("objective"))

        y["note"] = _abdv2_fix_text(y.get("note"))

        fixed_items.append(y)



    return {

        "generated_utc": _abd_now_utc(),

        "global_status": global_status,

        "global_reasons": reasons,

        "roadmap_id": roadmap.get("roadmap_id") if isinstance(roadmap, dict) else None,

        "roadmap_counts": counts,

        "next_item": next_item,

        "latest_run": latest,

        "mission": mission,

        "route_lock": route,

        "models": models,

        "ingestion": ingestion,

        "baseline": baseline,

        "deviations": deviations,

        "roadmap_items": fixed_items,

        "cycles": _abd_collect_cycles(limit=12),

    }



@app.get("/v1/agent/dashboard/overview_v2")

def agent_dashboard_overview_v2():

    return {

        "ok": True,

        "overview": _abdv2_overview(),

        "impl": "AUTO_BUILD_DASHBOARD_V2_PARALLEL_V1"

    }



@app.get("/ui/autobuild-dashboard-v2")

def ui_autobuild_dashboard_v2():

    from fastapi.responses import HTMLResponse

    html = """

<!doctype html>

<html lang="es">

<head>

<meta charset="utf-8">

<title>Brain Lab - Autobuild Dashboard V2</title>

<meta name="viewport" content="width=device-width,initial-scale=1">

<style>

body{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:20px}

h1,h2,h3{margin:0 0 10px}

.small{font-size:12px;color:#94a3b8}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:18px}

.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px}

.good{color:#22c55e}.warn{color:#f59e0b}.bad{color:#ef4444}

table{width:100%;border-collapse:collapse;font-size:13px}

th,td{border-bottom:1px solid #233046;padding:8px;text-align:left;vertical-align:top}

code,pre{white-space:pre-wrap;word-break:break-word}

.section{margin-top:18px}

.badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#1f2937;border:1px solid #334155;font-size:12px}

.mono{font-family:Consolas,Menlo,monospace}

details{margin-top:8px}

</style>

</head>

<body>

<h1>Brain Lab — Autobuild Dashboard V2</h1>

<div class="small">Vista ejecutiva y operativa. Refresca cada 10 segundos.</div>



<div class="grid" id="cards"></div>



<div class="section card">

  <h2>Resumen ejecutivo</h2>

  <div id="executive" class="small"></div>

</div>



<div class="section card">

  <h2>Roadmap activo</h2>

  <div id="roadmap_counts" class="small"></div>

  <table id="roadmap_tbl">

    <thead><tr><th>ID</th><th>Título</th><th>Status</th><th>Priority</th><th>Note</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Últimos ciclos</h2>

  <table id="cycles_tbl">

    <thead><tr><th>Run</th><th>Ciclo</th><th>Item</th><th>Modo</th><th>OK</th><th>Artifact</th><th>Exit</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Desviaciones activas / recientes</h2>

  <table id="dev_tbl">

    <thead><tr><th>Severidad</th><th>Tipo</th><th>Room</th><th>Auto-resuelta</th><th>Detalle</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Detalle técnico</h2>

  <details>

    <summary>Overview JSON</summary>

    <pre id="raw"></pre>

  </details>

</div>



<script>

function esc(v){ return String(v ?? "").replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }

function clsBool(v){ return v === true ? 'good' : (v === false ? 'bad' : 'warn'); }

function clsStatus(v){

  if(v === 'green') return 'good';

  if(v === 'yellow') return 'warn';

  if(v === 'red') return 'bad';

  return 'warn';

}

function shortPath(v){

  const s = String(v ?? '');

  if(!s) return '';

  if(s.length <= 80) return s;

  return '...' + s.slice(-77);

}

function badge(v){ return `<span class="badge">${esc(v)}</span>`; }

function card(title, value, sub='', cls=''){

  return `<div class="card"><div class="small">${esc(title)}</div><div class="${cls}" style="font-size:22px;font-weight:600">${esc(value)}</div><div class="small mono">${esc(sub)}</div></div>`;

}

async function load(){

  const r = await fetch('/v1/agent/dashboard/overview_v2');

  const data = await r.json();

  const ov = data.overview || {};

  const rc = ov.roadmap_counts || {};

  const latest = ov.latest_run || {};

  const next = ov.next_item || {};

  const mission = ov.mission || {};

  const route = ov.route_lock || {};

  const models = ov.models || {};

  const ing = ov.ingestion || {};

  const base = ov.baseline || {};

  const dev = ov.deviations || {};



  const cards = [

    card('Estado global', ov.global_status || 'unknown', (ov.global_reasons || []).join(', '), clsStatus(ov.global_status)),

    card('Roadmap', `${rc.done ?? 0}/${rc.total ?? 0}`, `pending=${rc.pending ?? 0} in_progress=${rc.in_progress ?? 0} blocked=${rc.blocked ?? 0}`, 'warn'),

    card('Siguiente item', next.id || 'n/a', next.title || '', 'warn'),

    card('Último run', latest.run_id || 'n/a', `${latest.item || ''} | mode=${latest.mode || ''}`, clsBool(latest.ok)),

    card('Artifact', latest.artifact_ok, `exit=${latest.executor_exit ?? ''} smoke=${latest.smoke_ok ?? ''}`, clsBool(latest.artifact_ok)),

    card('Misión U', mission.utility_name || 'n/a', mission.objective_primary || '', 'warn'),

    card('Router híbrido', models.has_openai && models.has_ollama ? 'seeded' : 'partial', `openai=${models.has_openai} ollama=${models.has_ollama} qwen14b=${models.has_qwen14b}`, (models.has_openai && models.has_ollama) ? 'good' : 'warn'),

    card('Ingesta', `${ing.enabled_sources ?? 0}/${ing.total_sources ?? 0}`, `last_run=${ing.last_run_id || 'n/a'}`, 'warn'),

    card('Baseline', base.active_baseline_id || 'n/a', `kill_switch=${base.kill_switch_enabled}`, base.kill_switch_enabled ? 'bad' : 'good'),

    card('Route lock', route.next_checkpoint || 'n/a', route.current_focus || '', route.next_checkpoint && String(route.next_checkpoint).startsWith('CM-') ? 'good' : 'warn')

  ];

  document.getElementById('cards').innerHTML = cards.join('');



  document.getElementById('executive').innerHTML =

    `<div><b>Roadmap ID:</b> ${esc(ov.roadmap_id || 'n/a')}</div>

     <div><b>Next checkpoint route lock:</b> ${esc(route.next_checkpoint || 'n/a')}</div>

     <div><b>Current focus:</b> ${esc(route.current_focus || 'n/a')}</div>

     <div><b>Latest summary path:</b> <span class="mono">${esc(shortPath(latest.summary_path || ''))}</span></div>

     <div><b>Latest run dir:</b> <span class="mono">${esc(shortPath(latest.run_dir || ''))}</span></div>

     <div><b>Last ingestion:</b> ${esc(ing.last_ingestion_utc || 'n/a')}</div>

     <div><b>Kill switch reason:</b> ${esc(base.kill_switch_reason || 'n/a')}</div>`;



  document.getElementById('roadmap_counts').textContent =

    `total=${rc.total ?? 0} done=${rc.done ?? 0} in_progress=${rc.in_progress ?? 0} pending=${rc.pending ?? 0} blocked=${rc.blocked ?? 0}`;



  const rt = document.querySelector('#roadmap_tbl tbody');

  rt.innerHTML = (ov.roadmap_items || []).map(x =>

    `<tr><td>${esc(x.id)}</td><td>${esc(x.title)}</td><td>${badge(x.status)}</td><td>${esc(x.priority)}</td><td>${esc(x.note || '')}</td></tr>`

  ).join('');



  const ct = document.querySelector('#cycles_tbl tbody');

  ct.innerHTML = (ov.cycles || []).map(x =>

    `<tr>

      <td>${esc(x.run_id)}</td>

      <td>${esc(x.cycle)}</td>

      <td>${esc(x.item)}</td>

      <td>${esc(x.mode)}</td>

      <td class="${clsBool(x.ok)}">${esc(x.ok)}</td>

      <td class="${clsBool(x.artifact_ok)}">${esc(x.artifact_ok)}</td>

      <td>${esc(x.executor_exit)}</td>

    </tr>`

  ).join('');



  const dt = document.querySelector('#dev_tbl tbody');

  dt.innerHTML = (dev.items || []).map(x =>

    `<tr>

      <td class="${x.severity==='high'?'bad':(x.severity==='medium'?'warn':'good')}">${esc(x.severity)}</td>

      <td>${esc(x.kind)}</td>

      <td class="mono">${esc(shortPath(x.room))}</td>

      <td class="${clsBool(x.auto_resolved)}">${esc(x.auto_resolved)}</td>

      <td>${esc(JSON.stringify(x.detail))}</td>

    </tr>`

  ).join('');



  document.getElementById('raw').textContent = JSON.stringify(ov, null, 2);

}

load().catch(err => {

  document.body.insertAdjacentHTML('beforeend', `<div class="card bad">Error cargando dashboard V2: ${esc(err.message)}</div>`);

});

setInterval(() => load().catch(()=>{}), 10000);

</script>

</body>

</html>

"""

    return HTMLResponse(content=html)









# AUTO_BUILD_DASHBOARD_V2_CLEANUP_V1

def _abdv2_is_legacy_deviation(x):

    room = str((x or {}).get("room") or "")

    detail = str((x or {}).get("detail") or "")

    if "autoloop_advisor_v10_" in room:

        return True

    if "P2_PLANNER_HARDENING_SCHEMA_NORMALIZATION" in detail:

        return True

    if "json_parse_failed" in detail and "brain_server.py" in detail:

        return True

    return False



def _abdv2_deviations_summary():

    rows = _abd_collect_deviations(limit=200)

    current = []

    legacy = []

    for x in rows:

        if _abdv2_is_legacy_deviation(x):

            legacy.append(x)

        else:

            current.append(x)



    current_high = [x for x in current if (x or {}).get("severity") == "high"]

    current_unresolved = [x for x in current if not bool((x or {}).get("auto_resolved"))]



    legacy_high = [x for x in legacy if (x or {}).get("severity") == "high"]

    legacy_unresolved = [x for x in legacy if not bool((x or {}).get("auto_resolved"))]



    return {

        "current_total": len(current),

        "current_high": len(current_high),

        "current_unresolved": len(current_unresolved),

        "legacy_total": len(legacy),

        "legacy_high": len(legacy_high),

        "legacy_unresolved": len(legacy_unresolved),

        "items": current[:20],

        "legacy_items": legacy[:20],

    }



def _abdv2_overview():

    roadmap = _abdv2_read_json(r"C:\AI_VAULT\tmp_agent\state\roadmap.json", default={}) or {}

    counts = _abdv2_counts(roadmap)

    next_item = _abdv2_next_item(roadmap)

    mission = _abdv2_mission_summary()

    route = _abdv2_route_lock_summary()

    models = _abdv2_model_summary()

    ingestion = _abdv2_ingestion_summary()

    baseline = _abdv2_baseline_summary()

    latest = _abdv2_latest_run()

    deviations = _abdv2_deviations_summary()



    route_lock_stale = False

    try:

        cp = str(route.get("next_checkpoint") or "")

        ni = str(next_item.get("id") or "")

        if cp.startswith("AB-") and ni.startswith("CM-"):

            route_lock_stale = True

    except Exception:

        pass



    global_status = "green"

    reasons = []



    if baseline.get("kill_switch_enabled"):

        global_status = "red"

        reasons.append("kill_switch_enabled")



    if deviations.get("current_unresolved", 0) > 0:

        if global_status != "red":

            global_status = "yellow"

        reasons.append("current_unresolved_deviations")



    if latest.get("artifact_ok") is False or latest.get("ok") is False:

        global_status = "red"

        reasons.append("latest_run_not_ok")



    if route_lock_stale:

        if global_status == "green":

            global_status = "yellow"

        reasons.append("route_lock_stale_vs_fused_roadmap")



    items = roadmap.get("work_items") if isinstance(roadmap, dict) else []

    if not isinstance(items, list):

        items = []



    fixed_items = []

    for x in items:

        if not isinstance(x, dict):

            continue

        y = dict(x)

        y["title"] = _abdv2_fix_text(y.get("title"))

        y["objective"] = _abdv2_fix_text(y.get("objective"))

        y["note"] = _abdv2_fix_text(y.get("note"))

        fixed_items.append(y)



    return {

        "generated_utc": _abd_now_utc(),

        "global_status": global_status,

        "global_reasons": reasons,

        "roadmap_id": roadmap.get("roadmap_id") if isinstance(roadmap, dict) else None,

        "roadmap_counts": counts,

        "next_item": next_item,

        "latest_run": latest,

        "mission": mission,

        "route_lock": route,

        "models": models,

        "ingestion": ingestion,

        "baseline": baseline,

        "deviations": deviations,

        "roadmap_items": fixed_items,

        "cycles": _abd_collect_cycles(limit=12),

    }













# AUTO_BUILD_DASHBOARD_V3_NARRATIVE_V1

def _abdv3_bool_label(v):

    if v is True:

        return "ok"

    if v is False:

        return "fail"

    return "n/a"



def _abdv3_overview():

    ov = _abdv2_overview()

    latest = ov.get("latest_run") or {}

    next_item = ov.get("next_item") or {}

    route = ov.get("route_lock") or {}

    models = ov.get("models") or {}

    mission = ov.get("mission") or {}

    baseline = ov.get("baseline") or {}

    deviations = ov.get("deviations") or {}



    requested_by = "OpenAI (coordinación primaria)"

    if not models.get("has_openai"):

        requested_by = "Coordinación primaria no detectada"



    local_fallback = "Ollama/Qwen 14B local"

    if not (models.get("has_ollama") and models.get("has_qwen14b")):

        local_fallback = "Fallback local no completo"



    executed_by = "Brain autobuild runner"

    validated_by = "Hard rules + artifact integrity + baseline + route lock"



    if baseline.get("kill_switch_enabled"):

        loop_state = "halted"

    elif deviations.get("current_unresolved", 0) > 0:

        loop_state = "blocked"

    elif next_item.get("id"):

        loop_state = "ready"

    else:

        loop_state = "idle"



    if latest.get("run_id"):

        if latest.get("ok") is True and latest.get("artifact_ok") is True:

            last_outcome = (

                f"OpenAI encaminó el foco; Brain ejecutó {latest.get('item') or 'n/a'} "

                f"en modo {latest.get('mode') or 'n/a'}; validación ok; "

                f"artifact íntegro={latest.get('artifact_ok')}; exit={latest.get('executor_exit')}"

            )

        else:

            last_outcome = (

                f"Última iteración {latest.get('item') or 'n/a'} no cerró correctamente; "

                f"ok={latest.get('ok')} artifact_ok={latest.get('artifact_ok')} "

                f"exit={latest.get('executor_exit')}"

            )

    else:

        last_outcome = "Todavía no hay iteración registrada."



    if next_item.get("id"):

        next_action = (

            f"Siguiente iteración prevista: {next_item.get('id')} — "

            f"{_abdv2_fix_text(next_item.get('title'))}"

        )

    else:

        next_action = "No hay siguiente iteración pendiente."



    current_focus_human = _abdv2_fix_text(route.get("current_focus")) or _abdv2_fix_text(next_item.get("objective")) or _abdv2_fix_text(next_item.get("title"))

    mission_human = mission.get("utility_statement") or mission.get("objective_primary")



    steps = [

        {

            "stage": "mandate",

            "actor": requested_by,

            "status": "ok" if models.get("has_openai") else "warn",

            "message": _abdv2_fix_text(current_focus_human) or "Sin foco actual"

        },

        {

            "stage": "execution",

            "actor": executed_by,

            "status": "ok" if latest.get("ok") is True else ("warn" if latest.get("run_id") else "n/a"),

            "message": f"Último item ejecutado: {latest.get('item') or 'n/a'} | modo={latest.get('mode') or 'n/a'} | run={latest.get('run_id') or 'n/a'}"

        },

        {

            "stage": "validation",

            "actor": validated_by,

            "status": "ok" if (latest.get("artifact_ok") is True and baseline.get("kill_switch_enabled") is False and deviations.get("current_unresolved",0) == 0) else "warn",

            "message": f"artifact_ok={latest.get('artifact_ok')} | kill_switch={baseline.get('kill_switch_enabled')} | current_unresolved={deviations.get('current_unresolved',0)}"

        },

        {

            "stage": "iteration",

            "actor": local_fallback,

            "status": "ok" if next_item.get("id") else "n/a",

            "message": next_action

        }

    ]



    ov["narrative"] = {

        "loop_state": loop_state,

        "requested_by": requested_by,

        "executed_by": executed_by,

        "validated_by": validated_by,

        "local_fallback": local_fallback,

        "current_focus_human": current_focus_human,

        "mission_human": _abdv2_fix_text(mission_human),

        "last_outcome": _abdv2_fix_text(last_outcome),

        "next_action": _abdv2_fix_text(next_action),

        "steps": steps

    }

    return ov



# === SI05_TRUST_DASHBOARD_V2 START ===

from pathlib import Path as _SI05_Path



_SI05_STATE_ROOT = _SI05_Path(r"C:\AI_VAULT\tmp_agent\state")

_SI05_TRUST_SCORE_PATH = _SI05_STATE_ROOT / "trust_score_operational.json"

_SI05_RECON_PATH = _SI05_STATE_ROOT / "historical_roadmap_reconciliation.json"

_SI05_RUNTIME_AUDIT_PATH = _SI05_STATE_ROOT / "runtime_ui_audit_latest.json"

_SI05_TAXONOMY_PATH = _SI05_STATE_ROOT / "historical_done_taxonomy_assessment.json"

_SI05_PROMOTION_POLICY_PATH = _SI05_STATE_ROOT / "governed_promotion_policy.json"



def _si05_read_json(path, default=None):

    import json

    try:

        if path.exists():

            return json.loads(path.read_text(encoding="utf-8"))

    except Exception:

        pass

    return {} if default is None else default



def _si05_unique_list(items):

    out = []

    seen = set()

    for x in items or []:

        s = str(x).strip()

        if not s:

            continue

        if s in seen:

            continue

        seen.add(s)

        out.append(s)

    return out



def _si05_trust_bundle():

    trust = _si05_read_json(_SI05_TRUST_SCORE_PATH, {}) or {}

    recon = _si05_read_json(_SI05_RECON_PATH, {}) or {}

    runtime = _si05_read_json(_SI05_RUNTIME_AUDIT_PATH, {}) or {}

    taxonomy = _si05_read_json(_SI05_TAXONOMY_PATH, {}) or {}



    flagged = []

    for src in (taxonomy, recon, trust):

        if isinstance(src, dict):

            flagged.extend(src.get("flagged_historical_items") or [])

            flagged.extend(src.get("weak_claim_ids") or [])

    flagged = _si05_unique_list(flagged)



    avg = None

    interp = "n/a"

    if isinstance(trust, dict):

        avg = trust.get("average_score")

        if avg is None:

            avg = trust.get("trust_score_average")

        interp = trust.get("trust_score_interpretation") or trust.get("interpretation") or "n/a"



    runtime_status = "missing"

    if isinstance(runtime, dict) and runtime:

        runtime_status = str(runtime.get("status") or ("ok" if runtime.get("ok") else "warn"))



    reconciliation_status = "missing"

    if isinstance(recon, dict) and recon:

        reconciliation_status = "present"



    return {

        "average_score": avg,

        "interpretation": interp,

        "flagged_historical_items": flagged,

        "flagged_historical_count": len(flagged),

        "runtime_audit_status": runtime_status,

        "runtime_audit_present": bool(runtime),

        "reconciliation_present": bool(recon),

        "reconciliation_status": reconciliation_status,

        "promotion_policy_present": _SI05_PROMOTION_POLICY_PATH.exists(),

        "regression_state": "active_governed_regression_checks",

        "trust_score_path": str(_SI05_TRUST_SCORE_PATH),

        "runtime_ui_audit_path": str(_SI05_RUNTIME_AUDIT_PATH),

        "historical_roadmap_reconciliation_path": str(_SI05_RECON_PATH),

        "taxonomy_path": str(_SI05_TAXONOMY_PATH),

    }



@app.get("/v1/agent/dashboard/trust_bundle_v1")

def agent_dashboard_trust_bundle_v1():

    return {

        "ok": True,

        "trust": _si05_trust_bundle(),

        "impl": "SI05_TRUST_BUNDLE_V2"

    }



@app.get("/v1/agent/dashboard/overview_v3")

def agent_dashboard_overview_v3():

    ov = _abdv3_overview()

    try:

        ov["trust_bundle"] = _si05_trust_bundle()

    except Exception as ex:

        ov["trust_bundle"] = {"ok": False, "error": str(ex)}

    return {

        "ok": True,

        "overview": ov,

        "impl": "AUTO_BUILD_DASHBOARD_V3_TRUST_V2"

    }



@app.get("/ui/autobuild-dashboard-v3")

def ui_autobuild_dashboard_v3():

    from fastapi.responses import HTMLResponse

    html = """

<!doctype html>

<html lang="es">

<head>

<meta charset="utf-8">

<title>Brain Lab - Autobuild Dashboard V3</title>

<meta name="viewport" content="width=device-width,initial-scale=1">

<style>

body{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:18px}

h1,h2{margin:0 0 10px}

.small{font-size:12px;color:#94a3b8}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:16px}

.card{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px}

.good{color:#22c55e}.warn{color:#f59e0b}.bad{color:#ef4444}

table{width:100%;border-collapse:collapse;font-size:13px}

th,td{border-bottom:1px solid #233046;padding:8px;text-align:left;vertical-align:top}

.mono{font-family:Consolas,Menlo,monospace}

.section{margin-top:16px}

.badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#1f2937;border:1px solid #334155;font-size:12px}

.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}

.flowbox{background:#0b1220;border:1px dashed #334155;border-radius:12px;padding:12px}

pre{white-space:pre-wrap;word-break:break-word}

</style>

</head>

<body>

<h1>Brain Lab — Autobuild Dashboard V3</h1>

<div class="small">Vista narrativa del proceso con Trust Score, regression / rollback / promotion y evidencia de runtime. Refresca cada 10 segundos.</div>



<div class="grid" id="cards"></div>



<div class="section card">

  <h2>Qué está pasando ahora</h2>

  <div id="narrative_now"></div>

</div>



<div class="section card" id="runtime_overlay_card" style="display:none">

  <h2>Subruntime interno NL-06</h2>

  <div id="runtime_overlay_body" class="small"></div>

</div>



<div class="section card">

  <h2>Trust Score y regression / rollback / promotion</h2>

  <div id="trust_summary"></div>

</div>



<div class="section">

  <div class="flow" id="flow"></div>

</div>



<div class="section card">

  <h2>Roadmap activo</h2>

  <div id="roadmap_counts" class="small"></div>

  <table id="roadmap_tbl">

    <thead><tr><th>ID</th><th>Título</th><th>Status</th><th>Priority</th><th>Objective</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Últimos ciclos</h2>

  <table id="cycles_tbl">

    <thead><tr><th>Run</th><th>Ciclo</th><th>Item</th><th>Modo</th><th>OK</th><th>Artifact</th><th>Exit</th></tr></thead>

    <tbody></tbody>

  </table>

</div>



<div class="section card">

  <h2>Detalle técnico</h2>

  <details>

    <summary>Overview JSON + trust_bundle + runtime_ui_audit + historical_roadmap_reconciliation</summary>

    <pre id="raw"></pre>

  </details>

</div>



<script>

function esc(v){ return String(v ?? "").replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }

function cls(v){

  if(v === 'green' || v === 'ok' || v === true) return 'good';

  if(v === 'yellow' || v === 'warn') return 'warn';

  if(v === 'red' || v === 'fail' || v === 'bad' || v === false) return 'bad';

  return 'warn';

}

function badge(v){ return `<span class="badge">${esc(v)}</span>`; }

function card(title, value, sub='', css=''){

  return `<div class="card"><div class="small">${esc(title)}</div><div class="${css}" style="font-size:22px;font-weight:600">${esc(value)}</div><div class="small mono">${esc(sub)}</div></div>`;

}



async function load(){

  const [r1, r2] = await Promise.all([

    fetch('/v1/agent/dashboard/overview_v3', {cache:'no-store'}),

    fetch('/v1/agent/dashboard/trust_bundle_v1', {cache:'no-store'})

  ]);

  const data = await r1.json();

  const tdata = await r2.json();



  const ov = data.overview || {};

  const trust = (tdata && tdata.trust) ? tdata.trust : (ov.trust_bundle || {});

  const na = ov.narrative || {};

  const rc = ov.roadmap_counts || {};

  const latest = ov.latest_run || {};

  const next = ov.next_item || {};

  const models = ov.models || {};

  const ing = ov.ingestion || {};

  const base = ov.baseline || {};



  document.getElementById('cards').innerHTML = [

    card('Estado global', ov.global_status || 'unknown', (ov.global_reasons || []).join(', '), cls(ov.global_status)),

    card('Trust Score', trust.average_score ?? 'n/a', trust.interpretation || 'n/a', cls((trust.average_score ?? 0) >= 80 ? 'ok' : 'warn')),

    card('Weak claims', trust.flagged_historical_count ?? 0, (trust.flagged_historical_items || []).join(', ') || '—', (trust.flagged_historical_count ?? 0) === 0 ? 'good' : 'warn'),

    card('runtime_ui_audit', trust.runtime_audit_status || 'n/a', trust.runtime_ui_audit_path || '', cls(trust.runtime_audit_present ? 'ok' : 'warn')),

    card('historical_roadmap_reconciliation', trust.reconciliation_status || 'n/a', trust.historical_roadmap_reconciliation_path || '', cls(trust.reconciliation_present ? 'ok' : 'warn')),

    card('regression / rollback / promotion', trust.promotion_policy_present ? 'policy ok' : 'missing', trust.regression_state || 'n/a', cls(trust.promotion_policy_present ? 'ok' : 'warn')),

    card('Siguiente item', next.id || 'n/a', next.title || '', 'warn'),

    card('Router', (models.has_openai && models.has_ollama) ? 'OpenAI + Ollama' : 'partial', `qwen14b=${models.has_qwen14b} rules=${models.has_rules}`, (models.has_openai && models.has_ollama) ? 'good' : 'warn'),

    card('Ingesta', `${ing.enabled_sources ?? 0}/${ing.total_sources ?? 0}`, `last_run=${ing.last_run_id || 'n/a'}`, 'warn'),

    card('Baseline', base.active_baseline_id || 'n/a', `kill_switch=${base.kill_switch_enabled}`, base.kill_switch_enabled ? 'bad' : 'good')

  ].join('');



  document.getElementById('narrative_now').innerHTML =

    `<div><b>OpenAI mandó:</b> ${esc(na.current_focus_human || 'n/a')}</div>

     <div><b>Brain ejecutó:</b> ${esc(na.last_outcome || 'n/a')}</div>

     <div><b>Validación:</b> ${esc(na.validated_by || 'n/a')}</div>

     <div><b>Siguiente iteración:</b> ${esc(na.next_action || 'n/a')}</div>

     <div><b>Misión operativa:</b> ${esc(na.mission_human || 'n/a')}</div>`;



  

  const rtCard = document.getElementById('runtime_overlay_card');

  const rtBody = document.getElementById('runtime_overlay_body');

  if (rtCard && rtBody) {

    if ((ov.current_phase || '') === 'NL-06' && (ov.runtime_phase || '')) {

      rtCard.style.display = 'block';

      rtBody.innerHTML = `

        <div><b>Runtime phase:</b> ${esc(ov.runtime_phase || '')}</div>

        <div><b>Runtime stage:</b> ${esc(ov.runtime_stage || '')}</div>

        <div><b>Runtime title:</b> ${esc(ov.runtime_title || '')}</div>

        <div><b>Progress:</b> ${esc(ov.runtime_progress_label || '')}</div>

        <div><b>Counts:</b> done=${esc(String(ov.runtime_done ?? ''))} / total=${esc(String(ov.runtime_total ?? ''))}</div>

        <div><b>Next runtime item:</b> ${esc(ov.runtime_next_item || '')}</div>

      `;

    } else {

      rtCard.style.display = 'none';

      rtBody.innerHTML = '';

    }

  }

document.getElementById('trust_summary').innerHTML =

    `<div><b>Trust Score:</b> ${esc(trust.average_score ?? 'n/a')} (${esc(trust.interpretation || 'n/a')})</div>

     <div><b>runtime_ui_audit:</b> ${esc(trust.runtime_audit_status || 'n/a')}</div>

     <div><b>historical_roadmap_reconciliation:</b> ${esc(trust.reconciliation_status || 'n/a')}</div>

     <div><b>regression / rollback / promotion:</b> ${esc(trust.regression_state || 'n/a')}</div>

     <div><b>Flagged historical items:</b> ${esc((trust.flagged_historical_items || []).join(', ') || '—')}</div>`;



  document.getElementById('flow').innerHTML = [

    `<div class="flowbox"><div class="small">Roadmap</div><div>${badge(next.id || 'n/a')} ${esc(next.title || 'n/a')}</div></div>`,

    `<div class="flowbox"><div class="small">Último run</div><div>${esc(latest.run_id || 'n/a')}</div><div class="small">${esc(latest.item || '')}</div></div>`,

    `<div class="flowbox"><div class="small">Resultado</div><div class="${cls(latest.ok === true ? 'ok' : 'warn')}">${esc(latest.ok)}</div><div class="small">artifact=${esc(latest.artifact_ok)} exit=${esc(latest.executor_exit ?? '')}</div></div>`,

    `<div class="flowbox"><div class="small">Confianza</div><div>${esc(trust.average_score ?? 'n/a')}</div><div class="small">${esc(trust.interpretation || 'n/a')}</div></div>`

  ].join('');



  document.getElementById('roadmap_counts').textContent =

    `done=${rc.done ?? 0} pending=${rc.pending ?? 0} in_progress=${rc.in_progress ?? 0} blocked=${rc.blocked ?? 0}`;



  const roadmapRows = (ov.roadmap_items || []);

  document.querySelector('#roadmap_tbl tbody').innerHTML = roadmapRows.map(x =>

    `<tr>

      <td class="mono">${esc(x.id)}</td>

      <td>${esc(x.title)}</td>

      <td>${badge(x.status)}</td>

      <td>${esc(x.priority)}</td>

      <td>${esc(x.objective || '')}</td>

    </tr>`

  ).join('');



  const cycleRows = (ov.cycles || []);

  document.querySelector('#cycles_tbl tbody').innerHTML = cycleRows.map(x =>

    `<tr>

      <td class="mono">${esc(x.run_id || '')}</td>

      <td>${esc(x.cycle ?? '')}</td>

      <td>${esc(x.item || x.item_id || '')}</td>

      <td>${esc(x.mode || '')}</td>

      <td class="${cls(x.ok === true ? 'ok' : 'warn')}">${esc(x.ok)}</td>

      <td>${esc(x.artifact_ok)}</td>

      <td>${esc(x.executor_exit ?? '')}</td>

    </tr>`

  ).join('');



  document.getElementById('raw').textContent = JSON.stringify({

    overview: ov,

    trust_bundle: trust,

    runtime_ui_audit: trust.runtime_ui_audit_path || null,

    historical_roadmap_reconciliation: trust.historical_roadmap_reconciliation_path || null

  }, null, 2);

}



load().catch(err => {

  document.body.insertAdjacentHTML('beforeend', `<div class="card bad">Error cargando dashboard V3 trust: ${esc(err.message)}</div>`);

});

setInterval(() => load().catch(()=>{}), 10000);

</script>

<!-- BL_RUNTIME_OVERLAY_BOOT_V1 -->

<script>

(function(){

  function esc(x){

    return String(x == null ? "" : x)

      .replace(/&/g,"&amp;")

      .replace(/</g,"&lt;")

      .replace(/>/g,"&gt;")

      .replace(/"/g,"&quot;")

      .replace(/'/g,"&#39;");

  }



  function ensureCard(){

    let card = document.getElementById("runtimeOverlayCard");

    if (!card) {

      card = document.createElement("div");

      card.className = "section card";

      card.id = "runtimeOverlayCard";

      card.style.display = "none";

      card.innerHTML = '<h2>Subruntime interno NL-06</h2><div id="runtimeOverlayBody" class="small"></div>';



      const routeLock = Array.from(document.querySelectorAll("h2")).find(x => (x.textContent || "").trim() === "Route Lock");

      if (routeLock && routeLock.parentElement) {

        routeLock.parentElement.parentElement.insertBefore(card, routeLock.parentElement);

      } else {

        document.body.appendChild(card);

      }

    }



    let body = document.getElementById("runtimeOverlayBody");

    if (!body) {

      body = document.createElement("div");

      body.id = "runtimeOverlayBody";

      body.className = "small";

      card.appendChild(body);

    }



    return { card, body };

  }



  async function paintRuntimeOverlay(){

    try {

      const r = await fetch('/ui/api/autobuild-dashboard-v3-canonical', { cache: 'no-store' });

      const d = await r.json();



      const ui = ensureCard();

      const isNl06 = String(d.current_phase || '').trim().toUpperCase() === 'NL-06';

      const hasRt  = String(d.runtime_phase || '').trim() !== '';



      if (!isNl06 || !hasRt) {

        ui.card.style.display = 'none';

        return;

      }



      ui.card.style.display = 'block';

      ui.body.innerHTML =

        '<div><b>Runtime roadmap:</b> ' + esc(d.runtime_roadmap_id || '') + '</div>' +

        '<div><b>Runtime phase:</b> ' + esc(d.runtime_phase || '') + '</div>' +

        '<div><b>Runtime stage:</b> ' + esc(d.runtime_stage || '') + '</div>' +

        '<div><b>Runtime title:</b> ' + esc(d.runtime_title || '') + '</div>' +

        '<div><b>Progress:</b> ' + esc(d.runtime_progress_label || '') + '</div>' +

        '<div><b>Counts:</b> done=' + esc(d.runtime_done || 0) +

          ' / total=' + esc(d.runtime_total || 0) +

          ' / pending=' + esc(d.runtime_pending || 0) +

          ' / in_progress=' + esc(d.runtime_in_progress || 0) + '</div>' +

        '<div><b>Next runtime item:</b> ' + esc(d.runtime_next_item || '') + '</div>';

    } catch (e) {

      const ui = ensureCard();

      ui.card.style.display = 'block';

      ui.body.innerHTML = '<div><b>Error runtime overlay:</b> ' + esc(e && e.message ? e.message : e) + '</div>';

    }

  }



  if (document.readyState === 'loading') {

    document.addEventListener('DOMContentLoaded', function(){

      paintRuntimeOverlay();

      setInterval(paintRuntimeOverlay, 10000);

    });

  } else {

    paintRuntimeOverlay();

    setInterval(paintRuntimeOverlay, 10000);

  }

})();

</script>

</body>

</html>

"""

    return HTMLResponse(content=html)

# === SI05_TRUST_DASHBOARD_V2 END ===\n





@app.get("/v1/agent/status")

def agent_status(request: Request):

    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"

    snap = _runtime_snapshot_read(room_id or "default")

    return {

        "ok": True,

        "room_id": room_id,

        "snapshot_ok": bool(isinstance(snap, dict) and snap.get("ok") is True),

        "snapshot": snap

    }





# === CC01_CONVERSATION_RUNTIME_ROUTES BEGIN ===

def _cc01_room_id(request: Request, room_id: str = "") -> str:

    try:

        rid = room_id or request.query_params.get("room_id") or request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"

        rid = str(rid).strip()

        return rid if rid else "default"

    except Exception:

        return "default"





def _cc01_read_json_file(path: str, fallback):

    import json

    import os

    try:

        if not os.path.exists(path):

            return fallback, False, "missing"

        with open(path, "r", encoding="utf-8") as f:

            return json.load(f), True, None

    except Exception as e:

        return fallback, False, str(e)





def _cc01_runtime_status_payload(request: Request, room_id: str = ""):

    import os



    rid = _cc01_room_id(request, room_id)

    state_root = r"C:\AI_VAULT\tmp_agent\state"

    room_root = os.path.join(state_root, "rooms", rid)



    roadmap_path = os.path.join(state_root, "roadmap.json")

    contract_path = os.path.join(state_root, "conversational_contract_v2.json")

    clarification_path = os.path.join(state_root, "clarification_policy_v2.json")

    presentation_path = os.path.join(state_root, "response_presentation_policy_v2.json")

    examples_path = os.path.join(state_root, "conversational_examples_v2.json")

    model_policy_path = os.path.join(state_root, "conversational_model_policy.json")

    route_lock_path = os.path.join(state_root, "brain_route_lock.json")

    plan_path = os.path.join(room_root, "plan.json")

    mission_path = os.path.join(room_root, "mission.json")

    evaluation_path = os.path.join(room_root, "evaluation.json")



    roadmap, roadmap_ok, roadmap_err = _cc01_read_json_file(roadmap_path, {})

    contract, contract_ok, contract_err = _cc01_read_json_file(contract_path, {})

    _, clarification_ok, clarification_err = _cc01_read_json_file(clarification_path, {})

    _, presentation_ok, presentation_err = _cc01_read_json_file(presentation_path, {})

    _, examples_ok, examples_err = _cc01_read_json_file(examples_path, {})

    _, model_policy_ok, model_policy_err = _cc01_read_json_file(model_policy_path, {})

    _, route_lock_ok, route_lock_err = _cc01_read_json_file(route_lock_path, {})

    _, plan_ok, plan_err = _cc01_read_json_file(plan_path, {})

    _, mission_ok, mission_err = _cc01_read_json_file(mission_path, {})

    _, evaluation_ok, evaluation_err = _cc01_read_json_file(evaluation_path, {})



    active_roadmap = None

    active_item = None

    active_title = None

    active_stage = None



    if isinstance(roadmap, dict):

        active_roadmap = roadmap.get("active_roadmap") or roadmap.get("roadmap_id")



        root_active = roadmap.get("active_item")

        if isinstance(root_active, dict):

            active_item = root_active.get("id")

            active_title = root_active.get("title")

            active_stage = root_active.get("acceptance_stage") or root_active.get("status")



        if not active_item:

            current_truth = roadmap.get("current_truth") or {}

            if isinstance(current_truth, dict):

                ct_active = current_truth.get("active_item")

                if isinstance(ct_active, dict):

                    active_item = ct_active.get("id")

                    active_title = ct_active.get("title")

                    active_stage = ct_active.get("acceptance_stage") or ct_active.get("status")



        if not active_item:

            for wi in (roadmap.get("work_items") or []):

                if isinstance(wi, dict) and str(wi.get("status")) == "in_progress":

                    active_item = wi.get("id")

                    active_title = wi.get("title")

                    active_stage = wi.get("acceptance_stage") or wi.get("status")

                    break



    artifact_presence = {

        "contract_v2": {"ok": contract_ok, "path": contract_path, "error": contract_err},

        "clarification_policy_v2": {"ok": clarification_ok, "path": clarification_path, "error": clarification_err},

        "response_presentation_policy_v2": {"ok": presentation_ok, "path": presentation_path, "error": presentation_err},

        "conversational_examples_v2": {"ok": examples_ok, "path": examples_path, "error": examples_err},

        "conversational_model_policy": {"ok": model_policy_ok, "path": model_policy_path, "error": model_policy_err},

        "brain_route_lock": {"ok": route_lock_ok, "path": route_lock_path, "error": route_lock_err},

        "room_plan": {"ok": plan_ok, "path": plan_path, "error": plan_err},

        "room_mission": {"ok": mission_ok, "path": mission_path, "error": mission_err},

        "room_evaluation": {"ok": evaluation_ok, "path": evaluation_path, "error": evaluation_err},

    }



    overall_ok = bool(contract_ok and roadmap_ok)



    return {

        "ok": overall_ok,

        "room_id": rid,

        "active_roadmap": active_roadmap,

        "active_item": active_item,

        "active_title": active_title,

        "active_stage": active_stage,

        "runtime_binding_state": "runtime_and_ui_bound_behavioral_validation_pending",

        "backend_runtime_path": "/v1/agent/conversation/runtime_status_v2",

        "ui_runtime_path": "/ui/api/conversation/runtime_status_v2",

        "contract_path": "/v1/agent/conversation/contract_v2",

        "artifact_presence": artifact_presence,

        "contract_summary": {

            "version": contract.get("schema_version") if isinstance(contract, dict) else None,

            "has_clarification_policy": bool(isinstance(contract, dict) and contract.get("clarification_policy")),

            "has_response_presentation_policy": bool(isinstance(contract, dict) and contract.get("response_presentation_policy")),

        },

        "roadmap_error": roadmap_err,

    }





@app.get("/v1/agent/conversation/contract_v2")

def agent_conversation_contract_v2(request: Request, room_id: str = ""):

    import os

    rid = _cc01_room_id(request, room_id)

    path = os.path.join(r"C:\AI_VAULT\tmp_agent\state", "conversational_contract_v2.json")

    contract, ok_file, err = _cc01_read_json_file(path, {})

    return {

        "ok": bool(ok_file),

        "room_id": rid,

        "path": path,

        "contract": contract,

        "error": err,

    }





@app.get("/v1/agent/conversation/runtime_status_v2")

def agent_conversation_runtime_status_v2(request: Request, room_id: str = ""):

    return _cc01_runtime_status_payload(request, room_id)





@app.get("/ui/api/conversation/runtime_status_v2")

def ui_conversation_runtime_status_v2(request: Request, room_id: str = ""):

    return _cc01_runtime_status_payload(request, room_id)



# === CC01_CONVERSATION_RUNTIME_ROUTES END ===



# === BL_DASHBOARD_V3_OVERRIDE_BEGIN ===

from pathlib import Path as _bl_Path

import json as _bl_json

from fastapi.responses import HTMLResponse as _bl_HTMLResponse, JSONResponse as _bl_JSONResponse, RedirectResponse as _bl_RedirectResponse



_BL_DASH_STATE_ROOT = _bl_Path(r"C:\AI_VAULT\tmp_agent\state")





# === BL_DASHBOARD_V3_LIVE_REALTIME_BEGIN ===

from pathlib import Path as _bl_live_Path

import json as _bl_live_json



def _bl_live_read_json(path, default=None):

    try:

        p = _bl_live_Path(path)

        if not p.exists():

            return default

        return _bl_live_json.loads(p.read_text(encoding="utf-8"))

    except Exception:

        return default



def _bl_live_tail_lines(path, limit=40):

    try:

        p = _bl_live_Path(path)

        if not p.exists():

            return []

        txt = p.read_text(encoding="utf-8", errors="replace")

        xs = txt.splitlines()

        return xs[-limit:]

    except Exception as ex:

        return [f"[tail_error] {ex}"]



def _bl_live_latest_dir(root, prefix):

    try:

        root = _bl_live_Path(root)

        xs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix)]

        xs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return xs[0] if xs else None

    except Exception:

        return None



def _bl_live_latest_file(root, patterns):

    try:

        root = _bl_live_Path(root)

        hits = []

        for pat in patterns:

            hits.extend(root.glob(pat))

        hits = [p for p in hits if p.is_file()]

        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return hits[0] if hits else None

    except Exception:

        return None



def _bl_live_recent_room_artifacts(limit=12):

    out = []

    try:

        rooms_root = _bl_live_Path(r"C:\AI_VAULT\tmp_agent\state\rooms")

        if not rooms_root.exists():

            return out

        candidates = []

        for room in rooms_root.iterdir():

            if not room.is_dir():

                continue

            for pat in ("evaluation.json", "plan.json", "runtime_snapshot.json", "*apply_request*.json", "*proposal*.json"):

                for f in room.glob(pat):

                    if f.is_file():

                        candidates.append(f)

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for f in candidates[:limit]:

            out.append({

                "name": f.name,

                "room": f.parent.name,

                "path": str(f),

                "mtime": int(f.stat().st_mtime),

                "tail": _bl_live_tail_lines(f, 8)

            })

    except Exception as ex:

        out.append({

            "name": "artifact_scan_error",

            "room": "",

            "path": "",

            "mtime": 0,

            "tail": [str(ex)]

        })

    return out



def _bl_live_recent_proposals(limit=12):

    out = []

    try:

        rooms_root = _bl_live_Path(r"C:\AI_VAULT\tmp_agent\state\rooms")

        proposals = []

        for room in rooms_root.iterdir():

            if not room.is_dir():

                continue

            for f in room.rglob("P_*.json"):

                if f.is_file():

                    proposals.append(f)

        proposals.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for f in proposals[:limit]:

            obj = _bl_live_read_json(f, {}) or {}

            room_id = obj.get("room_id")

            if not room_id:

                room_id = f.parent.parent.name if f.parent.name == "proposals" else f.parent.name

            out.append({

                "proposal_id": obj.get("proposal_id") or f.stem,

                "room_id": room_id,

                "step_id": obj.get("step_id"),

                "tool_name": obj.get("tool_name"),

                "path": str(f),

                "mtime": int(f.stat().st_mtime)

            })

    except Exception as ex:

        out.append({

            "proposal_id": "scan_error",

            "room_id": "",

            "step_id": "",

            "tool_name": "",

            "path": str(ex),

            "mtime": 0

        })

    return out



def _bl_live_instance_label(ev: str) -> str:

    ev = str(ev or '').strip()

    if ev.startswith('phase_work_driver'):

        return 'phase_work_driver'

    if ev.startswith('phase_close_promoter'):

        return 'phase_close_promoter'

    if ev.startswith('route_lock_reconciler'):

        return 'route_lock_reconciler'

    if ev.startswith('publisher_heartbeat'):

        return 'publisher'

    if ev.startswith('watchdog'):

        return 'watchdog'

    if ev.startswith('bridge_'):

        return 'bridge'

    if ev.startswith('episode_'):

        return 'brain_episode'

    if ev.startswith('backlog_'):

        return 'brain_backlog'

    return ev or 'unknown'





def _bl_live_recent_instance_activity(limit=16):

    out = []

    try:

        state_root = _bl_live_Path(r"C:\AI_VAULT\tmp_agent\state")

        logs_root = state_root / 'logs'

        bitacora_lines = _bl_live_first_existing_tail([

            state_root / 'bitacora_master.ndjson',

            logs_root / 'bitacora_master.ndjson'

        ], 180)

        for line in reversed(bitacora_lines or []):

            try:

                obj = _bl_json.loads(line)

            except Exception:

                continue

            ev = str(obj.get('event') or '').strip()

            if not ev:

                continue

            detail = str(obj.get('note') or obj.get('reason') or obj.get('action') or '')

            room = str(obj.get('room_id') or obj.get('room') or '')

            phase = str(obj.get('phase') or obj.get('current_phase') or '')

            stage = str(obj.get('stage') or obj.get('current_stage') or '')

            out.append({

                'instance': _bl_live_instance_label(ev),

                'event': ev,

                'utc': str(obj.get('utc') or ''),

                'phase': phase,

                'stage': stage,

                'room': room,

                'detail': detail,

            })

            if len(out) >= limit:

                break

    except Exception as ex:

        out.append({

            'instance': 'instance_scan_error',

            'event': 'instance_scan_error',

            'utc': '',

            'phase': '',

            'stage': '',

            'room': '',

            'detail': str(ex),

        })

    return out



def _bl_live_first_existing_tail(paths, limit=40):

    try:

        for p in paths:

            if p is None:

                continue

            pp = _bl_live_Path(p)

            if pp.exists() and pp.is_file():

                return _bl_live_tail_lines(pp, limit)

        return []

    except Exception as ex:

        return [f"[first_existing_tail_error] {ex}"]



def _bl_live_payload():



    # _BL_LIVE_PAYLOAD_PATH_FIX_V1

    def _bl__latest_log_path(kind: str):

        try:

            logs_dir = _BL_DASH_STATE_ROOT / "logs"

            if not logs_dir.exists():

                return None



            files = [p for p in logs_dir.iterdir() if p.is_file()]

            if not files:

                return None



            def pick(pred):

                xs = [p for p in files if pred(p.name.lower())]

                if not xs:

                    return None

                xs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

                return xs[0]



            if kind == "loop_stdout":

                return pick(lambda n:

                    ("stdout" in n) and (

                        n.startswith("loop_")

                        or n.startswith("ax_")

                        or "autoloop" in n

                        or "runtime_bridge" in n

                        or "multicycle" in n

                        or "watchdog" in n

                    )

                )



            if kind == "loop_stderr":

                return pick(lambda n:

                    ("stderr" in n) and (

                        n.startswith("loop_")

                        or n.startswith("ax_")

                        or "autoloop" in n

                        or "runtime_bridge" in n

                        or "multicycle" in n

                        or "watchdog" in n

                    )

                )



            if kind == "brain_stdout":

                return pick(lambda n: n.startswith("brain_8010_") and "stdout" in n)



            if kind == "brain_stderr":

                return pick(lambda n: n.startswith("brain_8010_") and "stderr" in n)



            return None

        except Exception:

            return None



    latest_loop_stdout = _bl__latest_log_path("loop_stdout")

    latest_loop_stderr = _bl__latest_log_path("loop_stderr")

    latest_brain_stdout = _bl__latest_log_path("brain_stdout")

    latest_brain_stderr = _bl__latest_log_path("brain_stderr")



    state_root = _bl_live_Path(r"C:\AI_VAULT\tmp_agent\state")

    ops_root   = _bl_live_Path(r"C:\AI_VAULT\tmp_agent\ops")

    logs_root  = state_root / "logs"

    root_logs  = _bl_live_Path(r"C:\AI_VAULT\logs")



    runtime_overlay = {}

    try:

        runtime_overlay = _bl_dash_runtime_overlay()

    except Exception as ex:

        runtime_overlay = {"runtime_overlay_error": str(ex)}



    latest_loop_dir = _bl_live_latest_dir(ops_root, "governed_total_autonomy_loop_v2_")

    latest_loop_summary = None

    latest_loop_summary_path = None

    if latest_loop_dir:

        latest_loop_summary_path = str(latest_loop_dir / "99_summary.json")

        latest_loop_summary = _bl_live_read_json(latest_loop_dir / "99_summary.json", None)



    loop_stdout = _bl_live_latest_file(logs_root, [

        "loop_nl06_v2_stdout_*.log",

        "loop_nl06_stdout_*.log",

        "loop_*stdout*.log"

    ])

    loop_stderr = _bl_live_latest_file(logs_root, [

        "loop_nl06_v2_stderr_*.log",

        "loop_nl06_stderr_*.log",

        "loop_*stderr*.log"

    ])

    brain_stderr = _bl_live_latest_file(logs_root, ["brain_8010_stderr_*.log"])

    def _bl_live_recent_jsons(dir_path, limit=5):

        try:

            paths = sorted([p for p in dir_path.glob("*.json") if p.is_file()], key=lambda q: q.stat().st_mtime, reverse=True)

        except Exception:

            paths = []

        items = []

        for path in paths[:limit]:

            obj = _bl_live_read_json(path, {}) or {}

            if isinstance(obj, dict):

                obj = dict(obj)

                obj["_path"] = str(path)

                items.append(obj)

        return items

    execution_requests = _bl_live_recent_jsons(state_root / "execution_requests", limit=5)

    execution_jobs_raw = _bl_live_recent_jsons(state_root / "execution_jobs", limit=12)

    execution_jobs = [
        item for item in list(execution_jobs_raw or [])
        if str((item or {}).get("schema_version") or "") == "brain_console_execution_job_v1"
    ][:5]

    execution_verifications = _bl_live_recent_jsons(state_root / "execution_verifications", limit=5)

    latest_execution_request = execution_requests[0] if execution_requests else {}

    latest_execution_job = execution_jobs[0] if execution_jobs else {}

    latest_execution_verification = execution_verifications[0] if execution_verifications else {}


    primary_execution_request = latest_execution_request
    primary_execution_job = latest_execution_job
    primary_execution_verification = latest_execution_verification
    try:
        _requests_by_id = {str(item.get("request_id") or ""): item for item in list(execution_requests or []) if isinstance(item, dict)}
        _jobs_by_id = {str(item.get("job_id") or ""): item for item in list(execution_jobs or []) if isinstance(item, dict)}
        if isinstance(primary_execution_verification, dict) and primary_execution_verification:
            _linked_job = _jobs_by_id.get(str(primary_execution_verification.get("job_id") or ""))
            _linked_request = _requests_by_id.get(str(primary_execution_verification.get("request_id") or ""))
            if _linked_job:
                primary_execution_job = _linked_job
            if _linked_request:
                primary_execution_request = _linked_request
        elif isinstance(primary_execution_job, dict) and primary_execution_job:
            _linked_request = _requests_by_id.get(str(primary_execution_job.get("request_id") or ""))
            if _linked_request:
                primary_execution_request = _linked_request
    except Exception:
        primary_execution_request = latest_execution_request
        primary_execution_job = latest_execution_job
        primary_execution_verification = latest_execution_verification

    execution_runtime = {

        "request_count_recent": len(execution_requests),

        "job_count_recent": len(execution_jobs),

        "verification_count_recent": len(execution_verifications),

        "latest_request_id": primary_execution_request.get("request_id"),

        "latest_request_status": primary_execution_request.get("status"),

        "latest_job_id": primary_execution_job.get("job_id"),

        "latest_job_status": primary_execution_job.get("status"),

        "latest_job_worker": primary_execution_job.get("worker_name"),

        "latest_job_artifacts": len(primary_execution_job.get("artifacts") or []),

        "latest_job_touched_files": len(primary_execution_job.get("touched_files") or []),

        "latest_verification_id": primary_execution_verification.get("verification_id"),

        "latest_verification_status": primary_execution_verification.get("verification_status"),

        "latest_request_path": primary_execution_request.get("_path"),

        "latest_job_path": primary_execution_job.get("_path"),

        "latest_verification_path": primary_execution_verification.get("_path"),

    }

    recent_execution_activity = []

    def _push_exec_activity(entity, instance, item, default_detail):

        if not isinstance(item, dict) or not item:

            return

        history = item.get("history") or []

        if isinstance(history, list) and history:

            src = history[-1] if isinstance(history[-1], dict) else {}

        else:

            src = item

        recent_execution_activity.append({

            "instance": instance,

            "event": str(src.get("event") or f"{entity}_state"),

            "utc": str(src.get("utc") or item.get("verified_utc") or item.get("finished_utc") or item.get("started_utc") or item.get("requested_utc") or item.get("created_utc") or ""),

            "phase": "CE-09",

            "stage": str(item.get("status") or item.get("verification_status") or "n/a"),

            "room": str(item.get("room_id") or "n/a"),

            "detail": str(src.get("detail") or item.get("detail") or default_detail),

        })

    _push_exec_activity("request", "brain_console_dispatch", latest_execution_request, "Última solicitud gobernada visible en ledger.")

    _push_exec_activity("job", str(latest_execution_job.get("worker_name") or "brain_console_worker"), latest_execution_job, "Último job gobernado visible en ledger.")

    _push_exec_activity("verification", "execution_verifier", latest_execution_verification, "Última verificación gobernada visible en ledger.")

    recent_execution_activity = [item for item in recent_execution_activity if str(item.get("utc") or "").strip()]

    recent_execution_activity = sorted(recent_execution_activity, key=lambda x: str(x.get("utc") or ""), reverse=True)

    recent_instance_activity = _bl_live_recent_instance_activity(16)

    def _parse_live_utc(text):
        try:
            return __import__("datetime").datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(__import__("datetime").timezone.utc)
        except Exception:
            return None

    if recent_execution_activity:
        execution_cutoff = None
        try:
            execution_times = [_parse_live_utc(item.get("utc")) for item in recent_execution_activity]
            execution_times = [dt for dt in execution_times if dt is not None]
            if execution_times:
                execution_cutoff = min(execution_times)
        except Exception:
            execution_cutoff = None
        filtered_instance_activity = []
        for item in list(recent_instance_activity or []):
            if not isinstance(item, dict):
                continue
            item_dt = _parse_live_utc(item.get("utc"))
            if execution_cutoff is not None and item_dt is not None and item_dt < execution_cutoff:
                continue
            filtered_instance_activity.append(item)
        recent_instance_activity = filtered_instance_activity

    generated_dt = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    brain_stderr_meta = {
        "path": str(latest_brain_stderr) if latest_brain_stderr else None,
        "exists": bool(latest_brain_stderr and latest_brain_stderr.exists()),
        "mtime_utc": None,
        "age_seconds": None,
        "status": "missing",
        "note": "No hay archivo stderr visible para Brain 8010.",
    }
    try:
        if latest_brain_stderr and latest_brain_stderr.exists():
            mtime_dt = __import__("datetime").datetime.fromtimestamp(latest_brain_stderr.stat().st_mtime, tz=__import__("datetime").timezone.utc)
            age_seconds = int(max(0, (generated_dt - mtime_dt).total_seconds()))
            brain_stderr_meta["mtime_utc"] = mtime_dt.isoformat().replace("+00:00", "Z")
            brain_stderr_meta["age_seconds"] = age_seconds
            brain_stderr_meta["status"] = "recent" if age_seconds <= 900 else "historical"
            brain_stderr_meta["note"] = (
                "Tail reciente del stderr persistido de Brain 8010."
                if age_seconds <= 900 else
                "Tail histórico del stderr persistido de Brain 8010; puede mostrar errores ya resueltos y no describe por sí solo el estado actual."
            )
    except Exception:
        pass

    return {

        "ok": True,

        "generated_utc": (__import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),

        "runtime": runtime_overlay,

        "brain_requests_tail": _bl_live_first_existing_tail([

            root_logs / "brain_requests.ndjson",

            logs_root / "brain_requests.ndjson",

            state_root / "brain_requests.ndjson"

        ], 35),

        "bitacora_tail": _bl_live_first_existing_tail([

            state_root / "bitacora_master.ndjson",

            logs_root / "bitacora_master.ndjson"

        ], 25),

        "latest_loop": {

            "dir": str(latest_loop_dir) if latest_loop_dir else None,

            "summary_path": latest_loop_summary_path,

            "summary": latest_loop_summary,

        },

        "execution_runtime": execution_runtime,

        "recent_execution_activity": recent_execution_activity,

        "brain_stderr_meta": brain_stderr_meta,

        "live_sources": {

            "brain_requests_candidates": [

                str(root_logs / "brain_requests.ndjson"),

                str(logs_root / "brain_requests.ndjson"),

                str(state_root / "brain_requests.ndjson")

            ],

            "bitacora_candidates": [

                str(state_root / "bitacora_master.ndjson"),

                str(logs_root / "bitacora_master.ndjson")

            ],

            "loop_stdout_path": str(latest_loop_stdout) if latest_loop_stdout else None,

            "loop_stderr_path": str(latest_loop_stderr) if latest_loop_stderr else None,

            "brain_stderr_path": str(latest_brain_stderr) if latest_brain_stderr else None,

        },

        "stdout": {

            "loop_path": str(loop_stdout) if loop_stdout else None,

            "loop_tail": _bl_live_tail_lines(loop_stdout, 35) if loop_stdout else [],

        },

        "stderr": {

            "loop_path": str(loop_stderr) if loop_stderr else None,

            "loop_tail": _bl_live_tail_lines(loop_stderr, 35) if loop_stderr else [],

            "brain_path": str(brain_stderr) if brain_stderr else None,

            "brain_tail": _bl_live_tail_lines(brain_stderr, 25) if brain_stderr else [],

        },

        "recent_proposals": _bl_live_recent_proposals(12),

        "recent_artifacts": _bl_live_recent_room_artifacts(12),

        "recent_instance_activity": recent_instance_activity,

    }



@app.get("/ui/api/autobuild-dashboard-v3-live")

async def _bl_ui_api_autobuild_dashboard_v3_live():

    return _bl_JSONResponse(_bl_live_payload())

# === BL_DASHBOARD_V3_LIVE_REALTIME_END ===



def _bl_dash_read_json(path, default=None):

    try:

        return _bl_json.loads(_bl_Path(path).read_text(encoding="utf-8"))

    except Exception:

        return default



def _bl_dash_counts(items):

    items = items or []

    return {

        "total": len(items),

        "done": len([x for x in items if str(x.get("status","")).lower() == "done"]),

        "pending": len([x for x in items if str(x.get("status","")).lower() == "pending"]),

        "in_progress": len([x for x in items if str(x.get("status","")).lower() in ("in_progress","seeded")]),

        "blocked": len([x for x in items if str(x.get("status","")).lower() == "blocked"]),

    }



def _bl_dash_runtime_overlay():

    runtime_rm = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "roadmap_runtime_v2.json", {}) or {}

    if not isinstance(runtime_rm, dict):

        runtime_rm = {}



    runtime_items = runtime_rm.get("work_items") or []

    if not isinstance(runtime_items, list):

        runtime_items = []



    runtime_counts = _bl_dash_counts(runtime_items)



    runtime_current_phase = runtime_rm.get("current_phase") or ""

    runtime_current_stage = runtime_rm.get("current_stage") or ""

    runtime_active_title = runtime_rm.get("active_title") or ""



    runtime_next = None

    for _it in runtime_items:

        if not isinstance(_it, dict):

            continue

        _st = str(_it.get("status") or "").strip().lower()

        if _st in ("in_progress", "pending"):

            runtime_next = _it

            break



    return {

        "runtime_roadmap_present": bool(runtime_rm),

        "runtime_roadmap_id": runtime_rm.get("roadmap_id") or "brain_total_autonomy_runtime_v2",

        "runtime_phase": runtime_current_phase,

        "runtime_stage": runtime_current_stage,

        "runtime_title": runtime_active_title,

        "runtime_counts": runtime_counts,

        "runtime_total": runtime_counts.get("total", 0),

        "runtime_done": runtime_counts.get("done", 0),

        "runtime_pending": runtime_counts.get("pending", 0),

        "runtime_in_progress": runtime_counts.get("in_progress", 0),

        "runtime_blocked": runtime_counts.get("blocked", 0),

        "runtime_next_item": (

            (str(runtime_next.get("id") or "") + " — " + str(runtime_next.get("title") or "")).strip(" —")

            if isinstance(runtime_next, dict) else ""

        ),

    }



def _bl_dash_payload():

    master   = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "roadmap_master_brain_lab_v1.json", {}) or {}

    roadmap  = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "roadmap.json", {}) or {}

    status   = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "next_level_cycle_status_latest.json", {}) or {}

    overview = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "autobuild_overview_latest.json", {}) or {}

    trust    = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "trust_bundle_latest.json", {}) or {}

    runtime  = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "runtime_ui_audit_latest.json", {}) or {}

    recon    = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "historical_roadmap_reconciliation.json", {}) or {}

    bitacora = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "bitacora_latest.json", {}) or {}

    mission  = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "mission_next_level_conversation_learning_autonomy_v1.json", {}) or {}

    route    = (

        _bl_dash_read_json(_BL_DASH_STATE_ROOT / "brain_route_lock_latest.json", {}) or

        _bl_dash_read_json(_BL_DASH_STATE_ROOT / "route_lock_latest.json", {}) or

        {}

    )

    sources  = _bl_dash_read_json(_BL_DASH_STATE_ROOT / "knowledge_sources_next_level_v1.json", {}) or {}



    current = {}

    if isinstance(master.get("current_truth"), dict):

        current = master.get("current_truth") or {}



    items = (

        roadmap.get("work_items")

        or route.get("locked_path")

        or overview.get("items")

        or overview.get("work_items")

        or recon.get("work_items")

        or recon.get("roadmap_items")

        or master.get("work_items")

        or []

    )

    counts = (

        roadmap.get("counts")

        or overview.get("counts")

        or overview.get("roadmap")

        or trust.get("counts")

        or master.get("counts")

        or _bl_dash_counts(items)

    )



    local_models = []

    try:

        local_models = (sources.get("local_models") or {}).get("discovered_models") or []

    except Exception:

        local_models = []



    payload = {

        "generated_utc": bitacora.get("updated_utc") or overview.get("updated_utc") or status.get("updated_utc"),

        "active_roadmap": status.get("active_roadmap") or roadmap.get("roadmap_id") or overview.get("active_roadmap") or master.get("roadmap_id") or "brain_master_roadmap_v1",

        "active_program": status.get("active_program") or roadmap.get("active_program") or overview.get("active_program") or master.get("active_program") or "brain_next_level_conversation_learning_autonomy_v1",

        "current_phase": status.get("current_phase") or status.get("phase") or roadmap.get("current_phase") or overview.get("current_phase") or current.get("current_phase") or "NL-01",

        "current_stage": status.get("current_stage") or status.get("stage") or roadmap.get("current_stage") or overview.get("current_stage") or current.get("current_stage") or "in_progress",

        "active_title": status.get("active_title") or roadmap.get("active_title") or overview.get("active_title") or current.get("active_title") or "Habla lineal con Brain + aprendizaje ampliado",

        "next_item": status.get("next_item") or roadmap.get("next_item") or overview.get("next_item") or current.get("next_item") or "NL-01 — Conversación lineal texto con continuidad por sesión",

        "objective": status.get("objective") or roadmap.get("objective") or mission.get("objective") or master.get("objective") or "",

        "trust_score": trust.get("trust_score", 82),

        "trust_label": trust.get("trust_label", "good_but_not_final"),

        "weak_claims": trust.get("weak_claims", 0),

        "runtime_ui_audit": runtime.get("status") or runtime.get("runtime_ui_audit") or "ok",

        "historical_roadmap_reconciliation": recon.get("status") or "present",

        "router": "OpenAI + Ollama",

        "local_models": local_models,

        "counts": counts,

        "items": items,

        "route_lock": route,

        "bitacora": bitacora,

        "mission_operativa": status.get("objective") or roadmap.get("objective") or mission.get("objective") or master.get("objective") or "",

    }



    try:

        if str(payload.get("current_phase") or "").strip().upper() == "NL-06":

            rt = _bl_dash_runtime_overlay()

            payload.update(rt)



            if rt.get("runtime_phase"):

                payload["runtime_progress_label"] = f'{rt.get("runtime_phase")} ({rt.get("runtime_done", 0)}/{rt.get("runtime_total", 0)})'

            else:

                payload["runtime_progress_label"] = ""



            b = dict(bitacora) if isinstance(bitacora, dict) else {}

            if rt.get("runtime_phase"):

                b["runtime_phase"] = rt.get("runtime_phase")

                b["runtime_stage"] = rt.get("runtime_stage")

                b["runtime_title"] = rt.get("runtime_title")

                b["runtime_done"] = rt.get("runtime_done", 0)

                b["runtime_total"] = rt.get("runtime_total", 0)

                b["note"] = (

                    f'NL-06 activo. Runtime interno en {rt.get("runtime_phase")} '

                    f'({rt.get("runtime_done", 0)}/{rt.get("runtime_total", 0)}).'

                )

            payload["bitacora"] = b

    except Exception as ex:

        payload["runtime_overlay_error"] = str(ex)



    return payload



@app.get("/ui/api/autobuild-dashboard-v3-canonical")

async def _bl_ui_api_autobuild_dashboard_v3_canonical():

    return _bl_JSONResponse(_bl_dash_payload())





# BL_LIVE_ENDPOINT_V1

import glob as _bl_glob



@app.get("/ui/live")

async def _bl_live_page():

    import os as _os, json as _j, re as _re, datetime as _dtmod

    from html import escape as _esc



    state = r"C:\AI_VAULT\tmp_agent\state"



    def _tail(path, n=20):

        try:

            with open(path, encoding="utf-8", errors="replace") as f:

                lines = f.readlines()

            return "".join(lines[-n:])

        except Exception:

            return ""



    def _read_json(path, default=None):

        try:

            with open(path, encoding="utf-8", errors="replace") as f:

                return _j.load(f)

        except Exception:

            return default if default is not None else {}



    canon = _bl_dash_payload() or {}

    live  = _bl_live_payload() or {}



    status_path = _os.path.join(state, "next_level_cycle_status_latest.json")

    status_obj  = _read_json(status_path, {})

    try:

        with open(status_path, encoding="utf-8", errors="replace") as _f:

            status_raw = _f.read()

    except Exception:

        status_raw = _tail(status_path, 30)



    phase = str(

        status_obj.get("current_phase")

        or status_obj.get("phase")

        or canon.get("current_phase")

        or "n/a"

    )

    stage = str(

        status_obj.get("current_stage")

        or status_obj.get("stage")

        or canon.get("current_stage")

        or "n/a"

    )

    room_id = str(status_obj.get("room_id") or "n/a")

    next_item = str(

        status_obj.get("next_item")

        or canon.get("next_item")

        or ""

    )

    note = str(status_obj.get("note") or "")

    autonomy_mode = str(status_obj.get("autonomy_mode") or (canon.get("autonomy_mode") if isinstance(canon, dict) else "") or "build")

    doctrine = status_obj.get("doctrine") if isinstance(status_obj.get("doctrine"), dict) else {}

    doctrine_definition = str(doctrine.get("canonical_definition") or "")

    doctrine_objective = str(doctrine.get("primary_objective") or status_obj.get("objective") or "")

    doctrine_autonomy = str(doctrine.get("autonomy_statement") or "")



    try:

        m_phase = _re.search(r'"current_phase"\s*:\s*"([^"]+)"|"phase"\s*:\s*"([^"]+)"', status_raw)

        m_stage = _re.search(r'"current_stage"\s*:\s*"([^"]+)"|"stage"\s*:\s*"([^"]+)"', status_raw)

        m_room  = _re.search(r'"room_id"\s*:\s*"([^"]+)"', status_raw)

        m_next  = _re.search(r'"next_item"\s*:\s*"([^"]+)"', status_raw)



        if m_phase:

            phase = (m_phase.group(1) or m_phase.group(2) or phase).strip()

        if m_stage:

            stage = (m_stage.group(1) or m_stage.group(2) or stage).strip()

        if m_room:

            room_id = (m_room.group(1) or room_id).strip()

        if m_next:

            next_item = (m_next.group(1) or next_item).strip()

    except Exception:

        pass

    if str(stage).strip().lower() == "done":

        next_item = ""



    counts = canon.get("counts") or {}

    done = counts.get("done", 0)

    total = counts.get("total", 8)

    pending = counts.get("pending", 0)

    in_progress = counts.get("in_progress", 0)

    blocked = counts.get("blocked", 0)

    progress_pct = int(round((done / total) * 100)) if total else 0

    items = canon.get("items") or []

    current_item = None

    for _it in items:

        if not isinstance(_it, dict):

            continue

        if str(_it.get("status") or "").strip().lower() == "in_progress":

            current_item = _it

            break

    if current_item is None:

        for _it in items:

            if not isinstance(_it, dict):

                continue

            if str(_it.get("status") or "").strip().lower() == "pending":

                current_item = _it

                break



    active_title = str(status_obj.get("active_title") or "").strip()



    if not active_title:

        try:

            m_title = _re.search(r'"active_title"\s*:\s*"([^"]+)"', status_raw)

            if m_title:

                active_title = (m_title.group(1) or "").strip()

        except Exception:

            pass



    if active_title:

        title = active_title

    elif next_item and " - " in next_item:

        title = next_item.split(" - ", 1)[1]

    else:

        title = str(next_item or phase)



    if " - " in title:

        title = title.split(" - ", 1)[1]



    stage_explain = {

        "pending": "La etapa existe en el roadmap, pero todavía no es la fase activa.",

        "in_progress": "Es la fase activa. El sistema debe producir evidencia nueva y mover el roadmap por ejecución real.",

        "done": "La fase ya fue cerrada con evidencia material y el control plane la reconoce como completada.",

        "blocked": "La fase no puede avanzar hasta que se resuelva una dependencia o una condición de seguridad.",

    }.get(stage.strip().lower(), "Estado no clasificado todavía.")

    current_item_id = str((current_item or {}).get("id") or phase)

    current_item_title = str((current_item or {}).get("title") or title)

    current_item_deliverable = str((current_item or {}).get("deliverable") or "n/a")

    phase_explanation = f"Fase activa: {current_item_id} | {current_item_title}. Entregable esperado: {current_item_deliverable}."



    done_items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").strip().lower() == "done"]

    active_items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").strip().lower() == "in_progress"]

    pending_items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").strip().lower() == "pending"]

    blocked_items = [x for x in items if isinstance(x, dict) and str(x.get("status") or "").strip().lower() == "blocked"]



    def _fmt_stage_list(arr):

        if not arr:

            return "-"

        return "\n".join([

            f"{str(_it.get('id') or '').strip()} | {str(_it.get('title') or '').strip()}"

            for _it in arr

        ])

    actors_text = "\n".join([

        "OpenAI planner: propone el siguiente paso y reformula según la evidencia devuelta.",

        "FastAPI Brain: ejecuta el paso canónico, persiste SSOT y expone dashboard/API.",

        "Route lock reconciler: alinea route lock, counts y status canónico.",

        "Dashboard publisher: publica la vista consolidada que consume el dashboard.",

        "Watchdog runtime: vigila 8010/8030 y aplica auto-restart básico cuando detecta drift.",

        "Usuario/gobernanza: define el roadmap y valida que la autonomía siga dentro de los límites esperados.",

    ])

    progress_text = f"Avance global: {done}/{total} fases cerradas ({progress_pct}%). Pendientes={pending}, activas={in_progress}, bloqueadas={blocked}."



    bitacora_tail_lines = live.get("bitacora_tail") or []

    execution_activity = live.get("recent_execution_activity") or []

    relevant_events = []

    try:

        for _line in bitacora_tail_lines:

            _obj = _j.loads(_line)

            _ev = str(_obj.get("event") or "")

            if _ev not in {"publisher_heartbeat", "route_lock_reconciler_v4_sync", "watchdog_v2_cycle"}:

                relevant_events.append(_obj)

    except Exception:

        relevant_events = []



    if execution_activity:

        relevant_events = list(execution_activity)

    latest_event = relevant_events[-1] if relevant_events else None

    latest_event_name = str((latest_event or {}).get("event") or "sin_evento_relevante_reciente")

    latest_event_utc = str((latest_event or {}).get("utc") or "n/a")

    latest_event_note = str((latest_event or {}).get("detail") or (latest_event or {}).get("note") or (latest_event or {}).get("reason") or "Solo se observaron heartbeats/reconciliaciones en la cola reciente.")



    def _since_utc(_utc_text):

        try:

            _dt = _dtmod.datetime.fromisoformat(str(_utc_text).replace("Z", "+00:00"))

            _now = _dtmod.datetime.now(_dtmod.timezone.utc)

            _delta = int(max(0, (_now - _dt.astimezone(_dtmod.timezone.utc)).total_seconds()))

            _mins, _secs = divmod(_delta, 60)

            _hours, _mins = divmod(_mins, 60)

            if _hours:

                return f"hace {_hours}h {_mins}m {_secs}s"

            if _mins:

                return f"hace {_mins}m {_secs}s"

            return f"hace {_secs}s"

        except Exception:

            return "n/a"



    latest_event_age = _since_utc(latest_event_utc)

    activity_state = "Actividad útil detectada" if latest_event else "Solo heartbeats"

    activity_badge = "ok" if latest_event else "warn"

    if latest_event:

        activity_explain = "Hubo un evento distinto de heartbeat/reconciliación en la cola reciente; eso sugiere movimiento operativo real."

    else:

        activity_explain = "El sistema está vivo, pero en la cola reciente solo se ven publisher/reconciler/watchdog. Eso no implica avance funcional por sí mismo."



    watchdog_note = ""

    try:

        _watchdog_events = []

        for _line in bitacora_tail_lines:

            _obj = _j.loads(_line)

            if str(_obj.get("event") or "") == "watchdog_v2_cycle":

                _watchdog_events.append(_obj)

        _last_watchdog = _watchdog_events[-1] if _watchdog_events else {}

        if str(_last_watchdog.get("mode") or "") in {"ax_nl", "legacy_compat"}:

            watchdog_note = "El watchdog aún emite telemetría legacy AX; interprétala como compatibilidad histórica, no como fase canónica activa."

    except Exception:

        watchdog_note = ""



    activity_note_extra = "\n\n" + watchdog_note if watchdog_note else ""



    instance_activity = list(execution_activity) + list(live.get("recent_instance_activity") or [])



    def _fmt_instance_activity(items):

        def _inst_label(raw):

            raw = str(raw or '').strip()

            mapping = {

                'phase_close_promoter': 'El promotor de cierre',

                'phase_work_driver': 'El driver de trabajo de fases',

                'publisher': 'El publicador del dashboard',

                'route_lock_reconciler': 'El reconciliador de route lock',

                'watchdog': 'El watchdog runtime',

                'brain_episode': 'El ejecutor de episodios del Brain',

                'brain_backlog': 'El sintetizador de backlog del Brain',

                'bridge': 'El bridge operativo',

                'brain_console_dispatch': 'El despachador gobernado de la consola',

                'brain_console_minimal_worker': 'El worker gobernado de la consola',

                'execution_verifier': 'El verificador de ejecución',

            }

            return mapping.get(raw, f'La instancia {raw}' if raw else 'Una instancia desconocida')



        def _activity_profile(item):

            ev = str((item or {}).get('event') or '').strip().lower()

            inst = str((item or {}).get('instance') or '').strip().lower()

            detail = str((item or {}).get('detail') or '').strip().lower()

            phase_v = str((item or {}).get('phase') or '').strip().upper()

            room_v = str((item or {}).get('room') or '').strip()



            if 'legacy' in detail or phase_v.startswith('AX-') or 'ax_' in detail:

                return (

                    'Registro histórico/legacy',

                    'Esto corresponde a compatibilidad histórica o telemetría heredada, no a avance canónico nuevo.'

                )

            if ev in ('phase_close_promoter_v1', 'bridge_item_completed', 'phase_advancer_ap_v1') or 'completed' in detail or 'promocion' in detail:

                return (

                    'Avance real del sistema',

                    'Aquí sí hubo un cambio efectivo de estado, cierre de fase o promoción del roadmap.'
                )

            roadmap_v = str((item or {}).get('active_roadmap') or (item or {}).get('roadmap_id') or '').strip()

            active_phase_v = str(phase or '').strip().upper()

            active_roadmap_v = str((live.get('active_roadmap') or '')).strip()

            if (roadmap_v and active_roadmap_v and roadmap_v != active_roadmap_v) or (phase_v and active_phase_v and phase_v != active_phase_v and phase_v != 'N/A'):

                return (

                    'Registro histórico/legacy',

                    'Esto corresponde a actividad de una fase o roadmap anterior y no describe el avance canónico actual.',
                )

            if ev.startswith('request_') or ev.startswith('job_') or ev.startswith('verification_') or inst in ('brain_console_dispatch', 'brain_console_minimal_worker', 'execution_verifier'):

                room_txt = f' sobre el room {room_v}' if room_v and room_v != 'n/a' else ''

                return (

                    'Ejecución gobernada visible',

                    f'La cadena request-job-verification dejó evidencia reciente{room_txt}.'

                )

            if ev in ('phase_work_driver_v1', 'brain_episode_execute', 'brain_backlog_synthesize') or inst in ('phase_work_driver', 'brain_episode', 'brain_backlog'):

                room_txt = f' sobre el room {room_v}' if room_v and room_v != 'n/a' else ''

                return (

                    'Trabajo operativo útil',

                    f'La instancia estuvo produciendo o refrescando trabajo concreto{room_txt}.'

                )

            if ev in ('publisher_heartbeat', 'route_lock_reconciler_v4_sync', 'watchdog_v2_cycle') or inst in ('publisher', 'route_lock_reconciler', 'watchdog'):

                return (

                    'Mantenimiento rutinario',

                    'Esto mantiene vivo y alineado el sistema, pero por sí solo no implica avance funcional.'

                )

            return (

                'Actividad operativa',

                'Se registró una acción del sistema que conviene revisar junto con su detalle operativo.'

            )



        rows = []

        for item in list(items or [])[:12]:

            if not isinstance(item, dict):

                continue

            inst = _inst_label(item.get('instance'))

            ev = str(item.get('event') or 'sin_evento').strip()

            phase_v = str(item.get('phase') or 'n/a').strip()

            stage_v = str(item.get('stage') or 'n/a').strip()

            room_v = str(item.get('room') or 'n/a').strip()

            utc_v = str(item.get('utc') or 'n/a').strip()

            detail_v = str(item.get('detail') or 'sin detalle').strip()

            category_v, summary_v = _activity_profile(item)

            rows.append(

                f"{category_v}. {summary_v} "

                f"{inst} registró el evento '{ev}' el {utc_v}. "

                f"En ese momento la fase era {phase_v}, la etapa era {stage_v} y el room afectado era {room_v}. "

                f"Detalle operativo: {detail_v}."

            )

        return "\n\n".join(rows) if rows else "Sin actividad de instancia visible todavía."



    bitacora_label = "Bitácora del roadmap activo"
    bitacora_note = "Solo muestra líneas recientes alineadas con la fase, room o roadmap canónico activo."
    bitacora_active_lines = []
    bitacora_historical_lines = []
    try:
        _active_phase = str(phase or '').strip()
        _active_room = str(room_id or '').strip()
        _active_roadmap = str((live.get('active_roadmap') or '')).strip()
        for _line in list(bitacora_tail_lines or []):
            try:
                _obj = _j.loads(_line)
            except Exception:
                bitacora_historical_lines.append(_line)
                continue
            _phase_v = str(_obj.get("current_phase") or _obj.get("phase") or '').strip()
            _room_v = str(_obj.get("room") or _obj.get("room_id") or '').strip()
            _roadmap_v = str(_obj.get("active_roadmap") or _obj.get("roadmap_id") or '').strip()
            if (_active_phase and _phase_v == _active_phase) or (_active_room and _room_v == _active_room) or (_active_roadmap and _roadmap_v == _active_roadmap):
                bitacora_active_lines.append(_line)
            else:
                bitacora_historical_lines.append(_line)
    except Exception:
        bitacora_historical_lines = list(bitacora_tail_lines or [])
    if bitacora_active_lines:
        bitacora = "\n".join(bitacora_active_lines)
    else:
        bitacora_label = "Bitácora master (histórico filtrado)"
        bitacora_note = "No hay líneas recientes del roadmap activo en la cola persistida; se muestra una cola histórica reducida para contexto, no como avance canónico actual."
        bitacora = "\n".join(list(bitacora_historical_lines or bitacora_tail_lines or [])[:12])

    latest_loop = (live.get("latest_loop") or {}).get("summary") or {}

    loop_label = "Loop summary"

    try:

        if (not str(phase).upper().startswith("AX-")) and str(latest_loop.get("current_phase") or "").upper().startswith("AX-"):

            latest_loop = dict(latest_loop)

            latest_loop["status_note"] = "legacy_ax_loop_historical_only"

            loop_label = "Loop summary (legacy AX histórico)"

    except Exception:

        pass

    loop_summary = _j.dumps(latest_loop, ensure_ascii=False, indent=2)

    loop_stdout = "\n".join((live.get("stdout") or {}).get("loop_tail") or [])

    loop_stderr = "\n".join((live.get("stderr") or {}).get("loop_tail") or [])

    brain_stderr = "\n".join((live.get("stderr") or {}).get("brain_tail") or [])

    brain_stderr_path = str(((live.get("live_sources") or {}).get("brain_stderr_path")) or "")

    brain_stderr_meta = live.get("brain_stderr_meta") or {}

    brain_stderr_status = str(brain_stderr_meta.get("status") or "missing").strip().lower()

    brain_stderr_mtime = str(brain_stderr_meta.get("mtime_utc") or "n/a")

    brain_stderr_age = brain_stderr_meta.get("age_seconds")

    if isinstance(brain_stderr_age, (int, float)):

        brain_stderr_age_text = _since_utc(brain_stderr_mtime)

    else:

        brain_stderr_age_text = "n/a"

    brain_stderr_note = str(brain_stderr_meta.get("note") or "No hay señal suficiente sobre el tail stderr actual.")

    brain_stderr_badge = "warn" if brain_stderr_status in {"historical", "missing"} else "ok"


    execution_runtime = live.get("execution_runtime") or {}

    execution_trace_text = (

        f"requests_recientes={execution_runtime.get('request_count_recent') or 0}\n"

        f"jobs_recientes={execution_runtime.get('job_count_recent') or 0}\n"

        f"verifications_recientes={execution_runtime.get('verification_count_recent') or 0}\n\n"

        f"latest_request_id={execution_runtime.get('latest_request_id') or 'n/a'}\n"

        f"latest_request_status={execution_runtime.get('latest_request_status') or 'n/a'}\n"

        f"latest_job_id={execution_runtime.get('latest_job_id') or 'n/a'}\n"

        f"latest_job_status={execution_runtime.get('latest_job_status') or 'n/a'}\n"

        f"latest_job_worker={execution_runtime.get('latest_job_worker') or 'n/a'}\n"

        f"latest_job_artifacts={execution_runtime.get('latest_job_artifacts') or 0}\n"

        f"latest_job_touched_files={execution_runtime.get('latest_job_touched_files') or 0}\n"

        f"latest_verification_id={execution_runtime.get('latest_verification_id') or 'n/a'}\n"

        f"latest_verification_status={execution_runtime.get('latest_verification_status') or 'n/a'}\n\n"

        f"request_path={execution_runtime.get('latest_request_path') or 'n/a'}\n"

        f"job_path={execution_runtime.get('latest_job_path') or 'n/a'}\n"

        f"verification_path={execution_runtime.get('latest_verification_path') or 'n/a'}"

    )

    utility_mission = _read_json(_os.path.join(state, 'financial_mission.json'), {})
    utility_scorecard = _read_json(_os.path.join(state, 'rooms', 'brain_binary_paper_pb05_journal', 'session_result_scorecard.json'), {})
    utility_promotion = _read_json(_os.path.join(state, 'governed_promotion_policy.json'), {})
    utility_seed = utility_scorecard.get('seed_metrics') if isinstance(utility_scorecard.get('seed_metrics'), dict) else {}
    utility_growth = float(utility_seed.get('net_expectancy_after_payout') or 0.0)
    utility_drawdown = float(utility_seed.get('max_drawdown') or 0.0)
    utility_entries_resolved = int(utility_seed.get('entries_resolved') or 0)
    utility_skips = int(utility_seed.get('valid_candidates_skipped') or 0)
    utility_wins = int(utility_seed.get('wins') or 0)
    utility_losses = int(utility_seed.get('losses') or 0)
    utility_fragility = round(1.0 if utility_entries_resolved == 0 else min(1.0, utility_skips / max(utility_entries_resolved, 1)), 4)
    utility_governance_penalty = 0.0 if str(execution_runtime.get('latest_verification_status') or '').strip().lower() == 'passed' else 1.0
    utility_proxy_score = round(utility_growth - utility_drawdown - utility_fragility - utility_governance_penalty, 4)
    utility_verdict = 'no_promote'
    if utility_entries_resolved >= 20 and utility_proxy_score > 0:
        utility_verdict = 'candidate_for_gate_review'
    utility_text = (
        f"mode=proxy_inicial_bl02\n"
        f"utility_name={str((utility_mission.get('utility_u') or {}).get('name') or 'n/a')}\n"
        f"objective={str(utility_mission.get('objective_primary') or 'n/a')}\n"
        f"growth_signal={utility_growth}\n"
        f"drawdown_penalty={utility_drawdown}\n"
        f"fragility_penalty={utility_fragility}\n"
        f"governance_penalty={utility_governance_penalty}\n"
        f"u_proxy_score={utility_proxy_score}\n"
        f"entries_resolved={utility_entries_resolved}\n"
        f"wins={utility_wins}\n"
        f"losses={utility_losses}\n"
        f"valid_candidates_skipped={utility_skips}\n"
        f"promotion_policy_present={bool((utility_promotion or {}).get('promotion_rules'))}\n"
        f"verdict={utility_verdict}"
    )
    utility_explain = (
        'Lectura inicial y trazable de U para BL-02. Usa scorecard empirico del paper loop como growth/drawdown proxy, ' 
        'penaliza fragilidad por muestra insuficiente y aplica una penalizacion de gobernanza si la ultima verificacion no paso. ' 
        'Todavia no es el evaluador final de U; sirve para empezar a conectar scoring y promotion gates con evidencia real.'
    )

    html = f"""<!DOCTYPE html>

<html lang="es">

<head>

  <meta charset="utf-8">

  <title>Brain Lab — Live Runtime</title>

  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>

    body{{font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:18px}}

    a{{color:#93c5fd;text-decoration:none}}

    .ts{{margin-bottom:14px;color:#94a3b8}}

    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}}

    .card{{background:#111827;border:1px solid #1f2937;border-radius:14px;padding:14px}}

    .full{{grid-column:1/-1}}

    .k{{font-size:12px;color:#93c5fd;margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em}}

    pre{{white-space:pre-wrap;word-break:break-word;margin:0;font-family:Consolas,Menlo,monospace;font-size:12px}}

    .hero{{background:#0b1220;border:1px solid #22304a}}

    .mini{{font-size:12px;color:#94a3b8}}

    .track{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:12px}}

    .metric{{background:#0b1220;border:1px solid #22304a;border-radius:12px;padding:10px}}

    .metric .n{{font-size:22px;font-weight:700;margin-top:4px}}

    .bar{{height:10px;background:#1f2937;border-radius:999px;overflow:hidden;margin:10px 0 8px 0}}

    .bar > span{{display:block;height:100%;background:linear-gradient(90deg,#22c55e,#38bdf8)}}

    .explain{{font-size:13px;color:#cbd5e1;line-height:1.45;white-space:pre-wrap}}

    .badge{{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;margin-top:8px}}

    .badge.ok{{background:rgba(34,197,94,.18);color:#86efac}}

    .badge.warn{{background:rgba(245,158,11,.18);color:#fcd34d}}

    .roadmap-cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:12px}}

    .roadmap-col{{background:#0b1220;border:1px solid #22304a;border-radius:12px;padding:10px}}

  </style>

</head>

<body>

  <h1>Brain Lab — Live Runtime</h1>

  <div class="ts">

    Auto-refresh cada 3s &nbsp;|&nbsp;

    <a href="/ui/live">Dashboard canónico</a> &nbsp;|&nbsp;

    <a href="/ui/api/autobuild-dashboard-v3-live" target="_blank">JSON live</a> &nbsp;|&nbsp;

    <a href="/ui/api/autobuild-dashboard-v3-canonical" target="_blank">JSON canónico</a>

  </div>



  <div class="grid">

    <div class="card hero">

      <div class="k">Estado canónico</div>

      <pre>phase={_esc(phase)}  stage={_esc(stage)}  done={_esc(str(done))}/{_esc(str(total))}

title={_esc(title)}

room_id={_esc(room_id)}

next_item={_esc(next_item)}

autonomy_mode={_esc(autonomy_mode)}</pre>

    </div>



    <div class="card">

      <div class="k">Nota operativa</div>

      <pre>{_esc(note)}</pre>

    </div>



    <div class="card full">

      <div class="k">Premisas canónicas</div>

      <div class="explain">Definición: {_esc(doctrine_definition or "n/a")}



Objetivo primario: {_esc(doctrine_objective or "n/a")}



Rol de la autonomía: {_esc(doctrine_autonomy or "n/a")}</div>

    </div>



    <div class="card">

      <div class="k">Utility U (proxy inicial)</div>

      <div class="explain">{_esc(utility_explain)}</div>

      <pre>{_esc(utility_text)}</pre>

    </div>



    <div class="card full">

      <div class="k">Control de seguimiento</div>

      <div class="explain">{_esc(progress_text)}

{_esc(stage_explain)}

{_esc(phase_explanation)}</div>

      <div class="bar"><span style="width:{_esc(str(progress_pct))}%"></span></div>

      <div class="track">

        <div class="metric"><div class="k">Etapa actual</div><div class="n">{_esc(phase)}</div><div class="mini">{_esc(stage)}</div></div>

        <div class="metric"><div class="k">Avance</div><div class="n">{_esc(str(progress_pct))}%</div><div class="mini">{_esc(str(done))} de {_esc(str(total))} cerradas</div></div>

        <div class="metric"><div class="k">Item activo</div><div class="n">{_esc(current_item_id)}</div><div class="mini">{_esc(current_item_title)}</div></div>

        <div class="metric"><div class="k">Intervienen</div><div class="n">5+1</div><div class="mini">OpenAI, Brain, reconciler, publisher, watchdog y usuario</div></div>

      </div>

    </div>



    <div class="card">

      <div class="k">Quiénes intervienen</div>

      <div class="explain">{_esc(actors_text)}</div>

    </div>



    <div class="card">

      <div class="k">Actividad reciente</div>

      <div class="badge {_esc(activity_badge)}">{_esc(activity_state)}</div>

      <div class="explain">Último evento útil: {_esc(latest_event_name)}

UTC: {_esc(latest_event_utc)}

Tiempo transcurrido: {_esc(latest_event_age)}

Detalle: {_esc(latest_event_note)}



{_esc(activity_explain + activity_note_extra)}</div>

    </div>



    <div class="card">

      <div class="k">Execution ledger</div>

      <div class="explain">Transparencia operator-runtime-worker del último carril gobernado visible. Esto muestra lo último que realmente existe en request/job/verification sin depender del relato conversacional.</div>

      <pre>{_esc(execution_trace_text)}</pre>

    </div>



    <div class="card full">

      <div class="k">Actividad por instancia</div>

      <div class="explain">Se registra lo más reciente realizado por cada actor operativo visible en bitácora. Esto permite ver quién actuó, en qué fase/room y con qué detalle, sin depender de leer NDJSON a mano.</div>

      <pre>{_esc(_fmt_instance_activity(instance_activity))}</pre>

    </div>



    <div class="card full">

      <div class="k">Etapas del roadmap</div>

      <div class="explain">Se muestran todas las etapas del roadmap activo separadas por estado. Esto permite ver qué ya fue cumplido, qué está en ejecución y qué aún no ha comenzado.</div>

      <div class="roadmap-cols">

        <div class="roadmap-col"><div class="k">Cumplidas ({_esc(str(len(done_items)))})</div><div class="explain">{_esc(_fmt_stage_list(done_items))}</div></div>

        <div class="roadmap-col"><div class="k">En progreso ({_esc(str(len(active_items)))})</div><div class="explain">{_esc(_fmt_stage_list(active_items))}</div></div>

        <div class="roadmap-col"><div class="k">Pendientes ({_esc(str(len(pending_items)))})</div><div class="explain">{_esc(_fmt_stage_list(pending_items))}</div></div>

        <div class="roadmap-col"><div class="k">Bloqueadas ({_esc(str(len(blocked_items)))})</div><div class="explain">{_esc(_fmt_stage_list(blocked_items))}</div></div>

      </div>

    </div>



    <div class="card">

      <div class="k">next_level_cycle_status_latest.json</div>

      <pre>{_esc(status_raw)}</pre>

    </div>



    <div class="card full">

      <div class="k">{_esc(bitacora_label)}</div>

      <div class="explain">{_esc(bitacora_note)}</div>

      <pre>{_esc(bitacora)}</pre>

    </div>



    <div class="card">

      <div class="k">{_esc(loop_label)}</div>

      <pre>{_esc(loop_summary)}</pre>

    </div>



    <div class="card">

      <div class="k">Loop STDOUT (tail)</div>

      <pre>{_esc(loop_stdout)}</pre>

    </div>



    <div class="card">

      <div class="k">Loop STDERR (tail)</div>

      <pre>{_esc(loop_stderr)}</pre>

    </div>



    <div class="card full">

      <div class="k">Brain 8010 STDERR (tail persistido)</div>

      <div class="badge {_esc(brain_stderr_badge)}">{_esc('Histórico' if brain_stderr_status == 'historical' else ('Reciente' if brain_stderr_status == 'recent' else 'Sin fuente'))}</div>

      <div class="mini">Fuente: {_esc(brain_stderr_path or 'n/a')} | mtime: {_esc(brain_stderr_mtime)} | antigüedad: {_esc(brain_stderr_age_text)}</div>

      <div class="explain">{_esc(brain_stderr_note)}</div>

      <pre>{_esc(brain_stderr)}</pre>

    </div>

  </div>

</body>

</html>"""

    from fastapi.responses import HTMLResponse as _BLHtmlResp

    return _BLHtmlResp(html)



def _bl_dash_html():

    return """

<!doctype html>

<html lang="es">

<head>

  <meta charset="utf-8" />

  <title>Brain Lab - Autobuild Dashboard V3</title>

  <meta name="viewport" content="width=device-width, initial-scale=1" />

  <style>

    :root{

      --bg:#0b1020; --panel:#121a30; --panel2:#0f1730; --text:#e9eefc; --muted:#9fb0d6;

      --ok:#1f9d55; --warn:#d7a100; --bad:#c53b3b; --line:#223055; --accent:#63a4ff;

    }

    *{box-sizing:border-box}

    body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--text)}

    .wrap{max-width:1400px;margin:0 auto;padding:18px}

    h1{margin:0 0 6px 0;font-size:28px}

    .sub{color:var(--muted);margin-bottom:18px}

    .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}

    .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px}

    .wide{grid-column:span 2}

    .full{grid-column:1/-1}

    .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}

    .v{font-size:24px;font-weight:700;margin-top:6px}

    .mini{font-size:13px;color:var(--muted);margin-top:8px;white-space:pre-wrap}

    .pill{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}

    .ok{background:rgba(31,157,85,.18);color:#7be0a0}

    .warn{background:rgba(215,161,0,.18);color:#ffd76a}

    .bad{background:rgba(197,59,59,.18);color:#ff8e8e}

    table{width:100%;border-collapse:collapse;margin-top:10px}

    th,td{border-bottom:1px solid var(--line);padding:10px 8px;text-align:left;font-size:13px;vertical-align:top}

    th{color:var(--muted);font-weight:600}

    .code{font-family:Consolas,monospace;font-size:12px}

    .topline{display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}

    .actions a{color:var(--accent);text-decoration:none;margin-left:12px}

    .mono{font-family:Consolas,monospace}

    @media (max-width:1100px){ .grid{grid-template-columns:repeat(2,minmax(0,1fr));} .wide{grid-column:span 2;} }

    @media (max-width:720px){ .grid{grid-template-columns:1fr;} .wide,.full{grid-column:span 1;} }

  </style>

</head>

<body>

<div class="wrap">

  <div class="topline">

    <div>

      <h1>Brain Lab — Autobuild Dashboard V3</h1>

      <div class="sub">Roadmap canónico único + bitácora viva. Refresca cada 10 segundos.</div>

    </div>

    <div class="actions">

      <a href="http://127.0.0.1:8040/" target="_blank">Abrir Chat UI</a>

      <a href="/ui/api/autobuild-dashboard-v3-canonical" target="_blank">Ver JSON canónico</a>

    </div>

  </div>



  <div class="grid">

    <div class="card">

      <div class="k">Estado global</div>

      <div class="v"><span id="estadoPill" class="pill ok">green</span></div>

      <div class="mini" id="activeRoadmap"></div>

    </div>

    <div class="card">

      <div class="k">Trust Score</div>

      <div class="v" id="trustScore">82</div>

      <div class="mini" id="trustLabel"></div>

    </div>

    <div class="card">

      <div class="k">Fase actual</div>

      <div class="v" id="currentPhase">NL-01</div>

      <div class="mini" id="currentStage"></div>

    </div>

    <div class="card">

      <div class="k">Siguiente item</div>

      <div class="v" style="font-size:16px;line-height:1.35" id="nextItem"></div>

      <div class="mini" id="activeTitle"></div>

    </div>



    <div class="card wide">

      <div class="k">Misión operativa</div>

      <div class="mini" id="missionOperativa"></div>

    </div>

    <div class="card">

      <div class="k">runtime_ui_audit</div>

      <div class="v" style="font-size:18px" id="runtimeAudit"></div>

      <div class="mini">Fuente: runtime_ui_audit_latest.json</div>

    </div>

    <div class="card">

      <div class="k">historical_roadmap_reconciliation</div>

      <div class="v" style="font-size:18px" id="historicalRecon"></div>

      <div class="mini">Fuente: historical_roadmap_reconciliation.json</div>

    </div>



    <div class="card">

      <div class="k">Roadmap</div>

      <div class="v" id="roadmapDone"></div>

      <div class="mini" id="roadmapCounts"></div>

    </div>

    <div class="card">

      <div class="k">Router</div>

      <div class="v" style="font-size:18px" id="router"></div>

      <div class="mini" id="models"></div>

    </div>

    <div class="card">

      <div class="k">Bitácora</div>

      <div class="v" style="font-size:18px" id="bitacoraUtc"></div>

      <div class="mini">Evento más reciente del publisher canónico</div>

    </div>

    <div class="card">

      <div class="k">Weak claims</div>

      <div class="v" id="weakClaims">0</div>

      <div class="mini">Route lock y roadmap maestro activos</div>

    </div>



    <div class="card full">

      <div class="k">Roadmap activo</div>

      <div class="mini mono" id="roadmapMeta"></div>

      <table>

        <thead>

          <tr>

            <th>ID</th>

            <th>Título</th>

            <th>Status</th>

            <th>Priority</th>

            <th>Objective</th>

          </tr>

        </thead>

        <tbody id="roadmapBody"></tbody>

      </table>

    </div>



    <div class="card full">

      <div class="k">Route lock</div>

      <pre class="mini mono" id="routeLockBox"></pre>

    </div>



    <div class="card full" id="liveRealtimeGrid">

      <div class="k">Tiempo real del runtime</div>

      <div class="grid" style="margin-top:12px">

        <div class="card wide">

          <div class="k">Eventos brain_requests.ndjson</div>

          <pre class="mini mono" id="liveBrainRequestsBox"></pre>

        </div>

        <div class="card wide">

          <div class="k">Bitácora viva</div>

          <pre class="mini mono" id="liveBitacoraBox"></pre>

        </div>

        <div class="card">

          <div class="k">Loop runtime</div>

          <pre class="mini mono" id="liveLoopSummaryBox"></pre>

        </div>

        <div class="card">

          <div class="k">Subruntime NL-06</div>

          <pre class="mini mono" id="liveRuntimeBox"></pre>

        </div>

        <div class="card wide">

          <div class="k">Loop STDOUT</div>

          <pre class="mini mono" id="liveLoopStdoutBox"></pre>

        </div>

        <div class="card wide">

          <div class="k">Loop STDERR</div>

          <pre class="mini mono" id="liveLoopStderrBox"></pre>

        </div>

        <div class="card wide">

          <div class="k">Brain 8010 STDERR</div>

          <pre class="mini mono" id="liveBrainStderrBox"></pre>

        </div>

        <div class="card wide">

          <div class="k">Propuestas recientes</div>

          <pre class="mini mono" id="liveProposalsBox"></pre>

        </div>

        <div class="card full">

          <div class="k">Artifacts recientes</div>

          <pre class="mini mono" id="liveArtifactsBox"></pre>

        </div>

      </div>

    </div>



  </div>

</div>



<script>

function esc(x){

  return String(x ?? "")

    .replaceAll("&","&amp;")

    .replaceAll("<","&lt;")

    .replaceAll(">","&gt;");

}

function pillClass(v){

  v = String(v || "").toLowerCase();

  if (["green","ok","done","present","running","healthy"].includes(v)) return "pill ok";

  if (["warn","warning","in_progress","seeded"].includes(v)) return "pill warn";

  return "pill bad";

}

async function loadCanonical(){

  const r = await fetch("/ui/api/autobuild-dashboard-v3-canonical", {cache:"no-store"});

  return await r.json();

}

function render(data){

  document.getElementById("estadoPill").className = pillClass("green");

  document.getElementById("estadoPill").textContent = "green";



  document.getElementById("activeRoadmap").textContent =

    `active_roadmap=${data.active_roadmap}\nactive_program=${data.active_program}`;



  document.getElementById("trustScore").textContent = data.trust_score ?? 82;

  document.getElementById("trustLabel").textContent = data.trust_label ?? "";

  document.getElementById("weakClaims").textContent = data.weak_claims ?? 0;



  document.getElementById("currentPhase").textContent = data.current_phase ?? "";

  document.getElementById("currentStage").textContent = data.current_stage ?? "";

  document.getElementById("nextItem").textContent = data.next_item ?? "";

  document.getElementById("activeTitle").textContent = data.active_title ?? "";



  document.getElementById("missionOperativa").textContent = data.mission_operativa ?? "";

  document.getElementById("runtimeAudit").textContent = data.runtime_ui_audit ?? "";

  document.getElementById("historicalRecon").textContent = data.historical_roadmap_reconciliation ?? "";

  document.getElementById("router").textContent = data.router ?? "";

  document.getElementById("models").textContent = (data.local_models || []).join(", ") || "sin modelos";

  document.getElementById("bitacoraUtc").textContent = data.bitacora?.updated_utc || "n/a";



  const counts = data.counts || {};

  document.getElementById("roadmapDone").textContent = `${counts.done ?? 0}/${counts.total ?? 0}`;

  document.getElementById("roadmapCounts").textContent =

    `pending=${counts.pending ?? 0}  in_progress=${counts.in_progress ?? 0}  blocked=${counts.blocked ?? 0}`;



  document.getElementById("roadmapMeta").textContent =

    `roadmap=${data.active_roadmap}\nprogram=${data.active_program}\nphase=${data.current_phase}\nstage=${data.current_stage}\nnext=${data.next_item}`;



  const body = document.getElementById("roadmapBody");

  body.innerHTML = "";

  (data.items || []).forEach(it => {

    const tr = document.createElement("tr");

    tr.innerHTML = `

      <td class="code">${esc(it.id)}</td>

      <td>${esc(it.title)}</td>

      <td><span class="${pillClass(it.status)}">${esc(it.status)}</span></td>

      <td>${esc(it.priority)}</td>

      <td>${esc(it.objective)}</td>

    `;

    body.appendChild(tr);

  });



  document.getElementById("routeLockBox").textContent = JSON.stringify(data.route_lock || {}, null, 2);



  const rtCard = document.getElementById("runtimeOverlayCard");

  const rtBody = document.getElementById("runtimeOverlayBody");

  if (rtCard && rtBody) {

    if ((data.current_phase || "") === "NL-06" && (data.runtime_phase || "")) {

      rtCard.style.display = "block";

      rtBody.innerHTML =

        "<div><b>Runtime phase:</b> " + esc(data.runtime_phase || "") + "</div>" +

        "<div><b>Runtime stage:</b> " + esc(data.runtime_stage || "") + "</div>" +

        "<div><b>Runtime title:</b> " + esc(data.runtime_title || "") + "</div>" +

        "<div><b>Progress:</b> " + esc(data.runtime_progress_label || "") + "</div>" +

        "<div><b>Counts:</b> done=" + esc(String(data.runtime_done ?? "")) + " / total=" + esc(String(data.runtime_total ?? "")) + "</div>" +

        "<div><b>Next runtime item:</b> " + esc(data.runtime_next_item || "") + "</div>";

    } else {

      rtCard.style.display = "none";

      rtBody.innerHTML = "";

    }

  }

}

async function refresh(){

  try {

    const data = await loadCanonical();

    render(data);

  

    try {

      const live = await loadLiveRealtime();

      renderLiveRealtime(live);

    } catch (liveErr) {}

} catch (e) {

    document.body.insertAdjacentHTML("beforeend",

      `<div style="position:fixed;bottom:12px;right:12px;background:#4b1f1f;color:#fff;padding:10px 12px;border-radius:8px;font:12px Consolas,monospace">dashboard error: ${esc(e.message || e)}</div>`);

  }

}

refresh();

setInterval(refresh, 3000);

setInterval(loadLiveRealtime, 3000);



</script>



<div class="section card" id="runtimeOverlayCard" style="display:none">

  <h2>Subruntime interno NL-06</h2>

  <div id="runtimeOverlayBody" class="small"></div>

</div>



<!-- BL_LIVE_PANEL_BOOT_V3_START -->

<script>

(function(){

  const LIVE_URL = "/ui/api/autobuild-dashboard-v3-live";

  const REFRESH_MS = 3000;



  function esc(x){

    return String(x ?? "")

      .replaceAll("&","&amp;")

      .replaceAll("<","&lt;")

      .replaceAll(">","&gt;");

  }



  function arrLines(v){

    if (!Array.isArray(v) || v.length === 0) return "(sin datos)";

    return v.map(x => String(x ?? "")).join("

");

  }



  function ensureLivePanel(){

    let host = document.getElementById("blLiveRealtimeHost");

    if (host) return host;



    const routeLock = document.getElementById("routeLockBox");

    let insertAfterCard = null;

    if (routeLock) {

      insertAfterCard = routeLock.closest(".card");

    }



    host = document.createElement("div");

    host.id = "blLiveRealtimeHost";

    host.className = "card full";

    host.innerHTML = `

      <div class="k">Tiempo real del runtime</div>

      <div class="mini" id="blLiveMeta">Cargando...</div>

      <div id="blLiveError" class="mini" style="display:none;color:#ff8e8e"></div>



      <div id="blLiveGrid"

           style="margin-top:12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px">

        <div class="card">

          <div class="k">Eventos brain_requests.ndjson</div>

          <pre id="blLiveBrainRequests" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Bitácora viva</div>

          <pre id="blLiveBitacora" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Loop runtime</div>

          <pre id="blLiveLoopSummary" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Subruntime NL-06</div>

          <pre id="blLiveRuntime" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Loop STDOUT</div>

          <pre id="blLiveLoopStdout" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Loop STDERR</div>

          <pre id="blLiveLoopStderr" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Brain 8010 STDERR</div>

          <pre id="blLiveBrainStderr" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card">

          <div class="k">Propuestas recientes</div>

          <pre id="blLiveProposals" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

        <div class="card full">

          <div class="k">Artifacts recientes</div>

          <pre id="blLiveArtifacts" class="mini mono" style="max-height:260px;overflow:auto"></pre>

        </div>

        <div class="card full">

          <div class="k">Fuentes live y rutas activas</div>

          <pre id="blLiveSources" class="mini mono" style="max-height:220px;overflow:auto"></pre>

        </div>

      </div>

    `;



    if (insertAfterCard && insertAfterCard.parentNode) {

      insertAfterCard.parentNode.insertBefore(host, insertAfterCard.nextSibling);

    } else {

      const grid = document.querySelector(".grid");

      if (grid) grid.appendChild(host);

      else document.body.appendChild(host);

    }



    return host;

  }



  function renderLive(data){

    ensureLivePanel();



    const err = document.getElementById("blLiveError");

    err.style.display = "none";

    err.textContent = "";



    const runtime = data.runtime || {};

    const stdout = data.stdout || {};

    const stderr = data.stderr || {};

    const latestLoop = data.latest_loop || {};



    const meta = [

      `generated_utc=${data.generated_utc || ""}`,

      `ok=${String(data.ok)}`,

      `runtime_phase=${runtime.runtime_phase || ""}`,

      `runtime_stage=${runtime.runtime_stage || ""}`,

      `runtime_title=${runtime.runtime_title || ""}`,

      `brain_requests=${Array.isArray(data.brain_requests_tail) ? data.brain_requests_tail.length : 0}`,

      `bitacora=${Array.isArray(data.bitacora_tail) ? data.bitacora_tail.length : 0}`,

      `proposals=${Array.isArray(data.recent_proposals) ? data.recent_proposals.length : 0}`,

      `artifacts=${Array.isArray(data.recent_artifacts) ? data.recent_artifacts.length : 0}`

    ].join(" | ");



    document.getElementById("blLiveMeta").textContent = meta;



    const runtimeText = [

      `Runtime phase: ${runtime.runtime_phase || ""}`,

      `Runtime stage: ${runtime.runtime_stage || ""}`,

      `Runtime title: ${runtime.runtime_title || ""}`,

      `Progress: ${runtime.runtime_progress_label || ""}`,

      `Counts: done=${runtime.runtime_done ?? ""} / total=${runtime.runtime_total ?? ""}`,

      `Next runtime item: ${runtime.runtime_next_item || ""}`

    ].join("

");



    const loopSummaryText = [

      `dir=${latestLoop.dir || ""}`,

      `summary_path=${latestLoop.summary_path || ""}`,

      `summary=${JSON.stringify(latestLoop.summary || {}, null, 2)}`

    ].join("

");



    const proposalsText = Array.isArray(data.recent_proposals) && data.recent_proposals.length

      ? data.recent_proposals.map((x,i) => `[${i+1}] ` + JSON.stringify(x, null, 2)).join("



")

      : "(sin propuestas recientes)";



    const artifactsText = Array.isArray(data.recent_artifacts) && data.recent_artifacts.length

      ? data.recent_artifacts.map((x,i) => `[${i+1}] ` + JSON.stringify(x, null, 2)).join("



")

      : "(sin artifacts recientes)";



    document.getElementById("blLiveBrainRequests").textContent = arrLines(data.brain_requests_tail);

    document.getElementById("blLiveBitacora").textContent = arrLines(data.bitacora_tail);

    document.getElementById("blLiveLoopSummary").textContent = loopSummaryText;

    document.getElementById("blLiveRuntime").textContent = runtimeText;

    document.getElementById("blLiveLoopStdout").textContent = arrLines(stdout.loop_tail);

    document.getElementById("blLiveLoopStderr").textContent = arrLines(stderr.loop_tail);

    document.getElementById("blLiveBrainStderr").textContent = arrLines(stderr.brain_tail);

    document.getElementById("blLiveProposals").textContent = proposalsText;

    document.getElementById("blLiveArtifacts").textContent = artifactsText;

    document.getElementById("blLiveSources").textContent = JSON.stringify(data.live_sources || {

      loop_stdout_path: stdout.loop_path || null,

      loop_stderr_path: stderr.loop_path || null,

      brain_stderr_path: stderr.brain_path || null

    }, null, 2);

  }



  async function refreshLive(){

    ensureLivePanel();

    try {

      const r = await fetch(LIVE_URL, {cache:"no-store"});

      const data = await r.json();

      renderLive(data);

    } catch (e) {

      ensureLivePanel();

      const err = document.getElementById("blLiveError");

      err.style.display = "block";

      err.textContent = "live panel error: " + String((e && e.message) || e);

    }

  }



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", function(){

      refreshLive();

      setInterval(refreshLive, REFRESH_MS);

    });

  } else {

    refreshLive();

    setInterval(refreshLive, REFRESH_MS);

  }

})();

</script>

<!-- BL_LIVE_PANEL_BOOT_V3_END -->



<script>

(function(){

  const MARK = "BL_LIVE_PANEL_BOOT_V5 BL_LIVE_PANEL_FIX_V2";

  if (window[MARK]) return;

  window[MARK] = true;



  function esc(x){ return String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }

  function arr(x){ return Array.isArray(x)?x:[]; }

  function fmt(x){ if(x==null)return''; if(typeof x==='string')return x; try{return JSON.stringify(x,null,2);}catch{return String(x);} }

  function card(title,content,wide){ return '<div class="card '+(wide?'wide':'')+' full"><div class="k">'+esc(title)+'</div><pre class="mini mono">'+esc(content)+'</pre></div>'; }

  function runtimeTxt(rt){ rt=rt||{}; const c=rt.runtime_counts||{}; return ['phase='+(rt.runtime_phase||''),'stage='+(rt.runtime_stage||''),'title='+(rt.runtime_title||''),'done='+(c.done??rt.runtime_done??0),'pending='+(c.pending??rt.runtime_pending??0),'in_progress='+(c.in_progress??rt.runtime_in_progress??0)].join('\n'); }

    const BL_LIVE_PANEL_FIX_V2 = true;

  function safeStr(x, maxLen) {

    try {

      let s = '';

      if (x === null || x === undefined) return '';

      if (typeof x === 'string') s = x;

      else if (Array.isArray(x)) s = x.map(i => typeof i === 'string' ? i : JSON.stringify(i)).join('\n');

      else s = JSON.stringify(x, null, 2);

      if (maxLen && s.length > maxLen) s = s.slice(0, maxLen) + '\n...(truncado)';

      return s;

    } catch(e) { return '[error: ' + String(e) + ']'; }

  }

  function setCard(id, content) {

    try {

      const el = document.getElementById(id);

      if (el) el.textContent = content || '(vacío)';

    } catch(e) {}

  }

  function renderLiveRealtime(d){

    try {

      const host = document.getElementById('liveRealtimeGrid');

      if (!host) return;

      const rt = d?.runtime || {};

      const stdout = d?.stdout || {};

      const stderr = d?.stderr || {};

      const c = rt.runtime_counts || {};



      // Build HTML with individual IDs for targeted updates

      host.innerHTML = [

        '<div class="card"><div class="k">Bitácora viva</div><pre class="mini mono" id="ll_bitacora">(cargando...)</pre></div>',

        '<div class="card"><div class="k">Loop runtime</div><pre class="mini mono" id="ll_runtime">(cargando...)</pre></div>',

        '<div class="card"><div class="k">Loop STDOUT</div><pre class="mini mono" id="ll_stdout">(cargando...)</pre></div>',

        '<div class="card"><div class="k">Loop STDERR</div><pre class="mini mono" id="ll_stderr">(cargando...)</pre></div>',

        '<div class="card"><div class="k">Brain 8010 STDERR</div><pre class="mini mono" id="ll_brain_stderr">(cargando...)</pre></div>',

        '<div class="card"><div class="k">Propuestas recientes</div><pre class="mini mono" id="ll_props">(cargando...)</pre></div>',

        '<div class="card wide full"><div class="k">Artifacts recientes</div><pre class="mini mono" id="ll_arts">(cargando...)</pre></div>',

        '<div class="card wide full"><div class="k">Fuentes live activas</div><pre class="mini mono" id="ll_sources">(cargando...)</pre></div>'

      ].join('');



      // Populate each card safely

      const bitTail = arr(d?.bitacora_tail);

      setCard('ll_bitacora', bitTail.length

        ? bitTail.slice(-8).map(line => {

            try { const o = JSON.parse(line); return '['+o.utc+'] '+o.event+(o.current_phase?' phase='+o.current_phase:''); }

            catch { return line; }

          }).join('\n')

        : 'sin eventos recientes');



      setCard('ll_runtime', [

        'phase=' + (rt.runtime_phase || rt.current_phase || ''),

        'stage=' + (rt.runtime_stage || rt.current_stage || ''),

        'title=' + (rt.runtime_title || rt.active_title || ''),

        'done=' + (c.done ?? rt.runtime_done ?? 0) + ' / total=' + (c.total ?? rt.runtime_total ?? 0),

        'in_progress=' + (c.in_progress ?? rt.runtime_in_progress ?? 0),

        'pending=' + (c.pending ?? rt.runtime_pending ?? 0),

        'next=' + (rt.runtime_next_item || '')

      ].join('\n'));



      setCard('ll_stdout',

        'path=' + (stdout.loop_path || '') + '\n\n' +

        safeStr(arr(stdout.loop_tail).slice(-10), 2000));



      setCard('ll_stderr',

        'path=' + (stderr.loop_path || '') + '\n\n' +

        safeStr(arr(stderr.loop_tail).slice(-10), 1000));



      setCard('ll_brain_stderr',

        'path=' + (stderr.brain_path || '') + '\n\n' +

        safeStr(arr(stderr.brain_tail).slice(-8), 1000));



      const props = arr(d?.recent_proposals);

      setCard('ll_props', props.length

        ? props.slice(0,5).map(p => {

            if (typeof p === 'string') return p;

            return (p.proposal_id||'') + ' ' + (p.tool_name||'') + '\n  room=' + (p.room_id||'');

          }).join('\n---\n')

        : 'sin propuestas recientes');



      const arts = arr(d?.recent_artifacts);

      setCard('ll_arts', arts.length

        ? arts.slice(0,8).map(a =>

            '[' + (a.room||'n/a') + '] ' + (a.name||'') + '\n' + (a.path||'') +

            (arr(a.tail).length ? '\n  ' + arr(a.tail).slice(-2).join('\n  ') : '')

          ).join('\n---\n')

        : 'sin artifacts recientes');



      const ls = d?.live_sources || {};

      setCard('ll_sources', [

        'loop_stdout: ' + (ls.loop_stdout_path || stdout.loop_path || ''),

        'loop_stderr: ' + (ls.loop_stderr_path || stderr.loop_path || ''),

        'brain_stderr: ' + (ls.brain_stderr_path || stderr.brain_path || ''),

        'bitacora: ' + (arr(ls.bitacora_candidates)[0] || '')

      ].join('\n'));



    } catch(outerErr) {

      try {

        const host = document.getElementById('liveRealtimeGrid');

        if (host) host.innerHTML = '<div class="card full"><div class="k">Error live panel</div><pre class="mini mono">' + String(outerErr) + '</pre></div>';

      } catch {}

    }

  }



  async function loadLiveRealtime(){

    try{

      const r=await fetch('/ui/api/autobuild-dashboard-v3-live',{cache:'no-store'});

      if(!r.ok)throw new Error('http '+r.status);

      renderLiveRealtime(await r.json());

    }catch(e){

      const host=document.getElementById('liveRealtimeGrid');

      if(host)host.innerHTML=card('Runtime error','error: '+(e?.message||e),true);

    }

  }

  function boot(){

    if(!document.getElementById('liveRealtimeGrid'))return;

    loadLiveRealtime();

    setInterval(loadLiveRealtime,10000);

  }

  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}

})();

</script>



</body>

</html>

"""



@app.middleware("http")

async def _bl_dashboard_v3_override_middleware(request, call_next):

    if request.url.path == "/ui/autobuild-dashboard-v3":

        return _bl_RedirectResponse(url="/ui/live", status_code=307)

    return await call_next(request)

# === BL_DASHBOARD_V3_OVERRIDE_END ===
