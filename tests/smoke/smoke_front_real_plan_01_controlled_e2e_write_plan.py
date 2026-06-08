"""
FRONT-REAL-PLAN-01: Controlled real e2e write plan — validation smoke test.

Validates that the plan document exists, is complete, and explicitly
declares that it does NOT authorize execution.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "docs" / "FRONT_REAL_PLAN_01_CONTROLLED_E2E_WRITE_PLAN.md"


class TestFrontRealPlan01ControlledE2EWritePlan:
    """Smoke tests for FRONT-REAL-PLAN-01 plan document."""

    def test_plan_file_exists(self):
        assert PLAN_PATH.exists(), f"Plan file not found at {PLAN_PATH}"

    def test_plan_declares_no_execution_authorization(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        # Must contain explicit statement about not authorizing execution
        assert "does not authorize execution" in content.lower(), (
            "Plan must explicitly state it does not authorize execution"
        )
        assert "no real write is permitted" in content.lower(), (
            "Plan must state that no real write is permitted"
        )

    def test_plan_requires_human_approval(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "human approval" in content.lower() or "operator" in content.lower(), (
            "Plan must require human/operator approval"
        )
        assert "approval 1" in content.lower(), "Plan must have Approval 1 gate"
        assert "approval 2" in content.lower(), "Plan must have Approval 2 gate"

    def test_plan_requires_backup_before_write(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "backup" in content.lower(), "Plan must require backup"
        assert "backup procedure" in content.lower(), "Plan must define backup procedure"

    def test_plan_requires_single_record_limit(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "exactly 1" in content or "single-record" in content.lower(), (
            "Plan must limit write to exactly 1 record"
        )

    def test_plan_requires_rollback(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "rollback" in content.lower(), "Plan must define rollback procedure"
        assert "rollback procedure" in content.lower(), "Plan must have rollback section"

    def test_plan_requires_retrieval_verification(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "retrieval" in content.lower(), "Plan must define retrieval verification"
        assert "verification" in content.lower(), "Plan must have verification steps"

    def test_plan_forbids_faiss_write_now(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "no escribir en faiss" in content.lower() or "no faiss write" in content.lower() or "not write in faiss" in content.lower() or "no escribir en FAISS" in content, (
            "Plan must forbid FAISS write"
        )

    def test_plan_forbids_trading(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "no activar trading" in content.lower() or "no trading" in content.lower(), (
            "Plan must forbid trading activation"
        )

    def test_plan_forbids_patch_application(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "no aplicar patches" in content.lower() or "no patch" in content.lower(), (
            "Plan must forbid patch application"
        )

    def test_plan_has_stop_conditions(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "stop conditions" in content.lower(), "Plan must have stop conditions section"

    def test_plan_has_evidence_requirements(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "evidence" in content.lower(), "Plan must mention evidence requirements"

    def test_plan_has_ledger_requirements(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "ledger" in content.lower(), "Plan must mention ledger requirements"

    def test_plan_has_failure_modes(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "failure modes" in content.lower() or "fallo" in content.lower(), (
            "Plan must define failure modes"
        )

    def test_plan_names_target_store(self):
        content = PLAN_PATH.read_text(encoding="utf-8")
        assert "semantic_memory.jsonl" in content, (
            "Plan must name the exact target store: semantic_memory.jsonl"
        )
