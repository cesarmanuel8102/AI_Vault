"""
Launcher full para Brain V9.

Activa capas de autonomia/automejora y modo GOD autenticado por chat.
Uso: python C:/AI_VAULT/tmp_agent/brain_v9/start_full_server.py
"""
import asyncio
import os
import sys
from pathlib import Path

import uvicorn


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["BRAIN_SAFE_MODE"] = "false"
os.environ["BRAIN_START_AUTONOMY"] = "true"
os.environ["BRAIN_START_PROACTIVE"] = "true"
os.environ["BRAIN_START_SELF_DIAGNOSTIC"] = "true"
os.environ["BRAIN_START_QC_LIVE_MONITOR"] = "true"
os.environ["BRAIN_WARMUP_MODEL"] = "true"
os.environ["BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS"] = "true"
# No activar ciclo financiero automático: queda bloqueado hasta que use solo
# fuentes verificables end-to-end y no interfiera con backtests/live.
os.environ["BRAIN_ENABLE_FINANCIAL_AUTOCYCLE"] = "false"

uvicorn.run(
    "brain_v9.main:app",
    host=os.getenv("BRAIN_HOST", "127.0.0.1"),
    port=int(os.getenv("BRAIN_PORT", "8090")),
    log_level=os.getenv("BRAIN_LOG_LEVEL", "info"),
    reload=False,
)
