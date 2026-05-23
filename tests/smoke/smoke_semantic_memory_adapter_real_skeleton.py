"""
P2-E Commit 4B: Smoke test for SemanticMemory Real Adapter Skeleton

Verifica que el esqueleto del adapter real existe, puede inicializarse,
y bloquea explícitamente escritura real.

NO escribe en memory/semantic real.
NO llama add_memory real.
NO importa FAISS.
"""

import sys
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_adapter_real import (
    SemanticMemoryRealAdapterSkeleton,
    SemanticMemoryRealAdapterStatus,
    SemanticMemoryRealWritePlan,
)


def smoke_test_real_adapter_skeleton():
    """Smoke test del esqueleto del adapter real."""
    print("=" * 60)
    print("SMOKE TEST: SemanticMemory Real Adapter Skeleton")
    print("=" * 60)
    
    # 1. Verificar que el adapter existe
    print("\n[1/5] Verificando que el adapter existe...")
    adapter = SemanticMemoryRealAdapterSkeleton()
    print(f"    Adapter: {type(adapter).__name__}")
    print("    OK: Adapter existe")
    
    # 2. Verificar contrato (dry-run solo, no escritura real)
    print("\n[2/5] Verificando contrato de seguridad...")
    summary = adapter.summarize_contract()
    assert summary["dry_run_only"] is True, "dry_run_only debe ser True"
    assert summary["allow_real_write"] is False, "allow_real_write debe ser False"
    print(f"    contract_version: {summary['contract_version']}")
    print(f"    dry_run_only: {summary['dry_run_only']}")
    print(f"    allow_real_write: {summary['allow_real_write']}")
    print("    OK: Contrato de seguridad correcto")
    
    # 3. Verificar creación de write plan
    print("\n[3/5] Verificando creación de write plan...")
    plan = adapter.build_write_plan(
        record_id="smoke_test_rec",
        text="Contenido de prueba para smoke test",
        source="smoke_test",
        content_hash="smoke_hash_12345",
        snapshot_id="smoke_snapshot_001",
    )
    assert isinstance(plan, SemanticMemoryRealWritePlan)
    assert plan.dry_run_only is True
    assert plan.allow_real_write is False
    print(f"    plan_id: {plan.plan_id}")
    print(f"    record_id: {plan.record_id}")
    print(f"    snapshot_id: {plan.snapshot_id}")
    print(f"    dry_run_only: {plan.dry_run_only}")
    print(f"    allow_real_write: {plan.allow_real_write}")
    print("    OK: Write plan creado con controles correctos")
    
    # 4. Verificar validación de plan
    print("\n[4/5] Verificando validación de write plan...")
    errors, warnings = adapter.validate_write_plan(plan)
    print(f"    Errores: {len(errors)}")
    print(f"    Warnings: {len(warnings)}")
    if errors:
        print(f"    Detalles de errores: {errors}")
    if warnings:
        print(f"    Detalles de warnings: {warnings}")
    print("    OK: Validación ejecutada")
    
    # 5. Verificar bloqueo de escritura real
    print("\n[5/5] Verificando bloqueo de escritura real...")
    result = adapter.block_real_write(plan)
    assert result.status == SemanticMemoryRealAdapterStatus.REAL_WRITE_BLOCKED
    assert result.dry_run_only is True
    assert result.allow_real_write is False
    print(f"    status: {result.status.value}")
    print(f"    dry_run_only: {result.dry_run_only}")
    print(f"    allow_real_write: {result.allow_real_write}")
    print("    OK: Escritura real bloqueada")
    
    print("\n" + "=" * 60)
    print("SMOKE_SEMANTIC_MEMORY_REAL_ADAPTER_SKELETON_OK")
    print("=" * 60)
    print("\nEstados del adapter:")
    print(f"  - CREATED: {SemanticMemoryRealAdapterStatus.CREATED.value}")
    print(f"  - READY_BLOCKED: {SemanticMemoryRealAdapterStatus.READY_BLOCKED.value}")
    print(f"  - VALIDATED_BLOCKED: {SemanticMemoryRealAdapterStatus.VALIDATED_BLOCKED.value}")
    print(f"  - REAL_WRITE_BLOCKED: {SemanticMemoryRealAdapterStatus.REAL_WRITE_BLOCKED.value}")
    print(f"  - FAILED: {SemanticMemoryRealAdapterStatus.FAILED.value}")
    
    return True


if __name__ == "__main__":
    try:
        success = smoke_test_real_adapter_skeleton()
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
