import os
import sys
import json
import time
import subprocess
import re

FAST_MODEL_DEFAULT = "llama3.1:8b"
QUALITY_MODEL_DEFAULT = "qwen2.5:14b"

def detect_domain(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ["rsi", "bollinger", "options", "opciones", "quantconnect", "lean", "ibkr", "trading", "backtest"]):
        return "TRADING"
    if any(k in t for k in ["fdot", "cei", "inspection", "concrete", "losa", "barrier", "spec", "standard plans"]):
        return "CEI"
    if any(k in t for k in ["python", "powershell", "uvicorn", "fastapi", "bug", "error", "stack trace", "code", "código", "json"]):
        return "CODE"
    return "GENERAL"

def _select_auto_model(domain: str, user_input: str) -> str:
    # AUTO simple y robusto
    # Dominios "pesados" -> 14b, resto -> 8b
    if domain in ["TRADING", "CEI", "CODE"]:
        return QUALITY_MODEL_DEFAULT
    # Si el prompt es largo, también sube a 14b
    if len(user_input) >= 700:
        return QUALITY_MODEL_DEFAULT
    return FAST_MODEL_DEFAULT

def choose_model(domain: str, user_input: str) -> str:
    env_model = (os.getenv("BRAIN_OLLAMA_MODEL") or "").strip()

    # Si no hay env, usa reglas por dominio
    if not env_model:
        return _select_auto_model(domain, user_input)

    # AUTO explícito
    if env_model.lower() == "auto":
        return _select_auto_model(domain, user_input)

    # Si es un modelo real, forza
    return env_model

def ask_ollama(model: str, prompt: str, timeout_s: int = 180):
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
    # argv o stdin
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
            "error": "NO_INPUT"
        }, ensure_ascii=False))
        return

    wants_json = ("solo json" in user_input.lower()) or user_input.strip().lower().startswith("json:")

    domain = detect_domain(user_input)
    model_used = choose_model(domain, user_input)

    env_model = (os.getenv("BRAIN_OLLAMA_MODEL") or "").strip()
    model_source = "env" if env_model else "router"

    t0 = time.time()

    prompt = (
        "Eres Brain Lab. Responde en español, claro y directo.\n"
        "Si el usuario pide SOLO JSON, devuelve un objeto JSON válido y nada más.\n\n"
        "[USER]\n"
        f"{user_input}\n"
    )

    out, err = ask_ollama(model_used, prompt, timeout_s=180)
    latency_ms = int((time.time() - t0) * 1000)

    if not out:
        print(json.dumps({
            "domain": domain,
            "model_used": model_used,
            "model_source": model_source,
            "mode": "ollama",
            "latency_ms": latency_ms,
            "answer": "",
            "error": "EMPTY_MODEL_OUTPUT",
            "stderr": (err[:800] if err else "")
        }, ensure_ascii=False))
        return

    # JSON determinístico {domain,message}
    if wants_json:
        parsed = try_parse_json(out)
        if isinstance(parsed, dict):
            msg = parsed.get("message") or parsed.get("saludo") or parsed.get("answer") or out
            out = json.dumps({"domain": domain, "message": str(msg).strip()}, ensure_ascii=False)
        else:
            out = json.dumps({"domain": domain, "message": out.strip()}, ensure_ascii=False)

    parsed2 = try_parse_json(out)
    if isinstance(parsed2, dict) and ("answer" in parsed2 or "message" in parsed2):
        ans = parsed2.get("answer") or parsed2.get("message") or json.dumps(parsed2, ensure_ascii=False)
        print(json.dumps({
            "domain": parsed2.get("domain", domain),
            "model_used": model_used,
            "model_source": model_source,
            "mode": "ollama_json" if wants_json else "ollama_text",
            "latency_ms": latency_ms,
            "answer": str(ans).strip(),
            "error": None
        }, ensure_ascii=False))
        return

    print(json.dumps({
        "domain": domain,
        "model_used": model_used,
        "model_source": model_source,
        "mode": "ollama_json" if wants_json else "ollama_text",
        "latency_ms": latency_ms,
        "answer": out,
        "error": None,
        "stderr": (err[:800] if err else "")
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()