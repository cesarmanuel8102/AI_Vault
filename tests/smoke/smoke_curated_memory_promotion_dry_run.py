"""
P2-E Smoke Test: CuratedMemoryPromotion Dry Run

Valida que el servicio CuratedMemoryPromotionService:
1. Importa correctamente
2. Ejecuta en modo dry-run (sin escribir archivos)
3. No importa FAISS ni SemanticMemory
4. No llama endpoints HTTP
5. No escribe en memory/semantic
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def check_imports():
    """Verificar que no hay imports prohibidos."""
    print("[1] Verificando imports...")
    
    forbidden_modules = [
        "faiss",
        "semantic_memory",
        "semantic_memory_faiss",
        "semantic_memory_bridge",
        "requests",
        "httpx",
        "urllib.request",
        "http.client",
    ]
    
    # Importar el módulo y verificar que no carga lo prohibido
    import brain.curated_memory_promotion as module
    
    import sys as sys_module
    loaded_modules = list(sys_module.modules.keys())
    
    violations = []
    for forbidden in forbidden_modules:
        if any(forbidden in mod for mod in loaded_modules):
            violations.append(forbidden)
    
    if violations:
        print(f"    ERROR: Módulos prohibidos cargados: {violations}")
        return False
    
    print("    OK: No hay imports prohibidos")
    return True


def create_test_record():
    """Crear un CuratedRecord de prueba."""
    print("[2] Creando CuratedRecord de prueba...")
    
    from brain.information_curator import CuratedRecord
    
    from brain.information_curator import ContentTopic, QualityLevel
    
    record = CuratedRecord(
        record_id="test_record_12345",
        content="Test content for promotion validation",
        topic=ContentTopic.GENERAL,
        quality=QualityLevel.HIGH,
        quality_score=0.95,
        source="smoke_test",
        content_hash="abc123def456"
    )
    
    print(f"    Record ID: {record.record_id}")
    print(f"    Source: {record.source}")
    print(f"    Content Hash: {record.content_hash}")
    return record


def create_test_validation_result():
    """Crear un CurationValidationResult de prueba."""
    print("[3] Creando CurationValidationResult de prueba...")
    
    from brain.curation_validation_adapter import (
        CurationValidationResult,
        CurationValidationStatus
    )
    
    result = CurationValidationResult(
        record_id="test_record_12345",
        content_hash="abc123def456",
        source="smoke_test",
        topic="smoke_test_topic",
        status=CurationValidationStatus.VALIDATED,
        validator_status="PASSED",
        passed=True,
        score=0.85,
        reason="Smoke test validation passed",
        validation_id="val_test_001"
    )
    
    print(f"    Status: {result.status.value}")
    print(f"    Score: {result.score}")
    print(f"    Passed: {result.passed}")
    return result


def test_promote_dry_run():
    """Probar promote_dry_run."""
    print("[4] Ejecutando promote_dry_run...")
    
    from brain.curated_memory_promotion import (
        CuratedMemoryPromotionService,
        PromotionStatus
    )
    
    # Crear servicio
    service = CuratedMemoryPromotionService(
        min_validation_score=0.7,
        require_approval=True
    )
    
    # Crear datos de prueba
    record = create_test_record()
    validation_result = create_test_validation_result()
    
    # Ejecutar dry-run
    plan = service.promote_dry_run(record, validation_result)
    
    # Verificaciones
    print("[5] Verificando resultado dry-run:")
    
    # Verificar dry_run=True
    assert plan.dry_run == True, f"Expected dry_run=True, got {plan.dry_run}"
    print(f"    OK: dry_run = {plan.dry_run}")
    
    # Verificar estado requiere aprobación
    assert plan.status == PromotionStatus.REQUIRES_APPROVAL, \
        f"Expected REQUIRES_APPROVAL, got {plan.status}"
    print(f"    OK: status = {plan.status.value}")
    
    # Verificar payload construido
    assert plan.memory_payload is not None, "Payload should be built"
    print(f"    OK: memory_payload construido")
    
    # Verificar campos del payload
    payload = plan.memory_payload
    assert "text" in payload, "Payload missing 'text'"
    assert "source" in payload, "Payload missing 'source'"
    assert "metadata" in payload, "Payload missing 'metadata'"
    print(f"    OK: Estructura del payload válida")
    
    # Verificar metadatos
    metadata = payload["metadata"]
    assert metadata.get("promotion_dry_run") == True, "Metadata should show dry_run"
    print(f"    OK: promotion_dry_run en metadata")
    
    return plan


def test_no_file_writes():
    """Verificar que no se escriben archivos."""
    print("[6] Verificando que no se escriben archivos...")
    
    # Verificar directorio memory/semantic no modificado
    semantic_dir = Path("memory/semantic")
    if semantic_dir.exists():
        initial_files = set(semantic_dir.glob("*"))
        
        # Ejecutar operación
        test_promote_dry_run()
        
        # Verificar que no hay cambios
        final_files = set(semantic_dir.glob("*"))
        assert initial_files == final_files, "Files were modified in memory/semantic"
    
    print("    OK: No se escribieron archivos")
    return True


def test_rejection_scenarios():
    """Probar escenarios de rechazo."""
    print("[7] Probando escenarios de rechazo...")
    
    from brain.curated_memory_promotion import (
        CuratedMemoryPromotionService,
        PromotionStatus
    )
    from brain.curation_validation_adapter import (
        CurationValidationResult,
        CurationValidationStatus
    )
    from brain.information_curator import CuratedRecord, ContentTopic, QualityLevel
    
    service = CuratedMemoryPromotionService(min_validation_score=0.7)
    
    # Test 1: No validado
    print("    [7.1] Registro no validado...")
    record = CuratedRecord(
        record_id="test1",
        content="content",
        topic=ContentTopic.GENERAL,
        quality=QualityLevel.HIGH,
        quality_score=0.8,
        source="source",
        content_hash="hash1"
    )
    
    invalid_result = CurationValidationResult(
        record_id="test1",
        content_hash="hash1",
        source="source",
        topic="test",
        status=CurationValidationStatus.REJECTED,
        validator_status="FAILED",
        passed=False,
        score=0.5,
        reason="Not validated",
        validation_id="val_test_rejected"
    )
    
    plan = service.promote_dry_run(record, invalid_result)
    assert plan.status == PromotionStatus.REJECTED_NOT_VALIDATED
    print(f"    OK: Rechazado por no validado")
    
    # Test 2: Score bajo
    print("    [7.2] Score bajo...")
    low_score_result = CurationValidationResult(
        record_id="test1",
        content_hash="hash1",
        source="source",
        topic="test",
        status=CurationValidationStatus.VALIDATED,
        validator_status="PASSED",
        passed=True,
        score=0.5,  # Menor que 0.7
        reason="Low score",
        validation_id="val_test_low"
    )
    
    plan = service.promote_dry_run(record, low_score_result)
    assert plan.status == PromotionStatus.REJECTED_LOW_SCORE
    print(f"    OK: Rechazado por score bajo")
    
    print("    OK: Todos los escenarios de rechazo pasaron")


def main():
    """Ejecutar smoke test completo."""
    print("=" * 60)
    print("P2-E Smoke Test: CuratedMemoryPromotion Dry Run")
    print("=" * 60)
    print()
    
    try:
        # Verificar imports
        if not check_imports():
            print("\nSMOKE_CURATED_MEMORY_PROMOTION_DRY_RUN_FAILED")
            return 1
        
        # Probar promote_dry_run
        plan = test_promote_dry_run()
        
        # Verificar no escritura de archivos
        test_no_file_writes()
        
        # Probar escenarios de rechazo
        test_rejection_scenarios()
        
        print()
        print("=" * 60)
        print("SMOKE_CURATED_MEMORY_PROMOTION_DRY_RUN_OK")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\nASSERTION FAILED: {e}")
        print("\nSMOKE_CURATED_MEMORY_PROMOTION_DRY_RUN_FAILED")
        return 1
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\nSMOKE_CURATED_MEMORY_PROMOTION_DRY_RUN_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
