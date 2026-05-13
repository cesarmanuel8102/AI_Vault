from fastapi import FastAPI
from .config import settings
from .logging_setup import configure_logging
from .routers.agent_proxy import router as agent_proxy_router

configure_logging()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

@app.get("/healthz")
def healthz():
    return {"ok": True, "app": settings.app_name}

app.include_router(agent_proxy_router, prefix="/v1")