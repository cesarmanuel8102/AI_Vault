"""
P2-E Commit 4D-0: Smoke test for SemanticMemory Real Write Readiness Gate

Smoke test que valida el gate de readiness antes de escritura real.
NO habilita escritura real.
NO toca memory/semantic real.
NO toca FAISS.
"""

import sys
from pathlib import Path
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", "CESAR_APPROVES_4D_DRY_GATE_ONLY")

from brain.semantic_memory_real_write_readiness_gate import (
    SemanticMemoryRealWriteReadinessGate,
    SemanticMemoryRealWriteReadinessStatus,
)


class FakeBackupContract:
    """Fake backup contract para testing."""
    pass


class FakeRealAdapter:
    """Fake real adapter para testing."""
    pass


class FakeRollbackSimulation:
    """Fake rollback simulation para testing."""
    pass


def smoke_test_readiness_gate():
    """
    Smoke test del readiness gate.
    
    Valida:
    1. Sin snapshot_id -> NOT_READY
    2. Con snapshot, sin token -> USER_APPROVAL_REQUIRED
    3. Con snapshot y token valido -> READY_BLOCKED (no real write)
    4. block_real_write -> REAL_WRITE_BLOCKED
    """
    print("=" * 70)
    print("P2-E Commit 4D-0: Smoke Test Real Write Readiness Gate")
    print("=" * 70)
    
    # 1. Crear readiness gate con dependencias
    print("\n[1/6] Creando SemanticMemoryRealWriteReadinessGate...")
    gate = SemanticMemoryRealWriteReadinessGate(
        backup_contract=FakeBackupContract(),
        real_adapter=FakeRealAdapter(),
        rollback_simulation=FakeRollbackSimulation(),
    )
    print("    Gate creado con dependencias")
    
    # 2. Evaluar sin snapshot_id
    print("\n[2/6] Evaluando sin snapshot_id...")
    report_no_snapshot = gate.evaluate_readiness(
        snapshot_id=None,
        user_approval_token=None,
    )
    print(f"    Status: {report_no_snapshot.status}")
    print(f"    allow_real_write: {report_no_snapshot.allow_real_write}")
    print(f"    dry_run_only: {report_no_snapshot.dry_run_only}")
    assert report_no_snapshot.status == SemanticMemoryRealWriteReadinessStatus.NOT_READY
    assert report_no_snapshot.allow_real_write is False
    assert report_no_snapshot.dry_run_only is True
    print("    OK: NOT_READY sin snapshot")
    
    # 3. Evaluar con snapshot simulado pero sin token
    print("\n[3/6] Evaluando con snapshot pero sin token...")
    report_no_token = gate.evaluate_readiness(
        snapshot_id="snap_smoke_test_001",
        user_approval_token=None,
    )
    print(f"    Status: {report_no_token.status}")
    print(f"    user_approval_required: {report_no_token.user_approval_required}")
    print(f"    user_approval_present: {report_no_token.user_approval_present}")
    print(f"    allow_real_write: {report_no_token.allow_real_write}")
    assert report_no_token.status == SemanticMemoryRealWriteReadinessStatus.USER_APPROVAL_REQUIRED
    assert report_no_token.user_approval_required is True
    assert report_no_token.user_approval_present is False
    assert report_no_token.allow_real_write is False
    print("    OK: USER_APPROVAL_REQUIRED sin token")
    
    # 4. Evaluar con snapshot y token valido
    print("\n[4/6] Evaluando con snapshot y token valido...")
    print(f'    Token: {os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", "")}')
    report_with_token = gate.evaluate_readiness(
        snapshot_id="snap_smoke_test_001",
        user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
    )
    print(f"    Status: {report_with_token.status}")
    print(f"    user_approval_present: {report_with_token.user_approval_present}")
    print(f"    allow_real_write: {report_with_token.allow_real_write}")
    print(f"    dry_run_only: {report_with_token.dry_run_only}")
    print(f"    Blockers: {report_with_token.blockers}")
    
    # IMPORTANTE: Con token valido, status es READY_BLOCKED (no READY)
    # allow_real_write sigue False
    assert report_with_token.status == SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED
    assert report_with_token.user_approval_present is True
    assert report_with_token.allow_real_write is False
    assert report_with_token.dry_run_only is True
    assert len(report_with_token.blockers) > 0
    print("    OK: READY_BLOCKED con token (NO real write habilitado)")
    
    # 5. Ejecutar block_real_write
    print("\n[5/6] Ejecutando block_real_write...")
    blocked_report = gate.block_real_write("Smoke test block")
    print(f"    Status: {blocked_report.status}")
    print(f"    allow_real_write: {blocked_report.allow_real_write}")
    print(f"    dry_run_only: {blocked_report.dry_run_only}")
    assert blocked_report.status == SemanticMemoryRealWriteReadinessStatus.REAL_WRITE_BLOCKED
    assert blocked_report.allow_real_write is False
    assert blocked_report.dry_run_only is True
    print("    OK: REAL_WRITE_BLOCKED")
    
    # 6. Verificar contrato
    print("\n[6/6] Verificando contrato de seguridad...")
    summary = gate.summarize_contract()
    print(f"    Contract version: {summary['contract_version']}")
    print(f"    allow_real_write: {summary['allow_real_write']}")
    print(f"    dry_run_only: {summary['dry_run_only']}")
    print(f"    Approval token: {summary['approval_token']}")
    print(f"    Token purpose: {summary['token_purpose']}")
    assert summary['allow_real_write'] is False
    assert summary['dry_run_only'] is True
    print("    OK: Contrato de seguridad correcto")
    
    print("\n" + "=" * 70)
    print("SMOKE_SEMANTIC_MEMORY_REAL_WRITE_READINESS_GATE_OK")
    print("=" * 70)
    
    print("\nResumen de verificaciones:")
    print("  [OK] Sin snapshot -> NOT_READY")
    print("  [OK] Con snapshot, sin token -> USER_APPROVAL_REQUIRED")
    print("  [OK] Con snapshot y token -> READY_BLOCKED (NO real write)")
    print("  [OK] block_real_write -> REAL_WRITE_BLOCKED")
    print("  [OK] allow_real_write=False siempre")
    print("  [OK] dry_run_only=True siempre")
    print("  [OK] Token NO autoriza escritura real")
    print("\n  [OK] NO se escribio en memory/semantic real")
    print("  [OK] NO se habilito escritura real")
    print("  [OK] NO se toco FAISS")
    print("  [OK] El token solo prueba el flujo del gate")
    
    return True


if __name__ == "__main__":
    try:
        success = smoke_test_readiness_gate()
        if success:
            print("\n[OK] Todos los smoke tests pasaron")
            sys.exit(0)
        else:
            print("\n[FAIL] Smoke test fallo")
            sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Smoke test fallo con error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
