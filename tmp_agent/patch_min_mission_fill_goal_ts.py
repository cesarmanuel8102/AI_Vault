import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "MIN_MISSION_GOAL_TS_V1"
if MARK in txt:
    print("SKIP: minimal mission goal/ts already patched")
    raise SystemExit(0)

# Anchor: planner minimal mission uses these titles
t1 = '\"title\": \"Write mission_log.txt (append_file) — gated\"'
t2 = '\"title\": \"Snapshot set mission_state.json (runtime_snapshot_set)\"'

if t1 not in txt or t2 not in txt:
    raise SystemExit("No encuentro los titles del planner minimal mission (S1/S2). Revisa si cambió el planner.")

lines = txt.splitlines(True)

# 1) Insert _now = datetime.now(timezone.utc).isoformat() before the plan["steps"] assignment (inside /v1/agent/plan)
idx_steps = None
for i, ln in enumerate(lines):
    if 'plan["steps"] = [' in ln:
        idx_steps = i
        break
if idx_steps is None:
    raise SystemExit('No encuentro la línea plan["steps"] = [ para insertar _now.')

indent = re.match(r"(\s*)", lines[idx_steps]).group(1)

# Insert only if not already present nearby
window = "".join(lines[max(0, idx_steps-20):idx_steps+5])
if "datetime.now(timezone.utc).isoformat()" not in window:
    inject = []
    inject.append(f"{indent}# === {MARK} BEGIN ===\n")
    inject.append(f"{indent}from datetime import datetime, timezone\n")
    inject.append(f"{indent}_now = datetime.now(timezone.utc).isoformat()\n")
    inject.append(f"{indent}# === {MARK} END ===\n")
    lines = lines[:idx_steps] + inject + lines[idx_steps:]
    # re-find idx_steps after insert
    for i, ln in enumerate(lines):
        if 'plan["steps"] = [' in ln:
            idx_steps = i
            break

txt2 = "".join(lines)

# 2) Replace S1 content "MISSION START\n" -> include ts/room/goal
# We target the FIRST occurrence of '"content": "MISSION START\n"' after S1 title.
pat_s1 = r'(\"title\": \"Write mission_log\.txt \(append_file\) — gated\"[\s\S]{0,400}?\"content\": )\"MISSION START\\n\"'
m = re.search(pat_s1, txt2)
if not m:
    raise SystemExit("No pude localizar S1.content para reemplazar (pattern mismatch).")

s1_repl = r'\1f"MISSION START\nroom_id={room_id}\ngoal={req.goal}\nts={_now}\n"'
txt2 = re.sub(pat_s1, s1_repl, txt2, count=1)

# 3) Replace S2 value {"ts":"","goal":"","room_id":""} -> {"ts": _now, "goal": req.goal, "room_id": room_id}
pat_s2 = r'(\"title\": \"Snapshot set mission_state\.json \(runtime_snapshot_set\)\"[\s\S]{0,500}?\"value\": )\{\s*\"ts\"\s*:\s*\"\"\s*,\s*\"goal\"\s*:\s*\"\"\s*,\s*\"room_id\"\s*:\s*\"\"\s*\}'
m2 = re.search(pat_s2, txt2)
if not m2:
    raise SystemExit("No pude localizar S2.value para reemplazar (pattern mismatch).")

s2_repl = r'\1{"ts": _now, "goal": req.goal, "room_id": str(room_id)}'
txt2 = re.sub(pat_s2, s2_repl, txt2, count=1)

p.write_text(txt2, encoding="utf-8")
print("OK: minimal mission now fills goal+ts into S1.content and S2.value")
