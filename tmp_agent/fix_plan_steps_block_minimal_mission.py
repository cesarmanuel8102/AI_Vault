import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Reemplaza plan["steps"] = [ ... ] justo antes de agent_store.save_plan(plan)
pat = r'plan\["steps"\]\s*=\s*\[(?s:.*?)\n\s*\]\s*\n(?=\s*agent_store\.save_plan\(plan\))'
m = re.search(pat, txt)
if not m:
    raise SystemExit("No pude encontrar el bloque plan[\"steps\"]=[...] antes de agent_store.save_plan(plan).")

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
    '                    "path": "C:\\\\AI_VAULT\\\\tmp_agent\\\\runs\\\\" + str(room_id) + "\\\\mission_log.txt",\n'
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

txt2 = re.sub(pat, replacement, txt, count=1)
p.write_text(txt2, encoding="utf-8")
print("OK: plan[steps] reemplazado (hard replace) -> minimal mission (S1 log, S2 set, S3 get).")
