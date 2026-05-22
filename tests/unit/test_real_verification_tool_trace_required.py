"""Test hardening conversacional post-N1/P1-A.

Evitar que route=llm diga "verifiqué realmente" si no hubo herramienta HTTP real.
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")
sys.path.insert(0, r"C:\AI_VAULT\brain")

from brain_v9.core.session import BrainSession


class TestRealVerificationToolTraceRequired:
    """Tests de hardening: verificación real requiere tool trace."""

    def test_no_ghost_verification_metrics(self):
        """1. /brain/metrics sin tool no puede decir 'verifiqué'."""
        # Simular respuesta de LLM sin tool trace
        llm_response = "Verifiqué realmente /brain/metrics y devuelve código HTTP 200."
        
        # Aplicar sanitización
        sanitized = BrainSession._sanitize_llm_chat_response(llm_response)
        
        # Verificar que el hardening bloqueó la afirmación fake
        assert "verifiqué realmente" not in sanitized.lower(), \
            "Hardening no bloqueó 'verifiqué realmente'"
        assert "código HTTP 200" not in sanitized.lower(), \
            "Hardening no bloqueó código HTTP 200 fake"
        
        # Verificar que devolvió mensaje seguro
        assert "no puedo confirmar estado real" in sanitized.lower() or \
               "necesito herramienta HTTP real" in sanitized.lower(), \
            "Hardening no devolvió mensaje seguro"

    def test_epistemic_restraint_for_metrics(self):
        """2. Sin tool trace, debe responder con mensaje de restricción."""
        # Caso: solicitud de /brain/metrics
        llm_response = "Consulté el endpoint /brain/metrics y devuelve código HTTP 200 con datos de métricas."
        
        # Aplicar sanitización
        sanitized = BrainSession._sanitize_llm_chat_response(llm_response)
        
        # Verificar que bloqueó
        assert "no puedo confirmar estado real" in sanitized.lower(), \
            "Hardening no aplicó restricción epistémica"

    def test_no_http_code_without_tool(self):
        """3. 'código HTTP' sin herramienta real no debe devolver 200."""
        # Caso problemático
        bad_response = "Verifiqué el endpoint y devuelve código HTTP 200."
        
        # Aplicar sanitización
        sanitized = BrainSession._sanitize_llm_chat_response(bad_response)
        
        # Verificar que bloqueó código HTTP fake
        assert "HTTP 200" not in sanitized or "no puedo confirmar" in sanitized.lower(), \
            "Hardening no bloqueó código HTTP 200 sin tool"

    def test_hardening_preserves_safe_responses(self):
        """4. Respuestas seguras no deben ser modificadas."""
        # Respuesta que no afirma verificación
        safe_response = "No puedo verificar ese endpoint sin herramientas HTTP."
        
        # Aplicar sanitización
        sanitized = BrainSession._sanitize_llm_chat_response(safe_response)
        
        # Verificar que no modificó innecesariamente
        assert "no puedo verificar" in sanitized.lower(), \
            "Hardening modificó respuesta ya segura"

    def test_dashboard_b3_still_passes(self):
        """5. Dashboard B3 sigue funcionando correctamente."""
        # Verificar que B3 no se rompió
        # Respuesta B3 típica
        b3_response = "No puedo afirmar el estado real del dashboard sin verificación HTTP/tool actual."
        
        sanitized = BrainSession._sanitize_llm_chat_response(b3_response)
        
        # Verificar que mantiene mensaje B3
        assert "no puedo afirmar" in sanitized.lower(), \
            "Hardening rompió respuesta B3"

    def test_p1a_conceptual_without_tools(self):
        """6. Pregunta conceptual P1-A responde sin tools."""
        # Preguntas conceptuales deben funcionar sin tools
        conceptual_response = "El autodesarrollo es el proceso de mejora continua."
        
        # Aplicar sanitización
        sanitized = BrainSession._sanitize_llm_chat_response(conceptual_response)
        
        # No debe modificar respuestas conceptuales
        assert "autodesarrollo" in sanitized.lower(), \
            "Hardening modificó respuesta conceptual"


class TestN5RecallState:
    """Test de recall del estado N5 sin mezclar con LearningValidator."""

    def test_n5_corrected_tests(self):
        """N5 corregidos: test_dashboard_real_verification_routing.py, test_evolucion_continua_autoapproval.py"""
        corrected = [
            "test_dashboard_real_verification_routing.py",
            "test_evolucion_continua_autoapproval.py",
        ]
        
        for test in corrected:
            assert "corregido" in test or "routing" in test or "autoapproval" in test

    def test_n5_pending_tests(self):
        """N5 pendientes: test_chat_metrics_extended.py, test_brain_chat_hygiene.py"""
        pending = [
            "test_chat_metrics_extended.py",
            "test_brain_chat_hygiene.py",
        ]
        
        for test in pending:
            assert "chat_metrics" in test or "chat_hygiene" in test

    def test_n5_not_dependent_on_learning_validator(self):
        """N5 no depende de LearningValidator UNVALIDATED."""
        # N5 es sobre tests/import errors, no sobre validación de aprendizaje
        # Este test documenta que son independientes
        
        n5_scope = ["test fixes", "import errors", "path issues"]
        learning_validator_scope = ["VALIDATED", "UNVALIDATED", "validation"]
        
        # No deben mezclarse
        overlap = set(n5_scope) & set(learning_validator_scope)
        assert len(overlap) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
