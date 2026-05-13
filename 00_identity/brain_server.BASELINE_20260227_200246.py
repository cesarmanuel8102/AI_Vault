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
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
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

@app.post("/v1/agent/risk/assess")
def agent_risk_assess(payload: dict, request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
    if snapshot is None:
        snapshot = payload  # permitir snapshot en raíz
    if not isinstance(snapshot, dict):
        return {"ok": False, "error": "SNAPSHOT_INVALID", "detail": "snapshot must be an object"}

    contract_path = str(payload.get("contract_path") or CONTRACT_DEFAULT_PATH) if isinstance(payload, dict) else CONTRACT_DEFAULT_PATH

    return risk_gate.persist_assess(
        room_id=str(room_id or "default"),
        contract_path=contract_path,
        snapshot=snapshot,
        risk_state_path=_risk_state_path(str(room_id or "default")),
    )






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
@app.post("/v1/agent/risk/reset_kill")
def agent_risk_reset_kill(payload: dict, request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    note = ""
    try:
        if isinstance(payload, dict):
            note = str(payload.get("note") or "").strip()
    except Exception:
        note = ""
    return risk_gate.reset_kill_switch(_risk_state_path(str(room_id or "default")), note=note)
# ===== /RISK_GATE_BLOCK_V1 =====
# --- Agent Loop (Planner→Executor→Evaluator) ---
from typing import Any, Dict as _Dict
from agent_loop import AgentLoop, ToolResult, AgentPaths
def _dispatch_tool(tool: str, args: dict) -> ToolResult:
    """
    Adaptador: conecta AgentLoop con tus tools reales.
    Ajusta aquí si tus funciones se llaman distinto.
    """
    try:
        if tool == "list_dir":
            out = list_dir(**args)
            return ToolResult(ok=True, output=out)
        if tool == "read_file":
            out = read_file(**args)
            return ToolResult(ok=True, output=out)
        if tool == "write_file":
            out = write_file(**args)
            return ToolResult(ok=True, output=out)
        if tool == "append_file":
            out = append_file(**args)
            return ToolResult(ok=True, output=out)
        return ToolResult(ok=False, error=f"UNKNOWN_TOOL: {tool}")
    except Exception as e:
        return ToolResult(ok=False, error=repr(e))
AVAILABLE_TOOLS = {
    "list_dir": True,
    "read_file": True,
    "write_file": True,
    "append_file": True
}


_AGENTS = {}  # room_id -> AgentLoop

def _norm_room_id(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return "default"
    v = "".join(ch for ch in v if ch.isalnum() or ch in ("-", "_"))[:64]
    return v or "default"

def _get_agent(request: Request) -> AgentLoop:
    rid = None
    try:
        rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id")
    except Exception:
        rid = None
    rid = _norm_room_id(rid)

    ag = _AGENTS.get(rid)
    if ag is None:
        ag = AgentLoop(paths=AgentPaths.default(room_id=rid))
        ag.dispatch_tool = _dispatch_tool
        _AGENTS[rid] = ag
    return ag





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
@app.post("/v1/agent/plan_legacy")
def agent_plan(payload: dict, request: Request):
    agent = _get_agent(request)
    goal = str(payload.get("goal") or "").strip()
    profile = str(payload.get("profile") or "default").strip()
    force_new = bool(payload.get("force_new", False))
    return agent.plan(goal=goal, profile=profile, force_new=force_new)





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
@app.post("/v1/agent/step_with_snapshot")
def step_with_snapshot(payload: StepWithSnapshotIn, request: Request):
    """One-shot: persiste runtime snapshot validado y ejecuta el mismo flujo que /v1/agent/step."""
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")

    # 1) Persistir snapshot (validado por Pydantic)
    snapshot_dict = payload.snapshot.model_dump()
    wr = _runtime_snapshot_write(rid, snapshot_dict)
    if not bool(wr.get("ok", False)):
        return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}

    # 2) Ejecutar MISMO flujo que /step (hard block -> preflight -> latch -> etc.)
    return agent_step(request)



@app.post("/v1/agent/snapshot/set")
def snapshot_set_alias(payload: RuntimeSnapshotIn, request: Request):
    """Alias de compatibilidad: escribe runtime snapshot en /v1/agent/runtime/snapshot/set."""
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")
    snapshot_dict = payload.model_dump()
    wr = _runtime_snapshot_write(rid, snapshot_dict)
    if not bool(wr.get("ok", False)):
        return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}
    return {"ok": True, "room_id": rid, "snapshot_path": wr.get("path")}


@app.post("/v1/agent/step")
def agent_step(request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")

    # 1) hard block if kill switch latched
    blocked = _risk_is_blocked(rid)
    if blocked:
        return blocked

    # 2) preflight assess using persisted runtime snapshot
    snapr = _runtime_snapshot_read(rid)
    if not bool(snapr.get("ok", False)):
        return {
            "ok": False,
            "error": str(snapr.get("error") or "SNAPSHOT_MISSING"),
            "detail": "Provide runtime snapshot via /v1/agent/runtime/snapshot/set",
            "room_id": rid,
            "snapshot_path": snapr.get("path")
        }

    snapshot = (snapr.get("snapshot") or {})
    contract_path = CONTRACT_DEFAULT_PATH

    # persist_assess will auto-latch kill switch if configured
    rg = risk_gate.persist_assess(
        room_id=rid,
        contract_path=contract_path,
        snapshot=snapshot,
        risk_state_path=_risk_state_path(rid)
    )

    assess = (rg.get("assess") or {}) if isinstance(rg, dict) else {}
    verdict = str(assess.get("verdict") or "")
    if verdict.lower() == "halt":
        return {
            "ok": False,
            "error": "RISK_HALT",
            "detail": "Risk Gate preflight blocked execution",
            "room_id": rid,
            "risk_gate": rg
        }

    # 3) execute one agent step
    return _get_agent(request).step()




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
@app.post("/v1/agent/eval")
def agent_eval(request: Request):
    return _get_agent(request).eval()






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
@app.get("/v1/agent/status")
def agent_status(request: Request):
# === STATUS ROOM BOOTSTRAP BEGIN ===
    # Room-aware bootstrap (robusto a nombres de params):
    # - Encuentra el Request buscando un objeto con .headers.get()
    # - Encuentra payload buscando dict con room_id o objeto con .room_id
    try:
        _req = None
        for _v in locals().values():
            try:
                if hasattr(_v, "headers") and hasattr(_v.headers, "get"):
                    _req = _v
                    break
            except Exception:
                pass

        _hdr_room = None
        try:
            if _req is not None:
                _hdr_room = _req.headers.get("x-room-id")
        except Exception:
            _hdr_room = None

        _payload_room = None
        for _v in locals().values():
            try:
                if isinstance(_v, dict) and "room_id" in _v:
                    _payload_room = _v.get("room_id")
                    break
                if hasattr(_v, "room_id"):
                    _payload_room = getattr(_v, "room_id", None)
                    if _payload_room:
                        break
            except Exception:
                pass

        room_id = _safe_room_id(_hdr_room or _payload_room or "default")
        _room_state_dir(room_id)

        # Seed inicial: copiar state/*.json global -> rooms/<room>/ si faltan
        base = _state_root_dir()
        src_m = os.path.join(base, "mission.json")
        src_p = os.path.join(base, "plan.json")
        src_s = os.path.join(base, "runtime_snapshot.json")
        dst = _room_paths(room_id)

        if os.path.exists(src_m) and (not os.path.exists(dst["mission"])):
            try: shutil.copyfile(src_m, dst["mission"])
            except Exception: pass
        if os.path.exists(src_p) and (not os.path.exists(dst["plan"])):
            try: shutil.copyfile(src_p, dst["plan"])
            except Exception: pass
        if os.path.exists(src_s) and (not os.path.exists(dst["snapshot"])):
            try: shutil.copyfile(src_s, dst["snapshot"])
            except Exception: pass

    except Exception:
        pass
# === STATUS ROOM BOOTSTRAP END ===
# === STATUS ROOMDIR PATCH BEGIN ===
    # Garantiza que exista el store por-room en disco
    try:
        # room_id efectivo: header x-room-id > payload.room_id > default
        # (si ya lo calculaste arriba, reutiliza la variable room_id)
        if 'room_id' in locals():
            _room_state_dir(room_id)
        else:
            room_id = _effective_room_id(request, None)
            _room_state_dir(room_id)
    except Exception:
        # No tumbar status por fallo de FS; pero dejamos rastro en logs si existen
        pass
# === STATUS ROOMDIR PATCH END ===
    # === STATUS ROOM-AWARE INJECT BEGIN ===
    # derive room_id from header x-room-id > payload.room_id > default
    try:
        _payload_room = None
        if isinstance(payload, dict):
            _payload_room = payload.get("room_id")
    except Exception:
        _payload_room = None
    room_id = _effective_room_id(request, _payload_room)
    # ensure room dirs exist + seed legacy if needed
    _seed_room_from_legacy_if_needed(room_id)
    _ = _room_paths(room_id)
    # === STATUS ROOM-AWARE INJECT END ===
    return _get_agent(request).status()






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
@app.post("/v1/agent/reset")
def agent_reset(request: Request):
    return _get_agent(request).reset()






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
@app.get("/v1/agent/capabilities")
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
@app.post("/v1/agent/risk/assess")
def agent_risk_assess(payload: dict, request: Request):
    # payload expects: snapshot {nlv,daily_pnl,weekly_drawdown,total_exposure}
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    snapshot = payload.get("snapshot") or payload  # allow sending snapshot at root
    if not isinstance(snapshot, dict):
        return {"ok": False, "error": "SNAPSHOT_INVALID", "detail": "snapshot must be an object"}
    contract_path = str(payload.get("contract_path") or CONTRACT_DEFAULT_PATH)
    rsp = risk_gate.persist_assess(
        room_id=(room_id or "default"),
        contract_path=contract_path,
        snapshot=snapshot,
        risk_state_path=_risk_state_path(room_id or "default")
    )
    return rsp







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
@app.post("/v1/agent/risk/reset_kill")
def agent_risk_reset_kill(payload: dict, request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    note = str((payload or {}).get("note") or "").strip() if isinstance(payload, dict) else ""
    return risk_gate.reset_kill_switch(_risk_state_path(room_id or "default"), note=note)

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
@app.get("/v1/agent/risk/status")
def agent_risk_status(request: Request):
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")
    st = _risk_read_state(rid)
    summary = _risk_summary(rid)
    return {"ok": True, "room_id": rid, "summary": summary, "risk_state": st}

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
@app.get("/healthz")
def healthz():
# === HEALTH ROOMDIR PATCH BEGIN ===
    # Forzar creación de store por-room (garantiza rooms/default) SIN depender de request
    try:
        _room_state_dir("default")
    except Exception:
        pass
# === HEALTH ROOMDIR PATCH END ===
    return {"ok": True, "name": APP_NAME, "version": APP_VERSION, "pid": os.getpid()}






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
@app.middleware("http")
async def add_timing_and_room(request: Request, call_next):
    t0 = time.time()
    room_id = request.headers.get("x-room-id", "default")
    try:
        response = await call_next(request)
    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e), "room_id": room_id, "latency_ms": dt_ms})
    dt_ms = int((time.time() - t0) * 1000)
    response.headers["x-latency-ms"] = str(dt_ms)
    response.headers["x-room-id"] = room_id
    return response















