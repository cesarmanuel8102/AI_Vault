import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Anchor: el bloque del planner v4.4 donde hace plan["steps"] = [...]
# Buscamos el inicio exacto de "plan[\"steps\"] = [" dentro del endpoint plan.
m = re.search(r'plan\["steps"\]\s*=\s*\[\s*\n', txt)
if not m:
    raise SystemExit("No encuentro plan[\"steps\"] = [ en el archivo; abortando.")

# Buscamos el cierre correspondiente de la lista: línea que empiece con "        ]" (indent del planner)
start = m.start()
tail = txt[m.end():]
m_end = re.search(r"\n\s*\]\s*\n\s*agent_store\.save_plan\(plan\)", tail)
if not m_end:
    raise SystemExit("No encuentro el cierre del bloque plan['steps'] antes de agent_store.save_plan(plan); abortando.")
end = m.end() + m_end.start()

# Construimos reemplazo (3 steps) — sin repo
replacement = (
    'plan["steps"] = [\n'
    '            {\n'
    '                "id": "S1",\n'
    '                "title": "Write mission_log.txt (append_file) — gated",\n'
    '                "status": "todo",\n'
    '                "tool_name": "append_file",\n'
    '                "mode": "propose",\n'
    '                "kind": "new_file",\n'
    '                "tool_args": {\n'
    '                    "path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\runs\\\\{room_id}\\\\mission_log.txt",\n'
    '                    "content": "MISSION START\\\\n"\n'
    '                }\n'
    '            },\n'
    '            {\n'
    '                "id": "S2",\n'
    '                "title": "Snapshot set mission_state.json (runtime_snapshot_set)",\n'
    '                "status": "todo",\n'
    '                "tool_name": "runtime_snapshot_set",\n'
    '                "mode": "propose",\n'
    '                "kind": "state",\n'
    '                "tool_args": {\n'
    '                    "path": "mission_state.json",\n'
    '                    "value": {"ts":"", "goal":"", "room_id":""}\n'
    '                }\n'
    '            },\n'
    '            {\n'
    '                "id": "S3",\n'
    '                "title": "Snapshot get mission_state.json (runtime_snapshot_get)",\n'
    '                "status": "todo",\n'
    '                "tool_name": "runtime_snapshot_get",\n'
    '                "mode": "propose",\n'
    '                "kind": "state",\n'
    '                "tool_args": {\n'
    '                    "path": "mission_state.json"\n'
    '                }\n'
    '            }\n'
    '        ]\n'
)

# Inyectamos {room_id} en runtime al momento del plan (usando el room_id del endpoint)
# Sustituimos el bloque completo plan["steps"] = [...]
before = txt[:start]
after = txt[end:]

# Ajuste: el planner tiene room_id disponible como variable room_id (ya calculada en endpoint /plan)
replacement = replacement.replace("{room_id}", '" + str(room_id) + "')

txt2 = before + replacement + after

p.write_text(txt2, encoding="utf-8")
print("OK: Planner actualizado -> plan mínimo misión (S1 log, S2 snapshot_set, S3 snapshot_get).")
