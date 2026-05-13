import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Locate the plan["steps"] assignment right before agent_store.save_plan(plan)
m_steps = re.search(r'plan\["steps"\]\s*=\s*\[(?s:.*?)\]\s*\n(?=\s*agent_store\.save_plan\(plan\))', txt)
if not m_steps:
    raise SystemExit('No encuentro el bloque plan["steps"]=[...] antes de agent_store.save_plan(plan).')

steps_block = m_steps.group(0)
if "mission_log.txt" not in steps_block:
    raise SystemExit('El bloque plan["steps"] encontrado no contiene mission_log.txt; no es el planner HARD que queremos parchear.')

# Find the full S1 dict inside that steps block
pat_s1 = r'\{\s*"id"\s*:\s*"S1"(?s:.*?)\n\s*\},\s*'
m_s1 = re.search(pat_s1, steps_block)
if not m_s1:
    raise SystemExit("No pude localizar el dict completo del step S1 dentro de plan['steps'].")

# Build repo-safe S1 (no absolute path; use dest_dir + relative filename)
new_s1 = r'''{
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
            },'''

# Replace by slicing (no re.sub replacement parsing)
steps_block2 = steps_block[:m_s1.start()] + new_s1 + "\n            " + steps_block[m_s1.end():]

txt2 = txt[:m_steps.start()] + steps_block2 + txt[m_steps.end():]
p.write_text(txt2, encoding="utf-8")
print("OK: HARD planner S1 patched -> repo-safe _agent_runs + relative mission_log.txt (slice replace)")
