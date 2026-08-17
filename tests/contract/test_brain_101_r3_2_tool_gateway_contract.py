"""BRAIN-101-R3-2 Agent V2 tool gateway contract tests.

Front: BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
Surface: C6 Tool gateway contract

Deterministic contract tests for tool registration, capability schema,
read-only tool execution, write-tool gating, path blocking, timeout/fallback
shape, and result normalization.  No server starts, no HTTP calls, no real
writes outside the configured safe paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


# ---------------------------------------------------------------------------
# 1. Tool capability inventory contract
# ---------------------------------------------------------------------------

def test_tool_gateway_lists_required_capabilities():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2

    gateway = ToolGatewayV2()
    caps = gateway.list_capabilities()
    names = {c["name"] for c in caps}
    required = {
        "repo_status_read",
        "repo_history_read",
        "file_read",
        "grep_search",
        "route_probe",
        "semantic_retrieve",
        "smoke_test_readonly",
        "file_patch_dry_run",
        "file_patch_apply_approval_required",
        "git_commit_approval_required",
        "promotion_candidate_validate",
        "promotion_candidate_promote",
        "repo_file_search",
        "repo_file_read",
        "memory_structure_inspect",
        "semantic_memory_status",
        "promotion_queue_status",
        "capability_registry_read",
        "brain_self_knowledge_lookup",
    }
    assert required.issubset(names)


def test_tool_capability_schema_has_required_fields():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2

    gateway = ToolGatewayV2()
    caps = gateway.list_capabilities()
    for cap in caps:
        assert {"name", "description", "risk_level", "read_only", "requires_approval", "allowed_modes"}.issubset(cap)
        assert isinstance(cap["allowed_modes"], list)
        assert cap["risk_level"] in {"low", "medium", "high"}
        assert isinstance(cap["read_only"], bool)
        assert isinstance(cap["requires_approval"], bool)


def test_tool_capability_read_only_set_is_accurate():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2

    gateway = ToolGatewayV2()
    read_only_caps = {c["name"] for c in gateway.list_capabilities() if c["read_only"]}
    write_caps = {c["name"] for c in gateway.list_capabilities() if not c["read_only"]}
    assert "file_read" in read_only_caps
    assert "repo_status_read" in read_only_caps
    assert "semantic_retrieve" in read_only_caps
    assert "file_patch_apply_approval_required" in write_caps
    assert "git_commit_approval_required" in write_caps
    assert "promotion_candidate_promote" in write_caps


# ---------------------------------------------------------------------------
# 2. Read-only tool execution contract
# ---------------------------------------------------------------------------

def test_repo_status_read_returns_git_head_and_status():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("repo_status_read", {}, "read_only"))
    assert result.ok is True
    assert "head" in result.result
    assert isinstance(result.result["head"], list)


def test_file_read_blocks_forbidden_path():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("file_read", {"path": ".env"}, "read_only"))
    assert result.ok is False
    assert result.blocked is True
    assert result.error in {"path_blocked", "forbidden_target"}


def test_file_read_returns_allowed_file():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("file_read", {"path": "README.md"}, "read_only"))
    assert result.ok is True
    assert "text" in result.result


def test_grep_search_returns_matches_shape():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("grep_search", {"pattern": "agent_kernel_v2", "glob": "*.py"}, "read_only"))
    assert result.ok is True
    assert "matches" in result.result
    assert isinstance(result.result["matches"], list)


# ---------------------------------------------------------------------------
# 3. Write tool gating contract
# ---------------------------------------------------------------------------

def test_write_tool_blocked_in_read_only_mode():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(
        ToolCallRequest(
            "file_patch_apply_approval_required", {"path": "README.md", "patch": "test"}, "read_only"
        )
    )
    assert result.ok is False
    assert result.blocked is True
    assert (
        "read_only" in result.error.lower()
        or result.error in {"write_tool_blocked_in_read_only_mode", "build_mode_required"}
    )


def test_write_tool_requires_build_mode():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(
        ToolCallRequest("file_patch_apply_approval_required", {"path": "README.md", "patch": "test"}, "build")
    )
    # No valid approval token, so it should still be approval_required.
    assert result.ok is False
    assert result.approval_required is True


def test_git_commit_approval_required_is_gated():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("git_commit_approval_required", {"message": "test"}, "read_only"))
    assert result.ok is False
    assert (result.blocked or result.approval_required) is True


# ---------------------------------------------------------------------------
# 4. Route probe contract
# ---------------------------------------------------------------------------

def test_route_probe_only_allows_localhost():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("route_probe", {"url": "https://example.com/health"}, "read_only"))
    assert result.ok is False
    assert result.blocked is True
    assert "only_local_routes_allowed" in result.error


def test_route_probe_blocks_non_allowlisted_post():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(
        ToolCallRequest("route_probe", {"url": "http://127.0.0.1:8091/not_allowed", "method": "POST"}, "read_only")
    )
    assert result.ok is False
    assert result.blocked is True
    assert result.error == "post_path_not_allowlisted"


def test_route_probe_normalizes_bare_relative_path():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("route_probe", {"url": "/v2/agent/status"}, "read_only"))
    assert result.result.get("url") == "http://127.0.0.1:8091/v2/agent/status"


# ---------------------------------------------------------------------------
# 5. Smoke test gating contract
# ---------------------------------------------------------------------------

def test_smoke_test_readonly_blocks_disallowed_target():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(
        ToolCallRequest("smoke_test_readonly", {"target": "tests/unit/test_trace_redactor.py"}, "read_only")
    )
    assert result.ok is False
    assert result.blocked is True
    assert "target_blocked" in result.error or "governance" in result.error


# ---------------------------------------------------------------------------
# 6. Tool result normalization contract
# ---------------------------------------------------------------------------

def test_tool_call_result_has_required_schema():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("repo_status_read", {}, "read_only"))
    assert hasattr(result, "tool_name")
    assert hasattr(result, "ok")
    assert hasattr(result, "result")
    assert hasattr(result, "blocked")
    assert hasattr(result, "approval_required")
    assert hasattr(result, "error")
    assert isinstance(result.ok, bool)
    assert isinstance(result.blocked, bool)
    assert isinstance(result.approval_required, bool)


# ---------------------------------------------------------------------------
# 7. Unknown tool contract
# ---------------------------------------------------------------------------

def test_unknown_tool_returns_unknown_error():
    from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest

    gateway = ToolGatewayV2()
    result = gateway.call(ToolCallRequest("rm_rf_everything", {}, "read_only"))
    assert result.ok is False
    assert result.error == "unknown_tool"


# ---------------------------------------------------------------------------
# 8. Safety: tool gateway source does not contain forbidden server tokens
# ---------------------------------------------------------------------------

def test_tool_gateway_source_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem("]
    assert not any(token in src for token in forbidden)


# ---------------------------------------------------------------------------
# Runner for direct invocation
# ---------------------------------------------------------------------------

_TESTS = [
    test_tool_gateway_lists_required_capabilities,
    test_tool_capability_schema_has_required_fields,
    test_tool_capability_read_only_set_is_accurate,
    test_repo_status_read_returns_git_head_and_status,
    test_file_read_blocks_forbidden_path,
    test_file_read_returns_allowed_file,
    test_grep_search_returns_matches_shape,
    test_write_tool_blocked_in_read_only_mode,
    test_write_tool_requires_build_mode,
    test_git_commit_approval_required_is_gated,
    test_route_probe_only_allows_localhost,
    test_route_probe_blocks_non_allowlisted_post,
    test_route_probe_normalizes_bare_relative_path,
    test_smoke_test_readonly_blocks_disallowed_target,
    test_tool_call_result_has_required_schema,
    test_unknown_tool_returns_unknown_error,
    test_tool_gateway_source_does_not_import_server_starters,
]


if __name__ == "__main__":
    passed = failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
