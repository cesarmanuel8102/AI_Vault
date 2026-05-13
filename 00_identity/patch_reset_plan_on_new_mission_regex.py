import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# 1) Ubicar el handler POST /v1/agent/mission
post_rx = r'@router\.post\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+agent_set_mission\s*\(.*?\)\s*:\s*\n'
m = re.search(post_rx, s, flags=re.S)
if not m:
    raise SystemExit("ERROR: No encuentro POST /v1/agent/mission en brain_router.py")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# 2) Confirmar que existe el marcador SYNC_PLAN_WITH_MISSION_V2 (si no, no tocamos nada)
if "SYNC_PLAN_WITH_MISSION_V2" not in block:
    raise SystemExit("ERROR: No encuentro SYNC_PLAN_WITH_MISSION_V2 dentro del POST /v1/agent/mission")

# 3) Encontrar el segmento que queremos reemplazar:
# desde "# SYNC_PLAN_WITH_MISSION_V2" hasta justo antes del return {"ok": True, "mission": mission}
seg_rx = re.compile(
    r'(?P<head>^\s*#\s*SYNC_PLAN_WITH_MISSION_V2[^\n]*\n)'
    r'(?P<body>.*?)(?=^\s*return\s+\{\s*"ok"\s*:\s*True\s*,\s*"mission"\s*:\s*mission\s*\}\s*$)',
    flags=re.S | re.M
)
ms = seg_rx.search(block)
if not ms:
    raise SystemExit("ERROR: No pude capturar el segmento SYNC_PLAN_WITH_MISSION_V2 hasta el return en POST /mission")

head = ms.group("head")
# indent base: el de la línea del marcador
indent = re.match(r'^(\s*)', head).group(1)

# 4) Construir el nuevo segmento (Política A: reset duro si cambia mission_id)
# Idempotencia: si ya contiene "RESET_PLAN_ON_NEW_MISSION_V2", no duplicar
if "RESET_PLAN_ON_NEW_MISSION_V2" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: brain_router.py ya tenía RESET_PLAN_ON_NEW_MISSION_V2 (no se duplicó).")
    raise SystemExit(0)

new_body = f"""{indent}# RESET_PLAN_ON_NEW_MISSION_V2: plan nuevo por misión nueva
{indent}try:
{indent}    room_dir = (STATE_AGENT_ROOT / room_id)
{indent}    room_dir.mkdir(parents=True, exist_ok=True)
{indent}    pp = (room_dir / "plan.json")
{indent}    plan_obj = {{}}
{indent}    if pp.exists():
{indent}        try:
{indent}            plan_obj = json.loads(pp.read_text(encoding="utf-8", errors="ignore") or "{{}}") or {{}}
{indent}        except Exception:
{indent}            plan_obj = {{}}

{indent}    # si no hay plan válido => crear uno mínimo
{indent}    if not isinstance(plan_obj, dict) or not plan_obj:
{indent}        plan_obj = {{
{indent}            "mission_id": mission.get("mission_id"),
{indent}            "created_ts": mission.get("created_ts"),
{indent}            "updated_ts": mission.get("updated_ts"),
{indent}            "profile": "default",
{indent}            "cursor": 0,
{indent}            "steps": []
{indent}        }}
{indent}    else:
{indent}        # mismatch => plan pertenece a otra misión => reset duro
{indent}        if plan_obj.get("mission_id") != mission.get("mission_id"):
{indent}            plan_obj = {{
{indent}                "mission_id": mission.get("mission_id"),
{indent}                "created_ts": mission.get("created_ts"),
{indent}                "updated_ts": mission.get("updated_ts"),
{indent}                "profile": "default",
{indent}                "cursor": 0,
{indent}                "steps": []
{indent}            }}
{indent}        else:
{indent}            # misma misión: solo refrescar updated_ts y saneo mínimo
{indent}            if mission.get("updated_ts"):
{indent}                plan_obj["updated_ts"] = mission.get("updated_ts")
{indent}            if not plan_obj.get("profile"):
{indent}                plan_obj["profile"] = "default"
{indent}            if "cursor" not in plan_obj:
{indent}                plan_obj["cursor"] = 0
{indent}            if "steps" not in plan_obj or plan_obj["steps"] is None:
{indent}                plan_obj["steps"] = []

{indent}    pp.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")
{indent}except Exception:
{indent}    pass

"""

block2 = block[:ms.start("head")] + head + new_body + block[ms.end("body"):]

s2 = s[:start] + block2 + s[end:]
p.write_text(s2, encoding="utf-8")
print("OK: brain_router.py parcheado: POST /mission resetea plan.json si cambia mission_id (regex robusto).")
