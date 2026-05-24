"""
P2-E Commit 4D-EvidenceInjection: Smoke test para SemanticMemoryExternalEvidenceContract

Este smoke test verifica que el contrato de evidencia externa:
1. Puede ser instanciado
2. Acepta bundles de evidencia válidos
3. Bloquea allow_real_write SIEMPRE
4. Reporta el estado correctamente
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_external_evidence_contract import (
    SemanticMemoryExternalEvidenceContract,
    SemanticMemoryEvidenceStatus,
)


def run_smoke_test():
    """Ejecutar smoke test del contrato de evidencia externa."""
    
    # Crear contrato
    contract = SemanticMemoryExternalEvidenceContract(repo_root=".")
    
    # Crear bundle de evidencia válido
    bundle = {
        "bundle_id": "smoke-test-1",
        "created_at_utc": "2026-05-23T00:00:00",
        "producer": "smoke_test",
        "repo_root": str(Path(".").resolve()),
        "branch": "codex/own-capital-sustainable-return",
        "head_hash": "smoke123",
        "git_state": {
            "verified": True,
            "pending_commits_vs_origin": 0,
            "staged_files": [],
            "memory_semantic_in_commit": False,
            "tmp_agent_strategies_in_commit": False,
            "nul_in_commit": False,
            "runtime_active": False,
        },
        "risk_summary": {
            "verified": True,
            "unresolved_high_risk_count": 0,
            "unresolved_write_like_count": 0,
            "unresolved_runtime_like_count": 0,
        },
        "security_validation": {
            "verified": True,
            "no_open": True,
            "no_subprocess": True,
            "no_faiss": True,
            "no_requests_httpx": True,
            "no_semantic_memory_bridge": True,
            "no_add_memory": True,
            "no_write_ops": True,
            "no_delete_ops": True,
            "no_move_ops": True,
            "no_allow_real_write_true": True,
        },
        "test_summary": {
            "verified": True,
            "failed": 0,
            "passed": 37,
            "decision_gate_tests_passed": True,
            "p2e_regression_tests_passed": True,
        },
        "smoke_summary": {
            "verified": True,
            "failed": 0,
            "passed": 1,
            "decision_gate_smoke_ok": True,
            "p2e_regression_smokes_ok": True,
        },
    }
    
    # Validar bundle
    report = contract.validate_bundle_read_only(bundle)
    
    # Verificaciones
    assert report is not None, "Report should not be None"
    assert report.allow_real_write is False, "allow_real_write must be False"
    assert report.dry_run_only is True, "dry_run_only must be True"
    assert report.can_execute_real_write is False, "can_execute_real_write must be False"
    
    # Si el bundle es válido, debería ser ACCEPTED
    if report.status == SemanticMemoryEvidenceStatus.ACCEPTED:
        print("SMOKE_SEMANTIC_MEMORY_EXTERNAL_EVIDENCE_CONTRACT_OK")
        return 0
    else:
        print(f"SMOKE_FAILED: Status={report.status.value}, Blockers={report.blocker_count}")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
