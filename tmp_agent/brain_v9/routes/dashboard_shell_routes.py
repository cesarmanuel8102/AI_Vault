"""Dashboard shell routes split from main.py.

Only serves the existing dashboard HTML shell. It does not start or control
dashboard runtime processes.
"""
from __future__ import annotations

import os
from typing import Callable

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard-shell"])
_dashboard_html_provider: Callable[[], str] = lambda: ""


def configure_dashboard_html_path(provider: Callable[[], str]) -> None:
    global _dashboard_html_provider
    _dashboard_html_provider = provider


@router.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    """Serve the professional monitoring dashboard."""
    dashboard_html = _dashboard_html_provider()
    if os.path.exists(dashboard_html):
        with open(dashboard_html, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


@router.get("/dashboard-v2", include_in_schema=False)
async def serve_dashboard_v2():
    """Compatibility alias for the Command Center v2 dashboard."""
    return await serve_dashboard()