# ===== Brain Lab Agent Endpoints (v4) =====
import os
import sys
from typing import Any, Dict, Optional

from fastapi import Body, HTTPException
from pydantic import BaseModel, Field

TMP_AGENT_ROOT = os.environ.get("BRAIN_TMP_AGENT_ROOT", r"C:\AI_VAULT\tmp_agent")
if TMP_AGENT_ROOT not in sys.path:
    sys.path.insert(0, TMP_AGENT_ROOT)

from agent_state import AgentStateStore  # noqa: E402

agent_store = AgentStateStore(root=TMP_AGENT_ROOT)


class AgentPlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    room_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AgentPlanResponse(BaseModel):
    ok: bool
    mission: Dict[str, Any]
    plan: Dict[str, Any]


class AgentEvalRequest(BaseModel):
    observation: Dict[str, Any] = Field(default_factory=dict)
    room_id: Optional[str] = None


class AgentEvalResponse(BaseModel):
    ok: bool
    plan: Dict[str, Any]
    verdict: Dict[str, Any]



@app.get("/v1/agent/plan")
def agent_plan_get(request: Request):
    # Room-aware: usa EXACTAMENTE el mismo flujo que POST /v1/agent/status (tipado)
    rid = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    try:
        req = AgentStatusRequest(room_id=(rid or "default"))
        st = agent_status(req, request)  # llama a la función del endpoint tipado
        plan = (st or {}).get("plan") if isinstance(st, dict) else None
        return {"ok": True, "room_id": (rid or "default"), "plan": plan or {}}
    except Exception as e:
        return {"ok": False, "error": "PLAN_GET_FAILED", "detail": repr(e), "room_id": (rid or "default")}




    # Prefer per-room store (coherent with /v1/agent/execute at the bottom of this file)
    try:
        store = agent_state.AgentStateStore(_resolve_tmp_agent_root())
        plan = store.load_plan(room_id)
        return {"ok": True, "plan": _safe_json(plan)}
    except Exception as e1:
        # Fallback: classic single-file plan
        try:
            p = Path(_room_paths(room_id)["plan"])
            if p.exists():
                import json
                plan = json.loads(p.read_text(encoding="utf-8"))
                return {"ok": True, "plan": _safe_json(plan), "_fallback": "state/plan.json"}
            return {"ok": True, "plan": {}, "_fallback": "empty", "_detail": repr(e1)}
        except Exception as e2:
            return {"ok": False, "error": "PLAN_GET_FAILED", "detail": repr(e1), "detail2": repr(e2), "room_id": room_id}


