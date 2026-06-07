"""Smoke test for runtime dashboard and chat recovery.

Verifies Brain V9 server starts, health responds, dashboard serves.
Does not require server to be pre-running (starts it if needed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\AI_VAULT")

REPO_ROOT = Path(r"C:\AI_VAULT")
SERVER_DIR = REPO_ROOT / "tmp_agent" / "brain_v9"
HEALTH_URL = "http://127.0.0.1:8090/health"
DASHBOARD_URL = "http://127.0.0.1:8090/dashboard"
CHAT_URL = "http://127.0.0.1:8090/chat"
DOCS_URL = "http://127.0.0.1:8090/docs"


def _probe(url: str, timeout: float = 5.0) -> int:
    try:
        import urllib.request
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except Exception:
        return 0


def _start_server() -> subprocess.Popen:
    env = {
        "BRAIN_HOST": "127.0.0.1",
        "BRAIN_PORT": "8090",
        "BRAIN_SAFE_MODE": "true",
        "BRAIN_START_AUTONOMY": "false",
        "PATH": os.environ.get("PATH", ""),
    }
    proc = subprocess.Popen(
        [sys.executable, "start_safe_server.py"],
        cwd=str(SERVER_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, **env},
    )
    # Wait for health
    for _ in range(60):
        time.sleep(1)
        code = _probe(HEALTH_URL, timeout=2)
        if code == 200:
            break
    return proc


def test_health_responds():
    code = _probe(HEALTH_URL, timeout=2)
    if code != 200:
        proc = _start_server()
        try:
            code = _probe(HEALTH_URL, timeout=5)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    assert code == 200, f"Health endpoint returned {code}"


def test_dashboard_responds():
    proc = None
    try:
        code = _probe(DASHBOARD_URL, timeout=2)
        if code != 200:
            proc = _start_server()
            code = _probe(DASHBOARD_URL, timeout=5)
        assert code in (200, 307), f"Dashboard returned {code}"
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)


def _probe_post(url: str, timeout: float = 5.0) -> int:
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, method="POST", data=b'{}',
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def test_chat_endpoint_exists():
    proc = None
    try:
        code = _probe_post(CHAT_URL, timeout=2)
        if code == 0:
            proc = _start_server()
            for _ in range(20):
                time.sleep(0.5)
                code = _probe_post(CHAT_URL, timeout=2)
                if code in (405, 422, 200):
                    break
        assert code in (405, 422, 200), f"Chat endpoint returned {code}"
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)


def test_docs_endpoint_exists():
    proc = None
    try:
        code = _probe(DOCS_URL, timeout=2)
        if code != 200:
            proc = _start_server()
            code = _probe(DOCS_URL, timeout=5)
        assert code == 200, f"Docs endpoint returned {code}"
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)


def test_no_external_services_required():
    # Verify we can import main without external services
    import sys
    sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))
    sys.path.insert(0, str(REPO_ROOT))
    from brain_v9.main import app
    assert app is not None


def test_import_no_error():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))
    sys.path.insert(0, str(REPO_ROOT))
    from brain_v9.main import app
    # Should not raise
    assert True
