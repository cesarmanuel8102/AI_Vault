"""
Tests unitarios para CurationValidationAdapter (P2-C).
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curation_validation_adapter import (
    CurationValidationAdapter,
    CurationValidationResult,
    CurationValidationStatus,
    create_curation_validation_adapter,
)
from brain.information_curator import CuratedRecord, QualityLevel
from brain.learning_validator import LearningValidator, ValidationResult, ValidationStatus


class TestCurationValidationAdapter:
    """Test suite."""
    
    @pytest.fixture
    def mock_validator(self):
        return Mock(spec=LearningValidator)
    
    @pytest.fixture
    def adapter(self, mock_validator):
        return CurationValidationAdapter(validator=mock_validator)
    
    @pytest.fixture
    def sample_record(self):
        return CuratedRecord(
            record_id="test_record_001",
            content="Contenido de prueba",
            topic="TEST_TOPIC",
            quality=QualityLevel.HIGH,
            quality_score=0.85,
            source="test_source",
            content_hash="hash123",
            ingested_at=1234567890.0,
            validated_at=None,
        )
    
    def test_null_record_returns_error(self, adapter, mock_validator):
        result = adapter.validate_record(None)
        assert result.status == CurationValidationStatus.ERROR
        assert result.passed is False
        mock_validator.validate.assert_not_called()
    
    def test_empty_content_rejected(self, adapter, mock_validator, sample_record):
        sample_record.content = ""
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.REJECTED
        mock_validator.validate.assert_not_called()
    
    def test_missing_source_rejected(self, adapter, mock_validator, sample_record):
        sample_record.source = ""
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.REJECTED
        mock_validator.validate.assert_not_called()
    
    def test_low_quality_not_validated(self, adapter, mock_validator, sample_record):
        sample_record.quality_score = 0.15
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.UNVALIDATED
        mock_validator.validate.assert_not_called()
    
    def test_contradictions_not_auto_validated(self, adapter, mock_validator, sample_record):
        contradictions = [(Mock(record_id="rec1"), Mock(record_id="rec2"), "contradiction")]
        result = adapter.validate_record(sample_record, contradictions=contradictions)
        assert result.status == CurationValidationStatus.UNVALIDATED
        mock_validator.validate.assert_not_called()
    
    def test_validator_validated_maps_to_validated(self, adapter, mock_validator, sample_record):
        mock_result = ValidationResult(
            learning_id="test",
            status=ValidationStatus.VALIDATED,
            overall_score=0.85,
            quality_gate="PASS",
            passed=True,
            strategy_results={},
            recommendations=["passed"],
        )
        mock_validator.validate.return_value = mock_result
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.VALIDATED
        assert result.passed is True
    
    def test_validator_unvalidated_maps_to_unvalidated(self, adapter, mock_validator, sample_record):
        mock_result = ValidationResult(
            learning_id="test",
            status=ValidationStatus.UNVALIDATED,
            overall_score=0.45,
            quality_gate="FAIL",
            passed=False,
            strategy_results={},
            recommendations=["failed"],
        )
        mock_validator.validate.return_value = mock_result
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.UNVALIDATED
        assert result.passed is False
    
    def test_validator_exception_maps_to_error(self, adapter, mock_validator, sample_record):
        mock_validator.validate.side_effect = Exception("crash")
        result = adapter.validate_record(sample_record)
        assert result.status == CurationValidationStatus.ERROR
    
    def test_does_not_mutate_record_validated_at(self, adapter, mock_validator, sample_record):
        original = sample_record.validated_at
        mock_result = ValidationResult(
            learning_id="test",
            status=ValidationStatus.VALIDATED,
            overall_score=0.85,
            quality_gate="PASS",
            passed=True,
            strategy_results={},
            recommendations=["passed"],
        )
        mock_validator.validate.return_value = mock_result
        adapter.validate_record(sample_record)
        assert sample_record.validated_at == original
    
    def test_no_runtime_imports(self):
        import brain.curation_validation_adapter as mod
        src = Path(mod.__file__).read_text()
        assert "brain_v9.core.session" not in src
        assert "main" not in src
    
    def test_factory_creates_adapter(self):
        adapter = create_curation_validation_adapter()
        assert isinstance(adapter, CurationValidationAdapter)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
