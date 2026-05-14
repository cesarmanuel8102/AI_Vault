"""
PHASE_EVALUATOR.PY — Criterios medibles para las 7 fases de autonomía

Reemplaza las fases declarativas (autonomy_phases.py) con criterios
cuantitativos basados en datos reales del sistema:

Fase 0 (INIT):              Sistema recién arrancado
Fase 1 (MONITOR):           ≥50% capacidades con evidence_count > 0
Fase 2 (SELF_AWARE):        ≥80% capacidades con evidence_count > 10
Fase 3 (SELF_HEAL):         ≥70% de errores auto-remediados
Fase 4 (LEARN):             ≥5 ciclos de aprendizaje validados por día
Fase 5 (EVOLVE):            Tasa de éxito en self-improvement > 70%
Fase 6 (AUTONOMY):          24h+ sin intervención humana

El evaluador recopila datos reales de MetaCognitionCore, AOS,
contadores de errores y logs de actividad.
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum

log = logging.getLogger("phase_evaluator")


class AutonomyPhase(str, Enum):
    INIT = "0_init"
    MONITOR = "1_monitor"
    SELF_AWARE = "2_self_aware"
    SELF_HEAL = "3_self_heal"
    LEARN = "4_learn"
    EVOLVE = "5_evolve"
    AUTONOMY = "6_autonomy"


@dataclass
class PhaseCriterion:
    """Criterio medible para una fase de autonomía."""
    name: str
    description: str
    target_value: float
    current_value: float
    met: bool
    weight: float = 1.0


@dataclass
class PhaseEvaluation:
    """Resultado de la evaluación de una fase."""
    current_phase: AutonomyPhase
    phase_name: str
    phase_progress: float  # 0.0 - 1.0
    criteria: List[PhaseCriterion] = field(default_factory=list)
    ready_for_next: bool = False
    blocking_factors: List[str] = field(default_factory=list)
    evaluated_at: float = field(default_factory=time.time)


class PhaseEvaluator:
    """
    Evaluador de fases de autonomía con criterios medibles.

    Diferencia con el sistema anterior:
    - ANTES: fases declarativas, activación manual con scripts
    - AHORA: criterios cuantitativos, evaluación automática
    """

    def __init__(self, meta_core=None, orchestrator=None,
                 learning_validator=None):
        self.meta_core = meta_core
        self.orchestrator = orchestrator
        self.learning_validator = learning_validator
        self._last_evaluation: Optional[PhaseEvaluation] = None
        self._error_count = 0
        self._auto_remediated_count = 0
        self._validated_learnings_today = 0
        self._self_improvement_attempts = 0
        self._self_improvement_successes = 0
        self._last_human_intervention: float = time.time()
        self._operation_start: float = time.time()

    def record_error(self, auto_remediated: bool = False):
        """Registra un error del sistema."""
        self._error_count += 1
        if auto_remediated:
            self._auto_remediated_count += 1

    def record_validated_learning(self):
        """Registra un aprendizaje validado."""
        self._validated_learnings_today += 1

    def record_self_improvement(self, success: bool):
        """Registra un intento de self-improvement."""
        self._self_improvement_attempts += 1
        if success:
            self._self_improvement_successes += 1

    def record_human_intervention(self):
        """Registra una intervención humana."""
        self._last_human_intervention = time.time()

    def evaluate(self) -> PhaseEvaluation:
        """
        Evalúa la fase actual de autonomía basándose en métricas reales.
        """
        # Recopilar métricas
        metrics = self._collect_metrics()

        # Evaluar cada fase en orden
        current_phase = AutonomyPhase.INIT
        phase_progress = 0.0
        all_criteria: List[PhaseCriterion] = []
        blocking: List[str] = []

        for phase in AutonomyPhase:
            criteria = self._evaluate_phase(phase, metrics)
            all_criteria.extend(criteria)

            met_count = sum(1 for c in criteria if c.met)
            total_count = len(criteria)

            if total_count > 0 and met_count == total_count:
                current_phase = phase
                phase_progress = 1.0
            elif total_count > 0:
                partial_progress = met_count / total_count
                if partial_progress > phase_progress:
                    phase_progress = partial_progress
                    if current_phase.value <= phase.value:
                        current_phase = phase
                # Si no todos los criterios se cumplen, este es el límite
                unmet = [c.name for c in criteria if not c.met]
                if unmet and current_phase.value >= phase.value:
                    blocking.extend(unmet)
                break

        # Determinar si está listo para la siguiente fase
        ready = len(blocking) == 0 and phase_progress >= 1.0

        evaluation = PhaseEvaluation(
            current_phase=current_phase,
            phase_name=current_phase.name,
            phase_progress=phase_progress,
            criteria=all_criteria,
            ready_for_next=ready,
            blocking_factors=blocking,
        )

        self._last_evaluation = evaluation
        return evaluation

    def get_phase_description(self, phase: AutonomyPhase) -> str:
        """Retorna descripción humana de una fase."""
        descriptions = {
            AutonomyPhase.INIT: "Sistema recién inicializado, sin datos de operación",
            AutonomyPhase.MONITOR: "Recolectando datos básicos de capacidades",
            AutonomyPhase.SELF_AWARE: "Conoce sus capacidades y limitaciones con evidencia",
            AutonomyPhase.SELF_HEAL: "Se auto-repara ante errores sin intervención",
            AutonomyPhase.LEARN: "Aprende validadamente de forma continua",
            AutonomyPhase.EVOLVE: "Se mejora a sí mismo con tasa de éxito >70%",
            AutonomyPhase.AUTONOMY: "Opera 24h+ sin intervención humana",
        }
        return descriptions.get(phase, "Fase desconocida")

    def get_progress_report(self) -> str:
        """Genera reporte de progreso legible."""
        if not self._last_evaluation:
            self.evaluate()

        ev = self._last_evaluation
        lines = [
            f"Fase actual: {ev.phase_name} (progreso: {ev.phase_progress:.0%})",
            f"Descripción: {self.get_phase_description(ev.current_phase)}",
        ]

        if ev.blocking_factors:
            lines.append(f"Factores bloqueantes: {', '.join(ev.blocking_factors)}")

        if ev.criteria:
            lines.append("\nCriterios:")
            for c in ev.criteria:
                status = "✓" if c.met else "✗"
                lines.append(f"  {status} {c.name}: {c.current_value:.2f}/{c.target_value:.2f}")

        return "\n".join(lines)

    def _collect_metrics(self) -> Dict[str, float]:
        """Recopila métricas reales de todos los subsistemas."""
        metrics = {
            "reliable_capabilities_pct": 0.0,
            "evaluated_capabilities_pct": 0.0,
            "auto_remediation_success_rate": 0.0,
            "validated_learnings_today": float(self._validated_learnings_today),
            "self_improvement_success_rate": 0.0,
            "hours_without_human": (time.time() - self._last_human_intervention) / 3600,
            "total_errors": float(self._error_count),
        }

        # From MetaCognitionCore
        if self.meta_core:
            try:
                report = self.meta_core.get_self_awareness_report()
                caps = report.get("capabilities_summary", {})
                total = max(1, caps.get("total", 0))
                metrics["reliable_capabilities_pct"] = caps.get("reliable", 0) / total
                metrics["evaluated_capabilities_pct"] = sum(
                    1 for c in self.meta_core.self_model.capabilities.values()
                    if c.evidence_count > 0
                ) / total
            except Exception:
                pass

        # Auto-remediation rate
        if self._error_count > 0:
            metrics["auto_remediation_success_rate"] = (
                self._auto_remediated_count / self._error_count
            )

        # Self-improvement success rate
        if self._self_improvement_attempts > 0:
            metrics["self_improvement_success_rate"] = (
                self._self_improvement_successes / self._self_improvement_attempts
            )

        # From learning validator
        if self.learning_validator:
            try:
                stats = self.learning_validator.get_validation_stats()
                if stats.get("total", 0) > 0:
                    # Count today's validated learnings from stats
                    metrics["validated_learnings_today"] = max(
                        metrics["validated_learnings_today"],
                        float(stats.get("validated", 0)),
                    )
            except Exception:
                pass

        return metrics

    def _evaluate_phase(self, phase: AutonomyPhase,
                        metrics: Dict[str, float]) -> List[PhaseCriterion]:
        """Evalúa los criterios de una fase específica."""
        criteria = []

        if phase == AutonomyPhase.INIT:
            # Fase 0: siempre cumplida (sistema arrancó)
            criteria.append(PhaseCriterion(
                name="system_booted",
                description="El sistema ha arrancado",
                target_value=1.0,
                current_value=1.0,
                met=True,
            ))

        elif phase == AutonomyPhase.MONITOR:
            criteria.append(PhaseCriterion(
                name="evaluated_capabilities_pct",
                description="≥50% de capacidades tienen al menos 1 evidencia",
                target_value=0.5,
                current_value=metrics.get("evaluated_capabilities_pct", 0.0),
                met=metrics.get("evaluated_capabilities_pct", 0.0) >= 0.5,
            ))

        elif phase == AutonomyPhase.SELF_AWARE:
            criteria.append(PhaseCriterion(
                name="reliable_capabilities_pct",
                description="≥80% de capacidades con evidence_count > 10 (confiables)",
                target_value=0.8,
                current_value=metrics.get("reliable_capabilities_pct", 0.0),
                met=metrics.get("reliable_capabilities_pct", 0.0) >= 0.8,
            ))

        elif phase == AutonomyPhase.SELF_HEAL:
            criteria.append(PhaseCriterion(
                name="auto_remediation_success_rate",
                description="≥70% de errores se auto-remedian",
                target_value=0.7,
                current_value=metrics.get("auto_remediation_success_rate", 0.0),
                met=metrics.get("auto_remediation_success_rate", 0.0) >= 0.7,
            ))

        elif phase == AutonomyPhase.LEARN:
            criteria.append(PhaseCriterion(
                name="validated_learnings_today",
                description="≥5 ciclos de aprendizaje validados hoy",
                target_value=5.0,
                current_value=metrics.get("validated_learnings_today", 0.0),
                met=metrics.get("validated_learnings_today", 0.0) >= 5.0,
            ))

        elif phase == AutonomyPhase.EVOLVE:
            criteria.append(PhaseCriterion(
                name="self_improvement_success_rate",
                description="Tasa de éxito en self-improvement > 70%",
                target_value=0.7,
                current_value=metrics.get("self_improvement_success_rate", 0.0),
                met=metrics.get("self_improvement_success_rate", 0.0) >= 0.7,
            ))

        elif phase == AutonomyPhase.AUTONOMY:
            criteria.append(PhaseCriterion(
                name="hours_without_human",
                description="24+ horas sin intervención humana",
                target_value=24.0,
                current_value=metrics.get("hours_without_human", 0.0),
                met=metrics.get("hours_without_human", 0.0) >= 24.0,
            ))

        return criteria


# ─── Singleton ─────────────────────────────────────────────────────────────────

_evaluator: Optional[PhaseEvaluator] = None

def get_phase_evaluator(meta_core=None, orchestrator=None,
                         learning_validator=None) -> PhaseEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = PhaseEvaluator(meta_core, orchestrator, learning_validator)
    return _evaluator
