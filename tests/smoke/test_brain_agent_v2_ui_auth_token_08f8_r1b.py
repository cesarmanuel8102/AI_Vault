"""
UI Auth Token smoke tests for FRONT-BRAIN-AGENT-V2-BROWSER-OPERATIONAL-RECOVERY-P0-08F8-R1B.

Tests that the browser UI properly handles the operator token flow.
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
    """Start the Brain service."""
    env = {**os.environ, "BRAIN_ADMIN_TOKEN": LOCAL_TOKEN, "PYTHONPATH": str(REPO_ROOT)}
    brain_cmd = [sys.executable, str(REPO_ROOT / "tmp_agent" / "brain_v9" / "start_safe_server.py")]
    brain_proc = subprocess.Popen(brain_cmd, env=env, cwd=str(REPO_ROOT))

    # Wait for health
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{BRAIN_URL}/health", timeout=1.0) as r:
                if r.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.5)

    yield

    brain_proc.terminate()
    try:
        brain_proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        brain_proc.kill()


class TestUIAuthToken:
    """UI auth token flow tests."""

    def test_ui_contains_token_input_field(self, services):
        """UI HTML has token input field."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "token-input" in content
        assert "type=\"password\"" in content or 'type="password"' in content

    def test_ui_contains_token_banner(self, services):
        """UI HTML has token banner that shows when no token."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "token-banner" in content
        assert "Token de operador requerido" in content

    def test_ui_includes_x_brain_token_in_fetch(self, services):
        """UI JavaScript includes X-Brain-Token in fetch calls."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "X-Brain-Token" in content
        assert "getOperatorToken" in content

    def test_ui_has_localstorage_token_storage(self, services):
        """UI uses localStorage for token persistence."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "localStorage" in content
        assert "brain_v9_operator_token" in content

    def test_ui_shows_explicit_auth_error_on_401(self, services):
        """UI shows explicit 'Operator token rejected or missing' on 401/403."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "Operator token rejected or missing" in content

    def test_ui_no_hardcoded_real_token(self, services):
        """UI does not contain hardcoded real token values."""
        ui_path = REPO_ROOT / "tmp_agent" / "brain_v9" / "ui" / "index.html"
        content = ui_path.read_text(encoding="utf-8")
        assert "AGENTV2_TEST_ADMIN_TOKEN" not in content
        assert "AGENTV2_" not in content or "AGENTV2_TEST" not in content

    def test_agent_status_403_without_token(self, services):
        """Agent status returns 403 without token."""
        status, data = _http_get(f"{BRAIN_URL}/v2/agent/status")
        assert status == 403
        assert "strict operator access required" in str(data.get("detail", "")).lower()

    def test_agent_status_200_with_token(self, services):
        """Agent status returns 200 with valid token."""
        status, data = _http_get(f"{BRAIN_URL}/v2/agent/status", headers={"X-Brain-Token": LOCAL_TOKEN})
        assert status == 200
        assert data.get("ok") is True

    def test_chat_403_without_token(self, services):
        """Chat returns 403 without token."""
        status, data = _http_post(f"{BRAIN_URL}/v2/chat/agent", {"message": "test", "mode": "read_only", "user_id": "test"})
        assert status == 403
        assert "strict operator access required" in str(data.get("detail", "")).lower()

    def test_chat_200_with_token(self, services):
        """Chat returns 200 with valid token."""
        status, data = _http_post(
            f"{BRAIN_URL}/v2/chat/agent",
            {"message": "hola", "mode": "read_only", "user_id": "test_ui"},
            headers={"X-Brain-Token": LOCAL_TOKEN},
        )
        assert status == 200
        assert "final_answer" in data or "response" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])