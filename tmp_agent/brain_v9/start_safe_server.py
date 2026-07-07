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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ.setdefault("BRAIN_SAFE_MODE", "false")
os.environ.setdefault("BRAIN_START_AUTONOMY", "false")
os.environ.setdefault("BRAIN_START_PROACTIVE", "false")
os.environ.setdefault("BRAIN_START_SELF_DIAGNOSTIC", "false")
os.environ.setdefault("BRAIN_START_QC_LIVE_MONITOR", "false")
os.environ.setdefault("BRAIN_WARMUP_MODEL", "false")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

if not os.getenv("BRAIN_ADMIN_TOKEN"):
    print(
        "[brain_v9] WARNING: BRAIN_ADMIN_TOKEN is not set. Strict operator routes "
        "(/v2/chat/agent, /v2/agent/*) will return 403 and the 8092 dashboard proxy "
        "(/brain-dashboard/chat) will report auth_governance errors. "
        "Set BRAIN_ADMIN_TOKEN in your local environment before starting the dashboard."
    )

uvicorn.run(
    "brain_v9.main:app",
    host=os.getenv("BRAIN_HOST", "127.0.0.1"),
    port=8091,
    log_level=os.getenv("BRAIN_LOG_LEVEL", "info"),
    reload=False,
)
