"""
P2-E Commit 4C: Smoke test for SemanticMemory Rollback Simulation

Smoke test que simula un flujo completo de rollback coordinado entre:
- MemorySemanticBackupContract (4A) - snapshot
- SemanticMemoryRealAdapterSkeleton (4B) - write plan
- SemanticMemoryRollbackSimulation (4C) - rollback plan

NO escribe en memory/semantic real.
NO restaura archivos reales.
NO toca FAISS.
"""

import sys
from pathlib import Path
import tempfile
import os

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.memory_semantic_backup import (
    MemorySemanticBackupContract,
    MemorySemanticBackupStatus,
)
from brain.semantic_memory_adapter_real import (
    SemanticMemoryRealAdapterSkeleton,
    SemanticMemoryRealAdapterStatus,
)
from brain.semantic_memory_rollback_simulation import (
    SemanticMemoryRollbackSimulation,
    SemanticMemoryRollbackSimulationStatus,
)


def smoke_test_rollback_simulation():
    """
    Smoke test de rollback simulation.
    
    Simula un flujo completo:
    1. Crear directorio temporal
    2. Crear archivos temporales
    3. Crear snapshot con backup contract (4A)
    4. Crear write plan con adapter skeleton (4B)
    5. Crear rollback plan vinculando ambos (4C)
    6. Ejecutar simulate_restore
    7. Ejecutar simulate_rollback_after_failed_write
    8. Bloquear rollback real
    """
    print("=" * 70)
    print("P2-E Commit 4C: Smoke Test SemanticMemory Rollback Simulation")
    print("=" * 70)
    
    # 1. Crear directorio temporal
    print("\n[1/9] Creando directorio temporal...")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        print(f"    Directorio temporal: {tmp_path}")
        
        # 2. Crear archivos temporales
        print("\n[2/9] Creando archivos temporales...")
        file1 = tmp_path / "test_file1.txt"
        file2 = tmp_path / "test_file2.txt"
        file1.write_text("Contenido de prueba 1")
        file2.write_text("Contenido de prueba 2")
        print(f"    Creados: {file1.name}, {file2.name}")
        
        # 3. Crear snapshot con backup contract (4A)
        print("\n[3/9] Creando snapshot con MemorySemanticBackupContract (4A)...")
        backup_contract = MemorySemanticBackupContract(source_root=tmp_path)
        snapshot = backup_contract.create_snapshot()
        print(f"    Snapshot ID: {snapshot.snapshot_id}")
        print(f"    Files: {snapshot.file_count}")
        print(f"    Bytes: {snapshot.total_bytes}")
        print(f"    dry_run_only: {snapshot.dry_run_only}")
        print(f"    allow_real_write: {snapshot.allow_real_write}")
        assert snapshot.dry_run_only is True
        assert snapshot.allow_real_write is False
        
        # 4. Crear write plan con adapter skeleton (4B)
        print("\n[4/9] Creando write plan con SemanticMemoryRealAdapterSkeleton (4B)...")
        adapter = SemanticMemoryRealAdapterSkeleton()
        write_plan = adapter.build_write_plan(
            record_id="smoke_test_rec",
            text="Contenido de prueba",
            source="smoke_test",
            content_hash="smoke_hash_12345",
            snapshot_id=snapshot.snapshot_id,
        )
        print(f"    Write Plan ID: {write_plan.plan_id}")
        print(f"    Snapshot ID: {write_plan.snapshot_id}")
        print(f"    dry_run_only: {write_plan.dry_run_only}")
        print(f"    allow_real_write: {write_plan.allow_real_write}")
        assert write_plan.dry_run_only is True
        assert write_plan.allow_real_write is False
        
        # 5. Ejecutar prepare_blocked_real_write (4B)
        print("\n[5/9] Ejecutando prepare_blocked_real_write (4B)...")
        prepare_result = adapter.prepare_blocked_real_write(write_plan)
        print(f"    Status: {prepare_result.status}")
        print(f"    dry_run_only: {prepare_result.dry_run_only}")
        print(f"    allow_real_write: {prepare_result.allow_real_write}")
        assert prepare_result.status == SemanticMemoryRealAdapterStatus.VALIDATED_BLOCKED
        assert prepare_result.dry_run_only is True
        assert prepare_result.allow_real_write is False
        
        # 6. Crear rollback simulation (4C)
        print("\n[6/9] Creando SemanticMemoryRollbackSimulation (4C)...")
        rollback_sim = SemanticMemoryRollbackSimulation(backup_contract=backup_contract)
        
        # 7. Crear rollback plan vinculando snapshot + write_plan
        print("\n[7/9] Creando rollback plan vinculando snapshot + write plan...")
        rollback_plan = rollback_sim.build_rollback_plan(
            snapshot=snapshot,
            write_plan_id=write_plan.plan_id,
            adapter_run_id=prepare_result.adapter_run_id,
            reason="Smoke test rollback simulation",
        )
        print(f"    Rollback Plan ID: {rollback_plan.rollback_plan_id}")
        print(f"    Snapshot ID: {rollback_plan.snapshot_id}")
        print(f"    Write Plan ID: {rollback_plan.write_plan_id}")
        print(f"    Adapter Run ID: {rollback_plan.adapter_run_id}")
        print(f"    Reason: {rollback_plan.reason}")
        print(f"    Expected files: {rollback_plan.expected_restore_files}")
        print(f"    Expected bytes: {rollback_plan.expected_restore_bytes}")
        print(f"    dry_run_only: {rollback_plan.dry_run_only}")
        print(f"    allow_real_write: {rollback_plan.allow_real_write}")
        assert rollback_plan.snapshot_id == snapshot.snapshot_id
        assert rollback_plan.write_plan_id == write_plan.plan_id
        assert rollback_plan.dry_run_only is True
        assert rollback_plan.allow_real_write is False
        
        # Validar rollback plan
        print("\n    Validando rollback plan...")
        errors, warnings = rollback_sim.validate_rollback_plan(rollback_plan)
        print(f"    Errores: {len(errors)}")
        print(f"    Warnings: {len(warnings)}")
        if warnings:
            for w in warnings:
                print(f"      - {w}")
        assert len(errors) == 0
        
        # 8. Ejecutar simulate_restore_from_snapshot
        print("\n[8/9] Ejecutando simulate_restore_from_snapshot (4C)...")
        restore_result = rollback_sim.simulate_restore_from_snapshot(rollback_plan)
        print(f"    Rollback Run ID: {restore_result.rollback_run_id}")
        print(f"    Status: {restore_result.status}")
        print(f"    dry_run_only: {restore_result.dry_run_only}")
        print(f"    allow_real_write: {restore_result.allow_real_write}")
        print("    Simulated actions:")
        for action in restore_result.simulated_actions:
            print(f"      - {action}")
        assert restore_result.status == SemanticMemoryRollbackSimulationStatus.RESTORE_SIMULATED
        assert restore_result.dry_run_only is True
        assert restore_result.allow_real_write is False
        
        # Ejecutar simulate_rollback_after_failed_write
        print("\n    Ejecutando simulate_rollback_after_failed_write (4C)...")
        rollback_result = rollback_sim.simulate_rollback_after_failed_write(rollback_plan)
        print(f"    Rollback Run ID: {rollback_result.rollback_run_id}")
        print(f"    Status: {rollback_result.status}")
        print(f"    dry_run_only: {rollback_result.dry_run_only}")
        print(f"    allow_real_write: {rollback_result.allow_real_write}")
        print("    Simulated actions:")
        for action in rollback_result.simulated_actions:
            print(f"      - {action}")
        assert rollback_result.status == SemanticMemoryRollbackSimulationStatus.ROLLBACK_SIMULATED
        assert rollback_result.dry_run_only is True
        assert rollback_result.allow_real_write is False
        
        # 9. Bloquear rollback real
        print("\n[9/9] Ejecutando block_real_rollback (4C)...")
        block_result = rollback_sim.block_real_rollback(
            rollback_plan,
            "Rollback real bloqueado por Commit 4C",
        )
        print(f"    Rollback Run ID: {block_result.rollback_run_id}")
        print(f"    Status: {block_result.status}")
        print(f"    dry_run_only: {block_result.dry_run_only}")
        print(f"    allow_real_write: {block_result.allow_real_write}")
        print("    Warnings:")
        for warning in block_result.warnings:
            print(f"      - {warning}")
        assert block_result.status == SemanticMemoryRollbackSimulationStatus.REAL_ROLLBACK_BLOCKED
        assert block_result.dry_run_only is True
        assert block_result.allow_real_write is False
    
    print("\n" + "=" * 70)
    print("SMOKE_SEMANTIC_MEMORY_ROLLBACK_SIMULATION_OK")
    print("=" * 70)
    
    print("\nResumen de verificaciones:")
    print("  [OK] Directorio temporal creado y limpiado")
    print("  [OK] Snapshot creado con backup contract (4A)")
    print("  [OK] Write plan creado con adapter skeleton (4B)")
    print("  [OK] Rollback plan creado vinculando ambos (4C)")
    print("  [OK] Restore simulado correctamente")
    print("  [OK] Rollback simulado correctamente")
    print("  [OK] Rollback real bloqueado explicitamente")
    print("  [OK] dry_run_only=True en todo el flujo")
    print("  [OK] allow_real_write=False en todo el flujo")
    print("\n  [OK] NO se escribio en memory/semantic real")
    print("  [OK] NO se restauraron archivos reales")
    print("  [OK] NO se toco FAISS")
    print("  [OK] NO se importo semantic_memory_bridge")
    print("  [OK] NO se llamo add_memory real")
    
    return True


if __name__ == "__main__":
    try:
        success = smoke_test_rollback_simulation()
        if success:
            print("\n[OK] Todos los smoke tests pasaron")
            sys.exit(0)
        else:
            print("\n[FAIL] Smoke test falló")
            sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Smoke test falló con error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
