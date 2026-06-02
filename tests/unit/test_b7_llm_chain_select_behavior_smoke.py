"""B7-STRANGLER-10 behavior smoke tests.

Verifies functional parity for extracted LLM chain selection helpers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import pytest

from brain_v9.core import session_llm_chain_select as lcs
from brain_v9.core.session import BrainSession


@pytest.mark.unit
class TestNormalizeModelPriority:
    def test_known_aliases(self):
        for raw, expected in BrainSession._MODEL_PRIORITY_ALIASES.items():
            assert lcs.normalize_model_priority(raw) == expected
            assert BrainSession._normalize_model_priority(raw) == expected

    def test_unknown_passthrough(self):
        assert lcs.normalize_model_priority("custom-model") == "custom-model"
        assert BrainSession._normalize_model_priority("custom-model") == "custom-model"

    def test_none_defaults_to_chat(self):
        assert lcs.normalize_model_priority(None) == "chat"
        assert BrainSession._normalize_model_priority(None) == "chat"

    def test_empty_defaults_to_chat(self):
        assert lcs.normalize_model_priority("") == "chat"
        assert BrainSession._normalize_model_priority("") == "chat"

    def test_whitespace_stripped(self):
        assert lcs.normalize_model_priority("  codex  ") == "codex"
        assert BrainSession._normalize_model_priority("  codex  ") == "codex"


@pytest.mark.unit
class TestShouldUseCompactChatPrompt:
    def test_short_general_query_true(self):
        payload = ("responde solo hola en una frase", "QUERY", [], "llama8b")
        assert lcs.should_use_compact_chat_prompt(*payload) is True
        assert BrainSession._should_use_compact_chat_prompt(*payload) is True

    def test_path_mention_false(self):
        payload = ("revisa C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\llm.py", "QUERY", [], "llama8b")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False

    def test_operational_agent_query_false(self):
        payload = ("ejecuta script de diagnostico", "QUERY", [], "chat")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False

    def test_llm_status_query_false(self):
        payload = ("estado de los modelos llm", "QUERY", [], "chat")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False

    def test_intent_code_false(self):
        payload = ("como funciona esto", "CODE", [], "chat")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False

    def test_large_history_false(self):
        history = [{"role": "user"}, {"role": "assistant"}, {"role": "user"}, {"role": "assistant"}]
        payload = ("hola", "QUERY", history, "chat")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False

    def test_non_chat_priority_false(self):
        payload = ("hola", "QUERY", [], "code")
        assert lcs.should_use_compact_chat_prompt(*payload) is False
        assert BrainSession._should_use_compact_chat_prompt(*payload) is False


@pytest.mark.unit
class TestShouldUseAnalysisFrontier:
    def test_non_operational_analysis_true(self):
        payload = (
            "que significa esa respuesta y por que codex no esta activo?",
            "CREATIVE",
            [],
            "chat",
        )
        assert lcs.should_use_analysis_frontier(*payload) is True
        assert BrainSession._should_use_analysis_frontier(*payload) is True

    def test_operational_analysis_false(self):
        payload = (
            "revisa el estado de todos los servicios y ejecuta diagnostico",
            "ANALYSIS",
            [],
            "chat",
        )
        assert lcs.should_use_analysis_frontier(*payload) is False
        assert BrainSession._should_use_analysis_frontier(*payload) is False

    def test_benign_security_audit_true(self):
        payload = ("auditoria benigna del brain", "ANALYSIS", [], "chat")
        assert lcs.should_use_analysis_frontier(*payload) is True
        assert BrainSession._should_use_analysis_frontier(*payload) is True

    def test_brain_diagnostic_true(self):
        payload = ("diagnostica el estado del brain", "ANALYSIS", [], "chat")
        assert lcs.should_use_analysis_frontier(*payload) is True
        assert BrainSession._should_use_analysis_frontier(*payload) is True

    def test_grounded_code_analysis_false(self):
        payload = ("analiza el archivo main.py", "ANALYSIS", [], "chat")
        assert lcs.should_use_analysis_frontier(*payload) is False
        assert BrainSession._should_use_analysis_frontier(*payload) is False

    def test_llm_status_false(self):
        payload = ("como esta el llm", "QUERY", [], "chat")
        assert lcs.should_use_analysis_frontier(*payload) is False
        assert BrainSession._should_use_analysis_frontier(*payload) is False

    def test_recent_activity_false(self):
        payload = ("que hiciste recientemente", "QUERY", [], "chat")
        assert lcs.should_use_analysis_frontier(*payload) is False
        assert BrainSession._should_use_analysis_frontier(*payload) is False

    def test_explicit_analysis_frontier_priority_true(self):
        payload = ("hola", "QUERY", [], "analysis_frontier")
        assert lcs.should_use_analysis_frontier(*payload) is True
        assert BrainSession._should_use_analysis_frontier(*payload) is True

    def test_codex_priority_false(self):
        payload = ("explica codex", "ANALYSIS", [], "codex")
        assert lcs.should_use_analysis_frontier(*payload) is False
        assert BrainSession._should_use_analysis_frontier(*payload) is False


@pytest.mark.unit
class TestSelectLlmChain:
    def test_code_intent_returns_code(self):
        payload = ("hola", "CODE", [], "chat")
        assert lcs.select_llm_chain(*payload) == "code"
        assert BrainSession._select_llm_chain(*payload) == "code"

    def test_analysis_frontier_returns_analysis_frontier(self):
        payload = (
            "que significa esa respuesta y por que codex no esta activo?",
            "CREATIVE",
            [],
            "chat",
        )
        assert lcs.select_llm_chain(*payload) == "analysis_frontier"
        assert BrainSession._select_llm_chain(*payload) == "analysis_frontier"

    def test_normal_chat_returns_chat(self):
        payload = ("hola", "CONVERSATION", [], "chat")
        assert lcs.select_llm_chain(*payload) == "chat"
        assert BrainSession._select_llm_chain(*payload) == "chat"

    def test_legacy_frontier_returns_legacy(self):
        payload = ("hola", "QUERY", [], "analysis_frontier_legacy")
        assert lcs.select_llm_chain(*payload) == "analysis_frontier_legacy"
        assert BrainSession._select_llm_chain(*payload) == "analysis_frontier_legacy"

    def test_codex_priority_returns_codex(self):
        payload = ("hola", "QUERY", [], "codex")
        assert lcs.select_llm_chain(*payload) == "codex"
        assert BrainSession._select_llm_chain(*payload) == "codex"

    def test_passthrough_unknown(self):
        payload = ("hola", "QUERY", [], "custom-model")
        assert lcs.select_llm_chain(*payload) == "custom-model"
        assert BrainSession._select_llm_chain(*payload) == "custom-model"
