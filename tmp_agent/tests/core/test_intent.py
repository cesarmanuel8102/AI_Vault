"""
Tests for brain_v9.core.intent — IntentDetector (Bilingual EN/ES).

Sprint 3 (P3-05): Verifies that the intent detector works with both
English and Spanish inputs across all intent categories.
"""
import pytest
from brain_v9.core.intent import IntentDetector, INTENT_SYNONYMS


@pytest.fixture
def detector():
    return IntentDetector()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Spanish detection (existing functionality, regression guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpanishIntents:

    def test_query_spanish(self, detector):
        intent, conf, meta = detector.detect("qué es un RSI?")
        assert intent == "QUERY"
        assert conf >= 0.7

    def test_command_spanish(self, detector):
        intent, conf, meta = detector.detect("ejecuta el diagnóstico")
        assert intent == "COMMAND"
        assert conf >= 0.7

    def test_analysis_spanish(self, detector):
        intent, conf, meta = detector.detect("analiza el rendimiento")
        assert intent == "ANALYSIS"
        assert conf >= 0.7

    def test_trading_spanish(self, detector):
        intent, conf, meta = detector.detect("cómo está el mercado de forex")
        assert intent in ("TRADING", "QUERY")
        assert conf >= 0.5

    def test_conversation_spanish(self, detector):
        intent, conf, meta = detector.detect("hola cómo estás")
        # Should match CONVERSATION or QUERY (hola + cómo)
        assert intent in ("CONVERSATION", "QUERY")
        assert conf >= 0.5

    def test_creative_spanish(self, detector):
        intent, conf, meta = detector.detect("escribe un resumen")
        assert intent == "CREATIVE"
        assert conf >= 0.7

    def test_code_spanish(self, detector):
        intent, conf, meta = detector.detect("revisa el código de la función")
        assert intent in ("CODE", "ANALYSIS")
        assert conf >= 0.5

    def test_memory_spanish(self, detector):
        intent, conf, meta = detector.detect("recuerdas lo que mencioné ayer")
        assert intent == "MEMORY"
        assert conf >= 0.7

    def test_system_spanish(self, detector):
        intent, conf, meta = detector.detect("muéstrame el estado del sistema")
        assert intent == "SYSTEM"
        assert conf >= 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: English detection (new P3-05 functionality)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnglishIntents:

    def test_query_english(self, detector):
        intent, conf, meta = detector.detect("what is the current price")
        assert intent in ("QUERY", "TRADING")
        assert conf >= 0.5

    def test_query_english_how(self, detector):
        intent, conf, meta = detector.detect("how does the strategy work")
        assert intent == "QUERY"
        assert conf >= 0.7

    def test_command_english(self, detector):
        intent, conf, meta = detector.detect("restart the dashboard")
        assert intent == "COMMAND"
        assert conf >= 0.7

    def test_command_english_start(self, detector):
        intent, conf, meta = detector.detect("start the brain server")
        assert intent == "COMMAND"
        assert conf >= 0.7

    def test_analysis_english(self, detector):
        intent, conf, meta = detector.detect("analyze the trading performance")
        assert intent == "ANALYSIS"
        assert conf >= 0.7

    def test_analysis_english_check(self, detector):
        intent, conf, meta = detector.detect("check the system status")
        assert intent in ("ANALYSIS", "SYSTEM")
        assert conf >= 0.5

    def test_creative_english(self, detector):
        intent, conf, meta = detector.detect("write a summary report")
        assert intent == "CREATIVE"
        assert conf >= 0.7

    def test_code_english(self, detector):
        intent, conf, meta = detector.detect("debug the function in loop.py")
        assert intent == "CODE"
        assert conf >= 0.5

    def test_code_english_refactor(self, detector):
        intent, conf, meta = detector.detect("refactor the class method")
        assert intent == "CODE"
        assert conf >= 0.5

    def test_memory_english(self, detector):
        intent, conf, meta = detector.detect("do you remember what I mentioned")
        assert intent == "MEMORY"
        assert conf >= 0.5

    def test_system_english(self, detector):
        intent, conf, meta = detector.detect("show me the system status")
        assert intent == "SYSTEM"
        assert conf >= 0.5

    def test_conversation_english_hello(self, detector):
        intent, conf, meta = detector.detect("hello there")
        assert intent == "CONVERSATION"
        assert conf >= 0.7

    def test_conversation_english_thanks(self, detector):
        intent, conf, meta = detector.detect("thanks for the help")
        assert intent == "CONVERSATION"
        assert conf >= 0.7

    def test_trading_english_market(self, detector):
        intent, conf, meta = detector.detect("how is the market doing today")
        assert intent in ("TRADING", "QUERY")
        assert conf >= 0.5

    def test_trading_english_strategy(self, detector):
        intent, conf, meta = detector.detect("show me the strategy performance")
        assert intent == "TRADING"
        assert conf >= 0.5

    def test_trading_english_backtest(self, detector):
        intent, conf, meta = detector.detect("run a backtest on EURUSD")
        assert intent in ("TRADING", "COMMAND")
        assert conf >= 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Metadata and confidence
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetadata:

    def test_returns_three_tuple(self, detector):
        result = detector.detect("hello")
        assert len(result) == 3

    def test_confidence_between_0_and_1(self, detector):
        _, conf, _ = detector.detect("analyze the data")
        assert 0.0 <= conf <= 1.0

    def test_metadata_has_method(self, detector):
        _, _, meta = detector.detect("ejecuta el test")
        assert "method" in meta

    def test_unknown_fallback(self, detector):
        """Gibberish should fall back to something with low confidence."""
        intent, conf, meta = detector.detect("xyzzy plugh foobar")
        # Should still return a valid intent name (even if confidence is low)
        assert isinstance(intent, str)
        assert conf >= 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Entity extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestEntityExtraction:

    def test_urls_extracted(self, detector):
        result = detector.extract_entities("check https://example.com/test")
        assert "https://example.com/test" in result["urls"]

    def test_emails_extracted(self, detector):
        result = detector.extract_entities("send to user@example.com")
        assert "user@example.com" in result["emails"]

    def test_numbers_extracted(self, detector):
        result = detector.extract_entities("port 8070 is running")
        assert "8070" in result["numbers"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: Sentiment analysis (bilingual)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSentiment:

    def test_neutral_message(self, detector):
        result = detector.analyze_sentiment("check the system")
        assert result["sentiment"] == "neutral"

    def test_positive_spanish(self, detector):
        result = detector.analyze_sentiment("excelente trabajo, gracias")
        assert result["sentiment"] == "positive"

    def test_negative_spanish(self, detector):
        result = detector.analyze_sentiment("hay un error, no funciona")
        assert result["sentiment"] == "negative"

    def test_positive_english(self, detector):
        result = detector.analyze_sentiment("great work, that looks awesome")
        assert result["sentiment"] == "positive"

    def test_negative_english(self, detector):
        result = detector.analyze_sentiment("this is broken, terrible crash")
        assert result["sentiment"] == "negative"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: INTENT_SYNONYMS structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntentSynonymsStructure:

    def test_all_intents_have_keywords(self):
        for name, data in INTENT_SYNONYMS.items():
            assert "keywords" in data, f"{name} missing keywords"
            assert len(data["keywords"]) > 0, f"{name} has empty keywords"

    def test_all_intents_have_patterns(self):
        for name, data in INTENT_SYNONYMS.items():
            assert "patterns" in data, f"{name} missing patterns"
            assert len(data["patterns"]) > 0, f"{name} has empty patterns"

    def test_trading_has_english_keywords(self):
        kws = INTENT_SYNONYMS["TRADING"]["keywords"]
        assert "market" in kws
        assert "strategy" in kws
        assert "broker" in kws

    def test_all_intents_have_english_keywords(self):
        """Every intent category must have at least one English keyword."""
        english_indicators = {
            "QUERY": "what",
            "COMMAND": "execute",
            "ANALYSIS": "analyze",
            "CREATIVE": "write",
            "CODE": "code",
            "MEMORY": "remember",
            "SYSTEM": "status",
            "CONVERSATION": "hello",
            "TRADING": "market",
        }
        for intent_name, english_kw in english_indicators.items():
            kws = INTENT_SYNONYMS[intent_name]["keywords"]
            assert english_kw in kws, f"{intent_name} missing English keyword '{english_kw}'"
