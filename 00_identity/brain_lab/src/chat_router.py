import os, json, uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM  = os.path.join(ROOT, "memory")
CHAT = os.path.join(MEM, "chat_sessions")
GOV  = os.path.join(ROOT, "governance")
CFG_PATH = os.path.join(GOV, "llm_config.json")

os.makedirs(CHAT, exist_ok=True)

def now(): return datetime.utcnow().isoformat()+"Z"

def new_session_id():
    return "sess_" + uuid.uuid4().hex[:10]

def _load_cfg():
    cfg = {
        "ollama_url": "http://127.0.0.1:11434",
        "default_model": "qwen2.5:14b",
        "temperature": 0.2,
        "max_chars": 2200
    }
    try:
        if os.path.exists(CFG_PATH):
            with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
                cfg.update(json.load(f))
    except:
        pass
    return cfg

def _append(session_id, role, content, meta=None):
    path = os.path.join(CHAT, f"{session_id}.jsonl")
    rec = {"ts": now(), "role": role, "content": content, "meta": meta or {}}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def _read_tail(session_id, n=24):
    path = os.path.join(CHAT, f"{session_id}.jsonl")
    if not os.path.exists(path): return []
    lines=[]
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip(): lines.append(line)
    tail = lines[-n:]
    out=[]
    for line in tail:
        try: out.append(json.loads(line))
        except: pass
    return out

def intent(message: str):
    m = (message or "").strip().lower()
    if m in ("status","estado","health"): return "status"
    if m in ("diag","diagnostico","diagnóstico"): return "diag"
    if m in ("run_day","runday","run today","hoy","operar hoy"): return "run_day"
    if "plan14d" in m or "plan 14" in m: return "plan14d"
    if "outreach" in m or "emails" in m or "correo" in m or "generate outreach" in m: return "outreach"
    if m.startswith("kpi "): return "kpi"
    return "chat"

def parse_kpi(message: str):
    parts = (message or "").strip().split()
    if len(parts) != 8: return None
    try:
        return {
            "outreach_sent": int(parts[1]),
            "responses": int(parts[2]),
            "calls_booked": int(parts[3]),
            "proposals_sent": int(parts[4]),
            "deals_closed": int(parts[5]),
            "revenue_usd": float(parts[6]),
            "cost_usd": float(parts[7]),
        }
    except:
        return None

def _history_text(hist):
    out=[]
    for h in hist[-16:]:
        role = h.get("role","")
        c = (h.get("content","") or "").strip()
        if role and c:
            if len(c) > 600: c = c[:600] + ""
            out.append(f"{role.upper()}: {c}")
    return "\n".join(out)

def try_ollama(url):
    try:
        import urllib.request
        req = urllib.request.Request(url + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.8) as r:
            return r.status == 200, None
    except Exception as e:
        return False, str(e)

def ollama_generate(url, model, prompt, temperature=0.2):
    import urllib.request, json as _json
    endpoint = url + "/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": float(temperature)}}
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = _json.loads(r.read().decode("utf-8", errors="ignore"))
    return (res.get("response","") or "").strip()