@app.post("/v1/agent/plan", response_model=AgentPlanResponse)
def agent_plan(req: AgentPlanRequest, request: Request):
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
        plan["steps"] = [
            {
                "id": "S1",
                "title": "Write mission_log.txt (append_file) — gated",
                "status": "todo",
                "tool_name": "append_file",
                "mode": "propose",
                "kind": "new_file",
                "tool_args": {
                    "path": f"C:\AI_VAULT\tmp_agent\runs\{room_id}\mission_log.txt",
                    "content": "MISSION START\n"
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
                    "value": {"ts":"", "goal":"", "room_id":""}
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
        agent_store.save_plan(plan)

    # Always append history
    # Derive room_id for history (prefer req.room_id, fallback x-room-id header)
    rid = None
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

    mission2, plan2 = agent_store.load()
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
    return {"ok": True, "mission": mission2, "plan": plan2}
    # ===== End Planner executable steps (v4.4) =====

@app.post("/v1/agent/evaluate", response_model=AgentEvalResponse)
def agent_evaluate(req: AgentEvalRequest):
    _, plan = agent_store.load()

    obs_ok = bool((req.observation or {}).get("ok", False))
    verdict = {"status": "no_change", "notes": []}

    steps = plan.get("steps", []) or []
    for s in steps:
        if s.get("id") == "S2" and s.get("status") == "in_progress" and obs_ok:
            s["status"] = "done"
            plan["status"] = "ready_for_next_step"
            verdict["status"] = "progress"
            verdict["notes"].append("Marked S2 done because observation.ok=true")

    plan["steps"] = steps
    plan["last_eval"] = {"room_id": req.room_id, "observation": req.observation}

    # ===== Plan auto-complete on evaluate (v4.3) =====
    try:
        _steps = plan.get("steps", []) or []
        if _steps and all((x.get("status") == "done") for x in _steps):
            plan["status"] = "complete"
            verdict["status"] = "complete"
            verdict["notes"].append("All steps done -> plan complete")
    except Exception:
        pass
    # ===== End plan auto-complete =====

    agent_store.save_plan(plan)

    agent_store.append_history({
        "kind": "evaluate",
        "room_id": req.room_id,
        "observation": req.observation,
        "verdict": verdict
    })

    plan2 = _load_room_plan(room_id)
    return {"ok": True, "plan": plan2, "verdict": verdict}
class AgentExecuteRequest(BaseModel):
    room_id: Optional[str] = None
    step_id: Optional[str] = None

    # tool interface
    tool_name: str = Field(..., min_length=1)
    tool_args: Dict[str, Any] = Field(default_factory=dict)

    # write gating
    mode: str = Field("read", description="read|propose|apply")
    kind: Optional[str] = Field(None, description="new_file|modify (required for write/append)")
    repo_path: Optional[str] = Field(None, description="required if kind=modify (absolute path inside REPO_ROOT)")
    dest_dir: Optional[str] = Field(None, description="optional dest root dir inside REPO_ROOT (used for kind=new_file)")
    approve_token: Optional[str] = Field(None, description="required if mode=apply (APPLY_<proposal_id>)")
    proposal_id: Optional[str] = Field(None, description="optional existing proposal id to apply")

class AgentExecuteResponse(BaseModel):
    ok: bool
    room_id: Optional[str] = None
    step_id: Optional[str] = None
    tool_name: str
    result: Dict[str, Any]

@app.post("/v1/_debug/sanitize_id", response_model=AgentExecuteResponse)
def _sanitize_id(s: str) -> str:
    import re
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", s)
    return s or f"p{time.time_ns()}"

@app.post("/v1/agent/execute", response_model=AgentExecuteResponse)
def agent_execute(req: AgentExecuteRequest):
    """
    Filesystem-only execution.
    - list_dir/read_file: direct (safe-rooted by tools_fs)
    - write/append: staged into tmp_agent/workspace and applied via apply_gate (approval token required on apply)
    """
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None
    room_id = req.room_id or hdr_room or "default"
    tool_name = (req.tool_name or "").strip()
    tool_args = req.tool_args or {}
    allowed = {"list_dir", "read_file", "write_file", "append_file", "runtime_snapshot_set", "runtime_snapshot_get"}
    if tool_name not in allowed:
        # === GATE_ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1 BEGIN ===
        # Allow runtime snapshot tools (room-scoped KV) through the tool gate
        if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):
            pass
        else:
            raise HTTPException(status_code=400, detail=f"tool_name not allowed: {tool_name}")
        # === GATE_ALLOW_RUNTIME_SNAPSHOT_TOOLS_V1 END ===

    # tools_fs expects a single dict arg
    from tools_fs import tool_list_dir, tool_read_file, tool_write_file, tool_append_file

    # read-only
    if tool_name == "list_dir":
        out = tool_list_dir(tool_args)
        _autopersist_step_done_fs(room_id, req.step_id)
        return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

    if tool_name == "read_file":
        out = tool_read_file(tool_args)
        _autopersist_step_done_fs(room_id, req.step_id)
        return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

    # === AGENT_EXECUTE_RUNTIME_SNAPSHOT_DISPATCH_V1 BEGIN ===

    # Handle runtime_snapshot_set/get here to bypass FS write gating

    if tool_name in ("runtime_snapshot_set", "runtime_snapshot_get"):

        try:

            args = tool_args or {}

            snap_path = str(args.get("path") or "")

            if tool_name == "runtime_snapshot_set":

                val = args.get("value")

                # enrich minimal fields if dict

                try:

                    from datetime import datetime, timezone

                    now = datetime.now(timezone.utc).isoformat()

                except Exception:

                    now = ""

                if isinstance(val, dict):

                    vv = dict(val)

                    vv["ts"] = vv.get("ts") or now

                    vv["room_id"] = vv.get("room_id") or str(room_id)

                    # goal may live in plan; best-effort

                    try:

                        vv["goal"] = vv.get("goal") or str((agent_store.load_plan(room_id) or {}).get("goal") or "")

                    except Exception:

                        vv["goal"] = vv.get("goal") or ""

                    val = vv

                out = _runtime_snapshot_set_kv(str(room_id), snap_path, val)

            else:

                out = _runtime_snapshot_get_kv(str(room_id), snap_path)

            return {"ok": bool(out.get("ok", False)), "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

        except Exception as e:

            raise HTTPException(status_code=500, detail=f"runtime_snapshot failure: {e}")

    # === AGENT_EXECUTE_RUNTIME_SNAPSHOT_DISPATCH_V1 END ===

    # ===== Guardrail: block placeholder content (v4.6) =====
    # Prevent accidental placeholder commits into repo.
    try:
        _c = tool_args.get("content", None)
        _c_txt = _c if isinstance(_c, str) else (json.dumps(_c, ensure_ascii=False) if _c is not None else "")
        if tool_name in {"write_file", "append_file"} and isinstance(_c_txt, str) and ("PLANNER_PLACEHOLDER" in _c_txt):
            raise HTTPException(status_code=400, detail="GUARDRAIL_BLOCKED: content contains PLANNER_PLACEHOLDER")
    except HTTPException:
        raise
    except Exception:
        # if guard fails, do not block; conservative
        pass
    # ===== End guardrail v4.6 =====
    # write gated
    mode = (req.mode or "read").strip().lower()
    if mode not in {"propose", "apply"}:
        raise HTTPException(status_code=400, detail="WRITE_GATED: mode must be propose|apply for write/append")

    kind = (req.kind or "").strip()
    if kind not in {"new_file", "modify"}:
        raise HTTPException(status_code=400, detail="WRITE_GATED: kind must be new_file|modify")

    # Load gate constants from apply_gate
    from apply_gate import WORK_DIR, DEFAULT_DEST_DIR, apply_bundle

    # Ensure workspace staging path
    # tools_fs uses _get_path_arg(args) to find path; we accept "path" or "p"
    p = tool_args.get("path") or tool_args.get("p")
    if not p:
        raise HTTPException(status_code=400, detail="WRITE_GATED: tool_args must include path (or p)")

    ws_path = Path(p)

    # force staging under WORK_DIR (security + matches preflight)
    # If user gives absolute path outside WORK_DIR, we remap to WORK_DIR / name
    if ws_path.is_absolute():
        try:
            ws_path = ws_path.resolve()
            if Path(WORK_DIR) not in ws_path.parents and ws_path != Path(WORK_DIR):
                ws_path = (Path(WORK_DIR) / ws_path.name).resolve()
        except Exception:
            ws_path = (Path(WORK_DIR) / Path(p).name).resolve()
    else:
        ws_path = (Path(WORK_DIR) / ws_path).resolve()

    ws_path.parent.mkdir(parents=True, exist_ok=True)

    # For modify: if appending and file doesn't exist in workspace, seed it from repo_path (optional).
    if kind == "modify":
        if not req.repo_path:
            raise HTTPException(status_code=400, detail="WRITE_GATED: repo_path required for kind=modify")
        # we do NOT read repo here; apply_gate will validate repo_path is inside repo.
        # Optional seeding could be added later.

    # Execute staging write/append into workspace via tools_fs (safe_path will allow tmp_agent; we pass the remapped workspace path)
    tool_args2 = dict(tool_args)
    tool_args2["path"] = str(ws_path)

    if tool_name == "write_file":
        stage_res = tool_write_file(tool_args2)
    else:        # --- idempotency guard: new_file+append_file must start clean (prevents staging accumulation) ---
        try:
            if tool_name == "append_file" and kind == "new_file":
                try:
                    if ws_path.exists():
                        ws_path.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        # --- idempotency guard: avoid duplicating planner_exec_log.txt content ---
        try:
            _p2 = str(ws_path).replace("/", "\\").lower()
            if _p2.endswith("\\planner_exec_log.txt") or _p2.endswith("planner_exec_log.txt"):
                _txt = tool_args2.get("content") if isinstance(tool_args2, dict) else None
                if isinstance(_txt, str) and _txt:
                    if ws_path.exists():
                        _existing = ws_path.read_text(encoding="utf-8", errors="ignore")
                        if _txt in _existing:
                            stage_res = {"ok": True, "note": "idempotent: content already present", "path": str(ws_path)}
                        else:
                            stage_res = tool_append_file(tool_args2)
                    else:
                        stage_res = tool_append_file(tool_args2)
                else:
                    stage_res = tool_append_file(tool_args2)
            else:
                stage_res = tool_append_file(tool_args2)
        except Exception:
            stage_res = tool_append_file(tool_args2)# Build / persist bundle
    # PATCH: proposal_id uses time_ns to avoid same-second collisions (v4.7.2)
    proposal_id = _sanitize_id(req.proposal_id or f"p{time.time_ns()}")
    bundle = {
        "proposal_id": proposal_id,
        "items": []
    }

    item = {"kind": kind, "workspace_path": str(ws_path)}
    if kind == "modify":
        item["repo_path"] = str(Path(req.repo_path).resolve())
    bundle["items"].append(item)

    # Write bundle into tmp_agent/proposals
    sandbox_root = Path(r"C:\AI_VAULT\tmp_agent").resolve()
    proposals_dir = (sandbox_root / "proposals").resolve()
    proposals_dir.mkdir(parents=True, exist_ok=True)

    bundle_path = (proposals_dir / f"bundle_{proposal_id}.json").resolve()
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    required = f"APPLY_{proposal_id}"

    if mode == "propose":
        out = {
            "stage": stage_res,
            "proposal_id": proposal_id,
            "bundle_path": str(bundle_path),
            "required_approve": required,
            "next": "POST /v1/agent/execute with mode=apply and approve_token"
        }
        return {"ok": True, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}

    # mode == apply
    approve = req.approve_token
    if approve != required:
        raise HTTPException(status_code=400, detail=f"APPROVAL_REQUIRED: approve_token must be {required}")

    dest_dir = req.dest_dir or str(DEFAULT_DEST_DIR)

    apply_res = apply_bundle(str(bundle_path), dest_dir=dest_dir, approve_token=approve)

    out = {
        "stage": stage_res,
        "proposal_id": proposal_id,
        "bundle_path": str(bundle_path),
        "required_approve": required,
        "apply": apply_res
    }
    ok = bool(apply_res.get("ok"))
    return {"ok": ok, "room_id": room_id, "step_id": req.step_id, "tool_name": tool_name, "result": out}# ===== Agent Step Execute (v4.2) =====
class AgentExecuteStepRequest(BaseModel):
    room_id: Optional[str] = None
    step_id: str = Field(..., min_length=1)

    # gating override (optional; if absent uses step fields)
    mode: Optional[str] = None
    approve_token: Optional[str] = None

class AgentExecuteStepResponse(BaseModel):
    ok: bool
    room_id: str
    step_id: str
    tool_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    plan: Optional[Dict[str, Any]] = None

# ================================
# AGENT_EXECUTE_FS_ALIAS_V1
# Keep reference to FS/tool executor before later redefinitions of agent_execute.
# ================================
agent_execute_fs = agent_execute
@app.post("/v1/agent/execute_step", response_model=AgentExecuteStepResponse)
def agent_execute_step(req: AgentExecuteStepRequest):
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None
    room_id = req.room_id or hdr_room or "default"
    step_id = req.step_id

    # load current plan
    mission, plan = agent_store.load()
    steps = plan.get("steps", []) or []
    step = next((s for s in steps if str(s.get("id")) == str(step_id)), None)
    if not step:
        raise HTTPException(status_code=404, detail=f"STEP_NOT_FOUND:{step_id}")

    tool_name = step.get("tool_name")
    # === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 BEGIN ===
    # Handle runtime_snapshot_set/get as non-gated tools (room-scoped KV)
    if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):
        args = (step.get('tool_args') or {}) if isinstance(step, dict) else {}
        snap_path = str(args.get('path') or '')
        if tool_name == 'runtime_snapshot_set':
            val = args.get('value')
            # enrich minimal fields if dict
            try:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
            except Exception:
                now = ''
            if isinstance(val, dict):
                vv = dict(val)
                vv['ts'] = vv.get('ts') or now
                try:
                    vv['goal'] = vv.get('goal') or str((plan or {}).get('goal') or '')
                except Exception:
                    vv['goal'] = vv.get('goal') or ''
                vv['room_id'] = vv.get('room_id') or str(room_id)
                val = vv
            res2 = _runtime_snapshot_set_kv(str(room_id), snap_path, val)
            result = {'ok': True, 'tool_name': tool_name, 'result': res2, 'proposal_id': None}
        else:
            res2 = _runtime_snapshot_get_kv(str(room_id), snap_path)
            result = {'ok': bool(res2.get('ok', False)), 'tool_name': tool_name, 'result': res2, 'proposal_id': None}
        # continue (persist SOT will mark done)
    # === EXECUTE_STEP_SNAPSHOT_KV_DISPATCH_V1 END ===
    tool_args = step.get("tool_args") or {}
    if not tool_name:
        raise HTTPException(status_code=400, detail=f"STEP_HAS_NO_TOOL_CALL:{step_id}")

    # derive gating fields from step; allow request override
    mode = (req.mode or step.get("mode") or "propose").strip().lower()
    kind = (step.get("kind") or "new_file").strip()
    repo_path = step.get("repo_path")
    dest_dir = step.get("dest_dir")

    # Call existing execute logic by constructing a request object
    exec_req = AgentExecuteRequest(
        room_id=room_id,
        step_id=step_id,
        tool_name=str(tool_name),
                tool_args=dict(tool_args),
        mode=mode,
        kind=kind,
        repo_path=repo_path,
        dest_dir=dest_dir,
        approve_token=req.approve_token,
        # PATCH: execute_step unique proposal per write-step (v4.7.1)
        # - propose: force new proposal_id (avoid token reuse across steps)
        # - apply: reuse stored step proposal_id from prior propose
        proposal_id=(step.get("proposal_id") if mode == "apply" else None),
    )
    # execute
    # PATCH: step-bound approvals (v4.7.3)
    if mode == "apply":
        expected = step.get("required_approve")
        if expected and req.approve_token != expected:
            raise HTTPException(status_code=400, detail=f"APPROVAL_REQUIRED: approve_token must be {expected}")
    res = agent_execute_fs(exec_req)
    # Update step status + store proposal_id if present
    # PATCH: read-only steps become done on propose (v4.2.1)
    try:
        _tn = str(tool_name or "")
        _is_read = _tn in {"list_dir", "read_file"}
        if isinstance(res, dict) and res.get("ok"):
            if _is_read:
                # read-only tools do not require apply; propose is terminal
                step["status"] = "done"
            else:
                # write tools: propose->proposed, apply->done
                step["status"] = "done" if mode == "apply" else "proposed"
            pid = (res.get("result") or {}).get("proposal_id")
            if pid:
                    step["proposal_id"] = pid
                    ra = (res.get("result") or {}).get("required_approve")
                    if ra:
                        step["required_approve"] = ra
        else:
            step["status"] = "error"
    except Exception:
        step["status"] = "error"
    plan["steps"] = steps
    agent_store.save_plan(plan)

    # history
    agent_store.append_history({
        "kind": "execute_step",
        "room_id": room_id,
        "step_id": step_id,
        "tool_name": tool_name,
        "mode": mode,
    })

    plan2 = _load_room_plan(room_id)
    # === EXECUTE_STEP PERSIST PLAN (FIX) BEGIN ===
    # Single Source of Truth: persist per-room plan.json here (step-driven)
    try:
        room_id = None
        try:
            room_id = getattr(req, 'room_id', None)
        except Exception:
            room_id = None
        room_id = room_id or 'default'
    
        step_id_local = ''
        try:
            step_id_local = str(getattr(req, 'step_id', '') or '')
        except Exception:
            step_id_local = ''
    
        mode_local = ''
        try:
            mode_local = str(getattr(req, 'mode', '') or '')
        except Exception:
            mode_local = ''
    
        def _load_plan_disk(_rid: str) -> dict:
            try:
                _room_state_dir(_rid)
                _paths = _room_paths(_rid) or {}
                import json
                from pathlib import Path
                pp = _paths.get('plan')
                if pp and Path(pp).exists():
                    return json.loads(Path(pp).read_text(encoding='utf-8')) or {}
            except Exception:
                return {}
            return {}
    
        def _save_plan_disk(_rid: str, plan_disk: dict) -> None:
            try:
                _room_state_dir(_rid)
                _paths = _room_paths(_rid) or {}
                import json
                from pathlib import Path
                pp = _paths.get('plan')
                if pp:
                    Path(pp).write_text(json.dumps(plan_disk or {}, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
    
        def _touch(plan_disk: dict) -> None:
            try:
                from datetime import datetime, timezone
                plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
            except Exception:
                pass
            try:
                plan_disk.setdefault('room_id', room_id)
            except Exception:
                pass
    
    
        if room_id and step_id_local:
            plan_disk = _load_plan_disk(room_id) or {}
            steps_disk = plan_disk.get('steps', []) or []
            if isinstance(steps_disk, list):
                target = None
                for _s in steps_disk:
                    if isinstance(_s, dict) and str(_s.get('id')) == step_id_local:
                        target = _s
                        break
    
                tool_name_step = ''
                if isinstance(target, dict):
                    tool_name_step = str(target.get('tool_name') or '')
    
                is_read = tool_name_step in ('list_dir','read_file','runtime_snapshot_set','runtime_snapshot_get')
                is_write = tool_name_step in ('write_file','append_file')
    
                # read-only propose => done
                if target and is_read and mode_local == 'propose':
                    target['status'] = 'done'
    
                # write propose => proposed + proposal_id
                if target and is_write and mode_local == 'propose':

                    # extract proposal_id from execute_step result (scope-safe)
                    pid = ''
                    for _name in ('res','result','out','resp','response','payload','r'):
                        try:
                            _obj = locals().get(_name)
                        except Exception:
                            _obj = None
                        # IMPORTANT: locals() here is agent_execute_step scope (we are not inside a nested func)
                        if _obj is None:
                            try:
                                _obj = eval(_name)
                            except Exception:
                                _obj = None
                        if isinstance(_obj, dict):
                            _pid = _obj.get('proposal_id')
                            if _pid:
                                pid = str(_pid)
                                break
                            _inner = _obj.get('result')
                            if isinstance(_inner, dict) and _inner.get('proposal_id'):
                                pid = str(_inner.get('proposal_id'))
                                break
                    if pid:
                        target['status'] = 'proposed'
                        target['proposal_id'] = pid
                        target['required_approve'] = 'APPLY_' + pid
    
                # write apply => done + clear proposal fields
                if target and is_write and mode_local == 'apply':
                    target['status'] = 'done'
                    try:
                        target.pop('required_approve', None)
                        target.pop('proposal_id', None)
                    except Exception:
                        pass
    
                plan_disk['steps'] = steps_disk
    
                # auto-complete if all done
                try:
                    if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk if isinstance(x, dict)):
                        plan_disk['status'] = 'complete'
                except Exception:
                    pass
    
                _touch(plan_disk)
                _save_plan_disk(room_id, plan_disk)
    except Exception:
        pass
    # === EXECUTE_STEP PERSIST PLAN (FIX) END ===
    return {
        "ok": bool(res.get("ok")) if isinstance(res, dict) else False,
        "room_id": room_id,
        "step_id": step_id,
        "tool_name": str(tool_name),
        "result": res.get("result") if isinstance(res, dict) else None,
        "error": (res.get("error") if isinstance(res, dict) else "UNKNOWN"),
        "plan": plan2,
    }
# ===== End Agent Step Execute =====
# ===== Plan refresh (v4.5) =====
# PATCH: plan_refresh rewrite stable (v4.5.3)
class AgentPlanRefreshRequest(BaseModel):
    room_id: Optional[str] = None
    step_id: Optional[str] = None  # reserved

class AgentPlanRefreshResponse(BaseModel):
    ok: bool
    room_id: str
    updated: bool
    notes: list[str] = Field(default_factory=list)
    plan: Dict[str, Any]

@app.post("/v1/agent/plan_refresh", response_model=AgentPlanRefreshResponse)
def agent_plan_refresh(req: AgentPlanRefreshRequest):
    # Always define these to avoid scope errors
    from datetime import datetime, timezone
    # === PLAN_REFRESH ROOM-SAFE (FIX): room_id only from req (no Request in signature) ===
    room_id = req.room_id or "default"
    notes: list[str] = []
    updated = False

    # marker identity
    ts = datetime.now(timezone.utc).isoformat()
    marker_prefix = "# BRAINLAB_MARK "
    marker_line = f"{marker_prefix}{ts}"

    # === PLAN_REFRESH ROOM-SAFE (FIX): load per-room plan/mission from disk ===
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
        mission, plan = {}, {}
    plan = plan or {}
    plan.setdefault('room_id', room_id)
    steps = plan.get("steps", []) or []

    # Find S2/S3
    s2 = next((s for s in steps if str(s.get("id")) == "S2"), None)
    s3 = next((s for s in steps if str(s.get("id")) == "S3"), None)

    if not s2 or not s3:
        notes.append("Missing S2 or S3 in current plan")
        return {"ok": True, "room_id": room_id, "updated": False, "notes": notes, "plan": plan}

    # Determine repo path from S2 or S3
    s2_args = (s2.get("tool_args") or {})
    repo_path = s2_args.get("path") or s3.get("repo_path")

    if not repo_path:
        notes.append("No repo_path available from S2.tool_args.path or S3.repo_path")
        return {"ok": True, "room_id": room_id, "updated": False, "notes": notes, "plan": plan}

    # Read file from repo using tools_fs
    from tools_fs import tool_read_file
    try:
        rf = tool_read_file({"path": str(repo_path), "max_bytes": 600000})
        content = str(rf.get("content", "") or "")
        # === PLAN_REFRESH ROOM-SAFE (FIX): strip any PLANNER_PLACEHOLDER lines to avoid refresh loop ===
        try:
            _ls = content.splitlines(True)
            _ls = [ln for ln in _ls if 'PLANNER_PLACEHOLDER' not in ln]
            content = ''.join(_ls)
        except Exception:
            pass
    except Exception as e:
        notes.append(f"read_file failed: {e}")
        return {"ok": False, "room_id": room_id, "updated": False, "notes": notes, "plan": plan}

    # If S3 still has placeholder, we must replace it with real content
    s3_args = (s3.get("tool_args") or {})
    cur_s3_content = str(s3_args.get("content", "") or "")
    had_placeholder = ("PLANNER_PLACEHOLDER" in cur_s3_content)

    # Decide whether to append a new marker
    # If file already has at least one marker, avoid spamming: only append if last 30 lines lack marker prefix
    lines = content.splitlines()
    tail = lines[-30:] if len(lines) >= 30 else lines
    tail_has_marker = any((ln.startswith(marker_prefix)) for ln in tail)
    already_marked_somewhere = any((ln.startswith(marker_prefix)) for ln in lines)

    new_content = content
    if not new_content.endswith("\n"):
        new_content += "\n"

    if (not already_marked_somewhere) or (not tail_has_marker):
        new_content += marker_line + "\n"
        notes.append("Appended marker to content")
    else:
        notes.append("Marker already present recently; not appending a new one")

    # Update S3 tool_args
    # Ensure staging filename
    s3_args["path"] = s3_args.get("path") or "risk_engine.py"
    s3_args["content"] = new_content
    s3["tool_args"] = s3_args

    # Persist updated plan
    plan["steps"] = [s if str(s.get("id")) != "S3" else s3 for s in steps]
    # === PLAN_REFRESH ROOM-SAFE (FIX): persist updated plan to per-room disk store ===
    try:
        from datetime import datetime, timezone
        import json
        from pathlib import Path
        now = datetime.now(timezone.utc).isoformat()
        plan['updated_at'] = now
        plan.setdefault('room_id', room_id)
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        pp = paths.get('plan')
        if pp:
            Path(pp).write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    # === PLAN_REFRESH ROOM-SAFE (FIX): append history into plan (room-scoped) ===
    try:
        plan.setdefault('history', [])
        plan['history'].append({
            'kind': 'plan_refresh',
            'room_id': room_id,
            'repo_path': str(repo_path),
            'marker': marker_line,
            'had_placeholder': had_placeholder,
            'appended_marker': (not tail_has_marker) or (not already_marked_somewhere),
        })
    except Exception:
        pass

    plan2 = plan
    updated = True
    notes.append("S3.tool_args.content refreshed from repo (placeholder cleared if present)")

    return {"ok": True, "room_id": room_id, "updated": updated, "notes": notes, "plan": plan2}
# ===== End plan refresh =====

# ===== Agent run_once (v4.7) =====
class AgentRunOnceRequest(BaseModel):
    room_id: Optional[str] = None
    # Optional: if provided, run_once will try to APPLY a pending write step whose proposal_id matches token
    approve_token: Optional[str] = None

class AgentRunOnceResponse(BaseModel):
    ok: bool
    room_id: str
    action: str
    step_id: Optional[str] = None
    needs_approval: bool = False
    approve_token: Optional[str] = None
    note: Optional[str] = None
    plan: Dict[str, Any]

def _is_read_tool(tool_name: str) -> bool:
    return str(tool_name or "") in {"list_dir", "read_file"}

def _is_write_tool(tool_name: str) -> bool:
    return str(tool_name or "") in {"write_file", "append_file"}

def _has_placeholder(step: Dict[str, Any]) -> bool:
    try:
        args = (step.get("tool_args") or {})
        content = str(args.get("content", "") or "")
        return ('PLANNER_PLACEHOLDER' in content) or (content.strip() == '')
    except Exception:
        return False

@app.post("/v1/agent/run_once", response_model=AgentRunOnceResponse)
def agent_run_once(req: AgentRunOnceRequest, request: Request):
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None
    room_id = req.room_id or hdr_room or "default"
    # === RUN_ONCE RELOAD ROOM PLAN (FIX) BEGIN ===
    def _load_room_plan(_rid: str) -> dict:
        try:
            _room_state_dir(_rid)
            _paths = _room_paths(_rid) or {}
            import json
            from pathlib import Path
            pp = _paths.get('plan')
            if pp and Path(pp).exists():
                return json.loads(Path(pp).read_text(encoding='utf-8')) or {}
        except Exception:
            return {}
        return {}
    # === RUN_ONCE RELOAD ROOM PLAN (FIX) END ===

    # === RUN_ONCE ROOM LOAD (FIX) BEGIN ===
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
        mission, plan = {}, {}
    # Fallback compat: if empty, try global store
    if not plan:
        try:
            mission, plan = agent_store.load()
        except Exception:
            mission, plan = {}, {}
    # === RUN_ONCE ROOM LOAD (FIX) END ===
    # Ensure plan carries room_id for auditing
    try:
        if isinstance(plan, dict):
            plan.setdefault('room_id', room_id)
    except Exception:
        pass
    status = str((plan or {}).get("status", "") or "").lower()
    steps = (plan or {}).get("steps", []) or []

    if status == "complete":
        return {"ok": True, "room_id": room_id, "action": "noop_complete", "plan": plan}

    # 0) If approve_token provided: try APPLY the corresponding proposed write step
    if req.approve_token:
        token = str(req.approve_token or "").strip()
        if not token.startswith("APPLY_"):
            raise HTTPException(status_code=400, detail="approve_token must be APPLY_<proposal_id>")

        target_pid = token.replace("APPLY_", "", 1)
        step_to_apply = next(
            (s for s in steps
             if str(s.get("status")) == "proposed"
             and _is_write_tool(s.get("tool_name"))
             and str(s.get("proposal_id") or "") == target_pid),
            None
        )

        if not step_to_apply:
            return {
                "ok": True,
                "room_id": room_id,
                "action": "noop_no_matching_proposed_step",
                "note": f"No proposed write step matches {token}",
                "plan": plan
            }

        step_id = str(step_to_apply.get("id"))
        res = agent_execute_step(AgentExecuteStepRequest(room_id=room_id, step_id=step_id, mode="apply", approve_token=token))
        if False:
                    # === RUN_ONCE PERSIST APPLY DONE (FIX) BEGIN ===
                    # Persist step status=done in per-room plan.json after apply
                    try:
                        plan_disk = _load_room_plan(room_id) or {}
                        steps_disk = plan_disk.get('steps', []) or []
                        for _s in steps_disk:
                            if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
                                _s['status'] = 'done'
                                # limpiar campos de propuesta
                                try:
                                    _s.pop('required_approve', None)
                                    _s.pop('proposal_id', None)
                                except Exception:
                                    pass
                                break
                        plan_disk['steps'] = steps_disk
                        # auto-complete si todos done
                        try:
                            if steps_disk and all((str(x.get('status'))=='done') for x in steps_disk):
                                plan_disk['status'] = 'complete'
                        except Exception:
                            pass
                        from datetime import datetime, timezone
                        plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
                        plan_disk.setdefault('room_id', room_id)
                        _room_state_dir(room_id)
                        _paths = _room_paths(room_id) or {}
                        import json
                        from pathlib import Path
                        pp = _paths.get('plan')
                        if pp:
                            Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
                    except Exception:
                        pass
                    # === RUN_ONCE PERSIST APPLY DONE (FIX) END ===
        _, plan2 = agent_store.load()
        return {"ok": True, "room_id": room_id, "action": "apply_step", "step_id": step_id, "plan": plan2}

    # 1) If any write step still has placeholder, refresh plan first (1 action per call)
    placeholder_step = next((s for s in steps if _is_write_tool(s.get("tool_name")) and _has_placeholder(s)), None)
    if placeholder_step:
        pr = agent_plan_refresh(AgentPlanRefreshRequest(room_id=room_id))
        _, plan2 = agent_store.load()
        return {
            "ok": bool(pr.get("ok", True)),
            "room_id": room_id,
            "action": "plan_refresh",
            "step_id": str(placeholder_step.get("id")),
            "note": "Refreshed S3 content to clear placeholder",
            "plan": plan2
        }

    # 2) Find next actionable step
    # Prefer todo; if none, then proposed read-only shouldn't exist (but handle anyway)
    next_step = next((s for s in steps if str(s.get("status")) in {"todo", "in_progress"}), None)
    if not next_step:
        # if nothing todo, do an evaluate to allow auto-complete logic
        try:
            ev = agent_evaluate(AgentEvalRequest(room_id=room_id, observation={"ok": True, "note": "run_once sweep"}))
            _, plan2 = agent_store.load()
            return {"ok": True, "room_id": room_id, "action": "evaluate_sweep", "plan": plan2}
        except Exception:
            _, plan2 = agent_store.load()
            return {"ok": True, "room_id": room_id, "action": "noop_no_todo", "plan": plan2}

    step_id = str(next_step.get("id"))
    tool_name = str(next_step.get("tool_name") or "")

    # Execute propose
    res = agent_execute_step(AgentExecuteStepRequest(room_id=room_id, step_id=step_id, mode="propose"))
    if False:
            # === RUN_ONCE MARK READ DONE (FIX) BEGIN ===
            # For read-only steps, persist status=done into per-room plan.json
            if _is_read_tool(tool_name):
                try:
                    plan_disk = _load_room_plan(room_id) or {}
                    steps_disk = plan_disk.get('steps', []) or []
                    for _s in steps_disk:
                        if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
                            _s['status'] = 'done'
                            break
                    plan_disk['steps'] = steps_disk
                    try:
                        from datetime import datetime, timezone
                        plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
                    except Exception:
                        pass
                    plan_disk.setdefault('room_id', room_id)
                    _room_state_dir(room_id)
                    _paths = _room_paths(room_id) or {}
                    import json
                    from pathlib import Path
                    pp = _paths.get('plan')
                    if pp:
                        Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
                    plan = plan_disk
                    steps = plan.get('steps', []) or []
                except Exception:
                    pass
            # === RUN_ONCE MARK READ DONE (FIX) END ===
    if False:
            # === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) BEGIN ===
            # Persist write-step proposal_id/required_approve into per-room plan.json so APPLY can match.
            if _is_write_tool(tool_name):
                try:
                    pid = None
                    try:
                        pid = (res.get('result') or {}).get('proposal_id')
                    except Exception:
                        pid = None
                    if pid:
                        plan_disk = _load_room_plan(room_id) or {}
                        steps_disk = plan_disk.get('steps', []) or []
                        for _s in steps_disk:
                            if isinstance(_s, dict) and str(_s.get('id')) == str(step_id):
                                _s['status'] = 'proposed'
                                _s['proposal_id'] = str(pid)
                                _s['required_approve'] = 'APPLY_' + str(pid)
                                break
                        plan_disk['steps'] = steps_disk
                        try:
                            from datetime import datetime, timezone
                            plan_disk['updated_at'] = datetime.now(timezone.utc).isoformat()
                        except Exception:
                            pass
                        plan_disk.setdefault('room_id', room_id)
                        _room_state_dir(room_id)
                        _paths = _room_paths(room_id) or {}
                        import json
                        from pathlib import Path
                        pp = _paths.get('plan')
                        if pp:
                            Path(pp).write_text(json.dumps(plan_disk, ensure_ascii=False, indent=2), encoding='utf-8')
                        plan = plan_disk
                        steps = plan.get('steps', []) or []
                except Exception:
                    pass
            # === RUN_ONCE PERSIST WRITE PROPOSAL (FIX) END ===

    # reload per-room plan after execute_step
    plan = _load_room_plan(room_id) or plan
    # If it's a write tool, we require approval token from result
    if _is_write_tool(tool_name):
        pid = None
        try:
            pid = (res.get("result") or {}).get("proposal_id")
        except Exception:
            pid = None
        approve = f"APPLY_{pid}" if pid else None

        _, plan2 = agent_store.load()
        return {
            "ok": True,
            "room_id": room_id,
            "action": "propose_write_step",
            "step_id": step_id,
            "needs_approval": True,
            "approve_token": approve,
            "note": "Write step proposed; re-call run_once with approve_token to apply",
            "plan": plan2
        }

    # read-only step is terminal; run evaluate to auto-complete if needed
    try:
        agent_evaluate(AgentEvalRequest(room_id=room_id, observation={"ok": True, "note": f"run_once after {step_id}"}))
    except Exception:
        pass

    plan2 = _load_room_plan(room_id)
    # === RUN_ONCE PERSIST AFTER LOAD (FIX) BEGIN ===
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        try:
            if isinstance(plan2, dict):
                plan2['updated_at'] = now
                plan2.setdefault('room_id', room_id)
        except Exception:
            pass
        try:
            if isinstance(mission, dict):
                mission['updated_at'] = now
                mission.setdefault('room_id', room_id)
        except Exception:
            pass
        pm = paths.get('mission')
        pp = paths.get('plan')
        if pm:
            Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
        if pp:
            Path(pp).write_text(json.dumps(plan2 or {}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    # === RUN_ONCE PERSIST AFTER LOAD (FIX) END ===
    # === RUN_ONCE ROOM PERSIST (FIX) BEGIN ===
    try:
        rid = None
        # prefer req.room_id si existe
        try:
            rid = getattr(req, 'room_id', None)
        except Exception:
            rid = None
        # fallback header x-room-id
        if not rid and 'request' in locals() and request is not None:
            try:
                rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')
            except Exception:
                rid = None
        if rid:
            # Tomar mission/plan actuales (si no existen, cargar del store)
            _mission = None
            _plan = None
            try:
                _mission = mission if 'mission' in locals() else None
            except Exception:
                _mission = None
            try:
                _plan = plan if 'plan' in locals() else None
            except Exception:
                _plan = None
            if _mission is None or _plan is None:
                try:
                    _mission, _plan = agent_store.load()
                except Exception:
                    pass
            from datetime import datetime, timezone
            import json
            now = datetime.now(timezone.utc).isoformat()
            if isinstance(_plan, dict):
                _plan['updated_at'] = now
                _plan.setdefault('room_id', rid)
            if isinstance(_mission, dict):
                _mission['updated_at'] = now
                _mission.setdefault('room_id', rid)
            _room_state_dir(rid)
            paths = _room_paths(rid) or {}
            pm = paths.get('mission')
            pp = paths.get('plan')
            from pathlib import Path
            if pm:
                Path(pm).write_text(json.dumps(_mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
            if pp:
                Path(pp).write_text(json.dumps(_plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    # === RUN_ONCE ROOM PERSIST (FIX) END ===
    # === RUN_ONCE ROOM PERSIST BEFORE RETURN (FIX) BEGIN ===
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        try:
            if isinstance(plan, dict):
                plan['updated_at'] = now
                plan.setdefault('room_id', room_id)
        except Exception:
            pass
        try:
            if isinstance(mission, dict):
                mission['updated_at'] = now
                mission.setdefault('room_id', room_id)
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
    # === RUN_ONCE ROOM PERSIST BEFORE RETURN (FIX) END ===
    return {"ok": True, "room_id": room_id, "action": "propose_read_step", "step_id": step_id, "plan": plan2}
# ===== End Agent run_once =====
# ===== Agent Status (v4.8) =====
class AgentStatusRequest(BaseModel):
    room_id: Optional[str] = None

class AgentStatusResponse(BaseModel):
    ok: bool
    room_id: str
    mission: Dict[str, Any]
    plan: Dict[str, Any]
    summary: Dict[str, Any]
    pending_approvals: Dict[str, str] = Field(default_factory=dict)

    # === AGENT_PLAN ROOM SAVE BEGIN ===
    # Persist plan/mission per-room (rooms/<room_id>/...)
    try:
        _room_state_dir(room_id)
        paths = _room_paths(room_id) or {}
        import json
        from pathlib import Path
        pm = paths.get('mission')
        pp = paths.get('plan')
        if pm:
            Path(pm).write_text(json.dumps(mission or {}, ensure_ascii=False, indent=2), encoding='utf-8')
        if pp:
            Path(pp).write_text(json.dumps(plan or {}, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    # === AGENT_PLAN ROOM SAVE END ===
@app.post("/v1/agent/status", response_model=AgentStatusResponse)
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


@app.post("/v1/agent/execute")
def agent_execute(payload: dict):
    """
    Ejecuta 1 paso del plan por request.
    Espera: { room_id, step_id? , max_tool_calls? }
    Devuelve: { ok, plan, executed, tool_results, next_step }
    """
    room_id = payload.get("room_id", "default")
    step_id = payload.get("step_id")  # opcional: si no, toma el siguiente pendiente
    max_tool_calls = int(payload.get("max_tool_calls", 3))

    # Importa AgentStateStore desde tmp_agent (ya está en sys.path[0])
    agent_state = _import_tmp_agent_module("agent_state")
    store = agent_state.AgentStateStore(_resolve_tmp_agent_root())
    plan = store.load_plan(room_id)

    # Selección de paso
    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    if not steps:
        return {"ok": False, "error": "Plan sin pasos. Llama /v1/agent/plan primero.", "plan": _safe_json(plan)}

    def is_done(s):
        return str(s.get("status","")).lower() in ("done","complete","completed","skipped")

    step = None
    if step_id is not None:
        for s in steps:
            if str(s.get("id")) == str(step_id):
                step = s
                break
        if step is None:
            return {"ok": False, "error": f"step_id no encontrado: {step_id}", "plan": _safe_json(plan)}
        if is_done(step):
            return {"ok": True, "note": "Paso ya completado", "executed": _safe_json(step), "plan": _safe_json(plan)}
    else:
        # primer paso no done
        for s in steps:
            if not is_done(s):
                step = s
                break
        if step is None:
            return {"ok": True, "note": "Plan ya completado", "plan": _safe_json(plan), "next_step": None}

    # Ejecutar usando sandbox_executor si existe
    # Contrato esperado: SandboxExecutor(root).run_step(step, room_id, max_tool_calls)
    tool_results = []
    executed = {"id": step.get("id"), "title": step.get("title"), "status_before": step.get("status","pending")}

    try:
        se = _import_tmp_agent_module("sandbox_executor")
    except Exception as e:
        # No abortamos: marcamos como bloqueado para que lo arreglemos con el nombre correcto
        step["status"] = "blocked"
        step["last_error"] = f"Import sandbox_executor failed: {e}"
        store.save_plan(room_id, plan)
        return {"ok": False, "error": "No se pudo importar sandbox_executor desde tmp_agent.", "detail": str(e), "plan": _safe_json(plan)}

    try:
        executor = se.SandboxExecutor(_resolve_tmp_agent_root())
        result = executor.run_step(step=step, room_id=room_id, max_tool_calls=max_tool_calls)
        # result puede contener: status, tool_results, notes, output
        tool_results = result.get("tool_results", []) if isinstance(result, dict) else []
        # Actualiza status en plan si el ejecutor no lo hizo
        if isinstance(result, dict) and result.get("status"):
            step["status"] = result["status"]
        else:
            step["status"] = step.get("status","done") if step.get("status") != "blocked" else "blocked"
        step["last_run"] = datetime.utcnow().isoformat() + "Z"
        step["last_output"] = result.get("output") if isinstance(result, dict) else str(result)
        store.save_plan(room_id, plan)
        executed["status_after"] = step.get("status")
        executed["output"] = step.get("last_output")
    except Exception as e:
        step["status"] = "blocked"
        step["last_error"] = str(e)
        step["last_run"] = datetime.utcnow().isoformat() + "Z"
        store.save_plan(room_id, plan)
        return {"ok": False, "error": "Ejecución falló", "detail": str(e), "executed": _safe_json(step), "plan": _safe_json(plan)}

    # Próximo paso
    next_step = None
    for s in steps:
        if not is_done(s):
            next_step = {"id": s.get("id"), "title": s.get("title"), "status": s.get("status","pending")}
            break


    return {
        "ok": True,
        "executed": _safe_json(executed),
        "tool_results": _safe_json(tool_results),
        "next_step": _safe_json(next_step),
        "plan": _safe_json(plan),
    }

# APP_INCLUDE_ROUTER_MOVED_V1: include router at EOF

@app.post("/v1/agent/run")
def agent_run(body: dict, request: Request):
    # v6.2: run loop MUST respect per-room plan.json and stop if complete
    try:
        hdr_room = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or None
    except Exception:
        hdr_room = None

    # Resolve request model without assuming parameter name (req/payload/body/etc.)
    _req = None
    try:
        _req = req  # type: ignore[name-defined]
    except Exception:
        _req = None
    if _req is None:
        for _k in ("payload","body","data","r","request_body","model"):
            try:
                if _k in locals() and locals().get(_k) is not None:
                    _req = locals().get(_k)
                    break
            except Exception:
                pass

    room_id = getattr(_req, "room_id", None) or hdr_room or "default"
    max_steps = int(getattr(_req, "max_steps", 10) or 10)
    if max_steps < 1: max_steps = 1
    if max_steps > 200: max_steps = 200

    # Always read per-room status first (via agent_status which loads from disk)
    st0 = agent_status(AgentStatusRequest(room_id=room_id), request)
    plan0 = (st0.get('plan') or {})
    mission0 = (st0.get('mission') or {})
    summary0 = (st0.get('summary') or {})
    pending0 = (st0.get('pending_approvals') or {})

    if str(plan0.get('status','')).lower() == 'complete':
        return {
            'ok': True,
            'room_id': room_id,
            'executed': [],
            'needs_approval': False,
            'approve_token': None,
            'summary': summary0,
            'pending_approvals': pending0,
            'plan': plan0,
            'mission': mission0,
        }

    executed = []
    needs_approval = False
    approve_token = None

    for _i in range(max_steps):
        r = agent_run_once(AgentRunOnceRequest(room_id=room_id), request)
        executed.append({'action': r.get('action'), 'step_id': r.get('step_id')})
        if bool(r.get('needs_approval', False)):
            needs_approval = True
            approve_token = r.get('approve_token')
            break
        if str(r.get('action') or '') == 'noop_complete':
            break
        if str(r.get('action') or '') in ('noop_no_todo','evaluate_sweep'):
            break

    # Recompute status from disk at end
    st = agent_status(AgentStatusRequest(room_id=room_id), request)
    return {
        'ok': True,
        'room_id': room_id,
        'executed': executed,
        'needs_approval': needs_approval,
        'approve_token': approve_token,
        'summary': st.get('summary') or {},
        'pending_approvals': st.get('pending_approvals') or {},
        'plan': st.get('plan') or {},
        'mission': st.get('mission') or {},
    }
