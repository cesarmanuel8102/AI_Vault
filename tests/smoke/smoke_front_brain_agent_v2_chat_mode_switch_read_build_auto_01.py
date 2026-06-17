"""Smoke test for Agent V2 READ/BUILD/AUTO chat modes."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import pytest
from tmp_agent.brain_v9.core.agent_kernel_v2.governance import (
    validate_mode, infer_auto_decision, mode_requires_escalation,
    WRITE_TOOL_NAMES, READ_ONLY_TOOL_NAMES
)
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import MODES, LEGACY_MODE_MAP
from tmp_agent.brain_v9.core.agent_kernel_v2.native_runtime import NativeAgentRuntimeV2

class TestModeValidation:
    def test_validate_mode_reads_read_only(self): assert validate_mode("read_only") == "read_only"
    def test_validate_mode_reads_build(self): assert validate_mode("build") == "build"
    def test_validate_mode_reads_auto(self): assert validate_mode("auto") == "auto"
    def test_validate_mode_maps_legacy_dry_run(self): assert validate_mode("dry_run") == "read_only"
    def test_validate_mode_maps_legacy_approval(self): assert validate_mode("approval_required") == "build"
    def test_validate_mode_defaults_invalid(self): assert validate_mode("xyz") == "read_only"

class TestInferAutoDecision:
    def test_infer_auto_read(self): assert infer_auto_decision("show me git status") == "read"
    def test_infer_auto_build(self): assert infer_auto_decision("fix the planner bug") == "build_required"
    def test_infer_auto_build_commit(self): assert infer_auto_decision("commit the changes") == "build_required"

class TestModeEscalation:
    def test_read_mode_no_escalation_for_read_tools(self):
        assert not mode_requires_escalation("show status", "read_only", ["repo_status_read"])
    def test_read_mode_escalation_for_write_tools(self):
        assert mode_requires_escalation("fix bug", "read_only", ["file_patch_dry_run"])
    def test_build_mode_never_escalates(self):
        assert not mode_requires_escalation("fix bug", "build", ["file_patch_dry_run"])
    def test_auto_mode_escalates_on_build_intent(self):
        assert mode_requires_escalation("fix the bug", "auto", [])
    def test_auto_mode_no_escalation_on_read_intent(self):
        assert not mode_requires_escalation("show status", "auto", ["repo_status_read"])

class TestToolGatewayBlocking:
    def test_read_mode_blocks_file_patch_dry_run(self):
        from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
        from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
        tg = ToolGatewayV2()
        res = tg.call(ToolCallRequest(tool_name="file_patch_dry_run", args={}, mode="read_only"))
        assert res.blocked
    def test_read_mode_blocks_git_commit(self):
        from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
        from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
        tg = ToolGatewayV2()
        res = tg.call(ToolCallRequest(tool_name="git_commit_approval_required", args={}, mode="read_only"))
        assert res.blocked
    def test_build_mode_allows_git_commit_with_token(self):
        from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
        from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
        tg = ToolGatewayV2()
        res = tg.call(ToolCallRequest(tool_name="git_commit_approval_required", args={}, mode="build", approval_token="AGENTV2_APPROVED_TEST"))
        assert not res.blocked
    def test_auto_mode_blocks_file_patch(self):
        from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
        from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
        tg = ToolGatewayV2()
        res = tg.call(ToolCallRequest(tool_name="file_patch_dry_run", args={}, mode="auto"))
        assert res.blocked
        assert res.approval_required

class TestSchemaModes:
    def test_modes_set(self): assert "read_only" in MODES and "build" in MODES and "auto" in MODES
    def test_legacy_map_exists(self): assert LEGACY_MODE_MAP["dry_run"] == "read_only"
