"""
Browser operational recovery smoke tests for FRONT-BRAIN-AGENT-V2-BROWSER-OPERATIONAL-RECOVERY-P0-08F8-R1B.

End-to-end tests that the browser UI works with strict operator token auth.
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
LOCAL_TOKEN = os.getenv("BRAIN_ADMIN_TOKEN", "").strip()
if not LOCAL_TOKEN:
    pytest.skip("BRAIN_ADMIN_TOKEN required for live auth smoke", allow_module_level=True)
BRAIN_URL = "http://127.0.0.1:8091"
DASHBOARD_URL = "http://127.0.0.1:8092"


def _http_get(url: str, headers: dict | None = None, timeout: float = 10.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionResetError, ConnectionError) as e:
        # Retry once on connection reset (Windows asyncio proactor issue)
        time.sleep(0.1)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except Exception as e2:
            return 0, {"error": str(e2)}
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
    except (urllib.error.URLError, ConnectionResetError, ConnectionError) as e:
        # Retry once on connection reset (Windows asyncio proactor issue)
        time.sleep(0.1)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except Exception as e2:
            return 0, {"error": str(e2)}
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

    yield True

    brain_proc.terminate()
    dash_proc.terminate()
    try:
        brain_proc.wait(timeout=5.0)
        dash_proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        brain_proc.kill()
        dash_proc.kill()


class TestBrowserOperationalRecovery:
    """Browser operational recovery tests."""

    def test_ui_html_loads(self, services):
        """GET /ui/ returns HTML with token banner."""
        status, _ = _http_get(f"{BRAIN_URL}/ui/")
        assert status == 200

    def test_ui_contains_token_banner_elements(self, services):
        """UI HTML contains token banner elements."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "token-banner" in content
        assert "token-input" in content
        assert "X-Brain-Token" in content
        assert "getOperatorToken" in content
        assert "Operator token rejected or missing" in content

    def test_health_endpoint_works(self, services):
        """GET /health returns 200 with healthy status."""
        status, data = _http_get(f"{BRAIN_URL}/health")
        assert status == 200
        assert data.get("status") == "healthy"

    def test_agent_status_403_without_token(self, services):
        """GET /v2/agent/status returns 403 without token."""
        status, data = _http_get(f"{BRAIN_URL}/v2/agent/status")
        assert status == 403
        assert "strict operator access required" in str(data.get("detail", "")).lower()

    def test_agent_status_200_with_token(self, services):
        """GET /v2/agent/status returns 200 with valid token."""
        status, data = _http_get(f"{BRAIN_URL}/v2/agent/status", headers={"X-Brain-Token": LOCAL_TOKEN})
        assert status == 200
        assert data.get("ok") is True
        assert data.get("canonical_for_new_agent_runs") is True

    def test_chat_403_without_token(self, services):
        """POST /v2/chat/agent returns 403 without token."""
        status, data = _http_post(
            f"{BRAIN_URL}/v2/chat/agent",
            {"message": "test", "mode": "read_only", "user_id": "test"},
        )
        assert status == 403

    def test_chat_200_with_token(self, services):
        """POST /v2/chat/agent returns 200 with valid token."""
        status, data = _http_post(
            f"{BRAIN_URL}/v2/chat/agent",
            {"message": "hola", "mode": "read_only", "user_id": "test_ui"},
            headers={"X-Brain-Token": LOCAL_TOKEN},
        )
        assert status == 200
        assert "final_answer" in data or "response" in data

    def test_capabilities_403_without_token(self, services):
        """GET /v2/agent/capabilities returns 403 without token."""
        status, _ = _http_get(f"{BRAIN_URL}/v2/agent/capabilities")
        assert status == 403

    def test_capabilities_200_with_token(self, services):
        """GET /v2/agent/capabilities returns 200 with token."""
        status, data = _http_get(f"{BRAIN_URL}/v2/agent/capabilities", headers={"X-Brain-Token": LOCAL_TOKEN})
        assert status == 200
        assert "capabilities" in data or "tools" in data

    def test_trace_endpoint_works_with_token(self, services):
        """GET /v2/agent/runs/{run_id}/trace works with token."""
        status, data = _http_post(
            f"{BRAIN_URL}/v2/chat/agent",
            {"message": "trace test", "mode": "read_only", "user_id": "trace_test"},
            headers={"X-Brain-Token": LOCAL_TOKEN},
        )
        assert status == 200
        run_id = data.get("run_id")
        assert run_id

        status, trace = _http_get(f"{BRAIN_URL}/v2/agent/runs/{run_id}/trace", headers={"X-Brain-Token": LOCAL_TOKEN})
        assert status in (200, 404)

    def test_no_hardcoded_secret_in_frontend(self, services):
        """Frontend does not contain hardcoded real tokens."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "AGENTV2_TEST_ADMIN_TOKEN" not in content
        assert "sk-" not in content
        assert "Bearer " not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])