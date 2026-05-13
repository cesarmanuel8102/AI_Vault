import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# 1) asegurar import
if "from agent_loop import AgentLoop, AgentPaths" not in s:
    m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
    ins = "from agent_loop import AgentLoop, AgentPaths\n"
    if m:
        s = s[:m.end()] + ins + s[m.end():]
    else:
        s = ins + s

# 2) localizar decorator del POST /v1/agent/mission
m = re.search(r'@router\.post\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(', s)
if not m:
    raise SystemExit("ERROR: No encuentro @router.post('/v1/agent/mission') en brain_router.py")

start = m.start()
after = s[m.end():]
m2 = re.search(r'^\s*@router\.(get|post|put|delete|api_route)\(', after, flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

if "agent_loop_sync:" in block:
    print("OK: brain_router.py ya tenía agent_loop_sync; no se duplicó.")
    p.write_text(s, encoding="utf-8")
    raise SystemExit(0)

lines = block.splitlines(True)

# Buscar último return dentro del handler
ret_i = None
for i in range(len(lines)-1, -1, -1):
    if re.match(r'^\s*return\b', lines[i]):
        ret_i = i
        break
if ret_i is None:
    raise SystemExit("ERROR: no encontré 'return' en el handler POST /v1/agent/mission")

indent = re.match(r'^(\s*)', lines[ret_i]).group(1)

inject = (
f"{indent}# agent_loop_sync: crear mission.json/plan.json compatibles con AgentLoop\n"
f"{indent}try:\n"
f"{indent}    room_id = request.headers.get('x-room-id') or request.headers.get('X-Room-Id') or 'default'\n"
f"{indent}    rid = (room_id or 'default')\n"
f"{indent}    objective = getattr(payload, 'objective', None)\n"
f"{indent}    loop = AgentLoop(paths=AgentPaths.default(room_id=rid))\n"
f"{indent}    loop.plan(goal=str(objective), profile='default', force_new=True)\n"
f"{indent}except Exception:\n"
f"{indent}    pass\n"
)

lines.insert(ret_i, inject)
new_block = "".join(lines)

s = s[:start] + new_block + s[end:]
p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: POST /v1/agent/mission ahora sincroniza AgentLoop (mission.json/plan.json).")
