"""
FRONT-REAL-APPROVAL-01: Operator approval gate for controlled write — validation smoke test.

Validates that the approval contract document exists, is complete,
and explicitly declares that it does NOT execute or authorize real writes.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_APPROVAL_01_OPERATOR_APPROVAL_GATE.md"
PLAN_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_PLAN_01_CONTROLLED_E2E_WRITE_PLAN.md"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
READINESS_GATE_PATH = REPO_ROOT / "brain" / "semantic_memory_real_write_readiness_gate.py"


class TestFrontRealApproval01OperatorGate:
    """Smoke tests for FRONT-REAL-APPROVAL-01 approval contract document."""

    def test_approval_doc_exists(self):
        assert APPROVAL_DOC_PATH.exists(), f"Approval doc not found at {APPROVAL_DOC_PATH}"

    def test_approval_doc_declares_no_execution(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        # Must explicitly state it does not authorize execution
        assert "does not execute or authorize a real write by itself" in content.lower() or (
            "no autoriza ejecucion por si mismo" in content.lower()
        ), (
            "Approval doc must declare it does not execute or authorize real writes"
        )
        assert "no real write is permitted" in content.lower() or (
            "no real write is permitted" in content.lower()
        ), (
            "Approval doc must state no real write is permitted"
        )

    def test_approval_doc_requires_human_approval(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "human" in content.lower() or "operador" in content.lower(), (
            "Approval doc must require human/operator approval"
        )
        assert "confirmacion 1" in content.lower() or "approval 1" in content.lower() or (
            "confirmacion" in content.lower() and "confirmacion 2" in content.lower()
        ), (
            "Approval doc must describe two confirmations"
        )

    def test_approval_doc_requires_double_confirmation(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "doble confirmacion" in content.lower() or "double confirmation" in content.lower(), (
            "Approval doc must require double confirmation"
        )
        assert "requires_second_confirmation" in content.lower() or (
            "segunda confirmacion" in content.lower()
        ), (
            "Approval doc must mention second confirmation"
        )

    def test_approval_doc_names_token_env_var(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN" in content, (
            "Approval doc must name the exact token env var"
        )

    def test_approval_doc_defines_fail_closed_behavior(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "fail-closed" in content.lower() or "fail closed" in content.lower(), (
            "Approval doc must define fail-closed behavior"
        )
        assert "BLOCKED" in content.upper(), "Approval doc must mention BLOCKED state"
        # Should mention at least some blocked conditions
        blocked_conditions = ["token ausente", "token vacio", "token invalido", "token missing", "token empty", "token invalid"]
        assert any(bc in content.lower() for bc in blocked_conditions), (
            "Approval doc must detail some blocked conditions"
        )

    def test_approval_doc_forbids_secret_printing(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "no se loguea" in content.lower() or "not logged" in content.lower() or (
            "no se imprime" in content.lower() or "not printed" in content.lower()
        ), (
            "Approval doc must forbid logging/printing tokens"
        )

    def test_approval_doc_blocks_missing_token(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "token ausente" in content.lower() or "BLOCKED" in content.upper(), (
            "Approval doc must block when token is missing"
        )

    def test_approval_doc_blocks_single_confirmation(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert (
            "solo 1 confirmacion" in content.lower()
            or "solo una confirmacion" in content.lower()
            or "single confirmation" in content.lower()
            or "falta segunda confirmacion" in content.lower()
        ), (
            "Approval doc must block when only one confirmation present"
        )

    def test_approval_doc_blocks_faiss_write(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "faiss" in content.lower() or "FAISS" in content, (
            "Approval doc must block FAISS writes"
        )

    def test_approval_doc_blocks_trading_b8(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        trading_b8 = content.lower()
        assert "trading" in trading_b8 and "b8" in trading_b8, (
            "Approval doc must block trading and B8"
        )

    def test_approval_doc_blocks_patch_application(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "patch" in content.lower(), "Approval doc must block patch application"

    def test_approval_doc_requires_preflight(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "preflight" in content.lower(), "Approval doc must require preflight"

    def test_approval_doc_requires_evidence(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "evidence" in content.lower(), "Approval doc must require evidence"

    def test_approval_doc_has_stop_conditions(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "stop conditions" in content.lower() or "condiciones de parada" in content.lower(), (
            "Approval doc must define stop conditions"
        )

    def test_approval_doc_has_safety_flags(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "safety flags" in content.lower() or "safety" in content.lower(), (
            "Approval doc must define safety flags"
        )

    def test_existing_readiness_gate_file_exists(self):
        assert READINESS_GATE_PATH.exists(), (
            f"Readiness gate module not found at {READINESS_GATE_PATH}"
        )
        # Verify it contains the token validation logic
        content = READINESS_GATE_PATH.read_text(encoding="utf-8")
        assert "hmac.compare_digest" in content, (
            "Readiness gate must use hmac.compare_digest for token validation"
        )
        assert "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN" in content, (
            "Readiness gate must reference BRAIN_APPROVAL_4D_DRY_GATE_TOKEN"
        )
        # Verify fail-closed: empty env var returns False
        assert 'os.getenv(self._ENV_VAR_NAME, "")' in content or (
            'os.getenv("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", "")' in content
        ), (
            "Readiness gate must default to empty string (fail-closed)"
        )

    def test_env_example_contains_approval_token_placeholder(self):
        assert ENV_EXAMPLE_PATH.exists(), ".env.example not found"
        content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
        assert "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN" in content, (
            ".env.example must contain BRAIN_APPROVAL_4D_DRY_GATE_TOKEN placeholder"
        )
