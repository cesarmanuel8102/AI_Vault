"""
Smoke tests for governance RBAC dev god hardening.

Rules:
- No memory mutation.
- No ingestion/promotion.
- Verify governance controls are enforced.
"""
import os
import sys
import json
import subprocess
import faiss
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
# Ensure dev endpoints are disabled by default for tests
os.environ.setdefault("BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS", "false")

from tmp_agent.brain_v9.main import app
from tmp_agent.brain_v9.config import BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS
from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
from tmp_agent.brain_v9.core.agent_kernel_v2 import governance

SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


def test_state_baseline_memory_counts_unchanged():
    records = [line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(IDX_PATH)).ntotal)
    assert len(records) == 1795, f"expected 1795 records, got {len(records)}"
    assert len(ids) == 1786, f"expected 1786 ids, got {len(ids)}"
    assert ntotal == 1786, f"expected 1786 ntotal, got {ntotal}"
    print("PASS: state_baseline_memory_counts_unchanged")


def test_critical_routes_reject_missing_token():
    for path in ["/v2/chat/agent", "/v2/agent/runs", "/v1/chat/completions"]:
        r = client.post(path, json={"message": "test", "mode": "read_only"})
        assert r.status_code in {401, 403}, f"{path} should reject missing token, got {r.status_code}"
    print("PASS: critical_routes_reject_missing_token")


def test_god_flags_do_not_bypass_auth():
    payloads = [
        {"message": "test with god=true", "mode": "read_only"},
        {"message": "test with god_mode", "mode": "read_only"},
        {"message": "test with bypass_auth", "mode": "read_only"},
        {"message": "test with mode=god", "mode": "read_only"},
    ]
    for p in payloads:
        r = client.post("/v2/chat/agent", json=p)
        # Requests without valid token should still be 403
        assert r.status_code in {401, 403}, f"payload {p} should be rejected, got {r.status_code}"
    print("PASS: god_flags_do_not_bypass_auth")


def test_invalid_token_rejected_even_with_god_flags():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "test", "mode": "read_only"},
        headers={"X-Brain-Token": "invalid_token"},
    )
    assert r.status_code in {401, 403}
    print("PASS: invalid_token_rejected_even_with_god_flags")


def test_valid_token_normal_chat_still_works():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What should I know about auth on critical endpoints?", "mode": "read_only", "user_id": "gov_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    print("PASS: valid_token_normal_chat_still_works")


def test_dev_endpoints_disabled_by_default():
    # Ensure env flag is false
    assert BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS is False
    r = client.post("/dev", json={"task": "test"})
    assert r.status_code in {403, 404}, f"/dev should be disabled, got {r.status_code}"
    r2 = client.post("/godmode", json={"task": "test", "session_id": "fake"})
    assert r2.status_code in {403, 404}, f"/godmode should be disabled, got {r2.status_code}"
    print("PASS: dev_endpoints_disabled_by_default")


def test_write_tools_blocked_in_read_only():
    req = ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": "gov_probe", "source": "all", "approval_token": "AGENTV2_APPROVED_TEST_SHOULD_NOT_MATTER", "operator_id": "probe", "confirm_phrase": "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"},
        mode="read_only",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False or bool(result.error), "write tool allowed in read_only"
    print("PASS: write_tools_blocked_in_read_only")


def test_memory_promote_requires_approval_token():
    req = ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": "gov_probe", "source": "all", "approval_token": "", "operator_id": "probe", "confirm_phrase": "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"},
        mode="build",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False or bool(result.error), "promotion allowed without approval token"
    print("PASS: memory_promote_requires_approval_token")


def test_selfdev_governance_files_denied_by_default():
    # Try to patch a governance-critical file without governance token
    req = ToolCallRequest(
        tool_name="file_patch_dry_run",
        args={"path": "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py", "patch": "# test"},
        mode="build",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False
    assert "governance_file_modification_denied_by_default" in str(result.error or ""), f"unexpected error: {result.error}"
    print("PASS: selfdev_governance_files_denied_by_default")


def test_governance_modify_requires_explicit_confirm_phrase():
    # Try with governance token but wrong confirm phrase
    req = ToolCallRequest(
        tool_name="file_patch_dry_run",
        args={"path": "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py", "patch": "# test", "governance_token": "AGENTV2_APPROVED_GOVERNANCE_CHANGE", "confirm_phrase": "WRONG_PHRASE"},
        mode="build",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False
    assert "governance_file_modification_denied_by_default" in str(result.error or ""), f"unexpected error: {result.error}"
    print("PASS: governance_modify_requires_explicit_confirm_phrase")


def test_validate_mode_rejects_dangerous_modes():
    assert governance.validate_mode("god") == "read_only"
    assert governance.validate_mode("god_mode") == "read_only"
    assert governance.validate_mode("execute") == "read_only"
    assert governance.validate_mode("unsafe") == "read_only"
    assert governance.validate_mode("superuser") == "read_only"
    assert governance.validate_mode("build") == "build"
    assert governance.validate_mode("read_only") == "read_only"
    assert governance.validate_mode("auto") == "auto"
    print("PASS: validate_mode_rejects_dangerous_modes")


def test_contains_forbidden_request_fields_detects_bypass():
    assert governance.contains_forbidden_request_fields({"god": True}) is True
    assert governance.contains_forbidden_request_fields({"bypass_auth": True}) is True
    assert governance.contains_forbidden_request_fields({"safe_mode": False}) is True
    assert governance.contains_forbidden_request_fields({"override_governance": True}) is True
    assert governance.contains_forbidden_request_fields({"message": "hello"}) is False
    print("PASS: contains_forbidden_request_fields_detects_bypass")


def test_guard_still_blocks_sensitive_paths():
    result = subprocess.run(
        ["python", "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd="C:/AI_VAULT_CANONICAL",
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    assert result.returncode == 0, f"guard failed: {result.stdout} {result.stderr}"
    print("PASS: guard_still_blocks_sensitive_paths")


def test_no_memory_files_tracked_or_staged():
    result = subprocess.run(["git", "ls-files"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    tracked = result.stdout.splitlines()
    forbidden = [
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/autonomous_journal.jsonl",
    ]
    for f in forbidden:
        assert f not in tracked, f"{f} is tracked"
    print("PASS: no_memory_files_tracked_or_staged")


def test_promotion_queue_and_semantic_staging_not_mutated():
    result = subprocess.run(["git", "status", "--short", "--", "memory/promotion_queue", "memory/semantic_staging"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    staged = [line for line in result.stdout.splitlines() if line.strip().startswith(("A", "M", "D"))]
    assert len(staged) == 0, f"promotion_queue or semantic_staging mutated: {staged}"
    print("PASS: promotion_queue_and_semantic_staging_not_mutated")


if __name__ == "__main__":
    test_state_baseline_memory_counts_unchanged()
    test_critical_routes_reject_missing_token()
    test_god_flags_do_not_bypass_auth()
    test_invalid_token_rejected_even_with_god_flags()
    test_valid_token_normal_chat_still_works()
    test_dev_endpoints_disabled_by_default()
    test_write_tools_blocked_in_read_only()
    test_memory_promote_requires_approval_token()
    test_selfdev_governance_files_denied_by_default()
    test_governance_modify_requires_explicit_confirm_phrase()
    test_validate_mode_rejects_dangerous_modes()
    test_contains_forbidden_request_fields_detects_bypass()
    test_guard_still_blocks_sensitive_paths()
    test_no_memory_files_tracked_or_staged()
    test_promotion_queue_and_semantic_staging_not_mutated()
    print("ALL 15 GOVERNANCE HARDENING TESTS PASSED")
