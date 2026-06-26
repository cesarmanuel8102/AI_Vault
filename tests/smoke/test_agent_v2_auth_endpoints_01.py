"""
Smoke tests for auth on critical Agent V2 and chat endpoints.

Policy:
- All protected endpoints require X-Brain-Token matching BRAIN_ADMIN_TOKEN.
- No localhost bypass for these critical endpoints.
- Tests use FastAPI TestClient and set token only inside test context.
- All chat/run calls are read_only; no promotion, ingestion, or trading.
- No memory mutation is expected.
"""
from __future__ import annotations

import os
import sys
import uuid
import time
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

import faiss

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")

from tmp_agent.brain_v9.main import app

VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"
INVALID_TOKEN = "INVALID_TOKEN"
SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"

client = TestClient(app)


def _memory_counts():
    records = [line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = __import__("json").loads(IDS_PATH.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(IDX_PATH)).ntotal)
    return len(records), len(ids), ntotal


def _unique_user():
    return f"auth_probe_{uuid.uuid4().hex[:8]}_{int(time.time())}"


def test_v2_chat_agent_rejects_without_token():
    r = client.post("/v2/chat/agent", json={"message": "ping", "mode": "read_only", "user_id": _unique_user()})
    assert r.status_code in {401, 403}
    print("PASS: v2_chat_agent_rejects_without_token")


def test_v2_chat_agent_accepts_with_valid_token():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "ping", "mode": "read_only", "user_id": _unique_user()},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("route") == "/v2/chat/agent"
    assert data.get("mode_effective") == "read_only"
    print("PASS: v2_chat_agent_accepts_with_valid_token")


def test_v2_agent_create_run_rejects_without_token():
    r = client.post("/v2/agent/runs", json={"goal": "read_only auth probe", "mode": "read_only", "user_id": _unique_user()})
    assert r.status_code in {401, 403}
    print("PASS: v2_agent_create_run_rejects_without_token")


def test_v2_agent_create_run_accepts_with_valid_token():
    r = client.post(
        "/v2/agent/runs",
        json={"goal": "read_only auth probe", "mode": "read_only", "user_id": _unique_user()},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "run" in data
    print("PASS: v2_agent_create_run_accepts_with_valid_token")


def test_v2_agent_plan_rejects_without_token():
    r = client.post("/v2/agent/runs/fake-run-id/plan", json={})
    assert r.status_code in {401, 403}
    print("PASS: v2_agent_plan_rejects_without_token")


def test_v2_agent_execute_rejects_without_token():
    r = client.post("/v2/agent/runs/fake-run-id/execute", json={})
    assert r.status_code in {401, 403}
    print("PASS: v2_agent_execute_rejects_without_token")


def test_v2_agent_pause_resume_cancel_reject_without_token():
    for action in ("pause", "resume", "cancel"):
        r = client.post(f"/v2/agent/runs/fake-run-id/{action}", json={})
        assert r.status_code in {401, 403}, f"{action} allowed unauth"
    print("PASS: v2_agent_pause_resume_cancel_reject_without_token")


def test_v1_chat_completions_rejects_without_token():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "brain-v9-local", "messages": [{"role": "user", "content": "ping"}]},
    )
    assert r.status_code in {401, 403}
    print("PASS: v1_chat_completions_rejects_without_token")


def test_v1_chat_completions_accepts_with_valid_token():
    r = client.post(
        "/v1/chat/completions",
        json={"model": "brain-v9-local", "messages": [{"role": "user", "content": "ping"}], "metadata": {"read_only": True, "dry_run": True}},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert "choices" in data
    assert data["brain"].get("dry_run") is True or data["brain"].get("read_only") is True
    print("PASS: v1_chat_completions_accepts_with_valid_token")


def test_invalid_token_rejected():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "ping", "mode": "read_only", "user_id": _unique_user()},
        headers={"X-Brain-Token": INVALID_TOKEN},
    )
    assert r.status_code in {401, 403}
    print("PASS: invalid_token_rejected")


def test_missing_header_rejected():
    r = client.post(
        "/v2/agent/runs",
        json={"goal": "read_only auth probe", "mode": "read_only", "user_id": _unique_user()},
    )
    assert r.status_code in {401, 403}
    print("PASS: missing_header_rejected")


def test_read_only_tool_gates_still_work_after_auth():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    req = ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={
            "candidate_id": "nonexistent_auth_gate_probe",
            "source": "all",
            "approval_token": "AGENTV2_APPROVED_TEST_SHOULD_NOT_MATTER",
            "operator_id": "auth_test",
            "confirm_phrase": "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY",
        },
        mode="read_only",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False or bool(result.error)
    error_text = str(result.error or result.result or "").lower()
    assert (
        "read_only" in error_text
        or "write_tool_blocked" in error_text
        or "approval" in error_text
        or result.approval_required is True
    ), f"expected read_only block, got error={result.error} result={result.result}"
    print("PASS: read_only_tool_gates_still_work_after_auth")


def test_write_tool_still_blocked_in_read_only_after_auth():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    req = ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={
            "candidate_id": "nonexistent_auth_gate_probe_02",
            "source": "all",
            "approval_token": "AGENTV2_APPROVED_TEST_SHOULD_NOT_MATTER",
            "operator_id": "auth_test",
            "confirm_phrase": "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY",
        },
        mode="read_only",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False or bool(result.error)
    print("PASS: write_tool_still_blocked_in_read_only_after_auth")


def test_no_memory_mutation_during_auth_tests():
    before_records, before_ids, before_ntotal = _memory_counts()
    _ = client.post(
        "/v2/chat/agent",
        json={"message": "ping", "mode": "read_only", "user_id": _unique_user()},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    after_records, after_ids, after_ntotal = _memory_counts()
    assert before_records == after_records
    assert before_ids == after_ids
    assert before_ntotal == after_ntotal
    print("PASS: no_memory_mutation_during_auth_tests")


def test_unauthenticated_request_does_not_create_run_artifacts():
    before = len([line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()])
    _ = client.post(
        "/v2/agent/runs",
        json={"goal": "should fail", "mode": "read_only", "user_id": _unique_user()},
    )
    after = len([line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()])
    assert before == after
    print("PASS: unauthenticated_request_does_not_create_run_artifacts")


if __name__ == "__main__":
    test_v2_chat_agent_rejects_without_token()
    test_v2_chat_agent_accepts_with_valid_token()
    test_v2_agent_create_run_rejects_without_token()
    test_v2_agent_create_run_accepts_with_valid_token()
    test_v2_agent_plan_rejects_without_token()
    test_v2_agent_execute_rejects_without_token()
    test_v2_agent_pause_resume_cancel_reject_without_token()
    test_v1_chat_completions_rejects_without_token()
    test_v1_chat_completions_accepts_with_valid_token()
    test_invalid_token_rejected()
    test_missing_header_rejected()
    test_read_only_tool_gates_still_work_after_auth()
    test_write_tool_still_blocked_in_read_only_after_auth()
    test_no_memory_mutation_during_auth_tests()
    test_unauthenticated_request_does_not_create_run_artifacts()
    print("ALL V2 AUTH ENDPOINT TESTS PASSED")
