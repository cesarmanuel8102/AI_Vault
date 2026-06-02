"""B7-STRANGLER-11 import compatibility tests.

Verifies that:
- The new module is importable and exports the expected API.
- BrainSession retains all three symbols with correct descriptor types.
- Shim output matches standalone output for representative inputs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import pytest

from brain_v9.core import session_agent_render as ar
from brain_v9.core.session import BrainSession


@pytest.mark.unit
class TestAgentRenderImportCompat:
    """Import-compatibility assertions for B7-STRANGLER-11."""

    # ------------------------------------------------------------------
    # 1. Module surface
    # ------------------------------------------------------------------
    def test_module_exports_all_symbols(self):
        assert hasattr(ar, "render_agent_failure_reply")
        assert hasattr(ar, "summarize_action_output")
        assert hasattr(ar, "render_operational_agent_summary")

    def test_module_all_is_exact(self):
        assert set(ar.__all__) == {
            "render_agent_failure_reply",
            "summarize_action_output",
            "render_operational_agent_summary",
        }

    # ------------------------------------------------------------------
    # 2. BrainSession surface preserved
    # ------------------------------------------------------------------
    def test_brain_session_has_render_agent_failure_reply(self):
        assert hasattr(BrainSession, "_render_agent_failure_reply")

    def test_brain_session_has_summarize_action_output(self):
        assert hasattr(BrainSession, "_summarize_action_output")

    def test_brain_session_has_render_operational_agent_summary(self):
        assert hasattr(BrainSession, "_render_operational_agent_summary")

    # ------------------------------------------------------------------
    # 3. Descriptor types
    # ------------------------------------------------------------------
    def test_render_agent_failure_reply_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_render_agent_failure_reply"], classmethod
        )

    def test_summarize_action_output_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_summarize_action_output"], classmethod
        )

    def test_render_operational_agent_summary_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_render_operational_agent_summary"], classmethod
        )

    # ------------------------------------------------------------------
    # 4. Shim == standalone for representative payloads
    # ------------------------------------------------------------------
    def test_render_agent_failure_reply_shim_parity(self):
        payload = ("ghost_completion", "raw tool output here")
        assert (
            BrainSession._render_agent_failure_reply(*payload)
            == ar.render_agent_failure_reply(
                *payload,
                sanitize_user_visible_response_func=BrainSession._sanitize_user_visible_response,
                contains_raw_tool_markup_func=BrainSession._contains_raw_tool_markup,
                looks_like_canned_failure_func=BrainSession._looks_like_canned_failure,
            )
        )

    def test_summarize_action_output_shim_parity(self):
        action = {"tool": "check_port", "success": True, "output": {"port": 8080}}
        assert (
            BrainSession._summarize_action_output(action)
            == ar.summarize_action_output(
                action,
                format_tool_result_func=BrainSession._format_tool_result,
            )
        )

    def test_render_operational_agent_summary_shim_parity(self):
        message = "hello"
        actions = [{"tool": "check_port", "success": True, "output": {"port": 8080}}]
        kwargs = {"steps": 3, "status": "completed"}
        assert (
            BrainSession._render_operational_agent_summary(message, actions, **kwargs)
            == ar.render_operational_agent_summary(
                message, actions,
                **kwargs,
                summarize_action_output_func=BrainSession._summarize_action_output,
                format_tool_result_func=BrainSession._format_tool_result,
                format_action_value_func=BrainSession._format_action_value,
            )
        )

    # ------------------------------------------------------------------
    # 5. Class-level access works
    # ------------------------------------------------------------------
    def test_class_level_access_for_render_agent_failure_reply(self):
        assert BrainSession._render_agent_failure_reply(
            "ghost_completion"
        ).startswith("No pude completar")

    def test_class_level_access_for_summarize_action_output(self):
        action = {"tool": "check_port", "success": True, "output": {"port": 8080}}
        assert "8080" in BrainSession._summarize_action_output(action)

    def test_class_level_access_for_render_operational_agent_summary(self):
        actions = [{"tool": "check_port", "success": True, "output": {"port": 8080}}]
        result = BrainSession._render_operational_agent_summary(
            "hola", actions, steps=1, status="completed"
        )
        assert "8080" in result or "check_port" in result
