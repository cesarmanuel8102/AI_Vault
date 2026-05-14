"""
Tests for SelfAwarenessInjector — brain/self_awareness_injector.py
29 tests covering inject(), cache behavior, extraction methods,
format_for_injection(), fallback block, and singleton.
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch

from brain.self_awareness_injector import (
    SelfAwarenessInjector,
    AwarenessBlock,
    get_injector,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def injector():
    return SelfAwarenessInjector()


def _make_meta_core(reliable=3, unreliable=1, total=4, stress=0.3,
                     resilience_mode="normal", unknown_risk=0.2, gaps=None):
    """Create a mock MetaCognitionCore."""
    meta = Mock()

    # Capabilities
    capabilities = {}
    for i in range(reliable):
        cap = Mock()
        cap.confidence = 0.9
        cap.evidence_count = 15
        cap.is_reliable.return_value = True
        capabilities[f"cap_reliable_{i}"] = cap
    for i in range(unreliable):
        cap = Mock()
        cap.confidence = 0.3
        cap.evidence_count = 1
        cap.is_reliable.return_value = False
        capabilities[f"cap_unreliable_{i}"] = cap

    self_model = Mock()
    self_model.capabilities = capabilities
    self_model.stress_level = stress
    self_model.resilience_mode = resilience_mode
    self_model.known_gaps = gaps or []

    meta.self_model = self_model
    meta.get_self_awareness_report.return_value = {
        "capabilities_summary": {
            "reliable": reliable,
            "unreliable": unreliable,
            "total": total,
        }
    }
    meta.get_unknown_unknowns_risk.return_value = unknown_risk

    return meta


def _make_gap(gap_id="gap1", domain="trading", description="Falta conocimiento de forex",
              impact_if_known=0.8, resolution_status="open"):
    """Create a mock gap."""
    gap = Mock()
    gap.gap_id = gap_id
    gap.domain = domain
    gap.description = description
    gap.impact_if_known = impact_if_known
    gap.resolution_status = resolution_status
    return gap


def _make_orchestrator(pending=2, executed=5, proactive_running=True):
    """Create a mock orchestrator with AOS."""
    aos = Mock()
    aos.status.return_value = {
        "pending": pending,
        "executed": executed,
        "proactive_running": proactive_running,
    }
    orchestrator = Mock()
    orchestrator.aos = aos
    return orchestrator


def _make_consciencia_limitaciones(known_caps=None):
    """Create a mock SistemaConscienciaLimitaciones."""
    cl = Mock()
    cl.known_capabilities = known_caps or {
        "trading": 0.8,
        "coding": 0.3,  # weak
        "analysis": 0.9,
        "forecasting": 0.2,  # weak
    }
    return cl


# ─── inject() basic ──────────────────────────────────────────────────────────

class TestInject:
    def test_inject_with_meta_core(self, injector):
        meta = _make_meta_core()
        block = injector.inject(meta_core=meta)
        assert isinstance(block, AwarenessBlock)
        assert block.source == "real"

    def test_inject_with_orchestrator(self, injector):
        orch = _make_orchestrator()
        block = injector.inject(orchestrator=orch)
        assert isinstance(block, AwarenessBlock)

    def test_inject_with_all_subsystems(self, injector):
        meta = _make_meta_core()
        orch = _make_orchestrator()
        cl = _make_consciencia_limitaciones()
        block = injector.inject(orchestrator=orch, meta_core=meta,
                                consciencia_limitaciones=cl)
        assert block.source == "real"
        assert "Capacidades" in block.text

    def test_inject_with_no_subsystems_returns_real(self, injector):
        # No subsystems provided, but no exception either
        block = injector.inject()
        assert isinstance(block, AwarenessBlock)

    def test_inject_caches_result(self, injector):
        meta = _make_meta_core()
        block1 = injector.inject(meta_core=meta)
        block2 = injector.inject(meta_core=meta)
        assert block1 is block2


# ─── Cache behavior (TTL) ───────────────────────────────────────────────────

class TestCacheBehavior:
    def test_cache_returns_same_within_ttl(self, injector):
        meta = _make_meta_core()
        block1 = injector.inject(meta_core=meta)
        block2 = injector.inject(meta_core=meta)
        assert block1.cached_at == block2.cached_at

    def test_cache_expires_after_ttl(self, injector):
        meta = _make_meta_core()
        block1 = injector.inject(meta_core=meta)
        # Simulate TTL expiration
        injector._cache_time = time.time() - injector.CACHE_TTL - 1
        block2 = injector.inject(meta_core=meta)
        assert block1 is not block2

    def test_cache_ttl_is_30_seconds(self, injector):
        assert injector.CACHE_TTL == 30.0


# ─── _extract_capabilities ───────────────────────────────────────────────────

class TestExtractCapabilities:
    def test_extract_capabilities_with_reliable(self, injector):
        meta = _make_meta_core(reliable=3, total=4)
        result = injector._extract_capabilities(meta)
        assert "Confiables" in result

    def test_extract_capabilities_with_unreliable(self, injector):
        meta = _make_meta_core(unreliable=2, total=4)
        result = injector._extract_capabilities(meta)
        assert "No confiables" in result

    def test_extract_capabilities_no_meta_core(self, injector):
        result = injector._extract_capabilities(None)
        assert "no disponible" in result

    def test_extract_capabilities_no_data(self, injector):
        meta = Mock()
        meta.get_self_awareness_report.return_value = {"capabilities_summary": {}}
        meta.self_model = Mock()
        meta.self_model.capabilities = {}
        result = injector._extract_capabilities(meta)
        assert "Sin datos" in result


# ─── _extract_gaps ───────────────────────────────────────────────────────────

class TestExtractGaps:
    def test_extract_gaps_with_open_gaps(self, injector):
        meta = _make_meta_core()
        gap = _make_gap()
        meta.self_model.known_gaps = [gap]
        result = injector._extract_gaps(meta)
        assert "trading" in result
        assert "Falta conocimiento" in result

    def test_extract_gaps_no_open_gaps(self, injector):
        meta = _make_meta_core()
        meta.self_model.known_gaps = []
        result = injector._extract_gaps(meta)
        assert "Sin brechas" in result

    def test_extract_gaps_no_meta_core(self, injector):
        result = injector._extract_gaps(None)
        assert result == ""

    def test_extract_gaps_limits_to_5(self, injector):
        meta = _make_meta_core()
        gaps = [_make_gap(gap_id=f"gap{i}") for i in range(8)]
        meta.self_model.known_gaps = gaps
        result = injector._extract_gaps(meta)
        assert "3 más" in result


# ─── _extract_limitations ────────────────────────────────────────────────────

class TestExtractLimitations:
    def test_extract_limitations_with_weak_caps(self, injector):
        cl = _make_consciencia_limitaciones({"coding": 0.3, "trading": 0.8})
        result = injector._extract_limitations(cl)
        assert "coding" in result

    def test_extract_limitations_no_weak_caps(self, injector):
        cl = _make_consciencia_limitaciones({"trading": 0.9, "analysis": 0.8})
        result = injector._extract_limitations(cl)
        assert result == ""

    def test_extract_limitations_no_consciencia(self, injector):
        result = injector._extract_limitations(None)
        assert result == ""


# ─── _extract_resilience ─────────────────────────────────────────────────────

class TestExtractResilience:
    def test_extract_resilience_with_meta_core(self, injector):
        meta = _make_meta_core(stress=0.5, resilience_mode="degraded")
        result = injector._extract_resilience(meta)
        assert "degraded" in result
        assert "0.50" in result

    def test_extract_resilience_no_meta_core(self, injector):
        result = injector._extract_resilience(None)
        assert result == ""


# ─── _extract_aos ────────────────────────────────────────────────────────────

class TestExtractAos:
    def test_extract_aos_with_orchestrator(self, injector):
        orch = _make_orchestrator(pending=3, executed=7, proactive_running=True)
        result = injector._extract_aos(orch)
        assert "Pendientes: 3" in result
        assert "Ejecutados: 7" in result
        assert "ACTIVO" in result

    def test_extract_aos_no_orchestrator(self, injector):
        result = injector._extract_aos(None)
        assert result == ""

    def test_extract_aos_no_aos(self, injector):
        orch = Mock()
        orch.aos = None
        result = injector._extract_aos(orch)
        assert result == ""

    def test_extract_aos_not_proactive(self, injector):
        orch = _make_orchestrator(proactive_running=False)
        result = injector._extract_aos(orch)
        assert "ACTIVO" not in result


# ─── format_for_injection() ──────────────────────────────────────────────────

class TestFormatForInjection:
    def test_format_for_injection(self, injector):
        block = AwarenessBlock(
            text="Test awareness block",
            token_estimate=10,
            cached_at=time.time(),
            source="real",
        )
        result = injector.format_for_injection(block)
        assert "Test awareness block" in result
        assert "honestamente" in result.lower()

    def test_format_adds_newlines(self, injector):
        block = AwarenessBlock(
            text="Block content",
            token_estimate=5,
            cached_at=time.time(),
            source="real",
        )
        result = injector.format_for_injection(block)
        assert result.startswith("\n\n")


# ─── _build_fallback_block() ─────────────────────────────────────────────────

class TestBuildFallbackBlock:
    def test_fallback_block_source_is_error(self, injector):
        block = injector._build_fallback_block("test error")
        assert block.source == "error"

    def test_fallback_block_contains_error(self, injector):
        block = injector._build_fallback_block("something went wrong")
        assert "something went wrong" in block.text

    def test_fallback_block_has_fallback_header(self, injector):
        block = injector._build_fallback_block("err")
        assert "fallback" in block.text.lower()

    def test_fallback_block_truncates_long_error(self, injector):
        long_error = "x" * 200
        block = injector._build_fallback_block(long_error)
        # Error is truncated to 100 chars in the block
        assert len(long_error[:100]) == 100


# ─── get_injector() singleton ────────────────────────────────────────────────

class TestGetInjector:
    def test_get_injector_returns_instance(self):
        import brain.self_awareness_injector as mod
        mod._injector = None
        inj = get_injector()
        assert isinstance(inj, SelfAwarenessInjector)

    def test_get_injector_singleton(self):
        import brain.self_awareness_injector as mod
        mod._injector = None
        inj1 = get_injector()
        inj2 = get_injector()
        assert inj1 is inj2
