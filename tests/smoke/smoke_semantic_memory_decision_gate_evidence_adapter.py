"""
P2-E Commit 4D-DecisionGateEvidenceAdapter: Smoke Test

Valida que el adaptador funciona correctamente con evidencia real.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def main():
    """Ejecutar smoke tests del adaptador."""
    print("=" * 80)
    print("SMOKE TEST: SemanticMemoryDecisionGateEvidenceAdapter")
    print("=" * 80)
    
    try:
        from brain.semantic_memory_decision_gate_evidence_adapter import (
            SemanticMemoryDecisionGateEvidenceAdapter,
            SemanticMemoryEvidenceAdapterStatus,
        )
        from brain.semantic_memory_real_write_decision_gate import SemanticMemoryDecision
        print("[OK] Importación exitosa")
    except ImportError as e:
        print(f"[FAIL] Error importando: {e}")
        return 1
    
    # Test 1: Crear adaptador
    print("\n[Test 1] Crear adaptador...")
    adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=".")
    print("[PASS] Adaptador creado")
    
    # Test 2: Bundle válido
    print("\n[Test 2] Evaluar bundle válido...")
    valid_bundle = {
        "bundle_id": "test-valid",
        "created_at_utc": "2026-01-01T00:00:00",
        "producer": "test",
        "repo_root": "C:/AI_VAULT",
        "branch": "codex/own-capital-sustainable-return",
        "head_hash": "abc123",
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
            "no_add_memory": True,
            "no_allow_real_write_true": True,
            "no_requests_httpx": True,
            "no_semantic_memory_bridge": True,
            "no_write_ops": True,
            "no_delete_ops": True,
            "no_move_ops": True,
        },
        "test_summary": {
            "verified": True,
            "failed": 0,
            "passed": 100,
            "decision_gate_tests_passed": True,
            "p2e_regression_tests_passed": True,
        },
        "smoke_summary": {
            "verified": True,
            "failed": 0,
            "passed": 10,
            "decision_gate_smoke_ok": True,
            "p2e_regression_smokes_ok": True,
        },
    }
    
    report = adapter.evaluate_with_evidence_read_only(valid_bundle)
    
    print(f"  - Status: {report.status.value}")
    print(f"  - Decision: {report.decision}")
    print(f"  - accepted_for_decision_gate: {report.accepted_for_decision_gate}")
    print(f"  - allow_real_write: {report.allow_real_write}")
    print(f"  - dry_run_only: {report.dry_run_only}")
    print(f"  - can_execute_real_write: {report.can_execute_real_write}")
    
    assert report.status == SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE
    assert report.decision == SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE.value
    assert report.accepted_for_decision_gate is True
    assert report.allow_real_write is False
    assert report.dry_run_only is True
    assert report.can_execute_real_write is False
    print("[PASS] Bundle válido aceptado")
    
    # Test 3: Bundle inválido (git)
    print("\n[Test 3] Evaluar bundle inválido (git)...")
    invalid_git = valid_bundle.copy()
    invalid_git["git_state"] = {
        "verified": True,
        "pending_commits_vs_origin": 1,
        "staged_files": [],
    }
    
    report = adapter.evaluate_with_evidence_read_only(invalid_git)
    
    print(f"  - Status: {report.status.value}")
    print(f"  - Decision: {report.decision}")
    
    assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
    print("[PASS] Bundle inválido (git) bloqueado")
    
    # Test 4: Bundle inválido (risk)
    print("\n[Test 4] Evaluar bundle inválido (risk)...")
    invalid_risk = valid_bundle.copy()
    invalid_risk["risk_summary"] = {
        "verified": True,
        "unresolved_high_risk_count": 1,
    }
    
    report = adapter.evaluate_with_evidence_read_only(invalid_risk)
    
    print(f"  - Status: {report.status.value}")
    print(f"  - Decision: {report.decision}")
    
    assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
    print("[PASS] Bundle inválido (risk) bloqueado")
    
    # Test 5: Block adapter
    print("\n[Test 5] Verificar block_adapter...")
    blocked = adapter.block_adapter("Smoke test")
    
    assert blocked.status == SemanticMemoryEvidenceAdapterStatus.BLOCKED
    assert blocked.allow_real_write is False
    assert blocked.can_execute_real_write is False
    print("[PASS] block_adapter funciona correctamente")
    
    # Resumen
    print("\n" + "=" * 80)
    print("SMOKE_SEMANTIC_MEMORY_DECISION_GATE_EVIDENCE_ADAPTER_OK")
    print("=" * 80)
    print("\nEstado: Adaptador integra EvidenceContract con DecisionGate")
    print("Seguridad: allow_real_write=False, dry_run_only=True, can_execute_real_write=False")
    print("\nPróximo paso: Revisión humana para P2-E Commit 4D")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
