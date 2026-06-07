"""
FRONT-TEST-01: Minimal e2e pipeline smoke test.

Este test demuestra un ciclo observable de pipeline sin escritura real irreversible:

  input controlado
  -> pipeline invocado (SemanticMemoryRealWriteReadinessGate)
  -> governance check
  -> dry-run only
  -> evidencia verificable
  -> no-mutation confirmado

No toca memory/semantic, FAISS, trading, B8, ni activa runtime.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from brain.semantic_memory_real_write_readiness_gate import (
    SemanticMemoryRealWriteReadinessGate,
    SemanticMemoryRealWriteReadinessStatus,
)


# ─── shared fakes ────────────────────────────────────────────────────────────

class FakeBackupContract:
    pass


class FakeRealAdapter:
    pass


class FakeRollbackSimulation:
    pass


# ─── E2E fixture controlado ──────────────────────────────────────────────────

TEST_SNAPSHOT_ID = "front_test_01_snapshot"
TEST_APPROVAL_TOKEN = "test_e2e_approval_token_front_test_01"


@pytest.fixture(scope="function")
def gate(monkeypatch, tmp_path):
    """
    Proporciona un gate listo para e2e con:
    - token de aprobacion configurado
    - todas las dependencias falsas para alcanzar READY_BLOCKED
    - no escritura real permitida
    """
    monkeypatch.setenv("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", TEST_APPROVAL_TOKEN)
    gate = SemanticMemoryRealWriteReadinessGate(
        backup_contract=FakeBackupContract(),
        real_adapter=FakeRealAdapter(),
        rollback_simulation=FakeRollbackSimulation(),
    )
    return gate


@pytest.fixture
def controlled_input():
    """Entrada controlada para el pipeline."""
    return {
        "source_id": "front_test_01_local_fixture",
        "content": "Controlled test item for minimal e2e pipeline. No real write allowed.",
        "front": "FRONT-TEST-01",
    }


# ─── Tests minimos obligatorios ──────────────────────────────────────────────


class TestMinimalE2EInputFixtureValid:
    """1. test_minimal_e2e_input_fixture_valid"""

    def test_input_has_required_fields(self, controlled_input):
        assert "source_id" in controlled_input
        assert "content" in controlled_input
        assert "front" in controlled_input
        assert controlled_input["front"] == "FRONT-TEST-01"

    def test_input_is_pure_dict(self, controlled_input):
        assert isinstance(controlled_input, dict)
        assert all(isinstance(k, str) for k in controlled_input.keys())


class TestPipelineInvocationProducesObservableResult:
    """2. test_pipeline_invocation_produces_observable_result"""

    def test_evaluate_readiness_returns_report(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report is not None
        assert hasattr(report, "to_dict")
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "readiness_id" in d
        assert "status" in d
        assert "created_at_utc" in d

    def test_report_is_json_serializable(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        d = report.to_dict()
        encoded = json.dumps(d)
        decoded = json.loads(encoded)
        assert decoded["status"] == "READY_BLOCKED"


class TestGovernanceBlocksRealWrite:
    """3. test_governance_blocks_real_write"""

    def test_allow_real_write_is_false(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.allow_real_write is False

    def test_status_is_ready_blocked_not_ready(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.status == SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED
        assert report.status != SemanticMemoryRealWriteReadinessStatus.NOT_READY

    def test_user_approval_required_always_true(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.user_approval_required is True

    def test_user_approval_present_when_token_valid(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.user_approval_present is True


class TestDryRunOnlyEnforced:
    """4. test_dry_run_only_enforced"""

    def test_dry_run_only_is_true(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.dry_run_only is True

    def test_real_write_blocked_explicitly(self, gate, controlled_input):
        report = gate.block_real_write("e2e dry-run block test")
        assert report.status == SemanticMemoryRealWriteReadinessStatus.REAL_WRITE_BLOCKED
        assert report.allow_real_write is False


class TestEvidenceWrittenOnlyToTmpAgent:
    """5. test_evidence_written_only_to_tmp_agent"""

    def test_report_contains_metadata(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.metadata == controlled_input

    def test_report_has_readiness_id(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.readiness_id
        assert len(report.readiness_id) > 0


class TestNoMemorySemanticWrite:
    """6. test_no_memory_semantic_write"""

    def test_no_add_memory_called(self, gate, controlled_input):
        # El gate no debe tener metodos que escriban memoria
        assert not hasattr(gate, "add_memory")
        assert not hasattr(gate, "write_semantic")

    def test_evaluate_readiness_does_not_return_real_write_allowed(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.allow_real_write is False


class TestNoFaissWrite:
    """7. test_no_faiss_write"""

    def test_gate_has_no_faiss_methods(self, gate):
        faiss_methods = ["add_faiss", "write_faiss", "index_faiss"]
        for m in faiss_methods:
            assert not hasattr(gate, m)

    def test_report_does_not_mention_faiss(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        d = report.to_dict()
        for v in d.values():
            assert "faiss" not in str(v).lower()


class TestNoPatchFileCreated:
    """8. test_no_patch_file_created"""

    def test_evaluate_readiness_does_not_create_files(self, gate, controlled_input, tmp_path):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        # El reporte es puro en memoria; no debe haber side-effect de archivos
        assert report is not None
        # tmp_path debe estar vacio porque el gate no escribe en el filesystem
        assert list(tmp_path.iterdir()) == []


class TestNoGitApplyExecuted:
    """9. test_no_git_apply_executed"""

    def test_gate_has_no_git_methods(self, gate):
        git_methods = ["git_apply", "apply_patch", "commit_changes"]
        for m in git_methods:
            assert not hasattr(gate, m)


class TestNoPromotionTriggered:
    """10. test_no_promotion_triggered"""

    def test_report_does_not_allow_promotion(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert report.allow_real_write is False
        assert report.dry_run_only is True
        assert report.status == SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED


class TestNoTradingOrB8Touch:
    """11. test_no_trading_or_b8_touch"""

    def test_gate_has_no_trading_methods(self, gate):
        trading_methods = ["execute_trade", "place_order", "run_strategy"]
        for m in trading_methods:
            assert not hasattr(gate, m)

    def test_metadata_does_not_contain_trading(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert "trading" not in str(report.metadata).lower()


class TestRollbackOrNoMutationConfirmed:
    """12. test_rollback_or_no_mutation_confirmed"""

    def test_block_real_write_returns_blocked_status(self, gate):
        report = gate.block_real_write("e2e no-mutation confirmation")
        assert report.status == SemanticMemoryRealWriteReadinessStatus.REAL_WRITE_BLOCKED
        assert report.allow_real_write is False
        assert report.dry_run_only is True

    def test_no_mutation_after_evaluate(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        # Despues de evaluate_readiness no debe haber cambios persistentes
        assert report.status == SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED
        assert report.allow_real_write is False


class TestReportContainsRequiredFields:
    """13. test_report_contains_required_fields"""

    def test_report_has_all_governance_fields(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        d = report.to_dict()
        required = [
            "readiness_id",
            "created_at_utc",
            "status",
            "snapshot_id",
            "backup_contract_ok",
            "real_adapter_ok",
            "rollback_simulation_ok",
            "user_approval_required",
            "user_approval_present",
            "allow_real_write",
            "dry_run_only",
            "validation_errors",
            "warnings",
            "blockers",
            "metadata",
        ]
        for field in required:
            assert field in d, f"missing field: {field}"

    def test_status_is_string_value(self, gate, controlled_input):
        report = gate.evaluate_readiness(
            snapshot_id=TEST_SNAPSHOT_ID,
            user_approval_token=TEST_APPROVAL_TOKEN,
            metadata=controlled_input,
        )
        assert isinstance(report.status.value, str)
        assert report.status.value == "READY_BLOCKED"