def brain_reply(message: str, tools: dict, session_id: str, sender="Cesar"):
    cfg = _load_cfg()
    ollama_url = os.environ.get("OLLAMA_URL", cfg["ollama_url"])
    model = os.environ.get("OLLAMA_MODEL", cfg["default_model"])
    temperature = cfg.get("temperature", 0.2)
    max_chars = int(cfg.get("max_chars", 2200))

    _append(session_id, "user", message)

    it = intent(message)

    if it == "status":
        s = tools["status"]()
        reply = json.dumps(s, ensure_ascii=False, indent=2)
        _append(session_id, "assistant", reply, {"intent":"status"})
        return reply

    if it == "diag":
        ok, err = try_ollama(ollama_url)
        lab_state = tools["status"]()
        diag = {
            "ts": now(),
            "intent": it,
            "server_state": lab_state,
            "cfg_path": CFG_PATH,
            "cfg_loaded": cfg,
            "OLLAMA_URL_used": ollama_url,
            "OLLAMA_MODEL_used": model,
            "ollama_tags_ok": ok,
            "ollama_tags_err": err
        }
        reply = json.dumps(diag, ensure_ascii=False, indent=2)
        _append(session_id, "assistant", reply, {"intent":"diag"})
        return reply

    if it == "plan14d":
        raw = tools["plan14d"]()
        reply = "Plan 14 días generado.\n\n" + (raw[:4000] if isinstance(raw,str) else str(raw)[:4000])
        _append(session_id, "assistant", reply, {"intent":"plan14d"})
        return reply

    if it == "outreach":
        raw = tools["outreach"]()
        reply = "Outreach generado/actualizado.\n\n" + (raw[:2000] if isinstance(raw,str) else str(raw)[:2000])
        _append(session_id, "assistant", reply, {"intent":"outreach"})
        return reply

    if it == "kpi":
        k = parse_kpi(message)
        if not k:
            reply = "Uso: kpi outreach responses calls proposals deals revenue cost\nEj: kpi 5 1 0 0 0 0 0"
            _append(session_id, "assistant", reply, {"intent":"kpi"})
            return reply
        tools["kpi"](k)
        reply = "KPI registrado."
        _append(session_id, "assistant", reply, {"intent":"kpi","kpi":k})
        return reply

    if it == "run_day":
        # Operación diaria mínima:
        # 1) Genera plan 14d (para escoger idea top) 2) Genera assets de outreach 3) Devuelve checklist operativo
        plan = tools["plan14d"]()
        out  = tools["outreach"]()
        reply = (
            "RUN_DAY (operación diaria) \n\n"
            "1) Plan actualizado (top ideas + acciones)\n"
            "2) Assets de outreach generados\n\n"
            "Ahora ejecuta HOY (2 horas):\n"
            "A) Abrir carpeta memory\\outreach y usar 1 plantilla\n"
            "B) Construir 10-20 leads 1:1 manual (público)  NO spam\n"
            "C) Enviar 3-5 mensajes personalizados con opt-out\n"
            "D) Registrar KPI al final del día: kpi sent responses calls proposals deals revenue cost\n\n"
            "Salida técnica:\n"
            f"- plan14d: {('OK' if plan else 'ERROR')}\n"
            f"- outreach: {('OK' if out else 'ERROR')}\n"
        )
        _append(session_id, "assistant", reply, {"intent":"run_day"})
        return reply

    # Chat natural (LLM) con disciplina
    lab_state = tools["status"]()
    hist = _read_tail(session_id, 24)

    system = (
        "ROL: Eres el Cerebro del Brain Lab (ente operativo autónomo). "
        "OBJETIVO: generar dinero y construir activos/procesos escalables en ciclos de 14/30 días. "
        "REGLAS DURAS: legalidad/ética estricta. Nada de spam, fraude, scraping ilegal, ni violación de TOS. "
        "CUALQUIER acción de dinero/ads/trading/cuentas => REVIEW (no ejecutar). "
        "SALIDA: concreta, con pasos numerados y decisión clara. "
        "No pidas que el humano invente ideas: tú propones y decides. "
        "Responde en español."
    )

    context = (
        f"Estado: ethics={lab_state.get('ethics')} planner={lab_state.get('planner')} "
        f"kpi_entries={lab_state.get('kpi_entries')} ollama={lab_state.get('ollama')}\n"
        "Historial:\n" + _history_text(hist) + "\n"
        f"Usuario: {message}\n"
    )

    ok, err = try_ollama(ollama_url)
    if ok:
        prompt = system + "\n\n" + context
        try:
            reply = ollama_generate(ollama_url, model, prompt, temperature=temperature)
            reply = reply[:max_chars]
        except Exception as e:
            reply = (
                "FALLBACK: Ollama generate falló.\n"
                f"OLLAMA_URL={ollama_url}\nMODEL={model}\nERROR={e}\n"
                "Acción: intenta 'diag'."
            )
    else:
        reply = (
            "FALLBACK: Ollama no accesible desde el router.\n"
            f"OLLAMA_URL={ollama_url}\nMODEL={model}\nERR={err}\n"
            "Acción: intenta 'diag'."
        )

    _append(session_id, "assistant", reply, {"intent":"chat","model":model,"ollama_ok":ok})
    return reply
