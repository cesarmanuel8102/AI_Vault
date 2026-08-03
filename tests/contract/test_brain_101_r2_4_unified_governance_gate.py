from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

from brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
from brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from brain_v9.governance.execution_gate import ExecutionGate
from brain_v9.governance.unified_gate import (
    evaluate_governed_operation,
    fail_closed_decision,
    utc_now,
    validate_gate_decision,
)


def test_unified_gate_fails_closed_for_missing_malformed_stale_and_invalid_decisions():
    assert validate_gate_decision(None).error == "missing_gate_decision"
    assert validate_gate_decision({"allowed": True}).error == "malformed_gate_decision"

    stale = fail_closed_decision("synthetic")
    stale_data = stale.to_dict()
    old = utc_now() - timedelta(seconds=900)
    stale_data["generated_utc"] = old.isoformat().replace("+00:00", "Z")
    stale_data["expires_utc"] = old.isoformat().replace("+00:00", "Z")
    assert validate_gate_decision(stale_data).error == "stale_gate_decision"

    invalid = fail_closed_decision("synthetic").to_dict()
    invalid["allowed"] = True
    invalid["blocked"] = True
    assert validate_gate_decision(invalid).error == "invalid_gate_decision"


def test_p3_is_never_allowed_even_when_the_decision_claims_allow():
    decision = evaluate_governed_operation(
        operation_class="execution",
        operation="dangerous_delete",
        risk_level="P3",
        mode="build",
        args={},
        authenticated=True,
        role="operator",
    )
    assert decision.allowed is False
    assert decision.error == "p3_denied"
    assert decision.approval_required is True

    forged = decision.to_dict()
    forged["allowed"] = True
    forged["blocked"] = False
    assert validate_gate_decision(forged).error == "p3_denied"


def test_tool_gateway_uses_unified_gate_for_patch_and_forbidden_fields():
    gateway = ToolGatewayV2()

    read_only_patch = gateway.call(
        ToolCallRequest(
            tool_name="file_patch_apply_approval_required",
            args={"path": "tmp_agent/brain_v9/main.py"},
            mode="read_only",
        )
    )
    assert read_only_patch.ok is False
    assert read_only_patch.blocked is True
    assert read_only_patch.error == "write_tool_blocked_in_read_only_mode"

    governance_dry_run = gateway.call(
        ToolCallRequest(
            tool_name="file_patch_dry_run",
            args={"path": "tmp_agent/brain_v9/governance/execution_gate.py"},
            mode="build",
        )
    )
    assert governance_dry_run.ok is False
    assert governance_dry_run.blocked is True
    assert governance_dry_run.error == "governance_file_modification_denied_by_default"

    legacy_protected_dry_run = gateway.call(
        ToolCallRequest(
            tool_name="file_patch_dry_run",
            args={"path": "tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py"},
            mode="build",
        )
    )
    assert legacy_protected_dry_run.ok is False
    assert legacy_protected_dry_run.blocked is True
    assert legacy_protected_dry_run.error == "governance_file_modification_denied_by_default"

    bypass_attempt = gateway.call(
        ToolCallRequest(
            tool_name="repo_status_read",
            args={"override_governance": True},
            mode="read_only",
        )
    )
    assert bypass_attempt.ok is False
    assert bypass_attempt.blocked is True
    assert bypass_attempt.error == "forbidden_request_field"


def test_execution_gate_routes_through_unified_model_and_preserves_p3_denial():
    gate = ExecutionGate()
    gate.enable_god_mode("contract-session")
    result = gate.check(
        "run_command",
        {"cmd": "rm -rf important"},
        session_id="contract-session",
    )
    assert result["allowed"] is False
    assert result["risk"] == "P3"
    assert result["requires_human_approval"] is True


def test_unified_gate_blocks_forbidden_runtime_surfaces():
    for target in (
        ".env",
        ".github/workflows/ci.yml",
        "memory/semantic/index.faiss",
        "financial_autonomy/live.py",
        "tmp_agent/state/runtime.json",
        "scripts/restart.ps1",
        "C:/AI_VAULT_CANONICAL/state.json",
    ):
        decision = evaluate_governed_operation(
            operation_class="patch",
            operation="file_patch_apply_approval_required",
            mode="build",
            risk_level="P2",
            target=target,
            args={"path": target, "approval_token": "AGENTV2_APPROVED_TEST"},
            approval_token="AGENTV2_APPROVED_TEST",
            authenticated=True,
            role="operator",
        )
        assert decision.allowed is False
        assert decision.error == "forbidden_target"
