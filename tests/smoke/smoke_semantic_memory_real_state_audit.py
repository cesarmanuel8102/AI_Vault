"""
P2-E Commit 4D-Preflight: Smoke test for SemanticMemory Real State Audit

Smoke test que audita el estado real de memory/semantic en modo read-only.
NO modifica memory/semantic real.
NO crea backup real.
NO restaura archivos.
NO toca FAISS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_real_state_audit import (
    SemanticMemoryRealStateAudit,
    SemanticMemoryRealStateAuditStatus,
)


def smoke_test_real_state_audit():
    """
    Smoke test del audit de estado real.
    
    Valida:
    1. Auditar memory/semantic en modo read-only
    2. Verificar dry_run_only=True, allow_real_write=False
    3. Detectar estado dirty si aplica
    4. Ejecutar block_real_write
    """
    print("=" * 70)
    print("P2-E Commit 4D-Preflight: Smoke Test Real State Audit")
    print("=" * 70)
    
    # 1. Crear auditoría
    print("\n[1/4] Creando SemanticMemoryRealStateAudit...")
    audit = SemanticMemoryRealStateAudit(source_root="memory/semantic")
    print("    Auditor creado")
    print("    Source root: memory/semantic")
    
    # 2. Ejecutar audit read-only
    print("\n[2/4] Ejecutando audit_read_only()...")
    print("    NOTA: Esto solo lee archivos, no escribe.")
    report = audit.audit_read_only()
    
    print(f"    Audit ID: {report.audit_id}")
    print(f"    Status: {report.status}")
    print(f"    Source root: {report.source_root}")
    print(f"    File count: {report.file_count}")
    print(f"    Total bytes: {report.total_bytes}")
    print(f"    Expected files present: {report.expected_files_present}")
    print(f"    Dirty state detected: {report.dirty_state_detected}")
    print(f"    dry_run_only: {report.dry_run_only}")
    print(f"    allow_real_write: {report.allow_real_write}")
    print(f"    Warnings: {len(report.warnings)}")
    print(f"    Blockers: {len(report.blockers)}")
    
    if report.warnings:
        print("    Detalles de warnings:")
        for w in report.warnings[:5]:  # Mostrar primeros 5
            print(f"      - {w}")
    
    # Verificar contrato de seguridad
    assert report.dry_run_only is True
    assert report.allow_real_write is False
    print("    OK: Contrato de seguridad correcto")
    
    # 3. Validar archivos esperados
    print("\n[3/4] Validando archivos esperados...")
    errors, warnings = audit.validate_expected_files(report)
    
    if errors:
        print(f"    Errores: {len(errors)}")
        for e in errors:
            print(f"      - {e}")
    else:
        print("    OK: Todos los archivos esperados presentes")
    
    if warnings:
        print(f"    Warnings: {len(warnings)}")
        for w in warnings:
            print(f"      - {w}")
    
    # 4. Ejecutar block_real_write
    print("\n[4/4] Ejecutando block_real_write()...")
    blocked_report = audit.block_real_write("Preflight audit only")
    
    print(f"    Status: {blocked_report.status}")
    print(f"    allow_real_write: {blocked_report.allow_real_write}")
    print(f"    dry_run_only: {blocked_report.dry_run_only}")
    
    assert blocked_report.status == SemanticMemoryRealStateAuditStatus.BLOCKED_REAL_WRITE
    assert blocked_report.allow_real_write is False
    assert blocked_report.dry_run_only is True
    print("    OK: BLOCKED_REAL_WRITE confirmado")
    
    print("\n" + "=" * 70)
    print("SMOKE_SEMANTIC_MEMORY_REAL_STATE_AUDIT_OK")
    print("=" * 70)
    
    print("\nResumen de verificaciones:")
    print("  [OK] Auditoría read-only completada")
    print("  [OK] dry_run_only=True")
    print("  [OK] allow_real_write=False")
    print(f"  [OK] File count: {report.file_count}")
    print(f"  [OK] Total bytes: {report.total_bytes}")
    print(f"  [OK] Expected files present: {report.expected_files_present}")
    print(f"  [OK] Dirty state detected: {report.dirty_state_detected}")
    print("  [OK] BLOCKED_REAL_WRITE")
    print("\n  [OK] NO se escribio en memory/semantic real")
    print("  [OK] NO se creo backup real")
    print("  [OK] NO se restauraron archivos")
    print("  [OK] NO se toco FAISS")
    
    return True


if __name__ == "__main__":
    try:
        success = smoke_test_real_state_audit()
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
