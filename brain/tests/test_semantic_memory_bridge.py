"""
Tests for SemanticMemoryBridge — brain/semantic_memory_bridge.py
12 tests covering enrich_prompt(), auto_ingest_if_relevant(), manual_ingest(),
search(), get_stats(), and with/without semantic_memory.
"""

import pytest
from unittest.mock import Mock, MagicMock

from brain.semantic_memory_bridge import (
    SemanticMemoryBridge,
    MemoryContext,
    get_semantic_memory_bridge,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def bridge():
    return SemanticMemoryBridge()


@pytest.fixture
def bridge_with_memory():
    memory = Mock()
    memory.search.return_value = [
        {"text": "RSI indicator overbought at 70", "score": 0.9, "source": "trading_doc"},
        {"text": "MACD crossover is bullish signal", "score": 0.8, "source": "analysis"},
    ]
    memory.ingest = Mock()
    memory.add_document = Mock()
    memory.status.return_value = {"total_documents": 42, "index_size": 1024}
    return SemanticMemoryBridge(semantic_memory=memory)


# ─── enrich_prompt() ─────────────────────────────────────────────────────────

class TestEnrichPrompt:
    def test_enrich_prompt_with_memories(self, bridge_with_memory):
        result = bridge_with_memory.enrich_prompt(
            "What is RSI?", "You are a helpful assistant."
        )
        assert "CONTEXTO DE MEMORIA" in result
        assert "RSI" in result

    def test_enrich_prompt_without_memories(self, bridge):
        result = bridge.enrich_prompt(
            "What is RSI?", "You are a helpful assistant."
        )
        assert result == "You are a helpful assistant."

    def test_enrich_prompt_preserves_base(self, bridge_with_memory):
        base = "Base system prompt content"
        result = bridge_with_memory.enrich_prompt("query", base)
        assert base in result


# ─── auto_ingest_if_relevant() ──────────────────────────────────────────────

class TestAutoIngestIfRelevant:
    def test_auto_ingest_correction_spanish(self, bridge_with_memory):
        result = bridge_with_memory.auto_ingest_if_relevant(
            "Corrección: el RSI está en 70, no 80",
            "El RSI está en 80",
        )
        assert result is True
        bridge_with_memory._semantic_memory.ingest.assert_called()

    def test_auto_ingest_correction_english(self, bridge_with_memory):
        result = bridge_with_memory.auto_ingest_if_relevant(
            "That's wrong, the value is 42",
            "The value is 24",
        )
        assert result is True

    def test_auto_ingest_decision(self, bridge_with_memory):
        result = bridge_with_memory.auto_ingest_if_relevant(
            "Decidimos usar la estrategia A",
            "Ok, estrategia A activada",
        )
        assert result is True

    def test_auto_ingest_factual_claim(self, bridge_with_memory):
        result = bridge_with_memory.auto_ingest_if_relevant(
            "¿Cuál es el valor?",
            "El valor es 42 en este contexto",
        )
        assert result is True

    def test_auto_ingest_not_relevant(self, bridge_with_memory):
        result = bridge_with_memory.auto_ingest_if_relevant(
            "Hola, ¿cómo estás?",
            "Bien, gracias por preguntar",
        )
        assert result is False

    def test_auto_ingest_no_memory(self, bridge):
        result = bridge.auto_ingest_if_relevant(
            "Corrección: el valor es 42",
            "El valor es 24",
        )
        assert result is False


# ─── manual_ingest() ─────────────────────────────────────────────────────────

class TestManualIngest:
    def test_manual_ingest_with_memory(self, bridge_with_memory):
        result = bridge_with_memory.manual_ingest("Important fact", source="test")
        assert result is True

    def test_manual_ingest_without_memory(self, bridge):
        result = bridge.manual_ingest("Important fact", source="test")
        assert result is False


# ─── search() ────────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_with_memory(self, bridge_with_memory):
        results = bridge_with_memory.search("RSI")
        assert len(results) > 0

    def test_search_without_memory(self, bridge):
        results = bridge.search("RSI")
        assert results == []

    def test_search_error_handling(self, bridge_with_memory):
        bridge_with_memory._semantic_memory.search.side_effect = Exception("search failed")
        results = bridge_with_memory.search("RSI")
        assert results == []


# ─── get_stats() ─────────────────────────────────────────────────────────────

class TestGetStats:
    def test_stats_with_memory(self, bridge_with_memory):
        stats = bridge_with_memory.get_stats()
        assert stats["memory_available"] is True
        assert stats["ingest_count"] >= 0
        assert "memory_status" in stats

    def test_stats_without_memory(self, bridge):
        stats = bridge.get_stats()
        assert stats["memory_available"] is False
        assert stats["ingest_count"] == 0

    def test_stats_includes_search_count(self, bridge_with_memory):
        bridge_with_memory.search("test query")
        stats = bridge_with_memory.get_stats()
        assert stats["search_count"] >= 1


# ─── get_semantic_memory_bridge() singleton ─────────────────────────────────

class TestGetSemanticMemoryBridge:
    def test_returns_instance(self):
        import brain.semantic_memory_bridge as mod
        mod._bridge = None
        b = get_semantic_memory_bridge()
        assert isinstance(b, SemanticMemoryBridge)
