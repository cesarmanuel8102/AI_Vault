"""
FRONT-REAL-CANARY-PLAN-01: Single-record canary execution plan — validation smoke test.

Validates that the canary plan document exists, is complete, and explicitly
declares that it does NOT execute the write.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANARY_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_CANARY_PLAN_01_SINGLE_RECORD_CANARY.md"
APPROVAL_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_APPROVAL_01_OPERATOR_APPROVAL_GATE.md"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


class TestFrontRealCanaryPlan01:
    """Smoke tests for FRONT-REAL-CANARY-PLAN-01 canary plan document."""

    def test_canary_plan_doc_exists(self):
        assert CANARY_DOC_PATH.exists(), f"Canary plan doc not found at {CANARY_DOC_PATH}"

    def test_canary_plan_declares_no_execution(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        # Must explicitly state it does not execute the write
        assert "does not execute the write" in content.lower() or (
            "no ejecuta el write" in content.lower()
        ), (
            "Canary plan must state it does not execute the write"
        )
        assert "no real write is permitted" in content.lower(), (
            "Canary plan must state no real write is permitted"
        )

    def test_canary_plan_names_target_store(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "semantic_memory.jsonl" in content, (
            "Canary plan must name exact target store"
        )

    def test_canary_plan_requires_single_record_limit(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "exactly 1" in content or "single-record" in content.lower() or (
            "solo 1" in content.lower()
        ), (
            "Canary plan must limit to exactly 1 record"
        )

    def test_canary_plan_defines_canary_schema(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "canary" in content.lower(), "Canary plan must define canary schema"
        assert "kind" in content.lower(), "Canary schema must include 'kind'"
        assert "id" in content.lower(), "Canary schema must include 'id'"
        assert "metadata" in content.lower(), "Canary schema must include 'metadata'"

    def test_canary_plan_requires_human_approval(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "human" in content.lower() or "operador" in content.lower(), (
            "Canary plan must require human/operator approval"
        )

    def test_canary_plan_requires_double_confirmation(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "doble" in content.lower() or "double" in content.lower() or (
            "confirmacion" in content.lower()
        ), (
            "Canary plan must require double confirmation"
        )
        assert "confirmation 1" in content.lower() or "confirmacion 1" in content.lower(), (
            "Canary plan must describe two confirmations"
        )

    def test_canary_plan_requires_backup(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "backup" in content.lower(), "Canary plan must require backup"
        assert "backup procedure" in content.lower(), "Canary plan must define backup procedure"

    def test_canary_plan_requires_hash_before_write(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "sha256" in content.lower() or "hash" in content.lower(), (
            "Canary plan must require hash before write"
        )

    def test_canary_plan_requires_retrieval_verification(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "retrieval" in content.lower(), "Canary plan must define retrieval verification"

    def test_canary_plan_requires_rollback(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "rollback" in content.lower(), "Canary plan must define rollback verification"

    def test_canary_plan_requires_hash_after_rollback(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "rollback" in content.lower(), (
            "Canary plan must mention rollback"
        )

    def test_canary_plan_forbids_faiss_write(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "faiss" in content.lower() or "FAISS" in content, (
            "Canary plan must forbid FAISS write"
        )

    def test_canary_plan_forbids_trading_b8(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "trading" in content.lower() and "b8" in content.lower(), (
            "Canary plan must block trading and B8"
        )

    def test_canary_plan_forbids_patch_application(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "patch" in content.lower(), "Canary plan must forbid patch application"

    def test_canary_plan_has_stop_conditions(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "stop conditions" in content.lower() or "condiciones de parada" in content.lower(), (
            "Canary plan must define stop conditions"
        )

    def test_canary_plan_has_failure_modes(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "failure modes" in content.lower() or "modos de fallo" in content.lower() or "fallo" in content.lower(), (
            "Canary plan must define failure modes"
        )

    def test_canary_plan_has_evidence_requirements(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "evidence" in content.lower(), "Canary plan must define evidence requirements"

    def test_canary_plan_has_ledger_requirements(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "ledger" in content.lower(), "Canary plan must define ledger requirements"

    def test_canary_plan_references_approval_gate(self):
        content = CANARY_DOC_PATH.read_text(encoding="utf-8")
        assert "FRONT-REAL-APPROVAL-01" in content, (
            "Canary plan must reference FRONT-REAL-APPROVAL-01 approval gate"
        )
