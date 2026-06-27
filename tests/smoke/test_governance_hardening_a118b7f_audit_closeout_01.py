"""
Smoke tests for FRONT-GOVERNANCE-HARDENING-A118B7F-AUDIT-AND-GAP-CLOSEOUT-01.

Rules:
- No memory mutation.
- No ingestion/promotion.
- Strong negative tests that prove real behavior, not superficial cases.
"""
import os
import sys
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

from tmp_agent.brain_v9.main import app
from tmp_agent.brain_v9.config import BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


def test_valid_token_with_extra_forbidden_field_rejected():
    """
    GAP-A: Prove that extra forbidden fields in the JSON body are rejected
    even when a valid token is present. Before the patch, Pydantic silently
    dropped extra fields, so the request proceeded.
    """
    r = client.post(
        "/v2/chat/agent",
        json={"message": "hello", "mode": "read_only", "bypass_auth": True},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    # Pydantic extra='forbid' now raises 422 on extra fields
    assert r.status_code == 422, f"Expected 422 for extra forbidden field, got {r.status_code}: {r.text}"
    print("PASS: valid_token_with_extra_forbidden_field_rejected")


def test_valid_token_with_extra_god_mode_field_rejected():
    """
    GAP-A: Same as above but with 'god_mode' extra field.
    """
    r = client.post(
        "/v2/chat/agent",
        json={"message": "hello", "mode": "read_only", "god_mode": True},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 422, f"Expected 422 for extra god_mode field, got {r.status_code}: {r.text}"
    print("PASS: valid_token_with_extra_god_mode_field_rejected")


def test_godmode_status_without_token_rejected():
    """
    GAP-B: /godmode/status must now require strict operator access.
    Before patch it returned 200 with session metadata leak.
    """
    r = client.get("/godmode/status")
    assert r.status_code == 403, f"Expected 403 without token, got {r.status_code}: {r.text}"
    print("PASS: godmode_status_without_token_rejected")


def test_godmode_status_with_valid_token_accessible():
    """
    GAP-B: With valid token, /godmode/status should still return JSON.
    The BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS flag does NOT block this endpoint;
    it only blocks /dev and /godmode POST execution.
    """
    r = client.get(
        "/godmode/status",
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200, f"Expected 200 with valid token, got {r.status_code}: {r.text}"
    data = r.json()
    assert "unsafe_endpoints_enabled" in data
    assert data["unsafe_endpoints_enabled"] is False
    print("PASS: godmode_status_with_valid_token_accessible")


def test_dev_post_without_token_rejected():
    """
    GAP-C: /dev POST must require strict operator access before PAD session check.
    """
    r = client.post("/dev", json={"task": "test"})
    assert r.status_code == 403, f"Expected 403 without token, got {r.status_code}: {r.text}"
    print("PASS: dev_post_without_token_rejected")


def test_godmode_post_without_token_rejected():
    """
    GAP-C: /godmode POST must require strict operator access before PAD session check.
    """
    r = client.post("/godmode", json={"task": "test", "session_id": "fake"})
    assert r.status_code == 403, f"Expected 403 without token, got {r.status_code}: {r.text}"
    print("PASS: godmode_post_without_token_rejected")


def test_valid_token_normal_chat_still_works():
    """
    Regression: Ensure extra='forbid' does not break legitimate requests.
    """
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What should I know about auth on critical endpoints?", "mode": "read_only", "user_id": "gov_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200, f"Expected 200 for normal chat, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("ok") is True
    print("PASS: valid_token_normal_chat_still_works")


def test_dev_endpoints_disabled_by_default():
    """
    Existing test: BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is false.
    Even with valid token, /dev and /godmode should return 403 because
    the flag blocks them before the PAD session check.
    """
    assert BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is False
    r1 = client.post(
        "/dev",
        json={"task": "test"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r1.status_code == 403, f"/dev should be disabled, got {r1.status_code}: {r1.text}"
    r2 = client.post(
        "/godmode",
        json={"task": "test", "session_id": "fake"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r2.status_code == 403, f"/godmode should be disabled, got {r2.status_code}: {r2.text}"
    print("PASS: dev_endpoints_disabled_by_default")


if __name__ == "__main__":
    test_valid_token_with_extra_forbidden_field_rejected()
    test_valid_token_with_extra_god_mode_field_rejected()
    test_godmode_status_without_token_rejected()
    test_godmode_status_with_valid_token_accessible()
    test_dev_post_without_token_rejected()
    test_godmode_post_without_token_rejected()
    test_valid_token_normal_chat_still_works()
    test_dev_endpoints_disabled_by_default()
    print("ALL 8 AUDIT CLOSEOUT TESTS PASSED")
