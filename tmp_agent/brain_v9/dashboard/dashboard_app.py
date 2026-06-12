from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from tmp_agent.brain_v9.dashboard.dashboard_routes import router

APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"

app = FastAPI(title="Brain Persistent Autonomy Dashboard", version="1.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(STATIC_ROOT)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "dashboard": "brain_persistent_autonomy", "port": 8092})
