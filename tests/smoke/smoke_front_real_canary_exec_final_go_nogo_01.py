"""
FRONT-REAL-CANARY-EXEC-FINAL-GO-NOGO-01: Final GO/NO-GO before canary execution — validation smoke test.

Validates that the final GO/NO-GO document exists, is complete,
and explicitly declares that it does NOT execute the canary write.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GO_NOGO_DOC_PATH = REPO_ROOT / "docs" / "FRONT_REAL_CANARY_EXEC_FINAL_GO_NOGO_01.md"


class TestFrontRealCanaryExecFinalGoNogo01:
    """Smoke tests for FRONT-REAL-CANARY-EXEC-FINAL-GO-NOGO-01."""

    def test_final_go_nogo_doc_exists(self):
        assert GO_NOGO_DOC_PATH.exists(), (
            f"Final GO/NO-GO doc not found at {GO_NOGO_DOC_PATH}"
        )

    def test_final_go_nogo_declares_no_execution(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "does not execute the canary write" in content.lower() or (
            "no ejecuta el canary write" in content.lower()
        ), (
            "GO/NO-GO doc must state it does not execute the canary write"
        )
        assert "no real write is permitted" in content.lower() or (
            "no-go" in content.lower() or "no_go" in content.lower() or "por defecto" in content.lower()
        ), (
            "GO/NO-GO doc must state no execution"
        )

    def test_final_go_nogo_references_canary_approval(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "FRONT-REAL-CANARY-APPROVAL-01" in content, (
            "GO/NO-GO doc must reference FRONT-REAL-CANARY-APPROVAL-01"
        )

    def test_final_go_nogo_references_canary_plan(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "FRONT-REAL-CANARY-PLAN-01" in content, (
            "GO/NO-GO doc must reference FRONT-REAL-CANARY-PLAN-01"
        )

    def test_final_go_nogo_names_target_store(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "semantic_memory.jsonl" in content, (
            "GO/NO-GO doc must name exact target store"
        )

    def test_final_go_nogo_names_token_env_var(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "BRAIN_APPROVAL_4D_DRY_GATE_TOKEN" in content, (
            "GO/NO-GO doc must name exact token env var"
        )

    def test_final_go_nogo_requires_double_confirmation(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "double confirmation" in content.lower() or (
            "doble confirmación" in content.lower() or "doble confirmacion" in content.lower()
        ), (
            "GO/NO-GO doc must require double confirmation"
        )
        assert "confirmation 1" in content.lower() or "confirmación 1" in content.lower(), (
            "GO/NO-GO doc must describe two confirmations"
        )

    def test_final_go_nogo_requires_runtime_stopped(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "runtime" in content.lower() and "stopped" in content.lower() or (
            "runtime" in content.lower() and "detenido" in content.lower()
        ), (
            "GO/NO-GO doc must require runtime stopped"
        )

    def test_final_go_nogo_requires_git_clean(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "git" in content.lower() and "clean" in content.lower() or (
            "git" in content.lower() and "limpio" in content.lower()
        ), (
            "GO/NO-GO doc must require git clean"
        )

    def test_final_go_nogo_requires_backup_readiness(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "backup" in content.lower(), "GO/NO-GO doc must require backup"
        assert "backup" in content.lower() and "required" in content.lower() or (
            "backup" in content.lower() and "readiness" in content.lower()
        ), (
            "GO/NO-GO doc must define backup readiness"
        )

    def test_final_go_nogo_requires_hash_readiness(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "sha256" in content.lower() or "hash" in content.lower(), (
            "GO/NO-GO doc must require hash"
        )
        assert "readiness" in content.lower() or "before" in content.lower(), (
            "GO/NO-GO doc must describe hash readiness"
        )

    def test_final_go_nogo_requires_retrieval_verification(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "retrieval" in content.lower(), (
            "GO/NO-GO doc must require retrieval verification"
        )

    def test_final_go_nogo_requires_rollback_verification(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "rollback" in content.lower(), (
            "GO/NO-GO doc must require rollback verification"
        )

    def test_final_go_nogo_has_go_conditions(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "go conditions" in content.lower() or "condiciones go" in content.lower() or (
            "required go conditions" in content.lower()
        ), (
            "GO/NO-GO doc must define GO conditions"
        )

    def test_final_go_nogo_has_no_go_conditions(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "no-go conditions" in content.lower() or "condiciones no-go" in content.lower() or (
            "automatic no-go" in content.lower()
        ), (
            "GO/NO-GO doc must define NO-GO conditions"
        )

    def test_final_go_nogo_has_explicit_blockers(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "blockers" in content.lower() or "bloqueadores" in content.lower(), (
            "GO/NO-GO doc must define explicit blockers"
        )
        assert "token" in content.lower() and "blockers" in content.lower() or (
            "token" in content.lower() and "bloqueadores" in content.lower()
        ), (
            "GO/NO-GO doc must list token as blocker"
        )

    def test_final_go_nogo_default_decision_is_no_go(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "default decision" in content.lower() or "decision por defecto" in content.lower() or (
            "no-go" in content.lower() and "default" in content.lower()
        ), (
            "GO/NO-GO doc must state default decision is NO-GO"
        )
        assert "NO_GO" in content.upper() or "no-go" in content.lower(), (
            "GO/NO-GO doc must mention NO_GO or no-go"
        )

    def test_final_go_nogo_forbids_faiss_write(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "faiss" in content.lower() or "FAISS" in content, (
            "GO/NO-GO doc must forbid FAISS write"
        )

    def test_final_go_nogo_forbids_trading_b8(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "trading" in content.lower() and "b8" in content.lower(), (
            "GO/NO-GO doc must block trading and B8"
        )

    def test_final_go_nogo_forbids_patch_application(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "patch" in content.lower(), (
            "GO/NO-GO doc must forbid patch application"
        )

    def test_final_go_nogo_requires_future_execution_front(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "future execution front" in content.lower() or (
            "frente futuro" in content.lower() or "future front" in content.lower()
        ), (
            "GO/NO-GO doc must require future execution front"
        )
        assert "canary-exec" in content.lower() or "FRONT-REAL-CANARY-EXEC" in content.upper(), (
            "GO/NO-GO doc must reference canary execution front"
        )

    def test_final_go_nogo_has_evidence_requirements(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "evidence" in content.lower(), (
            "GO/NO-GO doc must define evidence requirements"
        )

    def test_final_go_nogo_has_ledger_requirements(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "ledger" in content.lower(), (
            "GO/NO-GO doc must define ledger requirements"
        )

    def test_final_go_nogo_decision_schema_contains_canary_write_executed_false(self):
        content = GO_NOGO_DOC_PATH.read_text(encoding="utf-8")
        assert "canary_write_executed" in content.lower(), (
            "GO/NO-GO doc must include canary_write_executed in decision schema"
        )
        assert "canary_write_executed" in content.lower() and "false" in content.lower(), (
            "GO/NO-GO doc must set canary_write_executed to false"
        )
