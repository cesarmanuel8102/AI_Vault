import re
from pathlib import Path

p = Path("brain_server.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# Asegura import de Request (debe existir) y NO dependemos de HTTPException.
# (Si HTTPException está importado no molesta, pero ya no lo necesitamos.)

# Encuentra el bloque actual de step_with_snapshot y reemplázalo completo
pattern = r'@app\.post\(\s*["\']\/v1\/agent\/step_with_snapshot["\']\s*\)\s*\ndef\s+step_with_snapshot\([^\n]*\):\n(?:[ \t].*\n)+?\n'

m = re.search(pattern, s)
if not m:
    raise SystemExit("ERROR: No encuentro la definición actual de /v1/agent/step_with_snapshot para reemplazar.")

replacement = '''@app.post("/v1/agent/step_with_snapshot")
def step_with_snapshot(payload: StepWithSnapshotIn, request: Request):
    """One-shot: persiste runtime snapshot validado y ejecuta el mismo flujo que /v1/agent/step."""
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")

    # 1) Persistir snapshot (validado por Pydantic)
    snapshot_dict = payload.snapshot.model_dump()
    wr = _runtime_snapshot_write(rid, snapshot_dict)
    if not bool(wr.get("ok", False)):
        return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}

    # 2) Ejecutar MISMO flujo que /step (hard block -> preflight -> latch -> etc.)
    return agent_step(request)
'''

s = s[:m.start()] + replacement + "\n\n" + s[m.end():]

# (Opcional) Agrega alias /v1/agent/snapshot/set si no existe ya
if '"/v1/agent/snapshot/set"' not in s and "'/v1/agent/snapshot/set'" not in s:
    # Insertarlo cerca del endpoint runtime/snapshot/set si existe, si no, lo insertamos antes de /v1/agent/step
    insert_at = None
    rm = re.search(r'@app\.post\(\s*[\'"]\/v1\/agent\/runtime\/snapshot\/set[\'"]\s*\)', s)
    if rm:
        # inserta justo después del endpoint runtime/snapshot/set (al final de su función)
        # heurística: encuentra la siguiente línea en blanco doble tras ese endpoint
        # si falla, caemos al insert antes del /step.
        pass

    sm = re.search(r'@app\.post\(\s*[\'"]\/v1\/agent\/step[\'"]\s*\)\s*\n\s*def\s+', s)
    if sm:
        insert_at = sm.start()

    if insert_at is not None:
        alias = '''@app.post("/v1/agent/snapshot/set")
def snapshot_set_alias(payload: RuntimeSnapshotIn, request: Request):
    """Alias de compatibilidad: escribe runtime snapshot en /v1/agent/runtime/snapshot/set."""
    room_id = request.headers.get("x-room-id") or request.headers.get("X-Room-Id") or "default"
    rid = (room_id or "default")
    snapshot_dict = payload.model_dump()
    wr = _runtime_snapshot_write(rid, snapshot_dict)
    if not bool(wr.get("ok", False)):
        return {"ok": False, "error": str(wr.get("error") or "SNAPSHOT_WRITE_FAILED"), "detail": wr, "room_id": rid}
    return {"ok": True, "room_id": rid, "snapshot_path": wr.get("path")}
'''
        s = s[:insert_at] + alias + "\n\n" + s[insert_at:]

p.write_text(s, encoding="utf-8")
print("OK: step_with_snapshot corregido (usa _runtime_snapshot_write + llama agent_step). Alias /v1/agent/snapshot/set agregado si faltaba.")
