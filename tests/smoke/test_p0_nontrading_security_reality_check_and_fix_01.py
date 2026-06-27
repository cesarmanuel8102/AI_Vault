"""
FRONT-P0-NONTRADING-SECURITY-REALITY-CHECK-AND-FIX-01
Strong security smoke test (read-only, no mutation).

Validates:
1. Existing protections still hold (dev/god endpoints gated, RBAC enforced, extra=forbid, etc.)
2. NEW: Unauthenticated mutative endpoints return 403 (previously 200).
3. No memory mutation, no ingestion/promotion.

Rules:
- No memory mutation.
- No ingestion/promotion.
- Tests are deterministic and do not depend on prior state beyond session lifecycle.
"""
import os
import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

from tmp_agent.brain_v9.main import app
from tmp_agent.brain_v9.config import BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


# ── Existing protection regression tests ──

def test_dev_post_without_token_rejected():
    r = client.post("/dev", json={"task": "test"})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: dev_post_without_token_rejected")


def test_godmode_post_without_token_rejected():
    r = client.post("/godmode", json={"task": "test", "session_id": "fake"})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: godmode_post_without_token_rejected")


def test_godmode_status_without_token_rejected():
    r = client.get("/godmode/status")
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: godmode_status_without_token_rejected")


def test_dev_post_with_token_but_flag_off_rejected():
    r = client.post("/dev", json={"task": "test"}, headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: dev_post_with_token_but_flag_off_rejected")


def test_godmode_post_with_token_but_flag_off_rejected():
    r = client.post("/godmode", json={"task": "test", "session_id": "fake"}, headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: godmode_post_with_token_but_flag_off_rejected")


def test_godmode_status_with_valid_token_accessible():
    r = client.get("/godmode/status", headers={"X-Brain-Token": VALID_TOKEN})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("unsafe_endpoints_enabled") is False
    print("PASS: godmode_status_with_valid_token_accessible")


def test_extra_forbidden_field_rejected_even_with_valid_token():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "hello", "mode": "read_only", "bypass_auth": True},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    print("PASS: extra_forbidden_field_rejected_even_with_valid_token")


def test_critical_routes_reject_missing_token():
    for path in ["/v2/chat/agent", "/v1/chat/completions"]:
        r = client.post(path, json={"message": "test", "mode": "read_only"})
        assert r.status_code in {401, 403}, f"{path} should reject missing token, got {r.status_code}"
    print("PASS: critical_routes_reject_missing_token")


def test_gate_approve_rejects_without_token():
    r = client.post("/gate/approve/fake-id")
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: gate_approve_rejects_without_token")


def test_gate_reject_rejects_without_token():
    r = client.post("/gate/reject/fake-id")
    assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
    print("PASS: gate_reject_rejects_without_token")


# ── NEW gap tests: unauthenticated mutative endpoints must be 403 ──

def test_delete_session_requires_auth():
    r = client.delete("/sessions/fake_session_id")
    assert r.status_code == 403, f"DELETE /sessions/: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: delete_session_requires_auth")


def test_delete_session_memory_requires_auth():
    r = client.delete("/sessions/fake_session_id/memory")
    assert r.status_code == 403, f"DELETE /sessions/:id/memory: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: delete_session_memory_requires_auth")


def test_tool01_permission_approve_requires_auth():
    r = client.post("/tool01/permission/approve", json={"session_id": "fake", "permission_id": "fake", "decision": True})
    assert r.status_code == 403, f"POST /tool01/permission/approve: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: tool01_permission_approve_requires_auth")


def test_brain_learned_pattern_disable_requires_auth():
    r = client.post("/brain/learned/patterns/fake-id/disable")
    assert r.status_code == 403, f"POST /brain/learned/patterns/:id/disable: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: brain_learned_pattern_disable_requires_auth")


def test_brain_learned_pattern_delete_requires_auth():
    r = client.delete("/brain/learned/patterns/fake-id")
    assert r.status_code == 403, f"DELETE /brain/learned/patterns/:id: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: brain_learned_pattern_delete_requires_auth")


def test_brain_learned_test_simulate_requires_auth():
    r = client.post("/brain/learned/test_simulate", json={"tool": "fake", "args": {}, "error_text": "fake"})
    assert r.status_code == 403, f"POST /brain/learned/test_simulate: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: brain_learned_test_simulate_requires_auth")


def test_brain_mutation_rollback_requires_auth():
    r = client.post("/brain/mutations/fake-id/rollback")
    assert r.status_code == 403, f"POST /brain/mutations/:id/rollback: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: brain_mutation_rollback_requires_auth")


def test_brain_llm_circuit_breaker_reset_requires_auth():
    r = client.post("/brain/llm/circuit_breaker/reset")
    assert r.status_code == 403, f"POST /brain/llm/circuit_breaker/reset: Expected 403, got {r.status_code}: {r.text}"
    print("PASS: brain_llm_circuit_breaker_reset_requires_auth")


# ── Positive: valid token still works for safe operations ──

def test_valid_token_normal_chat_still_works():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What should I know about auth on critical endpoints?", "mode": "read_only", "user_id": "security_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data.get("ok") is True
    print("PASS: valid_token_normal_chat_still_works")


if __name__ == "__main__":
    test_dev_post_without_token_rejected()
    test_godmode_post_without_token_rejected()
    test_godmode_status_without_token_rejected()
    test_dev_post_with_token_but_flag_off_rejected()
    test_godmode_post_with_token_but_flag_off_rejected()
    test_godmode_status_with_valid_token_accessible()
    test_extra_forbidden_field_rejected_even_with_valid_token()
    test_critical_routes_reject_missing_token()
    test_gate_approve_rejects_without_token()
    test_gate_reject_rejects_without_token()
    test_delete_session_requires_auth()
    test_delete_session_memory_requires_auth()
    test_tool01_permission_approve_requires_auth()
    test_brain_learned_pattern_disable_requires_auth()
    test_brain_learned_pattern_delete_requires_auth()
    test_brain_learned_test_simulate_requires_auth()
    test_brain_mutation_rollback_requires_auth()
    test_brain_llm_circuit_breaker_reset_requires_auth()
    test_valid_token_normal_chat_still_works()
    print("ALL 19 SECURITY SMOKE TESTS PASSED")
