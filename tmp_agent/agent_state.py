import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing state file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

@dataclass
class AgentStatePaths:
    root: str

    @property
    def state_dir(self) -> str:
        return os.path.join(self.root, "state")

    @property
    def mission_path(self) -> str:
        return os.path.join(self.state_dir, "mission.json")

    @property
    def plan_path(self) -> str:
        return os.path.join(self.state_dir, "plan.json")

class AgentStateStore:
    def __init__(self, root: str):
        self.paths = AgentStatePaths(root=root)

    def ensure(self) -> None:
        os.makedirs(self.paths.state_dir, exist_ok=True)
        # No auto-create files here: explicit creation is safer and more visible.

    def load(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        self.ensure()
        mission = _safe_read_json(self.paths.mission_path)
        plan = _safe_read_json(self.paths.plan_path)
        return mission, plan

    def save_mission(self, mission: Dict[str, Any]) -> None:
        self.ensure()
        mission = dict(mission)
        mission["updated_at"] = _now_iso()
        if not mission.get("created_at"):
            mission["created_at"] = mission["updated_at"]
        _atomic_write_json(self.paths.mission_path, mission)

    def save_plan(self, plan: Dict[str, Any]) -> None:
        self.ensure()
        plan = dict(plan)
        plan["updated_at"] = _now_iso()
        if not plan.get("created_at"):
            plan["created_at"] = plan["updated_at"]
        _atomic_write_json(self.paths.plan_path, plan)

    def append_history(self, entry: Dict[str, Any], cap: int = 200) -> Dict[str, Any]:
        mission, plan = self.load()
        hist = plan.get("history", [])
        hist.append(entry)
        if len(hist) > cap:
            hist = hist[-cap:]
        plan["history"] = hist
        self.save_plan(plan)
        return plan

# ===== Legacy compatibility layer (Brain Lab v4) =====
# brain_router.py historically imports helpers from agent_state.
# We keep minimal safe compatibility here to avoid import failures.

def get_room_id(headers_or_request=None, default: str = "default") -> str:
    """
    Extract room id from:
    - dict-like headers: {'x-room-id': '...'}
    - FastAPI Request-like: obj.headers
    - fallback: env BRAIN_ROOM_ID
    """
    # env fallback
    rid = os.environ.get("BRAIN_ROOM_ID") or None

    def _try_get(d):
        try:
            # case-insensitive lookup
            for k in ("x-room-id", "X-Room-Id", "X-ROOM-ID", "x_room_id", "room_id", "Room-Id"):
                if hasattr(d, "get"):
                    v = d.get(k)
                    if v:
                        return str(v)
        except Exception:
            pass
        return None

    if headers_or_request is not None:
        # direct dict-like
        v = _try_get(headers_or_request)
        if v:
            rid = v
        else:
            # request-like with .headers
            try:
                h = getattr(headers_or_request, "headers", None)
                if h is not None:
                    v2 = _try_get(h)
                    if v2:
                        rid = v2
            except Exception:
                pass

    rid = (rid or default).strip()
    return rid if rid else default


# Generic shim: if legacy code imports a symbol that doesn't exist yet,
# allow import to succeed. If called, raise a clear error.
__LEGACY_MISSING = {}

def __getattr__(name: str):
    if name in __LEGACY_MISSING:
        return __LEGACY_MISSING[name]

    def _missing(*args, **kwargs):
        raise RuntimeError(
            f"agent_state.{name} is not implemented in tmp_agent\\agent_state.py. "
            f"Legacy brain_router imported it. Either port this helper into tmp_agent "
            f"or update brain_router imports."
        )

    __LEGACY_MISSING[name] = _missing
    return _missing
# ===== End legacy compatibility layer =====



# ===== Room dirs helpers (Brain Lab v4) =====
import re
from typing import Mapping

@dataclass
class RoomPaths:
    room_id: str
    vault_root: str
    rooms_root: str
    room_root: str
    memory_dir: str
    state_dir: str
    logs_dir: str
    artifacts_dir: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "room_id": self.room_id,
            "vault_root": self.vault_root,
            "rooms_root": self.rooms_root,
            "room_root": self.room_root,
            "memory_dir": self.memory_dir,
            "state_dir": self.state_dir,
            "logs_dir": self.logs_dir,
            "artifacts_dir": self.artifacts_dir,
        }

    def __getitem__(self, key: str) -> str:
        return self.as_dict()[key]

    def get(self, key: str, default=None):
        return self.as_dict().get(key, default)

    def __fspath__(self) -> str:
        return self.room_root

    def __str__(self) -> str:
        return self.room_root


