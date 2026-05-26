"""Microdiagnosis for diagnosis_timeout_guard."""
import json, subprocess, time
from pathlib import Path

OUT = Path("C:/AI_VAULT/tmp_agent/agent_non_blocking_evidence/diagnosis_micro")
OUT.mkdir(parents=True, exist_ok=True)

cases = [
    ("diagnosis_exact_original",
     "Diagnostica este error de Python: UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d. Explica causa y solucion robusta en Windows.",
     "auto"),
    ("diagnosis_simplified_ascii",
     "Diagnostica un UnicodeDecodeError en Python en Windows por encoding cp1252. Da causa y solucion robusta.",
     "auto"),
    ("diagnosis_force_chat",
     "Diagnostica un UnicodeDecodeError en Python en Windows por encoding cp1252. Da causa y solucion robusta.",
     "chat"),
    ("diagnosis_force_code",
     "Diagnostica este error de Python y da un ejemplo de fix: UnicodeDecodeError charmap codec can't decode byte. Usa Python.",
     "auto"),
]

for name, message, priority in cases:
    fpath = OUT / f"{name}.txt"
    print(f"EXEC={name}")
    body = json.dumps({"message": message, "model_priority": priority})

    lines = [
        f"START_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"NAME={name}", f"PRIORITY={priority}", "CURL_MAX_TIME=90", "",
    ]

    try:
        proc = subprocess.run(
            ["curl", "--max-time", "90", "-s", "-i", "-X", "POST",
             "http://127.0.0.1:8090/chat", "-H", "Content-Type: application/json", "-d", body],
            capture_output=True, text=False, timeout=105,
        )
        stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

        lines.append(f"CURL_RC={proc.returncode}")
        if proc.returncode == 0 and "HTTP/1.1 200" in stdout:
            lines.append("STATUS=200")
        elif proc.returncode == 28:
            lines.append("STATUS=EXTERNAL_TIMEOUT")
        elif proc.returncode == 0:
            lines.append("STATUS=CURL_RC_0_NO_HTTP_200")
        else:
            lines.append("STATUS=CURL_ERROR")

        lines += ["", "=== STDOUT ===", stdout, "", "=== STDERR ===", stderr]
    except subprocess.TimeoutExpired:
        lines.append("STATUS=WRAPPER_TIMEOUT")
    except Exception as e:
        lines.append(f"EXCEPTION={type(e).__name__}: {e}")

    lines.append(f"END_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")

    try:
        h = subprocess.run(
            ["curl", "--max-time", "10", "-s", "http://127.0.0.1:8090/health"],
            capture_output=True, text=False, timeout=15,
        )
        health = (h.stdout or b"").decode("utf-8", errors="replace")
        lines += ["", "=== HEALTH_AFTER ===", f"HEALTH_RC={h.returncode}", health]
        if h.returncode != 0 or "healthy" not in health:
            lines.append("STOP_REASON=HEALTH_FAILED")
            fpath.write_text("\n".join(lines), encoding="utf-8", errors="replace")
            print(f"DONE={name} HEALTH_FAILED")
            break
    except Exception as e:
        lines.append(f"HEALTH_EXCEPTION={type(e).__name__}: {e}")
        fpath.write_text("\n".join(lines), encoding="utf-8", errors="replace")
        print(f"DONE={name} HEALTH_EXCEPTION")
        break

    fpath.write_text("\n".join(lines), encoding="utf-8", errors="replace")
    print(f"DONE={name}")

print("DIAGNOSIS_MICRO_COMPLETE")
