import re, sys
from pathlib import Path

p = Path("brain_server.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# 1) Verifica que existan los endpoints base
if '"/v1/agent/step"' not in s and "'/v1/agent/step'" not in s:
    print("ERROR: No encuentro /v1/agent/step en brain_server.py")
    sys.exit(1)

if '"/v1/agent/snapshot/set"' not in s and "'/v1/agent/snapshot/set'" not in s:
    print("WARNING: No encuentro /v1/agent/snapshot/set. El one-shot lo puedo crear igual, pero necesito saber cómo guardas snapshot.")
    # no salimos; solo avisamos

# 2) Asegura imports mínimos (sin duplicar)
def ensure_import(line):
    nonlocal_s = globals()
    global s
    if line not in s:
        # inserta después del bloque de imports inicial (heurística)
        m = re.search(r'^(from .+\n|import .+\n)+', s, flags=re.M)
        if m:
            s = s[:m.end()] + line + "\n" + s[m.end():]
        else:
            s = line + "\n" + s

ensure_import("from pydantic import BaseModel, Field")
ensure_import("from typing import Any, Dict, Optional")

# 3) Inserta modelos si no existen
models_block = r'''
class RuntimeSnapshotIn(BaseModel):
    nlv: float = Field(..., description="Net Liquidation Value")
    daily_pnl: float = Field(..., description="PnL del día")
    weekly_drawdown: float = Field(..., description="DD semanal (escala consistente con tu motor)")
    total_exposure: float = Field(..., description="Exposición total (escala consistente con tu motor)")


class StepWithSnapshotIn(BaseModel):
    snapshot: RuntimeSnapshotIn
    plan: Optional[Dict[str, Any]] = None
'''.strip() + "\n\n"

if "class RuntimeSnapshotIn(BaseModel):" not in s:
    # inserta antes del primer @app. (para que esté definido antes de usarse)
    m = re.search(r'^\s*@app\.(get|post|put|delete)\(', s, flags=re.M)
    if not m:
        print("ERROR: No encuentro ningún decorator @app.* para insertar modelos antes.")
        sys.exit(1)
    s = s[:m.start()] + models_block + s[m.start():]

# 4) Inserta endpoint one-shot si no existe
if '"/v1/agent/step_with_snapshot"' not in s and "'/v1/agent/step_with_snapshot'" not in s:
    # Encuentra la función del endpoint /v1/agent/step y su nombre de función
    # Patrón: @app.post("/v1/agent/step")\n def NAME(
    m = re.search(r'@app\.post\(\s*[\'"]\/v1\/agent\/step[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(', s)
    if not m:
        print("ERROR: No pude identificar la función Python asociada a /v1/agent/step")
        sys.exit(1)
    step_fn = m.group(1)

    # Identifica snapshot_set fn si existe
    sm = re.search(r'@app\.post\(\s*[\'"]\/v1\/agent\/snapshot\/set[\'"]\s*\)\s*\n\s*def\s+([A-Za-z_]\w*)\s*\(', s)
    snapshot_fn = sm.group(1) if sm else None

    # Inserta el nuevo endpoint justo antes del /v1/agent/step (para que quede cerca)
    insert_at = m.start()

    one_shot = []
    one_shot.append('@app.post("/v1/agent/step_with_snapshot")')
    one_shot.append('def step_with_snapshot(payload: StepWithSnapshotIn, request: Request):')
    one_shot.append('    """One-shot: guarda snapshot validado y ejecuta el mismo flujo que /v1/agent/step."""')
    one_shot.append('    # Reusa el endpoint existente /snapshot/set si está disponible; si no, falla explícito.')
    if snapshot_fn:
        one_shot.append('    # 1) Persistir snapshot (validado por Pydantic)')
        one_shot.append(f'    {snapshot_fn}(payload.snapshot, request)')
        one_shot.append('    # 2) Ejecutar el mismo flujo que /step')
        one_shot.append(f'    return {step_fn}(payload.plan if payload.plan is not None else {{}}, request)')
    else:
        one_shot.append('    raise HTTPException(status_code=400, detail={"code":"SNAPSHOT_SET_MISSING","message":"No existe /v1/agent/snapshot/set en este servidor; no puedo persistir snapshot."})')
    one_shot.append('')

    block = "\n".join(one_shot) + "\n\n"
    s = s[:insert_at] + block + s[insert_at:]

# 5) Escribe de vuelta
p.write_text(s, encoding="utf-8")
print("OK: brain_server.py parcheado (models + /v1/agent/step_with_snapshot)")
