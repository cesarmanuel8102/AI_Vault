"""
Tests para validar que N2 (autoaprobación hardcodeada) está mitigada.

N2: evolucion_continua.py no debe permitir autoaprobación sin evidencia externa real.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestEvolucionContinuaAutoApproval:
    """Tests para validar reglas de autoaprobación segura."""
    
    def test_sin_evidence_no_autoapprove(self, tmp_path):
        """1. Sin evidence → no autoapprove"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        ec.teaching = MagicMock()
        ec.teaching.create_checkpoint.return_value = MagicMock(checkpoint_id="test_001")
        
        # Sin evidencia externa
        with patch.object(ec, '_get_validation_evidence', return_value={}):
            result = ec._can_auto_approve_from_evidence({})
            assert result is False
    
    def test_evidence_incompleta_no_autoapprove(self, tmp_path):
        """2. Evidence incompleta → no autoapprove"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        # Evidence incompleta (falta report_path)
        incomplete_evidence = {
            "all_passed": True,
            "score": 0.95,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            # Falta "report_path" y "evidence_hash"
        }
        
        result = ec._can_auto_approve_from_evidence(incomplete_evidence)
        assert result is False
    
    def test_evidence_con_failed_tests_no_autoapprove(self, tmp_path):
        """3. Evidence con failed tests → no autoapprove"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        evidence_with_failures = {
            "all_passed": True,
            "score": 0.95,
            "tests_total": 10,
            "tests_failed": 2,  # Tests fallando
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "abc123"
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_with_failures)
        assert result is False
    
    def test_evidence_score_bajo_no_autoapprove(self, tmp_path):
        """4. Evidence con score < 0.95 → no autoapprove"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        evidence_low_score = {
            "all_passed": True,
            "score": 0.94,  # Score bajo
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "abc123"
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_low_score)
        assert result is False
    
    def test_evidence_completa_valida_autoapprove_permitido(self, tmp_path):
        """5. Evidence completa y válida → autoapprove permitido"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        valid_evidence = {
            "all_passed": True,
            "score": 0.95,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "abc123"
        }
        
        result = ec._can_auto_approve_from_evidence(valid_evidence)
        assert result is True
    
    def test_no_existe_score_085_como_source_aprobacion(self, tmp_path):
        """6. No existe 'score=0.85' como source de aprobación"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        # Verificar que score=0.85 no es aceptado
        evidence_with_old_score = {
            "all_passed": True,
            "score": 0.85,  # Score antiguo hardcodeado
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "abc123"
        }
        
        result = ec._can_auto_approve_from_evidence(evidence_with_old_score)
        assert result is False  # 0.85 < 0.95
    
    def test_no_existe_auto_validado_sin_evidence(self, tmp_path):
        """7. No existe 'Auto-validado' como aprobación sin evidence"""
        import re
        
        # Verificar que no hay "Auto-validado" hardcodeado en el código
        source_file = Path("brain/evolucion_continua.py")
        content = source_file.read_text(encoding='utf-8')
        
        # Buscar patrones peligrosos de auto-validación hardcodeada
        # que NO estén dentro de bloques condicionales de evidencia
        dangerous_patterns = [
            r'# Simular validación exitosa para automatización',  # Comentario peligroso
            r'"score":\s*0\.85',  # Score hardcodeado antiguo
            r'"feedback":\s*"Auto-validado: comprensión adecuada"',  # Feedback hardcodeado
        ]
        
        for pattern in dangerous_patterns:
            matches = re.findall(pattern, content)
            assert len(matches) == 0, f"Patrón peligroso encontrado: {pattern}"
        
        # Verificar que ahora existe protección por evidencia
        assert "_can_auto_approve_from_evidence" in content
        assert "_get_validation_evidence" in content
        assert "HUMAN_REVIEW_REQUIRED" in content


class TestValidationEvidenceIntegrity:
    """Tests para integridad de evidencia de validación."""
    
    def test_get_validation_evidence_returns_required_fields(self):
        """_get_validation_evidence debe retornar campos requeridos"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        evidence = ec._get_validation_evidence()
        
        required_fields = [
            "all_passed", "score", "tests_passed", "tests_total",
            "tests_failed", "critical_failures", "report_path", 
            "evidence_hash", "timestamp", "source"
        ]
        
        for field in required_fields:
            assert field in evidence, f"Campo requerido faltante: {field}"
    
    def test_can_auto_approve_rejects_missing_fields(self):
        """Debe rechazar evidencia con campos faltantes"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        
        # Probar cada campo requerido faltante
        base_evidence = {
            "all_passed": True,
            "score": 0.95,
            "tests_total": 10,
            "tests_failed": 0,
            "critical_failures": 0,
            "report_path": "/reports/test.xml",
            "evidence_hash": "abc123"
        }
        
        required_fields = [
            "all_passed", "score", "tests_total", 
            "tests_failed", "critical_failures", "report_path", "evidence_hash"
        ]
        
        for field in required_fields:
            incomplete = {k: v for k, v in base_evidence.items() if k != field}
            result = ec._can_auto_approve_from_evidence(incomplete)
            assert result is False, f"Debe rechazar evidencia sin campo: {field}"


class TestCheckpointApprovalBehavior:
    """Tests para comportamiento de aprobación de checkpoints."""
    
    def test_complete_learning_cycle_requiere_evidence(self):
        """complete_learning_cycle debe requerir evidencia para autoaprobar"""
        from brain.evolucion_continua import EvolucionContinua
        
        ec = EvolucionContinua()
        ec.teaching = MagicMock()
        
        # Mock checkpoint
        mock_checkpoint = MagicMock(checkpoint_id="test_checkpoint_001")
        ec.teaching.create_checkpoint.return_value = mock_checkpoint
        
        # Sin evidencia - no debe aprobar
        with patch.object(ec, '_get_validation_evidence', return_value={}):
            with patch.object(ec, '_can_auto_approve_from_evidence', return_value=False):
                # Simular ciclo activo
                ec.current_cycle = MagicMock()
                ec.current_cycle.cycle_id = "cycle_001"
                ec.current_cycle.topic = "test_topic"
                ec.current_cycle.objective = "test_objective"
                ec.current_cycle.metrics = {}
                
                result = ec.complete_learning_cycle(success=True)
                
                # No debe llamar approve_checkpoint sin evidencia
                ec.teaching.approve_checkpoint.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
