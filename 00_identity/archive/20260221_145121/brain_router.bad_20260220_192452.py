import os
import re
import sys
import json
import time
import subprocess
from typing import Tuple

# ==========================
# CONFIG
# ==========================
DEFAULT_QUALITY_MODEL = "qwen2.5:14b"
DEFAULT_FAST_MODEL = "llama3.1:8b"

# Env overrides
ENV_MODEL = "BRAIN_OLLAMA_MODEL"          # si existe -> manda siempre
ENV_MODE = "BRAIN_MODE"                   # FAST | QUALITY | AUTO
ENV_FAST_MODEL = "BRAIN_OLLAMA_MODEL_FAST"
ENV_QUALITY_MODEL = "BRAIN_OLLAMA_MODEL_QUALITY"

TIMEOUT_SECONDS = int(os.getenv("BRAIN_OLLAMA_TIMEOUT", "180"))

DOMAINS = ("TRADING", "CEI", "CODE", "AI", "GENERAL")


# ==========================
# DOMAIN + MODE DETECTION
# ==========================
def _extract_last_user(prompt: str) -> str:
    """
    Desde el prompt tipo:
      [USER] ... [ASSISTANT] ... [USER] ...
    extrae el último bloque [USER].
    Si no encuentra tags, usa el prompt completo.
    """
    try:
        matches = re.findall(r"\[USER\]\s*(.*?)(?=\n\[[A-Z]+\]|\Z)", prompt, flags=re.S)
        if matches:
            return matches[-1].strip()
    except Exception:
        pass
    return (prompt or "").strip()


def detect_domain(prompt: str) -> str:
    text = _extract_last_user(prompt).lower()

    # TRADING
    if any(k in text for k in ["quantconnect", "lean", "ibkr", "options", "opciones", "delta", "theta", "iv", "dte", "backtest", "sharpe", "drawdown", "portfolio"]):
        return "TRADING"

    # CEI / FDOT
    if any(k in text for k in ["fdot", "cei", "spec", "standard plans", "asphalt", "concrete", "losa", "slab", "barrier", "joint", "compact", "density", "subgrade"]):
        return "CEI"

    # CODE / DEV
    if any(k in text for k in ["python", "powershell", "fastapi", "uvicorn", "api", "json", "regex", "script", "bug", "error", "stacktrace", "github"]):
        return "CODE"

    # AI / BRAIN LAB
    if any(k in text for k in ["ollama", "llama", "qwen", "rag", "lora", "agent", "memoria", "brain lab", "local ai"]):
        return "AI"

    return "GENERAL"


def detect_mode(prompt: str) -> str:
    """
    Decide modo: FAST | QUALITY | AUTO (default AUTO)
    - Prioridad: env BRAIN_MODE si existe
    - Si el prompt contiene [MODE]=FAST o "modo fast": FAST
    - Si contiene [MODE]=QUALITY o "modo quality": QUALITY
    """
    env_mode = (os.getenv(ENV_MODE) or "").strip().upper()
    if env_mode in ("FAST", "QUALITY", "AUTO"):
        return env_mode

    p = (prompt or "").lower()
    if "mode]=fast" in p or "modo fast" in p or "[mode]=fast" in p or "[mode:fast]" in p:
        return "FAST"
    if "mode]=quality" in p or "modo quality" in p or "[mode]=quality" in p or "[mode:quality]" in p:
        return "QUALITY"

    return "AUTO"


def wants_json_only(prompt: str) -> bool:
    """
    Heurística:
    - si el SYSTEM dice "solo json" / "only json" / "devuelve json" / "output json"
    - o si el último USER empieza con "JSON:" o "json:"
    """
    p = (prompt or "").lower()

    if any(k in p for k in ["solo json", "only json", "devuelve json", "output json", "responde en json", "respuesta en json"]):
        return True

    last_user = _extract_last_user(prompt)
    if last_user.strip().lower().startswith("json:"):
        return True

    return False


