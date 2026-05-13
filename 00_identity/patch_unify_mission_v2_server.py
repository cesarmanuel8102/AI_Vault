import re
from pathlib import Path

p = Path("brain_server.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# Imports mínimos (idempotente)
need = [
    ("import uuid", "import uuid\n"),
    ("from datetime import datetime, timezone", "from datetime import datetime, timezone\n"),
    ("from pathlib import Path", "from pathlib import Path\n"),
]
for marker, ins in need:
    if marker not in s:
        m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
        if m:
            s = s[:m.end()] + ins + s[m.end():]
        else:
            s = ins + s

# STATE_AGENT_ROOT (idempotente)
if "STATE_AGENT_ROOT = Path(r\"C:\\\\AI_VAULT\\\\state\\\\agent\")" not in s:
    m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
    insert_at = m.end() if m else 0
    s = s[:insert_at] + "\nSTATE_AGENT_ROOT = Path(r\"C:\\AI_VAULT\\state\\agent\")\n\n" + s[insert_at:]

def replace_endpoint_block(path: str, method: str, new_block: str):
    """
    Reemplaza el bloque de función decorada con @app.<method> o @router.<method> para ese path.
    """
    global s
    # soporta @app y @router
    rx = rf'@(app|router)\.{method}\(\s*[\'"]{re.escape(path)}[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(.*?\)\s*:\s*\n'
    m = re.search(rx, s, flags=re.S)
    if not m:
        raise SystemExit(f"ERROR: No encuentro {method.upper()} {path} en brain_server.py")
    start = m.start()
    after = s[m.end():]
    m2 = re.search(r'^\s*@(app|router)\.(get|post|put|delete|api_route)\(', after, flags=re.M)
    end = (m.end() + m2.start()) if m2 else len(s)
    s = s[:start] + new_block + s[end:]

post_block = r'''@app.post("/v1/agent/mission")
def agent_set_mission(request: Request, body: MissionCreate):
    """
    Misión v2 como source of truth: state/agent/<room>/mission.json
    Devuelve v2 + aliases legacy para compat.
    """
    room_id = get_room_id(request)

    goal = ""
    try:
        goal = (getattr(body, "objective", None) or "").strip()
    except Exception:
        goal = ""
    if not goal:
        goal = "unspecified"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        epoch = int(datetime.now(timezone.utc).timestamp())
    except Exception:
        epoch = 0

    mission = {
        "mission_id": "mission_" + uuid.uuid4().hex[:12],
        "created_ts": now,
        "updated_ts": now,
        "goal": goal,
        "status": "running",
        "notes": [],
        # legacy compat (sin romper clientes)
        "room_id": room_id,
        "objective": goal,
        "constraints": [],
        "created_at": epoch,
        "updated_at": epoch,
        "status_legacy": "active",
    }

    try:
        d = (STATE_AGENT_ROOT / room_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "mission.json").write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MISSION_WRITE_FAILED: {e!r}")

    return {"ok": True, "mission": mission}
'''

get_block = r'''@app.get("/v1/agent/mission")
def agent_get_mission(request: Request):
    """
    Lee misión v2 desde state/agent/<room>/mission.json.
    """
    room_id = get_room_id(request)
    mp = STATE_AGENT_ROOT / room_id / "mission.json"

    if not mp.exists():
        # fallback legacy si existe en tu server
        try:
            return {"ok": True, "mission": load_mission(room_id) or {}}
        except Exception:
            return {"ok": True, "mission": {}}

    try:
        mission = json.loads(mp.read_text(encoding="utf-8", errors="ignore") or "{}") or {}
    except Exception:
        mission = {}

    # asegurar alias legacy si es v2
    if isinstance(mission, dict) and mission.get("mission_id"):
        goal = (mission.get("goal") or "").strip()
        mission.setdefault("room_id", room_id)
        mission.setdefault("objective", goal)
        mission.setdefault("constraints", [])
        mission.setdefault("status_legacy", "active" if (mission.get("status") == "running") else str(mission.get("status") or ""))
        if "created_at" not in mission:
            try: mission["created_at"] = int(datetime.now(timezone.utc).timestamp())
            except Exception: mission["created_at"] = 0
        if "updated_at" not in mission:
            try: mission["updated_at"] = int(datetime.now(timezone.utc).timestamp())
            except Exception: mission["updated_at"] = 0

    return {"ok": True, "mission": mission}
'''

replace_endpoint_block("/v1/agent/mission", "post", post_block)
replace_endpoint_block("/v1/agent/mission", "get",  get_block)

p.write_text(s, encoding="utf-8")
print("OK: brain_server.py parcheado: POST/GET /v1/agent/mission unificados a v2 (mission_id).")
