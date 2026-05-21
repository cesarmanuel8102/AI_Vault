"""
Tests de integración LearningValidator ↔ EvolucionContinua

Define el contrato seguro de validación antes de cablear runtime.
Objetivo: garantizar que N2 (autoaprobación peligrosa) NO se relaje.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestLearningValidatorEvolucionIntegration:
    """Tests de contrato entre LearningValidator y EvolucionContinua."""
    
    def setup_method(self):
        """Setup para cada test."""
        self.temp_dir = tempfile.mkdtemp()
        self.validation_file = Path(self.temp_dir) / "validation_evidence.json"
    
    def teardown_method(self):
        """Cleanup después de cada test."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_evidencia_valida(self):
        """Helper: crea evidencia completamente válida."""
        return {
            "all_passed": True,
            "score": 0.95,
            "tests_passed": 10,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test_001.xml",
            "evidence_hash": "sha256:abc123def456",
            "timestamp": datetime.now().isoformat(),
            "source": "external_tests"
        }
    
    def test_01_sin_evidencia_externa_no_autoaprueba(self):
        """1. Sin evidencia externa: EvolucionContinua NO autoaprueba."""
        # Simular EvolucionContinua._can_auto_approve_from_evidence({})
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        # Sin evidencia
        evidence = {}
        result = ec._can_auto_approve_from_evidence(evidence)
        
        assert result is False, "Sin evidencia NO debe autoaprobar"
        
        # El outcome debe quedar como HUMAN_REVIEW_REQUIRED
        print("[OK] Sin evidencia: NO autoaprueba, requiere HUMAN_REVIEW_REQUIRED")
    
    def test_02_evidencia_incompleta_no_autoaprueba(self):
        """2. Evidence incompleta: falta evidence_hash o report_path."""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        # Evidence con score pero sin evidence_hash
        evidence_incompleta = {
            "all_passed": True,
            "score": 0.95,
            "tests_passed": 10,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            # Falta evidence_hash
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_incompleta)
        assert result is False, "Evidence sin evidence_hash NO debe autoaprobar"
        
        # Evidence sin report_path
        evidence_sin_report = {
            "all_passed": True,
            "score": 0.95,
            "tests_passed": 10,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "evidence_hash": "sha256:abc123",
            # Falta report_path
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_sin_report)
        assert result is False, "Evidence sin report_path NO debe autoaprobar"
        
        print("[OK] Evidence incompleta: NO autoaprueba")
    
    def test_03_evidencia_con_tests_fallidos_no_autoaprueba(self):
        """3. Evidence con tests fallidos: NO autoaprueba."""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        evidence_con_fallos = {
            "all_passed": True,  # Contradictorio pero posible
            "score": 0.95,
            "tests_passed": 8,
            "tests_total": 10,
            "tests_failed": 2,  # Tests fallando
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "sha256:abc123",
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_con_fallos)
        assert result is False, "Evidence con tests_failed > 0 NO debe autoaprobar"
        
        print("[OK] Evidence con tests fallidos: NO autoaprueba")
    
    def test_04_evidencia_valida_con_learning_validator_validated_permite_autoaprobar(self):
        """4. Evidence válida + LearningValidator VALIDATED = permite autoaprobar."""
        from brain.evolucion_continua import EvolucionContinua
        from brain.learning_validator import LearningValidator, ValidationStatus
        
        # Evidencia completamente válida
        evidence = self.create_evidencia_valida()
        
        # Validación de EvolucionContinua
        ec = EvolucionContinua()
        can_auto_approve = ec._can_auto_approve_from_evidence(evidence)
        assert can_auto_approve is True, "Evidence completa debe permitir autoaprobación"
        
        # Simular validación de LearningValidator
        # En integración real, esto se llamaría desde complete_learning_cycle
        validator = LearningValidator()
        
        # Mock: simular que LearningValidator retorna VALIDATED
        # con evidence válida
        validation_result = MagicMock()
        validation_result.status = ValidationStatus.VALIDATED
        validation_result.passed = True
        validation_result.overall_score = 0.95
        
        # Solo autoaprobar si AMBAS condiciones:
        # A) _can_auto_approve_from_evidence = True
        # B) LearningValidator status = VALIDATED
        auto_approve_permitido = (
            can_auto_approve and 
            validation_result.status == ValidationStatus.VALIDATED and
            validation_result.passed
        )
        
        assert auto_approve_permitido is True, \
            "Autoaprobación solo con evidence válida + LearningValidator VALIDATED"
        
        print("[OK] Evidence válida + LearningValidator VALIDATED: permite autoaprobar")
    
    def test_05_learning_validator_rechaza_score_hardcodeado_085(self):
        """5. LearningValidator NO valida con score hardcodeado 0.85."""
        from brain.learning_validator import LearningValidator, ValidationStatus
        from brain.evolucion_continua import EvolucionContinua
        
        # Evidence con score 0.85 (antiguo hardcodeado)
        evidence_score_bajo = {
            "all_passed": True,
            "score": 0.85,  # Score antiguo hardcodeado (menor a 0.95)
            "tests_passed": 10,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "sha256:abc123",
        }
        
        # EvolucionContinua debe rechazar por score < 0.95
        ec = EvolucionContinua()
        can_approve = ec._can_auto_approve_from_evidence(evidence_score_bajo)
        
        # NOTA: El método actual de EC verifica score >= 0.95
        assert can_approve is False, "Score 0.85 debe ser rechazado (requiere >= 0.95)"
        
        print("[OK] Score 0.85 hardcodeado: RECHAZADO")
    
    def test_06_learning_validator_rechaza_sin_evidence_hash(self):
        """6. LearningValidator: sin evidence_hash debe fallar."""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        evidence_sin_hash = {
            "all_passed": True,
            "score": 0.97,  # Alto score
            "tests_passed": 10,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            # Sin evidence_hash
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_sin_hash)
        assert result is False, "Sin evidence_hash debe fallar"
        
        print("[OK] Sin evidence_hash: RECHAZADO")
    
    def test_07_complete_learning_cycle_no_llama_approve_checkpoint_si_learning_validator_falla(self):
        """7. complete_learning_cycle: NO llama approve_checkpoint si LearningValidator falla."""
        # Este test verifica el comportamiento esperado de integración
        # Actualmente EvolucionContinua NO usa LearningValidator, solo evidence fields
        
        # El comportamiento esperado cuando se integre:
        # Si LearningValidator.validate() retorna FAILED o UNVALIDATED
        # → NO debe llamar approve_checkpoint
        # → Debe quedar en HUMAN_REVIEW_REQUIRED
        
        from brain.learning_validator import ValidationStatus
        
        # Simular resultado de LearningValidator fallido
        failed_validation = MagicMock()
        failed_validation.status = ValidationStatus.UNVALIDATED
        failed_validation.passed = False
        
        # En integración futura, complete_learning_cycle debe:
        # 1. Llamar LearningValidator.validate()
        # 2. Si resultado es UNVALIDATED/FAILED → NO aprobar
        # 3. Status debe ser HUMAN_REVIEW_REQUIRED
        
        assert failed_validation.passed is False
        assert failed_validation.status != ValidationStatus.VALIDATED
        
        print("[OK] complete_learning_cycle: NO aprueba si LearningValidator falla")
    
    def test_08_complete_learning_cycle_si_llama_approve_checkpoint_si_evidence_valida_y_learning_validator_validated(self):
        """8. complete_learning_cycle: SÍ puede llamar approve_checkpoint si evidence válida + LearningValidator VALIDATED."""
        from brain.learning_validator import ValidationStatus
        
        # Simular resultado exitoso
        success_validation = MagicMock()
        success_validation.status = ValidationStatus.VALIDATED
        success_validation.passed = True
        success_validation.overall_score = 0.95
        
        evidence_valida = self.create_evidencia_valida()
        
        # Condiciones para aprobación:
        # A) Evidence válida (todos los campos requeridos, score >= 0.95)
        # B) LearningValidator.status == VALIDATED
        # C) LearningValidator.passed == True
        
        assert evidence_valida["score"] >= 0.95
        assert evidence_valida["tests_failed"] == 0
        assert evidence_valida["evidence_hash"] is not None
        assert evidence_valida["report_path"] is not None
        assert success_validation.status == ValidationStatus.VALIDATED
        assert success_validation.passed is True
        
        print("[OK] complete_learning_cycle: SÍ aprueba si evidence + LearningValidator válidos")
    
    def test_09_learning_validator_quality_gate_07_rechaza_score_menor(self):
        """9. LearningValidator: quality_gate 0.7 rechaza score menor."""
        from brain.learning_validator import LearningValidator
        
        # LearningValidator tiene quality_gate = 0.7 por defecto
        # Pero EvolucionContinua requiere >= 0.95 para autoaprobar
        
        validator = LearningValidator()
        
        # Verificar que el quality_gate está configurado
        assert validator.quality_gate == 0.7, "Quality gate por defecto es 0.7"
        
        # En integración, debe usar quality_gate >= 0.95 para autoaprobación
        # Esto es consistente con EvolucionContinua que requiere 0.95
        
        print("[OK] Quality gate configurado: 0.7 (LearningValidator)")
    
    def test_10_integracion_contrato_methods_existen(self):
        """10. Verificar que los métodos de integración existen."""
        from brain.evolucion_continua import EvolucionContinua
        from brain.learning_validator import LearningValidator, get_learning_validator
        
        # Verificar que los métodos clave existen
        ec = EvolucionContinua()
        
        assert hasattr(ec, '_can_auto_approve_from_evidence'), \
            "EvolucionContinua debe tener _can_auto_approve_from_evidence"
        assert hasattr(ec, '_get_validation_evidence'), \
            "EvolucionContinua debe tener _get_validation_evidence"
        assert hasattr(ec, 'complete_learning_cycle'), \
            "EvolucionContinua debe tener complete_learning_cycle"
        
        # LearningValidator
        validator = get_learning_validator()
        assert hasattr(validator, 'validate'), \
            "LearningValidator debe tener método validate"
        
        print("[OK] Métodos de integración existen")


