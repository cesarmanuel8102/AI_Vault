"""
P2-D Smoke Test: CurationValidationAdapter usage demonstration

Muestra uso del adapter SIN runtime/chat, SIN SemanticMemoryBridge, SIN FAISS.
NO modifica validated_at.
NO activa autoaprendizaje.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.information_curator import InformationCurator, CuratedRecord, QualityLevel
from brain.curation_validation_adapter import (
    CurationValidationAdapter,
    CurationValidationStatus,
    CurationValidationResult
)


# Fake/Mock LearningValidator determinístico
class FakeValidationStrategy(str, Enum):
    CAPABILITY_ASSESSMENT = "capability_assessment"
    TEST_QUESTIONS = "test_questions"
    CONSISTENCY_CHECK = "consistency_check"


@dataclass
class FakeStrategyResult:
    strategy: FakeValidationStrategy
    score: float
    weight: float
    details: str
    passed: bool


@dataclass
class FakeValidationResult:
    """Mock ValidationResult para testing sin dependencias externas."""
    learning_id: str
    status: str  # "PENDING", "VALIDATED", "UNVALIDATED", "PARTIAL"
    overall_score: float
    quality_gate: float
    passed: bool
    strategy_results: List[FakeStrategyResult]
    recommendations: List[str]
    timestamp: float


class FakeLearningValidator:
    """Mock de LearningValidator que devuelve resultados determinísticos."""
    
    def __init__(self, min_score: float = 0.7):
        self.min_score = min_score
        self._call_log = []
    
    def validate(self, learning_id: str, content: str, context: Dict[str, Any],
                 before_state: Optional[Dict] = None,
                 after_state: Optional[Dict] = None) -> FakeValidationResult:
        """Simula validación de contenido."""
        self._call_log.append(learning_id)
        
        # Simulación determinística basada en contenido
        if not content or len(content.strip()) < 10:
            return FakeValidationResult(
                learning_id=learning_id,
                status="UNVALIDATED",
                overall_score=0.3,
                quality_gate=self.min_score,
                passed=False,
                strategy_results=[
                    FakeStrategyResult(
                        strategy=FakeValidationStrategy.CAPABILITY_ASSESSMENT,
                        score=0.2,
                        weight=0.3,
                        details="Content too short",
                        passed=False
                    )
                ],
                recommendations=["Expand content"],
                timestamp=0.0
            )
        
        if "contradiction" in content.lower():
            return FakeValidationResult(
                learning_id=learning_id,
                status="PARTIAL",
                overall_score=0.5,
                quality_gate=self.min_score,
                passed=False,
                strategy_results=[
                    FakeStrategyResult(
                        strategy=FakeValidationStrategy.CONSISTENCY_CHECK,
                        score=0.4,
                        weight=0.2,
                        details="Potential contradiction detected",
                        passed=False
                    )
                ],
                recommendations=["Review for contradictions"],
                timestamp=0.0
            )
        
        # Caso exitoso
        return FakeValidationResult(
            learning_id=learning_id,
            status="VALIDATED",
            overall_score=0.85,
            quality_gate=self.min_score,
            passed=True,
            strategy_results=[
                FakeStrategyResult(
                    strategy=FakeValidationStrategy.CAPABILITY_ASSESSMENT,
                    score=0.9,
                    weight=0.3,
                    details="Capability improved",
                    passed=True
                ),
                FakeStrategyResult(
                    strategy=FakeValidationStrategy.TEST_QUESTIONS,
                    score=0.8,
                    weight=0.25,
                    details="Questions answered correctly",
                    passed=True
                )
            ],
            recommendations=["Ready for promotion"],
            timestamp=0.0
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
    
    # 7. Verificaciones
    print("\n[7] Verificaciones:")
    assert result.record_id == record.record_id, "record_id preservado"
    print("  OK record_id preservado")
    
    assert result.source == record.source, "source preservado"
    print("  OK source preservado")
    
    assert result.content_hash, "content_hash generado"
    print("  OK content_hash generado")
    
    assert result.status in [
        CurationValidationStatus.VALIDATED,
        CurationValidationStatus.UNVALIDATED,
        CurationValidationStatus.REJECTED,
        CurationValidationStatus.ERROR
    ], "status valido"
    print(f"  OK status valido: {result.status.value}")
    
    assert record.validated_at is None, "validated_at NO modificado"
    print("  OK validated_at NO modificado (sigue None)")
    
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
        print(f"  ERROR: Modulos prohibidos importados: {found_forbidden}")
        raise AssertionError(f"Imports prohibidos detectados: {found_forbidden}")
    else:
        print("  OK Ningun modulo prohibido importado")
    
    print("\n" + "=" * 60)
    print("SMOKE_CURATION_VALIDATION_ADAPTER_OK")
    print("=" * 60)


if __name__ == "__main__":
    test_adapter_smoke()
