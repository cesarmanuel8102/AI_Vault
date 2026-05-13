import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Patch ONLY the default planner (/v1/agent/plan) minimal mission step S1
# Replace the whole S1 dict inside plan["steps"] assignment (the one that contains mission_log).
# New S1: dest_dir under repo-safe root + relative path mission_log.txt

# First, locate the plan["steps"] assignment that contains S1 and "mission_log.txt"
m_steps = re.search(r'plan\["steps"\]\s*=\s*\[(?s:.*?)\]\s*\n(?=\s*agent_store\.save_plan\(plan\))', txt)
if not m_steps:
    raise SystemExit('No encuentro el bloque plan["steps"]=[...] antes de agent_store.save_plan(plan).')

steps_block = m_steps.group(0)
if "mission_log.txt" not in steps_block:
    raise SystemExit('Encontré plan["steps"], pero no contiene mission_log.txt (no es el planner HARD esperado).')

# Replace S1 dict (from { "id":"S1" ... },) with a known-good repo-safe version.
pat_s1 = r'\{\s*"id"\s*:\s*"S1"(?s:.*?)\n\s*\},\s*'
m_s1 = re.search(pat_s1, steps_block)
if not m_s1:
    raise SystemExit("No pude localizar el dict completo del step S1 dentro de plan['steps'].")

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

steps_block2, n = re.subn(pat_s1, new_s1 + "\n            ", steps_block, count=1)
if n != 1:
    raise SystemExit("No se aplicó el reemplazo de S1 (pattern mismatch).")

txt2 = txt[:m_steps.start()] + steps_block2 + txt[m_steps.end():]
p.write_text(txt2, encoding="utf-8")
print("OK: patched planner HARD S1 -> repo-safe _agent_runs + relative mission_log.txt")
