import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
DECOR = '@app.post("/v1/agent/run_once"'

p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# 1) encuentra el decorador
i0 = None
for i, ln in enumerate(lines):
    if DECOR in ln:
        i0 = i
        break
if i0 is None:
    raise SystemExit("No encuentro el decorador de /v1/agent/run_once")

# 2) encuentra el 'def ' siguiente
i_def = None
for i in range(i0, min(len(lines), i0+40)):
    if re.match(r"\s*def\s+agent_run_once\s*\(", lines[i]):
        i_def = i
        break
if i_def is None:
    raise SystemExit("No encuentro def agent_run_once(...) cerca del decorador")

# indent base del cuerpo
m = re.match(r"(\s*)def\s+agent_run_once\s*\(", lines[i_def])
base_indent = (m.group(1) or "") + "    "  # 4 espacios dentro del def

BEGIN = f"{base_indent}# === RUN_ONCE ROOM PERSIST (FIX) BEGIN ===\n"
END   = f"{base_indent}# === RUN_ONCE ROOM PERSIST (FIX) END ===\n"

# si ya existe, no lo duplica
for ln in lines:
    if "RUN_ONCE ROOM PERSIST (FIX) BEGIN" in ln:
        print("SKIP: ya existe RUN_ONCE ROOM PERSIST (FIX)")
        raise SystemExit(0)

# 3) busca el primer 'return {' dentro del def (limitado)
#    Insertamos el bloque justo ANTES del primer return dict para asegurar persistencia del estado final
i_ret = None
for i in range(i_def, min(len(lines), i_def+450)):
    if re.match(rf"{re.escape(base_indent)}return\s+\{{", lines[i]):
        i_ret = i
        break
if i_ret is None:
    raise SystemExit("No encuentro un 'return {' dentro de agent_run_once (ventana 450 líneas)")

block = []
block.append(BEGIN)
block.append(f"{base_indent}try:\n")
block.append(f"{base_indent}    rid = None\n")
block.append(f"{base_indent}    # prefer req.room_id si existe\n")
block.append(f"{base_indent}    try:\n")
block.append(f"{base_indent}        rid = getattr(req, 'room_id', None)\n")
block.append(f"{base_indent}    except Exception:\n")
block.append(f"{base_indent}        rid = None\n")
block.append(f"{base_indent}    # fallback header x-room-id\n")
block.append(f"{base_indent}    if not rid and 'request' in locals() and request is not None:\n")
block.append(f"{base_indent}        try:\n")
block.append(f"{base_indent}            rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')\n")
block.append(f"{base_indent}        except Exception:\n")
block.append(f"{base_indent}            rid = None\n")
block.append(f"{base_indent}    if rid:\n")
block.append(f"{base_indent}        # Tomar mission/plan actuales (si no existen, cargar del store)\n")
block.append(f"{base_indent}        _mission = None\n")
block.append(f"{base_indent}        _plan = None\n")
block.append(f"{base_indent}        try:\n")
block.append(f"{base_indent}            _mission = mission if 'mission' in locals() else None\n")
block.append(f"{base_indent}        except Exception:\n")
block.append(f"{base_indent}            _mission = None\n")
block.append(f"{base_indent}        try:\n")
block.append(f"{base_indent}            _plan = plan if 'plan' in locals() else None\n")
block.append(f"{base_indent}        except Exception:\n")
block.append(f"{base_indent}            _plan = None\n")
block.append(f"{base_indent}        if _mission is None or _plan is None:\n")
block.append(f"{base_indent}            try:\n")
block.append(f"{base_indent}                _mission, _plan = agent_store.load()\n")
block.append(f"{base_indent}            except Exception:\n")
block.append(f"{base_indent}                pass\n")
block.append(f"{base_indent}        from datetime import datetime, timezone\n")
block.append(f"{base_indent}        import json\n")
block.append(f"{base_indent}        now = datetime.now(timezone.utc).isoformat()\n")
block.append(f"{base_indent}        if isinstance(_plan, dict):\n")
block.append(f"{base_indent}            _plan['updated_at'] = now\n")
block.append(f"{base_indent}            _plan.setdefault('room_id', rid)\n")
block.append(f"{base_indent}        if isinstance(_mission, dict):\n")
block.append(f"{base_indent}            _mission['updated_at'] = now\n")
block.append(f"{base_indent}            _mission.setdefault('room_id', rid)\n")
block.append(f"{base_indent}        _room_state_dir(rid)\n")
block.append(f"{base_indent}        paths = _room_paths(rid) or {{}}\n")
block.append(f"{base_indent}        pm = paths.get('mission')\n")
block.append(f"{base_indent}        pp = paths.get('plan')\n")
block.append(f"{base_indent}        from pathlib import Path\n")
block.append(f"{base_indent}        if pm:\n")
block.append(f"{base_indent}            Path(pm).write_text(json.dumps(_mission or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{base_indent}        if pp:\n")
block.append(f"{base_indent}            Path(pp).write_text(json.dumps(_plan or {{}}, ensure_ascii=False, indent=2), encoding='utf-8')\n")
block.append(f"{base_indent}except Exception:\n")
block.append(f"{base_indent}    pass\n")
block.append(END)

new_lines = lines[:i_ret] + block + lines[i_ret:]
p.write_text("".join(new_lines), encoding="utf-8")

print("OK: inserted RUN_ONCE room persist block before return")
print(f"decor_line={i0+1} def_line={i_def+1} insert_before_return_line={i_ret+1}")
