import json, sys, time, subprocess
from pathlib import Path

OUT = Path("tmp_agent/advanced_brain_capability_evidence")
cases = [
    ("adv_q11_instalacion_segura_simulada", "Si faltara una herramienta como pytest, httpx o ripgrep, como la instalarias de forma segura en Windows? No ejecutes instalacion real. Da comandos PowerShell con dry-run/validacion previa y criterios de rollback."),
    ("adv_q12_ingesta_curada", "Explica el estado de la ingesta de informacion externa curada: fuentes, medida de calidad, promocion, ledger, dry-run, que esta listo y que falta."),
    ("adv_q13_github_api", "Explica si tienes integracion con GitHub o fuentes externas por API, que puedes hacer hoy, que no puedes hacer, y que faltaria para hacerlo confiable."),
]

for name, message in cases:
    fpath = OUT / f"{name}.txt"
    if fpath.exists():
        print(f"SKIP={name}")
        continue
    print(f"EXEC={name}")
    body = json.dumps({"message": message, "model_priority": "auto"})
    start = time.time()
    try:
        proc = subprocess.run(
            ["curl", "--max-time", "35", "-s", "-i", "-X", "POST", "http://127.0.0.1:8090/chat", "-H", "Content-Type: application/json", "-d", body],
            capture_output=True, text=True, timeout=40
        )
        status = "TIMEOUT" if proc.returncode == 28 else ("OK" if "HTTP/1.1 200" in proc.stdout else f"RC={proc.returncode}")
        fpath.write_text(f"STATUS={status}\n\n{proc.stdout}\n{proc.stderr}", encoding="utf-8", errors="replace")
    except Exception as e:
        fpath.write_text(f"EXCEPTION={type(e).__name__}: {e}", encoding="utf-8")
        status = "EXCEPTION"
    elapsed = round(time.time() - start, 1)
    print(f"DONE={name} status={status} elapsed={elapsed}s")

print("BATCH_DONE")
