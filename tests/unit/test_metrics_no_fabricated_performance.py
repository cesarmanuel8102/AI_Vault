"""Test N1 mitigation: Verify metrics.py does not return fabricated performance data.

This test ensures that brain/metrics.py no longer returns hardcoded values
(avg_ms=150, p95_ms=300, p99_ms=500, uptime_percentage=99.5) as if they were
real measurements. Instead, it should mark performance metrics as unavailable
when no real measurement source exists.

See docs/AUTODESARROLLO_CONTINUIDAD_PLAN.md section N1 for context.
"""

import asyncio
import sys
import pytest
from pathlib import Path

# Add tmp_agent to path
sys.path.insert(0, r"C:\AI_VAULT\tmp_agent")

from brain_v9.brain.metrics import MetricsAggregator


def get_performance_result():
    """Helper function to get _performance() result using asyncio.run()."""
    metrics = MetricsAggregator()
    return asyncio.run(metrics._performance())


class TestMetricsNoFabricatedPerformance:
    """Tests to verify N1 mitigation: no fabricated performance metrics."""
    
    @pytest.fixture
    def metrics(self):
        """Fixture to provide MetricsAggregator instance."""
        return MetricsAggregator()
    
    def test_performance_not_return_hardcoded_avg_ms_150(self, metrics):
        """1. _performance() no devuelve avg_ms=150 hardcodeado."""
        result = asyncio.run(metrics._performance())
        assert result["response_times"]["avg_ms"] != 150, \
            "avg_ms should not be hardcoded to 150"
    
    def test_performance_not_return_hardcoded_p95_ms_300(self, metrics):
        """2. _performance() no devuelve p95_ms=300 hardcodeado."""
        result = asyncio.run(metrics._performance())
        assert result["response_times"]["p95_ms"] != 300, \
            "p95_ms should not be hardcoded to 300"
    
    def test_performance_not_return_hardcoded_p99_ms_500(self, metrics):
        """3. _performance() no devuelve p99_ms=500 hardcodeado."""
        result = asyncio.run(metrics._performance())
        assert result["response_times"]["p99_ms"] != 500, \
            "p99_ms should not be hardcoded to 500"
    
    def test_performance_not_return_hardcoded_uptime_99_5(self, metrics):
        """4. _performance() no devuelve uptime_percentage=99.5 hardcodeado."""
        result = asyncio.run(metrics._performance())
        assert result["availability"]["uptime_percentage"] != 99.5, \
            "uptime_percentage should not be hardcoded to 99.5"
    
    def test_performance_returns_unavailable_status(self, metrics):
        """5. Si no hay fuente real, status debe ser 'unavailable' o equivalente."""
        result = asyncio.run(metrics._performance())
        assert result.get("status") == "unavailable", \
            "status should be 'unavailable' when no real measurement source exists"
    
    def test_performance_returns_none_for_unmeasured_values(self, metrics):
        """6. Valores no medidos deben ser None, no números falsos."""
        result = asyncio.run(metrics._performance())
        assert result["response_times"]["avg_ms"] is None, \
            "avg_ms should be None when not measured"
        assert result["response_times"]["p95_ms"] is None, \
            "p95_ms should be None when not measured"
        assert result["response_times"]["p99_ms"] is None, \
            "p99_ms should be None when not measured"
        assert result["availability"]["uptime_percentage"] is None, \
            "uptime_percentage should be None when not measured"
    
    def test_performance_has_reason_or_generated_from(self, metrics):
        """7. Debe existir reason o generated_from que indique no_real_performance_source / not_measured."""
        result = asyncio.run(metrics._performance())
        assert "reason" in result, \
            "result should contain 'reason' field explaining why metrics are unavailable"
        assert result["reason"] == "no_real_performance_source", \
            "reason should indicate no real performance source"
        assert "generated_from" in result, \
            "result should contain 'generated_from' field"
        assert result["generated_from"] == "not_measured", \
            "generated_from should indicate metrics were not measured"
    
    def test_performance_has_note_about_n1(self, metrics):
        """8. Debe incluir nota referenciando N1 y documentación."""
        result = asyncio.run(metrics._performance())
        assert "note" in result, \
            "result should contain 'note' field"
        assert "N1" in result["note"], \
            "note should reference N1"
        assert "AUTODESARROLLO_CONTINUIDAD_PLAN" in result["note"], \
            "note should reference documentation"
    
    def test_performance_maintains_backward_compatible_structure(self, metrics):
        """9. response_times y availability deben seguir existiendo para backward compatibility."""
        result = asyncio.run(metrics._performance())
        assert "response_times" in result, \
            "response_times key must exist for backward compatibility"
        assert "availability" in result, \
            "availability key must exist for backward compatibility"
        assert "avg_ms" in result["response_times"], \
            "avg_ms key must exist in response_times"
        assert "p95_ms" in result["response_times"], \
            "p95_ms key must exist in response_times"
        assert "p99_ms" in result["response_times"], \
            "p99_ms key must exist in response_times"
        assert "uptime_percentage" in result["availability"], \
            "uptime_percentage key must exist in availability"
    
    def test_no_fake_numbers_in_response(self, metrics):
        """10. No debe afirmar que hay performance real si no hay medición real."""
        result = asyncio.run(metrics._performance())
        # Ensure no numeric values that could be mistaken for real measurements
        for field in ["avg_ms", "p95_ms", "p99_ms"]:
            value = result["response_times"].get(field)
            if value is not None:
                assert not isinstance(value, (int, float)) or value != 150, \
                    f"{field} should not contain fabricated numeric value 150"
                assert not isinstance(value, (int, float)) or value != 300, \
                    f"{field} should not contain fabricated numeric value 300"
                assert not isinstance(value, (int, float)) or value != 500, \
                    f"{field} should not contain fabricated numeric value 500"
        
        uptime = result["availability"].get("uptime_percentage")
        if uptime is not None:
            assert not isinstance(uptime, (int, float)) or uptime != 99.5, \
                "uptime_percentage should not contain fabricated value 99.5"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
