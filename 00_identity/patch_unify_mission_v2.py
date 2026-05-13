import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# asegurar imports mínimos (idempotente)
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

# helper: insertar STATE_AGENT_ROOT constant una sola vez (después de imports)
if "STATE_AGENT_ROOT = Path(r\"C:\\\\AI_VAULT\\\\state\\\\agent\")" not in s:
    m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
    insert_at = m.end() if m else 0
    s = s[:insert_at] + "\nSTATE_AGENT_ROOT = Path(r\"C:\\AI_VAULT\\state\\agent\")\n\n" + s[insert_at:]

def replace_function_block(decorator_regex: str, new_block: str):
    global s
    m = re.search(decorator_regex, s, flags=re.S)
    if not m:
        raise SystemExit(f"ERROR: No encuentro endpoint con patrón: {decorator_regex}")
    start = m.start()
    after = s[m.end():]
    m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
    end = (m.end() + m2.start()) if m2 else len(s)
    s = s[:start] + new_block + s[end:]

# -------------------------
# PATCH POST /v1/agent/mission
# -------------------------
post_regex = r'@router\.post\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+agent_set_mission\s*\(.*?\)\s*:\s*\n'
post_block = r'''@router.post("/v1/agent/mission")
def agent_set_mission(request: Request, body: MissionCreate):
    """
    Unificado a misión v2 (mission_id/goal/status/notes) como source of truth.
    Mantiene alias legacy dentro del mismo objeto para compat.
    """
    room_id = get_room_id(request)

    # goal preferente: objective (legacy)
    goal = ""
    try:
        goal = (getattr(body, "objective", None) or "").strip()
    except Exception:
        goal = ""
    if not goal:
        goal = "unspecified"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # epoch compat (legacy)
    try:
        created_epoch = int(datetime.now(timezone.utc).timestamp())
    except Exception:
        created_epoch = 0

    # construir misión v2
    mission = {
        "mission_id": "mission_" + uuid.uuid4().hex[:12],
        "created_ts": now,
        "updated_ts": now,
        "goal": goal,
        "status": "running",
        "notes": []
    }

    # alias legacy (compat)
    mission["room_id"] = room_id
    mission["objective"] = goal
    mission["constraints"] = []
    mission["created_at"] = created_epoch
    mission["updated_at"] = created_epoch
    mission["status_legacy"] = "active"

    # persistir
    try:
        d = (STATE_AGENT_ROOT / room_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "mission.json").write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MISSION_WRITE_FAILED: {e!r}")

    return {"ok": True, "mission": mission}
'''
replace_function_block(post_regex, post_block)

# -------------------------
# PATCH GET /v1/agent/mission
# -------------------------
get_regex = r'@router\.get\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+agent_get_mission\s*\(.*?\)\s*:\s*\n'
get_block = r'''@router.get("/v1/agent/mission")
def agent_get_mission(request: Request):
    """
    Devuelve misión v2 desde state/agent/<room>/mission.json.
    Si solo existe legacy, lo retorna tal cual.
    """
    room_id = get_room_id(request)

    mp = STATE_AGENT_ROOT / room_id / "mission.json"
    if not mp.exists():
        # fallback legacy si tu código lo tenía (si no existe, devolver {})
        try:
            return {"ok": True, "mission": load_mission(room_id) or {}}
        except Exception:
            return {"ok": True, "mission": {}}

    try:
        mission = json.loads(mp.read_text(encoding="utf-8", errors="ignore") or "{}") or {}
    except Exception:
        mission = {}

    # si es v2 (mission_id), asegurar aliases legacy para compat
    if isinstance(mission, dict) and mission.get("mission_id"):
        goal = (mission.get("goal") or "").strip()
        mission.setdefault("room_id", room_id)
        mission.setdefault("objective", goal)
        mission.setdefault("constraints", [])
        # epoch compat best-effort
        if "created_at" not in mission:
            try:
                mission["created_at"] = int(datetime.now(timezone.utc).timestamp())
            except Exception:
                mission["created_at"] = 0
        if "updated_at" not in mission:
            try:
                mission["updated_at"] = int(datetime.now(timezone.utc).timestamp())
            except Exception:
                mission["updated_at"] = 0
        mission.setdefault("status_legacy", "active" if (mission.get("status") == "running") else str(mission.get("status") or ""))

    return {"ok": True, "mission": mission}
'''
replace_function_block(get_regex, get_block)

p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: POST/GET /v1/agent/mission unificados a v2 (mission_id) con compat legacy.")
