"""
Tests for PhaseEvaluator — brain/phase_evaluator.py
23 tests covering evaluate(), _evaluate_phase() for each phase,
recording methods, get_phase_description(), get_progress_report(),
dataclasses, phase progression, and edge cases.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch

from brain.phase_evaluator import (
    PhaseEvaluator,
    AutonomyPhase,
    PhaseCriterion,
    PhaseEvaluation,
    get_phase_evaluator,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def evaluator():
    return PhaseEvaluator()


def _make_meta_core(reliable=3, total=4, with_evidence=2):
    """Create a mock MetaCognitionCore."""
    meta = Mock()
    capabilities = {}
    for i in range(with_evidence):
        cap = Mock()
        cap.evidence_count = 15
        capabilities[f"cap_{i}"] = cap
    for i in range(total - with_evidence):
        cap = Mock()
        cap.evidence_count = 0
        capabilities[f"cap_no_ev_{i}"] = cap
    meta.self_model = Mock()
    meta.self_model.capabilities = capabilities
    meta.get_self_awareness_report.return_value = {
        "capabilities_summary": {
            "reliable": reliable,
            "unreliable": total - reliable,
            "total": total,
        }
    }
    return meta


# ─── AutonomyPhase enum ──────────────────────────────────────────────────────

class TestAutonomyPhase:
    def test_init(self):
        assert AutonomyPhase.INIT.value == "0_init"

    def test_monitor(self):
        assert AutonomyPhase.MONITOR.value == "1_monitor"

    def test_self_aware(self):
        assert AutonomyPhase.SELF_AWARE.value == "2_self_aware"

    def test_self_heal(self):
        assert AutonomyPhase.SELF_HEAL.value == "3_self_heal"

    def test_learn(self):
        assert AutonomyPhase.LEARN.value == "4_learn"

    def test_evolve(self):
        assert AutonomyPhase.EVOLVE.value == "5_evolve"

    def test_autonomy(self):
        assert AutonomyPhase.AUTONOMY.value == "6_autonomy"

    def test_all_phases_count(self):
        assert len(AutonomyPhase) == 7


# ─── PhaseCriterion ──────────────────────────────────────────────────────────

class TestPhaseCriterion:
    def test_creation(self):
        pc = PhaseCriterion(
            name="test_criterion",
            description="A test criterion",
            target_value=1.0,
            current_value=0.5,
            met=False,
        )
        assert pc.name == "test_criterion"
        assert pc.met is False

    def test_met_criterion(self):
        pc = PhaseCriterion(
            name="test",
            description="desc",
            target_value=0.5,
            current_value=0.8,
            met=True,
        )
        assert pc.met is True


# ─── PhaseEvaluation ─────────────────────────────────────────────────────────

class TestPhaseEvaluation:
    def test_creation(self):
        pe = PhaseEvaluation(
            current_phase=AutonomyPhase.INIT,
            phase_name="INIT",
            phase_progress=1.0,
            ready_for_next=True,
        )
        assert pe.current_phase == AutonomyPhase.INIT
        assert pe.ready_for_next is True

    def test_default_values(self):
        pe = PhaseEvaluation(
            current_phase=AutonomyPhase.INIT,
            phase_name="INIT",
            phase_progress=0.0,
            ready_for_next=False,
        )
        assert pe.criteria == []
        assert pe.blocking_factors == []


# ─── record methods ──────────────────────────────────────────────────────────

class TestRecordMethods:
    def test_record_error(self, evaluator):
        evaluator.record_error()
        assert evaluator._error_count == 1

    def test_record_error_auto_remediated(self, evaluator):
        evaluator.record_error(auto_remediated=True)
        assert evaluator._error_count == 1
        assert evaluator._auto_remediated_count == 1

    def test_record_validated_learning(self, evaluator):
        evaluator.record_validated_learning()
        assert evaluator._validated_learnings_today == 1

    def test_record_self_improvement_success(self, evaluator):
        evaluator.record_self_improvement(success=True)
        assert evaluator._self_improvement_attempts == 1
        assert evaluator._self_improvement_successes == 1

    def test_record_self_improvement_failure(self, evaluator):
        evaluator.record_self_improvement(success=False)
        assert evaluator._self_improvement_attempts == 1
        assert evaluator._self_improvement_successes == 0

    def test_record_human_intervention(self, evaluator):
        before = evaluator._last_human_intervention
        time.sleep(0.01)
        evaluator.record_human_intervention()
        assert evaluator._last_human_intervention > before


# ─── evaluate() for each phase ───────────────────────────────────────────────

class TestEvaluate:
    def test_evaluate_init_phase(self, evaluator):
        """INIT phase should always pass — system booted."""
        result = evaluator.evaluate()
        assert result.current_phase == AutonomyPhase.INIT

    def test_evaluate_monitor_phase(self, evaluator):
        """MONITOR phase needs ≥50% capabilities with evidence."""
        meta = _make_meta_core(total=4, with_evidence=3)
        ev = PhaseEvaluator(meta_core=meta)
        result = ev.evaluate()
        # With 3/4 = 75% evidence, should at least reach MONITOR
        assert result.current_phase.value >= AutonomyPhase.MONITOR.value

    def test_evaluate_self_aware_phase(self, evaluator):
        """SELF_AWARE phase needs ≥80% reliable capabilities."""
        meta = _make_meta_core(reliable=4, total=4, with_evidence=4)
        ev = PhaseEvaluator(meta_core=meta)
        result = ev.evaluate()
        # With 4/4 = 100% reliable, should reach SELF_AWARE
        assert result.current_phase.value >= AutonomyPhase.SELF_AWARE.value

    def test_evaluate_self_heal_phase(self, evaluator):
        """SELF_HEAL phase needs ≥70% auto-remediation rate."""
        ev = PhaseEvaluator()
        # Record enough errors with auto-remediation
        for _ in range(7):
            ev.record_error(auto_remediated=True)
        for _ in range(3):
            ev.record_error(auto_remediated=False)
        result = ev.evaluate()
        # 70% auto-remediation, but still needs other phases
        assert isinstance(result, PhaseEvaluation)

    def test_evaluate_returns_phase_evaluation(self, evaluator):
        result = evaluator.evaluate()
        assert isinstance(result, PhaseEvaluation)

    def test_evaluate_has_criteria(self, evaluator):
        result = evaluator.evaluate()
        assert len(result.criteria) > 0


# ─── _evaluate_phase() criteria ──────────────────────────────────────────────

class TestEvaluatePhaseCriteria:
    def test_init_criteria_always_met(self, evaluator):
        metrics = {}
        criteria = evaluator._evaluate_phase(AutonomyPhase.INIT, metrics)
        assert len(criteria) == 1
        assert criteria[0].met is True

    def test_monitor_criteria_unmet(self, evaluator):
        metrics = {"evaluated_capabilities_pct": 0.1}
        criteria = evaluator._evaluate_phase(AutonomyPhase.MONITOR, metrics)
        assert len(criteria) == 1
        assert criteria[0].met is False

    def test_monitor_criteria_met(self, evaluator):
        metrics = {"evaluated_capabilities_pct": 0.6}
        criteria = evaluator._evaluate_phase(AutonomyPhase.MONITOR, metrics)
        assert criteria[0].met is True

    def test_self_aware_criteria(self, evaluator):
        metrics = {"reliable_capabilities_pct": 0.9}
        criteria = evaluator._evaluate_phase(AutonomyPhase.SELF_AWARE, metrics)
        assert criteria[0].met is True

    def test_self_heal_criteria(self, evaluator):
        metrics = {"auto_remediation_success_rate": 0.8}
        criteria = evaluator._evaluate_phase(AutonomyPhase.SELF_HEAL, metrics)
        assert criteria[0].met is True

    def test_learn_criteria(self, evaluator):
        metrics = {"validated_learnings_today": 6.0}
        criteria = evaluator._evaluate_phase(AutonomyPhase.LEARN, metrics)
        assert criteria[0].met is True

    def test_evolve_criteria(self, evaluator):
        metrics = {"self_improvement_success_rate": 0.8}
        criteria = evaluator._evaluate_phase(AutonomyPhase.EVOLVE, metrics)
        assert criteria[0].met is True

    def test_autonomy_criteria(self, evaluator):
        metrics = {"hours_without_human": 30.0}
        criteria = evaluator._evaluate_phase(AutonomyPhase.AUTONOMY, metrics)
        assert criteria[0].met is True


# ─── get_phase_description() ─────────────────────────────────────────────────

class TestGetPhaseDescription:
    def test_init_description(self, evaluator):
        desc = evaluator.get_phase_description(AutonomyPhase.INIT)
        assert "inicializado" in desc.lower()

    def test_monitor_description(self, evaluator):
        desc = evaluator.get_phase_description(AutonomyPhase.MONITOR)
        assert "datos" in desc.lower() or "recolectando" in desc.lower()

    def test_self_aware_description(self, evaluator):
        desc = evaluator.get_phase_description(AutonomyPhase.SELF_AWARE)
        assert "capacidades" in desc.lower() or "limitaciones" in desc.lower()

    def test_autonomy_description(self, evaluator):
        desc = evaluator.get_phase_description(AutonomyPhase.AUTONOMY)
        assert "24h" in desc or "intervención" in desc.lower()

    def test_unknown_phase_description(self, evaluator):
        desc = evaluator.get_phase_description("not_a_phase")
        assert "desconocida" in desc.lower()


# ─── get_progress_report() ───────────────────────────────────────────────────

class TestGetProgressReport:
    def test_progress_report_returns_string(self, evaluator):
        report = evaluator.get_progress_report()
        assert isinstance(report, str)

    def test_progress_report_contains_phase(self, evaluator):
        report = evaluator.get_progress_report()
        assert "Fase" in report or "fase" in report.lower()

    def test_progress_report_contains_criteria(self, evaluator):
        report = evaluator.get_progress_report()
        assert "✓" in report or "✗" in report


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_no_meta_core(self, evaluator):
        result = evaluator.evaluate()
        assert isinstance(result, PhaseEvaluation)

    def test_no_data(self, evaluator):
        result = evaluator.evaluate()
        # Should default to INIT
        assert result.current_phase == AutonomyPhase.INIT

    def test_meta_core_error(self):
        meta = Mock()
        meta.get_self_awareness_report.side_effect = Exception("fail")
        meta.self_model = Mock()
        meta.self_model.capabilities = {}
        ev = PhaseEvaluator(meta_core=meta)
        result = ev.evaluate()
        assert isinstance(result, PhaseEvaluation)


# ─── get_phase_evaluator() singleton ─────────────────────────────────────────

class TestGetPhaseEvaluator:
    def test_returns_instance(self):
        import brain.phase_evaluator as mod
        mod._evaluator = None
        ev = get_phase_evaluator()
        assert isinstance(ev, PhaseEvaluator)
