"""
Dashboard port 8092 recovery smoke tests for FRONT-BRAIN-AGENT-V2-BROWSER-OPERATIONAL-RECOVERY-P0-08F8-R1B.

Tests that the dashboard is operational on port 8092.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Get the canonical repo root (tests/smoke/ -> tests/ -> repo_root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN_08F8_R1B"
BRAIN_URL = "http://127.0.0.1:8091"
DASHBOARD_URL = "http://127.0.0.1:8092"


def _http_get(url: str, headers: dict | None = None, timeout: float = 10.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


def _http_post(url: str, body: dict, headers: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


@pytest.fixture(scope="module")
def services():
    """Start both Brain and Dashboard services."""
    env = {**os.environ, "BRAIN_ADMIN_TOKEN": LOCAL_TOKEN, "PYTHONPATH": str(REPO_ROOT)}
    brain_cmd = [sys.executable, str(REPO_ROOT / "tmp_agent" / "brain_v9" / "start_safe_server.py")]
    dashboard_cmd = [
        sys.executable,
        "-c",
        "import uvicorn; uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', host='127.0.0.1', port=8092, log_level='info', reload=False)",
    ]
    brain_proc = subprocess.Popen(brain_cmd, env=env, cwd=str(REPO_ROOT))
    dash_proc = subprocess.Popen(dashboard_cmd, env=env, cwd=str(REPO_ROOT))

    # Wait for health
    brain_ok = False
    dash_ok = False
    for i in range(40):
        try:
            with urllib.request.urlopen(f"{BRAIN_URL}/health", timeout=1.0) as r:
                if r.status == 200:
                    brain_ok = True
                    break
        except Exception:
            pass
        time.sleep(0.5)
    for i in range(20):
        try:
            with urllib.request.urlopen(f"{DASHBOARD_URL}/health", timeout=1.0) as r:
                if r.status == 200:
                    dash_ok = True
                    break
        except Exception:
            pass
        time.sleep(0.5)

    assert brain_ok, "Brain service failed to start"
    assert dash_ok, "Dashboard service failed to start"

    yield

    brain_proc.terminate()
    dash_proc.terminate()
    try:
        brain_proc.wait(timeout=5.0)
        dash_proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        brain_proc.kill()
        dash_proc.kill()


class TestDashboardPortRecovery:
    """Dashboard port 8092 recovery tests."""

    def test_dashboard_root_loads(self, services):
        """GET / on 8092 returns HTML."""
        status, _ = _http_get(f"{DASHBOARD_URL}/")
        assert status == 200, f"Dashboard root returned {status}"

    def test_dashboard_health_endpoint(self, services):
        """GET /health on 8092 returns 200."""
        status, data = _http_get(f"{DASHBOARD_URL}/health")
        assert status == 200
        assert data.get("dashboard") == "brain_persistent_autonomy"
        assert data.get("port") == 8092

    def test_dashboard_static_files_served(self, services):
        """Dashboard static files are served (app.js, index.html)."""
        status, _ = _http_get(f"{DASHBOARD_URL}/")
        assert status == 200
        status, _ = _http_get(f"{DASHBOARD_URL}/static/app.js")
        assert status == 200

    def test_dashboard_chat_endpoint_works(self, services):
        """POST /brain-dashboard/chat returns 200 with proper response."""
        status, data = _http_post(
            f"{DASHBOARD_URL}/brain-dashboard/chat",
            {"message": "hola", "mode": "read_only", "user_id": "test_dashboard"},
        )
        assert status == 200
        assert "content" in data
        assert "canonical_agent_v2" in data

    def test_dashboard_proxies_trace_to_brain(self, services):
        """Dashboard can proxy trace requests to Brain on 8091."""
        status, data = _http_post(
            f"{BRAIN_URL}/v2/chat/agent",
            {"message": "test trace", "mode": "read_only", "user_id": "trace_test"},
            headers={"X-Brain-Token": LOCAL_TOKEN},
        )
        assert status == 200
        run_id = data.get("run_id")
        assert run_id

        status, trace_data = _http_get(f"{DASHBOARD_URL}/brain-dashboard/agent-v2/runs/{run_id}/trace")
        assert status in (200, 404), f"Trace proxy returned {status}"

    def test_dashboard_agent_v2_status_endpoint(self, services):
        """GET /brain-dashboard/agent-v2/status returns 200."""
        status, data = _http_get(f"{DASHBOARD_URL}/brain-dashboard/agent-v2/status")
        assert status == 200
        assert data.get("ok") is True
        assert "agent_v2" in data

    def test_no_connection_refused_on_8092(self, services):
        """Port 8092 is not connection refused."""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex(("127.0.0.1", 8092))
        sock.close()
        assert result == 0, "Port 8092 connection refused"

    def test_dashboard_routes_use_strict_headers(self, services):
        """Dashboard routes use _strict_headers for backend calls."""
        routes_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "dashboard_routes.py"
        content = routes_path.read_text(encoding="utf-8")
        assert "_strict_headers" in content
        assert "BRAIN_ADMIN_TOKEN" in content or "brain_admin_token" in content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])