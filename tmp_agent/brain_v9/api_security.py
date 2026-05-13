"""
Runtime API security helpers.

Policy:
- localhost and test clients are trusted for operator routes
- non-local mutating requests require X-Brain-Token when BRAIN_ADMIN_TOKEN is set
- if BRAIN_ADMIN_TOKEN is not configured, non-local mutating requests are denied
"""
from __future__ import annotations

import os
from hmac import compare_digest
from typing import Optional

from fastapi import Header, HTTPException, Request, status


_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _client_host(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return ""
    return str(client.host).split("%", 1)[0].lower()


def is_local_request(request: Request) -> bool:
    return _client_host(request) in _LOCAL_CLIENT_HOSTS


async def require_operator_access(
    request: Request,
    x_brain_token: Optional[str] = Header(default=None, alias="X-Brain-Token"),
) -> None:
    if is_local_request(request):
        return

    expected = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
    if expected and x_brain_token and compare_digest(x_brain_token, expected):
        return

    detail = (
        "Operator access required for non-local requests. Provide X-Brain-Token."
        if expected
        else "Operator access required for non-local requests. Configure BRAIN_ADMIN_TOKEN or use localhost."
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
