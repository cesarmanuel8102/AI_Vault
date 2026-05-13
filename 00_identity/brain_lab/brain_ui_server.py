import os, json, subprocess, traceback
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.chat_router import brain_reply, new_session_id

ROOT = os.path.dirname(os.path.abspath(__file__))
LAB  = ROOT
SRC  = os.path.join(LAB, "src")
MEM  = os.path.join(LAB, "memory")
KPI  = os.path.join(LAB, "kpi")
UI   = os.path.join(LAB, "ui")

os.makedirs(MEM, exist_ok=True)
os.makedirs(KPI, exist_ok=True)

app = FastAPI(title="Brain Lab UI Server", version="0.2.1-debug")
app.mount("/ui", StaticFiles(directory=UI), name="ui")

class ChatReq(BaseModel):
    message: str
    session_id: str | None = None
    sender: str = "Cesar"
    debug: bool = False

class KpiReq(BaseModel):
    outreach_sent: int = 0
    responses: int = 0
    calls_booked: int = 0
    proposals_sent: int = 0
    deals_closed: int = 0
    revenue_usd: float = 0.0
    cost_usd: float = 0.0

def _count_jsonl(path: str) -> int:
    if not os.path.exists(path): return 0
    n=0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for _ in f: n+=1
    return n

def _ollama_health() -> bool:
    try:
        import urllib.request
        url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
        req = urllib.request.Request(url + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.2) as r:
            return r.status == 200
    except Exception:
        return False

def _run_ps1(ps1_path: str) -> Dict[str, Any]:
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
            capture_output=True, text=True, timeout=90
        )
        out = (cp.stdout or "").strip()
        err = (cp.stderr or "").strip()
        return {"ok": cp.returncode == 0, "stdout": out, "stderr": err, "code": cp.returncode}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}

@app.get("/", response_class=HTMLResponse)
def home():
    p = os.path.join(UI, "index.html")
    with open(p, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat() + "Z", "version": app.version}

@app.get("/api/status")
def status():
    ethics_ok = os.path.exists(os.path.join(SRC, "ethics_kernel.py"))
    planner_ok = os.path.exists(os.path.join(SRC, "autonomy_planner.py"))
    kpi_entries = _count_jsonl(os.path.join(KPI, "kpi_daily.jsonl"))
    ollama = _ollama_health()
    return {
        "ts": datetime.utcnow().isoformat() + "Z",
        "ethics": "ok" if ethics_ok else "missing",
        "planner": "ok" if planner_ok else "missing",
        "kpi_entries": kpi_entries,
        "ollama": "ok" if ollama else "off",
        "server_version": app.version
    }

def tool_status():
    return status()

def tool_plan14d():
    ps1 = os.path.join(LAB, "run_generate_and_plan_14d.ps1")
    if not os.path.exists(ps1):
        return "missing run_generate_and_plan_14d.ps1"
    r = _run_ps1(ps1)
    if not r["ok"]:
        return "ERROR:\n" + (r["stderr"] or r["stdout"])
    return r["stdout"]

def tool_outreach():
    ps1 = os.path.join(LAB, "generate_outreach_assets.ps1")
    if not os.path.exists(ps1):
        return "missing generate_outreach_assets.ps1"
    r = _run_ps1(ps1)
    if not r["ok"]:
        return "ERROR:\n" + (r["stderr"] or r["stdout"])
    return r["stdout"] or "OK"

def tool_kpi(payload: dict):
    path = os.path.join(KPI, "kpi_daily.jsonl")
    entry = {"ts": datetime.utcnow().isoformat()+"Z", **payload}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

@app.post("/api/chat")
def chat(req: ChatReq):
    sid = req.session_id or new_session_id()
    tools = {"status": tool_status, "plan14d": tool_plan14d, "outreach": tool_outreach, "kpi": tool_kpi}

    debug_info = {}
    if req.debug:
        debug_info = {
            "OLLAMA_URL_env": os.environ.get("OLLAMA_URL"),
            "OLLAMA_MODEL_env": os.environ.get("OLLAMA_MODEL"),
            "server_version": app.version,
        }

    try:
        reply = brain_reply(req.message, tools=tools, session_id=sid, sender=req.sender)
    except Exception as e:
        tb = traceback.format_exc()
        reply = f"[SERVER ERROR] {e}\n{tb}"
        if req.debug:
            debug_info["exception"] = str(e)
            debug_info["traceback"] = tb

    if req.debug:
        return {"ok": True, "session_id": sid, "reply": reply, "debug": debug_info}
    return {"ok": True, "session_id": sid, "reply": reply}