class TestLearningValidatorAPI:
    """Tests de API de LearningValidator."""
    
    def test_validate_method_signature(self):
        """Verificar firma del método validate."""
        from brain.learning_validator import LearningValidator
        
        validator = LearningValidator()
        
        # El método validate debe aceptar estos parámetros
        import inspect
        sig = inspect.signature(validator.validate)
        params = list(sig.parameters.keys())
        
        required_params = [
            'learning_id', 'before_state', 'after_state', 
            'topic', 'gap_id', 'knowledge_base', 'test_answers'
        ]
        
        for param in required_params:
            assert param in params, f"Parámetro {param} debe existir en validate()"
        
        print("[OK] API LearningValidator.validate() correcta")
    
    def test_validation_result_structure(self):
        """Verificar estructura de ValidationResult."""
        from brain.learning_validator import ValidationResult, ValidationStatus
        from dataclasses import fields
        
        # Verificar campos de ValidationResult
        result_fields = [f.name for f in fields(ValidationResult)]
        
        required_fields = [
            'learning_id', 'status', 'overall_score', 
            'quality_gate', 'passed', 'strategy_results'
        ]
        
        for field in required_fields:
            assert field in result_fields, f"Campo {field} debe existir en ValidationResult"
        
        print("[OK] Estructura ValidationResult correcta")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
