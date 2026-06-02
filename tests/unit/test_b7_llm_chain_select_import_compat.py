"""B7-STRANGLER-10 import compatibility tests.

Verifies that:
- The new module is importable and exports the expected API.
- BrainSession retains all five symbols with correct descriptor types.
- Shim output matches standalone output for representative inputs.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import pytest

from brain_v9.core import session_llm_chain_select as lcs
from brain_v9.core.session import BrainSession


@pytest.mark.unit
class TestLlmChainSelectImportCompat:
    """Import-compatibility assertions for B7-STRANGLER-10."""

    # ------------------------------------------------------------------
    # 1. Module surface
    # ------------------------------------------------------------------
    def test_module_exports_all_symbols(self):
        assert hasattr(lcs, "MODEL_PRIORITY_ALIASES")
        assert hasattr(lcs, "normalize_model_priority")
        assert hasattr(lcs, "should_use_compact_chat_prompt")
        assert hasattr(lcs, "should_use_analysis_frontier")
        assert hasattr(lcs, "select_llm_chain")

    def test_module_all_is_exact(self):
        assert set(lcs.__all__) == {
            "MODEL_PRIORITY_ALIASES",
            "normalize_model_priority",
            "should_use_compact_chat_prompt",
            "should_use_analysis_frontier",
            "select_llm_chain",
        }

    # ------------------------------------------------------------------
    # 2. BrainSession surface preserved
    # ------------------------------------------------------------------
    def test_brain_session_has_model_priority_aliases(self):
        assert hasattr(BrainSession, "_MODEL_PRIORITY_ALIASES")
        assert isinstance(BrainSession._MODEL_PRIORITY_ALIASES, dict)

    def test_brain_session_has_normalize_model_priority(self):
        assert hasattr(BrainSession, "_normalize_model_priority")

    def test_brain_session_has_should_use_compact_chat_prompt(self):
        assert hasattr(BrainSession, "_should_use_compact_chat_prompt")

    def test_brain_session_has_should_use_analysis_frontier(self):
        assert hasattr(BrainSession, "_should_use_analysis_frontier")

    def test_brain_session_has_select_llm_chain(self):
        assert hasattr(BrainSession, "_select_llm_chain")

    # ------------------------------------------------------------------
    # 3. Descriptor types
    # ------------------------------------------------------------------
    def test_normalize_model_priority_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_normalize_model_priority"], classmethod
        )

    def test_should_use_compact_chat_prompt_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_should_use_compact_chat_prompt"], classmethod
        )

    def test_should_use_analysis_frontier_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_should_use_analysis_frontier"], classmethod
        )

    def test_select_llm_chain_is_classmethod(self):
        assert isinstance(
            BrainSession.__dict__["_select_llm_chain"], classmethod
        )

    # ------------------------------------------------------------------
    # 4. Shim == standalone for representative payloads
    # ------------------------------------------------------------------
    def test_normalize_model_priority_shim_parity(self):
        for raw, expected in [
            ("codex", "codex"),
            ("openai", "codex"),
            ("frontier_legacy", "agent_frontier_legacy"),
            ("chat", "chat"),
            ("unknown-model", "unknown-model"),
        ]:
            assert BrainSession._normalize_model_priority(raw) == expected
            assert lcs.normalize_model_priority(raw, aliases=BrainSession._MODEL_PRIORITY_ALIASES) == expected

    def test_should_use_compact_chat_prompt_shim_parity(self):
        payload = ("responde solo hola en una frase", "QUERY", [], "llama8b")
        assert (
            BrainSession._should_use_compact_chat_prompt(*payload)
            == lcs.should_use_compact_chat_prompt(*payload)
        )

    def test_should_use_analysis_frontier_shim_parity(self):
        payload = (
            "que significa esa respuesta y por que codex no esta activo?",
            "CREATIVE",
            [],
            "chat",
        )
        assert (
            BrainSession._should_use_analysis_frontier(*payload)
            == lcs.should_use_analysis_frontier(*payload)
        )

    def test_select_llm_chain_shim_parity(self):
        payload = (
            "que significa esa respuesta y por que codex no esta activo?",
            "CREATIVE",
            [],
            "chat",
        )
        assert (
            BrainSession._select_llm_chain(*payload)
            == lcs.select_llm_chain(*payload)
        )

    # ------------------------------------------------------------------
    # 5. Class-level access works
    # ------------------------------------------------------------------
    def test_class_level_access_for_compact_chat(self):
        assert BrainSession._should_use_compact_chat_prompt(
            "hola", "CONVERSATION", [], "chat"
        ) is True

    def test_class_level_access_for_analysis_frontier(self):
        assert BrainSession._should_use_analysis_frontier(
            "explica por que codex no esta activo", "ANALYSIS", [], "chat"
        ) is True

    def test_class_level_access_for_select_llm_chain(self):
        assert BrainSession._select_llm_chain(
            "hola", "CONVERSATION", [], "chat"
        ) == "chat"

    def test_class_level_access_for_normalize_model_priority(self):
        assert BrainSession._normalize_model_priority("codex") == "codex"
