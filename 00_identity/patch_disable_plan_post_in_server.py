import re
from pathlib import Path

p = Path("brain_server.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# Si ya fue renombrado, no hacer nada
if '/v1/agent/plan_legacy' in s:
    print("OK: brain_server.py ya tenía /v1/agent/plan_legacy (no se duplicó).")
    raise SystemExit(0)

# Reemplazar SOLO el decorator exacto @app.post("/v1/agent/plan") (o con comillas simples)
s2, n = re.subn(
    r'@app\.post\(\s*[\'"]\/v1\/agent\/plan[\'"]\s*\)',
    '@app.post("/v1/agent/plan_legacy")',
    s,
    count=1
)

if n != 1:
    raise SystemExit("ERROR: No encontré @app.post('/v1/agent/plan') en brain_server.py para renombrar.")

p.write_text(s2, encoding="utf-8")
print("OK: brain_server.py parcheado: POST /v1/agent/plan -> /v1/agent/plan_legacy (evita colisión).")
