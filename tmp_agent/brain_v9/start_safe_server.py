"""
Launcher seguro para Brain V9 en Windows.

Usa WindowsSelectorEventLoopPolicy para evitar fallos intermitentes del
ProactorEventLoop con sockets locales de uvicorn.
"""
import asyncio
import os
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ.setdefault("BRAIN_SAFE_MODE", "true")
os.environ.setdefault("BRAIN_START_AUTONOMY", "false")
os.environ.setdefault("BRAIN_START_PROACTIVE", "false")
os.environ.setdefault("BRAIN_START_SELF_DIAGNOSTIC", "false")
os.environ.setdefault("BRAIN_START_QC_LIVE_MONITOR", "false")
os.environ.setdefault("BRAIN_WARMUP_MODEL", "false")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

uvicorn.run(
    "brain_v9.main:app",
    host=os.getenv("BRAIN_HOST", "127.0.0.1"),
    port=int(os.getenv("BRAIN_PORT", "8090")),
    log_level=os.getenv("BRAIN_LOG_LEVEL", "info"),
    reload=False,
)