def _sanitize_room_id(room_id: str, default: str = "default") -> str:
    room_id = (room_id or "").strip()
    if not room_id:
        return default
    room_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", room_id)
    return room_id or default


def ensure_room_dirs(headers_or_room_id=None, default: str = "default", vault_root: Optional[str] = None) -> RoomPaths:
    """
    Ensure per-room directory structure exists. Accepts:
      - room_id: str
      - dict-like headers / Request-like object (uses get_room_id)
    Returns RoomPaths (acts like dict + path-like).
    """
    if isinstance(headers_or_room_id, str):
        room_id = headers_or_room_id
    else:
        room_id = get_room_id(headers_or_room_id, default=default)

    room_id = _sanitize_room_id(room_id, default=default)

    vault_root = vault_root or os.environ.get("BRAIN_VAULT_ROOT") or r"C:\AI_VAULT"
    rooms_root = os.path.join(vault_root, "rooms")
    room_root = os.path.join(rooms_root, room_id)

    memory_dir = os.path.join(room_root, "memory")
    state_dir = os.path.join(room_root, "state")
    logs_dir = os.path.join(room_root, "logs")
    artifacts_dir = os.path.join(room_root, "artifacts")

    for d in (rooms_root, room_root, memory_dir, state_dir, logs_dir, artifacts_dir):
        os.makedirs(d, exist_ok=True)

    return RoomPaths(
        room_id=room_id,
        vault_root=vault_root,
        rooms_root=rooms_root,
        room_root=room_root,
        memory_dir=memory_dir,
        state_dir=state_dir,
        logs_dir=logs_dir,
        artifacts_dir=artifacts_dir,
    )
# ===== End room dirs helpers =====



# ===== Legacy mission/plan state helpers (Brain Lab v4) =====
def _default_mission() -> Dict[str, Any]:
    return {
        "version": 1,
        "mission_id": "brainlab-default",
        "title": "Brain Lab — Local Governed Agent",
        "objectives": [
            "Implement Planner→Evaluator endpoints with persistent mission/plan state.",
            "Maintain governance: no destructive actions, auditable logs, reproducible workflow."
        ],
        "constraints": [
            "No auto-executing PowerShell from the assistant.",
            r"All writes confined to C:\AI_VAULT\tmp_agent",
            "All changes must be logged."
        ],
        "created_at": None,
        "updated_at": None
    }

def _default_plan() -> Dict[str, Any]:
    return {
        "version": 1,
        "plan_id": "plan-default",
        "status": "idle",
        "steps": [],
        "history": [],
        "last_eval": None,
        "created_at": None,
        "updated_at": None
    }

def _coerce_room_paths(room_or_headers=None, default: str = "default") -> "RoomPaths":
    # Accept RoomPaths, room_id string, headers dict, request-like object
    if isinstance(room_or_headers, RoomPaths):
        return room_or_headers
    return ensure_room_dirs(room_or_headers, default=default)

def _room_state_path(rp: "RoomPaths", filename: str) -> str:
    return os.path.join(rp.state_dir, filename)

def ensure_room_state_files(room_or_headers=None, default: str = "default") -> "RoomPaths":
    rp = _coerce_room_paths(room_or_headers, default=default)

    mp = _room_state_path(rp, "mission.json")
    pp = _room_state_path(rp, "plan.json")

    if not os.path.exists(mp):
        _atomic_write_json(mp, _default_mission())
    if not os.path.exists(pp):
        _atomic_write_json(pp, _default_plan())

    return rp

