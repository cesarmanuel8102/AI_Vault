"""Local launcher for the Brain Dashboard on 8092 with operator token.

Reads BRAIN_ADMIN_TOKEN from the environment. Does NOT hardcode any token.
Run from C:\AI_VAULT_CANONICAL with PYTHONPATH=C:\AI_VAULT_CANONICAL.
"""
import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if not os.getenv("BRAIN_ADMIN_TOKEN"):
    print("[dashboard_8092] WARNING: BRAIN_ADMIN_TOKEN not set; /brain-dashboard/chat proxy to 8091 will get 403.")

uvicorn.run(
    "tmp_agent.brain_v9.dashboard.dashboard_app:app",
    host="127.0.0.1",
    port=8092,
    log_level=os.getenv("BRAIN_LOG_LEVEL", "info"),
    reload=False,
)