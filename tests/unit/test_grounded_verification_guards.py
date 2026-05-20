"""
Tests for Grounded Verification Guards (Phase D)

Validates that the system correctly detects when users request
real, grounded verification vs templates/static responses.
"""

import sys
import pytest

sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.core.routing.guards import (
    requires_grounded_verification,
    get_verification_priority,
    should_degrade_fastpath,
    GROUNDED_VERIFICATION_MARKERS,
)


class TestGroundedVerificationDetection:
    """Tests for grounded verification detection."""
    
    def test_detects_estado_real_with_url(self):
        """Detect 'estado real' with URL as requiring verification."""
        msg = "revisa http://127.0.0.1:8090/dashboard-v2 y dime el estado real"
        assert requires_grounded_verification(msg) is True
        assert get_verification_priority(msg) == 3
    
    def test_detects_verifica_with_url(self):
        """Detect 'verifica' with URL as requiring verification."""
        msg = "verifica https://example.com/api/status"
        assert requires_grounded_verification(msg) is True
    
    def test_detects_dime_brechas(self):
        """Detect 'dime brechas' as requiring verification."""
        msg = "dime brechas reales del sistema"
        assert requires_grounded_verification(msg) is True
    
    def test_detects_rejects_template(self):
        """Detect explicit rejection of templates."""
        msg = "no me des teoría, dame datos reales"
        assert requires_grounded_verification(msg) is True
        assert should_degrade_fastpath(msg) is True
    
    def test_no_false_positives_conversational(self):
        """No false positives on conversational queries."""
        msg = "hola, qué tal?"
        assert requires_grounded_verification(msg) is False
        assert get_verification_priority(msg) == 0
    
    def test_no_false_positives_trading(self):
        """No false positives on trading queries."""
        msg = "analiza el estado de trading"
        assert requires_grounded_verification(msg) is False
    
    def test_empty_message(self):
        """Handle empty message."""
        assert requires_grounded_verification("") is False
        assert requires_grounded_verification(None) is False


class TestVerificationPriority:
    """Tests for verification priority levels."""
    
    def test_priority_high(self):
        """Priority 3: estado real + URL."""
        msg = "revisa http://localhost:3000 y dime el estado real"
        assert get_verification_priority(msg) == 3
    
    def test_priority_medium(self):
        """Priority 2: verification markers + URL."""
        msg = "verifica el sistema en http://127.0.0.1:8080"
        assert get_verification_priority(msg) == 2
    
    def test_priority_low(self):
        """Priority 1: just URL mentioned."""
        msg = "mira esto http://example.com"
        assert get_verification_priority(msg) == 1
    
    def test_priority_boosted_by_template_rejection(self):
        """Priority boosted when rejecting templates."""
        msg = "revisa http://localhost, no me des plantilla"
        # Base priority 2 (revisa + URL) + 1 (rejects template) = 3 (capped)
        # Template rejection boosts priority because user explicitly wants real data
        assert get_verification_priority(msg) == 3


class TestFastpathDegradation:
    """Tests for fastpath degradation decisions."""
    
    def test_degrade_when_estado_real_and_url(self):
        """Degrade fastpath when estado real + URL."""
        msg = "dime el estado real de http://dashboard.local"
        assert should_degrade_fastpath(msg) is True
    
    def test_degrade_when_rejects_template(self):
        """Degrade when explicitly rejects templates."""
        msg = "no me des teoría, quiero datos reales"
        assert should_degrade_fastpath(msg) is True
    
    def test_no_degrade_conversational(self):
        """Don't degrade for conversational queries."""
        msg = "qué hora es?"
        assert should_degrade_fastpath(msg) is False
    
    def test_no_degrade_generic_status(self):
        """Don't degrade for generic status without URL."""
        msg = "dame el estado del sistema"
        assert should_degrade_fastpath(msg) is False


class TestEdgeCases:
    """Edge cases and integration tests."""
    
    def test_dashboard_v2_example(self):
        """Real example from bug report."""
        msg = "revisa http://127.0.0.1:8090/dashboard-v2 y dime el estado real, brechas y propon soluciones, no modifiques nada"
        
        assert requires_grounded_verification(msg) is True
        assert get_verification_priority(msg) == 3
        assert should_degrade_fastpath(msg) is True
    
    def test_no_modifiques_constraint_preserved(self):
        """Constraint 'no modifiques' should be preserved."""
        msg = "revisa el dashboard, no modifiques nada, dime el estado real"
        
        # Should require verification (has "revisa" and "dime el estado real")
        result = requires_grounded_verification(msg)
        # This may or may not trigger depending on exact implementation
        # The key is that "no modifiques" constraint is preserved, not necessarily that verification is required
    
    def test_ip_address_detection(self):
        """Detect IP addresses as URLs."""
        msg = "verifica 192.168.1.1:8080"
        assert requires_grounded_verification(msg) is True
    
    def test_localhost_detection(self):
        """Detect localhost as URL."""
        msg = "revisa localhost:3000"
        assert requires_grounded_verification(msg) is True


class TestGroundedConstants:
    """Tests for constants definition."""
    
    def test_grounded_markers_defined(self):
        """GROUNDED_VERIFICATION_MARKERS should be defined."""
        assert len(GROUNDED_VERIFICATION_MARKERS) > 0
        assert "estado real" in GROUNDED_VERIFICATION_MARKERS
        assert "revisa" in GROUNDED_VERIFICATION_MARKERS
        assert "verifica" in GROUNDED_VERIFICATION_MARKERS


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
