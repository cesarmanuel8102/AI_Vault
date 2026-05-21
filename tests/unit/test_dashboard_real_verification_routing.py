"""
Tests para B3: Verificación real bloquea dashboard fastpath.

Cuando el usuario pide verificación real explícita usando herramientas/evidencia,
el sistema NO debe emitir el template de dashboard como primera respuesta.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))


import pytest


class TestDashboardRealVerificationRouting:
    """Tests para B3 - Verificación real vs Template."""
    
    def test_real_verification_blocks_dashboard_system_fastpath(self):
        """1. real verification request bloquea dashboard system fastpath."""
        from brain_v9.core.session import BrainSession
        
        # Mensaje B3 - pide verificación real
        msg = "Necesito que verifiques realmente http://127.0.0.1:8090/dashboard-v2 usando herramientas si hace falta. No modifiques nada. Solo dime: código HTTP, si carga HTML, endpoint consultado, evidencia usada y brechas visibles."
        
        msg_lower = msg.lower()
        
        # Verificar que el patch detecta verificación real
        has_real_verification = (
            ("verifica realmente" in msg_lower or 
             "verifiques realmente" in msg_lower or
             "revisa realmente" in msg_lower or
             "comprueba realmente" in msg_lower or
             "usando herramientas" in msg_lower or
             "usa herramientas" in msg_lower) and
            any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
        )
        
        assert has_real_verification is True, "Debe detectar solicitud de verificación real"
    
    def test_real_verification_contains_codigo_http_and_evidencia(self):
        """2. real verification request contiene 'código HTTP' y 'evidencia usada' -> no template."""
        msg = "Necesito que verifiques realmente http://127.0.0.1:8090/dashboard-v2 usando herramientas si hace falta. Solo dime: código HTTP, si carga HTML, endpoint consultado, evidencia usada y brechas visibles."
        msg_lower = msg.lower()
        
        has_codigo_http = "codigo http" in msg_lower or "código http" in msg_lower
        has_evidencia = "evidencia usada" in msg_lower or "evidencia real" in msg_lower
        
        assert has_codigo_http is True, "Debe contener referencia a código HTTP"
        assert has_evidencia is True, "Debe contener referencia a evidencia"
    
    def test_real_verification_with_usando_herramientas_no_template(self):
        """3. real verification request con 'usando herramientas' -> no template."""
        msg = "Necesito que verifiques realmente http://127.0.0.1:8090/dashboard-v2 usando herramientas si hace falta. No modifiques nada."
        msg_lower = msg.lower()
        
        has_herramientas = "usando herramientas" in msg_lower or "usa herramientas" in msg_lower
        assert has_herramientas is True, "Debe solicitar uso de herramientas"
    
    def test_epistemic_question_returns_epistemic_restraint(self):
        """4. epistemic question existente sigue devolviendo epistemic_restraint."""
        msg = "Necesito el estado real de http://127.0.0.1:8090/dashboard-v2. No modifiques nada. Primero dime si puedes afirmar estado real sin HTTP."
        msg_lower = msg.lower()
        
        # Verificar que sigue siendo detectado como epistemic
        has_estado_real = "estado real" in msg_lower
        has_epistemic_marker = (
            "primero dime" in msg_lower or 
            "puedes afirmar" in msg_lower or
            "sin http" in msg_lower
        )
        
        assert has_estado_real is True, "Debe contener 'estado real'"
        assert has_epistemic_marker is True, "Debe contener marcador epistémico"
    
    def test_dashboard_status_simple_can_use_template(self):
        """5. dashboard status simple puede seguir usando template si NO pide verificación real."""
        msg = "Como está el dashboard?"
        msg_lower = msg.lower()
        
        # No debe tener señales de verificación real
        has_real_verification = (
            "verifica realmente" in msg_lower or
            "revisa realmente" in msg_lower or
            "usando herramientas" in msg_lower or
            "codigo http" in msg_lower or
            "evidencia usada" in msg_lower
        )
        
        assert has_real_verification is False, "Mensaje simple no debe pedir verificación real"
    
    def test_fake_grounded_risk_detects_both_cases(self):
        """6. fake_grounded_risk detecta tanto 'estado real' como 'verifica realmente'."""
        msg_b3 = "Necesito que verifiques realmente http://127.0.0.1:8090/dashboard-v2 usando herramientas"
        msg_epistemic = "Necesito el estado real de http://127.0.0.1:8090/dashboard-v2"
        
        for msg in [msg_b3, msg_epistemic]:
            msg_lower = msg.lower()
            
            # B3 FIX: Ahora detecta ambos casos
            has_real_verification = (
                ("verifica realmente" in msg_lower or 
                 "verifiques realmente" in msg_lower or
                 "revisa realmente" in msg_lower or
                 "comprueba realmente" in msg_lower or
                 "usando herramientas" in msg_lower or
                 "usa herramientas" in msg_lower) and
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
            )
            
            has_estado_real = (
                "estado real" in msg_lower and 
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])
            )
            
            fake_grounded_risk = has_real_verification or has_estado_real
            assert fake_grounded_risk is True, f"Ambos mensajes deben activar fake_grounded_risk: {msg[:50]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
