import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# 1) Helpers globales (una sola vez)
if "def _runtime_snapshot_path(" not in txt:
    m = re.search(r"^def\s+_room_paths\s*\(", txt, flags=re.MULTILINE)
    if not m:
        raise SystemExit("No encuentro def _room_paths(...) para insertar helper.")
    insert_at = m.start()
    helper = (
        "\n# === RUNTIME SNAPSHOT HELPERS (FIX) BEGIN ===\n"
        "def _runtime_snapshot_path(room_id: str) -> str:\n"
        "    paths = _room_paths(room_id) or {}\n"
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

# 2) Dispatch dentro de agent_execute_step: insertar después de la primera asignación "tool_name = str("
if "EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX)" in txt:
    print("SKIP: dispatch ya existe")
    p.write_text(txt, encoding="utf-8")
    raise SystemExit(0)

lines = txt.splitlines(True)

# Encontrar def agent_execute_step y luego la primera línea tool_name = str(
i_def = None
for i, ln in enumerate(lines):
    if re.match(r"\s*def\s+agent_execute_step\s*\(", ln):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_execute_step(...)")

idx_tool = None
for i in range(i_def, min(len(lines), i_def+600)):
    if re.search(r"^\s*tool_name\s*=\s*str\(", lines[i]):
        idx_tool = i
        break
if idx_tool is None:
    raise SystemExit("No encuentro línea tool_name = str(... ) dentro de agent_execute_step")

indent = re.match(r"(\s*)", lines[idx_tool]).group(1)

block = []
block.append(f"{indent}# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) BEGIN ===\n")
block.append(f"{indent}# Support tool_name: runtime_snapshot_set / runtime_snapshot_get\n")
block.append(f"{indent}if tool_name in ('runtime_snapshot_set','runtime_snapshot_get'):\n")
block.append(f"{indent}    args = (step.get('tool_args') or {{}}) if isinstance(step, dict) else {{}}\n")
block.append(f"{indent}    snap_path = str(args.get('path') or '')\n")
block.append(f"{indent}    if tool_name == 'runtime_snapshot_set':\n")
block.append(f"{indent}        val = args.get('value')\n")
block.append(f"{indent}        try:\n")
block.append(f"{indent}            from datetime import datetime, timezone\n")
block.append(f"{indent}            now = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{indent}        except Exception:\n")
block.append(f"{indent}            now = ''\n")
block.append(f"{indent}        if isinstance(val, dict):\n")
block.append(f"{indent}            val = dict(val)\n")
block.append(f"{indent}            val['ts'] = val.get('ts') or now\n")
block.append(f"{indent}            try:\n")
block.append(f"{indent}                val['goal'] = val.get('goal') or str((plan or {{}}).get('goal') or '')\n")
block.append(f"{indent}            except Exception:\n")
block.append(f"{indent}                val['goal'] = val.get('goal') or ''\n")
block.append(f"{indent}            val['room_id'] = val.get('room_id') or str(room_id)\n")
block.append(f"{indent}        res2 = _runtime_snapshot_set(str(room_id), snap_path, val)\n")
block.append(f"{indent}        result = {{'ok': True, 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{indent}    else:\n")
block.append(f"{indent}        res2 = _runtime_snapshot_get(str(room_id), snap_path)\n")
block.append(f"{indent}        result = {{'ok': bool(res2.get('ok', False)), 'tool_name': tool_name, 'result': res2, 'proposal_id': None}}\n")
block.append(f"{indent}# === EXECUTE_STEP RUNTIME SNAPSHOT DISPATCH (FIX) END ===\n")

lines = lines[:idx_tool+1] + block + lines[idx_tool+1:]
p.write_text("".join(lines), encoding="utf-8")
print("OK: agent_execute_step soporta runtime_snapshot_set/get (dispatch + helpers).")
