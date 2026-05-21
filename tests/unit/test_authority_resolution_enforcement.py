"""Tests REALES de Authority Resolution - FASE 6-7

Validan que:
- USER_CONSTRAINTS ganan sobre fastpaths
- EPISTEMIC_SAFETY bloquea templates
- VERIFICATION_POLICY degrada claims
- NO hay mixed emissions
- NO hay authority override
- NO hay timeout loops
"""

import pytest
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tmp_agent"))

from brain_v9.core.routing.authority_resolution import (
    resolve_authority_precedence,
    lock_epistemic_mode,
    validate_emission_safety,
    EpistemicMode,
)


class TestAuthorityPrecedenceEnforcement:
    """Tests de enforcemiento de precedencia de autoridad."""
    
    def test_user_constraints_no_tools_blocks_agent(self):
        """USER_CONSTRAINTS > ROUTE_SELECTION"""
        result = resolve_authority_precedence(
            user_constraints={"no_tools": True, "no_modify": False},
            epistemic_risk={"fake_grounded_risk": False},
            verification_required=False,
            proposed_route="agent",
        )
        
        assert result["allowed"] is False
        assert result["authority_applied"] == "user_constraints"
        assert "agent" in result["blocked_routes"]
        assert result["final_mode"] == EpistemicMode.NO_TOOLS_REASONING
    
    def test_user_constraints_no_trading_blocks_qc_live(self):
        """USER_CONSTRAINTS > FASTPATH_CONVENIENCE"""
        result = resolve_authority_precedence(
            user_constraints={"no_trading": True},
            epistemic_risk={},
            verification_required=False,
            proposed_route="qc_live_fastpath",
        )
        
        assert result["allowed"] is False
        assert result["blocked_routes"] == ["qc_live_fastpath"]
        assert result["authority_applied"] == "user_constraints"
    
    def test_epistemic_safety_blocks_fake_grounded_fastpath(self):
        """EPISTEMIC_SAFETY > FASTPATH_CONVENIENCE"""
        result = resolve_authority_precedence(
            user_constraints={},
            epistemic_risk={"fake_grounded_risk": True},
            verification_required=False,
            proposed_route="fastpath",
        )
        
        assert result["allowed"] is False
        assert result["authority_applied"] == "epistemic_safety"
        assert result["final_mode"] == EpistemicMode.DEGRADED
    
    def test_verification_policy_blocks_fastpath_without_evidence(self):
        """VERIFICATION_POLICY > FASTPATH_CONVENIENCE"""
        result = resolve_authority_precedence(
            user_constraints={},
            epistemic_risk={},
            verification_required=True,
            proposed_route="fastpath",
        )
        
        assert result["allowed"] is False
        assert result["authority_applied"] == "verification_policy"
        assert "verification required but no evidence" in result["reason"].lower()
    
    def test_verification_policy_allows_agent_with_tools(self):
        """VERIFICATION_POLICY permite agent cuando puede verificar"""
        result = resolve_authority_precedence(
            user_constraints={},
            epistemic_risk={},
            verification_required=True,
            proposed_route="agent",
        )
        
        assert result["allowed"] is True  # Agent puede usar tools para verificar
        assert result["final_mode"] == EpistemicMode.VERIFIED
    
    def test_fastpath_allowed_when_no_conflicts(self):
        """FASTPATH_CONVENIENCE funciona cuando no hay conflictos superiores"""
        result = resolve_authority_precedence(
            user_constraints={},
            epistemic_risk={},
            verification_required=False,
            proposed_route="fastpath",
        )
        
        assert result["allowed"] is True
        assert result["authority_applied"] == "fastpath_convenience"


class TestEpistemicModeLocking:
    """Tests de locking de modo epistémico."""
    
    def test_degraded_cannot_elevate_to_verified_without_evidence(self):
        """degraded NO puede pasar a verified sin tool/evidence"""
        final_mode, can_elevate = lock_epistemic_mode(
            current_mode=EpistemicMode.DEGRADED,
            proposed_elevation=EpistemicMode.VERIFIED,
            evidence_level="inferred",  # Sin evidencia real
        )
        
        assert final_mode == EpistemicMode.DEGRADED  # NO cambió
        assert can_elevate is False
    
    def test_degraded_can_elevate_to_verified_with_tool_evidence(self):
        """degraded SÍ puede pasar a verified CON tool evidence"""
        final_mode, can_elevate = lock_epistemic_mode(
            current_mode=EpistemicMode.DEGRADED,
            proposed_elevation=EpistemicMode.VERIFIED,
            evidence_level="tool",
        )
        
        assert final_mode == EpistemicMode.VERIFIED
        assert can_elevate is True
    
    def test_inferred_cannot_elevate_to_verified_by_memory(self):
        """inferred NO puede pasar a verified solo por memoria"""
        final_mode, can_elevate = lock_epistemic_mode(
            current_mode=EpistemicMode.INFERRED,
            proposed_elevation=EpistemicMode.VERIFIED,
            evidence_level="memory",  # Memoria no es suficiente
        )
        
        # Memory permite subir a inferred pero no a verified
        assert can_elevate is False or final_mode != EpistemicMode.VERIFIED
    
    def test_mode_can_degrade_freely(self):
        """Sí se puede degradar (bajar) sin restricciones"""
        final_mode, can_elevate = lock_epistemic_mode(
            current_mode=EpistemicMode.VERIFIED,
            proposed_elevation=EpistemicMode.DEGRADED,
            evidence_level="none",
        )
        
        assert final_mode == EpistemicMode.DEGRADED
        assert can_elevate is True  # Degradar siempre permitido


