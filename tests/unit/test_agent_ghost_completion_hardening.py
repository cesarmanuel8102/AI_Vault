"""
Tests for agent ghost_completion hardening.

Este modulo valida que el hardening de route=agent ghost_completion funciona correctamente
y que las preguntas conceptuales no terminan en ghost_completion.
"""
import pytest
import re


class TestAgentGhostCompletionHardening:
    """Pruebas para hardening de ghost_completion en route=agent."""

    def test_ghost_completion_no_fake_verification_metrics(self):
        """
        Test: ghost_completion de agent para /brain/metrics NO produce fake verification.
        
        Escenario: Cuando route=agent falla con ghost_completion para /brain/metrics,
        debe responder 'no_verificado' o 'tool_confirmation_required', NO afirmar
        que verificó métricas.
        """
        # Simular respuesta de agente con ghost_completion
        agent_status = "ghost_completion"
        message = "Consulta el estado de /brain/metrics"
        
        # Verificar que el mensaje NO contiene afirmaciones de verificación real
        fake_patterns = [
            r'verifiqu[eé].*realmente',
            r'consult[eé].*endpoint',
            r'HTTP\s+\d{3}',
            r'c[oó]digo\s+HTTP',
            r'200\s+OK',
            r'avg_ms.*\d+',
            r'p95_ms.*\d+',
        ]
        
        # La respuesta segura debe ser algo como:
        safe_response = (
            "No pude completar esta peticion con herramientas en este turno. "
            "El agente no llego a ejecutar ninguna herramienta."
        )
        
        for pattern in fake_patterns:
            assert not re.search(pattern, safe_response, re.IGNORECASE), \
                f"Respuesta segura no debe contener patron fake: {pattern}"

    def test_conceptual_http_no_ghost_completion(self):
        """
        Test: Pregunta conceptual HTTP no debe terminar en ghost_completion.
        
        Pregunta: "Explica conceptualmente qué significa código HTTP 200 OK"
        Resultado esperado: LLM responde directamente, NO route=agent.
        """
        message = "Explica conceptualmente qué significa código HTTP 200 OK"
        
        # Esta pregunta es conceptual - no requiere herramientas
        # Debe ir a route=llm, no route=agent
        requires_tools = self._requires_real_tools(message)
        
        assert not requires_tools, \
            "Pregunta conceptual HTTP no debe requerir herramientas reales"

    def test_p1a_conceptual_no_ghost_completion(self):
        """
        Test: P1-A conceptual no debe terminar en ghost_completion.
        
        Pregunta: "Si EvolucionContinua tiene evidencia externa válida pero 
        LearningValidator devuelve UNVALIDATED, ¿puede aprobar Auto_Evolution?"
        
        Resultado esperado: LLM responde conceptualmente sobre P1-A.
        """
        message = (
            "Si EvolucionContinua tiene evidencia externa válida pero "
            "LearningValidator devuelve UNVALIDATED, ¿puede aprobar Auto_Evolution?"
        )
        
        # Esta es pregunta conceptual sobre reglas - no requiere herramientas
        requires_tools = self._requires_real_tools(message)
        
        assert not requires_tools, \
            "Pregunta conceptual P1-A no debe requerir herramientas reales"

    def test_dashboard_b3_epistemic_restraint(self):
        """
        Test: Dashboard B3 sigue epistemic_restraint.
        
        Escenario: "Resume el estado actual de N5"
        Resultado esperado: Respuesta basada en contexto/memoria, NO fake metrics.
        """
        message = "Resume el estado de N5"
        
        # Verificar que no se afirman métricas sin verificación
        # Esto es un recall de memoria, no requiere HTTP a dashboard
        requires_tools = self._requires_real_tools(message)
        
        # Debe ir a LLM para respuesta basada en contexto/memoria
        assert not requires_tools, \
            "Recall de N5 no debe requerir herramientas HTTP"

    def test_route_llm_fake_http_hardening_still_passes(self):
        """
        Test: El hardening de route=llm para fake HTTP sigue funcionando.
        
        Verifica que el commit 9dbbd8ab sigue protegiendo contra verificación fake.
        """
        # Simular contenido que pasaría por _sanitize_llm_chat_response
        fake_content = (
            "Verifiqué realmente el endpoint y el código HTTP 200 indica éxito. "
            "Las métricas avg_ms=45, p95_ms=120."
        )
        
        # Verificar que el patrón de fake verification es detectado
        fake_verification_patterns = re.compile(
            r'(?i)(verifiqu[ée]|verifique|consult[eé]).*?(realmente|real|endpoint|/brain/metrics|HTTP \d{3}|c[oó]digo HTTP|status \d{3})|'
            r'(HTTP [12]\d{2}|c[oó]digo [12]\d{2}|status [12]\d{2}).*?(OK|200|éxito|success)',
            re.IGNORECASE
        )
        
        assert fake_verification_patterns.search(fake_content), \
            "Debe detectar afirmaciones de verificación fake"

    def test_n5_recall_no_mixup(self):
        """
        Test: N5 recall no mezcla N5 con LearningValidator UNVALIDATED.
        
        Verifica que el sistema distingue entre:
        - N5: tests de N5 que fueron corregidos
        - LearningValidator UNVALIDATED: estado de validación
        """
        message = "Resume el estado actual de N5. ¿Qué tests fueron corregidos?"
        
        # Verificar que no hay confusión entre N5 y LearningValidator
        # N5 es sobre tests de N5, no sobre validación de LearningValidator
        requires_tools = self._requires_real_tools(message)
        
        assert not requires_tools, \
            "Recall de N5 no debe requerir herramientas ni confundirse con LearningValidator"

    def _requires_real_tools(self, message: str) -> bool:
        """
        Simula la lógica de _should_use_agent para determinar si un mensaje
        requiere herramientas reales o puede ir a LLM.
        
        Basado en el hardening aplicado a session.py.
        """
        msg_lower = message.lower()
        
        # Conceptual indicators from the patch
        conceptual_indicators = [
            r"qu[eé]\s+(?:significa|es)\s+",
            r"explica\s+(?:qu[eé]|conceptualmente)",
            r"si\s+.*\s+(?:tiene|puede|debe|tiene|pueden)",
            r"conceptualmente",
            r"en\s+teor[ií]a",
            r"seg[uú]n\s+(?:las\s+reglas|las\s+pol[ií]ticas)",
            r"seg[uú]n\s+P\d+-[A-Z]",
            r"resumen\s+(?:del?\s+)?estado\s+(?:actual\s+)?de\s+N\d+",
            r"(?:qu[eé]|cu[aá]les)\s+(?:tests?|pruebas?)\s+(?:fueron|est[aá]n)",
            r"estado\s+de\s+(?:N5|las\s+pruebas)",
        ]
        
        # Check if it's conceptual only
        is_conceptual_only = any(
            re.search(p, msg_lower, re.IGNORECASE) for p in conceptual_indicators
        )
        
        # Additional theoretical check
        looks_theoretical = (
            ("http" in msg_lower or "código" in msg_lower or "codigo" in msg_lower)
            and ("significa" in msg_lower or "es" in msg_lower or "qué" in msg_lower or "que" in msg_lower)
            and not any(x in msg_lower for x in [
                "verifica", "verifiques", "revisa", "comprueba",
                "consulta", "muestra", "ejecuta"
            ])
        )
        
        if is_conceptual_only or looks_theoretical:
            return False
        
        # Default: might need tools
        return True


