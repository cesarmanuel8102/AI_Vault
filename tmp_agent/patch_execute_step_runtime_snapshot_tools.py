import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Insertar helper global si no existe
if "def _runtime_snapshot_path(" not in txt:
    # Insertamos cerca de _room_paths / _room_state_dir (top helpers)
    m = re.search(r"^def\s+_room_paths\s*\(", txt, flags=re.MULTILINE)
    if not m:
        raise SystemExit("No encuentro def _room_paths(...) para insertar helper; abortando.")
    # Insert before _room_paths
    insert_at = m.start()
    helper = (
        "\n# === RUNTIME SNAPSHOT HELPERS (FIX) BEGIN ===\n"
        "def _runtime_snapshot_path(room_id: str) -> str:\n"
        "    paths = _room_paths(room_id) or {}\n"
        "    # endpoint runtime/snapshot/set usa runtime_snapshot.json en rooms/<rid>/\n"
        "    return str(paths.get('runtime_snapshot') or '')\n"
        "\n"
        "def _runtime_snapshot_set(room_id: str, path: str, value):\n"
        "    from pathlib import Path\n"
        "    import json\n"
        "    _room_state_dir(room_id)\n"
        "    fp = _runtime_snapshot_path(room_id)\n"
        "    if not fp:\n"
        "        fp = str(Path(_room_state_dir(room_id)) / 'runtime_snapshot.json')\n"
        "    payload = {'path': str(path or ''), 'value': value}\n"
        "    Path(fp).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')\n"
        "    return {'ok': True, 'path': fp}\n"
        "\n"
        "def _runtime_snapshot_get(room_id: str, path: str):\n"
        "    from pathlib import Path\n"
        "    import json\n"
        "    _room_state_dir(room_id)\n"
        "    fp = _runtime_snapshot_path(room_id)\n"
        "    if not fp:\n"
        "        fp = str(Path(_room_state_dir(room_id)) / 'runtime_snapshot.json')\n"
        "    f = Path(fp)\n"
        "    if not f.exists():\n"
        "        return {'ok': False, 'error': 'SNAPSHOT_MISSING', 'path': fp}\n"
        "    obj = json.loads(f.read_text(encoding='utf-8')) or {}\n"
        "    if str(obj.get('path') or '') != str(path or ''):\n"
        "        return {'ok': False, 'error': 'SNAPSHOT_PATH_MISMATCH', 'path': fp, 'snapshot': obj}\n"
        "    return {'ok': True, 'path': fp, 'snapshot': obj}\n"
        "# === RUNTIME SNAPSHOT HELPERS (FIX) END ===\n\n"
    )
    txt = txt[:insert_at] + helper + txt[insert_at:]

# Ahora añadimos dispatch en agent_execute_step
# Buscamos un lugar estable: dentro de agent_execute_step debe existir tool_name = ...
m = re.search(r"def\s+agent_execute_step\s*\(.*?\):", txt)
if not m:
    raise SystemExit("No encuentro def agent_execute_step; abortando.")

# Insertamos un bloque justo después de resolver room_id/step_id/tool_name (buscamos 'tool_name =' dentro del def)
m2 = re.search(r"def\s+agent_execute_step\s*\(.*?\):(?s).*?\n\s*tool_name\s*=\s*str\(", txt)
if not m2:
    raise SystemExit("No encuentro asignación tool_name=str(...) dentro de agent_execute_step; abortando.")

# Insert after that line (primera ocurrencia)
lines = txt.splitlines(True)
idx_tool = None
for i, ln in enumerate(lines):
    if re.search(r"^\s*tool_name\s*=\s*str\(", ln):
        idx_tool = i
        break
if idx_tool is None:
    raise SystemExit("No encuentro línea tool_name = str(...); abortando.")

# Evitar duplicación
if "EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX)" in txt:
    print("SKIP: dispatch runtime snapshot ya existe")
    raise SystemExit(0)

indent = re.match(r"(\s*)", lines[idx_tool]).group(1)
b = indent

block = []
block.append(f"{b}# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) BEGIN ===\n")
block.append(f"{b}# Support tool_name: runtime_snapshot_set / runtime_snapshot_get\n")
block.append(f"{b}if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):\n")
block.append(f"{b}    args = (step.get('tool_args') or {{}}) if isinstance(step, dict) else {{}}\n")
block.append(f"{b}    snap_path = str(args.get('path') or '')\n")
block.append(f"{b}    if tool_name == 'runtime_snapshot_set':\n")
block.append(f"{b}        # fill value with live ts/goal/room_id if dict-like\n")
block.append(f"{b}        val = args.get('value')\n")
block.append(f"{b}        try:\n")
block.append(f"{b}            from datetime import datetime, timezone\n")
block.append(f"{b}            now = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{b}        except Exception:\n")
block.append(f"{b}            now = ''\n")
block.append(f"{b}        if isinstance(val, dict):\n")
block.append(f"{b}            val = dict(val)\n")
block.append(f"{b}            val.setdefault('ts', now)\n")
block.append(f"{b}            val.setdefault('goal', str((plan or {{}}).get('goal') or ''))\n")
block.append(f"{b}            val.setdefault('room_id', str(room_id))\n")
block.append(f"{b}        res2 = _runtime_snapshot_set(str(room_id), snap_path, val)\n")
block.append(f"{b}        result = {{'ok': True, 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{b}        # continue to return (persist block will mark done)\n")
block.append(f"{b}    else:\n")
block.append(f"{b}        res2 = _runtime_snapshot_get(str(room_id), snap_path)\n")
block.append(f"{b}        result = {{'ok': bool(res2.get('ok', False)), 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{b}# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) END ===\n")

lines = lines[:idx_tool+1] + block + lines[idx_tool+1:]
p.write_text("".join(lines), encoding="utf-8")
print("OK: agent_execute_step soporta runtime_snapshot_set/get (dispatch + helpers).")
