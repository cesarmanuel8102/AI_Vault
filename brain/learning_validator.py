"""
LEARNING_VALIDATOR.PY — Validación real de aprendizaje

Reemplaza la auto-aprobación simulada de EvolucionContinua con validación
real que incluye 5 estrategias:

1. Capability Assessment (0.30): Verifica que la capacidad mejoró después del aprendizaje
2. Test Questions (0.25): Genera y evalúa preguntas sobre lo aprendido
3. Consistency Check (0.20): Verifica consistencia con conocimiento existente
4. Gap Resolution (0.15): Verifica que el gap se cerró efectivamente
5. Before/After Comparison (0.10): Compara estado antes y después

Quality gate en 0.7 — si no pasa, se marca como UNVALIDATED, no se auto-aprueba.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

log = logging.getLogger("learning_validator")


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    UNVALIDATED = "unvalidated"
    PARTIAL = "partial"


class ValidationStrategy(str, Enum):
    CAPABILITY_ASSESSMENT = "capability_assessment"
    TEST_QUESTIONS = "test_questions"
    CONSISTENCY_CHECK = "consistency_check"
    GAP_RESOLUTION = "gap_resolution"
    BEFORE_AFTER = "before_after"


@dataclass
class StrategyResult:
    """Resultado de una estrategia de validación individual."""
    strategy: ValidationStrategy
    score: float  # 0.0 - 1.0
    weight: float
    details: str
    passed: bool


@dataclass
class QuestionResult:
    """Resultado de una pregunta de validación."""
    question: str
    expected_type: str  # "factual", "procedural", "analytical"
    answer_relevance: float  # 0.0 - 1.0
    correct: bool


@dataclass
class ValidationResult:
    """Resultado completo de la validación de aprendizaje."""
    learning_id: str
    status: ValidationStatus
    overall_score: float
    quality_gate: float
    passed: bool
    strategy_results: List[StrategyResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learning_id": self.learning_id,
            "status": self.status.value,
            "overall_score": self.overall_score,
            "quality_gate": self.quality_gate,
            "passed": self.passed,
            "strategy_results": [
                {"strategy": sr.strategy.value, "score": sr.score,
                 "weight": sr.weight, "details": sr.details, "passed": sr.passed}
                for sr in self.strategy_results
            ],
            "recommendations": self.recommendations,
        }


# ─── Pesos de estrategias ─────────────────────────────────────────────────────

STRATEGY_WEIGHTS = {
    ValidationStrategy.CAPABILITY_ASSESSMENT: 0.30,
    ValidationStrategy.TEST_QUESTIONS: 0.25,
    ValidationStrategy.CONSISTENCY_CHECK: 0.20,
    ValidationStrategy.GAP_RESOLUTION: 0.15,
    ValidationStrategy.BEFORE_AFTER: 0.10,
}


class LearningValidator:
    """
    Validador real de aprendizaje con 5 estrategias.

    Diferencia con el sistema anterior:
    - ANTES: score fijo 0.85, auto-aprobación
    - AHORA: 5 métricas reales, quality gate en 0.7, UNVALIDATED si no pasa
    """

    DEFAULT_QUALITY_GATE = 0.7

    def __init__(self, quality_gate: float = None, meta_core=None):
        self.quality_gate = quality_gate or self.DEFAULT_QUALITY_GATE
        self.meta_core = meta_core
        self._validation_history: List[ValidationResult] = []

    def validate(self, learning_id: str, before_state: Dict[str, Any] = None,
                 after_state: Dict[str, Any] = None, topic: str = "",
                 gap_id: str = "", knowledge_base: Dict[str, Any] = None,
                 test_answers: List[Dict] = None) -> ValidationResult:
        """
        Ejecuta validación completa del aprendizaje.

        Args:
            learning_id: ID del ciclo de aprendizaje
            before_state: Estado del sistema antes del aprendizaje
            after_state: Estado del sistema después del aprendizaje
            topic: Tema aprendido
            gap_id: ID del gap que se intentó cerrar
            knowledge_base: Base de conocimiento para consistencia
            test_answers: Respuestas a preguntas de test
        """
        results: List[StrategyResult] = []

        # 1. Capability Assessment
        cap_result = self._assess_capability(topic, before_state, after_state)
        results.append(cap_result)

        # 2. Test Questions
        test_result = self._evaluate_test_questions(topic, test_answers)
        results.append(test_result)

        # 3. Consistency Check
        consistency_result = self._check_consistency(topic, knowledge_base, after_state)
        results.append(consistency_result)

        # 4. Gap Resolution
        gap_result = self._check_gap_resolution(gap_id, topic, after_state)
        results.append(gap_result)

        # 5. Before/After Comparison
        ba_result = self._compare_before_after(before_state, after_state)
        results.append(ba_result)

        # Calcular score ponderado
        overall_score = sum(
            r.score * r.weight for r in results
        ) / sum(r.weight for r in results)

        # Determinar si pasa el quality gate
        passed = overall_score >= self.quality_gate
        status = ValidationStatus.VALIDATED if passed else ValidationStatus.UNVALIDATED

        # Generar recomendaciones
        recommendations = self._generate_recommendations(results, overall_score)

        validation = ValidationResult(
            learning_id=learning_id,
            status=status,
            overall_score=overall_score,
            quality_gate=self.quality_gate,
            passed=passed,
            strategy_results=results,
            recommendations=recommendations,
        )

        self._validation_history.append(validation)
        return validation

    def _assess_capability(self, topic: str, before_state: Dict,
                           after_state: Dict) -> StrategyResult:
        """Estrategia 1: Verifica mejora en la capacidad relacionada."""
        if not before_state or not after_state:
            return StrategyResult(
                strategy=ValidationStrategy.CAPABILITY_ASSESSMENT,
                score=0.3,
                weight=STRATEGY_WEIGHTS[ValidationStrategy.CAPABILITY_ASSESSMENT],
                details="No hay estado before/after para comparar capacidades",
                passed=False,
            )

        # Buscar mejora en la capacidad relacionada con el topic
        before_caps = before_state.get("capabilities", {})
        after_caps = after_state.get("capabilities", {})

        improvements = []
        for cap_name, after_data in after_caps.items():
            before_data = before_caps.get(cap_name, {})
            if isinstance(before_data, dict) and isinstance(after_data, dict):
                before_conf = before_data.get("confidence", 0.0)
                after_conf = after_data.get("confidence", 0.0)
                if after_conf > before_conf:
                    improvements.append(after_conf - before_conf)

        if improvements:
            avg_improvement = sum(improvements) / len(improvements)
            score = min(1.0, avg_improvement * 5)  # Escalar: 0.2 mejora = 1.0 score
        else:
            score = 0.2

        return StrategyResult(
            strategy=ValidationStrategy.CAPABILITY_ASSESSMENT,
            score=score,
            weight=STRATEGY_WEIGHTS[ValidationStrategy.CAPABILITY_ASSESSMENT],
            details=f"Mejora en capacidades: {len(improvements)} mejoradas, avg={score:.2f}",
            passed=score >= 0.5,
        )

    def _evaluate_test_questions(self, topic: str,
                                 test_answers: List[Dict] = None) -> StrategyResult:
        """Estrategia 2: Evalúa respuestas a preguntas sobre lo aprendido."""
        if not test_answers:
            return StrategyResult(
                strategy=ValidationStrategy.TEST_QUESTIONS,
                score=0.3,
                weight=STRATEGY_WEIGHTS[ValidationStrategy.TEST_QUESTIONS],
                details="No se proporcionaron respuestas de test",
                passed=False,
            )

        correct = sum(1 for a in test_answers if a.get("correct", False))
        total = len(test_answers)
        score = correct / total if total > 0 else 0.0

        return StrategyResult(
            strategy=ValidationStrategy.TEST_QUESTIONS,
            score=score,
            weight=STRATEGY_WEIGHTS[ValidationStrategy.TEST_QUESTIONS],
            details=f"Preguntas: {correct}/{total} correctas ({score:.0%})",
            passed=score >= 0.6,
        )

    def _check_consistency(self, topic: str, knowledge_base: Dict = None,
                           after_state: Dict = None) -> StrategyResult:
        """Estrategia 3: Verifica consistencia con conocimiento existente."""
        if not knowledge_base:
            return StrategyResult(
                strategy=ValidationStrategy.CONSISTENCY_CHECK,
                score=0.5,
                weight=STRATEGY_WEIGHTS[ValidationStrategy.CONSISTENCY_CHECK],
                details="No hay base de conocimiento para verificar consistencia",
                passed=True,  # No se puede verificar, pero no es fallo
            )

        # Verificar contradicciones
        new_entries = after_state.get("new_knowledge", []) if after_state else []
        contradictions = 0
        for entry in new_entries:
            if isinstance(entry, dict):
                entry_topic = entry.get("topic", "")
                entry_value = str(entry.get("value", ""))
                # Buscar contradicciones en KB
                for kb_key, kb_val in knowledge_base.items():
                    if entry_topic and entry_topic in kb_key:
                        if str(kb_val).lower() != entry_value.lower():
                            contradictions += 1

        if new_entries:
            consistency_rate = 1.0 - (contradictions / len(new_entries))
        else:
            consistency_rate = 0.7  # Neutral

        return StrategyResult(
            strategy=ValidationStrategy.CONSISTENCY_CHECK,
            score=consistency_rate,
            weight=STRATEGY_WEIGHTS[ValidationStrategy.CONSISTENCY_CHECK],
            details=f"Consistencia: {consistency_rate:.0%} ({contradictions} contradicciones de {len(new_entries)} entradas)",
            passed=consistency_rate >= 0.7,
        )

    def _check_gap_resolution(self, gap_id: str, topic: str,
                               after_state: Dict = None) -> StrategyResult:
        """Estrategia 4: Verifica que el gap se cerró efectivamente."""
        if not gap_id:
            return StrategyResult(
                strategy=ValidationStrategy.GAP_RESOLUTION,
                score=0.5,
                weight=STRATEGY_WEIGHTS[ValidationStrategy.GAP_RESOLUTION],
                details="No se especificó gap_id para verificar cierre",
                passed=True,
            )

        # Si tenemos meta_core, verificar el gap
        if self.meta_core:
            for gap in self.meta_core.self_model.known_gaps:
                if gap.gap_id == gap_id:
                    if gap.resolution_status == "resolved":
                        return StrategyResult(
                            strategy=ValidationStrategy.GAP_RESOLUTION,
                            score=1.0,
                            weight=STRATEGY_WEIGHTS[ValidationStrategy.GAP_RESOLUTION],
                            details=f"Gap {gap_id} resuelto exitosamente",
                            passed=True,
                        )
                    elif gap.resolution_status == "in_progress":
                        return StrategyResult(
                            strategy=ValidationStrategy.GAP_RESOLUTION,
                            score=0.5,
                            weight=STRATEGY_WEIGHTS[ValidationStrategy.GAP_RESOLUTION],
                            details=f"Gap {gap_id} aún en progreso",
                            passed=False,
                        )

        # Fallback: verificar por after_state
        resolved_gaps = (after_state or {}).get("resolved_gaps", [])
        if gap_id in resolved_gaps:
            score = 1.0
        else:
            score = 0.3

        return StrategyResult(
            strategy=ValidationStrategy.GAP_RESOLUTION,
            score=score,
            weight=STRATEGY_WEIGHTS[ValidationStrategy.GAP_RESOLUTION],
            details=f"Gap {gap_id}: {'resuelto' if score >= 0.7 else 'pendiente'}",
            passed=score >= 0.7,
        )

    def _compare_before_after(self, before_state: Dict,
                               after_state: Dict) -> StrategyResult:
        """Estrategia 5: Compara estado antes y después."""
        if not before_state or not after_state:
            return StrategyResult(
                strategy=ValidationStrategy.BEFORE_AFTER,
                score=0.5,
                weight=STRATEGY_WEIGHTS[ValidationStrategy.BEFORE_AFTER],
                details="No hay estados before/after para comparar",
                passed=True,
            )

        # Contar métricas que mejoraron
        improvements = 0
        total_metrics = 0

        for key in set(list(before_state.keys()) + list(after_state.keys())):
            b_val = before_state.get(key)
            a_val = after_state.get(key)
            if isinstance(b_val, (int, float)) and isinstance(a_val, (int, float)):
                total_metrics += 1
                if a_val > b_val:
                    improvements += 1

        score = improvements / total_metrics if total_metrics > 0 else 0.5

        return StrategyResult(
            strategy=ValidationStrategy.BEFORE_AFTER,
            score=score,
            weight=STRATEGY_WEIGHTS[ValidationStrategy.BEFORE_AFTER],
            details=f"Mejora: {improvements}/{total_metrics} métricas mejoraron",
            passed=score >= 0.5,
        )

    def _generate_recommendations(self, results: List[StrategyResult],
                                   overall_score: float) -> List[str]:
        """Genera recomendaciones basadas en resultados."""
        recs = []
        for r in results:
            if not r.passed:
                if r.strategy == ValidationStrategy.CAPABILITY_ASSESSMENT:
                    recs.append("Practicar más la capacidad antes de validar")
                elif r.strategy == ValidationStrategy.TEST_QUESTIONS:
                    recs.append("Repasar conceptos — las preguntas de test fallaron")
                elif r.strategy == ValidationStrategy.CONSISTENCY_CHECK:
                    recs.append("Revisar contradicciones con conocimiento existente")
                elif r.strategy == ValidationStrategy.GAP_RESOLUTION:
                    recs.append("El gap no se cerró — profundizar en el tema")
                elif r.strategy == ValidationStrategy.BEFORE_AFTER:
                    recs.append("No se detectó mejora medible — reconsiderar enfoque")

        if overall_score < 0.5:
            recs.append("Score muy bajo — considerar revertir el aprendizaje")
        elif overall_score < self.quality_gate:
            recs.append(f"Score {overall_score:.2f} por debajo del gate {self.quality_gate} — necesita más trabajo")

        return recs

    def get_validation_history(self) -> List[Dict[str, Any]]:
        """Retorna historial de validaciones."""
        return [v.to_dict() for v in self._validation_history]

    def get_validation_stats(self) -> Dict[str, Any]:
        """Estadísticas de validación."""
        if not self._validation_history:
            return {"total": 0, "validated": 0, "unvalidated": 0, "pass_rate": 0.0}

        validated = sum(1 for v in self._validation_history if v.passed)
        return {
            "total": len(self._validation_history),
            "validated": validated,
            "unvalidated": len(self._validation_history) - validated,
            "pass_rate": validated / len(self._validation_history),
            "avg_score": sum(v.overall_score for v in self._validation_history) / len(self._validation_history),
        }


# ─── Singleton ─────────────────────────────────────────────────────────────────

_validator: Optional[LearningValidator] = None

def get_learning_validator(quality_gate: float = None, meta_core=None) -> LearningValidator:
    global _validator
    if _validator is None:
        _validator = LearningValidator(quality_gate, meta_core)
    return _validator
