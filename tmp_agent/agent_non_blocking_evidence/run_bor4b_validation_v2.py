"""BOR-4B Runtime Validation v2 — 90s curl timeout."""
import json, subprocess, time
from pathlib import Path

OUT = Path("C:/AI_VAULT/tmp_agent/agent_non_blocking_evidence")
OUT.mkdir(parents=True, exist_ok=True)

cases = [
    ("agent_logs_timeout_guard", "revisa logs", "auto"),
    ("code_review_timeout_guard", "Revisa este codigo y detecta bugs: def load_json(path): import json; return json.loads(open(path).read()). Dame version corregida.", "auto"),
    ("tools_available_timeout_guard", "Lista tus herramientas disponibles y explica cuales puedes ejecutar realmente desde este chat. No inventes.", "auto"),
    ("diagnosis_timeout_guard", "Diagnostica este error de Python: UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d. Explica causa y solucion robusta en Windows.", "auto"),
]

for name, message, priority in cases:
    fpath = OUT / f"{name}.txt"
    print(f"EXEC={name}")

    body = json.dumps({"message": message, "model_priority": priority})
    lines = [
        f"START_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"NAME={name}",
        f"PRIORITY={priority}",
        f"CURL_MAX_TIME=90",
        "",
    ]
    try:
        proc = subprocess.run(
            [
                "curl", "--max-time", "90", "-s", "-i",
                "-X", "POST", "http://127.0.0.1:8090/chat",
                "-H", "Content-Type: application/json",
                "-d", body,
            ],
            capture_output=True, text=True, timeout=105,
        )
        if proc.returncode == 0 and "HTTP/1.1 200" in (proc.stdout or ""):
            lines += ["STATUS=200", f"CURL_RC={proc.returncode}", proc.stdout or ""]
        elif proc.returncode == 28:
            lines += ["STATUS=EXTERNAL_TIMEOUT", "CURL_RC=28"]
        else:
            lines += [f"STATUS=CURL_ERROR", f"CURL_RC={proc.returncode}", proc.stdout or "", proc.stderr or ""]
    except subprocess.TimeoutExpired:
        lines += ["STATUS=WRAPPER_TIMEOUT"]
    except Exception as e:
        lines += [f"EXCEPTION={type(e).__name__}: {e}"]

    lines.append(f"END_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    fpath.write_text("\n".join(lines), encoding="utf-8", errors="replace")
    print(f"DONE={name}")

print("BOR4B_REVALIDATION_COMPLETE_V2")
