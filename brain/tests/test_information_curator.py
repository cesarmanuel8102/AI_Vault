"""
Tests for InformationCurator — brain/information_curator.py
23 tests covering ingest_text pipeline, _clean_text, _compute_hash and
deduplication, _classify_topic, _evaluate_quality, _detect_contradictions,
ingest_file, search, deprecate_old, get_stats, and get_contradictions.
"""

import pytest
import os
import time
import tempfile

from brain.information_curator import (
    InformationCurator,
    ContentTopic,
    QualityLevel,
    CuratedRecord,
    NEGATION_PAIRS,
    get_information_curator,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def curator():
    return InformationCurator()


# ─── _clean_text() ───────────────────────────────────────────────────────────

class TestCleanText:
    def test_removes_html_tags(self, curator):
        result = curator._clean_text("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert "Hello world" in result

    def test_normalizes_whitespace(self, curator):
        result = curator._clean_text("Hello   world\n\nfoo")
        assert "  " not in result

    def test_removes_control_chars(self, curator):
        result = curator._clean_text("Hello\x00world\x1f")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_strips_whitespace(self, curator):
        result = curator._clean_text("  hello  ")
        assert result == "hello"


# ─── _compute_hash() and deduplication ───────────────────────────────────────

class TestHashAndDedup:
    def test_hash_deterministic(self, curator):
        h1 = curator._compute_hash("test content")
        h2 = curator._compute_hash("test content")
        assert h1 == h2

    def test_hash_differs_for_different_content(self, curator):
        h1 = curator._compute_hash("content A")
        h2 = curator._compute_hash("content B")
        assert h1 != h2

    def test_hash_case_insensitive(self, curator):
        h1 = curator._compute_hash("Hello World")
        h2 = curator._compute_hash("hello world")
        assert h1 == h2

    def test_deduplication_returns_existing(self, curator):
        r1 = curator.ingest_text("This is unique content for dedup testing", source="test")
        r2 = curator.ingest_text("This is unique content for dedup testing", source="test")
        assert r1.record_id == r2.record_id

    def test_different_content_not_deduplicated(self, curator):
        r1 = curator.ingest_text("First unique content for testing", source="test")
        r2 = curator.ingest_text("Second unique content for testing", source="test")
        assert r1.record_id != r2.record_id


# ─── _classify_topic() ───────────────────────────────────────────────────────

class TestClassifyTopic:
    def test_finance_topic(self, curator):
        result = curator._classify_topic("La inversión financiera tiene riesgo")
        assert result == ContentTopic.FINANCE

    def test_trading_topic(self, curator):
        result = curator._classify_topic("Trading strategy with backtest results")
        assert result == ContentTopic.TRADING

    def test_technology_topic(self, curator):
        result = curator._classify_topic("El servidor API necesita deploy")
        assert result == ContentTopic.TECHNOLOGY

    def test_ai_ml_topic(self, curator):
        result = curator._classify_topic("Machine learning model training with GPT")
        assert result == ContentTopic.AI_ML

    def test_risk_management_topic(self, curator):
        result = curator._classify_topic("Risk management with stop loss and volatility")
        assert result == ContentTopic.RISK_MANAGEMENT

    def test_architecture_topic(self, curator):
        result = curator._classify_topic("Microservice architecture with modular components")
        assert result == ContentTopic.ARCHITECTURE

    def test_general_topic_fallback(self, curator):
        result = curator._classify_topic("This is about random things")
        assert result == ContentTopic.GENERAL

    def test_explicit_topic_override(self, curator):
        record = curator.ingest_text(
            "Some general text content here",
            source="test",
            topic=ContentTopic.TRADING,
        )
        assert record.topic == ContentTopic.TRADING


# ─── _evaluate_quality() ─────────────────────────────────────────────────────

class TestEvaluateQuality:
    def test_high_quality(self, curator):
        text = (
            "This is a detailed analysis because the data shows clear trends. "
            "1. First point about the market dynamics and risk factors. "
            "2. Second point regarding portfolio allocation strategies. "
            "3. Third observation about volatility patterns in emerging markets. "
            "The conclusion supports a diversified approach because evidence suggests stability. "
            "Additional context about performance metrics and historical returns data. "
            "Further analysis of sector rotation and macroeconomic indicators that drive decisions."
        )
        score = curator._evaluate_quality(text, "official_docs")
        assert score >= 0.7

    def test_low_quality_short(self, curator):
        score = curator._evaluate_quality("Short", "manual")
        assert score < 0.5

    def test_medium_quality(self, curator):
        text = "Some medium length content about something specific."
        score = curator._evaluate_quality(text, "manual")
        assert 0.4 <= score <= 0.8

    def test_trusted_source_bonus(self, curator):
        text = "Reasonable content about research because evidence"
        score1 = curator._evaluate_quality(text, "random")
        score2 = curator._evaluate_quality(text, "research_paper")
        assert score2 >= score1

    def test_repetition_penalty(self, curator):
        text = "word " * 100
        score = curator._evaluate_quality(text, "manual")
        assert score < 0.7


# ─── _detect_contradictions() ────────────────────────────────────────────────

class TestDetectContradictions:
    def test_no_contradictions_empty(self, curator):
        result = curator._detect_contradictions("No conflicts here", ContentTopic.GENERAL)
        assert result == []

    def test_contradiction_detected(self, curator):
        # Ingest first record
        curator.ingest_text("El sistema debe estar activo siempre", source="test",
                            topic=ContentTopic.TECHNOLOGY)
        # Ingest contradicting record
        record = curator.ingest_text("El sistema no debe estar activo siempre", source="test2",
                                      topic=ContentTopic.TECHNOLOGY)
        assert len(record.metadata.get("contradictions_with", [])) > 0

    def test_no_contradiction_different_topic(self, curator):
        curator.ingest_text("El sistema debe estar activo", source="test",
                            topic=ContentTopic.TECHNOLOGY)
        record = curator.ingest_text("El sistema no debe estar activo", source="test2",
                                      topic=ContentTopic.FINANCE)
        # Different topics should not flag contradictions
        assert len(record.metadata.get("contradictions_with", [])) == 0

    def test_negation_pairs_count(self):
        assert len(NEGATION_PAIRS) == 12


# ─── ingest_text() pipeline ──────────────────────────────────────────────────

class TestIngestText:
    def test_full_pipeline(self, curator):
        record = curator.ingest_text(
            "Machine learning model training requires careful data preparation because "
            "the quality of input data determines model performance.",
            source="research_paper",
        )
        assert record.record_id.startswith("rec_")
        assert record.content != ""
        assert record.quality_score > 0
        assert record.source == "research_paper"

    def test_too_short_returns_error(self, curator):
        record = curator.ingest_text("Short", source="test")
        assert record.record_id.startswith("err_")
        assert record.quality == QualityLevel.UNRELIABLE

    def test_empty_returns_error(self, curator):
        record = curator.ingest_text("", source="test")
        assert record.record_id.startswith("err_")

    def test_whitespace_only_returns_error(self, curator):
        record = curator.ingest_text("   \t\n  ", source="test")
        assert record.record_id.startswith("err_")


# ─── ingest_file() ───────────────────────────────────────────────────────────

class TestIngestFile:
    def test_ingest_file_success(self, curator):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Machine learning model training requires data because quality matters. " * 5)
            f.flush()
            path = f.name
        try:
            records = curator.ingest_file(path)
            assert len(records) > 0
            assert records[0].source.startswith("file:")
        finally:
            os.unlink(path)

    def test_ingest_file_not_found(self, curator):
        records = curator.ingest_file("/nonexistent/path/file.txt")
        assert len(records) == 1
        assert records[0].record_id.startswith("err_")

    def test_ingest_file_with_source(self, curator):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Content about trading strategy with backtest results and signal processing. " * 5)
            f.flush()
            path = f.name
        try:
            records = curator.ingest_file(path, source="custom_source")
            assert records[0].source.startswith("custom_source")
        finally:
            os.unlink(path)


# ─── search() ────────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_by_keyword(self, curator):
        curator.ingest_text("Machine learning model training data", source="test")
        results = curator.search("machine learning")
        assert len(results) > 0

    def test_search_by_topic(self, curator):
        curator.ingest_text("Trading strategy with backtest", source="test")
        results = curator.search("trading", topic=ContentTopic.TRADING)
        assert len(results) > 0

    def test_search_min_quality(self, curator):
        curator.ingest_text("Short", source="test")  # Low quality error record
        results = curator.search("Short", min_quality=QualityLevel.MEDIUM)
        assert len(results) == 0

    def test_search_no_results(self, curator):
        results = curator.search("xyznonexistent123")
        assert len(results) == 0


# ─── deprecate_old() ─────────────────────────────────────────────────────────

class TestDeprecateOld:
    def test_deprecate_old_records(self, curator):
        record = curator.ingest_text(
            "Old content about trading strategy and backtest results here",
            source="test",
        )
        # Manually set old timestamp
        record.ingested_at = time.time() - (31 * 86400)
        count = curator.deprecate_old()
        assert count == 1
        assert record.deprecated is True

    def test_no_deprecation_for_recent(self, curator):
        curator.ingest_text("Recent trading strategy content for testing", source="test")
        count = curator.deprecate_old()
        assert count == 0


# ─── get_stats() ─────────────────────────────────────────────────────────────

class TestGetStats:
    def test_stats_empty(self, curator):
        stats = curator.get_stats()
        assert stats["total_records"] == 0

    def test_stats_with_records(self, curator):
        curator.ingest_text("Trading strategy content for stats testing", source="test")
        stats = curator.get_stats()
        assert stats["total_records"] >= 1
        assert "by_topic" in stats
        assert "by_quality" in stats


# ─── get_contradictions() ────────────────────────────────────────────────────

class TestGetContradictions:
    def test_get_contradictions_with_pairs(self, curator):
        curator.ingest_text("El sistema debe estar activo siempre para trading", source="test",
                            topic=ContentTopic.TECHNOLOGY)
        curator.ingest_text("El sistema no debe estar activo en trading", source="test2",
                            topic=ContentTopic.TECHNOLOGY)
        contradictions = curator.get_contradictions()
        assert len(contradictions) > 0

    def test_get_contradictions_none(self, curator):
        curator.ingest_text("El sistema funciona correctamente con trading", source="test",
                            topic=ContentTopic.TECHNOLOGY)
        contradictions = curator.get_contradictions()
        assert len(contradictions) == 0


# ─── get_information_curator() singleton ─────────────────────────────────────

class TestGetInformationCurator:
    def test_returns_instance(self):
        import brain.information_curator as mod
        mod._curator = None
        c = get_information_curator()
        assert isinstance(c, InformationCurator)
