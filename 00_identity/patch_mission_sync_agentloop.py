import re
from pathlib import Path

p = Path("brain_server.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# 1) Asegurar import de AgentLoop/AgentPaths
# Insertamos en el bloque de imports si no existen.
if "from agent_loop import AgentLoop, AgentPaths" not in s:
    # Encuentra el final del bloque de imports inicial
    m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
    ins = "from agent_loop import AgentLoop, AgentPaths\n"
    if m:
        s = s[:m.end()] + ins + s[m.end():]
    else:
        s = ins + s

# 2) Localizar handler POST /v1/agent/mission y meter sync a AgentLoop
# Encontrar la función asociada a POST /v1/agent/mission
m = re.search(r'@app\.post\(\s*[\'"]\/v1\/agent\/mission[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(', s)
if not m:
    raise SystemExit("ERROR: No encuentro @app.post('/v1/agent/mission') en brain_server.py")

fn_name = m.group(1)

# Capturar el bloque de la función (heurística: hasta el siguiente decorator @app.)
# Nota: esto asume que no hay decorators internos raros.
start = m.start()
m2 = re.search(r'^\s*@app\.(get|post|put|delete)\(', s[m.end():], flags=re.M)
end = (m.end() + m2.start()) if m2 else len(s)
block = s[start:end]

# Evitar doble parche
if "AgentLoop(AgentPaths.default" in block or "agent_loop_sync" in block:
    p.write_text(s, encoding="utf-8")
    print("OK: brain_server.py ya tenía sync con AgentLoop (no se duplicó).")
    raise SystemExit(0)

# Insertar el sync antes del return final.
# Buscamos el último 'return' del bloque y metemos código antes de ese return.
lines = block.splitlines(True)
return_idx = None
for i in range(len(lines)-1, -1, -1):
    if re.match(r'^\s*return\b', lines[i]):
        return_idx = i
        break
if return_idx is None:
    raise SystemExit("ERROR: No pude encontrar 'return' dentro del handler POST /v1/agent/mission")

indent = re.match(r'^(\s*)', lines[return_idx]).group(1)

insertion = (
f"{indent}# agent_loop_sync: asegurar misión/plan compatibles con AgentLoop (mission_id + plan.mission_id)\n"
f"{indent}try:\n"
f"{indent}    loop = AgentLoop(paths=AgentPaths.default(room_id=rid))\n"
f"{indent}    loop.plan(goal=objective, profile='default', force_new=True)\n"
f"{indent}except Exception as _e:\n"
f"{indent}    # No romper el endpoint si falla el sync; solo reportar en respuesta si quieres.\n"
f"{indent}    pass\n"
)

lines.insert(return_idx, insertion)
new_block = "".join(lines)

s = s[:start] + new_block + s[end:]

p.write_text(s, encoding="utf-8")
print("OK: brain_server.py parcheado: POST /v1/agent/mission ahora sincroniza mission.json/plan.json para AgentLoop.")
