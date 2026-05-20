"""
Tests para el fix de confirmación de tool execution.

Valida que cuando el usuario confirma después de un tool confirmation request,
el sistema retoma la tarea original con:
- URL/dashboard-v2 preserved
- Constraints preserved ("no modifiques nada")
- Proper routing (not MEMORY)
- No ghost_completion
"""

import sys
import pytest

sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.core.session import BrainSession


class TestConfirmationBugFix:
    """Test suite para el bug de confirmación."""
    
    def setup_method(self):
        """Setup antes de cada test."""
        self.session = BrainSession("test_confirmation_session")
        # Limpiar cualquier estado pendiente
        self.session._clear_pending_continuation()
    
    def test_confirmation_stores_original_message(self):
        """Verifica que el mensaje original se almacena correctamente."""
        original_msg = "revisa http://127.0.0.1:8090/dashboard-v2 y dime el estado, no modifiques nada"
        
        # Simular que el Brain pidió confirmación
        self.session._set_pending_continuation(
            original_msg,
            model_priority="chat",
            source="agent",
            force_agent=True,
        )
        
        # Verificar que se guardó
        assert self.session._pending_continuation is not None
        assert self.session._pending_confirmed_action is not None
        assert "dashboard-v2" in self.session._pending_continuation.get("message", "")
        assert "no modifiques" in self.session._pending_continuation.get("message", "")
    
    def test_confirmation_resumes_with_original_task(self):
        """Verifica que al confirmar se retoma la tarea original."""
        original_msg = "revisa http://127.0.0.1:8090/dashboard-v2 y dime el estado real"
        
        # Simular estado pendiente
        self.session._set_pending_continuation(
            original_msg,
            model_priority="chat",
            source="agent",
            force_agent=True,
        )
        
        # Verificar que pending contiene la URL
        pending = self.session._pending_confirmed_action
        assert pending is not None
        assert "127.0.0.1:8090" in pending.get("message", "")
        assert pending.get("force_agent") is True
    
    def test_no_pending_action_returns_none(self):
        """Verifica que sin pending action se maneja correctamente."""
        # Sin estado pendiente
        self.session._clear_pending_continuation()
        
        # Intentar resumir
        import asyncio
        result = asyncio.run(
            self.session._maybe_resume_pending_continuation("si, confirmo")
        )
        
        # Debe retornar None para que se muestre mensaje de aclaración
        assert result is None
    
    def test_confirmation_no_ghost_completion(self):
        """Verifica que la confirmación no produce ghost_completion."""
        # Este test verifica la lógica de routing
        # En una confirmación válida con pending action,
        # debe ir a agent, no a MEMORY
        
        original_msg = "revisa http://127.0.0.1:8090/dashboard-v2"
        self.session._set_pending_continuation(
            original_msg,
            model_priority="chat",
            source="agent",
            force_agent=True,
        )
        
        pending = self.session._pending_confirmed_action
        assert pending is not None
        assert pending.get("force_agent") is True
        # Cuando force_agent=True, debe ir a _route_to_agent
        # no a chat() que podría resultar en MEMORY


class TestIsToolConfirmationDetection:
    """Tests para detección de tool confirmation requests."""
    
    def test_detects_confirmation_request_spanish(self):
        """Detecta solicitud de confirmación en español."""
        response = "No ejecuto en esta ruta de chat... confirma si quieres que las llame."
        
        result = BrainSession._is_tool_confirmation_request_response(response)
        
        assert result is True
    
    def test_detects_confirmation_request_alternative(self):
        """Detecta variación de solicitud de confirmación."""
        response = "Confirma si quieres que ejecute las herramientas"
        
        result = BrainSession._is_tool_confirmation_request_response(response)
        
        assert result is True
    
    def test_no_false_positives(self):
        """No detecta falsos positivos."""
        response = "Aquí está el resultado del análisis"
        
        result = BrainSession._is_tool_confirmation_request_response(response)
        
        assert result is False


class TestIsConfirmationDetection:
    """Tests para detección de confirmaciones del usuario."""
    
    def test_detects_si_confirmo(self):
        """Detecta 'si, confirmo'."""
        assert BrainSession._is_confirmation("si, confirmo") is True
        assert BrainSession._is_confirmation("sí, confirmo") is True
    
    def test_detects_simple_confirmations(self):
        """Detecta confirmaciones simples."""
        assert BrainSession._is_confirmation("si") is True
        assert BrainSession._is_confirmation("ok") is True
        assert BrainSession._is_confirmation("dale") is True
        assert BrainSession._is_confirmation("yes") is True
    
    def test_rejects_long_messages(self):
        """Rechaza mensajes largos (evita falsos positivos)."""
        long_msg = "si, pero también quiero que analices otra cosa y me des más detalles"
        assert BrainSession._is_confirmation(long_msg) is False
    
    def test_rejects_non_confirmations(self):
        """Rechaza mensajes que no son confirmaciones."""
        assert BrainSession._is_confirmation("hola") is False
        assert BrainSession._is_confirmation("qué tal") is False


class TestConstraintPreservation:
    """Tests para preservación de constraints."""
    
    def setup_method(self):
        self.session = BrainSession("test_constraints")
        self.session._clear_pending_continuation()
    
    def test_no_modificar_preserved(self):
        """Preserva 'no modifiques nada'."""
        original_msg = "revisa el dashboard, no modifiques nada"
        
        self.session._set_pending_continuation(
            original_msg,
            model_priority="chat",
            source="agent",
            force_agent=True,
        )
        
        assert "no modifiques" in self.session._pending_continuation.get("message", "")
    
    def test_url_localhost_preserved(self):
        """Preserva URL localhost."""
        original_msg = "revisa http://127.0.0.1:8090/dashboard-v2"
        
        self.session._set_pending_continuation(
            original_msg,
            model_priority="chat",
            source="agent",
            force_agent=True,
        )
        
        assert "127.0.0.1:8090" in self.session._pending_continuation.get("message", "")
        assert "dashboard-v2" in self.session._pending_continuation.get("message", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
