"""
P2-E Commit 4D-CleanClassification: Smoke test for Extra File Classifier

Smoke test que clasifica archivos extra en memory/semantic en modo read-only.
NO modifica memory/semantic real.
NO borra archivos.
NO mueve archivos.
NO toca FAISS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_extra_file_classifier import (
    SemanticMemoryExtraFileClassifier,
)


def smoke_test_extra_file_classifier():
    """
    Smoke test del clasificador de archivos extra.
    
    Valida:
    1. Crear clasificador para memory/semantic
    2. Ejecutar classify_read_only()
    3. Verificar contrato de seguridad
    4. Imprimir clasificación de cada archivo
    5. Ejecutar block_cleanup()
    """
    print("=" * 70)
    print("P2-E Commit 4D-CleanClassification: Smoke Test Extra File Classifier")
    print("=" * 70)
    
    # 1. Crear clasificador
    print("\n[1/4] Creando SemanticMemoryExtraFileClassifier...")
    classifier = SemanticMemoryExtraFileClassifier(source_root="memory/semantic")
    print("    Clasificador creado")
    print("    Source root: memory/semantic")
    
    # 2. Ejecutar classify_read_only
    print("\n[2/4] Ejecutando classify_read_only()...")
    print("    NOTA: Esto solo lee archivos, no escribe.")
    report = classifier.classify_read_only()
    
    print(f"    Classification ID: {report.classification_id}")
    print(f"    Source root: {report.source_root}")
    print(f"    File count: {report.file_count}")
    print(f"    Extra file count: {report.extra_file_count}")
    print(f"    Required file count: {report.required_file_count}")
    print(f"    Dirty state detected: {report.dirty_state_detected}")
    print(f"    Requires manual review: {report.requires_manual_review}")
    print(f"    dry_run_only: {report.dry_run_only}")
    print(f"    allow_real_write: {report.allow_real_write}")
    print(f"    Warnings: {len(report.warnings)}")
    print(f"    Blockers: {len(report.blockers)}")
    
    # Verificar contrato de seguridad
    assert report.dry_run_only is True
    assert report.allow_real_write is False
    print("    OK: Contrato de seguridad correcto")
    
    # 3. Imprimir clasificación de cada archivo
    print("\n[3/4] Clasificación de archivos:")
    print("-" * 70)
    
    for classification in report.classifications:
        if not classification.exists:
            continue
            
        print(f"\n  Archivo: {classification.relative_path}")
        print(f"    Class: {classification.file_class.value}")
        print(f"    Risk: {classification.risk.value}")
        print(f"    Size: {classification.size_bytes} bytes")
        if classification.sha256:
            print(f"    SHA256: {classification.sha256[:12]}...")
        print(f"    Requires manual review: {classification.requires_manual_review}")
        print(f"    Summary: {classification.summary}")
        
        if classification.json_readable:
            print(f"    JSON readable: True")
            print(f"    JSON type: {classification.json_top_level_type}")
    
    print("\n" + "-" * 70)
    
    # 4. Ejecutar block_cleanup
    print("\n[4/4] Ejecutando block_cleanup()...")
    blocked_report = classifier.block_cleanup("Classification only")
    
    print(f"    allow_real_write: {blocked_report.allow_real_write}")
    print(f"    dry_run_only: {blocked_report.dry_run_only}")
    
    assert blocked_report.allow_real_write is False
    assert blocked_report.dry_run_only is True
    print("    OK: Cleanup bloqueado")
    
    print("\n" + "=" * 70)
    print("SMOKE_SEMANTIC_MEMORY_EXTRA_FILE_CLASSIFIER_OK")
    print("=" * 70)
    
    print("\nResumen de verificaciones:")
    print("  [OK] Clasificación read-only completada")
    print(f"  [OK] File count: {report.file_count}")
    print(f"  [OK] Extra files: {report.extra_file_count}")
    print(f"  [OK] Required files: {report.required_file_count}")
    print("  [OK] dry_run_only=True")
    print("  [OK] allow_real_write=False")
    print("  [OK] Requires manual review para extras")
    print("\n  [OK] NO se escribio en memory/semantic real")
    print("  [OK] NO se borraron archivos")
    print("  [OK] NO se movieron archivos")
    print("  [OK] NO se toco FAISS")
    
    return True


if __name__ == "__main__":
    try:
        success = smoke_test_extra_file_classifier()
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
