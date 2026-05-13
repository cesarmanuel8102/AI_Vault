import os
import sys
import json
import time
import subprocess
import re
from typing import Dict

def detect_domain(text: str) -> str:
    t = (text or "").lower()
    # Heurísticas simples
    if any(k in t for k in ["rsi", "bollinger", "options", "opciones", "quantconnect", "lean", "ibkr", "trading", "backtest"]):
        return "TRADING"
    if any(k in t for k in ["fdot", "cei", "inspection", "concrete", "losa", "barrier", "spec", "standard plans"]):
        return "CEI"
    if any(k in t for k in ["python", "powershell", "uvicorn", "fastapi", "bug", "error", "stack trace", "code", "código"]):
        return "CODE"
    return "GENERAL"

def choose_model(domain: str) -> str:
    # Prioridad: variable de entorno si existe
    env_model = os.getenv("BRAIN_OLLAMA_MODEL")
    if env_model and env_model.strip():
        return env_model.strip()

    # fallback por dominio
    if domain in ["TRADING", "CEI", "CODE"]:
        return "qwen2.5:14b"
    return "llama3.1:8b"

def ask_ollama(model: str, prompt: str, timeout_s: int = 180) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    p = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout_s,
        env=env
    )
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    return out, err

def strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    # elimina ```json ... ``` o ``` ... ```
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def try_parse_json(s: str):
    s2 = strip_code_fences(s)
    try:
        return json.loads(s2)
    except Exception:
        return None

def main():
    user_input = " ".join(sys.argv[1:]).strip()
if not user_input:
    user_input = (sys.stdin.read() or "").strip()
    if not user_input:
        print(json.dumps({
            "domain": "GENERAL",
            "model_used": None,
            "model_source": "router",
            "mode": "router",
            "latency_ms": 0,
            "answer": "",
            "error": "EMPTY_INPUT"
        }, ensure_ascii=False))
        return

    domain = detect_domain(user_input)
    model = choose_model(domain)
    model_source = "env" if (os.getenv("BRAIN_OLLAMA_MODEL") or "").strip() else "router"

    t0 = time.time()

    # IMPORTANTE: aunque el system diga "SOLO JSON", el router no depende de eso.
    # Envuelve el prompt de manera estable.
    prompt = f"""Eres Brain Lab. Responde en español, claro y directo.
Si el usuario pide SOLO JSON, devuelve un objeto JSON válido y nada más.

[USER]
{user_input}
"""

    out, err = ask_ollama(model, prompt, timeout_s=180)
    latency_ms = int((time.time() - t0) * 1000)

    if not out:
        # jamás devolvemos vacío: devolvemos JSON con error y fallback mínimo
        print(json.dumps({
            "domain": domain,
            "model_used": model,
            "model_source": model_source,
            "mode": "ollama",
            "latency_ms": latency_ms,
            "answer": "",
            "error": "EMPTY_MODEL_OUTPUT",
            "stderr": (err[:800] if err else "")
        }, ensure_ascii=False))
        return

    # Si el usuario pidió JSON, intentamos parsearlo, pero si no se puede igual damos answer texto
    parsed = try_parse_json(out)
    if isinstance(parsed, dict) and ("answer" in parsed or "message" in parsed):
        # Normalizamos si el modelo inventa esquema
        ans = parsed.get("answer") or parsed.get("message") or json.dumps(parsed, ensure_ascii=False)
        print(json.dumps({
            "domain": parsed.get("domain", domain),
            "model_used": model,
            "model_source": model_source,
            "mode": "ollama_json",
            "latency_ms": latency_ms,
            "answer": str(ans).strip(),
            "error": None
        }, ensure_ascii=False))
        return

    # default: devolvemos texto tal cual, pero envuelto en JSON estable
    print(json.dumps({
        "domain": domain,
        "model_used": model,
        "model_source": model_source,
        "mode": "ollama_text",
        "latency_ms": latency_ms,
        "answer": out,
        "error": None,
        "stderr": (err[:800] if err else "")
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()