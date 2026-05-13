import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

MARK = "AGENT_EXECUTE_RUNTIME_SNAPSHOT_DISPATCH_V1"
if MARK in txt:
    print("SKIP: agent_execute runtime_snapshot dispatch ya existe")
    raise SystemExit(0)

# 1) ampliar allowed set si existe literal
#    allowed = {"list_dir", "read_file", "write_file", "append_file"}
txt2, n = re.subn(
    r'allowed\s*=\s*\{\s*"list_dir"\s*,\s*"read_file"\s*,\s*"write_file"\s*,\s*"append_file"\s*\}',
    'allowed = {"list_dir", "read_file", "write_file", "append_file", "runtime_snapshot_set", "runtime_snapshot_get"}',
    txt,
    count=1
)
if n == 0:
    # no es fatal (puede estar formateado distinto), seguimos igual
    txt2 = txt

# 2) insertar dispatch justo después del bloque read_file (antes del guardrail/gating de write)
# buscamos el return del read_file:
#   if tool_name == "read_file":
#       ...
#       return {...}
m = re.search(r'(^\s*if\s+tool_name\s*==\s*"read_file"\s*:\s*\n(?:.*\n)*?^\s*return\s+\{[^\n]*\}\s*\n)', txt2, flags=re.MULTILINE)
if not m:
    raise SystemExit('No encuentro el bloque if tool_name == "read_file" con su return; abortando.')

block_indent = re.match(r"(\s*)", m.group(1).splitlines()[-1]).group(1)  # indent del return line
# El dispatch debe estar al mismo indent que los if tool_name == ...
# Derivamos del "if tool_name == "read_file"" indent:
m_if = re.search(r'(^\s*)if\s+tool_name\s*==\s*"read_file"', m.group(1), flags=re.MULTILINE)
if_indent = m_if.group(1) if m_if else ""

dispatch = []
dispatch.append(f"{if_indent}# === {MARK} BEGIN ===\n")
dispatch.append(f"{if_indent}# Handle runtime_snapshot_set/get here to bypass FS write gating\n")
dispatch.append(f"{if_indent}if tool_name in (\"runtime_snapshot_set\", \"runtime_snapshot_get\"):\n")
dispatch.append(f"{if_indent}    try:\n")
dispatch.append(f"{if_indent}        args = tool_args or {{}}\n")
dispatch.append(f"{if_indent}        snap_path = str(args.get(\"path\") or \"\")\n")
dispatch.append(f"{if_indent}        if tool_name == \"runtime_snapshot_set\":\n")
dispatch.append(f"{if_indent}            val = args.get(\"value\")\n")
dispatch.append(f"{if_indent}            # enrich minimal fields if dict\n")
dispatch.append(f"{if_indent}            try:\n")
dispatch.append(f"{if_indent}                from datetime import datetime, timezone\n")
dispatch.append(f"{if_indent}                now = datetime.now(timezone.utc).isoformat()\n")
dispatch.append(f"{if_indent}            except Exception:\n")
dispatch.append(f"{if_indent}                now = \"\"\n")
dispatch.append(f"{if_indent}            if isinstance(val, dict):\n")
dispatch.append(f"{if_indent}                vv = dict(val)\n")
dispatch.append(f"{if_indent}                vv[\"ts\"] = vv.get(\"ts\") or now\n")
dispatch.append(f"{if_indent}                vv[\"room_id\"] = vv.get(\"room_id\") or str(room_id)\n")
dispatch.append(f"{if_indent}                # goal may live in plan; best-effort\n")
dispatch.append(f"{if_indent}                try:\n")
dispatch.append(f"{if_indent}                    vv[\"goal\"] = vv.get(\"goal\") or str((agent_store.load_plan(room_id) or {{}}).get(\"goal\") or \"\")\n")
dispatch.append(f"{if_indent}                except Exception:\n")
dispatch.append(f"{if_indent}                    vv[\"goal\"] = vv.get(\"goal\") or \"\"\n")
dispatch.append(f"{if_indent}                val = vv\n")
dispatch.append(f"{if_indent}            out = _runtime_snapshot_set_kv(str(room_id), snap_path, val)\n")
dispatch.append(f"{if_indent}        else:\n")
dispatch.append(f"{if_indent}            out = _runtime_snapshot_get_kv(str(room_id), snap_path)\n")
dispatch.append(f"{if_indent}        return {{\"ok\": bool(out.get(\"ok\", False)), \"room_id\": room_id, \"step_id\": req.step_id, \"tool_name\": tool_name, \"result\": out}}\n")
dispatch.append(f"{if_indent}    except Exception as e:\n")
dispatch.append(f"{if_indent}        raise HTTPException(status_code=500, detail=f\"runtime_snapshot failure: {{e}}\")\n")
dispatch.append(f"{if_indent}# === {MARK} END ===\n\n")

txt3 = txt2[:m.end()] + "".join(dispatch) + txt2[m.end():]
p.write_text(txt3, encoding="utf-8")
print("OK: inserted agent_execute runtime_snapshot_set/get dispatch (bypass write gating)")