# ==========================
# MODEL SELECTION
# ==========================
def choose_model(domain: str, mode: str) -> Tuple[str, str]:
    """
    Retorna (model, source) donde source = env|rule
    Reglas:
      - si existe BRAIN_OLLAMA_MODEL -> manda siempre (env)
      - si mode=FAST -> usa FAST_MODEL
      - si mode=QUALITY -> usa QUALITY_MODEL
      - si AUTO -> por dominio (TRADING/CEI/CODE/AI => quality, GENERAL => fast)
    """
    env_model = (os.getenv(ENV_MODEL) or "").strip()
    if env_model:
        return env_model, "env"

    fast_model = (os.getenv(ENV_FAST_MODEL) or "").strip() or DEFAULT_FAST_MODEL
    quality_model = (os.getenv(ENV_QUALITY_MODEL) or "").strip() or DEFAULT_QUALITY_MODEL

    if mode == "FAST":
        return fast_model, "rule"
    if mode == "QUALITY":
        return quality_model, "rule"

    # AUTO
    if domain in ("TRADING", "CEI", "CODE", "AI"):
        return quality_model, "rule"
    return fast_model, "rule"


# ==========================
# OLLAMA CALL
# ==========================
def ask_ollama(model: str, prompt: str) -> str:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=env,
        timeout=TIMEOUT_SECONDS,
    )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if not out:
        raise RuntimeError(f"OLLAMA_EMPTY_OUTPUT: {err[:500]}")
    return out


def _json_instruction(domain: str) -> str:
    allowed = "|".join(DOMAINS)
    return (
        "INSTRUCCION CRITICA:\n"
        "Devuelve SOLO un JSON válido (sin markdown, sin texto extra).\n"
        "Debe ser EXACTAMENTE un objeto JSON con estas claves:\n"
        f'  "domain": uno de {allowed}\n'
        '  "message": string con la respuesta\n'
        "Nada más.\n\n"
        f"Dominio detectado: {domain}\n"
    )


def _try_parse_json(text: str) -> dict:
    text = (text or "").strip()

    # si vino con basura antes/después, intenta aislar el primer objeto {...}
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        text = m.group(0).strip()

    return json.loads(text)


# ==========================
# MAIN
# ==========================
def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "domain": "GENERAL",
            "model_used": None,
            "model_source": None,
            "answer": "",
            "error": "NO_INPUT"
        }, ensure_ascii=False))
        return

    prompt_in = sys.argv[1].strip()
    if not prompt_in:
        print(json.dumps({
            "domain": "GENERAL",
            "model_used": None,
            "model_source": None,
            "answer": "",
            "error": "EMPTY_INPUT"
        }, ensure_ascii=False))
        return

    t0 = time.time()

    domain = detect_domain(prompt_in)
    mode = detect_mode(prompt_in)
    model, source = choose_model(domain, mode)

    json_only = wants_json_only(prompt_in)

    try:
        if json_only:
            prompt = _json_instruction(domain) + "\n" + prompt_in
            raw = ask_ollama(model, prompt)

            try:
                obj = _try_parse_json(raw)
            except Exception:
                # 1 retry: “corrige JSON”
                repair = (
                    _json_instruction(domain)
                    + "\nTu salida anterior NO fue JSON válido. Corrige.\n"
                    + "Devuelve SOLO JSON válido.\n\n"
                    + prompt_in
                )
                raw2 = ask_ollama(model, repair)
                obj = _try_parse_json(raw2)

            answer = json.dumps(obj, ensure_ascii=False)

        else:
            raw = ask_ollama(model, prompt_in)
            answer = raw

        dt_ms = int((time.time() - t0) * 1000)

        print(json.dumps({
            "domain": domain,
            "mode": mode,
            "model_used": model,
            "model_source": source,
            "latency_ms": dt_ms,
            "answer": answer
        }, ensure_ascii=False))

    except Exception as e:
        dt_ms = int((time.time() - t0) * 1000)
        print(json.dumps({
            "domain": domain,
            "mode": mode,
            "model_used": model,
            "model_source": source,
            "latency_ms": dt_ms,
            "answer": "",
            "error": str(e)[:500]
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()