class TestEmissionSafetyValidation:
    """Tests de validación de seguridad de emisión."""
    
    def test_rejects_operational_claim_without_evidence(self):
        """Rechaza claims operacionales sin evidencia"""
        is_safe, reason, _ = validate_emission_safety(
            response_content="El dashboard está funcionando correctamente",
            response_mode=EpistemicMode.INFERRED,
            user_constraints={},
            blocked_routes=[],
        )
        
        assert is_safe is False
        assert "operational claim" in reason.lower() or "evidencia" in reason.lower()
    
    def test_accepts_conceptual_analysis(self):
        """Acepta análisis conceptual"""
        is_safe, reason, _ = validate_emission_safety(
            response_content="Podemos analizar la arquitectura conceptualmente",
            response_mode=EpistemicMode.NO_TOOLS_REASONING,
            user_constraints={"no_tools": True},
            blocked_routes=[],
        )
        
        assert is_safe is True
    
    def test_rejects_tool_mention_when_no_tools_constraint(self):
        """Rechaza mención de tools cuando user prohibió tools"""
        is_safe, reason, alternative = validate_emission_safety(
            response_content="Usaré la tool de análisis",
            response_mode=EpistemicMode.NO_TOOLS_REASONING,
            user_constraints={"no_tools": True},
            blocked_routes=[],
        )
        
        assert is_safe is False
        assert "tool" in reason.lower()
        assert alternative is not None
    
    def test_rejects_mixed_emission_template_in_degraded(self):
        """Rechaza formato template en modo degraded"""
        is_safe, reason, _ = validate_emission_safety(
            response_content="**Dashboard Status**: *activo*",
            response_mode=EpistemicMode.DEGRADED,
            user_constraints={},
            blocked_routes=[],
        )
        
        assert is_safe is False
        assert "mixed" in reason.lower() or "template" in reason.lower()


class TestRealWorldScenarios:
    """Escenarios del mundo real."""
    
    def test_dashboard_url_with_real_status_request(self):
        """
        Caso: "Necesito el estado real de http://127.0.0.1:8090/dashboard-v2"
        Expected: NO fastpath, verification required, degraded mode
        """
        user_constraints = {}
        epistemic_risk = {"fake_grounded_risk": True}  # Dashboard mencionado
        verification_required = True  # URL presente
        
        result = resolve_authority_precedence(
            user_constraints=user_constraints,
            epistemic_risk=epistemic_risk,
            verification_required=verification_required,
            proposed_route="fastpath",
        )
        
        # Debe ser bloqueado por verification_policy + epistemic_safety
        assert result["allowed"] is False
        assert result["final_mode"] == EpistemicMode.DEGRADED
    
    def test_no_tools_epistemic_analysis(self):
        """
        Caso: "No uses tools. ¿Sería fake grounded afirmar dashboard activo?"
        Expected: NO agent, no_tools_reasoning mode
        """
        result = resolve_authority_precedence(
            user_constraints={"no_tools": True},
            epistemic_risk={},
            verification_required=False,
            proposed_route="agent",
        )
        
        assert result["allowed"] is False
        assert result["final_mode"] == EpistemicMode.NO_TOOLS_REASONING
        assert "agent" in result["blocked_routes"]
    
    def test_no_trading_routing_analysis(self):
        """
        Caso: "No analices trading. Analiza routing conversacional."
        Expected: NO qc_live, NO trading fastpath
        """
        result = resolve_authority_precedence(
            user_constraints={"no_trading": True},
            epistemic_risk={},
            verification_required=False,
            proposed_route="qc_live_fastpath",
        )
        
        assert result["allowed"] is False
        assert "qc_live_fastpath" in result["blocked_routes"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