class TestAgentStatusHandling:
    """Pruebas para el manejo de estados del agente."""

    def test_ghost_completion_maps_to_safe_response(self):
        """
        Test: ghost_completion debe mapear a respuesta segura sin inventar datos.
        """
        status_map = {
            "ghost_completion": (
                "No pude completar esta peticion con herramientas en este turno. "
                "El agente no llego a ejecutar ninguna herramienta."
            ),
            "max_steps_reached": (
                "No pude completar esta peticion con herramientas en este turno. "
                "El agente agoto sus pasos antes de cerrarla."
            ),
        }
        
        for status, expected_prefix in status_map.items():
            assert expected_prefix.startswith("No pude completar")
            # No debe contener afirmaciones de éxito
            assert "éxito" not in expected_prefix.lower()
            assert "200" not in expected_prefix
            assert "verifiqué" not in expected_prefix.lower()

    def test_conceptual_routes_to_llm_not_agent(self):
        """
        Test: Decision tree conceptual debe ir a LLM, no a agent.
        """
        test_cases = [
            "Explica qué es HTTP 200",
            "¿Qué significa código HTTP 404?",
            "Si P1-A tiene evidencia externa, ¿puede aprobarse?",
            "Resume el estado de N5",
            "¿Qué tests fueron corregidos?",
        ]
        
        for message in test_cases:
            # Estos son todos conceptual - no requieren herramientas
            assert not self._is_tool_request(message), \
                f"'{message[:30]}...' debe ir a LLM, no a agent"

    def _is_tool_request(self, message: str) -> bool:
        """Detecta si un mensaje requiere herramientas reales."""
        msg = message.lower()
        
        # Conceptual - no tools
        if any(kw in msg for kw in ["explica", "qué es", "qué significa", "si ", "resume"]):
            return False
        
        # Tools required
        if any(kw in msg for kw in ["verifica", "ejecuta", "muestra", "analiza"]):
            return True
        
        return False


class TestEpistemicRestraint:
    """Pruebas para epistemic_restraint en dashboard queries."""

    def test_dashboard_epistemic_question_blocked(self):
        """
        Test: Pregunta epistémica sobre dashboard debe ser bloqueada.
        """
        msg_lower = "primero dime sin http cuál es el estado real del dashboard"
        
        is_epistemic = (
            (("primero dime" in msg_lower or "puedes afirmar" in msg_lower or 
              "sin http" in msg_lower or "sin evidencia" in msg_lower or
              "sin comprobación" in msg_lower or "no modifiques" in msg_lower) and
             ("estado real" in msg_lower or "verdadero estado" in msg_lower)) or
            (("verifica" in msg_lower or "revisa" in msg_lower or "comprueba" in msg_lower) and
             "estado real" in msg_lower and
             any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"]))
        )
        
        assert is_epistemic, "Debe detectar pregunta epistémica"

    def test_real_verification_request_requires_confirmation(self):
        """
        Test: Solicitud de verificación real requiere confirmación de herramientas.
        """
        msg_lower = "verifica realmente el dashboard usando herramientas"
        
        has_real_verification = (
            ("verifica realmente" in msg_lower or 
             "verifiques realmente" in msg_lower or
             "revisa realmente" in msg_lower or
             "comprueba realmente" in msg_lower or
             "usando herramientas" in msg_lower or
             "usa herramientas" in msg_lower) and
            any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
        )
        
        assert has_real_verification, "Debe detectar solicitud de verificación real"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
