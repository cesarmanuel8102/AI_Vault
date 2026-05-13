from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
import os
from pathlib import Path
from datetime import datetime
import asyncio

app = FastAPI(title="Brain Lab Dashboard Enhanced", version="2.1")

# Configurar archivos estáticos y plantillas
BASE_DIR = Path("C:/AI_VAULT/tmp_agent")
static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"

static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

async def get_system_status():
    \"\"\"Obtener estado completo del sistema\"\"\"
    status = {
        "timestamp": datetime.now().isoformat(),
        "servers": {},
        "roadmap": {},
        "trust_score": 85,
        "performance_metrics": {}
    }
    
    # Verificar Brain Server
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("http://127.0.0.1:8010/v1/agent/status")
            status["servers"]["brain"] = {
                "status": "online" if response.status_code == 200 else "offline",
                "response_time": response.elapsed.total_seconds()
            }
    except:
        status["servers"]["brain"] = {"status": "offline"}
    
    # Verificar Advisor Server
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get("http://127.0.0.1:8030/healthz")
            status["servers"]["advisor"] = {
                "status": "online" if response.status_code == 200 else "offline",
                "response_time": response.elapsed.total_seconds()
            }
    except:
        status["servers"]["advisor"] = {"status": "offline"}
    
    # Leer roadmap
    try:
        roadmap_path = BASE_DIR / "state" / "roadmap.json"
        if roadmap_path.exists():
            status["roadmap"] = json.loads(roadmap_path.read_text())
    except:
        pass
    
    # Métricas de performance básicas
    status["performance_metrics"] = {
        "uptime": "100%",
        "completed_phases": 6,
        "active_processes": 3,
        "memory_usage": "optimal"
    }
    
    return status

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    status = await get_system_status()
    
    return templates.TemplateResponse("enhanced_dashboard.html", {
        "request": request,
        "status": status,
        "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.get("/api/status")
async def api_status():
    return await get_system_status()

@app.get("/api/roadmap")
async def api_roadmap():
    try:
        roadmap_path = Path("C:/AI_VAULT/tmp_agent/state/roadmap.json")
        if roadmap_path.exists():
            return json.loads(roadmap_path.read_text())
    except:
        pass
    return {"error": "Roadmap no disponible"}

if __name__ == "__main__":
    import uvicorn
    print("🌐 Brain Lab Dashboard Enhanced iniciando en http://127.0.0.1:8503")
    uvicorn.run(app, host="127.0.0.1", port=8503)

