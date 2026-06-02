"""B7-STRANGLER-11 behavior smoke tests.

Verifies functional parity for extracted agent rendering helpers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import pytest

from brain_v9.core import session_agent_render as ar
from brain_v9.core.session import BrainSession


@pytest.mark.unit
class TestRenderAgentFailureReply:
    def _inject(self):
        return dict(
            sanitize_user_visible_response_func=BrainSession._sanitize_user_visible_response,
            contains_raw_tool_markup_func=BrainSession._contains_raw_tool_markup,
            looks_like_canned_failure_func=BrainSession._looks_like_canned_failure,
        )

    def test_ghost_completion(self):
        assert "no llego a ejecutar" in ar.render_agent_failure_reply("ghost_completion", **self._inject())
        assert "no llego a ejecutar" in BrainSession._render_agent_failure_reply("ghost_completion")

    def test_max_steps_reached(self):
        assert "agoto pasos" in ar.render_agent_failure_reply("max_steps_reached", **self._inject())
        assert "agoto pasos" in BrainSession._render_agent_failure_reply("max_steps_reached")

    def test_timeout(self):
        assert "expiro por tiempo" in ar.render_agent_failure_reply("timeout", **self._inject())
        assert "expiro por tiempo" in BrainSession._render_agent_failure_reply("timeout")

    def test_raw_text_clean(self):
        raw = "Hola, esto es una respuesta limpia."
        result = ar.render_agent_failure_reply("ghost_completion", raw, **self._inject())
        assert raw in result
        assert BrainSession._render_agent_failure_reply("ghost_completion", raw) == result

    def test_raw_text_empty(self):
        result = ar.render_agent_failure_reply("ghost_completion", "", **self._inject())
        assert "Reformula" in result
        assert BrainSession._render_agent_failure_reply("ghost_completion", "") == result

    def test_raw_text_with_tool_markup(self):
        raw = '<invoke name="check_port">'
        result = ar.render_agent_failure_reply("ghost_completion", raw, **self._inject())
        assert "Reformula" in result
        assert BrainSession._render_agent_failure_reply("ghost_completion", raw) == result

    def test_canned_failure(self):
        raw = "no obtuve resultados para esta consulta"
        result = ar.render_agent_failure_reply("ghost_completion", raw, **self._inject())
        assert "Reformula" in result
        assert BrainSession._render_agent_failure_reply("ghost_completion", raw) == result


@pytest.mark.unit
class TestSummarizeActionOutput:
    def _inject(self):
        return dict(format_tool_result_func=BrainSession._format_tool_result)

    def test_ok_action(self):
        action = {"tool": "check_port", "success": True, "output": {"port": 8080}}
        result = ar.summarize_action_output(action, **self._inject())
        assert BrainSession._summarize_action_output(action) == result
        assert "8080" in result or "check_port" in result

    def test_error_action(self):
        action = {"tool": "read_file", "success": False, "error": "File not found"}
        result = ar.summarize_action_output(action, **self._inject())
        assert BrainSession._summarize_action_output(action) == result
        assert "error" in result.lower() or "File not found" in result


@pytest.mark.unit
class TestRenderOperationalAgentSummary:
    def _inject(self):
        return dict(
            summarize_action_output_func=BrainSession._summarize_action_output,
            format_tool_result_func=BrainSession._format_tool_result,
            format_action_value_func=BrainSession._format_action_value,
        )

    def test_no_actions(self):
        actions = []
        kwargs = dict(steps=0, status="completed", **self._inject())
        result = ar.render_operational_agent_summary("hola", actions, **kwargs)
        assert BrainSession._render_operational_agent_summary("hola", actions, steps=0, status="completed") == result
        assert "No se ejecutaron herramientas" in result

    def test_single_ok_action(self):
        actions = [{"tool": "check_port", "success": True, "output": {"port": 8080}}]
        kwargs = dict(steps=1, status="completed", **self._inject())
        result = ar.render_operational_agent_summary("hola", actions, **kwargs)
        assert BrainSession._render_operational_agent_summary("hola", actions, steps=1, status="completed") == result
        assert "check_port" in result
        assert "1 ok" in result

    def test_single_failed_action(self):
        actions = [{"tool": "read_file", "success": False, "error": "File not found"}]
        kwargs = dict(steps=1, status="completed", **self._inject())
        result = ar.render_operational_agent_summary("hola", actions, **kwargs)
        assert BrainSession._render_operational_agent_summary("hola", actions, steps=1, status="completed") == result
        assert "Fallos" in result

    def test_timeout_status(self):
        actions = [{"tool": "check_port", "success": True, "output": {"port": 8080}}]
        kwargs = dict(steps=1, status="timeout", **self._inject())
        result = ar.render_operational_agent_summary("hola", actions, **kwargs)
        assert BrainSession._render_operational_agent_summary("hola", actions, steps=1, status="timeout") == result
        assert "timeout" in result

    def test_many_tools_capped_at_6(self):
        actions = [{"tool": f"tool_{i}", "success": True, "output": {"i": i}} for i in range(10)]
        kwargs = dict(steps=10, status="completed", **self._inject())
        result = ar.render_operational_agent_summary("hola", actions, **kwargs)
        assert BrainSession._render_operational_agent_summary("hola", actions, steps=10, status="completed") == result
        assert "herramientas adicionales" in result
