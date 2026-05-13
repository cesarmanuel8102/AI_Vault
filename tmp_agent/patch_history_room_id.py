import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"

p = Path(SERVER)
txt = p.read_text(encoding="utf-8")
lines = txt.splitlines(True)

# Buscamos el bloque específico (Planner v4.4) donde aparece "# Always append history"
needle = "    # Always append history"
idx = None
for i, ln in enumerate(lines):
    if ln.rstrip("\n") == needle:
        idx = i
        break
if idx is None:
    raise SystemExit("No encuentro la línea exacta: '    # Always append history'")

# Verifica que unas líneas después exista "agent_store.append_history"
window = "".join(lines[idx:idx+15])
if "agent_store.append_history" not in window:
    raise SystemExit("Encontré '# Always append history' pero no veo agent_store.append_history cerca; abortando para no tocar lo equivocado.")

# Insertamos cálculo de rid justo después del comentario
indent = re.match(r"[ \t]*", lines[idx]).group(0)  # debería ser '    '

insertion = []
insertion.append(f"{indent}# Derive room_id for history (prefer req.room_id, fallback x-room-id header)\n")
insertion.append(f"{indent}rid = None\n")
insertion.append(f"{indent}try:\n")
insertion.append(f"{indent}    rid = getattr(req, 'room_id', None)\n")
insertion.append(f"{indent}except Exception:\n")
insertion.append(f"{indent}    rid = None\n")
insertion.append(f"{indent}if not rid and 'request' in locals() and request is not None:\n")
insertion.append(f"{indent}    try:\n")
insertion.append(f"{indent}        rid = request.headers.get('x-room-id') or request.headers.get('X-Room-Id')\n")
insertion.append(f"{indent}    except Exception:\n")
insertion.append(f"{indent}        rid = None\n")

# Ahora reemplazamos dentro del dict: "room_id": req.room_id, -> "room_id": rid,
# pero solo dentro de una ventana acotada para evitar falsos positivos.
start = idx
end = min(len(lines), idx + 40)
sub = lines[start:end]
joined = "".join(sub)

if '"room_id": req.room_id' not in joined:
    raise SystemExit('No encuentro el literal \'"room_id": req.room_id\' dentro de la ventana; abortando.')

joined2 = joined.replace('"room_id": req.room_id,', '"room_id": rid,', 1)
# Re-armar sub-bloque
sub2 = joined2.splitlines(True)

# Construir archivo final:
# - mantener hasta idx+1 (incluye el comentario)
# - insertar líneas de rid
# - luego reemplazar ventana con la versión modificada
new_lines = []
new_lines.extend(lines[:idx+1])
new_lines.extend(insertion)
new_lines.extend(sub2[1:])  # sub2 ya incluye la línea del comentario como primera; evitamos duplicarla
new_lines.extend(lines[end:])

p.write_text("".join(new_lines), encoding="utf-8")
print("OK: history room_id patched (rid derived + append_history uses rid)")
print(f"Inserted after line {idx+1}, replaced within lines {start+1}-{end}")
