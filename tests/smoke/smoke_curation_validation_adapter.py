"""
P2-D Smoke Test: CurationValidationAdapter usage demonstration

Muestra uso del adapter SIN runtime/chat, SIN SemanticMemoryBridge, SIN FAISS.
NO modifica validated_at.
NO activa autoaprendizaje.
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.information_curator import InformationCurator
from brain.curation_validation_adapter import (
    CurationValidationAdapter,
    CurationValidationStatus
)
from brain.learning_validator import ValidationResult, ValidationStatus


class FakeLearningValidator:
    """Mock de LearningValidator compatible con la API real."""
    
    def __init__(self, min_score: float = 0.7):
        self.min_score = min_score
        self._call_log = []

    def validate(
        self,
        learning_id: str,
        before_state: Optional[Dict] = None,
        after_state: Optional[Dict] = None,
        topic: str = "",
        gap_id: str = "",
        knowledge_base: Optional[Dict] = None,
        test_answers: Optional[Any] = None,
        **kwargs,
    ):
        self._call_log.append({
            "learning_id": learning_id,
            "before_state": before_state,
            "after_state": after_state,
            "topic": topic,
            "gap_id": gap_id,
        })

        return ValidationResult(
            learning_id=learning_id,
            status=ValidationStatus.VALIDATED,
            overall_score=0.85,
            quality_gate="PASS",
            passed=True,
            strategy_results={},
            recommendations=["smoke validator passed"],
        )


def test_adapter_smoke():
    """Smoke test: usar adapter sin runtime/chat."""
    print("=" * 60)
    print("P2-D Smoke Test: CurationValidationAdapter")
    print("=" * 60)
    
    # 1. Crear InformationCurator
    print("\n[1] Creando InformationCurator...")
    curator = InformationCurator()
    
    # 2. Crear CuratedRecord vía ingest_text
    print("\n[2] Ingiriendo contenido...")
    record = curator.ingest_text(
        text="Python es un lenguaje de programacion de alto nivel con tipado dinamico.",
        source="python_docs",
        topic="programming"
    )
    print(f"  Record ID: {record.record_id}")
    print(f"  Source: {record.source}")
    print(f"  Topic: {record.topic}")
    print(f"  Validated at: {record.validated_at}")
    
    # 3. Crear fake validator
    print("\n[3] Creando FakeLearningValidator...")
    fake_validator = FakeLearningValidator(min_score=0.7)
    
    # 4. Crear adapter
    print("\n[4] Creando CurationValidationAdapter...")
    adapter = CurationValidationAdapter(
        validator=fake_validator
    )
    
    # 5. Validar record
    print("\n[5] Validando registro...")
    result = adapter.validate_record(record)
    
    # 6. Imprimir resultado
    print("\n[6] Resultado de validacion:")
    print(f"  Record ID: {result.record_id}")
    print(f"  Content Hash: {result.content_hash}")
    print(f"  Source: {result.source}")
    print(f"  Status: {result.status.value}")
    print(f"  Passed: {result.passed}")
    print(f"  Score: {result.score}")
    print(f"  Reason: {result.reason}")
    
    # 7. Verificaciones críticas
    print("\n[7] Verificaciones:")
    
    if result.status == CurationValidationStatus.ERROR:
        print(f"  FAIL: Status es ERROR - reason: {result.reason}")
        raise AssertionError(f"Status es ERROR: {result.reason}")
    else:
        print(f"  OK Status: {result.status.value}")
    
    assert result.status == CurationValidationStatus.VALIDATED, f"Expected VALIDATED, got {result.status.value}"
    print(f"  OK Status es VALIDATED")
    
    assert result.passed is True, f"Expected passed=True, got {result.passed}"
    print("  OK passed=True")
    
    assert result.score >= 0.7, f"Expected score >= 0.7, got {result.score}"
    print(f"  OK Score: {result.score}")
    
    assert record.validated_at is None, "validated_at NO debe modificarse"
    print("  OK validated_at sigue None")
    
    # 8. Verificar que NO importa runtime/chat
    print("\n[8] Verificando NO imports prohibidos...")
    forbidden_modules = [
        "brain_v9.core.session",
        "tmp_agent.brain_v9.main",
        "semantic_memory_bridge",
        "faiss"
    ]
    
    imported_modules = list(sys.modules.keys())
    found_forbidden = []
    
    for forbidden in forbidden_modules:
        for mod in imported_modules:
            if forbidden in mod:
                found_forbidden.append(mod)
    
    if found_forbidden:
        print(f"  FAIL: Modulos prohibidos: {found_forbidden}")
        raise AssertionError(f"Imports prohibidos: {found_forbidden}")
    else:
        print("  OK Ningun modulo prohibido")
    
    print("\n" + "=" * 60)
    print("SMOKE_CURATION_VALIDATION_ADAPTER_OK")
    print("=" * 60)


if __name__ == "__main__":
    test_adapter_smoke()
