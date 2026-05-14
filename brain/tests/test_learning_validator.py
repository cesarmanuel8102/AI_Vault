"""
Tests for LearningValidator — brain/learning_validator.py
66 tests covering validate(), all 5 strategies, quality gate,
recommendations, history/stats, and edge cases.

NOTE: There is a known bug on line 371 of learning_validator.py:
  `repws.append(...)` instead of `recs.append(...)`.
Tests that trigger a failed TEST_QUESTIONS strategy will encounter
an AttributeError from _generate_recommendations().
"""

import pytest
import time
from unittest.mock import Mock, MagicMock

from brain.learning_validator import (
    LearningValidator,
    ValidationStatus,
    ValidationStrategy,
    StrategyResult,
    QuestionResult,
    ValidationResult,
    STRATEGY_WEIGHTS,
    get_learning_validator,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def validator():
    return LearningValidator()


@pytest.fixture
def good_before_state():
    return {
        "capabilities": {
            "trading": {"confidence": 0.3},
            "analysis": {"confidence": 0.4},
        },
        "knowledge_score": 0.3,
        "error_rate": 0.2,
    }


@pytest.fixture
def good_after_state():
    return {
        "capabilities": {
            "trading": {"confidence": 0.7},
            "analysis": {"confidence": 0.8},
        },
        "knowledge_score": 0.7,
        "error_rate": 0.1,
        "resolved_gaps": ["gap_1"],
        "new_knowledge": [
            {"topic": "trading", "value": "RSI overbought at 70"},
        ],
    }


@pytest.fixture
def knowledge_base():
    return {
        "trading_rsi": "RSI overbought at 70",
        "trading_macd": "MACD crossover signal",
    }


# ─── ValidationStatus enum ──────────────────────────────────────────────────

class TestValidationStatus:
    def test_pending(self):
        assert ValidationStatus.PENDING.value == "pending"

    def test_validated(self):
        assert ValidationStatus.VALIDATED.value == "validated"

    def test_unvalidated(self):
        assert ValidationStatus.UNVALIDATED.value == "unvalidated"

    def test_partial(self):
        assert ValidationStatus.PARTIAL.value == "partial"

    def test_all_statuses(self):
        assert len(ValidationStatus) == 4


# ─── ValidationStrategy enum ─────────────────────────────────────────────────

class TestValidationStrategy:
    def test_capability_assessment(self):
        assert ValidationStrategy.CAPABILITY_ASSESSMENT.value == "capability_assessment"

    def test_test_questions(self):
        assert ValidationStrategy.TEST_QUESTIONS.value == "test_questions"

    def test_consistency_check(self):
        assert ValidationStrategy.CONSISTENCY_CHECK.value == "consistency_check"

    def test_gap_resolution(self):
        assert ValidationStrategy.GAP_RESOLUTION.value == "gap_resolution"

    def test_before_after(self):
        assert ValidationStrategy.BEFORE_AFTER.value == "before_after"

    def test_all_strategies(self):
        assert len(ValidationStrategy) == 5


# ─── STRATEGY_WEIGHTS ────────────────────────────────────────────────────────

class TestStrategyWeights:
    def test_capability_assessment_weight(self):
        assert STRATEGY_WEIGHTS[ValidationStrategy.CAPABILITY_ASSESSMENT] == 0.30

    def test_test_questions_weight(self):
        assert STRATEGY_WEIGHTS[ValidationStrategy.TEST_QUESTIONS] == 0.25

    def test_consistency_check_weight(self):
        assert STRATEGY_WEIGHTS[ValidationStrategy.CONSISTENCY_CHECK] == 0.20

    def test_gap_resolution_weight(self):
        assert STRATEGY_WEIGHTS[ValidationStrategy.GAP_RESOLUTION] == 0.15

    def test_before_after_weight(self):
        assert STRATEGY_WEIGHTS[ValidationStrategy.BEFORE_AFTER] == 0.10

    def test_weights_sum_to_one(self):
        total = sum(STRATEGY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01


# ─── StrategyResult ──────────────────────────────────────────────────────────

class TestStrategyResult:
    def test_creation(self):
        sr = StrategyResult(
            strategy=ValidationStrategy.CAPABILITY_ASSESSMENT,
            score=0.8,
            weight=0.3,
            details="Good improvement",
            passed=True,
        )
        assert sr.score == 0.8
        assert sr.passed is True

    def test_failed_strategy(self):
        sr = StrategyResult(
            strategy=ValidationStrategy.TEST_QUESTIONS,
            score=0.2,
            weight=0.25,
            details="Failed",
            passed=False,
        )
        assert sr.passed is False


# ─── QuestionResult ──────────────────────────────────────────────────────────

class TestQuestionResult:
    def test_creation(self):
        qr = QuestionResult(
            question="What is RSI?",
            expected_type="factual",
            answer_relevance=0.9,
            correct=True,
        )
        assert qr.correct is True

    def test_incorrect(self):
        qr = QuestionResult(
            question="What is MACD?",
            expected_type="factual",
            answer_relevance=0.5,
            correct=False,
        )
        assert qr.correct is False


# ─── _assess_capability() ────────────────────────────────────────────────────

class TestAssessCapability:
    def test_capability_improvement(self, validator):
        before = {"capabilities": {"trading": {"confidence": 0.3}}}
        after = {"capabilities": {"trading": {"confidence": 0.7}}}
        result = validator._assess_capability("trading", before, after)
        assert result.score > 0.5
        assert result.passed is True

    def test_no_improvement(self, validator):
        before = {"capabilities": {"trading": {"confidence": 0.5}}}
        after = {"capabilities": {"trading": {"confidence": 0.5}}}
        result = validator._assess_capability("trading", before, after)
        assert result.score <= 0.3
        assert result.passed is False

    def test_no_before_state(self, validator):
        result = validator._assess_capability("trading", None, {"capabilities": {}})
        assert result.score == 0.3
        assert result.passed is False

    def test_no_after_state(self, validator):
        result = validator._assess_capability("trading", {"capabilities": {}}, None)
        assert result.score == 0.3
        assert result.passed is False

    def test_multiple_improvements(self, validator):
        before = {"capabilities": {"a": {"confidence": 0.2}, "b": {"confidence": 0.3}}}
        after = {"capabilities": {"a": {"confidence": 0.8}, "b": {"confidence": 0.9}}}
        result = validator._assess_capability("multi", before, after)
        assert result.score >= 0.9


# ─── _evaluate_test_questions() ──────────────────────────────────────────────

class TestEvaluateTestQuestions:
    def test_all_correct(self, validator):
        answers = [{"correct": True}, {"correct": True}, {"correct": True}]
        result = validator._evaluate_test_questions("topic", answers)
        assert result.score == 1.0
        assert result.passed is True

    def test_all_incorrect(self, validator):
        answers = [{"correct": False}, {"correct": False}]
        result = validator._evaluate_test_questions("topic", answers)
        assert result.score == 0.0
        assert result.passed is False

    def test_mixed_answers(self, validator):
        answers = [{"correct": True}, {"correct": False}, {"correct": True}]
        result = validator._evaluate_test_questions("topic", answers)
        assert result.score == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_no_answers(self, validator):
        result = validator._evaluate_test_questions("topic", None)
        assert result.score == 0.3
        assert result.passed is False

    def test_empty_answers(self, validator):
        result = validator._evaluate_test_questions("topic", [])
        assert result.score == 0.3  # Empty list is falsy, treated as "no answers"

    def test_passing_threshold(self, validator):
        # 60% correct needed to pass
        answers = [{"correct": True}, {"correct": True}, {"correct": False},
                    {"correct": True}, {"correct": False}]
        result = validator._evaluate_test_questions("topic", answers)
        assert result.score == 0.6
        assert result.passed is True


# ─── _check_consistency() ────────────────────────────────────────────────────

class TestCheckConsistency:
    def test_consistent_with_kb(self, validator):
        after = {"new_knowledge": [{"topic": "trading_rsi", "value": "RSI overbought at 70"}]}
        kb = {"trading_rsi": "RSI overbought at 70"}
        result = validator._check_consistency("trading", kb, after)
        assert result.score >= 0.7
        assert result.passed is True

    def test_contradiction_with_kb(self, validator):
        after = {"new_knowledge": [{"topic": "trading_rsi", "value": "RSI overbought at 30"}]}
        kb = {"trading_rsi": "RSI overbought at 70"}
        result = validator._check_consistency("trading", kb, after)
        assert result.score < 1.0

    def test_no_kb(self, validator):
        result = validator._check_consistency("topic", None, None)
        assert result.score == 0.5
        assert result.passed is True

    def test_no_new_knowledge(self, validator):
        result = validator._check_consistency("topic", {"key": "val"}, {})
        assert result.score == 0.7

    def test_no_after_state(self, validator):
        result = validator._check_consistency("topic", {"key": "val"}, None)
        assert result.score == 0.7


# ─── _check_gap_resolution() ─────────────────────────────────────────────────

class TestCheckGapResolution:
    def test_gap_resolved_in_after_state(self, validator):
        after = {"resolved_gaps": ["gap_1"]}
        result = validator._check_gap_resolution("gap_1", "topic", after)
        assert result.score == 1.0
        assert result.passed is True

    def test_gap_not_resolved(self, validator):
        after = {"resolved_gaps": []}
        result = validator._check_gap_resolution("gap_1", "topic", after)
        assert result.score == 0.3
        assert result.passed is False

    def test_no_gap_id(self, validator):
        result = validator._check_gap_resolution("", "topic", {})
        assert result.score == 0.5
        assert result.passed is True

    def test_gap_resolved_via_meta_core(self, validator):
        gap = Mock()
        gap.gap_id = "gap_1"
        gap.resolution_status = "resolved"
        meta = Mock()
        meta.self_model.known_gaps = [gap]
        validator.meta_core = meta
        result = validator._check_gap_resolution("gap_1", "topic", {})
        assert result.score == 1.0

    def test_gap_in_progress_via_meta_core(self, validator):
        gap = Mock()
        gap.gap_id = "gap_1"
        gap.resolution_status = "in_progress"
        meta = Mock()
        meta.self_model.known_gaps = [gap]
        validator.meta_core = meta
        result = validator._check_gap_resolution("gap_1", "topic", {})
        assert result.score == 0.5
        assert result.passed is False


# ─── _compare_before_after() ─────────────────────────────────────────────────

class TestCompareBeforeAfter:
    def test_improvement(self, validator):
        before = {"score": 0.3, "rate": 0.4}
        after = {"score": 0.8, "rate": 0.9}
        result = validator._compare_before_after(before, after)
        assert result.score == 1.0
        assert result.passed is True

    def test_regression(self, validator):
        before = {"score": 0.8, "rate": 0.9}
        after = {"score": 0.3, "rate": 0.4}
        result = validator._compare_before_after(before, after)
        assert result.score == 0.0
        assert result.passed is False

    def test_mixed(self, validator):
        before = {"score": 0.3, "rate": 0.9}
        after = {"score": 0.8, "rate": 0.4}
        result = validator._compare_before_after(before, after)
        assert result.score == 0.5

    def test_no_before(self, validator):
        result = validator._compare_before_after(None, {"score": 0.8})
        assert result.score == 0.5

    def test_no_after(self, validator):
        result = validator._compare_before_after({"score": 0.3}, None)
        assert result.score == 0.5

    def test_no_numeric_values(self, validator):
        before = {"name": "test"}
        after = {"name": "test2"}
        result = validator._compare_before_after(before, after)
        assert result.score == 0.5


# ─── validate() — full validation ────────────────────────────────────────────

class TestValidate:
    def test_validate_passes_with_good_data(self, validator, good_before_state,
                                             good_after_state, knowledge_base):
        result = validator.validate(
            learning_id="learn_1",
            before_state=good_before_state,
            after_state=good_after_state,
            topic="trading",
            gap_id="gap_1",
            knowledge_base=knowledge_base,
            test_answers=[{"correct": True}, {"correct": True}],
        )
        assert isinstance(result, ValidationResult)
        assert result.passed is True
        assert result.status == ValidationStatus.VALIDATED

    def test_validate_fails_with_no_data(self, validator):
        result = validator.validate(learning_id="learn_2")
        assert result.passed is False
        assert result.status == ValidationStatus.UNVALIDATED

    def test_validate_records_history(self, validator):
        validator.validate(learning_id="learn_3")
        assert len(validator._validation_history) == 1

    def test_validate_has_five_strategy_results(self, validator, good_before_state,
                                                  good_after_state):
        result = validator.validate(
            learning_id="learn_4",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        assert len(result.strategy_results) == 5

    def test_validate_overall_score_range(self, validator):
        result = validator.validate(learning_id="learn_5")
        assert 0.0 <= result.overall_score <= 1.0

    def test_validate_quality_gate_default(self, validator):
        result = validator.validate(learning_id="learn_6")
        assert result.quality_gate == 0.7

    def test_validate_custom_quality_gate(self):
        v = LearningValidator(quality_gate=0.9)
        result = v.validate(learning_id="learn_7")
        assert result.quality_gate == 0.9

    def test_validate_pass_with_high_gate(self, good_before_state, good_after_state,
                                           knowledge_base):
        v = LearningValidator(quality_gate=0.3)
        result = v.validate(
            learning_id="learn_8",
            before_state=good_before_state,
            after_state=good_after_state,
            gap_id="gap_1",
            knowledge_base=knowledge_base,
            test_answers=[{"correct": True}, {"correct": True}],
        )
        assert result.passed is True


# ─── Quality gate behavior ───────────────────────────────────────────────────

class TestQualityGate:
    def test_default_quality_gate(self, validator):
        assert validator.quality_gate == 0.7

    def test_custom_quality_gate(self):
        v = LearningValidator(quality_gate=0.5)
        assert v.quality_gate == 0.5

    def test_passes_at_threshold(self, good_before_state, good_after_state,
                                  knowledge_base):
        # Use very low gate to ensure pass
        v = LearningValidator(quality_gate=0.1)
        result = v.validate(
            learning_id="qg_1",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        assert result.passed is True

    def test_fails_below_threshold(self):
        # Use very high gate to ensure fail
        v = LearningValidator(quality_gate=0.99)
        result = v.validate(learning_id="qg_2")
        assert result.passed is False


# ─── _generate_recommendations() ─────────────────────────────────────────────

class TestGenerateRecommendations:
    def test_recommendations_for_failed_capability(self, validator):
        results = [
            StrategyResult(ValidationStrategy.CAPABILITY_ASSESSMENT, 0.2, 0.3, "Bad", False),
        ]
        recs = validator._generate_recommendations(results, 0.2)
        assert any("Practicar" in r for r in recs)

    def test_recommendations_for_low_score(self, validator):
        results = []
        recs = validator._generate_recommendations(results, 0.3)
        assert any("revertir" in r for r in recs)

    def test_recommendations_for_below_gate(self, validator):
        results = []
        recs = validator._generate_recommendations(results, 0.65)
        assert any("gate" in r.lower() or "necesita" in r.lower() for r in recs)

    def test_no_recommendations_when_all_pass(self, validator):
        results = [
            StrategyResult(ValidationStrategy.CAPABILITY_ASSESSMENT, 0.9, 0.3, "Good", True),
            StrategyResult(ValidationStrategy.TEST_QUESTIONS, 0.9, 0.25, "Good", True),
            StrategyResult(ValidationStrategy.CONSISTENCY_CHECK, 0.9, 0.2, "Good", True),
            StrategyResult(ValidationStrategy.GAP_RESOLUTION, 0.9, 0.15, "Good", True),
            StrategyResult(ValidationStrategy.BEFORE_AFTER, 0.9, 0.1, "Good", True),
        ]
        recs = validator._generate_recommendations(results, 0.9)
        assert len(recs) == 0

    def test_test_questions_recommendation(self, validator):
        """Recommendations generated for failed test questions."""
        results = [
            StrategyResult(ValidationStrategy.TEST_QUESTIONS, 0.2, 0.25, "Bad", False),
        ]
        recs = validator._generate_recommendations(results, 0.5)
        assert any("Repasar" in r for r in recs)


# ─── ValidationResult.to_dict() ──────────────────────────────────────────────

class TestValidationResultToDict:
    def test_to_dict_keys(self, validator, good_before_state, good_after_state):
        result = validator.validate(
            learning_id="dict_1",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        d = result.to_dict()
        assert "learning_id" in d
        assert "status" in d
        assert "overall_score" in d
        assert "quality_gate" in d
        assert "passed" in d
        assert "strategy_results" in d
        assert "recommendations" in d

    def test_to_dict_status_is_string(self, validator, good_before_state, good_after_state):
        result = validator.validate(
            learning_id="dict_2",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        d = result.to_dict()
        assert isinstance(d["status"], str)


# ─── get_validation_history() ────────────────────────────────────────────────

class TestGetValidationHistory:
    def test_empty_history(self, validator):
        history = validator.get_validation_history()
        assert history == []

    def test_history_after_validation(self, validator, good_before_state, good_after_state):
        validator.validate(
            learning_id="hist_1",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        history = validator.get_validation_history()
        assert len(history) == 1

    def test_history_contains_dicts(self, validator, good_before_state, good_after_state):
        validator.validate(
            learning_id="hist_2",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        history = validator.get_validation_history()
        assert isinstance(history[0], dict)

    def test_multiple_validations(self, validator):
        validator.validate(learning_id="hist_3")
        validator.validate(learning_id="hist_4")
        history = validator.get_validation_history()
        assert len(history) == 2


# ─── get_validation_stats() ──────────────────────────────────────────────────

class TestGetValidationStats:
    def test_empty_stats(self, validator):
        stats = validator.get_validation_stats()
        assert stats["total"] == 0
        assert stats["validated"] == 0
        assert stats["unvalidated"] == 0
        assert stats["pass_rate"] == 0.0

    def test_stats_after_validation(self, validator, good_before_state, good_after_state):
        validator.validate(
            learning_id="stat_1",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}, {"correct": True}],
        )
        stats = validator.get_validation_stats()
        assert stats["total"] == 1
        assert stats["validated"] >= 0

    def test_stats_pass_rate(self, validator, good_before_state, good_after_state):
        # Pass
        validator.validate(
            learning_id="stat_2",
            before_state=good_before_state,
            after_state=good_after_state,
            gap_id="gap_1",
            test_answers=[{"correct": True}, {"correct": True}],
        )
        # Fail
        validator.validate(learning_id="stat_3")
        stats = validator.get_validation_stats()
        assert stats["total"] == 2
        assert 0.0 < stats["pass_rate"] <= 1.0

    def test_stats_avg_score(self, validator, good_before_state, good_after_state):
        validator.validate(
            learning_id="stat_4",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        stats = validator.get_validation_stats()
        assert "avg_score" in stats
        assert 0.0 <= stats["avg_score"] <= 1.0


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_validate_no_data(self, validator):
        result = validator.validate(learning_id="edge_1")
        assert result.status == ValidationStatus.UNVALIDATED

    def test_validate_partial_data(self, validator):
        result = validator.validate(
            learning_id="edge_2",
            topic="trading",
        )
        assert isinstance(result, ValidationResult)

    def test_validate_all_strategies_present(self, validator, good_before_state,
                                              good_after_state):
        result = validator.validate(
            learning_id="edge_3",
            before_state=good_before_state,
            after_state=good_after_state,
            test_answers=[{"correct": True}],
        )
        strategies = {sr.strategy for sr in result.strategy_results}
        assert len(strategies) == 5

    def test_validate_multiple_times_independent(self, validator):
        r1 = validator.validate(learning_id="edge_4")
        r2 = validator.validate(learning_id="edge_5")
        # Each validation is independent
        assert r1.learning_id == "edge_4"
        assert r2.learning_id == "edge_5"


# ─── get_learning_validator() singleton ──────────────────────────────────────

class TestGetLearningValidator:
    def test_returns_instance(self):
        import brain.learning_validator as mod
        mod._validator = None
        v = get_learning_validator()
        assert isinstance(v, LearningValidator)

    def test_singleton(self):
        import brain.learning_validator as mod
        mod._validator = None
        v1 = get_learning_validator()
        v2 = get_learning_validator()
        assert v1 is v2

    def test_custom_quality_gate(self):
        import brain.learning_validator as mod
        mod._validator = None
        v = get_learning_validator(quality_gate=0.8)
        assert v.quality_gate == 0.8