def load_mission(room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    mp = _room_state_path(rp, "mission.json")
    m = _safe_read_json(mp)
    return m

def load_plan(room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    pp = _room_state_path(rp, "plan.json")
    p = _safe_read_json(pp)
    return p

def save_mission(mission: Dict[str, Any], room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    mp = _room_state_path(rp, "mission.json")
    m = dict(mission or {})
    m["updated_at"] = _now_iso()
    if not m.get("created_at"):
        m["created_at"] = m["updated_at"]
    _atomic_write_json(mp, m)
    return m

def save_plan(plan: Dict[str, Any], room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    pp = _room_state_path(rp, "plan.json")
    p = dict(plan or {})
    p["updated_at"] = _now_iso()
    if not p.get("created_at"):
        p["created_at"] = p["updated_at"]
    if "history" not in p:
        p["history"] = []
    _atomic_write_json(pp, p)
    return p

def append_history(entry: Dict[str, Any], room_or_headers=None, default: str = "default", cap: int = 200) -> Dict[str, Any]:
    p = load_plan(room_or_headers, default=default)
    hist = p.get("history", [])
    hist.append(entry)
    if len(hist) > cap:
        hist = hist[-cap:]
    p["history"] = hist
    return save_plan(p, room_or_headers, default=default)

# Convenience alias some legacy code may use
def ensure_state_files(room_or_headers=None, default: str = "default") -> "RoomPaths":
    return ensure_room_state_files(room_or_headers, default=default)
# ===== End legacy mission/plan helpers =====



# ===== State repair + legacy helpers (Brain Lab v4) =====
def _needs_init_state_file(path: str) -> bool:
    """
    Initialize if missing OR empty OR invalid JSON OR non-dict.
    """
    if not os.path.exists(path):
        return True
    try:
        obj = _safe_read_json(path)
    except Exception:
        return True
    if not isinstance(obj, dict):
        return True
    if len(obj) == 0:
        return True
    return False


# Override: ensure_room_state_files with repair behavior
def ensure_room_state_files(room_or_headers=None, default: str = "default") -> "RoomPaths":
    rp = _coerce_room_paths(room_or_headers, default=default)

    mp = _room_state_path(rp, "mission.json")
    pp = _room_state_path(rp, "plan.json")

    if _needs_init_state_file(mp):
        _atomic_write_json(mp, _default_mission())
    if _needs_init_state_file(pp):
        _atomic_write_json(pp, _default_plan())

    return rp


def reset_plan(room_or_headers=None, default: str = "default", keep_history: bool = False) -> Dict[str, Any]:
    """
    Reset plan.json to default. Optionally keeps history.
    """
    rp = ensure_room_state_files(room_or_headers, default=default)
    old = None
    if keep_history:
        try:
            old = _safe_read_json(_room_state_path(rp, "plan.json"))
        except Exception:
            old = None

    p = _default_plan()
    if keep_history and isinstance(old, dict):
        p["history"] = old.get("history", []) or []

    return save_plan(p, rp, default=default)


def append_log_ndjson(event: Dict[str, Any], room_or_headers=None, default: str = "default", filename: str = "brain_requests.ndjson") -> str:
    """
    Append a JSON line to per-room logs file.
    Returns log path.
    """
    rp = _coerce_room_paths(room_or_headers, default=default)
    os.makedirs(rp.logs_dir, exist_ok=True)
    log_path = os.path.join(rp.logs_dir, filename)

    e = dict(event or {})
    e.setdefault("ts", _now_iso())
    e.setdefault("room_id", rp.room_id)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

    return log_path
# ===== End state repair + legacy helpers =====



# ===== Mission normalization override (v4) =====
def load_mission(room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    mp = _room_state_path(rp, "mission.json")
    m = _safe_read_json(mp)

    if not isinstance(m, dict):
        m = {}

    # normalize legacy keys -> objective
    if not m.get("objective"):
        if isinstance(m.get("mission"), str) and m["mission"].strip():
            m["objective"] = m["mission"].strip()
        elif isinstance(m.get("title"), str) and m["title"].strip():
            m["objective"] = m["title"].strip()

    # persist normalized form if objective exists
    if m.get("objective"):
        try:
            _atomic_write_json(mp, m)
        except Exception:
            pass

    return m
# ===== End mission normalization override =====



# ===== Mission constraints normalization override (v4.1) =====
def load_mission(room_or_headers=None, default: str = "default") -> Dict[str, Any]:
    rp = ensure_room_state_files(room_or_headers, default=default)
    mp = _room_state_path(rp, "mission.json")
    m = _safe_read_json(mp)

    if not isinstance(m, dict):
        m = {}

    # normalize legacy keys -> objective
    if not m.get("objective"):
        if isinstance(m.get("mission"), str) and m["mission"].strip():
            m["objective"] = m["mission"].strip()
        elif isinstance(m.get("title"), str) and m["title"].strip():
            m["objective"] = m["title"].strip()

    # constraints may be list[str] (from API). Some legacy code incorrectly does dict(constraints).
    # Convert list[str] -> list[tuple[str,str]] so dict() works deterministically.
    c = m.get("constraints")
    if isinstance(c, list) and all(isinstance(x, str) for x in c):
        # keep original too
        m["constraints_list"] = list(c)
        m["constraints"] = [(f"c{i}", s) for i, s in enumerate(c)]

    # persist normalized form
    if m.get("objective"):
        try:
            _atomic_write_json(mp, m)
        except Exception:
            pass

    return m
# ===== End mission constraints normalization override =====

