"""
FRONT-REAL-CANARY-APPROVAL-01: Approve canary execution package — validation smoke test.

Validates that the canary approval package document exists, is complete,
and explicitly declares that it does NOT execute the canary write.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_CANARY_APPROVAL_01_EXECUTION_PACKAGE.md"
CANARY_PLAN_PATH = REPO_ROOT / "docs" / "FRONT_REAL_CANARY_PLAN_01_SINGLE_RECORD_CANARY.md"
APPROVAL_GATE_PATH = REPO_ROOT / "docs" / "FRONT_REAL_APPROVAL_01_OPERATOR_APPROVAL_GATE.md"


class TestFrontRealCanaryApproval01:
    """Smoke tests for FRONT-REAL-CANARY-APPROVAL-01 canary approval package."""

    def test_canary_approval_doc_exists(self):
        assert APPROVAL_DOC_PATH.exists(), (
            f"Canary approval doc not found at {APPROVAL_DOC_PATH}"
        )

    def test_canary_approval_declares_no_execution(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "does not execute the canary write" in content.lower() or (
            "no ejecuta el canary write" in content.lower()
        ), (
            "Approval package must state it does not execute the canary write"
        )
        assert "no real write is permitted" in content.lower(), (
            "Approval package must state no real write is permitted"
        )

    def test_canary_approval_references_canary_plan(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "FRONT-REAL-CANARY-PLAN-01" in content, (
            "Approval package must reference FRONT-REAL-CANARY-PLAN-01"
        )

    def test_canary_approval_references_operator_gate(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "FRONT-REAL-APPROVAL-01" in content, (
            "Approval package must reference FRONT-REAL-APPROVAL-01"
        )

    def test_canary_approval_names_target_store(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "semantic_memory.jsonl" in content, (
            "Approval package must name exact target store"
        )

    def test_canary_approval_names_token_env_var(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN" in content, (
            "Approval package must name exact token env var"
        )

    def test_canary_approval_requires_double_confirmation(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "double confirmation" in content.lower() or (
            "doble confirmación" in content.lower() or "doble confirmacion" in content.lower()
        ), (
            "Approval package must require double confirmation"
        )
        assert "confirmation 1" in content.lower() or "confirmación 1" in content.lower(), (
            "Approval package must describe two confirmations"
        )

    def test_canary_approval_requires_runtime_stopped(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "runtime" in content.lower() and "stopped" in content.lower() or (
            "runtime" in content.lower() and "detenido" in content.lower()
        ), (
            "Approval package must require runtime stopped"
        )

    def test_canary_approval_requires_git_clean(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "git" in content.lower() and "clean" in content.lower() or (
            "git" in content.lower() and "limpio" in content.lower()
        ), (
            "Approval package must require git clean"
        )

    def test_canary_approval_requires_backup(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "backup" in content.lower(), "Approval package must require backup"

    def test_canary_approval_requires_hash_before_after(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "sha256" in content.lower() or "hash" in content.lower(), (
            "Approval package must require hash verification"
        )
        assert "before" in content.lower() and "after" in content.lower(), (
            "Approval package must mention before and after hash"
        )

    def test_canary_approval_requires_retrieval_verification(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "retrieval" in content.lower(), (
            "Approval package must require retrieval verification"
        )

    def test_canary_approval_requires_rollback_verification(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "rollback" in content.lower(), (
            "Approval package must require rollback verification"
        )

    def test_canary_approval_has_go_no_go_checklist(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "go/no-go" in content.lower() or "go / no-go" in content.lower() or (
            "go no go" in content.lower()
        ), (
            "Approval package must have Go/No-Go checklist"
        )

    def test_canary_approval_has_explicit_blockers(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "blockers" in content.lower() or "bloqueadores" in content.lower() or (
            "blocked" in content.lower() or "bloqueado" in content.lower()
        ), (
            "Approval package must define explicit blockers"
        )
        assert "token" in content.lower() and "blocked" in content.lower() or (
            "token" in content.lower() and "bloqueado" in content.lower() or (
                "token" in content.lower() and "blockers" in content.lower()
            )
        ), (
            "Approval package must list token as blocker"
        )

    def test_canary_approval_forbids_faiss_write(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "faiss" in content.lower() or "FAISS" in content, (
            "Approval package must forbid FAISS write"
        )

    def test_canary_approval_forbids_trading_b8(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "trading" in content.lower() and "b8" in content.lower(), (
            "Approval package must block trading and B8"
        )

    def test_canary_approval_forbids_patch_application(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "patch" in content.lower(), (
            "Approval package must forbid patch application"
        )

    def test_canary_approval_requires_future_execution_front(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "future execution" in content.lower() or "futura" in content.lower() or (
            "frente futuro" in content.lower() or "separate future front" in content.lower()
        ), (
            "Approval package must require future execution front"
        )
        assert "canary-exec" in content.lower() or "CANARY-EXEC" in content.upper() or (
            "execution front" in content.lower()
        ), (
            "Approval package must name canary execution front"
        )

    def test_canary_approval_has_evidence_requirements(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "evidence" in content.lower(), (
            "Approval package must define evidence requirements"
        )

    def test_canary_approval_has_ledger_requirements(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "ledger" in content.lower(), (
            "Approval package must define ledger requirements"
        )

    def test_canary_approval_does_not_authorize_real_write(self):
        content = APPROVAL_DOC_PATH.read_text(encoding="utf-8")
        assert "does not authorize" in content.lower() or (
            "no autoriza" in content.lower()
        ), (
            "Approval package must state it does not authorize real write"
        )
        assert "until a future front" in content.lower() or (
            "hasta un frente futuro" in content.lower()
        ), (
            "Approval package must require future front for execution"
        )
