import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# locate def agent_plan_refresh
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_plan_refresh\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_plan_refresh(...)")

# find end (next decorator @app. at same indent or '# ===== End plan refresh =====')
def_indent = re.match(r"(\s*)def\s+agent_plan_refresh", lines[i_def]).group(1)
i_end = None
for j in range(i_def+1, len(lines)):
    if lines[j].startswith(def_indent + "@app."):
        i_end = j
        break
    if "===== End plan refresh" in lines[j]:
        i_end = j+1
        break
if i_end is None:
    i_end = len(lines)

chunk = lines[i_def:i_end]
chunk_txt = "".join(chunk)
MARK = "PLAN_REFRESH ROOM-SAFE (FIX)"
if MARK in chunk_txt:
    print("SKIP: ya existe PLAN_REFRESH ROOM-SAFE (FIX)")
    raise SystemExit(0)

body = def_indent + "    "

# helpers: replace specific parts in the function body using regex on text chunk
t = chunk_txt

# 1) remove request.headers try/except and force room_id from req only
t = re.sub(
    r"\n\s*try:\n\s*hdr_room\s*=\s*request\.headers\.get\([^\n]+\)\s*or\s*request\.headers\.get\([^\n]+\)\s*or\s*None\s*\n\s*except Exception:\n\s*hdr_room\s*=\s*None\s*\n\s*room_id\s*=\s*req\.room_id\s*or\s*hdr_room\s*or\s*\"default\"\s*\n",
    f"\n{body}# === {MARK}: room_id only from req (no Request in signature) ===\n{body}room_id = req.room_id or \"default\"\n",
    t,
    flags=re.MULTILINE
)

# if the above didn't match (format drift), do a simpler replacement of room_id assignment
if "room_id = req.room_id" in t and "hdr_room" in t and "request.headers" in t:
    # fallback: just hard-override after that block
    t = t.replace("room_id = req.room_id or hdr_room or \"default\"", "room_id = req.room_id or \"default\"")

# 2) replace 'mission, plan = agent_store.load()' with per-room disk load
disk_load = (
f"{body}# === {MARK}: load per-room plan/mission from disk ===\n"
f"{body}mission, plan = {{}}, {{}}\n"
f"{body}try:\n"
f"{body}    _room_state_dir(room_id)\n"
f"{body}    paths = _room_paths(room_id) or {{}}\n"
f"{body}    import json\n"
f"{body}    from pathlib import Path\n"
f"{body}    pm = paths.get('mission')\n"
f"{body}    pp = paths.get('plan')\n"
f"{body}    if pm and Path(pm).exists():\n"
f"{body}        mission = json.loads(Path(pm).read_text(encoding='utf-8')) or {{}}\n"
f"{body}    if pp and Path(pp).exists():\n"
f"{body}        plan = json.loads(Path(pp).read_text(encoding='utf-8')) or {{}}\n"
f"{body}except Exception:\n"
f"{body}    mission, plan = {{}}, {{}}\n"
f"{body}plan = plan or {{}}\n"
f"{body}plan.setdefault('room_id', room_id)\n"
)
t = t.replace(f"{body}mission, plan = agent_store.load()\n", disk_load)

# 3) before computing marker, ensure plan/history exists
if "notes: list[str]" in t:
    pass

# 4) sanitize placeholder in repo file content: remove any line containing PLANNER_PLACEHOLDER
# Insert after: content = str(rf.get("content", "") or "")
t = re.sub(
    r"(content\s*=\s*str\(rf\.get\(\"content\",\s*\"\"\)\s*or\s*\"\"\)\s*)\n",
    r"\1\n" + f"{body}        # === {MARK}: strip any PLANNER_PLACEHOLDER lines to avoid refresh loop ===\n"
              f"{body}        try:\n"
              f"{body}            _ls = content.splitlines(True)\n"
              f"{body}            _ls = [ln for ln in _ls if 'PLANNER_PLACEHOLDER' not in ln]\n"
              f"{body}            content = ''.join(_ls)\n"
              f"{body}        except Exception:\n"
              f"{body}            pass\n",
    t
)

# 5) replace agent_store.save_plan(plan) with disk persist (plan.json) + updated_at UTC
disk_save = (
f"{body}# === {MARK}: persist updated plan to per-room disk store ===\n"
f"{body}try:\n"
f"{body}    from datetime import datetime, timezone\n"
f"{body}    import json\n"
f"{body}    from pathlib import Path\n"
f"{body}    now = datetime.now(timezone.utc).isoformat()\n"
f"{body}    plan['updated_at'] = now\n"
f"{body}    plan.setdefault('room_id', room_id)\n"
f"{body}    _room_state_dir(room_id)\n"
f"{body}    paths = _room_paths(room_id) or {{}}\n"
f"{body}    pp = paths.get('plan')\n"
f"{body}    if pp:\n"
f"{body}        Path(pp).write_text(json.dumps(plan or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n"
f"{body}except Exception:\n"
f"{body}    pass\n"
)
t = t.replace(f"{body}agent_store.save_plan(plan)\n", disk_save)

# 6) replace agent_store.append_history({...}) with plan['history'].append(...)
# crude but safe: replace the whole block from agent_store.append_history({ to the matching }) line
t = re.sub(
    r"\n\s*agent_store\.append_history\(\{\n([\s\S]*?)\n\s*\}\)\n",
    "\n" + f"{body}# === {MARK}: append history into plan (room-scoped) ===\n"
           f"{body}try:\n"
           f"{body}    plan.setdefault('history', [])\n"
           f"{body}    plan['history'].append({{\n"
           f"{body}        'kind': 'plan_refresh',\n"
           f"{body}        'room_id': room_id,\n"
           f"{body}        'repo_path': str(repo_path),\n"
           f"{body}        'marker': marker_line,\n"
           f"{body}        'had_placeholder': had_placeholder,\n"
           f"{body}        'appended_marker': (not tail_has_marker) or (not already_marked_somewhere),\n"
           f"{body}    }})\n"
           f"{body}except Exception:\n"
           f"{body}    pass\n",
    t,
    flags=re.MULTILINE
)

# 7) replace "_, plan2 = agent_store.load()" with "plan2 = plan"
t = t.replace(f"{body}_, plan2 = agent_store.load()\n", f"{body}plan2 = plan\n")

# Write back chunk
new_chunk = t.splitlines(True)
new_lines = lines[:i_def] + new_chunk + lines[i_end:]
p.write_text("".join(new_lines), encoding="utf-8")
print("OK: agent_plan_refresh patched to room-safe disk load/save + strip PLANNER_PLACEHOLDER lines")
