"""
BOR-4B Agent Non-Blocking Timeout Tests

Validar que _route_to_agent tiene timeout interno y fallback BOR-2.
No requiere runtime: usa parsing estático.
"""

import ast
from pathlib import Path
import pytest

SESSION_PY = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"


def _parse_session_ast():
    assert SESSION_PY.exists(), f"session.py no encontrado en {SESSION_PY}"
    return SESSION_PY.read_text(encoding="utf-8", errors="replace")


def _find_function_source(name: str) -> str:
    src = _parse_session_ast()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = src.splitlines()
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 500)
            return "\n".join(lines[start:end])
    return ""


class TestAgentNonBlocking:
    """Verificar timeout interno en _route_to_agent."""

    def test_route_to_agent_has_wait_for(self):
        """_route_to_agent debe usar asyncio.wait_for con timeout."""
        body = _find_function_source("_route_to_agent")
        assert "asyncio.wait_for" in body, "asyncio.wait_for no encontrado"
        # Verificar que el timeout es menor a 300 segundos (no es el valor anterior)
        assert not "timeout=600" in body, "Timeout antiguo 600s encontrado"
        assert not "timeout=300" in body, "Timeout antiguo 300s encontrado"
        assert "timeout=45" in body or "timeout=35" in body, "Timeout BOR-4B (45s o 35s) no encontrado"
    
    def test_route_to_agent_catches_timeout_error(self):
        """Debe capturar asyncio.TimeoutError."""
        body = _find_function_source("_route_to_agent")
        assert "except asyncio.TimeoutError" in body, "No captura asyncio.TimeoutError"

    def test_timeout_agent_result_shape(self):
        """En timeout agent_result debe tener status=timeout."""
        body = _find_function_source("_route_to_agent")
        assert '"status"' in body and '"timeout"' in body, "No se detecta status=timeout"

    def test_bor2_fallback_exists(self):
        """BOR-2 fallback debe existir y activarse en failure."""
        body = _find_function_source("_route_to_agent")
        assert "_is_agent_execution_failure" in body, "No existe _is_agent_execution_failure"
        assert "agent_fallback" in body.lower() or "bor-2" in body.lower() or "bor2" in body.lower(), "No hay fallback BOR-2"

    def test_agent_failure_notice_exists(self):
        """Existencia de _agent_failure_notice."""
        body = _find_function_source("_agent_failure_notice")
        assert len(body) > 0, "No existe _agent_failure_notice"
        assert "No pude ejecutar herramientas reales" in body, "Mensaje fallback inesperado"

    def test_render_agent_failure_reply_exists(self):
        """Existencia de _render_agent_failure_reply."""
        body = _find_function_source("_render_agent_failure_reply")
        assert len(body) > 0, "No existe _render_agent_failure_reply"

    def test_all_timeout_statuses_covered(self):
        """Los estados de timeout deben estar cubiertos."""
        body = _find_function_source("_route_to_agent")
        for status in ("ghost_completion", "max_steps_reached", "retry_exhausted", "timeout"):
            assert status in body, f"{status} no cubierto en _route_to_agent"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
